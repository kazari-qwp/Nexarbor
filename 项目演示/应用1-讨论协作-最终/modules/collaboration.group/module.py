"""Historical peer claims, shared records, publish/merge, candidate votes."""
import asyncio,json,posixpath,time,os
from pathlib import Path,PureWindowsPath
from copy import deepcopy
from uuid import uuid4
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw
from . import protocol


def group(ctx):
    return ctx.state.setdefault('group',dict(group_id=ctx.node_id,phase='ready',members=[],claims={},entries=[],candidate=None,unavailable={},requests={},jobs={},runs={}))

def active(g):return [n for n in g['members'] if n not in g.get('unavailable',{})]
def live(g):
    if g['phase'] not in ('running','review'):raise ValueError('当前小组未运行：'+g['phase'])

def append(g,actor,kind,content):
    entry=dict(id=str(uuid4()),run_id=g['run_id'],actor=actor,kind=kind,content=content,at=time.time());g['entries'].append(entry);return deepcopy(entry)

async def git(ctx,operation,p=None):
    r=await ctx.local.call('git.workspace',operation,p or {})
    if r['status']!='ok':raise ValueError(r['error'])
    return r['data']

async def member_nodes(ctx):
    return [n for n in await ctx.network.nodes(channels=['collaboration']) if 'collaboration.member' in n.modules]

async def announce(ctx,text,*,sender=None,wake=False):
    for node in await member_nodes(ctx):
        if node.node_id==sender:continue
        await node.call('collaboration.member','notify',dict(text=text))
    if wake:
        receipt=ctx.network.emit(channels=['collaboration.work'],content={'run_id':group(ctx)['run_id']},timeout_seconds=86400,node_timeout_seconds=86400)
        group(ctx)['signal']=receipt['signal_id'] if isinstance(receipt,dict) else receipt

async def status(ctx,p):
    g=group(ctx);section=p.get('section','all');result=dict(group_id=ctx.node_id,phase=g['phase'])
    fields={'summary':('task','members','unavailable','failure'),'claims':('claims',),'records':('entries',),'candidate':('candidate',)}
    if section=='all':result.update(deepcopy(g));result.update(workspace=g.get('workspace'),repository=await git(ctx,'repository'))
    else:result.update({k:deepcopy(g.get(k)) for k in fields[section]})
    if 'entries' in result:
        query=p.get('query');rows=g['entries'];result['entry_count']=len(rows)
        result['entries']=[r for r in rows if query.casefold() in r['content'].casefold() or query==r['id']] if query else deepcopy(rows[-20:])
    result['active_members']=active(g);return result

async def operation(ctx,op,p):
    g=group(ctx);actor=p.get('actor') or ctx.requester_id
    if op=='control':
        action=p['action']
        if action=='status':return await status(ctx,p)
        if action=='stop':g.update(phase='stopped',failure='调用者请求停止');await announce(ctx,'协作已停止。');return await status(ctx,{})
        if g['phase'] in ('running','review'):raise ValueError('小组正在执行任务')
        members=await member_nodes(ctx);ids=[n.node_id for n in members]
        prepared=await git(ctx,'prepare',{'members':ids})
        g.update(phase='running',started_at=time.time(),run_id=str(uuid4()),task=p['task'],members=ids,claims={},entries=[],candidate=None,unavailable={},failure=None,caller=actor,notified=False,workspace=prepared['directory'],personal_paths=prepared['members'])
        receipt=ctx.network.emit(channels=['collaboration.work'],content={'run_id':g['run_id']},timeout_seconds=86400,node_timeout_seconds=86400)
        g['signal']=receipt['signal_id'] if isinstance(receipt,dict) else receipt
        return dict(status='accepted',group_id=ctx.node_id,run_id=g['run_id'],members=ids)
    if op=='status':return await status(ctx,p)
    if op=='member_exit':
        g['unavailable'][actor]=p['reason']
        for c in g['claims'].values():
            if c['actor']==actor and c['state']=='active':c.update(state='released',evidence='成员退出：'+p['reason'])
        protocol.complete_candidate(g)
        if not active(g):g.update(phase='failed',failure='所有成员均已退出')
        await announce(ctx,'成员 '+actor+' 已退出，未完成认领已释放。请查看状态后继续。',sender=actor,wake=False)
        return dict(retired=True,phase=g['phase'])
    if op=='context':return dict(phase=g['phase'],candidate_pending=g.get('candidate') is not None and actor not in g['candidate']['approvals'],task=g.get('task'),run_id=g.get('run_id'),personal_path=g.get('personal_paths',{}).get(actor))
    if op=='wait':
        while g['phase'] in ('running','review'):
            await asyncio.sleep(.1)
        return await status(ctx,{})
    if actor not in active(g):raise ValueError('仅本组有效成员可调用协作工具')
    if op=='command_logs':
        r=await ctx.local.call('execution.logs','query',dict(p,actor=actor,since=g.get('started_at',0)))
        if r['status']!='ok':raise ValueError(r['error'])
        return r['data']
    if op=='claim':return protocol.claim(g,dict(p,actor=actor),append)
    if op=='note':
        live(g)
        if p['kind'] not in ('OBSERVED','FACT','FAIL','PATCH_SUMMARY') or not p['content'].strip():raise ValueError('记录须有有效 kind 和正文')
        return append(g,actor,p['kind'],p['content'])
    if op=='send':
        live(g);target=p['target']
        if target==actor or target not in active(g):raise ValueError('只能向本组其他有效成员发信')
        node=(await ctx.nodes)[target]
        await node.call('collaboration.member','notify',dict(text=json.dumps(dict(type='message',from_actor=actor,message_type=p.get('message_type','work_order'),content=p['content']),ensure_ascii=False)))
        return dict(delivered=True,target=target)
    if op=='workspace':
        if p['action']!='inspect' and g['phase']!='running':raise ValueError('仅运行阶段允许修改共同成果')
        return await git(ctx,p['action'],dict(actor=actor,message=p.get('message','Publish contribution')))
    if op=='finish':
        arguments=dict(p,actor=actor);action=p['action']
        if action=='propose' and g['phase']=='running' and not g['candidate'] and not any(c['state']=='active' for c in g['claims'].values()):
            logs=await ctx.local.call('execution.logs','collect',dict(actor=actor,since=g['started_at'],**({'ids':p['log_ids']} if 'log_ids' in p else {})))
            if logs['status']!='ok':raise ValueError(logs['error'])
            arguments['review']=await git(ctx,'proposal',dict(actor=actor,test_scripts=p.get('test_scripts',[]),test_results=p.get('test_results',[]),logs=logs['data']))
        result=protocol.finish(g,arguments,append)
        if result['phase']=='review' and action=='propose':
            await announce(ctx,'本组已提出成果候选：'+result['candidate']['id']+'。读取候选与验收材料，无异议批准，有异议指出证据。',sender=actor,wake=True)
        elif action=='reject':
            await announce(ctx,'成果候选被否决：'+p['evidence']+'。请继续修正。',sender=actor,wake=True)
        if g['phase']=='completed':
            root=Path(os.environ.get('DATANET_PROJECT_DIRECTORY','.'))/'workspace/cooperation-archives'/g['run_id'];root.mkdir(parents=True,exist_ok=True)
            (root/'result.md').write_text(g['candidate']['content'],encoding='utf8');(root/'run.json').write_text(json.dumps(g,ensure_ascii=False,indent=2),encoding='utf8');g['archive_path']=str(root)
            await announce(ctx,'共同成果已获本轮剩余成员验收，协作结束。请停止当前工作。')
        return dict(phase=g['phase'],candidate=deepcopy(g['candidate']),workspace=g['workspace'])
    raise ValueError('Unknown collaboration operation')

async def execute(ctx,activation):
    try:return ComponentResult(data=await operation(ctx,activation.operation,thaw(activation.parameters)))
    except Exception as error:return ComponentResult(status='error',error=str(error))
