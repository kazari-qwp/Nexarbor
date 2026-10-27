"""讨论会话：发现席位，再由信号推进发言、决策和记录。"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from domain.core import CallableTool, Module, access
from . import operations
from .state import ROLES, _member_channels, _mark_failed, _record_error, _state

TOOLS = json.loads(Path(__file__).with_name("tools.json").read_text(encoding="utf-8"))


class Seats:
    def __init__(self, module):
        self._access_origin = module._access_origin
        self.channels = _member_channels(module)
        self.channel_mode = module.config.get("channel_modes", {}).get("member_channel", "allow")
        self.strength = module.strength

    @access()
    async def describe(self, node):
        seat = node.modules.get("discussion.seat")
        if seat is None:
            return None
        try:
            return {"data": await seat.describe()}
        except Exception as error:
            return {"error": str(error)}


class DiscussionSessionModule(Module):
    def __init__(self, transaction, emit, config=None, state=None, **access_settings):
        super().__init__("discussion.session.rev_697d80a33d", **access_settings)
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

    async def discover(self):
        seats = {key:value for key,value in (await Seats(self).describe()).items() if value is not None}
        if not seats:
            raise ValueError("未发现 discussion.seat 席位；请确认席位模块已安装，并通过频道 "
                             + "、".join(_member_channels(self)) + " 可达")
        found, failures = [], []
        for node_id, result in seats.items():
            if "error" in result:
                failures.append(f"{node_id}：{result['error'] or 'describe 失败'}")
                continue
            data = result["data"]
            member_id = str(data.get("id") or node_id)
            name = str(data.get("name") or node_id)
            role = str(data.get("role") or "")
            if role not in ROLES:
                failures.append(f"{member_id}：角色“{role or '空'}”不是 leader/recorder/member")
                continue
            if any(item["id"] == member_id for item in found):
                failures.append(f"{member_id}：席位 id 重复")
                continue
            found.append({"id":member_id, "name":name, "role":role, "status":"active"})
        leaders = [item for item in found if item["role"] == "leader"]
        recorders = [item for item in found if item["role"] == "recorder"]
        members = [item for item in found if item["role"] == "member"]
        problems = []
        if len(leaders) != 1:
            problems.append(f"需要恰好 1 名 leader，实际 {len(leaders)} 名")
        if len(recorders) != 1:
            problems.append(f"需要恰好 1 名 recorder，实际 {len(recorders)} 名")
        if not members:
            problems.append("需要至少 1 名 member，实际 0 名")
        if failures:
            problems.append("部分席位无法读取：" + "；".join(failures))
        if problems:
            listing = "；".join(f'{item["name"]}({item["id"]})={item["role"]}' for item in found) or "无"
            raise ValueError("参与者发现不符合要求：" + "；".join(problems) + "。发现结果：" + listing)
        return found

    async def _call(self, operation, parameters):
        return next(iter((await self._operate(operation, parameters)).values()))

    @access(channels=())
    async def _operate(self, node, operation, parameters):
        _state(self)
        try:
            return await getattr(operations, "_" + operation)(self, node, parameters)
        except ValueError as error:
            _record_error(self, operation, str(error))
            raise
        except Exception as error:
            _mark_failed(self, operation, str(error))
            _record_error(self, operation, str(error))
            raise

    async def start(self, task, rounds=None, key=None):
        parameters = {"task":task}
        if rounds is not None: parameters["rounds"] = rounds
        if key is not None: parameters["key"] = key
        return await self._call("start", parameters)

    async def speak(self, text, round=None, key=None):
        return await self._call("speak", {"text":text, "round":round, "key":key})

    async def read(self, round=None, limit=20):
        return await self._call("read", {"round":round, "limit":limit})

    async def decide(self, decision, tasks=None, key=None):
        return await self._call("decide", {"decision":decision, "tasks":tasks or [], "key":key})

    async def draft(self, section, text, key=None):
        return await self._call("draft", {"section":section, "text":text, "key":key})

    async def finish(self, title=None):
        return await self._call("finish", {"title":title})

    async def advance(self, reason=None):
        return await self._call("advance", {"reason":reason})

    async def leave(self, member=None, reason=None):
        return await self._call("leave", {"member":member, "reason":reason})

    async def stop(self, reason=None):
        return await self._call("stop", {"reason":reason})

    async def status(self, include_history=False):
        return await self._call("status", {"include_history":include_history})
