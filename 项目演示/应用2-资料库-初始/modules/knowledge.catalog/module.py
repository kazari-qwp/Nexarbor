"""Historical durable knowledge engine, bound to one ordinary network node."""
import os,json,asyncio
from pathlib import Path
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw
from .store import KnowledgeStore
_STORES={}
def store(ctx):
    directory=Path(os.environ['DATANET_PROJECT_DIRECTORY'])/ctx.config.get('directory','workspace/knowledge')
    key=(str(directory),ctx.node_id,json.dumps(thaw(ctx.config.get('embedding')),sort_keys=True))
    if key not in _STORES:_STORES[key]=KnowledgeStore(directory,embedding_config=thaw(ctx.config.get('embedding')),owner_node=ctx.node_id)
    engine=_STORES[key]
    engine.owner_nodes=thaw(ctx.state.get('owners',{}))
    return engine

async def execute(ctx,activation):
    op=activation.operation;p=thaw(activation.parameters)
    try:
        engine=store(ctx)
        if op=='pending':
            offset=p.get('offset',0);limit=min(p.get('limit',20),100)
            with engine.connection() as db:
                total=db.execute("SELECT count(*) FROM intakes WHERE status IN ('pending','partial')").fetchone()[0]
                items=[dict(r) for r in db.execute("SELECT id,purpose,status FROM intakes WHERE status IN ('pending','partial') ORDER BY rowid LIMIT ? OFFSET ?",(limit,offset))]
            return ComponentResult(data=dict(items=items,total=total,offset=offset,next_offset=offset+limit if offset+limit<total else None))
        if op=='locate':
            with engine.connection() as db:
                row=db.execute('SELECT collection_id FROM records WHERE id=?',(p['id'],)).fetchone()
            if row is None:raise KeyError('Unknown record: '+p['id'])
            return ComponentResult(data=engine.collection(row['collection_id']))
        if op=='collection_access':
            collection=p['collection'];owner=ctx.state.get('owners',{}).get(collection)
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
            owners=thaw(ctx.state.get('owners',{}))
            if item['id'] not in owners:
                created=await ctx.network.invoke(ctx.node_id,'templates:instantiate',dict(template='knowledge-collection',key=item['id'],arguments=dict(label=item['name'],collection=item['id'],storage=item['storage'])),channels=['runtime.template'])
                owners=thaw(ctx.state.get('owners',{}));owners[item['id']]=created['node_ids']['collection'];ctx.state['owners']=owners;engine.owner_nodes=owners
            return ComponentResult(data={**engine.collection(item['id']),'reused':item['reused']})
        if op=='guide':
            name=p['name']
            if name not in ('AGENTS.md','READING.md','WIKI.md','ingest','query','lint'):raise ValueError('Unknown guide')
            file=Path(__file__).parent/(name if name.endswith('.md') else 'vendor/skills/'+name+'/SKILL.md')
            return ComponentResult(data=dict(id='knowledge:'+name,text=file.read_text('utf8')))
        if op=='wiki':
            action=p.get('action','guide')
            if action=='guide':return ComponentResult(data=dict(engine='llm-wiki',workflow=p.get('workflow','ingest')))
            collection=engine.collection(p['collection'])
            if collection['storage']!='wiki':raise ValueError('Choose a Wiki collection')
            records=[];offset=0
            while True:
                hits=engine.search(collection=collection['id'],limit=1000,offset=offset)
                records.extend(engine.fetch(hit['id']) for hit in hits['items'])
                if hits['next_offset'] is None:break
                offset=hits['next_offset']
            from datanet.llm_wiki.upstream import run
            result=await asyncio.to_thread(run,Path(__file__).parent,action,records,query=p.get('query',''),limit=p.get('limit',10))
            if action=='lint':result.update(stale=[dict(id=r['id'],sources=r['sources']) for r in records if r['needs_refresh']],unsourced=[r['id'] for r in records if not r['sources'] and not r['origins']])
            else:
                by_id={r['id']:r for r in records}
                result['items']=[dict(id=h['slug'],node_id=by_id[h['slug']]['node_id'],version=by_id[h['slug']]['version'],title=h['title'],score=h['score'],entry=by_id[h['slug']]['page']) for h in result['items']]
            return ComponentResult(data=dict(engine='llm-wiki',**result))
        result=await asyncio.to_thread(getattr(engine,op),**p)
        if op=='export' and 'content' in result:
            from uuid import uuid4
            path=engine.directory/'exports'/(uuid4().hex+'.'+result['format']);engine._atomic(path,result['content'].encode('utf8'));result=dict(format=result['format'],count=result['count'],path=str(path))
        return ComponentResult(data=result)
    except Exception as error:return ComponentResult(status='error',error=str(error))
