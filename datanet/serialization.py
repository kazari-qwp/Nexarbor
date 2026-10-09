"""JSON v2：节点、连接、Agent 创建配置和显式委托许可，兼容 v1。"""

import json
import math
import os
import tempfile
from pathlib import Path

from datanet.network import Network
from datanet.nodes import Node, ValueNode, CsvNode, SqliteNode
from datanet.agent import Agent
from datanet.agent.configuration import validate_config


LINKS = ("strong_read_interfaces", "weak_read_interfaces",
         "strong_write_interfaces", "weak_write_interfaces")
TYPES = {Node: "node", ValueNode: "value", CsvNode: "csv", SqliteNode: "sqlite"}


def _string(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} 必须是非空字符串")
    return value


def _json_value(value):
    """拒绝会被 JSON 静默转换、丢失类型的信息。"""
    if type(value) is float and not math.isfinite(value):
        raise ValueError("JSON 不支持非有限数值")
    if value is None or type(value) in (str, bool, int, float):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError("单值数据必须由 JSON 原生类型组成；不支持元组、对象或非字符串字典键")


def _path_string(path, base):
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:  # Windows 不同盘符无法表示为相对路径。
        return path.as_posix()


def save_network(network: Network, path: str | Path) -> None:
    """保存结构；CSV/SQLite 只记录路径，ValueNode 保存其 JSON 值。"""
    path = Path(path).resolve()
    entries = []
    for node_id, node in network.nodes.items():
        if node_id != node.node_id:
            raise ValueError("网络注册编号与节点编号不一致")
        if type(node) not in TYPES:
            raise ValueError(f"不支持保存的节点类型：{type(node).__name__}")
        _string(node_id, "node_id")
        _string(node.name, "name")
        if not isinstance(node.description, str):
            raise ValueError("description 必须为字符串")
        if node.data_kind is not None:
            _string(node.data_kind, "data_kind")
        parameters = {}
        if type(node) is ValueNode:
            parameters = {"value": node.get("value").items[0]["value"]}
            _json_value(parameters["value"])
        elif type(node) is CsvNode:
            if not all(isinstance(k, str) and isinstance(v, str) for k, v in node.dtype.items()):
                raise ValueError("保存 CSV dtype 时请使用字符串类型名，例如 Int64")
            parameters = {"file_path": _path_string(node.file_path, path.parent),
                          "key_column": node.key_column, "dtype": node.dtype}
        elif type(node) is SqliteNode:
            parameters = {"db_path": _path_string(node.db_path, path.parent),
                          "table_name": node.table_name, "key_column": node.key_column}
        connections = {}
        for label in LINKS:
            targets = [interface.target_node_id for interface in getattr(node, label)]
            if any(target not in network.nodes for target in targets):
                raise ValueError(f"节点 {node_id} 的 {label} 含不存在的目标")
            connections[label] = targets
        agent_config = node.agent_config
        if isinstance(node.agent, Agent):
            if node.agent.extra_body not in (None, {"thinking": {"type": "disabled"}}, {"thinking": {"type": "enabled"}}):
                raise ValueError("Agent 配置只支持 thinking 开关，不保存其他 extra_body")
            agent_config = {"model": node.agent.model, "prompt_path": str(node.agent.prompt_path),
                "tools_path": (agent_config or {}).get("tools_path"),
                "max_rounds": node.agent.max_rounds, "max_tokens": node.agent.max_tokens,
                "thinking": None if node.agent.extra_body is None else node.agent.extra_body["thinking"]["type"] == "enabled"}
            if agent_config["tools_path"] is None:
                known = node.tool_definitions.keys() | {"list_nodes", "list_tools", "invoke_tool", "ask_agent"}
                if any(d["function"]["name"] not in known for d in node.agent.tool_definitions):
                    raise ValueError("保存 Agent 前需要配置工具定义文件或登记本地工具元数据")
        agent_config = validate_config(agent_config, path.parent)
        if agent_config is not None:
            for label in ("prompt_path", "tools_path"):
                if agent_config[label] is not None:
                    agent_config[label] = _path_string(Path(agent_config[label]), path.parent)
        entries.append({"type": TYPES[type(node)], "node_id": node_id, "name": node.name,
                        "description": node.description,
                        "data_kind": node.data_kind, "parameters": parameters,
                        "connections": connections, "agent": agent_config})
    document = {"version": 2, "nodes": entries, "delegations": [
        {"source": source, "target": target} for source, targets in network.delegation_permissions.items()
        for target in targets]}
    # 同样通过加载校验器验证，保证保存出来的配置可以加载。
    _build(document, path.parent)
    content = json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False) as file:
            temporary = Path(file.name)
            file.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{label} 字段必须为：{', '.join(expected)}")


def _build(document, base):
    if not isinstance(document, dict) or type(document.get("version")) is not int or document["version"] not in (1, 2):
        raise ValueError("不支持的网络配置版本")
    version = document["version"]
    _fields(document, ("version", "nodes") if version == 1 else ("version", "nodes", "delegations"), "网络配置")
    if not isinstance(document["nodes"], list):
        raise ValueError("nodes 必须是列表")
    network = Network()
    # 先创建全部节点，再恢复连接，支持前向引用与环。
    for entry in document["nodes"]:
        fields = ("type", "node_id", "name", "data_kind", "parameters", "connections")
        if isinstance(entry, dict) and "description" in entry:
            fields = (*fields, "description")
        _fields(entry, fields if version == 1 else (*fields, "agent"), "节点")
        node_id = _string(entry["node_id"], "node_id")
        name = _string(entry["name"], "name")
        kind = entry["data_kind"]
        if kind is not None:
            _string(kind, "data_kind")
        params = entry["parameters"]
        node_type = _string(entry["type"], "type")
        common = (node_id, name, kind)
        if node_type == "node":
            _fields(params, (), "基础节点参数")
            node = Node(*common)
        elif node_type == "value":
            _fields(params, ("value",), "单值节点参数")
            _json_value(params["value"])
            node = ValueNode(*common, params["value"])
        elif node_type == "csv":
            _fields(params, ("file_path", "key_column", "dtype"), "CSV 节点参数")
            dtype = params["dtype"]
            if not isinstance(dtype, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in dtype.items()):
                raise ValueError("dtype 必须是字符串到字符串的字典")
            node = CsvNode(*common, base / _string(params["file_path"], "file_path"),
                           _string(params["key_column"], "key_column"), dtype)
        elif node_type == "sqlite":
            _fields(params, ("db_path", "table_name", "key_column"), "SQLite 节点参数")
            node = SqliteNode(*common, base / _string(params["db_path"], "db_path"),
                              _string(params["table_name"], "table_name"),
                              _string(params["key_column"], "key_column"))
        else:
            raise ValueError(f"未知节点类型：{node_type}")
        node.agent_config = validate_config(entry.get("agent"), base)
        description = entry.get("description", "")
        if not isinstance(description, str):
            raise ValueError("description 必须为字符串")
        node.description = description
        network.add_node(node)
    for entry in document["nodes"]:
        connections = entry["connections"]
        _fields(connections, LINKS, "连接")
        node = network.nodes[entry["node_id"]]
        for label, targets in connections.items():
            if not isinstance(targets, list):
                raise ValueError(f"{label} 必须是列表")
            for target in targets:
                _string(target, "连接目标")
                if target not in network.nodes:
                    raise ValueError(f"连接目标不存在：{target}")
                getattr(node, label).append(network.nodes[target].interface)
    delegations = document.get("delegations", [])
    if not isinstance(delegations, list):
        raise ValueError("delegations 必须是列表")
    for grant in delegations:
        _fields(grant, ("source", "target"), "委托许可")
        source, target = _string(grant["source"], "source"), _string(grant["target"], "target")
        if source not in network.nodes or target not in network.nodes:
            raise ValueError("委托许可引用不存在的节点")
        targets = network.delegation_permissions.setdefault(source, [])
        if target in targets:
            raise ValueError("委托许可重复")
        targets.append(target)
    return network


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"JSON 字段重复：{key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"JSON 不支持数值：{value}")


def load_network(path: str | Path) -> Network:
    """相对数据路径以配置文件所在目录为基准；不访问实际存储内容。"""
    path = Path(path).resolve()
    with path.open(encoding="utf-8") as file:
        document = json.load(file, object_pairs_hook=_unique_object,
                             parse_constant=_invalid_constant)
    return _build(document, path.parent)
