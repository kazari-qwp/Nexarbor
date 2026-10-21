"""遍历到节点后，先调用其收集器，再直接读取工具表。"""
from hashlib import sha256
from datanet.core.module_protocol import ComponentResult


def tool_id(node_id, reference):
    return 'tool_' + sha256((node_id+'\0'+reference).encode()).hexdigest()[:24]


async def collect(ctx):
    tools = {}
    visited = {item['node_id'] for item in ctx.call_path if item['module'] == ctx.module_id}
    channels = ctx.filter_channels('channels', ['tools'])
    for node in await ctx.network.nodes(channels=channels):
        if node.node_id not in visited and ctx.module_id in node.modules:
            result = await node.call(ctx.module_id, 'collect')
            if result['status'] != 'ok': raise RuntimeError(result['error'])
            for item in result['data']:
                item = dict(item, via=[node.node_id, *item['via']])
                previous = tools.get(item['id'])
                if previous is None or len(item['via']) < len(previous['via']):
                    tools[item['id']] = item
        for definition in node.tools:
            reference = definition.get('ref', definition['name'])
            identifier = tool_id(node.node_id, reference)
            tools[identifier] = dict(id=identifier, name=definition['name'],
                description=definition['description'], parameters=definition['parameters'],
                origin=dict(node_id=node.node_id, tool=reference), via=[])
    return list(tools.values())


async def execute(ctx, activation):
    if activation.kind != 'access': return ComponentResult(status='error', error='工具收集器仅接受访问请求')
    if activation.operation == 'collect':
        tools = await collect(ctx)
        ctx.state['routes'] = {item['id']:dict(origin=item['origin'],via=item['via']) for item in tools}
        return ComponentResult(data=tools)
    if activation.operation != 'invoke': return ComponentResult(status='error', error='未知工具收集操作')
    selected = ctx.state.get('routes', {}).get(activation.parameters['tool_id'])
    if selected is None: return ComponentResult(status='error', error='该工具未收集或已被移除')
    arguments = dict(activation.parameters['arguments'])
    try:
        if selected['via']:
            result = await ctx.network.call(selected['via'][0], ctx.module_id, 'invoke',
                dict(tool_id=activation.parameters['tool_id'], arguments=arguments),
                channels=ctx.filter_channels('channels', ['tools']))
            return ComponentResult(status=result['status'], data=result.get('data'), error=result.get('error'))
        origin = selected['origin']
        return ComponentResult(data=await ctx.network.invoke(origin['node_id'], origin['tool'], arguments))
    except (PermissionError, KeyError) as error:
        return ComponentResult(status='error', error=str(error))
