"""六个数字节点的小网络：运行 python -m scripts.demo_number_network。"""

from datanet.network import Network
from datanet.nodes.node import NodeResult
from datanet.nodes.value_node import ValueNode


def build_number_network():
    network = Network()
    nodes = {
        number: ValueNode(f"n{number}", f"数字 {number}", "number", number)
        for number in range(1, 7)
    }
    for node in nodes.values():
        network.add_node(node)

    # 强读：1→2→4→1 构成环；3→4 是共享后继；5→6。
    for source, target in [(1, 2), (2, 4), (4, 1), (3, 4), (5, 6)]:
        nodes[source].strong_read_interfaces.append(nodes[target].interface)

    # 弱读使三个区域可达；1→2 同时放在两类列表中验证去重。
    for source, target in [(1, 3), (2, 5), (6, 2), (1, 2)]:
        nodes[source].weak_read_interfaces.append(nodes[target].interface)

    # 四个列表都存在，写列表保持为空。
    return network


def show_result(label: str, result: NodeResult, expected: list[int]):
    values = [item["value"] for item in result.items]
    assert result.status == "ok", result.errors
    assert values == expected, (label, values, expected)
    assert len(values) == len(set(values)), "同一节点被重复读取"
    print(f"{label}：{values}")
    for source in result.sources:
        print("  路径：" + " → ".join(source["retrieval_path"]))


def main():
    network = build_number_network()
    print("强读连接：1→2、2→4、4→1、3→4、5→6")
    print("弱读连接：1→3、2→5、6→2、1→2（与强读列表重叠）")
    print("采用 BFS，每个节点在一次读取中最多访问一次。")

    cases = [
        ("n1", [1, 2, 4], [1, 2, 3, 4, 5, 6]),
        ("n3", [3, 4, 1, 2], [3, 4, 1, 2, 5, 6]),
        ("n5", [5, 6], [5, 6, 2, 4, 1, 3]),
    ]
    for start_id, weak_expected, strong_expected in cases:
        show_result(
            f"从 {start_id} 弱读",
            network.weak_read(start_id, "value", "number"),
            weak_expected,
        )
        show_result(
            f"从 {start_id} 强读",
            network.strong_read(start_id, "value", "number"),
            strong_expected,
        )

    assert network.get("n1", "value", scope="local").items == [{"value": 1}]
    assert all(
        not node.strong_write_interfaces and not node.weak_write_interfaces
        for node in network.nodes.values()
    )
    print("全部检查通过：读取范围、顺序、环去重和写列表为空。")


if __name__ == "__main__":
    main()
