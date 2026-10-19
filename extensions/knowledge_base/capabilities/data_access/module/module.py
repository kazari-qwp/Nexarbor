"""只操作所在节点的数据；知识操作通过同节点依赖复用只读检查。"""
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw
async def execute(ctx,activation):
    if activation.kind!='access':return ComponentResult(status='error',error='本地数据只接受访问调用')
    op=activation.operation;p=thaw(activation.parameters)
    try:
        if op=='check':
            if p['write'] and ctx.config.get('read_only',False):raise PermissionError('该数据节点已配置为只读')
            return ComponentResult(data=True)
        if op=='inspect':return ComponentResult(data=ctx.schema())
        if op=='read':result=ctx.read(dict(method='key',key=p['key']))
        elif op=='query':result=ctx.read(p['request'])
        elif op=='write':
            if ctx.config.get('read_only',False):raise PermissionError('该数据节点已配置为只读')
            async with ctx.network.lock_nodes([ctx.node_id]):
                result=ctx.write(p['key'],p['value'],mode=p.get('mode','upsert'))
        else:raise ValueError('未知数据操作')
        return ComponentResult(data=result)
    except Exception as error:return ComponentResult(status='error',error=str(error))
