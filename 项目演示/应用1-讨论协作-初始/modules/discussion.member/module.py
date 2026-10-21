"""Per-member native execution and compact context, with explicit turn conclusion."""
import json
from datanet.core.module_protocol import ComponentResult

async def target(ctx):
    name=ctx.config['group_module'];channel=ctx.config['channel']
    return next(n for n in await ctx.network.nodes(channels=[channel]) if name in n.modules)

async def call(ctx,operation,parameters=None):
    node=await target(ctx);p=dict(parameters or {});p['actor']=ctx.node_id
    r=await node.call(ctx.config['group_module'],operation,p)
    if r['status']!='ok':raise ValueError(r.get('error') or '小组操作失败')
    return r['data']

def conclude(data):return dict(format='nexarbor-tool-control/v1',conclude=True,data=data)

def packet(tail):
    return dict(format='nexarbor-context/v1',patch=dict(system_prompt='',context=[],inputs=[],tail=tail),sources=[],errors=[])

async def execute(ctx,activation):
    op,p=activation.operation,activation.parameters
    try:
        if activation.kind=='signal' or op=='run':
            if ctx.state.get('running'):
                ctx.state['pending']=True;return ComponentResult(data=dict(status='queued'))
            ctx.state.update(running=True,pending=False)
            try:
                data=await call(ctx,'context')
                if activation.kind=='signal':
                    turn=dict(activation.signal.content)
                    if turn['run_id']!=data['run_id'] or ctx.node_id in data['unavailable']:
                        return ComponentResult(data=dict(status='idle'))
                    final=turn.get('final',False)
                    if final and ctx.config['role']!='recorder' or not final and ctx.node_id in data['submitted']:
                        return ComponentResult(data=dict(status='idle'))
                    if final:
                        others={n:t for n,t in data['submitted'].items() if n!=ctx.node_id}
                        message=f"本次运行：{data['run_id']}。讨论已结束，请根据本次任务、输出板草稿和历史上下文定稿。最后一轮其他成员发言：\n"+json.dumps(others,ensure_ascii=False,indent=2)+f"\n把最终成果写入 {data['output']}，用 write_output；然后回复完成情况。"
                    else:
                        # Re-read the board at every pulse, rather than keeping opening content.
                        snapshot=await call(ctx,'read_round')
                        others={n:t for n,t in snapshot['previous_submitted'].items() if n!=ctx.node_id}
                        message=(f"项目任务：{data['task']}\n输出板ID：{data['output']}。" if data['round']==1 else '')
                        message+=f"\n本次运行：{data['run_id']}。\n上轮其他成员发言：\n"+json.dumps(others,ensure_ascii=False,indent=2)
                    ctx.state['turn']=dict(final=final)
                else:
                    ctx.state['turn']=dict(p);message=p['message']
                result=await ctx.network.invoke(ctx.node_id,'runtime:agent_run',dict(message=message),channels=['runtime.agent'])
                if result.get('status') not in ('completed','ok'):
                    raise RuntimeError(result.get('error') or 'Member execution failed')
                if not ctx.state['turn'].get('final'):
                    current=await call(ctx,'context')
                    if ctx.node_id not in current['submitted']:raise RuntimeError('本轮未提交或跳过')
                return ComponentResult(data=result)
            finally:ctx.state['running']=False
        if op=='notify':
            number=ctx.state.get('notification',0)+1;ctx.state['notification']=number
            ctx.update_inputs({'inputs':[dict(id='message-'+str(number),text=p['text'],delivery='steer')]})
            return ComponentResult(data=dict(delivered=True))
        if op=='prepare':
            data=await call(ctx,'context')
            turn=ctx.state.get('turn',{});stage='讨论已结束；当前阶段：成果汇总。' if turn.get('final') else f"当前轮数：{data['round']}/{data['total']}。"
            tail=['[讨论状态：'+ctx.node_id+']\n'+stage+'\n当前请求次数：{{request.count}}/{{request.limit}}。']
            if not turn.get('final'):tail.append('[公共笔记]\n'+data['notebook'])
            return ComponentResult(data=packet(tail))
        data=await call(ctx,op,p)
        return ComponentResult(data=conclude(data) if op in ('submit_round','skip_round') else data)
    except Exception as error:
        if activation.kind=='signal':await call(ctx,'member_exit',dict(reason=str(error)))
        return ComponentResult(status='error',error=str(error))
