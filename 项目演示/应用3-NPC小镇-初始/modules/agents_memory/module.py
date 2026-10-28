"""角色的原有私人记忆业务，只按明确请求写入和查询，不自动组装上下文。"""

from copy import deepcopy
import json
from pathlib import Path

from app.runtime.requester import requester_id
from app.transactions.locks import require_transaction_node
from domain.core import CallableTool, Module, access


TOOLS = json.loads(Path(__file__).with_name("tools.json").read_text(encoding="utf-8"))


def _memory_result(memories, duplicate=False):
    return dict(duplicate=duplicate, memories=deepcopy(memories), count=len(memories))


class AgentsMemoryModule(Module):
    def __init__(self, config=None, state=None, **access_settings):
        super().__init__("agents.memory", **access_settings)
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec["name"], getattr(self, spec["name"]),
                                         spec["description"], deepcopy(spec["parameters"])))

    async def remember(self, text, key=None):
        return next(iter((await self._remember(text, key)).values()))

    @access(channels=())
    async def _remember(self, node, text, key):
        if (requester_id.get() or node.info.node_id) != node.info.node_id:
            raise PermissionError("只能操作自己的私人记忆")
        require_transaction_node(node.info.node_id)
        memories = [dict(item) for item in self.state.get("memories", []) if isinstance(item, dict)]
        if key is not None:
            for item in memories:
                if item.get("key") == key:
                    if item.get("text") == text:
                        return _memory_result(memories, duplicate=True)
                    raise ValueError("相同记忆键已经记录了不同内容，不能覆盖")
        entry = {"text": text}
        if key is not None:entry["key"] = key
        memories.append(entry)
        limit = self.config.get("max_memories", 100)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:limit = 100
        if len(memories) > limit:memories = memories[-limit:]
        self.state["memories"] = memories
        return _memory_result(memories)

    async def recall(self, query=""):
        return next(iter((await self._recall(query)).values()))

    @access(channels=())
    async def _recall(self, node, query):
        if (requester_id.get() or node.info.node_id) != node.info.node_id:
            raise PermissionError("只能操作自己的私人记忆")
        query = query or ""
        needle = str(query).casefold()
        memories = []
        for item in self.state.get("memories", []):
            if not isinstance(item, dict):continue
            text = str(item.get("text", ""))
            if not needle or needle in text.casefold():memories.append(dict(item))
        return dict(query=str(query), memories=deepcopy(memories), count=len(memories))
