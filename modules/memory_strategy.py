"""记忆策略负责提供工具；具体数据操作由节点的 Dataer 完成。"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import partial

from domain.core import access
from domain.core import Module
from domain.core import Tools
from domain.declared_tool import DeclaredTool


class MemoryStrategy(ABC):
    auto_memory: Callable[[str], list[str]] | None = None

    @abstractmethod
    def create_tools(self, owner: Module) -> Tools | None:
        pass


class EmptyMemoryStrategy(MemoryStrategy):
    def create_tools(self, owner: Module) -> None:
        return None


@access(channels=())
def _query(owner, node, query: str = "") -> str:
    return node.dataer.query(query)


@access(channels=())
def _modify(owner, node, old_text: str, new_text: str) -> int:
    return node.dataer.modify(old_text, new_text)


@access(channels=())
def _append(owner, node, content: str) -> int:
    return node.dataer.append(content)


class MarkdownMemoryStrategy(MemoryStrategy):
    def create_tools(self, owner: Module) -> Tools:
        return Tools([
            DeclaredTool(
                "memory_query", partial(_query, owner),
                description="查询本节点 Markdown 记忆，按节点 ID 返回结果。query 留空返回全文，否则返回包含该文本的行。",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "additionalProperties": False,
                },
                modules=(owner,), private=True,
            ),
            DeclaredTool(
                "memory_modify", partial(_modify, owner),
                description="精确替换记忆中的唯一文本片段，需提供足够上下文；按节点 ID 返回替换次数，不返回全文。",
                parameters={
                    "type": "object",
                    "properties": {
                        "old_text": {"type": "string", "minLength": 1},
                        "new_text": {"type": "string"},
                    },
                    "required": ["old_text", "new_text"],
                    "additionalProperties": False,
                },
                modules=(owner,), private=True,
            ),
            DeclaredTool(
                "memory_append", partial(_append, owner),
                description="将 content 原样追加到记忆末尾，不自动补换行；按节点 ID 返回追加字符数，不返回全文。",
                parameters={
                    "type": "object",
                    "properties": {"content": {"type": "string"}},
                    "required": ["content"],
                    "additionalProperties": False,
                },
                modules=(owner,), private=True,
            ),
        ])
