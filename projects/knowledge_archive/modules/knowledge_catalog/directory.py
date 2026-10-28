"""集合目录：待办、路由和记录定位；正文与版本由独立集合保存。"""
from pathlib import Path
from copy import deepcopy
import json
from .store import KnowledgeStore, encoded


class Registry(KnowledgeStore):
    def _initialize_storage(self, collection):
        pass


class KnowledgeDirectory:
    def __init__(self, directory, *, owner_node):
        self.registry=Registry(directory,owner_node=owner_node)
        self.directory=self.registry.directory
        self.stores={}
        with self.connection() as db:
            db.execute('CREATE TABLE IF NOT EXISTS record_locations(id TEXT PRIMARY KEY,collection_id TEXT NOT NULL,version INTEGER NOT NULL,deleted INTEGER NOT NULL)')

    def connection(self):return self.registry.connection()
    def catalog(self, **p):return self.registry.catalog(**p)
    def collection(self, target):return self.registry.collection(target)
    def create_collection(self, **p):return self.registry.create_collection(**p)
    def stage(self, **p):return self.registry.stage(**p)
    def intake(self, id, **p):return self.registry.intake(id,**p)
    def route(self, **p):return self.registry.route(**p)

    def bind(self, stores):
        self.stores=dict(stores)
        self.registry.owner_nodes={key:store.owner_node for key,store in stores.items()}
        for collection,store in self.stores.items():
            store.source_lookup=self.source_state
            with store.connection() as source, self.connection() as db:
                rows=source.execute('SELECT id,version,deleted FROM records').fetchall()
                db.executemany('INSERT INTO record_locations VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET collection_id=excluded.collection_id,version=excluded.version,deleted=excluded.deleted WHERE record_locations.collection_id<>excluded.collection_id OR record_locations.version<>excluded.version OR record_locations.deleted<>excluded.deleted',[(r['id'],collection,r['version'],r['deleted']) for r in rows])

    def source_state(self, id):
        with self.connection() as db:row=db.execute('SELECT version,deleted FROM record_locations WHERE id=?',(id,)).fetchone()
        return dict(row) if row else None

    def locate(self, id):
        with self.connection() as db:row=db.execute('SELECT collection_id FROM record_locations WHERE id=?',(id,)).fetchone()
        if row is None:raise KeyError('Unknown record: '+id)
        return self.collection(row['collection_id'])

    def shard(self, collection):
        key=self.collection(collection)['id']
        if key not in self.stores:raise ValueError('集合数据节点未通过 knowledge 频道连接到目录：'+key)
        return self.stores[key]

    def remember(self, record):
        with self.connection() as db:db.execute('INSERT OR REPLACE INTO record_locations VALUES(?,?,?,0)',(record['id'],record['collection_id'],record['version']))
        return record

    def store(self, collection, value, **p):
        return self.remember(self.shard(collection).store(collection,value,**p))

    def fetch(self, id, **p):
        return self.shard(self.locate(id)['id']).fetch(id,**p)

    def update(self, id, content, **p):
        return self.remember(self.shard(self.locate(id)['id']).update(id,content,**p))

    def delete(self, id, **p):
        result=self.shard(self.locate(id)['id']).delete(id,**p)
        with self.connection() as db:db.execute('UPDATE record_locations SET deleted=1 WHERE id=?',(id,))
        return result

    def index(self, collection, **p):return self.shard(collection).index(collection,**p)
    def query(self, collection, **p):return self.shard(collection).query(collection,**p)
    def export(self, collection, **p):return self.shard(collection).export(collection,**p)

    def search(self, query='', *, collection=None, filters=None, limit=10, offset=0, semantic=False, allowed_collections=None):
        self.registry._page(limit,offset)
        targets=[self.collection(collection)] if collection else self.catalog(limit=1000)
        if allowed_collections is not None:targets=[c for c in targets if c['id'] in allowed_collections]
        if semantic:
            if not query.strip():raise ValueError('Semantic queries require text')
            if collection and targets and targets[0]['storage']!='wiki':raise ValueError('RAG directory search requires a Wiki collection')
            targets=[c for c in targets if c['storage']=='wiki']
        hits=[]
        for target in targets:
            result=self.shard(target['id']).search(query,collection=target['id'],filters=filters,limit=1000,semantic=semantic)
            hits.extend(result['items'])
        if semantic:
            lexical=sorted([h for h in hits if h.get('_keyword_match')],key=lambda h:h['id'])
            scores={h['id']:1/(60+i) for i,h in enumerate(lexical,1)}
            for hit in hits:
                ranks=[p['rank'] for p in hit.get('matches',[]) if 'rank' in p]
                if ranks:scores[hit['id']]=scores.get(hit['id'],0)+1/(60+min(ranks))
            hits.sort(key=lambda h:(-scores.get(h['id'],0),h['id']))
        else:hits.sort(key=lambda h:h['id'])
        total=len(hits)
        page=[{k:v for k,v in hit.items() if k!='_keyword_match'} for hit in hits[offset:offset+limit]]
        return dict(items=page,total=total,offset=offset,next_offset=offset+limit if offset+limit<total else None,method='hybrid' if semantic else 'keyword' if query else 'filter')

    def _copy_intake(self, id, store):
        intake=self.intake(id)
        source=self.registry._file('intakes/'+id+'.json')
        store._atomic(store._file('intakes/'+id+'.json'),source.read_bytes())
        original=self.registry._file('intakes/'+id+'.source.json')
        if original.exists():
            descriptor=json.loads(original.read_text(encoding='utf-8'))
            relative=descriptor['archived_path']
            store._atomic(store._file(relative),self.registry._file(relative).read_bytes())
            store._atomic(store._file('intakes/'+id+'.source.json'),original.read_bytes())
        with store.connection() as db:
            db.execute('INSERT OR IGNORE INTO intakes VALUES(?,?,?,?,NULL)',(id,'intakes/'+id+'.json',intake['purpose'],'pending'))
        return intake

    def commit_intake(self, id, collection, indices=None):
        with self.registry.lock:
            intake=self.intake(id)
            if intake['status']=='completed':return intake['result']
            target=self.collection(collection);store=self.shard(target['id'])
            self._copy_intake(id,store)
            selected=intake['remaining_indices'] if indices is None else indices
            result=store.commit_intake(id,target['id'],indices=selected)
            assigned=store.intake(id)['assigned']
            with self.registry.transaction() as db:
                for item in assigned:
                    record=self.remember(store.fetch(item['record_id']))
                    db.execute('INSERT OR REPLACE INTO intake_items VALUES(?,?,?,?)',(id,item['item_index'],target['id'],record['id']))
                assignments=[dict(r) for r in db.execute('SELECT * FROM intake_items WHERE intake_id=? ORDER BY item_index',(id,))]
                remaining=[i for i in range(intake['total_items']) if i not in {r['item_index'] for r in assignments}]
                receipts=[dict(id=r['record_id'],version=self.fetch(r['record_id'])['version'],node_id=self.collection(r['collection_id'])['node_id']) for r in assignments]
                output=dict(intake_id=id,status='partial' if remaining else 'stored',records=receipts,remaining_indices=remaining)
                if 'index' in result:output['index']=result['index']
                db.execute('UPDATE intakes SET status=?,result=? WHERE id=?',('partial' if remaining else 'completed',encoded(output),id))
                signature=self.registry.signature(intake['content'],intake['purpose']) if len(selected)==intake['total_items'] else None
                if signature:db.execute('INSERT OR REPLACE INTO routing_rules VALUES(?,?)',(signature,target['id']))
            return output

    def finish_intake(self, id, action, record_id=None, reason=''):
        self.registry.fetch=self.fetch
        result=self.registry.finish_intake(id,action,record_id,reason)
        if action=='associate' and result['status']=='completed':
            store=self.shard(self.locate(record_id)['id']);self._copy_intake(id,store)
            with store.connection() as db:db.execute('INSERT OR IGNORE INTO record_intakes VALUES(?,?)',(record_id,id))
        return result
