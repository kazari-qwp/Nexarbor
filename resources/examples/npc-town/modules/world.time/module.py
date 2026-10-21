"""小镇时间：一次 tick 推进一格，同时公开原始计数和本节点文本。"""
from datanet.core.module_protocol import ComponentResult

def clock(ctx):
    tick=ctx.state.get('tick',ctx.config.get('initial_tick',0))
    labels=ctx.config.get('labels') or ('早上','中午','下午','傍晚','午夜')
    return dict(tick=tick,day=(max(1,tick)-1)//len(labels)+1,slot=labels[(max(1,tick)-1)%len(labels)])

async def execute(ctx,activation):
    if activation.kind=='signal':
        async with ctx.network.lock_nodes([ctx.node_id]):
            if activation.signal.signal_id not in ctx.state.get('seen',[]):
                ctx.state['tick']=clock(ctx)['tick']+1
                ctx.state['seen']=(list(ctx.state.get('seen',[]))+[activation.signal.signal_id])[-200:]
                value=clock(ctx)
                result=ctx.write('content',ctx.config.get('text_template','当前时间：第{day}天 {slot}（总 tick：{tick}）').format(**value))
                if result['status']!='ok':raise RuntimeError('更新时间文本失败')
                ctx.publish_metadata(value)
    return ComponentResult(data=clock(ctx))
