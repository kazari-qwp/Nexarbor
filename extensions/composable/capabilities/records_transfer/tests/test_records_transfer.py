import asyncio
import unittest
from pathlib import Path

from datanet.studio.testing import ModuleHarness

CHANNELS = ["self", "social", "records", "movement"]
EDGE_CHANNELS = ["social", "records", "movement"]


class RecordsTransferTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        self.h.add_node("a", agent=True, name="甲")
        self.h.add_node("b", agent=True, name="乙")
        self.h.add_node("c", agent=True, name="丙")
        self.h.add_node("d", name="普通节点")
        self.h.add_node("e", agent=True, name="丁")

        self._mount_agent("a", {"gold": 10, "ap": 5}, "广场")
        self._mount_agent("b", {"gold": 0, "ap": 5}, "广场")
        self._mount_agent("c", {"gold": 10, "ap": 5}, "广场")
        self.h.mount(
            "d",
            module="place.info",
            config={"location": "广场", "description": "广场"},
            access={"strength": 1, "channels": ["movement"]},
        )
        self.h.mount(
            "e",
            module="records.store",
            config={"initial": {"gold": 0, "ap": 5}},
            access={"strength": 1, "channels": ["records"]},
        )
        self.h.mount(
            "e",
            module="place.info",
            config={"location": "森林", "description": "森林"},
            access={"strength": 1, "channels": ["movement"]},
        )

        self.h.connect("a", "b", channels=EDGE_CHANNELS, threshold=1)
        self.h.connect("b", "a", channels=EDGE_CHANNELS, threshold=1)
        self.h.connect("c", "b", channels=EDGE_CHANNELS, threshold=1)
        self.h.connect("a", "d", channels=EDGE_CHANNELS, threshold=1)
        self.h.connect("a", "e", channels=EDGE_CHANNELS, threshold=1)

    async def asyncTearDown(self):
        await self.h.close()

    def _mount_agent(self, node_id, records, location):
        self.h.mount(
            node_id,
            module="records.store",
            config={"initial": records},
            access={"strength": 1, "channels": ["records"]},
        )
        self.h.mount(
            node_id,
            module="place.info",
            config={"location": location, "description": location},
            access={"strength": 1, "channels": ["movement"]},
        )
        self.h.mount(
            node_id,
            module="records.transfer",
            config={"cost": 1, "same_location": True},
            access={"strength": 3, "channels": CHANNELS},
        )

    async def _give(self, node, recipient, resource, quantity, key=None, actor=None):
        parameters = {
            "recipient": recipient,
            "resource": resource,
            "quantity": quantity,
        }
        if key is not None:
            parameters["key"] = key
        return await self.h.call(
            node, "give", parameters, actor=actor, channels=["self"], strength=2
        )

    async def _records(self, node):
        result = await self.h.call(
            node, "read", {}, module="records.store", channels=["records"], strength=2
        )
        self.assertEqual(result["status"], "ok", result)
        return result["data"]["values"]

    async def test_two_real_agents_give_and_conserve(self):
        result = await self._give("a", "b", "gold", 3)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(
            result["data"],
            {
                "from": "a",
                "to": "b",
                "resource": "gold",
                "quantity": 3,
                "ap": 4,
                "duplicate": False,
            },
        )

        a_values = await self._records("a")
        b_values = await self._records("b")
        self.assertEqual(a_values["gold"], 7)
        self.assertEqual(b_values["gold"], 3)
        self.assertEqual(a_values["ap"], 4)
        self.assertEqual(b_values["ap"], 5)
        self.assertEqual(a_values["gold"] + b_values["gold"], 10)

    async def test_give_ap_merges_same_field(self):
        result = await self._give("a", "b", "ap", 3)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["ap"], 1)

        a_values = await self._records("a")
        b_values = await self._records("b")
        self.assertEqual(a_values["ap"], 1)
        self.assertEqual(b_values["ap"], 8)
        self.assertEqual(a_values["gold"], 10)

    async def test_rejects_non_owner_and_ordinary_recipient(self):
        self.h.connect("b", "a", channels=["self"], threshold=1)
        non_owner = await self._give("a", "b", "gold", 1, actor="b")
        self.assertEqual(non_owner["status"], "error", non_owner)
        self.assertIn("本人", non_owner["error"])

        ordinary = await self._give("a", "d", "gold", 1)
        self.assertEqual(ordinary["status"], "error", ordinary)
        self.assertIn("真实 Agent", ordinary["error"])

        self.assertEqual((await self._records("a"))["gold"], 10)
        self.assertEqual((await self._records("b"))["gold"], 0)

    async def test_rejects_different_location_and_unreachable(self):
        different = await self._give("a", "e", "gold", 2)
        self.assertEqual(different["status"], "error", different)
        self.assertIn("同一地点", different["error"])
        self.assertEqual((await self._records("a"))["gold"], 10)
        self.assertEqual((await self._records("e"))["gold"], 0)

        self.h.disconnect("a", "b")
        unreachable = await self._give("a", "b", "gold", 2)
        self.assertEqual(unreachable["status"], "error", unreachable)
        self.assertIn("不可达", unreachable["error"])

    async def test_insufficient_resource_and_ap_leave_no_change(self):
        await self.h.call(
            "a",
            "apply",
            {"set": {"gold": 2, "ap": 0}},
            module="records.store",
            channels=["records"],
            strength=2,
        )

        poor_resource = await self._give("a", "b", "gold", 3)
        self.assertEqual(poor_resource["status"], "error", poor_resource)
        self.assertIn("资源不足", poor_resource["error"])

        poor_ap = await self._give("a", "b", "gold", 1)
        self.assertEqual(poor_ap["status"], "error", poor_ap)
        self.assertIn("行动点不足", poor_ap["error"])

        self.assertEqual((await self._records("a"))["gold"], 2)
        self.assertEqual((await self._records("a"))["ap"], 0)
        self.assertEqual((await self._records("b"))["gold"], 0)

    async def test_concurrent_requests_cannot_overdraw(self):
        first, second = await asyncio.gather(
            self._give("a", "b", "gold", 8),
            self._give("a", "b", "gold", 8),
        )
        statuses = sorted([first["status"], second["status"]])
        self.assertEqual(statuses, ["error", "ok"], (first, second))

        a_values = await self._records("a")
        b_values = await self._records("b")
        self.assertEqual(a_values["gold"], 2)
        self.assertEqual(b_values["gold"], 8)
        self.assertGreaterEqual(a_values["gold"], 0)

    async def test_failure_at_recipient_rolls_back_both_nodes(self):
        await self.h.call(
            "b",
            "apply",
            {"set": {"gold": "很多"}},
            module="records.store",
            channels=["records"],
            strength=2,
        )

        failed = await self._give("a", "b", "gold", 2)
        self.assertEqual(failed["status"], "error", failed)

        a_values = await self._records("a")
        b_values = await self._records("b")
        self.assertEqual(a_values["gold"], 10)
        self.assertEqual(a_values["ap"], 5)
        self.assertEqual(b_values["gold"], "很多")

    async def test_same_key_across_instances_and_retry(self):
        first = await self._give("a", "b", "gold", 2, key="协作-1")
        second = await self._give("c", "b", "gold", 3, key="协作-1")
        self.assertEqual(first["status"], "ok", first)
        self.assertEqual(second["status"], "ok", second)
        self.assertFalse(first["data"]["duplicate"])
        self.assertFalse(second["data"]["duplicate"])

        a_values = await self._records("a")
        c_values = await self._records("c")
        b_values = await self._records("b")
        self.assertEqual(a_values["gold"], 8)
        self.assertEqual(c_values["gold"], 7)
        self.assertEqual(b_values["gold"], 5)

        retried = await self._give("a", "b", "gold", 2, key="协作-1")
        self.assertEqual(retried["status"], "ok", retried)
        self.assertTrue(retried["data"]["duplicate"])
        self.assertEqual(retried["data"]["ap"], 4)
        self.assertEqual((await self._records("a"))["gold"], 8)
        self.assertEqual((await self._records("b"))["gold"], 5)

        changed = await self._give("a", "b", "gold", 4, key="协作-1")
        self.assertEqual(changed["status"], "error", changed)
        self.assertIn("不同参数", changed["error"])
        self.assertEqual((await self._records("a"))["gold"], 8)
        self.assertEqual((await self._records("b"))["gold"], 5)

    async def test_each_agent_only_discovers_own_give_and_cannot_give_for_other(self):
        a_entries = await self.h.tools.visit("a", "a", strength=1, channels=["self"])
        b_entries = await self.h.tools.visit("b", "b", strength=1, channels=["self"])
        a_gives = [entry for entry in a_entries if entry.get("tool_id") == "give"]
        b_gives = [entry for entry in b_entries if entry.get("tool_id") == "give"]
        self.assertEqual(len(a_gives), 1, a_entries)
        self.assertEqual(len(b_gives), 1, b_entries)

        # 常见网络没有 self 出边，因此不能经 self 频道看到另一位 Agent 的赠送工具。
        a_sees_b = await self.h.tools.visit("a", "b", strength=1, channels=["self"])
        b_sees_a = await self.h.tools.visit("b", "a", strength=1, channels=["self"])
        self.assertEqual([entry for entry in a_sees_b if entry.get("tool_id") == "give"], [])
        self.assertEqual([entry for entry in b_sees_a if entry.get("tool_id") == "give"], [])

        from_a = await self.h.tools.invoke(
            "a",
            a_gives[0],
            {"recipient": "b", "resource": "gold", "quantity": 2},
            strength=1,
            channels=["self"],
        )
        self.assertEqual(from_a["from"], "a")
        self.assertEqual(from_a["to"], "b")
        self.assertFalse(from_a["duplicate"])

        from_b = await self.h.tools.invoke(
            "b",
            b_gives[0],
            {"recipient": "a", "resource": "ap", "quantity": 1},
            strength=1,
            channels=["self"],
        )
        self.assertEqual(from_b["from"], "b")
        self.assertEqual(from_b["to"], "a")
        self.assertFalse(from_b["duplicate"])

        a_values = await self._records("a")
        b_values = await self._records("b")
        self.assertEqual(a_values["gold"], 8)
        self.assertEqual(b_values["gold"], 2)
        self.assertEqual(a_values["ap"], 5)
        self.assertEqual(b_values["ap"], 3)

        # 即使显式铺出 self 边，让另一位 Agent 拿到工具入口并转调，也必须被本人校验拒绝。
        self.h.connect("b", "a", channels=["self"], threshold=1)
        before_a = await self._records("a")
        before_b = await self._records("b")
        with self.assertRaises(Exception) as caught:
            await self.h.tools.invoke(
                "b",
                a_gives[0],
                {"recipient": "b", "resource": "gold", "quantity": 1},
                strength=1,
                channels=["self"],
            )
        self.assertIn("本人", str(caught.exception))
        self.assertEqual((await self._records("a"))["gold"], before_a["gold"])
        self.assertEqual((await self._records("b"))["gold"], before_b["gold"])


if __name__ == "__main__":
    unittest.main()
