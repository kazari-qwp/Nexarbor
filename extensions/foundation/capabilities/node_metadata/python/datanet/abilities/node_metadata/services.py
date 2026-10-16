"""Namespaced extension metadata, outside the core node object."""
from copy import deepcopy
from datanet.core.json_values import freeze
from datanet.core.access_budget import active_agent


def namespace(value):
    if not isinstance(value,str) or not value or value=='core':raise ValueError('A non-core metadata namespace is required')
    return value


def combined(b,target,space,base=None):
    namespace(space)
    if target not in b.network.nodes:raise ValueError('Metadata target does not exist')
    extra=b.extension_state.get('node_metadata',{}).get(target,{}).get(space,{})
    result=deepcopy(base or {})
    if result.keys() & extra.keys():raise ValueError('Stored metadata conflicts with provider-owned fields')
    result.update(deepcopy(extra));freeze(result);return result


def set_values(b,p):
    if p.get('actor')!='root':raise PermissionError('Only the host may extend node metadata')
    target=p['target'];space=namespace(p['namespace']);combined(b,target,space)
    if not isinstance(p['values'],dict):raise ValueError('Metadata values must be an object')
    provider=b._node_metadata_providers.get(space)
    base=provider(target) if provider else {}
    if set(base or {}) & p['values'].keys():raise ValueError('Cannot replace provider-owned metadata fields')
    freeze(p['values'])
    b.extension_state.setdefault('node_metadata',{}).setdefault(target,{})[space]=deepcopy(p['values'])
    return dict(target=target,namespace=space)


def register_provider(b,space,provider,*,public=False):
    namespace(space)
    if not callable(provider):raise TypeError('Metadata provider must be callable')
    b._node_metadata_providers[space]=provider
    if public:b._node_metadata_public.add(space)
    else:b._node_metadata_public.discard(space)


def extend(b,node_id):
    if 'capabilities/node_metadata' not in b.components.enabled:return {}
    acting=active_agent.get();own=not acting or acting[1] in (node_id,b.root.node_id)
    spaces=set(b._node_metadata_providers)|set(b.extension_state.get('node_metadata',{}).get(node_id,{}))
    result={}
    for space in sorted(spaces):
        if not own and space not in b._node_metadata_public:continue
        provider=b._node_metadata_providers.get(space);base=provider(node_id) if provider else {}
        if base is not None and not isinstance(base,dict):raise ValueError('Metadata provider must return an object')
        values=combined(b,node_id,space,base)
        if values:result[space]=values
    return result


def install(b):
    b._node_metadata_providers={};b._node_metadata_public=set()
    b.metadata_registry.register('capabilities/node_metadata',lambda node_id:extend(b,node_id))


def register(s):
    s.initializers.append(install)
    s.rpc('node_metadata_set',set_values,mutation=True)
