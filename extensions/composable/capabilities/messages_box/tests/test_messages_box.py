import asyncio
import unittest
from pathlib import Path

from datanet.studio.testing import ModuleHarness
from jsonschema.exceptions import ValidationError


class MessagesBoxTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        for node in ("box", "forum", "alice", "bob", "mallory", "island"):
            self.h.add_node(node, agent=node in {"alice", "bob", "island"})

        # 发送者到消息箱使用 chat 频道；消息箱回访发送者记录仓使用 records 频道。
        for target in ("box", "forum"):
            for sender in ("alice", "bob"):
                self.h.connect(sender, target, channels=["chat"], threshold=1)
                self.h.connect(
                    target,
                    sender,
                    channels=["chat", "records"],
                    threshold=1,
                )
        self.h.connect("mallory", "box", channels=["chat"], threshold=1)
        self.h.connect("box", "mallory", channels=["chat"], threshold=1)

    async def asyncTearDown(self):
        await self.h.close()

    def _mount_box(self, node="box", **overrides):
        config = {
            "read_policy": "self",
            "send_cost": 0,
            "max_messages": 200,
            "require_agent": True,
        }
        config.update(overrides)
        self.h.mount(
            node,
            config=config,
            access={"strength": 2, "channels": ["chat", "records"]},
        )

    def _mount_records(self, node, ap):
        self.h.mount(
            node,
            module="records.store",
            config={"initial": {"ap": ap}, "minimum": {"ap": 0}},
            access={"strength": 1, "channels": ["records"]},
        )

    def _prepare(self, box_config=None, ap=5, nodes=("alice", "bob")):
        self._mount_box(**(box_config or {}))
        for node in nodes:
            self._mount_records(node, ap)

    async def test_paid_preflight_leaves_inbox_untouched_until_transaction_starts(self):
        from copy import deepcopy
        self._prepare({'read_policy':'reachable','send_cost':1})
        instance=self.h.modules.instances[('box','messages.box')]
        before=deepcopy(instance.state);locks=self.h.network.node_locks;real=locks.transaction
        def reject(*args,**kwargs):raise RuntimeError('模拟申请事务失败')
        locks.transaction=reject
        try:
            result=await self.h.call('box','send',{'text':'不得提前入箱','key':'preflight'},actor='alice',channels=['chat'])
            self.assertEqual(result['status'],'error');self.assertEqual(instance.state,before)
        finally:locks.transaction=real
        read=await self.h.call('alice','read',{},module='records.store',channels=['records'])
        self.assertEqual(read['data']['values']['ap'],5)

    async def test_duplicate_paid_delivery_does_not_acquire_another_transaction(self):
        self._prepare({'read_policy':'reachable','send_cost':1})
        args={'text':'仅一次','key':'once'}
        first=await self.h.call('box','send',args,actor='alice',channels=['chat'])
        self.assertEqual(first['status'],'ok');self.assertFalse(first['data']['duplicate']);self.assertEqual(first['data']['ap'],4)
        locks=self.h.network.node_locks;real=locks.transaction
        def reject(*args,**kwargs):raise AssertionError('重复消息不应申请事务')
        locks.transaction=reject
        try:
            again=await self.h.call('box','send',args,actor='alice',channels=['chat'])
            self.assertEqual(again['status'],'ok');self.assertTrue(again['data']['duplicate'])
        finally:locks.transaction=real

    async def test_agent_send_and_read(self):
        self._prepare({"read_policy": "reachable"})
        sent = await self.h.call(
            "box",
            "send",
            {"text": "今晚在广场集合", "topic": "协作"},
            actor="alice",
            channels=["chat"],
        )
        self.assertEqual(sent["status"], "ok", sent)
        data = sent["data"]
        self.assertEqual(data["from"], "alice")
        self.assertEqual(data["to"], "box")
        self.assertEqual(data["topic"], "协作")
        self.assertFalse(data["duplicate"])
        self.assertIsNone(data["ap"])

        read = await self.h.call(
            "box",
            "read",
            {"limit": 10},
            actor="bob",
            channels=["chat"],
        )
        self.assertEqual(read["status"], "ok", read)
        self.assertEqual(len(read["data"]["messages"]), 1)
        self.assertEqual(read["data"]["messages"][0]["text"], "今晚在广场集合")

    async def test_private_box_rejects_remote_read_but_public_forum_allows(self):
        self._mount_box("box", read_policy="self")
        self._mount_box("forum", read_policy="reachable")
        self._mount_records("alice", 5)

        await self.h.call(
            "box", "send", {"text": "私信内容"}, actor="alice", channels=["chat"]
        )
        await self.h.call(
            "forum",
            "send",
            {"text": "公开公告", "topic": "公告"},
            actor="alice",
            channels=["chat"],
        )

        private = await self.h.call(
            "box", "read", {}, actor="alice", channels=["chat"]
        )
        self.assertEqual(private["status"], "error", private)
        self.assertIn("仅允许", private["error"])

        owner_read = await self.h.call(
            "box", "read", {}, actor="box", channels=["chat"]
        )
        self.assertEqual(owner_read["status"], "ok", owner_read)
        self.assertEqual(owner_read["data"]["messages"][0]["text"], "私信内容")

        public = await self.h.call(
            "forum", "read", {}, actor="bob", channels=["chat"]
        )
        self.assertEqual(public["status"], "ok", public)
        self.assertEqual(public["data"]["messages"][0]["text"], "公开公告")

    async def test_normal_node_cannot_send_or_forge_identity(self):
        self._prepare()
        denied = await self.h.call(
            "box", "send", {"text": "普通节点冒充"}, actor="mallory", channels=["chat"]
        )
        self.assertEqual(denied["status"], "error", denied)
        self.assertIn("Agent", denied["error"])

        with self.assertRaises(ValidationError):
            await self.h.call(
                "box",
                "send",
                {"text": "伪造字段", "from": "alice"},
                actor="alice",
                channels=["chat"],
            )

    async def test_path_and_channel_are_required(self):
        self._prepare()
        with self.assertRaises(PermissionError):
            await self.h.call(
                "box", "send", {"text": "不可达"}, actor="island", channels=["chat"]
            )
        with self.assertRaises(PermissionError):
            await self.h.call(
                "box", "send", {"text": "频道不对"}, actor="alice", channels=["records"]
            )

    async def test_schema_rejects_bad_types_and_bounds(self):
        self._prepare()
        with self.assertRaises(ValidationError):
            await self.h.call(
                "box", "send", {"text": ""}, actor="alice", channels=["chat"]
            )
        with self.assertRaises(ValidationError):
            await self.h.call(
                "box", "send", {"text": 123}, actor="alice", channels=["chat"]
            )
        with self.assertRaises(ValidationError):
            await self.h.call(
                "box", "read", {"limit": 0}, actor="box", channels=["chat"]
            )

    async def test_ap_shortage_does_not_write_message_or_charge(self):
        self._prepare({"send_cost": 2}, ap=1)
        charged = await self.h.call(
            "box", "send", {"text": "买不起的消息"}, actor="alice", channels=["chat"]
        )
        self.assertEqual(charged["status"], "error", charged)

        records = await self.h.call(
            "alice",
            "read",
            {},
            module="records.store",
            actor="alice",
            channels=["records"],
        )
        self.assertEqual(records["status"], "ok", records)
        self.assertEqual(records["data"]["values"]["ap"], 1)
        box = self.h.modules.get("box", "messages.box")
        self.assertEqual(box.state.get("messages", []), [])

    async def test_concurrent_sends_do_not_overspend_ap(self):
        self._prepare({"send_cost": 1}, ap=5)
        calls = [
            self.h.call(
                "box",
                "send",
                {"text": f"并发消息 {index}", "key": f"并发-{index}"},
                actor="alice",
                channels=["chat"],
            )
            for index in range(8)
        ]
        results = await asyncio.gather(*calls)
        successes = [item for item in results if item["status"] == "ok"]
        failures = [item for item in results if item["status"] == "error"]
        self.assertEqual(len(successes), 5, results)
        self.assertEqual(len(failures), 3, results)

        records = self.h.modules.get("alice", "records.store")
        self.assertEqual(records.state["values"]["ap"], 0)
        read = await self.h.call(
            "box", "read", {"limit": 200}, actor="box", channels=["chat"]
        )
        self.assertEqual(len(read["data"]["messages"]), 5, read)

    async def test_same_key_is_idempotent_and_conflict_is_rejected(self):
        self._prepare({"send_cost": 1}, ap=5)
        first = await self.h.call(
            "box",
            "send",
            {"text": "任务通知", "topic": "任务", "key": "任务-1"},
            actor="alice",
            channels=["chat"],
        )
        self.assertEqual(first["status"], "ok", first)
        self.assertFalse(first["data"]["duplicate"])

        second = await self.h.call(
            "box",
            "send",
            {"text": "任务通知", "topic": "任务", "key": "任务-1"},
            actor="alice",
            channels=["chat"],
        )
        self.assertEqual(second["status"], "ok", second)
        self.assertTrue(second["data"]["duplicate"])
        self.assertEqual(second["data"]["id"], first["data"]["id"])

        conflict = await self.h.call(
            "box",
            "send",
            {"text": "内容被改写", "topic": "任务", "key": "任务-1"},
            actor="alice",
            channels=["chat"],
        )
        self.assertEqual(conflict["status"], "error", conflict)

        records = self.h.modules.get("alice", "records.store")
        self.assertEqual(records.state["values"]["ap"], 4)
        box = self.h.modules.get("box", "messages.box")
        self.assertEqual(len(box.state["messages"]), 1)

    async def test_clear_is_only_allowed_for_owner(self):
        self._prepare()
        await self.h.call(
            "box", "send", {"text": "待清理"}, actor="alice", channels=["chat"]
        )
        denied = await self.h.call(
            "box", "clear", {}, actor="alice", channels=["chat"]
        )
        self.assertEqual(denied["status"], "error", denied)

        cleared = await self.h.call(
            "box", "clear", {}, actor="box", channels=["chat"]
        )
        self.assertEqual(cleared["status"], "ok", cleared)
        self.assertEqual(cleared["data"]["cleared"], 1)

        read = await self.h.call("box", "read", {}, actor="box", channels=["chat"])
        self.assertEqual(read["data"]["messages"], [])

    async def test_same_key_two_recipients_charge_twice_and_retries_are_free(self):
        self._mount_box("box", send_cost=1)
        self._mount_box("forum", send_cost=1)
        self._mount_records("alice", 5)

        first = await self.h.call(
            "box",
            "send",
            {"text": "同一请求发给第一位收件人", "key": "同一请求"},
            actor="alice",
            channels=["chat"],
        )
        self.assertEqual(first["status"], "ok", first)
        self.assertFalse(first["data"]["duplicate"])
        self.assertEqual(first["data"]["ap"], 4)

        second = await self.h.call(
            "forum",
            "send",
            {"text": "同一请求发给第二位收件人", "key": "同一请求"},
            actor="alice",
            channels=["chat"],
        )
        self.assertEqual(second["status"], "ok", second)
        self.assertFalse(second["data"]["duplicate"])
        self.assertEqual(second["data"]["ap"], 3)

        for target in ("box", "forum"):
            retry = await self.h.call(
                target,
                "send",
                {"text": f"同一请求发给{target}的重试", "key": "同一请求"},
                actor="alice",
                channels=["chat"],
            )
            self.assertEqual(retry["status"], "error", retry)
            self.assertIn("不同内容", retry["error"])

        retry_box = await self.h.call(
            "box",
            "send",
            {"text": "同一请求发给第一位收件人", "key": "同一请求"},
            actor="alice",
            channels=["chat"],
        )
        self.assertEqual(retry_box["status"], "ok", retry_box)
        self.assertTrue(retry_box["data"]["duplicate"])
        self.assertIsNone(retry_box["data"]["ap"])

        retry_forum = await self.h.call(
            "forum",
            "send",
            {"text": "同一请求发给第二位收件人", "key": "同一请求"},
            actor="alice",
            channels=["chat"],
        )
        self.assertEqual(retry_forum["status"], "ok", retry_forum)
        self.assertTrue(retry_forum["data"]["duplicate"])
        self.assertIsNone(retry_forum["data"]["ap"])

        box = self.h.modules.get("box", "messages.box")
        forum = self.h.modules.get("forum", "messages.box")
        self.assertEqual(len(box.state["messages"]), 1, box.state)
        self.assertEqual(len(forum.state["messages"]), 1, forum.state)
        self.assertEqual(box.state["messages"][0]["text"], "同一请求发给第一位收件人")
        self.assertEqual(forum.state["messages"][0]["text"], "同一请求发给第二位收件人")

        records = await self.h.call(
            "alice",
            "read",
            {},
            module="records.store",
            actor="alice",
            channels=["records"],
        )
        self.assertEqual(records["status"], "ok", records)
        self.assertEqual(records["data"]["values"]["ap"], 3)

    async def test_tail_failure_rolls_back_message_and_ap(self):
        self._prepare({"send_cost": 2}, ap=5)
        definition = self.h.modules.get("alice", "records.store").definition
        original_execute = definition.execute

        async def fail_after_apply(ctx, activation):
            result = await original_execute(ctx, activation)
            if activation.kind == "access" and activation.operation == "apply":
                raise RuntimeError("测试注入：末尾扣费后失败")
            return result

        definition.execute = fail_after_apply
        failed = await self.h.call(
            "box",
            "send",
            {"text": "应当在回滚后消失", "key": "回滚-1"},
            actor="alice",
            channels=["chat"],
        )
        self.assertEqual(failed["status"], "error", failed)
        self.assertIn("末尾扣费后失败", failed["error"])

        box_after = self.h.modules.get("box", "messages.box")
        self.assertEqual(box_after.state.get("messages", []), [])
        self.assertEqual(box_after.state.get("seen", []), [])

        records = await self.h.call(
            "alice",
            "read",
            {},
            module="records.store",
            actor="alice",
            channels=["records"],
        )
        self.assertEqual(records["status"], "ok", records)
        self.assertEqual(records["data"]["values"]["ap"], 5)
