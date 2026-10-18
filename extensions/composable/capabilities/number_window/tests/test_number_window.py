import asyncio
import unittest
from pathlib import Path

from jsonschema.exceptions import ValidationError

from datanet.studio.testing import ModuleHarness


class NumberWindowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        self.h.add_node("a", agent=True)
        self.h.add_node("b")
        self.instance = self.h.mount(
            "a",
            config={"window_size": 3},
            access={"strength": 2, "channels": ["measurement"]},
        )
        self.h.mount(
            "b",
            config={"window_size": 3},
            access={"strength": 2, "channels": ["measurement"]},
        )

    async def asyncTearDown(self):
        await self.h.close()

    async def push(self, value, key=None, node="a"):
        parameters = {"value": value}
        if key is not None:
            parameters["key"] = key
        return await self.h.call(
            node, "push", parameters, channels=["measurement"], strength=2
        )

    async def test_push_and_read_round_trip(self):
        for value in (1, 2, 3):
            result = await self.push(value)
            self.assertEqual(result["status"], "ok", result)

        self.assertEqual(result["data"]["count"], 3)
        self.assertEqual(result["data"]["min"], 1)
        self.assertEqual(result["data"]["max"], 3)
        self.assertEqual(result["data"]["mean"], 2.0)
        self.assertEqual(result["data"]["window_size"], 3)
        self.assertFalse(result["data"]["duplicate"])

        read = await self.h.call("a", "read", {}, channels=["measurement"])
        self.assertEqual(read["status"], "ok", read)
        self.assertEqual(
            read["data"],
            {
                "count": 3,
                "min": 1,
                "max": 3,
                "mean": 2.0,
                "window_size": 3,
                "values": [1, 2, 3],
            },
        )

        read_without_parameters = await self.h.call(
            "a", "read", None, channels=["measurement"]
        )
        self.assertEqual(read_without_parameters["status"], "ok")
        self.assertEqual(read_without_parameters["data"]["values"], [1, 2, 3])

    async def test_window_rolls_and_keeps_only_recent_values(self):
        for value in (1, 2, 3, 10):
            result = await self.push(value)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["count"], 3)
        self.assertEqual(result["data"]["min"], 2)
        self.assertEqual(result["data"]["max"], 10)
        self.assertEqual(result["data"]["mean"], 5.0)
        self.assertEqual(result["data"]["window_size"], 3)

        read = await self.h.call("a", "read", {}, channels=["measurement"])
        self.assertEqual(read["data"]["values"], [2, 3, 10])
        self.assertLessEqual(len(read["data"]["values"]), 3)

    async def test_empty_window_is_explicit(self):
        read = await self.h.call("a", "read", {}, channels=["measurement"])
        self.assertEqual(read["status"], "ok", read)
        self.assertEqual(
            read["data"],
            {
                "count": 0,
                "min": None,
                "max": None,
                "mean": None,
                "window_size": 3,
                "values": [],
            },
        )

    async def test_invalid_parameters_are_rejected(self):
        for parameters in (
            {},
            {"value": "1"},
            {"value": True},
            {"value": 1, "unknown": 2},
            {"value": 1, "key": ""},
        ):
            with self.assertRaises(ValidationError):
                await self.h.call(
                    "a", "push", parameters, channels=["measurement"]
                )

        read_with_extra = {"unexpected": 1}
        with self.assertRaises(ValidationError):
            await self.h.call(
                "a", "read", read_with_extra, channels=["measurement"]
            )

    async def test_non_finite_values_are_rejected_before_execution(self):
        # 框架的冻结 JSON 层会先拒绝 NaN/Infinity；实现内部仍保留有限数值检查。
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                await self.push(value)

        read = await self.h.call("a", "read", {}, channels=["measurement"])
        self.assertEqual(read["data"]["count"], 0)

    async def test_same_key_and_value_is_idempotent(self):
        first = await self.push(7, key="样本-001")
        second = await self.push(7, key="样本-001")
        self.assertEqual(first["status"], "ok", first)
        self.assertEqual(second["status"], "ok", second)
        self.assertFalse(first["data"]["duplicate"])
        self.assertTrue(second["data"]["duplicate"])
        self.assertEqual(second["data"]["count"], 1)

        conflict = await self.push(8, key="样本-001")
        self.assertEqual(conflict["status"], "error")
        self.assertIn("不同数值", conflict["error"])

        read = await self.h.call("a", "read", {}, channels=["measurement"])
        self.assertEqual(read["data"]["values"], [7])

    async def test_concurrent_same_key_appends_once(self):
        results = await asyncio.gather(
            *[self.push(4.5, key="并发样本") for _ in range(6)]
        )
        for result in results:
            self.assertEqual(result["status"], "ok", result)
            self.assertEqual(result["data"]["count"], 1)
        self.assertEqual(
            sum(1 for result in results if not result["data"]["duplicate"]), 1
        )

        read = await self.h.call("a", "read", {}, channels=["measurement"])
        self.assertEqual(read["data"]["values"], [4.5])

    async def test_instances_are_isolated(self):
        await self.push(11, key="仅-a")
        read_b = await self.h.call("b", "read", {}, channels=["measurement"])
        self.assertEqual(read_b["status"], "ok", read_b)
        self.assertEqual(read_b["data"]["count"], 0)

    async def test_wrong_channel_is_rejected(self):
        with self.assertRaises(PermissionError):
            await self.h.call("a", "push", {"value": 1}, channels=["demo"])

        with self.assertRaises(PermissionError):
            await self.h.call("a", "read", {}, channels=["demo"])

    async def test_custom_window_size(self):
        self.h.add_node("c")
        self.h.mount(
            "c",
            config={"window_size": 2},
            access={"strength": 2, "channels": ["measurement"]},
        )
        for value in (1, 2, 3):
            result = await self.h.call(
                "c", "push", {"value": value}, channels=["measurement"]
            )
            self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["window_size"], 2)
        self.assertEqual(result["data"]["count"], 2)
        self.assertEqual(result["data"]["mean"], 2.5)

        read = await self.h.call("c", "read", {}, channels=["measurement"])
        self.assertEqual(read["data"]["values"], [2, 3])

    async def test_local_state_is_bounded(self):
        for index in range(250):
            result = await self.push(index, key=f"k-{index}")
            self.assertEqual(result["status"], "ok", result)

        state = self.instance.state
        self.assertLessEqual(len(state["window"]), 3)
        self.assertLessEqual(len(state["receipts"]), 200)

    async def test_agent_tools_are_available_and_route_to_operations(self):
        entries = await self.h.tools.visit(
            "a", "a", strength=2, channels=["measurement"]
        )
        by_id = {entry["tool_id"]: entry for entry in entries}
        self.assertIn("push", by_id)
        self.assertIn("read", by_id)

        pushed = await self.h.tools.invoke(
            "a",
            by_id["push"],
            {"value": 6, "key": "工具样本"},
            strength=2,
            channels=["measurement"],
        )
        self.assertEqual(pushed["count"], 1)
        self.assertEqual(pushed["mean"], 6.0)

        read = await self.h.tools.invoke(
            "a",
            by_id["read"],
            {},
            strength=2,
            channels=["measurement"],
        )
        self.assertEqual(read["values"], [6])


if __name__ == "__main__":
    unittest.main()
