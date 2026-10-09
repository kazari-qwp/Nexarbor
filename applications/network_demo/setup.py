"""装配演示网络，工具绑定上下文；Agent 可选择附加。"""

import json
from functools import partial
from pathlib import Path

from datanet.agent import Agent
from datanet.nodes import Node
from datanet.nodes.value_node.demo_network import build_number_network
from applications.network_demo.tools import describe_node, strong_read, weak_read


APP_DIR = Path(__file__).resolve().parent


def build_demo_network():
    network = build_number_network()
    root = Node("root", "数字网络管理助手", None)
    network.add_node(root)
    # 管理工具显式持有整个演示网络；不依赖 root 的连接来限制起点。
    root.tools.update({
        "describe_node": partial(describe_node, network=network),
        "weak_read": partial(weak_read, network=network),
        "strong_read": partial(strong_read, network=network),
    })
    return network, root


def build_agent_network(client, model: str):
    network, root = build_demo_network()
    with (APP_DIR / "tools.json").open(encoding="utf-8") as file:
        definitions = json.load(file)
    root.agent = Agent(
        client=client,
        model=model,
        system_prompt=(APP_DIR / "system.md").read_text(encoding="utf-8"),
        tool_definitions=definitions,
        extra_body={"thinking": {"type": "disabled"}},
    )
    return network, root
