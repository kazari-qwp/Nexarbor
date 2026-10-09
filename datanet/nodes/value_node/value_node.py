"""单值节点：保存在内存中，文件路径仅作为值，不读取文件。"""

from copy import deepcopy
from typing import Any

from datanet.nodes.node import Node, NodeResult
from datanet.nodes.write_support import validate_write


class ValueNode(Node):
    def write(self, key: str, value: Any, *, mode: str = "upsert") -> NodeResult:
        validate_write(key, mode)
        if key != "value":
            return NodeResult(status="not_found", errors=["单值节点只支持主键 value"])
        if mode == "insert":
            return NodeResult(status="conflict", errors=["单值节点的 value 已存在"])
        self._value = deepcopy(value)
        result = self.get(key)
        result.sources[0].update(operation="write", mode=mode)
        return result

    def __init__(self, node_id: str, name: str, data_kind: str, value: Any):
        super().__init__(node_id, name, data_kind)
        # 隔离调用者传入的可变数据，避免外部修改改变节点内容。
        self._value = deepcopy(value)

    def get(self, key: str) -> NodeResult:
        if not isinstance(key, str):
            raise TypeError("查询主键必须是字符串")
        if key != "value":
            return NodeResult(status="not_found")
        return NodeResult(
            items=[{"value": deepcopy(self._value)}],
            sources=[{
                "node_id": self.node_id,
                "storage": "memory",
                "key": "value",
            }],
        )
