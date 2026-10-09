"""装配演示网络，工具绑定上下文；Agent 可选择附加。"""

from functools import partial
from pathlib import Path

from datanet.agent.configuration import assemble_agents
from datanet.serialization import load_network
from datanet.nodes.local_tools import attach_local_tools
from datanet.tool_access import attach_discovery_tools
from applications.network_demo.tools import describe_node, strong_read, weak_read, strong_write, weak_write


APP_DIR = Path(__file__).resolve().parent


def build_demo_network():
    network = load_network(APP_DIR / "network.json")
    root = network.nodes["root"]
    # 管理工具显式持有整个演示网络；不依赖 root 的连接来限制起点。
    root.tools.update({
        "describe_node": partial(describe_node, network=network),
        "weak_read": lambda key, node_id=None: weak_read(
            key, node_id, network=network, entry_node_id=root.node_id),
        "strong_read": lambda key, node_id=None: strong_read(
            key, node_id, network=network, entry_node_id=root.node_id),
        "weak_write": partial(weak_write, network=network, entry_node_id=root.node_id),
        "strong_write": partial(strong_write, network=network, entry_node_id=root.node_id),
    })
    for node in network.nodes.values():
        attach_local_tools(node)
    attach_discovery_tools(network, root)
    return network, root


def build_agent_network(client, model: str):
    network, root = build_demo_network()
    assemble_agents(network, client, model_override=model)
    return network, root
