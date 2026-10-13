from datanet.components.networks.delegated_number.paths import COMPONENTS_DIR
from datanet.core.packages import load_network_package
from datanet.core.agent_configuration import assemble_agents
CONFIG_PATH = COMPONENTS_DIR / 'package.json'

def build_agent_network(client, model=None, *, config_path=CONFIG_PATH):
    network, mounted = load_network_package(config_path).instantiate()
    assemble_agents(network, client, model_override=model)
    return (network, network.nodes[mounted.entry_points['root']])
