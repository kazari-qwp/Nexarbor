"""沿 chat 频道把便笺转交给收件人自己的消息箱。"""

from copy import deepcopy
import json
from pathlib import Path

from app.runtime.requester import as_requester, requester_id
from domain.core import CallableTool, Module, access

TOOLS = json.loads(Path(__file__).with_name("tools.json").read_text(encoding="utf-8"))


class MessagesRelayModule(Module):
    def __init__(self, config=None, state=None, **access_settings):
        super().__init__("messages.relay", **access_settings)
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec["id"], getattr(self, spec["operation"]),
                                         spec["description"], deepcopy(spec["parameters"])))

    @access(channels=())
    async def _identity(self, node):
        return node.info.node_id

    async def send_to(self, recipient, text, topic="", key=None):
        origin = next(iter((await self._identity()).values()))
        if recipient == origin:raise ValueError("收件人必须是自己以外的另一位真实 Agent")
        with as_requester(requester_id.get() or origin):
            reached = await self._forward(recipient, text, topic, key)
        if recipient not in reached:raise ValueError(f"收件人 {recipient} 当前不可达")
        return reached[recipient]

    @access(channels=("chat",))
    async def _forward(self, node, recipient, text, topic, key):
        if node.info.node_id != recipient:return None
        if node.node_type != "agent":raise ValueError(f"收件人 {recipient} 不是真实 Agent")
        box = node.modules.get("messages.box")
        if box is None:raise ValueError("收件人未装配消息箱")
        try:return await box.send(text=text, topic=topic, key=key)
        except Exception as error:
            raise ValueError(f"收件人 {recipient} 的消息箱拒绝投递：{error}") from error
