"""实际讨论、协作和整合模块的阶段接线；真实模型应用验收另行运行。"""

import asyncio
from copy import deepcopy
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.module_emitter import emit_module_signal
from app.runtime.requester import as_requester
from domain.agent import AgentNode
from domain.core import CallableTool, Link, Network, Node, NodeInfo
from projects.discussion_collaboration.modules.app_coordinator import AppCoordinatorModule
from projects.discussion_collaboration.modules.app_coordinator.state import _Fail, _normalize_tasks
from projects.discussion_collaboration.modules.collab_board import CollabBoardModule
from projects.discussion_collaboration.modules.collab_participant import CollabParticipantModule
from projects.discussion_collaboration.modules.discussion_seat import DiscussionSeatModule
from projects.discussion_collaboration.modules.discussion_session import DiscussionSessionModule
from projects.discussion_collaboration.modules.git_integrator import GitIntegratorModule
from test_git_integrator import HARNESS, OfficialTerminal

ROOT = Path(__file__).resolve().parents[1]
DISCUSSION = "discussion.session.rev_697d80a33d"
BOARD = "collab.board.rev_9191e2380f.rev_96569f0263"
GIT = "git.integrator.rev_2863bbe53e.rev_c376775a7e"


class AppCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix=".coordinator-", dir=ROOT / "build")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = Node(NodeInfo("root", "Coordinator"))
        self.discussion = Node(NodeInfo("discussion", "Discussion"))
        self.group = Node(NodeInfo("collab", "Collaboration"))
        self.seats = {role:AgentNode(NodeInfo(role, role.title())) for role in ("leader", "recorder", "member")}
        self.workers = [AgentNode(NodeInfo(name, name)) for name in ("one", "two")]
        self.root.links.add(Link("discussion", "discussion"))
        self.root.links.add(Link("collab", ["collaboration", "collaboration.review"]))
        for role, node in self.seats.items():
            node.install(DiscussionSeatModule({"role":role}))
            self.discussion.links.add(Link(role, "discussion"))
        for node in self.workers:
            self.group.links.add(Link(node.info.node_id, ["collaboration", "collaboration.work", "collaboration.review"]))
        self.factories = {
            "app.coordinator.entry":lambda record:self.make_coordinator(),
            DISCUSSION:lambda record:DiscussionSessionModule(self.transaction, self.emit, {"rounds":1}, strength=2),
            BOARD:lambda record:CollabBoardModule(self.transaction, self.emit, {"integrator_module":GIT}, strength=2),
            GIT:lambda record:GitIntegratorModule({"repository":str(self.directory / "repository")}, strength=2),
            "collab.participant":lambda record:CollabParticipantModule({"integrator_module":GIT}),
            "discussion.seat":lambda record:DiscussionSeatModule(),
        }
        self.saver = NetworkSaver()
        self.saver.tables.module_types.update(self.factories)
        self.saver.tables.tool_types["pwsh"] = lambda node, record:CallableTool("pwsh", self.invoke)
        self.coordinator = self.make_coordinator()
        self.session = self.factories[DISCUSSION](None)
        self.board = self.factories[BOARD](None)
        self.integrator = self.factories[GIT](None)
        self.participant = self.factories["collab.participant"](None)
        self.root.install(self.coordinator)
        self.discussion.install(self.session)
        for module in (self.board, self.integrator, self.participant):self.group.install(module)
        self.group.install(CallableTool("pwsh", self.invoke))
        self.backend = Backend(self.directory, network=Network([self.root, self.discussion, self.group, *self.seats.values(), *self.workers]), saver=self.saver)

    def make_coordinator(self):
        return AppCoordinatorModule(self.emit, {"discussion_node":"discussion", "board_node":"collab", "integrator_node":"collab"}, strength=2)

    def transaction(self, nodes, **options):
        return self.backend.node_locks.transaction(nodes, **options)

    def emit(self, node, **parameters):
        return emit_module_signal(self.backend.signals, node, **parameters)

    async def invoke(self, **arguments):
        return await self.terminal.invoke(**arguments)

    async def settle(self):
        while self.backend.signals._active:
            await asyncio.gather(*tuple(self.backend.signals._active.values()))

    async def asyncTearDown(self):
        await self.settle()
        self.backend.close()

    async def finish_discussion(self, tasks=None):
        for role in self.seats:
            with as_requester(role):await self.session.speak(text=role, round=1)
        with as_requester("leader"):
            await self.session.decide(decision="write files", tasks=tasks or [{"title":"Implement", "paths":["src"], "detail":"exact"}])
        with as_requester("recorder"):
            await self.session.draft(section="Plan", text="implement and verify")
            await self.session.finish(title="Deliverable")

    async def executing(self):
        await self.coordinator.start(task="Build", rounds=1, key="run")
        await self.finish_discussion()
        return await self.coordinator.handoff()

    async def test_start_and_handoff_use_actual_discussion_result_and_board_contract(self):
        first = await self.coordinator.start(task="Build", rounds=1, key="run")
        duplicate = await self.coordinator.start(task="different is intentionally ignored for same key", key="run")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(first["run"]["id"], duplicate["run"]["id"])
        with self.assertRaisesRegex(_Fail, "讨论尚未完成"):
            await self.coordinator.handoff()
        await self.finish_discussion()
        result = await self.coordinator.handoff()
        self.assertEqual(result["run"]["status"], "executing")
        self.assertEqual(result["tasks"], [{"title":"Implement", "paths":["src"], "detail":"exact"}])
        self.assertEqual(result["execution_run"], (await self.board.status())["run"]["id"])
        self.assertEqual(result["run"]["artifact_title"], "Deliverable")

    async def test_concurrent_starts_serialize_per_module_and_only_one_discussion_starts(self):
        results = await asyncio.gather(self.coordinator.start(task="one", rounds=1), self.coordinator.start(task="two", rounds=1), return_exceptions=True)
        self.assertEqual(sum(isinstance(value, dict) for value in results), 1)
        self.assertEqual(sum(isinstance(value, _Fail) for value in results), 1)
        self.assertEqual((await self.session.status())["status"], "discussing")

    async def test_access_blocks_downstream_without_matching_channel_and_keeps_run_unstarted(self):
        edge = next(edge for edge in self.root.links if edge.target_id == "discussion")
        self.root.links.remove(edge)
        self.root.links.add(Link("discussion", "wrong"))
        with self.assertRaisesRegex(_Fail, "不可达"):
            await self.coordinator.start(task="blocked")
        self.assertIsNone(self.coordinator.state["run"])
        self.assertEqual((await self.session.status())["status"], "idle")

    async def test_status_keeps_successful_sections_when_one_target_fails(self):
        self.coordinator.config["integrator_node"] = "missing"
        result = await self.coordinator.status()
        self.assertEqual(result["discussion"]["status"], "idle")
        self.assertIsNone(result["board"]["run"])
        self.assertEqual(result["integration"]["status"], "error")
        self.assertIn("不可达", result["integration"]["error"])
        self.assertEqual(len(result["errors"]), 1)

    async def test_stop_discussion_and_execution_keep_original_partial_reports(self):
        await self.coordinator.start(task="Build", rounds=1)
        stopped = await self.coordinator.stop(reason="stop discussion")
        self.assertEqual(stopped["run"]["status"], "stopped")
        self.assertEqual(stopped["discussion"]["status"], "ok")
        self.assertEqual((await self.session.status())["status"], "stopped")
        await self.executing()
        self.coordinator.config["board_node"] = "missing"
        stopped = await self.coordinator.stop(reason="stop with failure")
        self.assertEqual(stopped["run"]["status"], "stopped")
        self.assertEqual(stopped["board"]["status"], "error")
        self.assertEqual((await self.board.status())["run"]["status"], "running")

    async def test_reviewing_promotion_failure_is_reported_without_rebuilding_candidate(self):
        await self.executing()
        self.coordinator.state["run"].update(status="reviewing", candidate="cand-0000000000000000")
        self.integrator.state["candidate"] = {"id":"cand-0000000000000000", "status":"promotion_failed", "members":["one", "two"], "votes":{}}
        before = deepcopy(self.integrator.state["candidate"])
        with self.assertRaisesRegex(_Fail, "promote"):
            await self.coordinator.integrate(reason="retry")
        self.assertEqual(self.integrator.state["candidate"], before)
        self.assertEqual(self.coordinator.state["run"]["status"], "reviewing")

    def test_task_normalization_uses_decision_fallback_and_original_limits(self):
        task = {"title":"x" * 150, "description":"d" * 2500, "paths":["src", None, ""]}
        result = _normalize_tasks({"title":"Artifact"}, {"tasks":[task] * 25}, {"task":"Run"})
        self.assertEqual(len(result), 20)
        self.assertEqual(result[0], {"title":"x" * 120, "detail":"d" * 2000, "paths":["src"]})
        self.assertEqual(_normalize_tasks({"title":"Artifact", "body":"body"}, {}, {}), [{"title":"Artifact", "paths":[], "detail":"body"}])

    @unittest.skipUnless(HARNESS.is_file(), "Requires installed native Harness SDK")
    async def test_real_discussion_handoff_git_review_reopen_publish_and_cold_reopen(self):
        self.repo = self.directory / "repository"
        self.repo.mkdir()
        def git(*arguments):
            result = subprocess.run(["git", *arguments], cwd=self.repo, capture_output=True, text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:raise RuntimeError(result.stderr or result.stdout)
            return result.stdout.strip()
        git("init", "-b", "main")
        git("config", "user.name", "Migration verification")
        git("config", "user.email", "migration@localhost")
        (self.repo / "base.txt").write_text("base", encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "base")
        base = git("rev-parse", "HEAD")
        commits = {}
        for member in ("one", "two"):
            git("checkout", "-B", "member/" + member, base)
            (self.repo / (member + ".txt")).write_text(member, encoding="utf-8")
            git("add", ".")
            git("commit", "-m", member)
            commits[member] = git("rev-parse", "HEAD")
        git("checkout", "main")
        self.terminal = OfficialTerminal(self.directory)
        self.addAsyncCleanup(self.terminal.close)
        await self.terminal.start()
        await self.executing()
        for member, commit in commits.items():
            with as_requester(member):await self.participant.submit(commit=commit)
        candidate = (await self.coordinator.integrate())["candidate"]
        with as_requester("two"):await self.participant.veto(reason="check again")
        reopened = (await self.coordinator.integrate(reason="checked"))["candidate"]
        self.assertEqual(reopened["id"], candidate["id"])
        self.assertEqual(reopened["round"], 2)
        for member in commits:
            with as_requester(member):await self.participant.approve(reason="verified")
        published = await self.coordinator.promote()
        self.assertEqual(published["run"]["status"], "completed")
        self.assertEqual(git("rev-parse", "nexarbor/integration"), candidate["commit"])
        for member in commits:self.assertEqual(git("show", candidate["commit"] + ":" + member + ".txt"), member)
        await self.settle()
        self.backend.save()
        self.backend.close()
        self.backend = Backend(self.directory, saver=self.saver)
        self.coordinator = self.backend.network.get("root").modules.get("app.coordinator.entry")
        restored = await self.coordinator.status()
        self.assertEqual(restored["run"]["status"], "completed")
        self.assertEqual(restored["integration"]["candidate"]["id"], candidate["id"])
        self.assertEqual(restored["integration"]["candidate"]["status"], "passed")
