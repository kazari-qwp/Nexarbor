from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any, TYPE_CHECKING

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
    def __init__(self, node_id: str, name: str, data_kind: str | None,
                 *, agent_enabled: bool = False):
        self.node_id = node_id
        self.name = name
        self.data_kind = data_kind
        self.set_agent_enabled(agent_enabled)
        self.agent: "Agent | None" = None
        self.interface = Interface(target_node_id=node_id)
        # 同一地址可属于多个列表；各节点的列表互不共享。
        self.strong_read_interfaces: list[Interface] = []
        self.weak_read_interfaces: list[Interface] = []
        self.strong_write_interfaces: list[Interface] = []
        self.weak_write_interfaces: list[Interface] = []
        self.tools: dict[str, Callable[..., Any]] = {}

    def describe(self) -> dict:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "data_kind": self.data_kind,
            "agent_enabled": self.agent_enabled,
        }

    def set_agent_enabled(self, enabled: bool) -> None:
        """设置 Agent 启用状态；关闭不会删除已有实例或历史。"""
        if not isinstance(enabled, bool):
            raise TypeError("Agent 开关必须是 bool，使用 True 或 False")
        self.agent_enabled = enabled

    def get(self, key: str) -> NodeResult | None:
        """基础节点没有本地读取能力，由具体数据节点重写。"""
        return None

    def query(self, filters: dict[str, Any]) -> NodeResult | None:
        if self.data_kind is None:
            return None
        return NodeResult(status="unsupported", errors=["节点尚不支持条件查询"])

    def invoke_tool(self, tool_name: str, **arguments) -> Any:
        if tool_name not in self.tools:
            raise ValueError(f"工具不存在：{tool_name}")
        return self.tools[tool_name](**arguments)

    def invoke_agent(self, user_message: str) -> str:
        if not self.agent_enabled:
            raise RuntimeError("该节点未开启 Agent")
        if self.agent is None:
            raise RuntimeError("该节点尚未配置 Agent")
        return self.agent.run(user_message, node=self)
