"""Read-only graph and tool views for active module callbacks."""
from .access_request import AccessRequest
from .json_values import thaw
from .module_values import json_copy

QUERY_OPERATIONS=frozenset(('nodes','module_endpoints','metadata','edges','tools','visit','tool_sources','node_read'))

def query_request(runtime,key,operation,p):
    network=runtime.backend.network
    frame=runtime._scope(key)
    if operation == 'nodes' and p.get('reuse') and frame.get('nodes_request') is not None:
        return frame['nodes_request']
    p = dict(p); p['strength'],p['channels'] = runtime._budget(key,p)
    async def query():
        if operation == 'nodes':
            from .module_nodes import ReachedNode, ReachedNodes
            strength, channels = p['strength'], p['channels']
            reached = list(network.walk_states(key[0], strength=strength, channels=channels))
            by_node = {}
            for (owner, name), instance in runtime.instances.items():
                by_node.setdefault(owner, []).append((name, instance))
            return ReachedNodes(ReachedNode(runtime, key, node, path, left, channels, by_node.get(node.node_id, ()))
                                for node, path, left in reached)
        while True:
            strength, channels = runtime._budget(key,p)
            reached = list(network.walk_states(key[0],strength=strength,channels=channels))
            targets = [n.node_id for n,_,_ in reached] if operation in ('nodes','module_endpoints') else [p['target']]
            if operation not in ('nodes','module_endpoints'): runtime._route(key,p['target'],strength,channels)
            async with runtime.backend.node_locks.access(targets,mutable=False):
                runtime._scope(key)
                with runtime.backend._transaction_lock:
                    if operation == 'module_endpoints':
                        result=[]
                        family_reached=[network.nodes[id] for target,_,_ in reached for id in network.local_family(target.node_id)]
                        seen_targets=set()
                        for target in family_reached:
                            if target.node_id in seen_targets:continue
                            seen_targets.add(target.node_id)
                            for (owner,name),candidate in runtime.instances.items():
                                if owner!=target.node_id or p.get('module') not in (None,name):continue
                                available=[]
                                for op in candidate.operations:
                                    try:runtime._accessible(key[0],owner,name,op,strength,channels);available.append(op)
                                    except PermissionError:continue
                                if available:result.append(dict(node_id=owner,module=name,operations=available))
                        return result
                    target,path,left = runtime._route(key,p['target'],strength,channels)
                    if operation == 'node_read': return json_copy(target.read(json_copy(p['request'])))
                    if operation == 'metadata': return json_copy(target.get_metadata())
                    if operation == 'edges': return [json_copy(edge) for edge in network.routing_snapshot()[1][p['target']]]
                    if operation == 'tool_sources': return runtime._tool_sources(key[0],p['target'],strength=strength,channels=channels)
                    offers = getattr(runtime.backend,'external_tools',None)
                    if operation == 'visit':
                        return dict(metadata=json_copy(target.get_metadata()),path=path,strength=left,
                            tools=offers.visit(key[0],target.node_id,strength=strength,channels=channels) if offers else [])
                    return query_tools(runtime,key,p['target'],strength,channels)
    request = AccessRequest(query());frame['children'].append(request)
    if operation == 'nodes' and p.get('reuse'): frame['nodes_request'] = request
    return request
def query_tools(runtime,key,target_id,strength,channels):
    target, _, _ = runtime._route(key, target_id, strength, channels)
    result = []
    for name, definition in target.tool_definitions.items():
        if name not in target.expose or name not in target.tools: continue
        selected = tuple(c for c in channels if c in definition['access_channels'])
        if (definition['access_channels'] or target_id != key[0]) and not selected: continue
        try: _, path, remaining = runtime._route(key, target_id, strength, selected)
        except PermissionError: continue
        result.append(dict(**json_copy(definition), path=path, remaining_strength=remaining))
    if getattr(runtime.backend, 'external_tools', None):
        result.extend(runtime.backend.external_tools.visit(key[0], target.node_id, strength=strength, channels=channels, acquire=False))
    for (node_id,module),instance in runtime.instances.items():
        if node_id!=target_id:continue
        for tool in instance.definition.agent_tools.values():
            try:runtime._accessible(key[0],target_id,module,tool['operation'],strength,channels)
            except PermissionError:continue
            operation=instance.definition.operations[tool['operation']]
            result.append(dict(ref='module:'+module+'/'+tool['id'],name=tool['name'],description=tool['description'],parameters=thaw(operation['parameters'])))
    return result
