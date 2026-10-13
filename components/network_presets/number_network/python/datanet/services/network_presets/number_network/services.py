from functools import partial
from datanet.components.networks.number_network.toolkit import TOOLKITS
from datanet.components.networks.number_network.tools import describe_node, read, write
from datanet.core.tool_access import attach_discovery_tools

def restore_node(backend, node, document):
    definitions = document['tools'].get(node.node_id, {})
    if 'describe_node' not in definitions:
        return
    attach_discovery_tools(backend.network, node)
    functions = {'describe_node': partial(describe_node, network=backend.network), 'read': partial(read, network=backend.network, entry_node_id=node.node_id), 'write': partial(write, network=backend.network, entry_node_id=node.node_id)}
    for name, fn in functions.items():
        definition = definitions[name]
        node.register_tool(name, fn, description=definition['description'], parameters=definition['parameters'], read_only=definition['read_only'])

def register(services):
    services.network_presets['number_network'] = services.catalog['network_presets/number_network']['directory'] / 'python/datanet/components/networks/number_network/package.json'
    services.toolkit_factories.append(lambda backend: TOOLKITS)
    services.node_restorers.append(restore_node)
