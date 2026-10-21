"""Historical round snapshots, parallel members, recorder finalization."""
import asyncio,json,os
from pathlib import Path
from uuid import uuid4
from copy import deepcopy
from datanet.core.module_protocol import ComponentResult


def state(ctx):
    return ctx.state.setdefault('group',dict(phase='ready',run_id=None,round=0,busy=False,submitted={},previous_submitted={},unavailable={},archives=[]))

async def nodes(ctx):
    return await ctx.nodes

async def text(ctx,field):
    node=(await nodes(ctx))[ctx.config[field]]
    result=await node.read({'method':'key','key':'content'})
    return result['items'][0]['content']

async def write(ctx,field,content):
    result=await (await nodes(ctx))[ctx.config[field]].write('content',content)
    if result.get('status')!='ok':raise ValueError(str(result.get('errors')))

async def members(ctx):
    return [n for n in await ctx.network.nodes(channels=['discussion']) if 'discussion.member' in n.modules]

async def archive(ctx,name,content):
    root=Path(os.environ.get('DATANET_PROJECT_DIRECTORY','.') )
    path=root/'workspace/discussions'/state(ctx)['run_id']/name
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf8')
    return str(path)

async def pulse(ctx,final=False):
    """One local closed-loop wave; next round waits for every receiver."""
    g=state(ctx)
    receipt=ctx.network.emit(channels=['discussion.round'],kind='pulse',close_loop=True,
        sequence=g['round'],content=dict(run_id=g['run_id'],round=g['round'],final=final),
        timeout_seconds=86400,node_timeout_seconds=86400)
    g['signal']=receipt['signal_id']
    report=await ctx.network.wait_signal(g['signal'])
    if not report['returned'] or report['status']!='completed':
        raise RuntimeError('Discussion pulse did not complete: '+str(report['status']))

async def board(ctx):
    raw=await text(ctx,'board')
    return json.loads(raw) if raw.strip() else dict(round=0,submitted={},previous_submitted={})

async def save_board(ctx):
    g=state(ctx)
    await write(ctx,'board',json.dumps({k:g[k] for k in ('round','submitted','previous_submitted')},ensure_ascii=False,indent=2))

async def discuss(ctx,p):
    g=state(ctx)
    if g['phase']=='running':raise ValueError('Discussion is already running')
    if g['phase']=='completed' and not p.get('task'):
        return dict(status='ok',run_id=g['run_id'],output=await text(ctx,'output'),archive_path=g.get('archive_path'))
    task=p.get('task') or g.get('task')
    if not task:raise ValueError('New discussion requires a task')
    if g['phase']=='completed':
        await write(ctx,'notebook','');await write(ctx,'output','');await write(ctx,'board','')
        g.update(run_id=None,round=0,busy=False,submitted={},previous_submitted={},unavailable={},archives=[])
    participants=await members(ctx)
    leader=next(n for n in participants if n.modules['discussion.member'].config['role']=='leader')
    recorder=next(n for n in participants if n.modules['discussion.member'].config['role']=='recorder')
    g.update(phase='running',task=task,run_id=g.get('run_id') or uuid4().hex,caller=ctx.requester_id,
             members=[n.node_id for n in participants],leader=leader.node_id,recorder=recorder.node_id)
    total=ctx.config.get('rounds',2)
    try:
        while g['round']<total or g.get('busy'):
            if not g.get('busy'):
                g['previous_submitted']=dict((await board(ctx))['submitted']);g['submitted']={};g['round']+=1
                await save_board(ctx)
                g['notebook_snapshot']=await text(ctx,'notebook');g['busy']=True
            await pulse(ctx)
            if any(n not in g['submitted'] for n in (leader.node_id,recorder.node_id)):
                raise RuntimeError('Leader or Recorder did not submit this round')
            body='\n'.join(f"## 第{g['round']}轮 · {n}\n{t}\n" for n,t in g['submitted'].items())
            g['archives'].append(await archive(ctx,f"round_{g['round']:03d}.md",body));g['busy']=False
        g['phase']='finalizing'
        g['final_written']=False
        await pulse(ctx,final=True)
        if not g['final_written']:raise ValueError('FINAL_OUTPUT_NOT_CONFIRMED: Recorder 本次未保存非空最终成果')
        output=await text(ctx,'output');g['archive_path']=await archive(ctx,'result.md',output);g['phase']='completed'
        return dict(status='ok',run_id=g['run_id'],output=output,archive_path=g['archive_path'],unavailable=deepcopy(g['unavailable']))
    except Exception as error:
        g['phase']='interrupted';g['last_error']=str(error);raise

async def operation(ctx,name,p):
    g=state(ctx);actor=p.get('actor') or ctx.requester_id
    if name=='discuss':return await discuss(ctx,p)
    if name=='status':return {k:deepcopy(v) for k,v in g.items() if k not in ('submitted','previous_submitted','notebook_snapshot')}
    if name=='context':
        return dict(phase=g['phase'],round=g['round'],total=ctx.config.get('rounds',2),notebook=g.get('notebook_snapshot',''),previous_submitted=(await board(ctx))['previous_submitted'],submitted=deepcopy(g['submitted']),task=g.get('task'),run_id=g.get('run_id'),output=ctx.config['output'],unavailable=deepcopy(g['unavailable']))
    if name=='read_round':
        snapshot=await board(ctx)
        return dict(round=snapshot['round'],previous_submitted=snapshot['previous_submitted'])
    if name=='member_exit':
        if actor in (g.get('leader'),g.get('recorder')):raise RuntimeError(p['reason'])
        g['unavailable'][actor]=p['reason'];return dict(retired=True)
    if actor not in g.get('members',[]):raise ValueError('Only discussion members may write')
    if name in ('submit_round','skip_round'):
        if g['phase']!='running' or actor in g['submitted'] or actor in g['unavailable']:raise ValueError('not an active member or already submitted')
        content=p.get('reason','') if name=='skip_round' else p.get('content','')
        if name=='submit_round' and not content.strip():raise ValueError('empty submission')
        g['submitted'][actor]=('[跳过] ' if name=='skip_round' else '')+content
        await save_board(ctx)
        return dict(submitted=True,round=g['round'],member=actor)
    if name=='read_output':return dict(content=await text(ctx,'output'))
    if actor!=g.get('recorder'):raise ValueError('Only Recorder may maintain notes/output')
    if name=='write_notebook':
        if len(p['content'])>200:raise ValueError('公共笔记最多200字符，细节请写输出板')
        await write(ctx,'notebook',p['content']);return dict(written=True)
    if name=='write_output':
        if not p['content'].strip():raise ValueError('输出正文不能为空')
        await write(ctx,'output',p['content'])
        if g['phase']=='finalizing':g['final_written']=True
        return dict(written=True)
    raise ValueError('Unknown discussion operation')

async def execute(ctx,activation):
    try:return ComponentResult(data=await operation(ctx,activation.operation,activation.parameters))
    except Exception as error:return ComponentResult(status='error',error=str(error))
