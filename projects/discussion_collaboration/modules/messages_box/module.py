"""消息投递与幂等回执；收费和入箱使用同一节点事务。"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from app.runtime.requester import as_requester, requester_id
from app.runtime.signal_work import current_work
from app.transactions.locks import require_transaction_node
from domain.core import CallableTool, Module, access

TOOLS = json.loads(Path(__file__).with_name("tools.json").read_text(encoding="utf-8"))


def _plan(module,message,identity,fingerprint):
    messages=deepcopy(module.state.get('messages',[]));seen=deepcopy(module.state.get('seen',[]))
    if identity is not None:
        for receipt in reversed(seen):
            if receipt['key']!=identity:continue
            if receipt['fingerprint']!=fingerprint:raise ValueError('相同去重键不能发送不同内容')
            return None,dict(message,id=receipt['id'],duplicate=True,ap=None)
    messages.append(message)
    if identity is not None:seen.append(dict(key=identity,fingerprint=fingerprint,id=message['id']))
    limit=int(module.config.get('max_messages',200))
    return dict(messages=messages[-limit:],seen=seen[-max(limit,200):]),dict(message,duplicate=False,ap=None)

def _commit(module,candidate):
    for field,value in candidate.items():module.state[field]=value


class Accounts:
    def __init__(self, module):
        self._access_origin = module._access_origin
        self.channels = module.config.get("record_channels", ["location", "records", "road"])
        self.channel_mode = module.config.get("channel_modes", {}).get("record_channels", "allow")
        self.strength = module.strength

    @access()
    async def collect(self, node, sender):
        if node.info.node_id == sender:
            return node.modules.get("records.store")


class MessagesBoxModule(Module):
    def __init__(self, transaction, config=None, state=None, **access_settings):
        super().__init__("messages.box", **access_settings)
        self.transaction = transaction
        self.config = deepcopy(config or {})
        self.state = deepcopy(state or {})
        for spec in TOOLS:
            self.tools._add(CallableTool(spec["id"], getattr(self, spec["operation"]),
                                         spec["description"], deepcopy(spec["parameters"])))

    def _bind(self, node):
        super()._bind(node)
        source_id = sha256((node.info.node_id + "\0" + self.module_id).encode()).hexdigest()[:24]
        for tool, spec in zip(self.tools, TOOLS):
            tool.name = "mod_" + sha256((source_id + "\0" + spec["id"]).encode()).hexdigest()[:24]
            tool.description = node.info.node_id + " · " + spec["name"] + " · " + spec["description"]

    async def send(self, text, topic="", key=None):
        return next(iter((await self._send(text, topic, key)).values()))

    @access()
    async def _sender(self, node, sender):
        if node.info.node_id == sender:
            return dict(node_type=node.node_type, records=node.modules.get("records.store"))

    @access(channels=())
    async def _send(self, node, text, topic, key):
        require_transaction_node(node.info.node_id)
        sender = requester_id.get() or node.info.node_id
        identity = json.dumps([sender, key], ensure_ascii=False, separators=(",", ":")) if key is not None else None
        fingerprint = json.dumps(dict(text=text, topic=topic), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        message = dict(id=uuid4().hex, **{"from": sender}, to=node.info.node_id, text=text, topic=topic)
        info = (await self._sender(sender))[sender]
        if self.config.get("require_agent", True) and info["node_type"] != "agent":
            raise ValueError("只有真实 Agent 节点可以发送消息")
        cost = self.config.get("send_cost", 0)
        candidate, result = _plan(self, message, identity, fingerprint)
        if candidate is None:return result
        if cost:
            account = (await Accounts(self).collect(sender))[sender]
            async with self.transaction(list(dict.fromkeys([node.info.node_id, sender])), timeout=20):
                candidate, result = _plan(self, message, identity, fingerprint)
                if candidate is not None:
                    values = (await account.read())["values"]
                    ap = values.get("ap")
                    if type(ap) not in (int, float) or ap < cost:raise ValueError("行动点不足，无法发送消息")
                    receipt = json.dumps([self.module_id, node.info.node_id, sender, "send", key if key is not None else message["id"]],
                                         ensure_ascii=False, separators=(",", ":"))
                    charged = await account.apply(deltas={"ap": -cost}, key=receipt)
                    result["ap"] = charged["values"]["ap"]
                    _commit(self, candidate)
        else:
            _commit(self, candidate)
        work = current_work.get()
        if not result["duplicate"] and self.config.get("notify_activity", False) and work is not None:
            try:
                notify = node.modules.get("agents.activity").notify
                async def later():
                    with as_requester(node.info.node_id):return await notify(key=work.signal_id)
                result["notification"] = work.post(later, node.info.node_id + "/agents.activity/notify")
            except Exception as error:
                result["notification"] = dict(queued=False, error=str(error))
        return result

    async def read(self, limit=20):
        return next(iter((await self._read(limit)).values()))

    @access(channels=())
    async def _read(self, node, limit):
        if self.config.get("read_policy", "self") != "reachable" and (requester_id.get() or node.info.node_id) != node.info.node_id:
            raise PermissionError("该消息箱仅允许所在节点自己读取")
        return dict(messages=deepcopy(self.state.get("messages", []))[-limit:])

    async def clear(self):
        return next(iter((await self._clear()).values()))

    @access(channels=())
    async def _clear(self, node):
        if (requester_id.get() or node.info.node_id) != node.info.node_id:
            raise PermissionError("只有消息箱所在节点可以清理本地消息")
        require_transaction_node(node.info.node_id)
        count = len(self.state.get("messages", []))
        _commit(self, dict(messages=[], seen=[]))
        return dict(cleared=count)
