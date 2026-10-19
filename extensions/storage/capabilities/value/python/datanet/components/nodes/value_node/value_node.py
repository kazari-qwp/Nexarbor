"""单值节点：保存在内存中，文件路径仅作为值，不读取文件。"""
from copy import deepcopy
from typing import Any
from datanet.core.node import Node, NodeResult
from datanet.core.write_support import validate_write

class ValueNode(Node):
    signal_type = 'value'

    def install_local_tools(self):
        """当前协议由节点上的 data.local 模块显式提供工具。"""
        pass

    def write(self, key: str, value: Any, *, mode: str='upsert') -> NodeResult:
        validate_write(key, mode)
        if key != 'value':
            return NodeResult(status='not_found', errors=['单值节点只支持主键 value'])
        if mode == 'insert':
            return NodeResult(status='conflict', errors=['单值节点的 value 已存在'])
        self._value = deepcopy(value)
        result = self.read({'method': 'key', 'key': key})
        result.sources[0].update(operation='write', mode=mode)
        return result

    def __init__(self, node_id: str, name: str, data_kind: str, value: Any, *, description: str=''):
        super().__init__(node_id, name, data_kind, description=description)
        self._value = deepcopy(value)

    value=property(lambda self:deepcopy(self._value),lambda self,value:setattr(self,'_value',deepcopy(value)))

    def get_schema(self) -> dict:
        names = {type(None): 'null', bool: 'boolean', int: 'integer', float: 'number', str: 'string', list: 'array', dict: 'object'}
        return {'kind': 'single_value', 'key': 'value', 'value_type': names.get(type(self._value)), 'python_type': type(self._value).__name__}

    def _read_key(self, key: str) -> NodeResult:
        if not isinstance(key, str):
            raise TypeError('查询主键必须是字符串')
        if key != 'value':
            return NodeResult(status='not_found')
        return NodeResult(items=[{'value': deepcopy(self._value)}], sources=[{'node_id': self.node_id, 'storage': 'memory', 'key': 'value'}])
