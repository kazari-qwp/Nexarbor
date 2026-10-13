"""从配置包装配数字网络及其工具，可附加独立 Agent。"""
from datanet.components.networks.number_network.paths import COMPONENTS_DIR
from datanet.core.agent_configuration import assemble_agents
from datanet.core.packages import load_network_package
from datanet.components.networks.number_network.toolkit import TOOLKITS
PACKAGE_PATH = COMPONENTS_DIR

def build_demo_network():
    network, mounted = load_network_package(PACKAGE_PATH).instantiate(toolkits=TOOLKITS)
    return (network, network.nodes[mounted.entry_points['root']])

def build_agent_network(client, model: str):
    network, root = build_demo_network()
    assemble_agents(network, client, model_override=model)
    return (network, root)
