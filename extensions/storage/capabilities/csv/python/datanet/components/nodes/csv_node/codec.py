from pathlib import Path
from datanet.components.nodes.csv_node.csv_node import CsvNode
from datanet.core.serialization import _path_string, _json_value, _string, _fields
from datanet.core.component_registry import NodeCodec, register_node

def encode(node, base):
    if not all((isinstance(k, str) and isinstance(v, str) for k, v in node.dtype.items())):
        raise ValueError('保存 CSV dtype 时请使用字符串类型名，例如 Int64')
    parameters = {'file_path': _path_string(node.file_path, base), 'key_column': node.key_column, 'dtype': node.dtype}
    return parameters

def decode(common, params, base):
    node_id, name, kind = common
    _fields(params, ('file_path', 'key_column', 'dtype'), 'CSV 节点参数')
    dtype = params['dtype']
    if not isinstance(dtype, dict) or not all((isinstance(k, str) and isinstance(v, str) for k, v in dtype.items())):
        raise ValueError('dtype 必须是字符串到字符串的字典')
    node = CsvNode(*common, base / _string(params['file_path'], 'file_path'), _string(params['key_column'], 'key_column'), dtype)
    return node

def register():
    register_node(NodeCodec('csv', CsvNode, encode, decode, parameter_fields=['file_path', 'key_column', 'dtype'], description='CSV 表格节点。按指定主键列读取记录，支持字段条件查询和记录写入。适合实验记录、清单等结构化表格数据，不提供语义检索。', resources=('file_path',), references={}, local_write=True))
