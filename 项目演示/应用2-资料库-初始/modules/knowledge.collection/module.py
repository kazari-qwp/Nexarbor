from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw
async def execute(ctx,activation):
    try:
        target=next(n for n in await ctx.network.nodes(channels=['knowledge']) if 'knowledge.catalog' in n.modules)
        result=await target.call('knowledge.catalog','collection_access',dict(collection=ctx.config['collection'],operation=activation.operation,arguments=thaw(activation.parameters)))
        return ComponentResult(status=result['status'],data=result.get('data'),error=result.get('error'))
    except Exception as error:return ComponentResult(status='error',error=str(error))
