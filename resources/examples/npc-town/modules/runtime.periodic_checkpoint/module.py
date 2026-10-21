"""只计信号次数，定期请求宿主存档；与日历、时间文本无关。"""
from datanet.core.module_protocol import ComponentResult

async def flush(ctx):
    if not ctx.state.get('pending',False):return False
    await ctx.network.invoke(ctx.node_id,'runtime:checkpoint',{'full':True},channels=['runtime.checkpoint'])
    async with ctx.network.lock_nodes([ctx.node_id]):ctx.state['pending']=False
    return True

async def execute(ctx,activation):
    if activation.kind=='signal':
        async with ctx.network.lock_nodes([ctx.node_id]):
            identifier=activation.signal.signal_id
            if identifier not in ctx.state.get('seen',[]):
                count=ctx.state.get('count',0)+1;ctx.state['count']=count
                ctx.state['seen']=(list(ctx.state.get('seen',[]))+[identifier])[-200:]
                if count%ctx.config.get('every',5)==0:ctx.state['pending']=True
        await flush(ctx)
    elif activation.operation=='flush':await flush(ctx)
    return ComponentResult(data=dict(count=ctx.state.get('count',0),pending=ctx.state.get('pending',False)))
