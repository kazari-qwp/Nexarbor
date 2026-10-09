from pathlib import Path

from datanet.serialization import load_network
from datanet.nodes.local_tools import attach_local_tools
from datanet.agent.configuration import assemble_agents


CONFIG_PATH = Path(__file__).resolve().parent / "network.json"


def build_agent_network(client, model=None, *, config_path=CONFIG_PATH):
    network = load_network(config_path)
    for node in network.nodes.values():
        attach_local_tools(node)
    assemble_agents(network, client, model_override=model)
    return network, network.nodes["root"]
