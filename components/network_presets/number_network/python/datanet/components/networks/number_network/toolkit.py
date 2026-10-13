"""数字网络管理工具；所有默认起点绑定到所属节点。"""
import json
from pathlib import Path
from functools import partial
from datanet.components.networks.number_network.tools import describe_node, read, write

def attach_management_tools(network, node):
    functions = {'describe_node': partial(describe_node, network=network), 'read': partial(read, network=network, entry_node_id=node.node_id), 'write': partial(write, network=network, entry_node_id=node.node_id)}
    definitions = json.loads(Path(node.agent_config['tools_path']).read_text(encoding='utf-8'))
    for definition in definitions:
        function = definition['function']
        name = function['name']
        node.register_tool(name, functions[name], description=function['description'], parameters=function['parameters'], read_only=name in {'describe_node', 'read'})
TOOLKITS = {'number_management': attach_management_tools}
