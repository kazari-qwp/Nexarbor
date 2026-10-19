"""通过局部网络端口收集和调用工具。"""
import asyncio
from hashlib import sha256
from datanet.core.module_protocol import ComponentResult


def tool_id(node_id, reference):
    return 'tool_' + sha256((node_id+'\0'+reference).encode()).hexdigest()[:24]


async def collect(ctx):
    tools = {}
    pending = []
    channels=ctx.filter_channels('channels',['tools'])
    visited={item['node_id'] for item in ctx.call_path if item['module']==ctx.module_id}
    for reached in await ctx.network.nodes(channels=channels):
        node_id = reached['metadata']['node_id']
        for definition in await ctx.network.tools(node_id):
            reference = definition.get('ref', definition['name'])
            identifier = tool_id(node_id, reference)
            tools[identifier] = dict(id=identifier, name=definition['name'],
                description=definition['description'], parameters=definition['parameters'],
                origin=dict(node_id=node_id, tool=reference), via=[])
    for source in await ctx.network.modules(ctx.module_id,channels=channels):
        node_id=source['node_id']
        if node_id in visited:continue
        pending.append((node_id,ctx.network.call(node_id,ctx.module_id,'collect',channels=channels)))
    results = await asyncio.gather(*(request for _, request in pending))
    for (node_id, _), result in zip(pending, results):
        if result['status'] != 'ok': raise RuntimeError(result['error'])
        for item in result['data']:
            item = dict(item, via=[node_id, *item['via']])
            previous = tools.get(item['id'])
            # 优先直接访问，再选较短的收集器链；同长时保持原顺序。
            if previous is None or len(item['via']) < len(previous['via']): tools[item['id']] = item
    return list(tools.values())


async def execute(ctx, activation):
    if activation.kind != 'access': return ComponentResult(status='error', error='工具收集器仅接受访问请求')
    tools = await collect(ctx)
    if activation.operation == 'collect': return ComponentResult(data=tools)
    if activation.operation != 'invoke': return ComponentResult(status='error', error='未知工具收集操作')
    selected = next((item for item in tools if item['id'] == activation.parameters['tool_id']), None)
    if selected is None: return ComponentResult(status='error', error='该工具已无法通过此收集器访问')
    arguments = dict(activation.parameters['arguments'])
    if selected['via']:
        result = await ctx.network.call(selected['via'][0], ctx.module_id, 'invoke',
            dict(tool_id=selected['id'], arguments=arguments),channels=ctx.filter_channels('channels',['tools']))
        if result['status'] != 'ok': return ComponentResult(status='error', error=result['error'])
        return ComponentResult(data=result['data'])
    origin = selected['origin']
    return ComponentResult(data=await ctx.network.invoke(origin['node_id'], origin['tool'], arguments))
