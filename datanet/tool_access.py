"""可达节点的工具发现与确定性只读调用；不调用目标 Agent。"""

from collections import deque
from copy import deepcopy

from datanet.nodes import NodeResult


def reachable(network, node_id, scope):
    if scope not in ("local", "integrated", "federated"):
        raise ValueError("scope 必须为 local、integrated 或 federated")
    if not isinstance(node_id, str):
        raise TypeError("节点编号必须是字符串")
    if node_id not in network.nodes:
        raise ValueError(f"起点不存在：{node_id}")
    queue = deque([(node_id, [node_id])])
    visited = set()
    while queue:
        current, path = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        node = network.nodes.get(current)
        if node is None:
            continue
        yield node, path
        if scope == "local":
            continue
        interfaces = list(node.strong_read_interfaces)
        if scope == "federated":
            interfaces.extend(node.weak_read_interfaces)
        queue.extend((i.target_node_id, [*path, i.target_node_id]) for i in interfaces)


def list_nodes(network, node_id, scope="integrated"):
    return NodeResult(items=[{**node.describe(include_schema=False),
        "read_only_tool_count": sum(d["read_only"] for name, d in node.tool_definitions.items() if name in node.tools),
        "retrieval_path": path,
    } for node, path in reachable(network, node_id, scope)])


def list_tools(network, node_id, target_node_id, scope="integrated"):
    for node, path in reachable(network, node_id, scope):
        if node.node_id == target_node_id:
            return NodeResult(items=[{**deepcopy(definition), "node_id": node.node_id,
                                     "retrieval_path": path.copy()}
                for name, definition in node.tool_definitions.items()
                if definition["read_only"] and name in node.tools])
    return NodeResult(status="forbidden", errors=["目标不在当前读取范围内"])


def validate_arguments(value, schema):
    """当前工具使用的 JSON Schema 子集：类型、字段、必填、枚举与数组。"""
    types = {"object": dict, "array": list, "string": str, "boolean": bool,
             "integer": int, "number": (int, float), "null": type(None)}
    expected = schema.get("type")
    choices = expected if isinstance(expected, list) else [expected]
    if expected is not None and not any(
        type(value) in (types[t] if isinstance(types[t], tuple) else (types[t],)) for t in choices
    ):
        raise TypeError(f"参数类型不符合定义：{expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("参数不在允许的枚举值中")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if any(name not in value for name in schema.get("required", [])):
            raise ValueError("缺少工具必填参数")
        if schema.get("additionalProperties") is False and set(value) - properties.keys():
            raise ValueError("包含未声明的工具参数")
        for name, item in value.items():
            if name in properties:
                validate_arguments(item, properties[name])
    if isinstance(value, list) and "items" in schema:
        for item in value:
            validate_arguments(item, schema["items"])


def invoke_tool(network, node_id, target_node_id, tool_name, arguments, scope="integrated"):
    if not isinstance(target_node_id, str) or not isinstance(tool_name, str) or not isinstance(arguments, dict):
        raise TypeError("目标和工具名必须为字符串，arguments 必须为字典")
    for node, path in reachable(network, node_id, scope):
        if node.node_id != target_node_id:
            continue
        definition = node.tool_definitions.get(tool_name)
        if definition is None or tool_name not in node.tools:
            return NodeResult(status="not_found", errors=["目标没有注册该工具"])
        if not definition["read_only"]:
            return NodeResult(status="forbidden", errors=["读连接只能调用显式标记的只读工具"])
        validate_arguments(arguments, definition["parameters"])
        result = node.invoke_tool(tool_name, **arguments)
        source = {"node_id": node.node_id, "tool_name": tool_name, "retrieval_path": path.copy()}
        if isinstance(result, NodeResult):
            result = deepcopy(result)
            result.sources = [{**s, "tool_name": tool_name, "tool_path": path.copy()} for s in result.sources]
            result.sources.append(source)
            return result
        return NodeResult(items=[{"result": result}], sources=[source])
    return NodeResult(status="forbidden", errors=["目标不在当前读取范围内"])


def discovery_definitions():
    scope = {"type": "string", "enum": ["local", "integrated", "federated"],
             "description": "默认 integrated；federated 同时沿强弱读连接。"}
    result = []
    for name, description, properties, required in (
        ("list_nodes", "列出当前 Agent 所属节点可达的节点概况；不预加载工具参数。", {}, []),
        ("list_tools", "按需查询一个可达节点的只读工具名称、用途及参数定义。",
         {"target_node_id": {"type": "string"}}, ["target_node_id"]),
        ("invoke_tool", "根据 list_tools 返回的定义调用指定节点的只读工具；不会调用目标 Agent。",
         {"target_node_id": {"type": "string"}, "tool_name": {"type": "string"},
          "arguments": {"type": "object"}}, ["target_node_id", "tool_name", "arguments"]),
    ):
        result.append({"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": {**properties, "scope": deepcopy(scope)},
                           "required": required, "additionalProperties": False}}})
    return result


def attach_discovery_tools(network, owner):
    """使用闭包固定当前所属起点，模型不能覆盖网络上下文。"""
    discovered = set()

    def discover(target_node_id, scope="integrated"):
        result = list_tools(network, owner.node_id, target_node_id, scope)
        if result.status == "ok":
            discovered.update((target_node_id, item["name"]) for item in result.items)
        return result

    def invoke(target_node_id, tool_name, arguments, scope="integrated"):
        if not isinstance(target_node_id, str) or not isinstance(tool_name, str):
            raise TypeError("目标和工具名称必须为字符串")
        if (target_node_id, tool_name) not in discovered:
            return NodeResult(status="forbidden", errors=["请先通过 list_tools 发现目标工具"])
        return invoke_tool(network, owner.node_id, target_node_id, tool_name, arguments, scope)

    owner.tools.update({
        "list_nodes": lambda scope="integrated": list_nodes(network, owner.node_id, scope),
        "list_tools": discover,
        "invoke_tool": invoke,
    })
    return discovery_definitions()
