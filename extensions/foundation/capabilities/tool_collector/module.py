"""Tool collection and invocation use only the local component network port."""
import asyncio
from hashlib import sha256
from datanet.core.module_protocol import ComponentResult


def tool_id(node_id, reference):
    return 'tool_' + sha256((node_id+'\0'+reference).encode()).hexdigest()[:24]


async def collect(ctx):
    tools = {}
    pending = []
    for reached in await ctx.network.nodes():
        node_id = reached['metadata']['node_id']
        for definition in await ctx.network.tools(node_id):
            reference = definition.get('ref', definition['name'])
            identifier = tool_id(node_id, reference)
            tools[identifier] = dict(id=identifier, name=definition['name'],
                description=definition['description'], parameters=definition['parameters'],
                origin=dict(node_id=node_id, tool=reference), via=[])
        if node_id == ctx.node_id: continue  # Only invoke another collector.
        for source in await ctx.network.tool_sources(node_id):
            if source['module'] == ctx.module_id:
                pending.append((node_id, ctx.network.call(node_id, ctx.module_id, source['list'])))
    results = await asyncio.gather(*(request for _, request in pending))
    for (node_id, _), result in zip(pending, results):
        if result['status'] != 'ok': raise RuntimeError(result['error'])
        for item in result['data']:
            item = dict(item, via=[node_id, *item['via']])
            previous = tools.get(item['id'])
            # Prefer direct access, then fewer collector delegations. Stable tie order.
            if previous is None or len(item['via']) < len(previous['via']): tools[item['id']] = item
    return list(tools.values())


async def execute(ctx, activation):
    if activation.kind != 'access': return ComponentResult(status='error', error='Tool collector accepts access requests')
    tools = await collect(ctx)
    if activation.operation == 'collect': return ComponentResult(data=tools)
    if activation.operation != 'invoke': return ComponentResult(status='error', error='Unknown collector operation')
    selected = next((item for item in tools if item['id'] == activation.parameters['tool_id']), None)
    if selected is None: return ComponentResult(status='error', error='Tool is no longer available through this collector')
    arguments = dict(activation.parameters['arguments'])
    if selected['via']:
        result = await ctx.network.call(selected['via'][0], ctx.module_id, 'invoke',
            dict(tool_id=selected['id'], arguments=arguments))
        if result['status'] != 'ok': return ComponentResult(status='error', error=result['error'])
        return ComponentResult(data=result['data'])
    origin = selected['origin']
    return ComponentResult(data=await ctx.network.invoke(origin['node_id'], origin['tool'], arguments))
