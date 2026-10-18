import unittest
from pathlib import Path

from datanet.core.text_node import TextFileNode
from datanet.studio.testing import ModuleHarness


CHECKPOINT_PARAMETERS = {
    "type": "object",
    "properties": {"full": {"type": "boolean"}},
    "required": ["full"],
    "additionalProperties": False,
}


class ClockCounterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])

    async def asyncTearDown(self):
        await self.h.close()

    def mount_clock(self, node, **config):
        defaults = {
            "signal_channels": ["tick"],
            "labels": ["清晨", "上午", "下午", "傍晚", "夜晚"],
            "initial_tick": 0,
            "checkpoint_every": 0,
            "write_text": False,
        }
        defaults.update(config)
        return self.h.mount(
            node,
            config=defaults,
            access={
                "strength": 1,
                "channels": ["info", "tick", "runtime.checkpoint"],
            },
        )

    async def read_clock(self, node):
        result = await self.h.call(
            node, "read", {}, channels=["info", "tick"]
        )
        self.assertEqual(result["status"], "ok", result)
        return result["data"]

    def register_checkpoint(self):
        calls = []

        async def execute(actor, name, arguments):
            calls.append((actor, name, arguments))
            return {"ok": True, "full": arguments["full"]}

        self.h.register_tools(
            "runtime",
            [
                {
                    "name": "checkpoint",
                    "description": "测试用运行时存档",
                    "parameters": CHECKPOINT_PARAMETERS,
                }
            ],
            execute,
        )
        return calls

    async def test_initial_read_and_default_five_slots(self):
        self.h.add_node("root")
        self.h.add_node("clock")
        self.h.connect("root", "clock", channels=["tick"])
        self.mount_clock("clock")
        self.assertEqual(
            await self.read_clock("clock"),
            {"tick": 0, "day": 1, "slot": "清晨"},
        )

        expected = [
            (1, 1, "清晨"),
            (2, 1, "上午"),
            (3, 1, "下午"),
            (4, 1, "傍晚"),
            (5, 1, "夜晚"),
            (6, 2, "清晨"),
        ]
        for tick, day, slot in expected:
            await self.h.emit("root", ["tick"], strength=3)
            self.assertEqual(
                await self.read_clock("clock"),
                {"tick": tick, "day": day, "slot": slot},
            )

    async def test_initial_tick_is_configurable(self):
        self.h.add_node("root")
        self.h.add_node("clock")
        self.h.connect("root", "clock", channels=["tick"])
        self.mount_clock("clock", initial_tick=4)
        self.assertEqual(
            await self.read_clock("clock"),
            {"tick": 4, "day": 1, "slot": "傍晚"},
        )
        await self.h.emit("root", ["tick"], strength=3)
        self.assertEqual(
            await self.read_clock("clock"),
            {"tick": 5, "day": 1, "slot": "夜晚"},
        )

    async def test_same_signal_through_multiple_paths_counts_once(self):
        for node in ("root", "left", "right"):
            self.h.add_node(node)
        self.h.add_node("clock")
        self.h.connect("root", "left", channels=["tick"])
        self.h.connect("root", "right", channels=["tick"])
        self.h.connect("left", "clock", channels=["tick"])
        self.h.connect("right", "clock", channels=["tick"])
        self.mount_clock("clock")

        await self.h.emit("root", ["tick"], strength=3)

        self.assertEqual(
            await self.read_clock("clock"),
            {"tick": 1, "day": 1, "slot": "清晨"},
        )
        instance = self.h.modules.get("clock", "clock.counter")
        self.assertEqual(len(instance.state["seen"]), 1)

    async def test_two_instances_keep_independent_labels(self):
        self.h.add_node("root")
        self.h.add_node("town")
        self.h.add_node("camp")
        self.h.connect("root", "town", channels=["tick"])
        self.h.connect("root", "camp", channels=["tick"])
        self.mount_clock("town", labels=["黎明", "正午", "黄昏"])
        self.mount_clock("camp", labels=["一更", "二更"])

        await self.h.emit("root", ["tick"], strength=3)
        self.assertEqual(
            await self.read_clock("town"),
            {"tick": 1, "day": 1, "slot": "黎明"},
        )
        self.assertEqual(
            await self.read_clock("camp"),
            {"tick": 1, "day": 1, "slot": "一更"},
        )

        await self.h.emit("root", ["tick"], strength=3)
        self.assertEqual(
            await self.read_clock("town"),
            {"tick": 2, "day": 1, "slot": "正午"},
        )
        self.assertEqual(
            await self.read_clock("camp"),
            {"tick": 2, "day": 1, "slot": "二更"},
        )

    async def test_text_file_receives_chinese_time(self):
        self.h.add_node("root")
        text_node = TextFileNode(
            "clock_text",
            "时钟文本",
            None,
            self.h.folder / "clock.txt",
        )
        self.h.network.add_node(text_node)
        self.h.connect("root", "clock_text", channels=["tick"])
        self.mount_clock("clock_text", write_text=True)

        await self.h.emit("root", ["tick"], strength=3)
        result = text_node.read({"method": "key", "key": "content"})
        self.assertEqual(result.status, "ok", result)
        self.assertEqual(result.items[0]["content"], "第1天 清晨")

        await self.h.emit("root", ["tick"], strength=3)
        result = text_node.read({"method": "key", "key": "content"})
        self.assertEqual(result.items[0]["content"], "第1天 上午")

    async def test_checkpoint_every_five_calls_once_per_boundary(self):
        calls = self.register_checkpoint()
        self.h.add_node("root")
        self.h.add_node("clock")
        self.h.connect("root", "clock", channels=["tick"])
        self.mount_clock("clock", checkpoint_every=5)
        self.h.network.nodes["clock"].offered_tools = [
            {"ref": "runtime:checkpoint", "channels": ["runtime.checkpoint"]}
        ]

        for _ in range(5):
            outcome = await self.h.emit("root", ["tick"], strength=3)
        self.assertEqual(
            await self.read_clock("clock"),
            {"tick": 5, "day": 1, "slot": "夜晚"},
        )
        self.assertEqual(len(calls), 1, repr(outcome))
        self.assertEqual(calls[0][1:], ("checkpoint", {"full": True}))
        self.assertEqual(self.h.network.nodes["clock"].offered_tools, [
            {"ref": "runtime:checkpoint", "channels": ["runtime.checkpoint"]}
        ])

        await self.h.emit("root", ["tick"], strength=3)
        self.assertEqual(len(calls), 1)
        for _ in range(4):
            await self.h.emit("root", ["tick"], strength=3)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1:], ("checkpoint", {"full": True}))

    async def test_disabled_checkpoint_never_calls_runtime(self):
        calls = self.register_checkpoint()
        self.h.add_node("root")
        self.h.add_node("clock")
        self.h.connect("root", "clock", channels=["tick"])
        self.mount_clock("clock", checkpoint_every=0)
        self.h.network.nodes["clock"].offered_tools = [
            {"ref": "runtime:checkpoint", "channels": ["runtime.checkpoint"]}
        ]

        for _ in range(5):
            await self.h.emit("root", ["tick"], strength=3)

        self.assertEqual(len(calls), 0)
        self.assertEqual((await self.read_clock("clock"))["tick"], 5)

    async def test_checkpoint_failure_marks_signal_failed_and_stops_successor(self):
        calls = self.register_checkpoint()
        self.h.add_node("root")
        self.h.add_node("clock")
        self.h.add_node("after")
        self.h.connect("root", "clock", channels=["tick"])
        self.h.connect("clock", "after", channels=["tick"])
        self.mount_clock("clock", checkpoint_every=1)
        self.mount_clock("after", checkpoint_every=0)

        outcome = await self.h.emit("root", ["tick"], strength=3)

        self.assertEqual(outcome["status"], "failed", outcome)
        self.assertEqual(outcome["layers"], [["clock"]], outcome)
        self.assertEqual(len(outcome["deliveries"]), 1, outcome)
        self.assertEqual(outcome["deliveries"][0]["node_id"], "clock")
        self.assertEqual(outcome["deliveries"][0]["status"], "failed")
        self.assertEqual(calls, [])
        instance = self.h.modules.get("clock", "clock.counter")
        self.assertTrue(instance.state.get("pending_checkpoint"))
        self.assertEqual((await self.read_clock("clock"))["tick"], 1)
        self.assertEqual((await self.read_clock("after"))["tick"], 0)

    async def test_flush_retries_pending_checkpoint_exactly_once(self):
        calls = self.register_checkpoint()
        self.h.add_node("root")
        self.h.add_node("clock")
        self.h.connect("root", "clock", channels=["tick"])
        self.mount_clock("clock", checkpoint_every=1)

        outcome = await self.h.emit("root", ["tick"], strength=3)
        self.assertEqual(outcome["status"], "failed", outcome)
        instance = self.h.modules.get("clock", "clock.counter")
        self.assertTrue(instance.state.get("pending_checkpoint"))
        self.assertEqual((await self.read_clock("clock"))["tick"], 1)

        self.h.network.nodes["clock"].offered_tools = [
            {"ref": "runtime:checkpoint", "channels": ["runtime.checkpoint"]}
        ]
        result = await self.h.call(
            "clock", "flush", {}, channels=["runtime.checkpoint"]
        )
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"], {"checkpointed": True, "tick": 1})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1:], ("checkpoint", {"full": True}))
        self.assertFalse(instance.state.get("pending_checkpoint"))
        self.assertEqual((await self.read_clock("clock"))["tick"], 1)

        repeated = await self.h.call(
            "clock", "flush", {}, channels=["runtime.checkpoint"]
        )
        self.assertEqual(repeated["status"], "ok", repeated)
        self.assertEqual(repeated["data"], {"checkpointed": False, "tick": 1})
        self.assertEqual(len(calls), 1)
        self.assertFalse(instance.state.get("pending_checkpoint"))


if __name__ == "__main__":
    unittest.main()
