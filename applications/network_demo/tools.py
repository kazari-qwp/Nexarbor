"""根节点的演示网络管理工具，允许选择已注册的任意起点。"""

from dataclasses import asdict

from datanet.network import Network


def describe_node(node_id: str, *, network: Network) -> dict:
    if not isinstance(node_id, str):
        raise TypeError("节点编号必须是字符串")
    node = network.nodes.get(node_id)
    if node is None:
        raise ValueError(f"节点不存在：{node_id}")
    return {
        **node.describe(),
        "strong_read_targets": [i.target_node_id for i in node.strong_read_interfaces],
        "weak_read_targets": [i.target_node_id for i in node.weak_read_interfaces],
        "tools": sorted(node.tools),
    }


def weak_read(node_id: str, key: str, *, network: Network) -> dict:
    if not isinstance(node_id, str) or not isinstance(key, str):
        raise TypeError("节点编号和查询主键必须是字符串")
    return asdict(network.weak_read(node_id, key))


def strong_read(node_id: str, key: str, *, network: Network) -> dict:
    if not isinstance(node_id, str) or not isinstance(key, str):
        raise TypeError("节点编号和查询主键必须是字符串")
    return asdict(network.strong_read(node_id, key))
