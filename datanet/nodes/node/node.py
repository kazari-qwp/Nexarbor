from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, TYPE_CHECKING
from copy import deepcopy
from threading import get_ident

from datanet.interface import Interface

if TYPE_CHECKING:
    from datanet.agent import Agent


@dataclass
class NodeResult:
    status: str = "ok"
    items: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class Node:
    def __init__(self, node_id: str, name: str, data_kind: str | None, *, description: str = ""):
        if not isinstance(description, str):
            raise TypeError("description 必须是字符串")
        self.node_id = node_id
        self.name = name
        self.data_kind = data_kind
        self.description = description
        self.agent: "Agent | None" = None
        self.agent_config: dict | None = None
        self.interface = Interface(target_node_id=node_id)
        # 同一地址可属于多个列表；各节点的列表互不共享。
        self.strong_read_interfaces: list[Interface] = []
        self.weak_read_interfaces: list[Interface] = []
        self.strong_write_interfaces: list[Interface] = []
        self.weak_write_interfaces: list[Interface] = []
        self.tools: dict[str, Callable[..., Any]] = {}
        self.tool_definitions: dict[str, dict] = {}

    def register_tool(self, name: str, function: Callable[..., Any], *,
                      description: str, parameters: dict, read_only: bool = False) -> None:
        """应用显式声明可发现的能力；未声明只读的工具不能通过读连接调用。"""
        if not isinstance(name, str) or not name or not callable(function):
            raise ValueError("工具名称必须非空，工具必须可调用")
        if type(read_only) is not bool:
            raise TypeError("read_only 必须为 bool")
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            raise ValueError("工具参数定义必须为 object")
        self.tools[name] = function
        self.tool_definitions[name] = {
            "name": name, "description": description,
            "parameters": deepcopy(parameters), "read_only": read_only,
        }

    def get_schema(self) -> dict | None:
        return None

    @property
    def schema(self) -> dict | None:
        return self.get_schema()

    def describe(self, *, include_schema: bool = True) -> dict:
        result = {
            "node_id": self.node_id,
            "name": self.name,
            "data_kind": self.data_kind,
            "description": self.description,
            "has_agent": self.agent is not None,
        }
        if include_schema:
            try:
                result["schema"] = self.get_schema()
            except (OSError, ValueError) as error:
                result.update(schema=None, schema_error=str(error))
        return result

    def get(self, key: str) -> NodeResult | None:
        """基础节点没有本地读取能力，由具体数据节点重写。"""
        return None

    def query(self, filters: dict[str, Any]) -> NodeResult | None:
        if self.data_kind is None:
            return None
        return NodeResult(status="unsupported", errors=["节点尚不支持条件查询"])

    def invoke_tool(self, tool_name: str, /, **arguments) -> Any:
        if tool_name not in self.tools:
            raise ValueError(f"工具不存在：{tool_name}")
        return self.tools[tool_name](**arguments)

    def write(self, key: str, value: Any, *, mode: str = "upsert") -> NodeResult:
        return NodeResult(status="unsupported", errors=["节点不支持本地写入"])

    def invoke_agent(self, user_message: str) -> str:
        if self.agent is None:
            raise RuntimeError("该节点尚未配置 Agent")
        return self.agent.run(user_message, node=self)

    def restart_agent(self) -> None:
        """等待现有任务结束，先构建新实例，成功后替换；失败保留旧实例。"""
        previous = self.agent
        if previous is None:
            raise RuntimeError("该节点尚未配置 Agent")
        if previous._running_thread == get_ident():
            raise RuntimeError("Agent 不能在自身任务执行中同步重启")
        with previous._lifecycle_lock:
            if self.agent is not previous:
                raise RuntimeError("Agent 实例已改变，请重新发起重启")
            replacement = previous.rebuild()
            self.agent = replacement
