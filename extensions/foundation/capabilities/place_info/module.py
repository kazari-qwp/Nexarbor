"""节点自己的位置资料，跨节点修改仍通过公开操作进入。"""
from datanet.core.module_protocol import ComponentResult

def information(ctx):
    metadata=ctx.metadata()
    return dict(node_id=ctx.node_id,name=metadata['name'],description=ctx.config.get('description') or metadata.get('description',''),
                location=ctx.state.get('location',ctx.config.get('location')),visitors=list(ctx.state.get('visitors',ctx.config.get('visitors',()))))

async def execute(ctx,activation):
    if activation.kind!='access':return ComponentResult(status='error',error='位置资料仅接受访问请求')
    value=information(ctx);parameters=activation.parameters
    if activation.operation=='read':return ComponentResult(data=value)
    if activation.operation in ('arrive','leave'):
        if parameters['visitor']!=ctx.requester_id:raise PermissionError('只能修改请求发起者自己的访客记录')
        visitors=set(value['visitors'])
        if activation.operation=='arrive':visitors.add(parameters['visitor'])
        else:visitors.discard(parameters['visitor'])
        ctx.state['visitors']=sorted(visitors)
    elif activation.operation=='set_location':
        if ctx.metadata()['node_type']!='agent' or ctx.node_id!=ctx.requester_id or activation.source!=parameters['location']:
            raise PermissionError('只有实际发起移动的 Agent 可以更新自己的位置')
        ctx.state['location']=parameters['location']
        ctx.update_inputs({'tail':['当前位置：'+parameters['location']+'\n'+parameters['description']]})
    else:return ComponentResult(status='error',error='未知位置资料操作')
    value=information(ctx);ctx.publish_metadata(value)
    return ComponentResult(data=value)
