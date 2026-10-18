"""Optional trusted host bridge, never a generic backend/RPC escape hatch."""
from dataclasses import asdict, replace
from datanet.core.module_protocol import ModuleDefinition, ComponentResult
from datanet.core.json_values import names

OPERATIONS = ('nodes', 'metadata', 'incoming', 'interfaces', 'connect', 'disconnect')


def host_operation(backend, owner, policy, operation, arguments):
    if operation not in OPERATIONS: raise PermissionError('Unknown extended network operation')
    allowed, network = policy['targets'], backend.network
    def permitted(target): return '*' in allowed or target in allowed
    def target_node(target):
        if not isinstance(target, str) or not permitted(target): raise PermissionError('Extended target is not granted')
        if target not in network.nodes: raise ValueError('Extended target does not exist')
        return network.nodes[target]
    if operation == 'nodes':
        if arguments: raise ValueError('nodes takes no arguments')
        return [node.get_metadata() for key, node in network.nodes.items() if permitted(key)]
    target = arguments.get('target'); node = target_node(target)
    if operation == 'metadata':
        if set(arguments) != {'target'}: raise ValueError('metadata requires target only')
        return node.get_metadata()
    if operation == 'incoming':
        if set(arguments) != {'target'}: raise ValueError('incoming requires target only')
        return [dict(source=key, **asdict(edge)) for key, source in network.nodes.items() if permitted(key)
                for edge in source.interfaces if edge.target_node_id == target]
    if operation == 'interfaces':
        if set(arguments) != {'target'}: raise ValueError('interfaces requires target only')
        return [asdict(edge) for edge in node.interfaces if permitted(edge.target_node_id)]
    if set(arguments) - {'source', 'target', 'channels', 'threshold', 'multiplier'}:
        raise ValueError('Unknown network edit parameter')
    source = target_node(arguments.get('source'))
    channels = names(arguments.get('channels'), 'edited channels', allow_empty=False)
    with backend._transaction_lock:
        if operation == 'connect':
            edge = source.connect(target, channels=channels, threshold=arguments.get('threshold', 0),
                                  multiplier=arguments.get('multiplier', 1))
            result = asdict(edge)
        else:
            if set(arguments) != {'source', 'target', 'channels'}: raise ValueError('disconnect requires source, target, channels')
            edges = []
            for edge in source.interfaces:
                if edge.target_node_id != target:
                    edges.append(edge); continue
                remaining = tuple(c for c in edge.metadata.channels if c not in channels)
                if remaining: edges.append(replace(edge, metadata=replace(edge.metadata, channels=remaining)))
            source.interfaces[:] = edges
            result = dict(disconnected=True)
        backend.dispatch('save', {})
        return result


async def execute(ctx, activation):
    return ComponentResult(data=ctx.extended(activation.operation, dict(activation.parameters)))


def register(services):
    definition = ModuleDefinition(execute, operations=[dict(name=name, channels=['network.extended'],
        parameters={'type':'object'}, result={}) for name in OPERATIONS])
    services.node_module('network.gateway', definition, extension=host_operation)
