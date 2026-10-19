from pathlib import Path
from datanet.components.nodes.sqlite_node.sqlite_node import SqliteNode
from datanet.core.serialization import _path_string, _json_value, _string, _fields
from datanet.core.component_registry import NodeCodec, register_node

def encode(node, base):
    parameters = {'db_path': _path_string(node.db_path, base), 'table_name': node.table_name, 'key_column': node.key_column}
    return parameters

def decode(common, params, base):
    node_id, name, kind = common
    _fields(params, ('db_path', 'table_name', 'key_column'), 'SQLite 节点参数')
    node = SqliteNode(*common, base / _string(params['db_path'], 'db_path'), _string(params['table_name'], 'table_name'), _string(params['key_column'], 'key_column'))
    return node

def register():
    register_node(NodeCodec('sqlite', SqliteNode, encode, decode, parameter_fields=['db_path', 'table_name', 'key_column'], description='SQLite 数据表节点。绑定数据库中的一张表，支持主键读取、字段条件查询和记录写入。适合需要精确查询与更新的结构化数据；创建节点不会自动创建数据表。', resources=('db_path',), references={}, local_write=True))
