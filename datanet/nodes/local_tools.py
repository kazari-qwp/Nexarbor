"""把本地只读能力挂在数据所属节点，组合工具仍由应用装配。"""

from datanet.nodes import CsvNode, SqliteNode, ValueNode, NodeResult


def attach_local_tools(node):
    key_schema = {"type": "object", "properties": {"key": {"type": "string"}},
                  "required": ["key"], "additionalProperties": False}
    if isinstance(node, ValueNode):
        node.register_tool("get_value", lambda: node.get("value"),
            description="读取本节点的单值，不沿任何连接。",
            parameters={"type": "object", "properties": {}, "additionalProperties": False}, read_only=True)
    elif isinstance(node, (CsvNode, SqliteNode)):
        node.register_tool("get_record", lambda key: node.get(key),
            description="按主键读取本节点的记录，不沿连接。", parameters=key_schema, read_only=True)
        if isinstance(node, CsvNode):
            node.register_tool("query_records", lambda filters: node.query(filters),
                description="在本 CSV 节点按字段等值条件查询，多个条件按且组合。",
                parameters={"type": "object", "properties": {"filters": {"type": "object"}},
                            "required": ["filters"], "additionalProperties": False}, read_only=True)
    if isinstance(node, (ValueNode, CsvNode, SqliteNode)):
        def read_schema():
            try:
                return node.get_schema()
            except (OSError, ValueError) as error:
                return NodeResult(status="error", errors=[str(error)])
        node.register_tool("get_schema", read_schema, description="查看本节点的字段、主键及类型结构，不读取记录值。",
            parameters={"type": "object", "properties": {}, "additionalProperties": False}, read_only=True)
