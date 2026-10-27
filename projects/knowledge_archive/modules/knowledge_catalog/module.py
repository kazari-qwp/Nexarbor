"""实际知识目录模块；保留集合装配、来源访问及上游 Wiki 工作流。"""

import asyncio
from copy import deepcopy
import json
from pathlib import Path

from domain.core import Module, access
from domain.json_values import thaw
from .store import KnowledgeStore


class KnowledgeCatalogModule(Module):
    def __init__(self, directory, instantiate, config=None, state=None, **access_settings):
        super().__init__("knowledge.catalog", **access_settings)
        self.directory = Path(directory).resolve()
        self.instantiate = instantiate
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        self._stores = {}

    def engine(self, node):
        directory = self.directory / self.config.get("directory", "workspace/knowledge")
        key = (str(directory), node.info.node_id, json.dumps(thaw(self.config.get("embedding")), sort_keys=True))
        if key not in self._stores:
            self._stores[key] = KnowledgeStore(directory, embedding_config=thaw(self.config.get("embedding")), owner_node=node.info.node_id)
        engine = self._stores[key]
        engine.owner_nodes = thaw(self.state.get("owners", {}))
        return engine

    async def execute(self, action, **parameters):
        return next(iter((await self._operate(action, parameters)).values()))

    async def catalog(self, **parameters):
        return await self.execute("catalog", **parameters)

    async def collection(self, **parameters):
        return await self.execute("collection", **parameters)

    async def create_collection(self, **parameters):
        return await self.execute("create_collection", **parameters)

    async def store(self, **parameters):
        return await self.execute("store", **parameters)

    async def fetch(self, **parameters):
        return await self.execute("fetch", **parameters)

    async def search(self, **parameters):
        return await self.execute("search", **parameters)

    async def update(self, **parameters):
        return await self.execute("update", **parameters)

    async def delete(self, **parameters):
        return await self.execute("delete", **parameters)

    async def export(self, **parameters):
        return await self.execute("export", **parameters)

    async def intake(self, **parameters):
        return await self.execute("intake", **parameters)

    async def stage(self, **parameters):
        return await self.execute("stage", **parameters)

    async def route(self, **parameters):
        return await self.execute("route", **parameters)

    async def commit_intake(self, **parameters):
        return await self.execute("commit_intake", **parameters)

    async def index(self, **parameters):
        return await self.execute("index", **parameters)

    async def query(self, **parameters):
        return await self.execute("query", **parameters)

    async def wiki(self, **parameters):
        return await self.execute("wiki", **parameters)

    async def guide(self, **parameters):
        return await self.execute("guide", **parameters)

    async def locate(self, **parameters):
        return await self.execute("locate", **parameters)

    async def collection_access(self, **parameters):
        return await self.execute("collection_access", **parameters)

    async def pending(self, **parameters):
        return await self.execute("pending", **parameters)

    async def finish_intake(self, **parameters):
        return await self.execute("finish_intake", **parameters)

    @access(channels=())
    async def _operate(self, node, op, p):
        p = thaw(p)
        engine=self.engine(node)
        if op=='pending':
            offset=p.get('offset',0);limit=min(p.get('limit',20),100)
            with engine.connection() as db:
                total=db.execute("SELECT count(*) FROM intakes WHERE status IN ('pending','partial')").fetchone()[0]
                items=[dict(r) for r in db.execute("SELECT id,purpose,status FROM intakes WHERE status IN ('pending','partial') ORDER BY rowid LIMIT ? OFFSET ?",(limit,offset))]
            return dict(items=items,total=total,offset=offset,next_offset=offset+limit if offset+limit<total else None)
        if op=='locate':
            with engine.connection() as db:
                row=db.execute('SELECT collection_id FROM records WHERE id=?',(p['id'],)).fetchone()
            if row is None:raise KeyError('Unknown record: '+p['id'])
            return engine.collection(row['collection_id'])
        if op=='collection_access':
            collection=p['collection'];owner=self.state.get('owners',{}).get(collection)
            if not owner:raise ValueError('Collection has no bound network node')
            op=p['operation'];p=p.get('arguments',{})
            if op not in ('collection','store','fetch','search','update','delete','export','commit_intake','index','query','wiki'):raise ValueError('Unknown collection operation')
            if op in ('fetch','update','delete'):
                with engine.connection() as db:row=db.execute('SELECT collection_id FROM records WHERE id=?',(p['id'],)).fetchone()
                if row is None or row['collection_id']!=collection:raise ValueError('Record belongs to another collection')
            elif op=='collection':p={'target':collection}
            else:p={**p,'collection':collection}
        if op=='create_collection':
            item=await asyncio.to_thread(engine.create_collection,**p)
            owners=thaw(self.state.get('owners',{}))
            if item['id'] not in owners:
                created=await self.instantiate(node.info.node_id,template='knowledge-collection',key=item['id'],arguments=dict(label=item['name'],collection=item['id'],storage=item['storage']))
                owners=thaw(self.state.get('owners',{}));owners[item['id']]=created['node_ids']['collection'];self.state['owners']=owners;engine.owner_nodes=owners
            return {**engine.collection(item['id']),'reused':item['reused']}
        if op=='guide':
            name=p['name']
            if name not in ('AGENTS.md','READING.md','WIKI.md','ingest','query','lint'):raise ValueError('Unknown guide')
            file=Path(__file__).parent/(name if name.endswith('.md') else 'vendor/skills/'+name+'/SKILL.md')
            return dict(id='knowledge:'+name,text=file.read_text('utf8'))
        if op=='wiki':
            action=p.get('action','guide')
            if action=='guide':return dict(engine='llm-wiki',workflow=p.get('workflow','ingest'))
            collection=engine.collection(p['collection'])
            if collection['storage']!='wiki':raise ValueError('Choose a Wiki collection')
            records=[];offset=0
            while True:
                hits=engine.search(collection=collection['id'],limit=1000,offset=offset)
                records.extend(engine.fetch(hit['id']) for hit in hits['items'])
                if hits['next_offset'] is None:break
                offset=hits['next_offset']
            from projects.knowledge_archive.storage.wiki.upstream import run
            result=await asyncio.to_thread(run,Path(__file__).parent,action,records,query=p.get('query',''),limit=p.get('limit',10))
            if action=='lint':result.update(stale=[dict(id=r['id'],sources=r['sources']) for r in records if r['needs_refresh']],unsourced=[r['id'] for r in records if not r['sources'] and not r['origins']])
            else:
                by_id={r['id']:r for r in records}
                result['items']=[dict(id=h['slug'],node_id=by_id[h['slug']]['node_id'],version=by_id[h['slug']]['version'],title=h['title'],score=h['score'],entry=by_id[h['slug']]['page']) for h in result['items']]
            return dict(engine='llm-wiki',**result)
        result=await asyncio.to_thread(getattr(engine,op),**p)
        if op=='export' and 'content' in result:
            from uuid import uuid4
            path=engine.directory/'exports'/(uuid4().hex+'.'+result['format']);engine._atomic(path,result['content'].encode('utf8'));result=dict(format=result['format'],count=result['count'],path=str(path))
        return result
