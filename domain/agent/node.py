"""Agent 节点；具体记忆能力由所继承的数据节点决定。"""

from collections.abc import Callable

from domain.core import MarkdownNode, Node, NodeInfo, Tools, access
from .inputs import AgentInputs
from .memory import EmptyMemoryStrategy, MarkdownMemoryStrategy


class AgentNode(Node):
    node_type = "agent"
    strategy_types = {MarkdownNode: MarkdownMemoryStrategy}

    def __init__(self, info: NodeInfo, *args, runner: Callable | None = None, **kwargs):
        super().__init__(info, *args, **kwargs)
        self._access_origin = self
        self.runner = runner
        self.inputs = AgentInputs()
        strategy = next((strategy for node_type, strategy in self.strategy_types.items()
                         if isinstance(self, node_type)), EmptyMemoryStrategy)
        self.memory_strategy = strategy()
        tools = self.memory_strategy.create_tools(self)
        if tools is not None:
            self.install(tools)

    @access(channels=())
    def available_tools(self, node):
        discovery = node.modules.get("tool_discovery")
        return node.tools if discovery is None else Tools((node.tools, discovery.discover()))

    def update_inputs(self, source: str, **patch) -> dict:
        return self.inputs.update(source, patch)

    @property
    def auto_memory(self):
        return self.memory_strategy.auto_memory

    def run(self, new_input: str) -> str:
        if self.runner is None:
            raise NotImplementedError("Agent 节点尚未接入模型执行")
        return self.runner(new_input, Tools(self.available_tools().values()))


class MarkdownAgentNode(AgentNode, MarkdownNode):
    pass
