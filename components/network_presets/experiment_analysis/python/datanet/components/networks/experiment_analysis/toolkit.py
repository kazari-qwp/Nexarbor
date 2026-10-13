"""实验组合工具的显式装配入口，可绑定任意拼图实例。"""
from functools import partial
from datanet.components.networks.experiment_analysis.tools.network_tools import analyze_project_via_network

def attach_experiment_tools(network, node):
    node.register_tool('analyze_project', partial(analyze_project_via_network, network=network, entry_node_id=node.node_id, strength=1), description='组合规则和记录计算项目合格率，返回实际规则和数据来源。', parameters={'type': 'object', 'properties': {'project_id': {'type': 'string'}}, 'required': ['project_id'], 'additionalProperties': False}, read_only=True)
TOOLKITS = {'experiment_analysis': attach_experiment_tools}
