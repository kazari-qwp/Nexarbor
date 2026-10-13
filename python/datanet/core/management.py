"""Management ancestry is independent of data interfaces and signal propagation."""
SCOPES = ('self', 'children', 'descendants')

def validate_management(network):
    """Validate a forest in linear time; never infer ancestry from IDs or links."""
    complete = set()
    for node_id, node in network.nodes.items():
        parent = node.management_parent_id
        if parent is not None and (not isinstance(parent, str) or parent not in network.nodes):
            raise ValueError(f'Missing management parent for {node_id}')
    for node_id in network.nodes:
        trail = set()
        current = node_id
        while current is not None and current not in complete:
            if current in trail:
                raise ValueError('Management ancestry contains a cycle')
            trail.add(current)
            current = network.nodes[current].management_parent_id
        complete.update(trail)

def can_manage(network, actor, target, scope='self'):
    if scope not in SCOPES:
        raise ValueError('Management scope must be self, children or descendants')
    if actor not in network.nodes or target not in network.nodes:
        return False
    if target == actor:
        return True
    if scope == 'self':
        return False
    if scope == 'children':
        return network.nodes[target].management_parent_id == actor
    seen = set()
    current = target
    while current is not None:
        if current in seen:
            raise ValueError('Management ancestry contains a cycle')
        seen.add(current)
        node = network.nodes.get(current)
        if node is None:
            raise ValueError('Missing management parent')
        current = node.management_parent_id
        if current == actor:
            return True
    return False

def resolve_managed(network, actor, target=None, scope='self'):
    target = actor if target is None else target
    if not isinstance(target, str) or not target:
        raise ValueError('Management target must be a nonempty node ID')
    if not can_manage(network, actor, target, scope):
        raise PermissionError('Target is outside management grant')
    return network.nodes[target]
