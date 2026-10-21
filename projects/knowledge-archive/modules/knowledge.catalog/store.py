"""Durable knowledge records, typed collections and recoverable materialized storage."""
from contextlib import contextmanager
from hashlib import sha256
import csv
import io
import json
import os
import re
from pathlib import Path
import sqlite3
from threading import local
from uuid import uuid4
from filelock import FileLock

from datanet.components.nodes.csv_node.csv_node import CsvNode
from datanet.components.nodes.sqlite_node.sqlite_node import SqliteNode, quote_identifier


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def text_of(value):
    return value if isinstance(value, str) else encoded(value)


class KnowledgeStore:
    def __init__(self, directory, *, embedding_config=None, owner_node):
        self.owner_node=owner_node
        self.owner_nodes={}
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / 'catalog.sqlite3'
        self.lock = FileLock(str(self.directory / '.write.lock'), timeout=30)
        self._local = local()
        self.embedding_config = embedding_config
        self.indexes = {}
        self.embed_model = None
        self._batch_ids = None
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS collections(
                    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, storage TEXT NOT NULL,
                    description TEXT NOT NULL, schema_json TEXT NOT NULL, tags TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records(
                    id TEXT PRIMARY KEY, collection_id TEXT NOT NULL, record_key TEXT NOT NULL,
                    version INTEGER NOT NULL, hash TEXT NOT NULL, raw_path TEXT NOT NULL,
                    state TEXT NOT NULL, index_state TEXT NOT NULL, metadata TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0, UNIQUE(collection_id,record_key));
                CREATE INDEX IF NOT EXISTS records_collection ON records(collection_id,deleted);
                CREATE TABLE IF NOT EXISTS versions(
                    record_id TEXT NOT NULL, version INTEGER NOT NULL, raw_path TEXT NOT NULL,
                    hash TEXT NOT NULL, metadata TEXT NOT NULL, sources_json TEXT NOT NULL, PRIMARY KEY(record_id,version));
                CREATE TABLE IF NOT EXISTS references_to_sources(
                    record_id TEXT NOT NULL, source_id TEXT NOT NULL, source_version INTEGER NOT NULL,
                    PRIMARY KEY(record_id,source_id));
                CREATE TABLE IF NOT EXISTS intake_items(intake_id TEXT NOT NULL, item_index INTEGER NOT NULL, collection_id TEXT NOT NULL, record_id TEXT NOT NULL, PRIMARY KEY(intake_id,item_index));
                CREATE TABLE IF NOT EXISTS record_intakes(record_id TEXT NOT NULL,intake_id TEXT NOT NULL,PRIMARY KEY(record_id,intake_id));
                CREATE TABLE IF NOT EXISTS routing_rules(signature TEXT PRIMARY KEY, collection_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS wiki_pages(record_id TEXT PRIMARY KEY,title TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS wiki_names(collection_id TEXT NOT NULL,name TEXT NOT NULL,record_id TEXT NOT NULL,
                    PRIMARY KEY(collection_id,name,record_id));
                CREATE TABLE IF NOT EXISTS intakes(
                    id TEXT PRIMARY KEY, raw_path TEXT NOT NULL, purpose TEXT NOT NULL,
                    status TEXT NOT NULL, result TEXT);
                CREATE VIRTUAL TABLE IF NOT EXISTS searchable USING fts5(record_id UNINDEXED, content, tokenize='trigram');
                CREATE VIRTUAL TABLE IF NOT EXISTS short_search USING fts5(record_id UNINDEXED, tokens);
            ''')
        self.recover()

    @contextmanager
    def connection(self):
        shared=getattr(self._local,'transaction',None)
        if shared is not None:
            yield shared
            return
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            self._local.transaction=db
            try:yield db
            finally:self._local.transaction=None

    def _file(self, relative):
        result = (self.directory / relative).resolve()
        if not result.is_relative_to(self.directory):
            raise ValueError('Storage path escaped knowledge directory')
        return result

    def _atomic(self,path,data):
        from datanet.core.text_node import TextFileNode
        path.parent.mkdir(parents=True,exist_ok=True)
        TextFileNode._atomic_bytes(path,data)

    def catalog(self, query='', limit=50, offset=0):
        self._page(limit, offset)
        with self.connection() as db:
            rows = db.execute('SELECT * FROM collections WHERE name LIKE ? OR description LIKE ? ORDER BY name LIMIT ? OFFSET ?',
                              ('%' + query + '%', '%' + query + '%', limit, offset)).fetchall()
        return [self._collection(row) for row in rows]

    def owner_for(self, collection):
        return self.owner_nodes.get(collection,self.owner_node)

    def _collection(self,row):
        item = dict(row)
        item['schema'] = json.loads(item.pop('schema_json'))
        item['tags'] = json.loads(item['tags'])
        item['node_id'] = self.owner_for(item['id'])
        return item

    def collection(self, target):
        if not isinstance(target, str):
            raise TypeError('Collection ID or name must be a string')
        # Collection IDs and record IDs are data keys, independent of graph node IDs.
        with self.connection() as db:
            row = db.execute('SELECT * FROM collections WHERE id=? OR name=?', (target, target)).fetchone()
        if row is None:
            raise KeyError('Unknown collection: ' + target)
        return self._collection(row)

    def create_collection(self, name, storage, description='', schema=None, tags=None):
        if storage not in {'csv', 'sqlite', 'rag', 'wiki'}:
            raise ValueError('Choose csv, sqlite, rag or wiki')
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Collection name is required')
        schema = schema or {}
        if not isinstance(schema, dict) or any(not isinstance(k, str) or not k or k == '_id' or v not in {'string', 'integer', 'number', 'boolean', 'object', 'array'} for k, v in schema.items()):
            raise ValueError('Schema maps field names to string/integer/number/boolean/object/array')
        if storage in {'csv', 'sqlite'} and not schema:
            raise ValueError('Structured collections require a field schema')
        if any(not isinstance(tag, str) for tag in (tags or [])):
            raise TypeError('Tags must be strings')
        with self.lock, self.connection() as db:
            old = db.execute('SELECT * FROM collections WHERE name=?', (name,)).fetchone()
            if old:
                result = self._collection(old)
                if result['storage'] != storage or result['schema'] != schema:
                    raise ValueError('An existing collection has a different storage type or schema')
                return dict(result, reused=True)
            id = uuid4().hex
            candidate=dict(id=id,name=name,storage=storage,description=description,schema=schema,tags=tags or [],node_id=self.owner_for(id))
            self._initialize_storage(candidate)
            db.execute('INSERT INTO collections VALUES(?,?,?,?,?,?)', (id, name, storage, description, encoded(schema), encoded(tags or [])))
        result = self.collection(id)
        return dict(result, reused=False)

    def _initialize_storage(self, collection):
        directory = self._file('data/' + collection['id'])
        directory.mkdir(parents=True, exist_ok=True)
        if collection['storage'] == 'csv':
            path = directory / 'records.csv'
            if not path.exists():
                buffer = io.StringIO(newline='')
                csv.writer(buffer).writerow(['_id', *collection['schema']])
                self._atomic(path, buffer.getvalue().encode('utf-8-sig'))
        elif collection['storage'] == 'sqlite':
            types = {'string': 'TEXT', 'integer': 'INTEGER', 'number': 'REAL', 'boolean': 'INTEGER', 'object': 'TEXT', 'array': 'TEXT'}
            columns = ','.join(quote_identifier(k) + ' ' + types[t] for k, t in collection['schema'].items())
            db = sqlite3.connect(directory / 'records.sqlite3')
            try:
                with db:
                    db.execute('CREATE TABLE IF NOT EXISTS records(_id TEXT PRIMARY KEY,' + columns + ')')
                    for field, kind in collection['schema'].items():
                        if kind not in {'object','array'}:
                            db.execute('CREATE INDEX IF NOT EXISTS '+quote_identifier('idx_'+field)+' ON records('+quote_identifier(field)+')')
            finally:
                db.close()

    def _driver(self, collection):
        directory = self._file('data/' + collection['id'])
        if collection['storage'] == 'csv':
            return CsvNode(collection['node_id'], collection['name'], 'record', directory / 'records.csv', '_id', dtype={k: {'string':'string','integer':'Int64','number':'Float64','boolean':'boolean','object':'string','array':'string'}[v] for k,v in collection['schema'].items()})
        return SqliteNode(collection['node_id'], collection['name'], 'record', directory / 'records.sqlite3', 'records', '_id')

    @staticmethod
    def _validate_content(collection, value):
        if collection['storage'] in {'wiki', 'rag'}:
            if not isinstance(value, str):
                raise TypeError('Wiki pages and documents must be strings')
            return
        if not isinstance(value, dict) or set(value) - collection['schema'].keys():
            raise ValueError('Record fields must belong to the collection schema')
        types = {'string': (str,), 'integer': (int,), 'number': (int, float), 'boolean': (bool,), 'object': (dict,), 'array': (list,)}
        for key, item in value.items():
            if item is not None and type(item) not in types[collection['schema'][key]]:
                raise TypeError('Field type mismatch: ' + key)

    def store(self, collection, value, *, key=None, metadata=None, sources=None, expected_version=None):
        collection = self.collection(collection)
        value = self.normalize(collection,value)
        self._validate_content(collection, value)
        metadata = metadata or {}
        payload = encoded(value).encode('utf-8')
        hash = sha256(payload).hexdigest()
        key = key or hash
        if not isinstance(key, str) or not key:
            raise ValueError('Record key must be a nonempty string')
        if collection['storage']=='wiki':
            from datanet.llm_wiki.navigation import identity
            identity(dict(id='',key=key,content=value,metadata=metadata))
        with self.lock:
            with self.connection() as db:
                old = db.execute('SELECT * FROM records WHERE collection_id=? AND record_key=?', (collection['id'], key)).fetchone()
                if expected_version is not None and (old is None or old['version'] != expected_version):
                    raise ValueError('Version conflict; fetch the current record before updating')
                references = []
                for source in dict.fromkeys(sources or []):
                    row = db.execute('SELECT version,deleted FROM records WHERE id=?', (source,)).fetchone()
                    if row is None or row['deleted']:
                        raise ValueError('Unknown or deleted source: ' + source)
                    references.append((source, row['version']))
                previous_refs=[(r['source_id'],r['source_version']) for r in db.execute('SELECT source_id,source_version FROM references_to_sources WHERE record_id=?',(old['id'],))] if old else []
                if old and not old['deleted'] and old['hash'] == hash and json.loads(old['metadata']) == metadata and sorted(previous_refs)==sorted(references):
                    if self._batch_ids is not None and old['state']=='pending': self._batch_ids.append(old['id'])
                    elif old['state']=='pending':self._materialize(old['id'])
                    return dict(self.fetch(old['id']), unchanged=True)
                id, version = (old['id'], old['version'] + 1) if old else (uuid4().hex, 1)
                relative = 'sources/' + id + '/' + str(version) + '.json'
                self._atomic(self._file(relative), payload)
                db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?)', (id, version, relative, hash, encoded(metadata), encoded(references)))
                db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,0) ON CONFLICT(id) DO UPDATE SET version=excluded.version,hash=excluded.hash,raw_path=excluded.raw_path,state=excluded.state,index_state=excluded.index_state,metadata=excluded.metadata,deleted=0',
                           (id, collection['id'], key, version, hash, relative, 'pending', 'pending', encoded(metadata)))
                db.execute('DELETE FROM references_to_sources WHERE record_id=?', (id,))
                db.executemany('INSERT INTO references_to_sources VALUES(?,?,?)', [(id, source, ver) for source, ver in references])
            if self._batch_ids is not None:
                self._batch_ids.append(id)
                return dict(id=id,version=version,node_id=collection['node_id'])
            self._materialize(id)
            result = self.fetch(id)
            if collection['storage'] in {'rag','wiki'}:
                result['index'] = self.index(collection['id'])
            return result

    def _materialize(self, id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM records WHERE id=?', (id,)).fetchone()
        collection = self.collection(row['collection_id'])
        self._initialize_storage(collection)
        value = json.loads(self._file(row['raw_path']).read_text(encoding='utf-8'))
        if collection['storage'] in {'csv', 'sqlite'}:
            converted = {k: encoded(v) if isinstance(v, (dict, list)) else v for k, v in value.items()}
            result = self._driver(collection).write(id, {'_id': id, **converted})
            if result.status != 'ok':
                raise RuntimeError('; '.join(result.errors))
        else:
            self._atomic(self._file('data/' + collection['id'] + '/pages/' + id + '.md'), value.encode('utf-8'))
        with self.transaction() as db:
            if collection['storage']=='wiki':
                self._wiki_identity(dict(id=id,collection_id=collection['id'],key=row['record_key'],content=value,metadata=json.loads(row['metadata'])))
            db.execute('DELETE FROM searchable WHERE record_id=?', (id,))
            db.execute('INSERT INTO searchable VALUES(?,?)', (id, text_of(value)))
            self._short_index(db,id,text_of(value))
            db.execute("UPDATE records SET state='ready',index_state=? WHERE id=?", ('pending' if collection['storage'] in {'rag','wiki'} else 'ready', id))

    def _wiki_identity(self, record):
        from datanet.llm_wiki.navigation import identity
        title,names=identity(record)
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO wiki_pages VALUES(?,?)',(record['id'],title))
            db.execute('DELETE FROM wiki_names WHERE record_id=?',(record['id'],))
            db.executemany('INSERT INTO wiki_names VALUES(?,?,?)',[(record['collection_id'],name,record['id']) for name in names])

    def _entry(self, record):
        collection=self.collection(record['collection_id'])
        result=dict(id=record['id'],node_id=collection['node_id'],version=record['version'],storage=collection['storage'],fetch=dict(id=record['id'],version=record['version']))
        if collection['storage']=='wiki':
            with self.connection() as db:title=db.execute('SELECT title FROM wiki_pages WHERE record_id=?',(record['id'],)).fetchone()
            result.update(title=title['title'] if title else record['key'],wiki_link='[['+record['id']+']]',read=dict(id=record['id'],version=record['version'],view='section',section_id='document'))
        return result

    def _wiki_links(self,record,offset=0,limit=40):
        from datanet.llm_wiki.navigation import references,target_parts
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:raise ValueError('Link offset must be nonnegative and limit 1..100')
        links=references(record);items=[]
        for target,label in links[offset:offset+limit]:
            name,anchor=target_parts(target)
            with self.connection() as db:
                rows=db.execute("SELECT r.id,r.collection_id,r.record_key AS key,r.version FROM wiki_names n JOIN records r ON r.id=n.record_id WHERE n.collection_id=? AND n.name=? AND r.deleted=0 AND r.state='ready' ORDER BY r.id LIMIT 11",
                                (record['collection_id'],(name or record['id']).casefold())).fetchall()
            item=dict(target=target,label=label,anchor=anchor,status='resolved' if len(rows)==1 else 'ambiguous' if rows else 'unresolved')
            if len(rows)==1:
                item.update(self._entry(dict(rows[0])))
                if anchor:item['read']=dict(id=item['id'],version=item['version'],view='outline')
            elif rows:
                item['candidates']=[self._entry(dict(row)) for row in rows[:10]];item['candidates_truncated']=len(rows)>10
            items.append(item)
        return dict(links=items,total_links=len(links),links_next_fetch=dict(id=record['id'],version=record['version'],view='links',offset=offset+limit,limit=limit) if offset+limit<len(links) else None,
                    link_versions='target_current_at_read')

    def recover(self):
        with self.connection() as db:
            ids = [r['id'] for r in db.execute("SELECT id FROM records WHERE state='pending' AND deleted=0")]
        for id in ids:
            self._materialize(id)

    def fetch(self, id, version=None, *, view='full', section_id=None, start_line=None, end_line=None, offset=0, max_chars=6000, limit=40):
        with self.connection() as db:
            row = db.execute('SELECT * FROM records WHERE id=?', (id,)).fetchone()
            if row is None or (row['deleted'] and version is None):
                raise KeyError('Record not found: ' + id)
            record = dict(row)
            if version is not None:
                previous = db.execute('SELECT * FROM versions WHERE record_id=? AND version=?', (id, version)).fetchone()
                if previous is None:
                    raise KeyError('Version not found')
                record.update(dict(previous))
            references = [dict(r) for r in db.execute('SELECT x.source_id,x.source_version,r.version AS current_version,r.deleted FROM references_to_sources x LEFT JOIN records r ON r.id=x.source_id WHERE x.record_id=?', (id,))]
        if version is not None:
            references=[]
            with self.connection() as db:
                for source_id,source_version in json.loads(record['sources_json']):
                    current=db.execute('SELECT version,deleted FROM records WHERE id=?',(source_id,)).fetchone()
                    references.append(dict(source_id=source_id,source_version=source_version,current_version=current['version'] if current else None,deleted=current['deleted'] if current else True))
        with self.connection() as db:
            origin_ids=[r['intake_id'] for r in db.execute('SELECT intake_id FROM record_intakes WHERE record_id=?',(id,))]
        origins=[]
        for origin_id in origin_ids:
            file=self._file('intakes/'+origin_id+'.source.json')
            if file.exists():
                source=json.loads(file.read_text(encoding='utf-8'));source['archived_path']=str(self._file(source['archived_path']));origins.append(source)
        value = json.loads(self._file(record['raw_path']).read_text(encoding='utf-8'))
        result = dict(id=id, node_id=self.owner_for(record['collection_id']), collection_id=record['collection_id'], key=record['record_key'], version=record['version'], content=value,
                    metadata=json.loads(record['metadata']), origins=origins, state=record['state'], index_state=record['index_state'], sources=references,
                    needs_refresh=any(r['deleted'] or r['current_version'] != r['source_version'] for r in references),
                    original_path=str(self._file(record['raw_path'])), fetch=dict(id=id, version=record['version']))
        result['evidence']=dict(node_id=result['node_id'],locator=id,version=result['version'])
        is_wiki=self.collection(record['collection_id'])['storage']=='wiki'
        if is_wiki:
            from datanet.llm_wiki.navigation import identity
            result['page']=self._entry(dict(id=id,collection_id=record['collection_id'],key=record['record_key'],version=record['version']))
            result['page']['title']=identity(result)[0]
        if view=='full':
            if is_wiki:result.update(self._wiki_links(result,0,limit))
            return result
        from datanet.document_structure.structure import DocumentStructure
        if not isinstance(value,str):raise ValueError('Outline and context views require a text document')
        structure=DocumentStructure(value)
        reference=dict(id=id,version=result['version'])
        summary={k:v for k,v in result.items() if k not in {'content','original_path','metadata'}}
        if view=='links':
            if not is_wiki:raise ValueError('Link navigation requires a Wiki collection')
            selected=self._wiki_links(result,offset,limit)
            return dict(**summary,**selected,view=view,is_excerpt=True,full_fetch=reference)
        if view=='outline':
            selected=structure.outline(offset,limit)
            for heading in selected['outline']:heading['read']=dict(**reference,view='section',section_id=heading['section_id'])
            continuation=dict(**reference,view='outline',offset=selected['next_offset'],limit=limit) if selected['next_offset'] is not None else None
        else:
            selected=structure.context(view=view,section_id=section_id,start_line=start_line,end_line=end_line,offset=offset,max_chars=max_chars)
            for heading in [selected['section'],*selected['children'],selected['previous'],selected['next']]:
                if heading:heading['read']=dict(**reference,view='section',section_id=heading['section_id'])
            for ancestor in selected['ancestor_context']:ancestor['section']['read']=dict(**reference,view='section',section_id=ancestor['section']['section_id'])
            continuation=dict(**reference,view=view,offset=selected['next_offset'],max_chars=max_chars) if selected['next_offset'] is not None else None
            if continuation is not None:
                if view=='section':continuation['section_id']=section_id or 'document'
                else:continuation.update(start_line=start_line,**({'end_line':end_line} if end_line is not None else {}))
        if is_wiki:
            selected['links_fetch']=dict(**reference,view='links')
            if view in ('section','window'):
                local_links=self._wiki_links(dict(result,content=selected['content']),0,min(limit,10))
                selected['links']=local_links['links'];selected['links_truncated']=local_links['total_links']>len(local_links['links'])
                selected['link_versions']=local_links['link_versions']
        return dict(**summary,**selected,view=view,is_excerpt=True,next_fetch=continuation,full_fetch=reference)

    @staticmethod
    def _page(limit, offset):
        if type(limit) is not int or not 1 <= limit <= 1000 or type(offset) is not int or offset < 0:
            raise ValueError('limit must be 1..1000 and offset nonnegative')

    @staticmethod
    def _short_index(db,id,text):
        tokens=set()
        for word in re.findall(r'[\u3400-\u9fff]+',text):
            tokens.update(word)
            tokens.update(word[i:i+2] for i in range(len(word)-1))
        db.execute('DELETE FROM short_search WHERE record_id=?',(id,))
        db.execute('INSERT INTO short_search VALUES(?,?)',(id,' '.join(sorted(tokens))))

    def search(self, query='', *, collection=None, filters=None, limit=10, offset=0, semantic=False, allowed_collections=None):
        self._page(limit, offset)
        scope = self.collection(collection) if collection else None
        parameters, clauses = [], ['deleted=0', "state='ready'"]
        if scope:
            clauses.append('collection_id=?'); parameters.append(scope['id'])
        if allowed_collections is not None:
            if not allowed_collections:
                return dict(items=[],total=0,offset=offset,next_offset=None,method='keyword')
            clauses.append('collection_id IN ('+','.join('?' for _ in allowed_collections)+')')
            parameters.extend(allowed_collections)
        if filters:
            if not scope or scope['storage'] not in {'csv','sqlite'}:
                raise ValueError('Structured filters require a CSV or SQLite collection')
            if set(filters)-scope['schema'].keys():
                raise ValueError('Unknown filter field')
            converted={k:encoded(v) if isinstance(v,(dict,list)) else v for k,v in filters.items()}
            matched=self._driver(scope).read(dict(method='filter',filters=converted))
            if matched.status!='ok':raise RuntimeError('; '.join(matched.errors))
            ids=[r['_id'] for r in matched.items]
            if not ids:return dict(items=[],total=0,offset=offset,next_offset=None,method='filter')
            clauses.append('id IN ('+','.join('?' for _ in ids)+')');parameters.extend(ids)
        if query:
            if len(query)>=3:
                clauses.append('id IN (SELECT record_id FROM searchable WHERE searchable MATCH ?)')
                parameters.append('"'+query.replace('"','""')+'"')
            elif re.fullmatch(r'[\u3400-\u9fff]{1,2}',query):
                clauses.append('id IN (SELECT record_id FROM short_search WHERE short_search MATCH ?)');parameters.append('"'+query+'"')
            else:
                clauses.append('id IN (SELECT record_id FROM searchable WHERE instr(content,?)>0)');parameters.append(query)
        where=' AND '.join(clauses)
        with self.connection() as db:
            total=db.execute('SELECT COUNT(*) FROM records WHERE '+where,parameters).fetchone()[0]
            rows=db.execute('SELECT * FROM records WHERE '+where+' ORDER BY id LIMIT ? OFFSET ?', [*parameters,limit+offset if semantic else limit,0 if semantic else offset]).fetchall()
            hits=[]
            for row in rows:
                excerpt=db.execute('SELECT substr(content,1,500) FROM searchable WHERE record_id=?',(row['id'],)).fetchone()
                hits.append(dict(id=row['id'],node_id=self.owner_for(row['collection_id']),collection_id=row['collection_id'],key=row['record_key'],version=row['version'],snippet=excerpt[0] if excerpt else '',metadata=json.loads(row['metadata']),fetch=dict(id=row['id'],version=row['version'])))
        if semantic:
            if not query.strip():
                raise ValueError('Semantic queries require text')
            targets = [scope] if scope else [c for c in self.catalog(limit=1000) if c['storage'] in {'rag','wiki'}]
            if allowed_collections is not None:
                targets = [c for c in targets if c['id'] in allowed_collections]
            if not targets or any(c['storage'] not in {'rag','wiki'} for c in targets):
                raise ValueError('Semantic search requires an accessible RAG or Wiki collection; use field queries for structured storage')
            scores = {r['id']: 1 / (60 + i) for i, r in enumerate(hits, 1)}
            all_hits = {r['id']: r for r in hits}
            prepared={}
            for target in targets:
                with self.connection() as db:count=db.execute("SELECT count(*) FROM records WHERE collection_id=? AND deleted=0 AND state='ready'",(target['id'],)).fetchone()[0]
                if not count:continue
                index = self._index(target)
                if index is None:
                    raise RuntimeError('Semantic search needs the application embedding configuration; keyword search remains available')
                result = index.search(query, top_k=min(100,3*(limit + offset)))
                seen=set()
                for hit in result.items:
                    id = Path(hit['metadata']['file_name']).stem
                    try:
                        if id not in prepared:
                            from datanet.document_structure.structure import DocumentStructure
                            record=self.fetch(id)
                            prepared[id]=(record,DocumentStructure(record['content']))
                        record,structure=prepared[id]
                    except KeyError:continue
                    if record['index_state']!='ready':continue
                    indexed_hash=hit['metadata'].get('source_sha256')
                    if indexed_hash and indexed_hash!=sha256(record['content'].encode('utf8')).hexdigest():continue
                    location=structure.locate(hit['text'],hit.get('start_char'),hit.get('end_char'))
                    passage=dict(chunk_id=hit['chunk_id'],score=hit['score'],location_verified=location is not None)
                    if location:
                        section=structure.at(location['start_char'])
                        passage.update(location=location,section=structure.describe(section),
                            section_fetch=dict(**record['fetch'],view='section',section_id=section['section_id']),
                            window_fetch=dict(**record['fetch'],view='window',start_line=max(1,location['start_line']-3),end_line=min(len(structure.lines),location['end_line']+3)))
                    else:passage['outline_fetch']=dict(**record['fetch'],view='outline')
                    if id not in seen:
                        seen.add(id)
                        scores[id]=scores.get(id,0)+1/(60+len(seen))
                        all_hits[id]=dict(id=id,node_id=record['node_id'],collection_id=record['collection_id'],key=record['key'],version=record['version'],snippet=hit['text'][:500],fetch=record['fetch'],outline_fetch=dict(**record['fetch'],view='outline'),matches=[passage])
                    elif len(all_hits[id]['matches'])<3:
                        all_hits[id]['matches'].append(passage)
            hits = [all_hits[id] for id in sorted(scores, key=lambda k: (-scores[k], k))]
        if semantic: total=len(hits); hits=hits[offset:offset+limit]
        for hit in hits:hit['entry']=self._entry(hit)
        return dict(items=hits,total=total,offset=offset,next_offset=offset+limit if offset+limit<total else None,method='hybrid' if semantic else 'keyword' if query else 'filter')

    def _index(self, collection):
        if not self.embedding_config:
            return None
        if collection['id'] not in self.indexes:
            from datanet.components.nodes.llamaindex_node.llamaindex_node import LlamaIndexNode
            node = LlamaIndexNode(collection['node_id'], collection['name'], self._file('indexes/' + collection['id']), embedding_config=self.embedding_config)
            if self.embed_model is not None:
                node._embed_model = self.embed_model
            self.indexes[collection['id']] = node
        return self.indexes[collection['id']]

    def index(self, collection, rebuild=False):
        collection = self.collection(collection)
        if collection['storage'] not in {'rag','wiki'}:raise ValueError('Semantic indexes require a RAG or Wiki collection')
        if type(rebuild) is not bool:raise TypeError('rebuild must be boolean')
        with self.lock:
            node = self._index(collection)
            if node is None:
                return dict(status='unavailable', reason='embedding_not_configured', keyword_search=True)
            with self.connection() as db:
                rows = db.execute("SELECT id FROM records WHERE collection_id=? AND deleted=0 AND state='ready'"+("" if rebuild else " AND index_state='pending'"), (collection['id'],)).fetchall()
                deleted = db.execute("SELECT id FROM records WHERE collection_id=? AND deleted=1 AND index_state='delete_pending'",(collection['id'],)).fetchall()
            if deleted:
                node.delete_documents([str(self._file('data/'+collection['id']+'/pages/'+r['id']+'.md')) for r in deleted])
                with self.connection() as db:
                    db.executemany("UPDATE records SET index_state='deleted' WHERE id=?",[(r['id'],) for r in deleted])
            if not rows:
                return dict(status='ready', indexed=0)
            if collection['storage']=='wiki':
                for row in rows:self._wiki_identity(self.fetch(row['id']))
            try:
                result = node.update_documents([str(self._file('data/' + collection['id'] + '/pages/' + r['id'] + '.md')) for r in rows])
                self.embed_model = node.embed_model
                with self.connection() as db:
                    db.executemany("UPDATE records SET index_state='ready' WHERE id=?", [(r['id'],) for r in rows])
                return dict(status='ready', indexed=len(rows), details=result)
            except Exception as error:
                return dict(status='pending', error=str(error), keyword_search=True)

    def update(self, id, content, *, expected_version, metadata=None, sources=None):
        previous = self.fetch(id)
        return self.store(previous['collection_id'], content, key=previous['key'], metadata=previous['metadata'] if metadata is None else metadata,
                          sources=[s['source_id'] for s in previous['sources']] if sources is None else sources, expected_version=expected_version)

    def query(self, collection, *, fields=None, filters=None, group_by=None, aggregate=None, order_by=None, descending=False, limit=50, offset=0):
        """Bound identifiers and parameters; no model-authored SQL is executed."""
        self._page(limit,offset)
        target=self.collection(collection)
        if target['storage']!='sqlite':raise ValueError('Database queries require a SQLite collection')
        allowed=set(target['schema'])|{'_id'}
        fields=fields or ['_id',*target['schema']]
        group_by=group_by or []
        filters=filters or {}
        requested=set(fields)|set(filters)|set(group_by)|({order_by} if order_by else set())
        if not requested<=allowed:raise ValueError('Unknown database field')
        def column(name):return 'd.'+quote_identifier(name)
        columns=[column(k) for k in fields]
        if aggregate:
            function=aggregate.get('function','count')
            field=aggregate.get('field')
            if function not in {'count','sum','avg','min','max'}:raise ValueError('Unsupported aggregation')
            if field is not None and field not in allowed:raise ValueError('Unknown aggregate field')
            if function!='count' and field is None:raise ValueError('aggregate.field is required for '+function+'; fields only selects returned columns')
            columns=[column(k) for k in group_by]+[function+'('+('*' if field is None else column(field))+') AS value']
        sql='SELECT '+','.join(columns)+' FROM records d JOIN kb.records m ON m.id=d._id WHERE m.deleted=0 AND m.state=\'ready\''
        parameters=[]
        for field,value in filters.items():
            sql+=' AND '+column(field)+(' IS NULL' if value is None else '=?')
            if value is not None:parameters.append(encoded(value) if isinstance(value,(dict,list)) else value)
        if aggregate and group_by:sql+=' GROUP BY '+','.join(column(k) for k in group_by)
        if order_by:sql+=' ORDER BY '+column(order_by)+(' DESC' if descending else ' ASC')
        sql+=' LIMIT ? OFFSET ?';parameters.extend([limit,offset])
        db=sqlite3.connect(self._file('data/'+target['id']+'/records.sqlite3'))
        db.row_factory=sqlite3.Row
        try:
            db.execute('ATTACH DATABASE ? AS kb',(str(self.database),))
            rows=[dict(row) for row in db.execute(sql,parameters)]
        finally:db.close()
        return dict(items=rows,node_id=target['node_id'],collection_id=target['id'],offset=offset)

    def delete(self, id, *, expected_version):
        with self.lock, self.connection() as db:
            row = db.execute('SELECT version FROM records WHERE id=? AND deleted=0', (id,)).fetchone()
            if row is None:
                raise KeyError('Record not found')
            if row['version'] != expected_version:
                raise ValueError('Version conflict')
            db.execute("UPDATE records SET deleted=1,index_state='delete_pending' WHERE id=?", (id,))
            db.execute('DELETE FROM searchable WHERE record_id=?', (id,))
            db.execute('DELETE FROM short_search WHERE record_id=?',(id,))
        return dict(id=id, deleted=True, history_retained=True)

    def export(self, collection, format='json'):
        collection = self.collection(collection)
        with self.connection() as db:
            ids = [r['id'] for r in db.execute('SELECT id FROM records WHERE collection_id=? AND deleted=0 ORDER BY record_key', (collection['id'],))]
        records = [self.fetch(id) for id in ids]
        if format=='wiki':
            if collection['storage']!='wiki':raise ValueError('Wiki export requires a wiki collection')
            from datanet.wiki.mkdocs import MarkdownWiki
            pages=[]
            for record in records:
                heading=next((line[2:].strip() for line in record['content'].splitlines() if line.startswith('# ')),record['key'])
                references='\n'.join('- '+source['source_id']+' v'+str(source['source_version']) for source in record['sources'])
                pages.append(dict(id=record['id'],title=heading,content=record['content']+'\n\n记录：'+record['id']+' v'+str(record['version'])+('\n\n来源：\n'+references if references else '')))
            return MarkdownWiki(self._file('exports/'+collection['id'])).publish(collection['name'],pages)
        if format == 'json':
            return dict(format='json', content=encoded(records), count=len(records))
        if format != 'csv' or collection['storage'] not in {'csv', 'sqlite'}:
            raise ValueError('CSV export requires a structured collection')
        buffer = io.StringIO(newline=''); writer = csv.DictWriter(buffer, fieldnames=['_id', *collection['schema']])
        writer.writeheader()
        for record in records:
            writer.writerow({'_id': record['id'], **{k: encoded(v) if isinstance(v, (dict, list)) else v for k, v in record['content'].items()}})
        return dict(format='csv', content=buffer.getvalue(), count=len(records))

    def stage(self, content, purpose='', original_file=None):
        id = uuid4().hex; relative = 'intakes/' + id + '.json'
        self._atomic(self._file(relative), encoded(content).encode('utf-8'))
        if original_file:
            source=Path(original_file);data=source.read_bytes();archived='intakes/'+id+'/original'+source.suffix.lower()
            self._atomic(self._file(archived),data)
            self._atomic(self._file('intakes/'+id+'.source.json'),encoded(dict(name=source.name,archived_path=archived,hash=sha256(data).hexdigest())).encode('utf-8'))
        with self.connection() as db:
            db.execute('INSERT INTO intakes VALUES(?,?,?,?,NULL)', (id, relative, purpose, 'pending'))
        return self.intake(id)

    def intake(self, id, *, preview=False, offset=0, limit=None):
        with self.connection() as db:
            row = db.execute('SELECT * FROM intakes WHERE id=?', (id,)).fetchone()
        if row is None:
            raise KeyError('Intake not found')
        with self.connection() as db:
            assigned=[dict(r) for r in db.execute('SELECT item_index,collection_id,record_id FROM intake_items WHERE intake_id=? ORDER BY item_index',(id,))]
        content=json.loads(self._file(row['raw_path']).read_text(encoding='utf-8'));count=len(content) if isinstance(content,list) else 1
        source_file=self._file('intakes/'+id+'.source.json')
        remaining=[i for i in range(count) if i not in {r['item_index'] for r in assigned}]
        truncated=False
        if preview:
            size=len(content) if isinstance(content,(list,str)) else 1
            limit=limit if limit is not None else 20 if isinstance(content,list) else 6000
            if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=10000:raise ValueError('Invalid intake page')
            if isinstance(content,(list,str)):content=content[offset:offset+limit]
            truncated=offset+limit<size
        else:size=count
        return dict(assigned=assigned[:50] if preview else assigned,remaining_indices=remaining[:50] if preview else remaining,remaining_count=len(remaining),total_items=count,content_size=size,truncated=truncated,next_offset=offset+limit if truncated else None,original_source=json.loads(source_file.read_text(encoding='utf-8')) if source_file.exists() else None,id=id,purpose=row['purpose'],status=row['status'],content=content,result=json.loads(row['result']) if row['result'] else None)

    def finish_intake(self, id, action, record_id=None, reason=''):
        with self.lock, self.connection() as db:
            intake=self.intake(id)
            if intake['status'] in ('completed','dismissed'):return intake['result']
            if action=='dismiss':
                if not reason.strip():raise ValueError('Explain why this is not source material')
                result=dict(intake_id=id,status='dismissed',reason=reason)
            elif action=='associate':
                if isinstance(intake['content'],list):raise ValueError('Use kb_store with indices to archive a batch')
                record=self.fetch(record_id)
                body=record['content']
                if isinstance(body,str) and not isinstance(intake['content'],str):
                    try:body=json.loads(body)
                    except ValueError:pass
                if body!=intake['content']:raise ValueError('Existing record content differs from intake; archive or update it instead')
                with db:
                    db.execute('INSERT OR REPLACE INTO intake_items VALUES(?,?,?,?)',(id,0,record['collection_id'],record_id))
                    db.execute('INSERT OR IGNORE INTO record_intakes VALUES(?,?)',(record_id,id))
                result=dict(intake_id=id,status='completed',records=[dict(id=record_id,version=record['version'],node_id=record['node_id'])],remaining_indices=[])
            else:raise ValueError('Choose associate or dismiss')
            db.execute('UPDATE intakes SET status=?,result=? WHERE id=?',(result['status'],encoded(result),id))
            return result

    @staticmethod
    def signature(content,purpose):
        values=content if isinstance(content,list) else [content]
        if values and all(isinstance(v,dict) for v in values):
            shapes=sorted(set(encoded({k:type(x).__name__ for k,x in v.items()}) for v in values))
            return sha256(encoded([purpose,shapes]).encode()).hexdigest()
        if purpose.strip():return sha256(encoded([purpose,type(content).__name__]).encode()).hexdigest()
        return None

    @staticmethod
    def normalize(collection,value):
        if collection['storage'] not in {'csv','sqlite'} or not isinstance(value,dict):return value
        result=dict(value)
        for key,kind in collection['schema'].items():
            item=result.get(key)
            if not isinstance(item,str):continue
            if kind=='integer' and re.fullmatch(r'[+-]?\d+',item.strip()):result[key]=int(item)
            elif kind=='number':result[key]=float(item)
            elif kind=='boolean' and item.lower() in {'true','false'}:result[key]=item.lower()=='true'
            elif kind in {'object','array'}:result[key]=json.loads(item)
        return result

    def route(self,id):
        intake=self.intake(id);signature=self.signature(intake['content'],intake['purpose'])
        with self.connection() as db:
            row=db.execute('SELECT collection_id FROM routing_rules WHERE signature=?',(signature,)).fetchone()
        return dict(collection=row['collection_id'] if row else None)

    def commit_intake(self, id, collection, indices=None):
        with self.lock:
            intake=self.intake(id)
            if intake['status']=='completed':return intake['result']
            target=self.collection(collection)
            values=intake['content'] if isinstance(intake['content'],list) else [intake['content']]
            indices=intake['remaining_indices'] if indices is None else indices
            if len(indices)!=len(set(indices)) or any(type(i) is not int or i<0 or i>=len(values) for i in indices):raise ValueError('indices must contain unique valid intake item positions')
            selected=[self.normalize(target,values[i]) for i in indices]
            for value in selected:self._validate_content(target,value)
            self._batch_ids=[]
            try:
                with self.transaction():
                    records=[self.store(target['id'],value,metadata={'purpose':intake['purpose']}) for value in selected]
            finally:
                pending=list(dict.fromkeys(self._batch_ids));self._batch_ids=None
            if target['storage'] in {'csv','sqlite'} and pending:
                self._initialize_storage(target)
                batch=[]
                for record_id in pending:
                    record=self.fetch(record_id)
                    batch.append({'_id':record_id,**{k:encoded(v) if isinstance(v,(dict,list)) else v for k,v in record['content'].items()}})
                result=self._driver(target).write_many(batch)
                if result.status!='ok':raise RuntimeError('; '.join(result.errors))
                with self.transaction() as db:
                    for record_id in pending:
                        value=self.fetch(record_id)['content']
                        db.execute('DELETE FROM searchable WHERE record_id=?',(record_id,))
                        db.execute('INSERT INTO searchable VALUES(?,?)',(record_id,text_of(value)))
                        self._short_index(db,record_id,text_of(value))
                        db.execute("UPDATE records SET state='ready',index_state='ready' WHERE id=?",(record_id,))
            else:
                for record_id in pending:self._materialize(record_id)
            index=self.index(target['id']) if target['storage'] in {'rag','wiki'} else None
            signature=self.signature(intake['content'],intake['purpose']) if len(indices)==len(values) else None
            with self.connection() as db:
                for item_index,record in zip(indices,records):
                    db.execute('INSERT OR REPLACE INTO intake_items VALUES(?,?,?,?)',(id,item_index,target['id'],record['id']))
                    db.execute('INSERT OR IGNORE INTO record_intakes VALUES(?,?)',(record['id'],id))
                assigned=[dict(r) for r in db.execute('SELECT x.item_index,x.record_id,x.collection_id,r.version FROM intake_items x JOIN records r ON r.id=x.record_id WHERE x.intake_id=? ORDER BY x.item_index',(id,))]
                remaining=[i for i in range(len(values)) if i not in {r['item_index'] for r in assigned}]
                result=dict(intake_id=id,status='partial' if remaining else 'stored',records=[dict(id=r['record_id'],version=r['version'],node_id=self.owner_for(r['collection_id'])) for r in assigned],remaining_indices=remaining)
                if index:result['index']=index
                db.execute("UPDATE intakes SET status=?,result=? WHERE id=?",('partial' if remaining else 'completed',encoded(result),id))
                if signature:db.execute('INSERT OR REPLACE INTO routing_rules VALUES(?,?)',(signature,target['id']))
            return result
