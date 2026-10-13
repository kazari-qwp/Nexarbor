from pathlib import Path
from datanet.components.nodes.text_file_node.text_file_node import TextFileNode
from datanet.core.serialization import _path_string, _json_value, _string, _fields
from datanet.core.component_registry import NodeCodec, register_node

def encode(node, base):
    parameters = {'file_path': _path_string(node.file_path, base), 'delivery': node.delivery}
    return parameters

def decode(common, params, base):
    node_id, name, kind = common
    _fields({k: v for k, v in params.items() if k != 'delivery'}, ('file_path',), '文本文件节点参数')
    node = TextFileNode(*common, base / _string(params['file_path'], 'file_path'), delivery=params.get('delivery', 'plain'))
    return node

def register():
    register_node(NodeCodec('text_file', TextFileNode, encode, decode, parameter_fields=['file_path', 'delivery'], description='文本文件节点。绑定一个 UTF-8 文本或 Markdown 文件，支持读取全文、写入和追加。适合笔记、提示词或 Agent 记忆文档，不提供语义检索。', resources=('file_path',), references={}, local_write=True))
