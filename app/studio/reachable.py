"""Editor reachability is computed through the actual access decorator."""
import asyncio
from domain.core import Tools, access


async def reachable_view(backend, parameters):
    actor = parameters["actor"]
    origin = backend.network.get(actor)
    if origin is None:
        raise KeyError("节点不存在：" + actor)
    strength = parameters.get("strength", 2)
    channels = backend.network.channel_names()
    reachable = {}

    class Visitor:
        _access_origin = origin

    for channel in channels:
        @access(channels=(channel,), strength=strength)
        async def collect(owner, node):
            return dict(id=node.info.node_id, name=node.info.name, type=node.node_type, channels=[channel])
        reachable[channel] = list((await collect(Visitor())).values())
    if origin.node_type == "agent":
        tools = Tools((await asyncio.to_thread(origin.available_tools)).values())
    else:
        tools = origin.tools
    return dict(actor=actor, strength=strength, reachable=reachable,
                tools=[dict(name=tool.name, description=tool.description, parameters=tool.parameters) for tool in tools])
