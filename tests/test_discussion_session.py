"""原讨论生命周期、权限、回执、失败报告和新信号端口。"""

import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.module_emitter import emit_module_signal
from app.runtime.requester import as_requester, requester_id
from domain.agent import AgentNode
from domain.core import Link, Network, Node, NodeInfo
from projects.discussion_collaboration.modules.discussion_seat import DiscussionSeatModule
from projects.discussion_collaboration.modules.discussion_session import DiscussionSessionModule

ROOT = Path(__file__).resolve().parents[1]
SESSION = "discussion.session.rev_697d80a33d"


class DiscussionSessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix=".discussion-session-", dir=ROOT / "build")
        self.addCleanup(self.temp.cleanup)
        self.group = Node(NodeInfo("group", "Discussion"))
        self.people = {role:AgentNode(NodeInfo(role, role.title())) for role in ("leader", "recorder", "member")}
        for role, node in self.people.items():
            node.install(DiscussionSeatModule({"role":role}))
            self.group.links.add(Link(role, "members"))
        self.saver = NetworkSaver()
        self.saver.tables.module_types.update({SESSION:lambda record:self.make(), "discussion.seat":lambda record:DiscussionSeatModule()})
        self.backend = Backend(self.temp.name, network=Network([self.group, *self.people.values()]), saver=self.saver)
        self.session = self.make()
        self.group.install(self.session)

    def make(self):
        return DiscussionSessionModule(self.transaction, self.emit, {"member_channel":["members"], "rounds":2}, strength=2)

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
            return await getattr(self.session, operation)(**parameters)

    async def start(self, **parameters):
        return await self.call("control", "start", task="build a library", **parameters)

    async def round(self, number):
        await asyncio.gather(*(self.call(role, "speak", text=role, round=number, key=f"{number}:{role}") for role in self.people))

    async def decision(self):
        await self.start(rounds=1)
        await self.round(1)
        return await self.call("leader", "decide", decision="write storage", tasks=[{"title":"storage", "paths":["src/store.py"]}], key="decision")

    async def test_full_two_round_decision_draft_artifact_and_history(self):
        first = await self.start(key="start")
        await self.round(1)
        status = await self.session.status()
        self.assertEqual((status["round"], status["phase"]), (2, "discussing"))
        await self.round(2)
        await self.call("leader", "decide", decision="use files", tasks=[{"title":"Store", "paths":["store.py"], "detail":"atomic"}])
        await self.call("recorder", "draft", section="Plan", text="first")
        await self.call("recorder", "draft", section="Plan", text="final")
        artifact = (await self.call("recorder", "finish", title="Plan"))["artifact"]
        self.assertIn("use files", artifact["content"])
        self.assertIn("store.py", artifact["content"])
        self.assertIn("final", artifact["content"])
        self.assertEqual(len((await self.session.read())["draft"]["sections"]), 1)
        self.assertEqual((await self.call("recorder", "finish"))["artifact"], artifact)
        status = await self.session.status(include_history=True)
        self.assertEqual(status["status"], "completed")
        self.assertEqual(status["runs"][0]["id"], first["run"])

    async def test_start_duplicate_key_reuse_and_active_run_rejection(self):
        first = await self.start(key="start")
        duplicate = await self.start(key="start")
        self.assertEqual(first["run"], duplicate["run"])
        self.assertTrue(duplicate["duplicate"])
        with self.assertRaisesRegex(ValueError, "不同请求"):
            await self.call("control", "start", task="different", key="start")
        with self.assertRaisesRegex(ValueError, "进行中的讨论"):
            await self.start()
        self.assertEqual(len((await self.session.read())["errors"]), 2)
        self.assertEqual((await self.session.status())["status"], "discussing")

    async def test_concurrent_speakers_advance_once_and_duplicate_receipts_survive_advance(self):
        await self.start()
        await self.round(1)
        result = await self.call("member", "speak", text="member", round=1, key="1:member")
        self.assertEqual(result["accepted_round"], 1)
        self.assertEqual(result["round"], 2)
        self.assertEqual(len((await self.session.read())["speeches"]), 3)
        with self.assertRaisesRegex(ValueError, "不同发言"):
            await self.call("member", "speak", text="changed", round=1, key="1:member")
        await self.settle()
        rounds = [item for item in self.backend.signals.records.values() if item["signal"]["kind"] == "discussion.round"]
        self.assertEqual(len(rounds), 2)

    async def test_roles_and_old_round_window(self):
        await self.start(rounds=3)
        with self.assertRaisesRegex(ValueError, "active"):
            await self.call("outsider", "speak", text="invalid")
        with self.assertRaisesRegex(ValueError, "Leader"):
            await self.call("member", "decide", decision="invalid")
        await self.session.advance()
        await self.session.advance()
        with self.assertRaisesRegex(ValueError, "已过期"):
            await self.call("member", "speak", text="expired", round=1)
        with self.assertRaisesRegex(ValueError, "不是当前轮"):
            await self.call("member", "speak", text="future", round=4)
        accepted = await self.call("member", "speak", text="late", round=2)
        self.assertEqual(accepted["accepted_round"], 2)
        self.assertEqual((await self.session.status())["round"], 3)

    async def test_recorder_and_draft_requirements(self):
        await self.decision()
        with self.assertRaisesRegex(ValueError, "Recorder"):
            await self.call("member", "draft", section="x", text="x")
        with self.assertRaisesRegex(ValueError, "任何章节"):
            await self.call("recorder", "finish")
        await self.call("recorder", "draft", section="x", text="x", key="draft")
        await self.call("recorder", "draft", section="x", text="x", key="draft")
        with self.assertRaisesRegex(ValueError, "不同草稿"):
            await self.call("recorder", "draft", section="x", text="changed", key="draft")
        self.assertEqual((await self.session.status())["status"], "drafting")

    async def test_leave_is_idempotent_member_cannot_expel_others_and_control_can(self):
        await self.start()
        with self.assertRaisesRegex(ValueError, "本人退出"):
            await self.call("member", "leave", member="leader")
        first = await self.call("member", "leave", reason="done")
        second = await self.call("member", "leave", reason="done")
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(len((await self.session.read())["events"]), 1)
        await self.call("control", "leave", member="leader")
        await self.call("control", "leave", member="recorder")
        self.assertEqual((await self.session.status())["status"], "stopped")

    async def test_seat_discovery_uses_channel_strength_and_retains_failure_details(self):
        self.group.links.remove(list(self.group.links)[2])
        with self.assertRaisesRegex(ValueError, "至少 1 名 member"):
            await self.start()
        self.group.links.add(Link("member", "wrong"))
        with self.assertRaisesRegex(ValueError, "至少 1 名 member"):
            await self.start()
        self.group.links.add(Link("member", "members", threshold=3))
        with self.assertRaisesRegex(ValueError, "至少 1 名 member"):
            await self.start()
        self.group.links.add(Link("member", "members"))
        self.people["member"].modules.get("discussion.seat").config["role"] = "bad"
        with self.assertRaisesRegex(ValueError, "部分席位无法读取"):
            await self.start()

    async def test_signal_failure_marks_run_failed_after_state_commit(self):
        def fail(node, **parameters):
            raise OSError("emit fixture failed")
        self.session.emit = fail
        with self.assertRaisesRegex(OSError, "emit fixture failed"):
            await self.start()
        view = await self.session.status(include_history=True)
        self.assertEqual(view["status"], "failed")
        self.assertEqual(view["runs"][0]["status"], "failed")
        self.assertIn("emit fixture failed", view["errors"][-1]["message"])

    async def test_journal_reopen_keeps_run_receipts_seats_and_tools(self):
        await self.start(key="start")
        await self.call("member", "speak", text="member", round=1, key="speech")
        await self.settle()
        before = deepcopy(self.session.state)
        names = [tool.name for tool in self.session.tools]
        self.backend.save()
        self.backend.close()
        self.backend = Backend(self.temp.name, saver=self.saver)
        self.group = self.backend.network.get("group")
        self.session = self.group.modules.get(SESSION)
        self.assertEqual(self.session.state, before)
        self.assertEqual([tool.name for tool in self.session.tools], names)
        await self.call("member", "speak", text="member", round=1, key="speech")
        self.assertEqual(len((await self.session.read())["speeches"]), 1)

    async def test_detached_stage_signals_use_publisher_identity_and_do_not_hold_group_transaction(self):
        received = []
        self.group.links.add(Link("leader", "discussion.round"))
        async def receive(context):
            received.append((requester_id.get(), context.signal.origin))
            await self.call("leader", "speak", text="leader", round=1)
        self.backend.signals.bind("leader", receive, access_strength=2)
        await self.start()
        await self.settle()
        self.assertEqual(received, [("leader", "group")])
        self.assertIsNone(requester_id.get())
        self.assertEqual(len((await self.session.read())["speeches"]), 1)
        self.assertTrue(all(item["status"] == "completed" for item in self.backend.signals.records.values()))

    async def test_foreign_transaction_cannot_write_failure_or_run_state(self):
        await self.start()
        await self.settle()
        before = deepcopy(self.session.state)
        async with self.transaction(["leader"]):
            with self.assertRaises(PermissionError):
                await self.call("outsider", "speak", text="invalid")
        self.assertEqual(self.session.state, before)
