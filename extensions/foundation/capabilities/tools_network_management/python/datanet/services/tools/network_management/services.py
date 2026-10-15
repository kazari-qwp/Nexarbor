from pathlib import Path
from datanet.core.interface_management import attach_interface_management_tools
from datanet.core.packages.network import load_network_package
from datanet.core.agent_node import AgentNode


def load_root_network(self, p):
    if len(self.network.nodes) != 1 or self.agents or self.root.agent_config is not None:
        return {'status': 'ok', 'restored': True, 'root_node_id': self.root.node_id}
    path = Path(p['package'])
    if not path.is_absolute():
        if p['package'] not in self.components.root_packages:
            raise ValueError('Root network preset is disabled or absent')
        path = self.components.root_packages[p['package']]
    package = load_network_package(path)
    entry = p.get('entry_point', 'root')
    if package.entry_points.get(entry) != 'root':
        raise ValueError('Root entry must reference canonical node ID root')
    network, report = package.instantiate(storage_dir=self.directory / 'resources', toolkits=self.components.toolkits(self))
    self.network = network
    self.root = network.nodes[report.entry_points[entry]]
    self.components.graph_loaded(self)
    self.attach_creation()
    attach_interface_management_tools(self.network, self.root, scope='descendants')
    return {'status': 'ok', 'node_ids': report.node_ids, 'entry_points': report.entry_points}

def agent_capability(self, p):
    owner = self.network.nodes[p['actor']]
    if p['tool'] == 'list_node_presets':
        self.attach_creation(owner, p.get('options'))
    elif p['tool'] == 'manage_interfaces':
        attach_interface_management_tools(self.network, owner, **p.get('options', {}))
    else:
        raise ValueError('Unsupported Agent-private capability')
    return owner.invoke_tool(p['tool'], **p.get('arguments', {}))

def create_network(self, p):
    preset = p['preset']
    if preset not in self.components.network_presets:
        raise ValueError('Network preset is disabled or absent')
    handler = self.components.network_handlers.get(preset, {})
    state = handler['prepare'](self, p) if 'prepare' in handler else None
    owner = self.network.nodes[p.get('actor', 'root')]
    from datanet.core.node_creation import attach_node_creation_tools
    options = p.get('options', {'allow_custom': True})
    packages = dict(self.components.network_presets)
    if 'package' in handler:
        packages[preset] = handler['package'](self, p, state)
    attach_node_creation_tools(self.network, owner, storage_dir=self.directory / 'created', presets=self.components.node_presets,
                               scope=options.get('scope', 'descendants'), allow_custom=options.get('allow_custom', False),
                               network_presets=packages, toolkits=self.components.toolkits(self))
    result = owner.invoke_tool('create_network', preset=preset, instance_id=p['instance_id'], entry_point=p.get('entry_point', handler.get('entry_point', 'root')), with_agents=False, parent_node_id=p.get('parent_node_id'), strength=p.get('strength', 0), read_interface=p.get('read_interface'), write_interface=p.get('write_interface'))
    if result.status != 'ok':
        return result
    if 'finalize' in handler:
        return handler['finalize'](self, p, result, state)
    result.items[0]['structure'] = self.created_structure(result.items[0])
    return result

def create_node(self, p):
    spec = p.get('node_spec', {})
    for key, value in spec.get('parameters', {}).items():
        if isinstance(value, str) and (key.endswith('path') or key.endswith('dir')):
            candidate = (self.directory / value).resolve()
            if not candidate.is_relative_to(self.directory):
                raise ValueError('Node storage must stay inside this workspace')
    arguments = dict(p)
    owner = self.network.nodes[arguments.pop('actor', 'root')]
    options = arguments.pop('options', {'allow_custom': True})
    self.attach_creation(owner, options)
    return owner.invoke_tool('create_child_node', **arguments)

def register(services):
    services.rpc('load_root_network', load_root_network, mutation=True)
    services.rpc('agent_capability', agent_capability, mutation=True)
    services.rpc('create_network', create_network, mutation=True)
    services.rpc('create_node', create_node, mutation=True)
