"""讨论应用与小镇不同的活动指令及消息记账频道。"""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.requester import as_requester
from app.runtime.signal_work import current_work
from domain.agent import AgentNode
from domain.core import Link, Network, Node, NodeInfo
from projects.discussion_collaboration.modules.agents_activity import AgentsActivityModule
from projects.discussion_collaboration.modules.messages_box import MessagesBoxModule
from projects.discussion_collaboration.modules.records_store import RecordsStoreModule

ROOT = Path(__file__).resolve().parents[1]


class DiscussionModulePolicyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix=".discussion-policies-", dir=ROOT / "build")
        self.addCleanup(self.temp.cleanup)
        self.actor = AgentNode(NodeInfo("actor", "Actor"))
        self.group = Node(NodeInfo("group", "Group"))
        self.group.links.add(Link("actor", "chat"))
        self.saver = NetworkSaver()
        self.saver.tables.module_types.update({
            "records.store":lambda record:RecordsStoreModule(),
            "messages.box":lambda record:MessagesBoxModule(self.transaction),
            "agents.activity":lambda record:AgentsActivityModule(self.agent_run),
        })
        self.account = RecordsStoreModule({"initial":{"ap":3}, "minimum":{"ap":0}})
        self.box = MessagesBoxModule(self.transaction, {"send_cost":1, "read_policy":"reachable"}, channels=["chat", "records"], strength=2)
        self.actor.install(self.account)
        self.group.install(self.box)
        self.backend = Backend(self.temp.name, network=Network([self.actor, self.group]), saver=self.saver)
        self.addCleanup(lambda:self.backend.close())
        self.calls = []

    def transaction(self, nodes, **options):
        return self.backend.node_locks.transaction(nodes, **options)

    async def agent_run(self, actor, message):
        self.calls.append(message)
        await self.account.apply(deltas={"ap":-1})
        if len(self.calls) == 1:await self.activity.notify("one")
        return {"status":"completed"}

    async def test_metadata_channel_does_not_grant_accounting_channel_and_no_partial_delivery(self):
        with as_requester("actor"):
            with self.assertRaises(KeyError):await self.box.send("hello", key="one")
        self.assertEqual(self.box.state, {})
        self.assertEqual((await self.account.read())["values"]["ap"], 3)
        self.group.links.add(Link("actor", "records"))
        with as_requester("actor"):
            first = await self.box.send("hello", key="one")
            second = await self.box.send("hello", key="one")
        self.assertEqual(first["ap"], 2)
        self.assertTrue(second["duplicate"])
        self.assertEqual(len((await self.box.read())["messages"]), 1)

    async def test_account_failure_rolls_back_records_and_mailbox(self):
        self.group.links.add(Link("actor", "records"))
        before = deepcopy(self.account.state)
        original = self.account.apply
        async def fail(**parameters):
            await original(**parameters)
            raise OSError("after debit fixture")
        with as_requester("actor"), patch.object(self.account, "apply", side_effect=fail):
            with self.assertRaises(OSError):await self.box.send("hello", key="one")
        self.assertEqual(self.account.state, before)
        self.assertEqual(self.box.state, {})

    async def test_pending_message_uses_discussion_follow_up_instruction_and_remaining_budget(self):
        self.activity = AgentsActivityModule(self.agent_run, {"enabled":True, "budget":3, "prompt":"collaborate", "max_reactions":1})
        self.actor.install(self.activity)
        class Work:signal_id = "one"
        token = current_work.set(Work())
        try:await self.activity.activate("one")
        finally:current_work.reset(token)
        self.assertEqual(self.calls, ["collaborate", "你收到新便条。按当前剩余行动点处理需要回应的内容；不要重复已完成的行动，自然结束。"])
        self.assertEqual((await self.account.read())["values"]["ap"], 1)
        self.assertEqual(self.activity.state["completed_total"], 1)
