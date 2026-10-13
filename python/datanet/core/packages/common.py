"""配置包的文件与字段校验。配置只选择已登记的工具，不执行任意代码。"""
import json
from pathlib import Path
from datanet.core.serialization import _unique_object, _invalid_constant, _fields, _string

def read_manifest(path, kind, fields):
    path = Path(path).resolve()
    if path.is_dir():
        path = path / 'package.json'
    with path.open(encoding='utf-8') as file:
        document = json.load(file, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    _fields(document, fields, '配置包')
    if document['kind'] != kind or type(document['version']) is not int or document['version'] != 1:
        raise ValueError(f'必须是 {kind} 类型的 v1 配置包')
    _string(document['id'], '配置包 id')
    _string(document['description'], '配置包 description')
    return (path, document)
