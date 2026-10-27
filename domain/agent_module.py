"""Agent 在安装时选择记忆策略；节点访问通过 @access 执行。"""

from collections.abc import Callable

from .access import access
from .markdownNode import MarkdownNode
from .memory_strategy import EmptyMemoryStrategy, MarkdownMemoryStrategy
from .module import Module
from .node import Node
from .tool import Tools
from .tool_discovery_module import ToolDiscoveryModule


class AgentModule(Module):
    strategy_types = {MarkdownNode: MarkdownMemoryStrategy}

    def __init__(self, runner: Callable[[str, Tools], str] | None = None) -> None:
        super().__init__("agent", description="Agent 及记忆能力")
        self.runner = runner
        self.memory_strategy = EmptyMemoryStrategy()
        self._memory_tools: Tools | None = None

    def _bind(self, node: Node) -> None:
        super()._bind(node)
        strategy_type = next(
            (strategy for node_type, strategy in self.strategy_types.items() if isinstance(node, node_type)),
            EmptyMemoryStrategy,
        )
        if type(self.memory_strategy) is strategy_type:
            return
        if self._memory_tools is not None:
            self.tools._remove(self._memory_tools)
        self.memory_strategy = strategy_type()
        self._memory_tools = self.memory_strategy.create_tools(self)
        if self._memory_tools is not None:
            self.tools._add(self._memory_tools)

    @access(channels=())
    def available_tools(self, node: Node) -> Tools:
        discovery = node.modules.get("tool_discovery")
        return discovery.discover() if isinstance(discovery, ToolDiscoveryModule) else node.tools

    @property
    def auto_memory(self):
        return self.memory_strategy.auto_memory

    def run(self, new_input: str) -> str:
        if self.runner is None:
            raise NotImplementedError("Agent 模块尚未接入模型执行")
        tools = Tools(self.available_tools().values())
        return self.runner(new_input, tools)
