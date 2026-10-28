"""成员提出候选、同伴验收、自动交付；沿用旧协作协议。"""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from time import time
from uuid import uuid4

from app.runtime.requester import requester_id
from app.runtime.agent_policy import agent_defaults
from app.runtime.signal_work import current_work
from domain.core import CallableTool, Module, access
from domain.json_values import thaw
from . import state as rules
from .workspace import Workspace
from .command_logs import CommandLogs

TOOLS = json.loads(Path(__file__).with_name("tools.json").read_text(encoding="utf-8"))


class Members:
    def __init__(self, module):
        self._access_origin = module._access_origin
        self.channels = module.config.get("member_channel", ["collaboration"])
        self.strength = module.strength

    @access()
    async def collect(self, node):
        if node.node_type == "agent":
            return node.info.node_id


class CooperativeGroupModule(Module):
    def __init__(self, directory, transaction, emit, write_documents, config=None, state=None, command_logs=None, **access_settings):
        super().__init__("cooperation.group", **access_settings)
        self.directory = Path(directory).resolve()
        self.transaction, self.emit, self.write_documents = transaction, emit, write_documents
        self.config, self.state = deepcopy(config or {}), deepcopy(state or {})
        self._work = None
        self.request_limit = agent_defaults()["max_requests"]
        self.command_log_store = CommandLogs(self.directory) if command_logs is None else command_logs
        for spec in TOOLS:
            function = self.finish_tool if spec["operation"] == "finish" else getattr(self, spec["operation"])
            self.tools._add(CallableTool(spec["id"], function, spec["description"], deepcopy(spec["parameters"])))

    def _bind(self, node):
        super()._bind(node)
        source = sha256((node.info.node_id + "\0" + self.module_id).encode()).hexdigest()[:24]
        for tool, spec in zip(self.tools, TOOLS):
            tool.name = "mod_" + sha256((source + "\0" + spec["id"]).encode()).hexdigest()[:24]
            tool.description = node.info.node_id + " · " + spec["id"] + " · " + spec["description"]

    def _group(self, node):
        if not self.state:
            self.state.update(group_id=node.info.node_id, phase="ready", members=[], run_id=None, task=None, caller=None, deadline=None, report_reference=None,
                              entry_points={"output": self.config["output"], "findings": self.config["findings"]},
                              claims={}, entries=[], candidate=None, requests={}, jobs={}, notified=False,
                              unavailable={}, runs={}, archives=[], failure=None)
        return self.state

    def workspace_store(self):
        return Workspace(self.directory / self.config.get("directory", "workspace/cooperation"), self.state["members"])

    def actor(self, node):
        return requester_id.get() or node.info.node_id

    def member(self, node):
        actor = self.actor(node)
        if actor not in rules.active_members(self.state):
            raise PermissionError("节点不是本轮有效协作成员")
        return actor

    async def _call(self, operation, parameters):
        return next(iter((await self._operate(operation, parameters)).values()))

    @access(channels=())
    async def _operate(self, node, operation, parameters):
        group = self._group(node)
        actor, parameters = self.actor(node), thaw(parameters)
        if operation == "status":
            work = current_work.get()
            if work is not None:
                self._work = (group["run_id"], work)
            result = deepcopy(group)
            query = parameters.get("query")
            result["entries"] = [entry for entry in result["entries"] if query.casefold() in entry["content"].casefold() or query == entry["id"]] if query else result["entries"][-20:]
            result.update(active_members=rules.active_members(group), entry_count=len(group["entries"]))
            if group["members"]:
                result["repository"] = self.workspace_store().repository()
            return result
        if operation == "command_logs":
            return self.command_log_store.tool_datanet_command_logs(actor, parameters)
        targets = [node.info.node_id, group["entry_points"]["output"], group["entry_points"]["findings"]]
        if operation == "start":
            if group["phase"] in rules.ACTIVE:
                raise ValueError("小组正在执行任务，使用 status 查看或 stop 收尾")
            if not isinstance(parameters.get("task"), str) or not parameters["task"].strip():
                raise ValueError("start 必须提供非空 task")
            minutes = parameters.get("budget_minutes", 30)
            if isinstance(minutes, bool) or not isinstance(minutes, (float, int)) or not .1 <= minutes <= 1440:
                raise ValueError("budget_minutes 须在 0.1 至 1440 之间")
            members = [value for value in (await Members(self).collect()).values() if value is not None]
            if actor in members:
                raise PermissionError("由网络调用者启动或停止小组")
            if not members:
                raise ValueError("协作成员尚未装配")
            workspace = Workspace(self.directory / self.config.get("directory", "workspace/cooperation"), members)
            workspace.prepare()
            async with self.transaction(targets, timeout=20):
                if group["phase"] in rules.ACTIVE:
                    raise ValueError("小组正在执行任务，使用 status 查看或 stop 收尾")
                await self._archive()
                await self._write("output", "")
                await self._write("findings", "")
                group.update(phase="running", caller=actor, task=parameters["task"], members=members,
                             run_id=str(uuid4()), started_at=time(), deadline=time() + minutes * 60,
                             claims={}, entries=[], candidate=None, requests={}, jobs={}, notified=False,
                             failure=None, archive_path=None, report_reference=None, unavailable={}, loss_notice_sent=False)
            self.emit(node, access_strength=self.strength, channels=["collaboration.work"], strength=2,
                      content={"run_id": group["run_id"]}, timeout_seconds=minutes * 60, node_timeout_seconds=minutes * 60)
            return deepcopy(group)
        if operation == "workspace":
            self.member(node)
            if parameters["action"] != "inspect" and group["phase"] != "running":
                raise ValueError("仅运行阶段允许修改共同成果")
            result = self.workspace_store().invoke(actor, parameters["action"], parameters.get("message", "Publish contribution"))
            artifacts = self.command_log_store.directory(actor)
            return dict(result, artifacts_path=str(artifacts))
        async with self.transaction(targets, timeout=20):
            before = len(group["entries"])
            if operation in ("claim", "note", "finish"):
                self.member(node)
                parameters["actor"] = actor
            if operation == "finish" and parameters["action"] == "propose" and group["phase"] == "running" and not group["candidate"] and not any(c["state"] == "active" for c in group["claims"].values()):
                artifacts = self.command_log_store.directory(actor)
                logs = self.command_log_store.logs(actor, parameters.get("log_ids"), since=group.get("started_at", 0))
                parameters["review"] = self.workspace_store().proposal(actor, parameters.get("test_scripts", []), parameters.get("test_results", []), logs, artifacts)
            if operation in ("claim", "note", "finish"):
                result = getattr(rules, operation)(group, parameters)
            elif operation == "request":
                self.member(node)
                count = group["requests"].get(actor, 0)
                if count >= self.request_limit:
                    raise RuntimeError("模型请求次数达到上限 " + str(self.request_limit))
                group["requests"][actor] = count + 1
                result = dict(requests=count + 1)
            elif operation == "member_exit":
                if actor != parameters["target"] and actor != group.get("caller"):
                    raise PermissionError("只能退出自己，调用者可处理失效成员")
                result = rules.member_exit(group, parameters)
                if not rules.active_members(group) and group["phase"] in rules.ACTIVE:
                    group.update(phase="failed", failure="本轮全部成员无法继续")
            elif operation == "stop":
                if actor != group.get("caller"):
                    raise PermissionError("由本次协作调用者停止小组")
                if group["phase"] in rules.ACTIVE:
                    group.update(phase=parameters.get("phase", "stopped"), failure=parameters.get("failure"))
                result = deepcopy(group)
            else:
                raise ValueError("Unknown cooperation operation: " + operation)
            for entry in group["entries"][before:]:
                await self._write("findings", json.dumps(entry, ensure_ascii=False) + "\n", append=True)
            if group["phase"] == "completed":
                await self._write("output", group["candidate"]["content"])
            if group["phase"] in rules.TERMINAL:
                await self._archive()
            if operation in ("finish", "member_exit", "stop"):
                return deepcopy(group)
            return result

    @access(channels=["collaboration.delivery"])
    async def _write(self, node, field, text, append=False):
        if node.info.node_id != self.state["entry_points"][field]:
            return
        if append:
            node.dataer.append(text)
        else:
            node.dataer.write(text)

    @access(channels=["collaboration.delivery"])
    async def _documents(self, node):
        if node.info.node_id in self.state["entry_points"].values():
            return node.dataer.read()

    async def _archive(self):
        group = self.state
        if not group.get("run_id") or group["run_id"] in group.get("runs", {}):
            return
        documents = await self._documents()
        home = "cooperation/" + group["group_id"].encode().hex() + "/runs/" + group["run_id"]
        record = {key: deepcopy(group.get(key)) for key in ("run_id", "task", "phase", "failure", "claims", "entries", "candidate", "requests", "jobs", "report_reference", "unavailable", "loss_notice_sent")}
        files = {}
        for name, field in (("output.md", "output"), ("findings.md", "findings")):
            record[name] = home + "/" + name
            files[record[name]] = documents[group["entry_points"][field]]
        files[home + "/run.json"] = json.dumps(record, ensure_ascii=False, indent=2)
        self.write_documents(files)
        group["archive_path"] = home
        group["archives"] = list(dict.fromkeys([*group.get("archives", []), *files]))
        group.setdefault("runs", {})[group["run_id"]] = dict(run_id=group["run_id"], task=group["task"], phase=group["phase"], archive_path=home, report_reference=group.get("report_reference"))

    async def request(self):
        return await self._call("request", {})

    async def start(self, task, budget_minutes=30):
        return await self._call("start", dict(task=task, budget_minutes=budget_minutes))

    async def status(self, section="all", query=None):
        result = await self._call("status", dict(query=query))
        if section == "all":
            return result
        fields = {"summary": ("task", "members", "active_members", "unavailable", "requests", "failure"), "claims": ("claims",), "records": ("entries", "entry_count"), "candidate": ("candidate",)}
        return dict(group_id=result["group_id"], phase=result["phase"], **{key: result[key] for key in fields[section]})

    async def claim(self, **parameters):
        return await self._call("claim", parameters)

    async def command_logs(self, **parameters):
        return await self._call("command_logs", parameters)

    async def note(self, **parameters):
        return await self._call("note", parameters)

    async def workspace(self, action, message="Publish contribution"):
        return await self._call("workspace", dict(action=action, message=message))

    async def finish(self, **parameters):
        result = await self._call("finish", parameters)
        actor = requester_id.get()
        text = None
        if result["phase"] == "review" and parameters["action"] == "propose":
            text = "本组已提出成果候选：" + result["candidate"]["id"] + "。读取候选验收材料，审阅测试脚本、命令、结果和已知问题；无异议批准，有疑问指出具体问题再补测。"
        elif parameters["action"] == "reject":
            text = "成果候选被否决：" + parameters["evidence"] + "。小组恢复工作，请协商认领并修正。"
        if result["phase"] == "completed":
            text = "共同成果已获本轮剩余成员验收，协作结束。请停止当前工作并简短回复。"
        await self._notify(result, actor, text)
        return dict(phase=result["phase"], candidate=result["candidate"], output_id=result["entry_points"]["output"])

    async def finish_tool(self, **parameters):
        result = await self.finish(**parameters)
        approved = result["candidate"] and requester_id.get() in result["candidate"]["approvals"]
        return dict(format="nexarbor-tool-control/v1", conclude=result["phase"] == "completed" or bool(approved), data=result)

    async def member_exit(self, target, reason, status="failed"):
        result = await self._call("member_exit", dict(target=target, reason=reason, status=status))
        await self._notify(result, target, "成员 " + target + " 已退出本轮，其未完成认领已释放。读取协作状态并继续推进。")
        return result

    async def stop(self, failure=None, phase="stopped"):
        result = await self._call("stop", dict(failure=failure, phase=phase))
        await self._notify(result, None, "本轮协作已结束：" + phase)
        return result

    async def _notify(self, result, sender, text):
        async def deliver():
            if text:
                await self._broadcast(sender, text, result["run_id"] + ":" + str(uuid4()), result["phase"], (result.get("candidate") or {}).get("id"))
            if result["phase"] in rules.TERMINAL:
                await self._deliver_result(result)
                await self._mark_notified()
        work = current_work.get()
        if work is None and self._work is not None and self._work[0] == result["run_id"] and not self._work[1].closed:
            work = self._work[1]
        if work is None:
            await deliver()
        else:
            work.post(deliver, result["group_id"] + "/cooperation/notify")

    @access(channels=["collaboration"])
    async def _broadcast(self, node, sender, text, event_id, phase, candidate_id):
        if node.info.node_id == sender or node.info.node_id not in rules.active_members(self.state):
            return
        if phase == "review":
            current = self.state.get("candidate")
            if not current or current["id"] != candidate_id or node.info.node_id in current["approvals"]:
                return
        await node.modules.get("cooperation.member").receive(text, event_id)

    @access(channels=["collaboration.result"])
    async def _deliver_result(self, node, result):
        if node.info.node_id != result.get("caller"):
            return
        coordinator = node.modules.get("app.coordinator.entry")
        if coordinator is not None:
            await coordinator.cooperation_completed(result)
        node.update_inputs("cooperation:" + result["group_id"], inputs=[dict(id=result["run_id"] + ":result", text=json.dumps(dict(type="cooperation_result", group_id=result["group_id"], run_id=result["run_id"], status=result["phase"], output_id=result["entry_points"]["output"], archive_path=result.get("archive_path"), failure=result.get("failure")), ensure_ascii=False), delivery="steer")])

    @access(channels=())
    async def _mark_notified(self, node):
        self.state["notified"] = True
