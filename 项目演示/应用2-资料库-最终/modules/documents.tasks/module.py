"""Immutable task inputs, separate deliveries, revisions and actual evidence receipts."""
import os,json,hashlib
from pathlib import Path
from uuid import uuid4
from copy import deepcopy
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw

def tasks(ctx):return ctx.state.setdefault('tasks',{})
def current(ctx,p):
    task=tasks(ctx).get(p.get('task_id',ctx.state.get('current')))
    if task is None:raise ValueError('No current task')
    return task
def reference(ctx,t):return dict(task_id=t['id'],mode=t['mode'],input_id=ctx.config['input'],result_id=ctx.config['output'],references=list(t['references']))
def directory(t):return Path(os.environ['DATANET_PROJECT_DIRECTORY'])/'workspace/tasks'/t['id'].split('/')[-1]
async def save_current(ctx,field,text):
    node=(await ctx.nodes)[ctx.config[field]];r=await node.write('content',text)
    if r['status']!='ok':raise ValueError(str(r['errors']))
async def record(ctx,id,version):
    nodes=await ctx.network.nodes(channels=['knowledge']);catalog=next(n for n in nodes if 'knowledge.catalog' in n.modules)
    d=await catalog.call('knowledge.catalog','locate',dict(id=id))
    if d['status']!='ok':raise ValueError(d['error'])
    r=await nodes[d['data']['node_id']].call('knowledge.collection','fetch',dict(id=id,version=version))
    if r['status']!='ok':raise ValueError(r['error'])
    return r['data']
async def execute(ctx,activation):
    op=activation.operation;p=thaw(activation.parameters)
    try:
        if op=='current':return ComponentResult(data=deepcopy(tasks(ctx).get(ctx.state.get('current'))))
        if op=='begin':
            t=dict(id='task/'+uuid4().hex,mode=p.get('mode','agent'),references=[],receipts=[],revision=0,sources=[])
            tasks(ctx)[t['id']]=t;ctx.state['current']=t['id'];home=directory(t);home.mkdir(parents=True)
            text=p['content'] if isinstance(p['content'],str) else json.dumps(p['content'],ensure_ascii=False)
            (home/'input.md').write_text(text,encoding='utf8');(home/'result.md').write_text('',encoding='utf8')
            await save_current(ctx,'input',text);await save_current(ctx,'output','')
            return ComponentResult(data=reference(ctx,t))
        t=current(ctx,p);home=directory(t)
        if op=='reference':
            if p.get('intake_id') and p['intake_id'] not in t['references']:t['references'].append(p['intake_id'])
            return ComponentResult(data=reference(ctx,t))
        if op=='remember':
            for r in p['records']:
                key=dict(id=r['id'],version=r['version'])
                if key not in t['receipts']:t['receipts'].append(key)
            return ComponentResult(data=dict(remembered=True))
        if op=='task_document_read':
            node=p.get('node_id',ctx.config['input']);kind='input' if node==ctx.config['input'] else 'result' if node==ctx.config['output'] else None
            if kind is None:raise ValueError('Document is outside task')
            text=(home/(kind+'.md')).read_text('utf8')
            return ComponentResult(data=dict(**reference(ctx,t),node_id=node,content=text,sha256=hashlib.sha256(text.encode()).hexdigest(),**({'immutable':True} if kind=='input' else dict(author=ctx.node_id,revision=t['revision'],sources=deepcopy(t['sources']),receipts=deepcopy(t.get('delivery_receipts',[]))))))
        if p.get('expected_revision',t['revision'])!=t['revision']:raise ValueError('Delivery revision changed; read it before retrying')
        for s in p.get('sources',[]):
            if s['node_id'] in (ctx.config['input'],ctx.config['output']):continue
            if not s.get('locator') or not s.get('version'):raise ValueError('Knowledge evidence requires record ID and version')
            r=await record(ctx,s['locator'],s['version'])
            if r['node_id']!=s['node_id']:raise ValueError('Evidence node does not match record')
        for receipt in p.get('receipts',[]):
            key=dict(id=receipt['id'],version=receipt['version'])
            if key not in t['receipts']:raise ValueError('Receipt was not produced by this task')
            r=await record(ctx,**key)
            if receipt.get('node_id',r['node_id'])!=r['node_id']:raise ValueError('Receipt node does not match record')
        (home/'result.md').write_text(p['content'],encoding='utf8')
        if ctx.state['current']==t['id']:await save_current(ctx,'output',p['content'])
        t.update(revision=t['revision']+1,sources=p.get('sources',[]),delivery_receipts=p.get('receipts',[]))
        (home/'delivery.json').write_text(json.dumps(t,ensure_ascii=False,indent=2),encoding='utf8')
        return ComponentResult(data=dict(node_id=ctx.config['output'],revision=t['revision'],written=True,path=str(home/'result.md')))
    except Exception as error:return ComponentResult(status='error',error=str(error))
