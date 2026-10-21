"""Original knowledge admission and tool mapping; no corpus-specific facts."""
import csv,json,os
from pathlib import Path
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw

async def invoke(node,module,op,p):
    r=await node.call(module,op,p)
    if r['status']!='ok':raise ValueError(r['error'])
    return r['data']
async def storage(ctx,op,p=None):
    p=dict(p or {});nodes=await ctx.network.nodes(channels=['knowledge']);catalog=next(n for n in nodes if 'knowledge.catalog' in n.modules)
    if op in ('catalog','create_collection','stage','intake','route','guide','pending','finish_intake'):
        return await invoke(catalog,'knowledge.catalog',op,p)
    if op=='search' and not p.get('collection'):
        visible=[n.modules['knowledge.collection'].config['collection'] for n in nodes if 'knowledge.collection' in n.modules]
        return await invoke(catalog,'knowledge.catalog','search',{**p,'allowed_collections':visible})
    descriptor=await invoke(catalog,'knowledge.catalog','collection',{'target':p['collection']}) if p.get('collection') else await invoke(catalog,'knowledge.catalog','locate',{'id':p['id']})
    target=nodes.get(descriptor['node_id'])
    if target is None:raise ValueError('Collection node is not connected to this Agent')
    return await invoke(target,'knowledge.collection',op,p)
async def docs(ctx,op,p=None):
    r=await ctx.local.call('documents.tasks',op,p or {})
    if r['status']!='ok':raise ValueError(r['error'])
    return r['data']
async def guide(ctx,name):
    item=await storage(ctx,'guide',dict(name=name))
    ctx.update_inputs(dict(context=[item]))
async def ingest(ctx,p):
    if p.get('intake_id'):item=await storage(ctx,'intake',dict(id=p['intake_id']))
    else:
        content=p.get('content');source=None
        if p.get('file_path'):
            workspace=Path(os.environ['DATANET_PROJECT_DIRECTORY'])/'workspace';source=Path(p['file_path']);source=(source if source.is_absolute() else workspace/source).resolve()
            if not source.is_relative_to(workspace.resolve()):raise ValueError('Import file must be inside the application workspace')
            if source.suffix.lower()=='.csv':
                with source.open(encoding='utf-8-sig',newline='') as file:content=list(csv.DictReader(file))
            elif source.suffix.lower()=='.json':content=json.loads(source.read_text('utf8'))
            elif source.suffix.lower() in ('.md','.txt'):content=source.read_text('utf8')
            else:raise ValueError('Supported import files: CSV, JSON, TXT, Markdown')
        if content is None:raise ValueError('Provide content, file_path or an existing intake_id')
        item=await storage(ctx,'stage',dict(content=content,purpose=p.get('purpose',''),original_file=str(source) if source else None))
    task=await docs(ctx,'current')
    if task and task['mode']=='read':raise ValueError('Current task is read-only')
    if not task:await docs(ctx,'begin',dict(content={'intake_id':item['id'],'purpose':item['purpose']},mode='write'))
    reference=await docs(ctx,'reference',dict(intake_id=item['id']))
    target=p.get('collection') or (await storage(ctx,'route',dict(id=item['id'])))['collection']
    if item['status']=='completed':result=item['result']
    elif target:result=await storage(ctx,'commit_intake',dict(id=item['id'],collection=target))
    else:return dict(status='pending',intake_id=item['id'],**reference)
    await docs(ctx,'remember',dict(records=result.get('records',[])))
    await docs(ctx,'task_document_write',dict(content=json.dumps(result,ensure_ascii=False),receipts=result.get('records',[])))
    return dict(**result,**reference)

async def execute(ctx,activation):
    op=activation.operation;p=thaw(activation.parameters)
    try:
        if op=='prepare':
            task=await docs(ctx,'current');tail=[] if not task else [f"[当前知识任务] {task['id']}；模式：{task['mode']}。只读任务不修改知识记录，交付文档仍可写入。"]
            return ComponentResult(data=dict(format='nexarbor-context/v1',patch=dict(system_prompt='',context=[],inputs=[],tail=tail),sources=[],errors=[]))
        await guide(ctx,'AGENTS.md')
        task=await docs(ctx,'current')
        if op=='kb_task':
            ref=await docs(ctx,'begin',dict(content=p['content'],mode=p.get('mode','agent')))
            return ComponentResult(data=await ingest(ctx,dict(content=p['content'])) if p.get('mode')=='write' else ref)
        mutations={'kb_ingest','kb_create_node','kb_store','kb_update','kb_delete','kb_index'}
        if op in mutations and task and task['mode']=='read':raise ValueError('Current task is read-only')
        if op=='kb_intake' and p.get('action','read')!='read':
            if task and task['mode']=='read':raise ValueError('Current task is read-only')
            if p.get('record_id'):await storage(ctx,'fetch',dict(id=p['record_id']))
            return ComponentResult(data=await storage(ctx,'finish_intake',p))
        if op=='kb_ingest':return ComponentResult(data=await ingest(ctx,p))
        if op=='kb_wiki':
            workflow=p.get('workflow','query' if p.get('action')=='search' else 'lint' if p.get('action')=='lint' else 'ingest')
            await guide(ctx,'WIKI.md');await guide(ctx,workflow)
            result=await storage(ctx,'wiki',p)
        elif op=='kb_store':
            if p.get('intake_id'):result=await storage(ctx,'commit_intake',dict(id=p['intake_id'],collection=p['collection'],**({'indices':p['indices']} if 'indices' in p else {})))
            else:
                p.pop('intake_id',None);p['value']=p.pop('content');result=await storage(ctx,'store',p)
        else:
            mapping={'kb_catalog':'catalog','kb_create_node':'create_collection','kb_fetch':'fetch','kb_search':'search','kb_update':'update','kb_delete':'delete','kb_export':'export','kb_intake':'intake','kb_index':'index','kb_query':'query'}
            if op=='kb_intake' and not p.get('id'):return ComponentResult(data=await storage(ctx,'pending',p))
            if op=='kb_intake':p.pop('action',None);p['preview']=True
            result=await storage(ctx,mapping[op],p)
        if op in ('kb_store','kb_update'):
            records=result.get('records',[result] if 'id' in result and 'version' in result else [])
            await docs(ctx,'remember',dict(records=records))
        return ComponentResult(data=result)
    except Exception as error:return ComponentResult(status='error',error=str(error))
