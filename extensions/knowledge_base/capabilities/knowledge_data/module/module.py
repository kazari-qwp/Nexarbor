"""知识操作复用本地数据授权；不接收文件路径或全局集合 ID。"""
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw
async def execute(ctx,activation):
    if activation.kind!='access':return ComponentResult(status='error',error='知识资料只接受访问调用')
    op=activation.operation
    try:
        guard=await ctx.network.call(ctx.node_id,'data.local','check',{'write':op not in ('history','search','fetch')})
        if guard['status']!='ok':raise PermissionError(guard['error'])
        if op in ('history','search','fetch'):return ComponentResult(data=ctx.write('$command',dict(operation=op,arguments=thaw(activation.parameters))))
        async with ctx.network.lock_nodes([ctx.node_id]):
            result=ctx.write('$command',dict(operation=op,arguments=thaw(activation.parameters)))
        return ComponentResult(data=result)
    except Exception as error:return ComponentResult(status='error',error=str(error))
