from pathlib import Path
from copy import deepcopy
from datanet.components.nodes.value_node.value_node import ValueNode
from datanet.core.serialization import _path_string, _json_value, _string, _fields
from datanet.core.component_registry import NodeCodec, register_node

def encode(node, base):
    parameters = {'value': deepcopy(node._value)}
    _json_value(parameters['value'])
    return parameters

def decode(common, params, base):
    node_id, name, kind = common
    _fields(params, ('value',), '单值节点参数')
    _json_value(params['value'])
    node = ValueNode(*common, params['value'])
    return node

def register():
    register_node(NodeCodec('value', ValueNode, encode, decode, parameter_fields=['value'], description='单值存储节点。保存一个 JSON 兼容值，例如数字、文本、列表、字典或文件路径，通过固定键 value 读写。适合少量配置、状态或简单信息；保存文件路径不会自动读取文件。', resources=(), references={}, local_write=True))
