"""Root only calls the two group entries; it does not coordinate individual workers."""
from datanet.core.module_protocol import ComponentResult

async def execute(ctx,activation):
    try:
        p=dict(activation.parameters);op=activation.operation
        wanted='discussion.group' if op=='datanet_discuss' else 'collaboration.group'
        nodes=[n for n in await ctx.nodes if wanted in n.modules]
        group=p.pop('group_id',None)
        if group:nodes=[n for n in nodes if n.node_id==group or n.name==group]
        if len(nodes)!=1:raise ValueError('请连接唯一的小组入口，或指定 group_id')
        if op=='wait_group':operation='wait'
        else:operation='discuss' if wanted=='discussion.group' else 'control'
        result=await nodes[0].call(wanted,operation,p)
        return ComponentResult(status=result['status'],data=result.get('data'),error=result.get('error'))
    except Exception as error:return ComponentResult(status='error',error=str(error))
