from datanet.components.nodes.text_file_node.text_file_node import TextFileNode

def migrate(backend):
    for target in ('root/project', 'root/progress', 'root/work'):
        node = backend.network.nodes.get(target)
        if isinstance(node, TextFileNode):
            node.delivery = 'query'

def register(services):
    services.migrations.append(migrate)
    package=services.catalog['network_presets/project_root']['directory']/'python/resources/package.json'
    services.root_packages.update({'project_root':package,'host_configs/project_root/package.json':package})
