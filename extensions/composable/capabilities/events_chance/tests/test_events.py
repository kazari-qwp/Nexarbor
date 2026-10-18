import unittest
from pathlib import Path

from jsonschema.exceptions import ValidationError
from datanet.core.module_protocol import ComponentResult, ModuleDefinition
from datanet.studio.testing import ModuleHarness


async def outer_lock_execute(ctx, activation):
    if activation.kind != "access" or activation.operation != "nested":
        return ComponentResult(status="error", error="不支持的测试操作")
    try:
        async with ctx.network.lock_nodes(
            [ctx.node_id, ctx.requester_id], timeout=20
        ):
            result = await ctx.network.call(
                ctx.node_id, "events.chance", "sample", {}
            )
            if result["status"] != "ok":
                raise RuntimeError(result["error"])
    except Exception as error:
        return ComponentResult(status="error", error=str(error))
    return ComponentResult(data={"nested": True})


class EventsChanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        self.h.add_node("npc", agent=True)
        self.h.add_node("place")
        self.h.connect("npc", "place", channels=["events", "records"])
        self.h.connect("place", "npc", channels=["events", "records"])
        self.records = self.h.mount(
            "npc",
            module="records.store",
            config={"initial": {"金币": 10}},
            access={"strength": 2, "channels": ["records"]},
        )
        await self.h.call(
            "npc",
            "read",
            {},
            actor="npc",
            module="records.store",
            channels=["records"],
        )

    async def asyncTearDown(self):
        await self.h.close()

    def mount_events(self, events, state=None):
        return self.h.mount(
            "place",
            config={"events": events},
            state=state if state is not None else {"counts": {}},
            access={"strength": 2, "channels": ["events", "records"]},
        )

    async def sample(self, actor="npc", channels=None):
        return await self.h.call(
            "place",
            "sample",
            {},
            actor=actor,
            channels=channels or ["events"],
        )

    async def test_probability_zero_and_one(self):
        instance = self.mount_events(
            [
                {
                    "id": "never",
                    "text": "不会发生。",
                    "probability": 0,
                    "limit": None,
                    "rewards": {"金币": 99},
                },
                {
                    "id": "always",
                    "text": "一定会发生。",
                    "probability": 1,
                    "limit": None,
                    "rewards": {"金币": 2, "木材": 1},
                },
            ]
        )

        result = await self.sample()

        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["observations"], ["一定会发生。"])
        self.assertEqual(result["data"]["rewards"], {"金币": 2, "木材": 1})
        self.assertEqual(result["data"]["counts"], {"never": 0, "always": 1})
        self.assertEqual(instance.state["counts"], {"never": 0, "always": 1})
        self.assertEqual(self.records.state["values"]["金币"], 12)
        self.assertEqual(self.records.state["values"]["木材"], 1)

    async def test_limit_stops_successes(self):
        instance = self.mount_events(
            [
                {
                    "id": "once",
                    "text": "只发生一次。",
                    "probability": 1,
                    "limit": 1,
                    "rewards": {"金币": 5},
                }
            ]
        )

        first = await self.sample()
        second = await self.sample()

        self.assertEqual(first["status"], "ok", first)
        self.assertEqual(first["data"]["counts"], {"once": 1})
        self.assertEqual(second["status"], "ok", second)
        self.assertEqual(second["data"]["observations"], [])
        self.assertEqual(second["data"]["rewards"], {})
        self.assertEqual(second["data"]["counts"], {"once": 1})
        self.assertEqual(instance.state["counts"], {"once": 1})
        self.assertEqual(self.records.state["values"]["金币"], 15)

    async def test_duplicate_event_configuration_is_rejected(self):
        self.mount_events(
            [
                {
                    "id": "dup",
                    "text": "第一项。",
                    "probability": 1,
                    "limit": None,
                    "rewards": {"金币": 1},
                },
                {
                    "id": "dup",
                    "text": "第二项。",
                    "probability": 1,
                    "limit": None,
                    "rewards": {"金币": 1},
                },
            ]
        )

        result = await self.sample()

        self.assertEqual(result["status"], "error", result)
        self.assertIn("重复", result["error"])
        self.assertEqual(self.records.state["values"]["金币"], 10)

    async def test_reward_failure_rolls_back_counts_and_rewards(self):
        self.records.state["values"]["金币"] = "损坏的旧值"
        instance = self.mount_events(
            [
                {
                    "id": "reward",
                    "text": "奖励发放会失败。",
                    "probability": 1,
                    "limit": 1,
                    "rewards": {"金币": 3},
                }
            ]
        )

        result = await self.sample()

        self.assertEqual(result["status"], "error", result)
        self.assertIn("发放事件奖励失败", result["error"])
        self.assertEqual(instance.state["counts"].get("reward", 0), 0)
        self.assertEqual(self.records.state["values"]["金币"], "损坏的旧值")

    async def test_nested_outer_lock_is_reentrant(self):
        self.h.modules.factories["test.outer"] = ModuleDefinition(
            outer_lock_execute,
            operations=[
                {
                    "name": "nested",
                    "channels": ["events"],
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                    "result": {"type": "object"},
                }
            ],
        )
        instance = self.mount_events(
            [
                {
                    "id": "nested",
                    "text": "嵌套锁内仍然可用。",
                    "probability": 1,
                    "limit": None,
                    "rewards": {"金币": 1},
                }
            ]
        )
        self.h.mount(
            "place",
            module="test.outer",
            config={},
            state={},
            access={"strength": 2, "channels": ["events", "records"]},
        )

        result = await self.h.call(
            "place",
            "nested",
            {},
            actor="npc",
            module="test.outer",
            channels=["events"],
        )

        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"], {"nested": True})
        self.assertEqual(instance.state["counts"], {"nested": 1})
        self.assertEqual(self.records.state["values"]["金币"], 11)

    async def test_non_agent_requester_is_rejected(self):
        self.h.add_node("outsider")
        self.h.connect("outsider", "place", channels=["events", "records"])
        instance = self.mount_events(
            [
                {
                    "id": "blocked",
                    "text": "普通节点不能抽奖。",
                    "probability": 1,
                    "limit": None,
                    "rewards": {"金币": 1},
                }
            ]
        )

        result = await self.sample(actor="outsider")

        self.assertEqual(result["status"], "error", result)
        self.assertIn("Agent", result["error"])
        self.assertEqual(instance.state["counts"], {})

    async def test_wrong_channel_is_rejected(self):
        self.mount_events([])

        with self.assertRaises(PermissionError):
            await self.sample(channels=["records"])

    async def test_parameters_must_be_empty_object(self):
        self.mount_events([])

        with self.assertRaises(ValidationError):
            await self.h.call(
                "place",
                "sample",
                {"unexpected": True},
                actor="npc",
                channels=["events"],
            )


if __name__ == "__main__":
    unittest.main()
