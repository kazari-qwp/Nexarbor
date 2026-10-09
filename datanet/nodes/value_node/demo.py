"""运行 python -m scripts.demo_value_node，演示网络读取单值节点。"""

import json
from dataclasses import asdict

from datanet.network import Network
from datanet.nodes.node import Node
from datanet.nodes.value_node import ValueNode


def main():
    root = Node("root", "项目入口", None)
    note = ValueNode(
        node_id="project_note",
        name="项目说明",
        data_kind="text",
        value="本项目使用模拟实验数据。",
    )
    root.strong_read_interfaces.append(note.interface)
    network = Network()
    network.add_node(root)
    network.add_node(note)
    result = network.get("root", "value", "integrated", data_kind="text")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
