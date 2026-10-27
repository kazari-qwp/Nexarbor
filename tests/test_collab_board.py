"""原协作板认领冲突、回执、退出同步和持久化行为。"""

import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.module_emitter import emit_module_signal
from app.runtime.requester import as_requester, caller_id, requester_id
from domain.agent import AgentNode
from domain.core import Link, Module, Network, Node, NodeInfo
from projects.discussion_collaboration.modules.collab_board import CollabBoardModule
from projects.discussion_collaboration.modules.collab_board.state import BoardError

ROOT = Path(__file__).resolve().parents[1]
BOARD = "collab.board.rev_9191e2380f.rev_96569f0263"


class CollabBoardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix=".collab-board-", dir=ROOT / "build")
        self.addCleanup(self.temp.cleanup)
        self.group = Node(NodeInfo("group", "Group"))
        self.members = [AgentNode(NodeInfo(name, name)) for name in ("one", "two")]
        for node in self.members:
            self.group.links.add(Link(node.info.node_id, "collaboration"))
        self.saver = NetworkSaver()
        self.saver.tables.module_types[BOARD] = lambda record:self.make()
        self.backend = Backend(self.temp.name, network=Network([self.group, *self.members]), saver=self.saver)
        self.board = self.make()
        self.group.install(self.board)

    def make(self):
        return CollabBoardModule(self.transaction, self.emit, strength=2)

    def transaction(self, nodes, **options):
        return self.backend.node_locks.transaction(nodes, **options)

    def emit(self, node, **parameters):
        return emit_module_signal(self.backend.signals, node, **parameters)

    async def settle(self):
        while self.backend.signals._active:
            await asyncio.gather(*tuple(self.backend.signals._active.values()))

    async def asyncTearDown(self):
        await self.settle()
        self.backend.close()

    async def call(self, actor, operation, **parameters):
        with as_requester(actor):
            return await getattr(self.board, operation)(**parameters)

    async def open(self, **parameters):
        return await self.call("control", "open", tasks=[{"id":"t", "title":"Implement", "paths":["src"]}], **parameters)

    async def test_open_duplicate_conflict_and_agent_discovery(self):
        first = await self.open(key="open")
        second = await self.open(key="open")
        self.assertEqual({entry["id"] for entry in first["members"]}, {"one", "two"})
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["run"], second["run"])
        with self.assertRaisesRegex(BoardError, "不同参数"):
            await self.call("control", "open", tasks=[{"title":"different"}], key="open")
        with self.assertRaisesRegex(BoardError, "正在进行"):
            await self.open()

    async def test_simultaneous_overlapping_claims_commit_only_one(self):
        await self.open()
        results = await asyncio.gather(*(self.call(actor, "claim", task="t", paths=["./src/"], key="claim") for actor in ("one", "two")), return_exceptions=True)
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)
        error = next(item for item in results if isinstance(item, Exception))
        self.assertIsInstance(error, BoardError)
        self.assertIn("路径冲突", str(error))
        self.assertEqual(len((await self.board.list())["tasks"][0]["claims"]), 1)

    async def test_nested_and_self_path_conflicts_leave_state_unchanged(self):
        await self.open()
        await self.call("one", "claim", task="t", paths=["src"])
        before = deepcopy(self.board.state)
        with self.assertRaisesRegex(BoardError, "路径冲突"):
            await self.call("two", "claim", task="t", paths=["src/a.py"])
        self.assertEqual(self.board.state, before)
        with self.assertRaisesRegex(BoardError, "你已认领"):
            await self.call("one", "extend", task="t", paths=["src/b.py"])
        self.assertEqual(self.board.state, before)
        await self.call("two", "claim", task="t", paths=["docs"])
        self.assertEqual(len((await self.board.list())["tasks"][0]["claims"]), 2)

    async def test_extend_complete_and_original_duplicate_receipt_after_close(self):
        await self.open()
        await self.call("one", "claim", task="t", paths=["src/a.py"], key="claim")
        result = await self.call("one", "extend", task="t", paths=["src/b.py"], key="extend")
        self.assertEqual(result["paths"], ["src/a.py", "src/b.py"])
        with self.assertRaisesRegex(BoardError, "十六进制"):
            await self.call("one", "complete", task="t", commit="invalid", summary="done")
        await self.call("one", "complete", task="t", commit="a" * 40, summary="done", key="done")
        await self.board.close(summary="round done")
        duplicate = await self.call("one", "complete", task="t", commit="a" * 40, summary="done", key="done")
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual((await self.board.list())["overview"]["completed"], 1)
        self.assertEqual((await self.board.list(include_closed=False))["tasks"], [])
        self.assertEqual((await self.board.list())["tasks"][0]["summary"], "done")

    async def test_member_cannot_release_or_expel_other_member(self):
        await self.open()
        await self.call("one", "claim", task="t", paths=["src"])
        before = deepcopy(self.board.state)
        with self.assertRaisesRegex(BoardError, "控制方"):
            await self.call("two", "release", task="t", member="one")
        with self.assertRaisesRegex(BoardError, "控制方"):
            await self.call("two", "leave", member="one")
        self.assertEqual(self.board.state, before)
        released = await self.call("control", "release", task="t", member="one")
        self.assertEqual(released["released_paths"], ["src"])
        self.assertEqual((await self.board.list())["tasks"][0]["status"], "open")

    async def test_leave_releases_unfinished_keeps_completed_and_is_idempotent(self):
        await self.board.open(tasks=[{"id":"t", "title":"unfinished"}, {"id":"done", "title":"completed"}])
        for task in ("t", "done"):
            await self.call("one", "claim", task=task, paths=[task])
        await self.call("one", "complete", task="done", commit="b" * 40, summary="done")
        first = await self.call("one", "leave", reason="bye")
        self.assertEqual(first["released_tasks"], ["t"])
        second = await self.call("one", "leave")
        self.assertTrue(second["duplicate"])
        tasks = {task["id"]:task for task in (await self.board.list())["tasks"]}
        self.assertEqual(tasks["done"]["claims"][0]["member"], "one")
        self.assertEqual(tasks["t"]["claims"], [])
        with self.assertRaisesRegex(BoardError, "已退出"):
            await self.call("one", "claim", task="t", paths=["src"])

    async def test_leave_integrator_failure_keeps_committed_board_and_identity(self):
        calls = []
        class Integrator(Module):
            def __init__(self):super().__init__("integrator.fixture")
            async def leave(module, **parameters):
                calls.append((parameters, caller_id.get(), requester_id.get()))
                raise RuntimeError("integrator fixture failed")
        self.saver.tables.module_types["integrator.fixture"] = lambda record:Integrator()
        self.group.install(Integrator())
        self.board.config["integrator_module"] = "integrator.fixture"
        await self.open()
        result = await self.call("one", "leave", reason="bye")
        self.assertIn("integrator fixture failed", result["integrator_error"])
        self.assertEqual(calls, [({"member":"one", "reason":"bye"}, "group", "one")])
        member = next(item for item in (await self.board.status())["members"] if item["id"] == "one")
        self.assertEqual(member["status"], "left")

    async def test_shared_records_idempotency_limits_and_closed_history(self):
        await self.open()
        self.board.config["max_shared"] = 10
        for index in range(12):
            await self.call("one", "discover", text=f"finding {index}", key=str(index))
        result = await self.call("one", "discover", text="finding 11", key="11")
        self.assertTrue(result["duplicate"])
        await self.call("two", "fail", text="failure", task="t", key="failure")
        view = await self.board.list()
        self.assertEqual(len(view["shared"]), 10)
        self.assertEqual(view["shared"][-1]["kind"], "failure")
        await self.board.close()
        self.assertEqual(len((await self.board.list())["shared"]), 10)
        self.assertEqual((await self.board.status(include_events=False))["events"], [])

    async def test_notification_failure_does_not_undo_open_and_retry_is_duplicate(self):
        def fail(node, **parameters):raise OSError("signal fixture failed")
        self.board.emit = fail
        result = await self.open(key="open")
        self.assertIn("signal fixture failed", result["signal_error"])
        self.assertEqual((await self.board.status())["run"]["status"], "running")
        self.assertTrue((await self.open(key="open"))["duplicate"])

    async def test_journal_reopen_keeps_claims_and_duplicate_keys(self):
        await self.open(key="open")
        await self.call("one", "claim", task="t", paths=["src/a.py"], key="claim")
        await self.settle()
        before = deepcopy(self.board.state)
        self.backend.save()
        self.backend.close()
        self.backend = Backend(self.temp.name, saver=self.saver)
        self.board = self.backend.network.get("group").modules.get(BOARD)
        self.assertEqual(self.board.state, before)
        self.assertTrue((await self.call("one", "claim", task="t", paths=["src/a.py"], key="claim"))["duplicate"])

    async def test_discovery_wrong_channel_and_strength_do_not_see_agents(self):
        self.board.config["member_channel"] = ["blocked"]
        with self.assertRaisesRegex(BoardError, "没有发现"):
            await self.open()
        self.assertIsNone((await self.board.status())["run"])

    async def test_foreign_transaction_cannot_write_shared_state(self):
        await self.open()
        await self.settle()
        before = deepcopy(self.board.state)
        async with self.transaction(["one"]):
            with self.assertRaisesRegex(BoardError, "locked node group"):
                await self.call("one", "discover", text="invalid write")
        self.assertEqual(self.board.state, before)
