"""普通激活入口；可达性和提交由宿主登记的官方能力检查。"""
from datanet.core.module_protocol import ComponentResult
from datanet.core.json_values import thaw

async def execute(ctx, activation):
    return ComponentResult(data=await ctx.extended('manage', {'operation':activation.operation, **thaw(activation.parameters)}))
