"""管理工具默认从所属节点出发；可显式选择已注册起点。"""
from dataclasses import asdict

def describe_node(node_id, *, network):
    node = network.nodes.get(node_id)
    if node is None:
        raise ValueError(f'节点不存在：{node_id}')
    return {**node.describe(), 'interfaces':[asdict(i) for i in node.interfaces], 'tools': sorted(node.tools)}

def read(request, node_id=None, scope='network', data_kind=None, strength=0, *, network, entry_node_id):
    origin = entry_node_id if node_id is None else node_id
    return asdict(network.read(origin, request, scope=scope, data_kind=data_kind, strength=strength))

def write(target_node_id, key, value, *, mode='upsert', strength=0, node_id=None, scope='network', network, entry_node_id):
    origin = entry_node_id if node_id is None else node_id
    return asdict(network.write(origin, target_node_id, key, value, mode=mode, strength=strength, scope=scope))
