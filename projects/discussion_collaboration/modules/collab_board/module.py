"""认领协作板：成员自主认领路径，保留进度、退出与共享记录。"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from app.runtime.requester import as_caller
from app.transactions.locks import require_transaction_node
from domain.core import CallableTool, Module, access
from . import operations
from .state import BoardError, _config, _state

TOOLS = json.loads(Path(__file__).with_name("tools.json").read_text(encoding="utf-8"))


class Members:
    def __init__(self, module):
        self._access_origin = module._access_origin
        self.channels = _config(module)["member_channel"]
        self.channel_mode = module.config.get("channel_modes", {}).get("member_channel", "allow")
        self.strength = module.strength

    @access()
    async def collect(self, node):
        if node.node_type == "agent":
            return {"id":node.info.node_id, "name":node.info.name or node.info.node_id,
                    "status":"active", "left_reason":None}


class CollabBoardModule(Module):
    def __init__(self, transaction, emit, config=None, state=None, **access_settings):
        super().__init__("collab.board.rev_9191e2380f.rev_96569f0263", **access_settings)
        self.transaction = transaction
        self.emit = emit
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

    async def members(self):
        try:
            members = [entry for entry in (await Members(self).collect()).values() if entry is not None]
        except Exception as error:
            raise BoardError("无法沿成员发现频道查找成员：%s" % (str(error) or "请求失败")) from error
        if not members:
            raise BoardError("没有发现可参与的 Agent 成员；请检查成员发现频道、节点类型和连接")
        return members

    async def _call(self, operation, parameters):
        return next(iter((await self._operate(operation, parameters)).values()))

    @access(channels=())
    async def _operate(self, node, operation, parameters):
        _state(self)
        try:
            if operation == "open":
                return await operations._open(self, node, parameters)
            if operation in ("list", "status"):
                return getattr(operations, "_" + operation)(self, parameters)
            if operation in ("discover", "fail"):
                require_transaction_node(node.info.node_id)
                return operations._share(self, parameters, "discovery" if operation == "discover" else "failure")
            async with self.transaction([node.info.node_id], timeout=20):
                data = getattr(operations, "_" + operation + "_locked")(self, parameters)
            if operation == "leave":
                return await self._propagate_leave(node, parameters, data)
            return data
        except BoardError:
            raise
        except Exception as error:
            raise BoardError("协作板操作失败：%s" % (str(error) or "未知错误")) from error

    async def _propagate_leave(self, node, parameters, data):
        data["integrator"] = None
        data["integrator_error"] = None
        try:
            module_id = self.config.get("integrator_module", "")
            if module_id is None:
                module_id = ""
            if not isinstance(module_id, str):
                raise BoardError("配置 integrator_module 必须是字符串")
            module_id = module_id.strip()
            if not module_id:
                return data
            with as_caller(node.info.node_id):
                data["integrator"] = await node.modules.get(module_id).leave(
                    member=data["member"], reason=parameters.get("reason") or "主动退出")
        except Exception as error:
            data["integrator_error"] = str(error) or "整合器 leave 调用失败"
        return data

    async def open(self, tasks, run_id=None, key=None):
        return await self._call("open", {"tasks":tasks, "run_id":run_id, "key":key})

    async def list(self, include_closed=True):
        return await self._call("list", {"include_closed":include_closed})

    async def claim(self, task, paths, key=None):
        return await self._call("claim", {"task":task, "paths":paths, "key":key})

    async def extend(self, task, paths, key=None):
        return await self._call("extend", {"task":task, "paths":paths, "key":key})

    async def release(self, task, member=None, reason=None):
        return await self._call("release", {"task":task, "member":member, "reason":reason})

    async def complete(self, task, commit, summary, key=None):
        return await self._call("complete", {"task":task, "commit":commit, "summary":summary, "key":key})

    async def discover(self, text, task=None, key=None):
        return await self._call("discover", {"text":text, "task":task, "key":key})

    async def fail(self, text, task=None, key=None):
        return await self._call("fail", {"text":text, "task":task, "key":key})

    async def leave(self, member=None, reason=None):
        return await self._call("leave", {"member":member, "reason":reason})

    async def status(self, include_events=True):
        return await self._call("status", {"include_events":include_events})

    async def close(self, summary=None):
        return await self._call("close", {"summary":summary})
