"""旧协作成员循环：提出/批准后等待，否决通知后继续工作。"""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
from time import time

from app.runtime.requester import as_requester
from app.runtime.signal_work import current_work
from domain.core import Module, access

GUIDE = Path(__file__).parent.parent / "cooperative_group/MEMBER_GUIDE.md"


class CooperativeMemberModule(Module):
    signal_channels = ("collaboration.work",)

    def __init__(self, agent_run, config=None, state=None, **access_settings):
        super().__init__("cooperation.member", **access_settings)
        self.agent_run = agent_run
        self.config, self.state = deepcopy(config or {}), deepcopy(state or {})
        self._active = False

    async def on_model_request(self, event):
        if self._active:
            counts = await self._request()
            self.state["requests"] = next(value for value in counts.values() if value is not None)["requests"]

    @access(channels=["collaboration"])
    async def _request(self, node):
        group = node.modules.get("cooperation.group")
        if group is not None:
            return await group.request()

    async def on_signal(self, context):
        return next(iter((await self._run()).values()))

    @access(channels=["collaboration"])
    async def _view(self, node, workspace=False):
        group = node.modules.get("cooperation.group")
        if group is None:
            return
        result = await group.status()
        if workspace and result["phase"] in ("running", "review"):
            result["personal_workspace"] = await group.workspace("inspect")
        guide = GUIDE.read_text(encoding="utf-8")
        for tool, spec in zip(group.tools, json.loads(GUIDE.with_name("tools.json").read_text(encoding="utf-8"))):
            guide = guide.replace(spec["id"], tool.name)
        return dict(group=result, guide=guide)

    async def view(self, workspace=False):
        return next(value for value in (await self._view(workspace)).values() if value is not None)

    async def prepare(self):
        return next(iter((await self._prepare()).values()))

    @access(channels=())
    async def _prepare(self, node):
        view = await self.view(workspace=True)
        group = view["group"]
        approved = group.get("candidate") and node.info.node_id in group["candidate"]["approvals"]
        tail = "[协作组：" + group["group_id"] + "] 阶段：" + group["phase"] + "。"
        if group["phase"] == "review" and not approved:
            tail += "目前有成果等待审核。"
        return dict(format="nexarbor-context/v1", patch=dict(system_prompt="", context=[dict(id="cooperation:guide", text=view["guide"]), dict(id="cooperation:project", text=group.get("task") or ""), dict(id="cooperation:state", text=json.dumps(group, ensure_ascii=False))], inputs=[], tail=[tail]), sources=[], errors=[])

    async def receive(self, text, event_id):
        return next(iter((await self._receive(text, event_id)).values()))

    @access(channels=())
    async def _receive(self, node, text, event_id):
        node.update_inputs(self.module_id, inputs=[dict(id=event_id, text=text, delivery="steer")])
        work = current_work.get()
        if not self._active and work is not None:
            return work.post(lambda: self.on_signal(None), node.info.node_id + "/cooperation/resume")
        return dict(queued=True)

    @access(channels=["collaboration"])
    async def _retire(self, node, actor, reason):
        group = node.modules.get("cooperation.group")
        if group is not None:
            return await group.member_exit(actor, reason)

    @access(channels=())
    async def _run(self, node):
        if self._active:
            return dict(status="queued")
        self._active = True
        try:
            with as_requester(node.info.node_id):
                while True:
                    group = (await self.view())["group"]
                    if group["phase"] not in ("running", "review") or node.info.node_id in group.get("unavailable", {}):
                        return dict(status="completed", phase=group["phase"])
                    candidate = group.get("candidate")
                    if candidate and node.info.node_id in candidate["approvals"]:
                        return dict(status="waiting", phase="review", candidate_id=candidate["id"])
                    if self.state.get("run_id") != group["run_id"]:
                        self.state.update(run_id=group["run_id"], turns=0, requests=0)
                    left = group["deadline"] - time()
                    if left <= 0:
                        raise TimeoutError("协作时间预算已结束")
                    prompt = "共同目标尚未收尾。依据当前协作状态继续推进；已有候选时阅读验收材料，有异议指出具体问题，无异议提交批准。"
                    result = await asyncio.wait_for(self.agent_run(node.info.node_id, prompt), left)
                    self.state["turns"] += 1
        except Exception as error:
            with as_requester(node.info.node_id):
                await self._retire(node.info.node_id, str(error))
            raise
        finally:
            self._active = False
