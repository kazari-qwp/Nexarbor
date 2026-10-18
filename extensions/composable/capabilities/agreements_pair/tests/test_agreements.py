import asyncio
import unittest
from pathlib import Path

from datanet.studio.testing import ModuleHarness
from jsonschema.exceptions import ValidationError


CHANNELS = ["agreements", "records", "movement", "info", "runtime.template", "tools"]


class AgreementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        self.h.add_node("house")
        self.h.add_node("office")
        self.h.mount(
            "office",
            module="place.info",
            config={"location": None, "description": "协议兑现处"},
            access={"strength": 0, "channels": ["movement", "info"]},
        )
        self.h.add_node("clock")
        self.clock = self.h.mount(
            "clock",
            module="clock.counter",
            config={"initial_tick": 0},
            access={"strength": 0, "channels": ["info", "tick"]},
        )
        self.h.add_node("hall")
        self.h.connect("hall", "clock", channels=["info"])
        self.h.connect("hall", "office", channels=["runtime.template"])

        self.agents = {}
        self.records = {}
        self.places = {}
        for node_id in ("a", "b", "c", "d"):
            self.h.add_node(node_id, agent=True)
            records_config = {"initial": {"ap": 10, "age": 18, "home": "house"}}
            if node_id == "b":
                records_config["minimum"] = {"ap": 0}
            self.records[node_id] = self.h.mount(
                node_id,
                module="records.store",
                config=records_config,
                access={"strength": 0, "channels": ["records"]},
            )
            self.places[node_id] = self.h.mount(
                node_id,
                module="place.info",
                config={"location": "office", "description": node_id},
                access={"strength": 0, "channels": ["movement", "info"]},
            )
            if node_id != "d":
                self.h.connect(
                    node_id, "hall", channels=CHANNELS
                )
                self.h.connect(
                    "hall", node_id, channels=CHANNELS
                )
        self.h.add_node("n1")
        self.h.connect("n1", "hall", channels=CHANNELS)
        self.hall = None

    def rules(self):
        return [
            {
                "id": "marriage",
                "title": "婚姻登记",
                "cost": 1,
                "require_values": {"age": 18},
                "pair_field": "spouse",
                "forbid_existing_pair": True,
                "set_values": {"married": True},
                "delay_ticks": 0,
            },
            {
                "id": "family_plan",
                "title": "共同家庭计划",
                "cost": 1,
                "require_values": {"age": 18},
                "set_values": {"planning": True},
                "delay_ticks": 10,
            },
            {
                "id": "delayed",
                "title": "延后协议",
                "cost": 1,
                "set_values": {"delayed_done": True},
                "delay_ticks": 5,
            },
        ]

    def mount_hall(self, **overrides):
        config = {
            "clock": "clock",
            "address": None,
            "delivery_address": None,
            "sources": [],
            "rules": self.rules(),
        }
        config.update(overrides)
        self.hall = self.h.mount(
            "hall",
            config=config,
            access={"strength": 3, "channels": CHANNELS},
        )
        return self.hall

    async def agree(self, actor, partner, rule, key):
        if self.hall is None:
            self.mount_hall()
        return await self.h.call(
            "hall",
            "agree",
            {"partner": partner, "rule": rule, "key": key},
            actor=actor,
            channels=["agreements"],
        )

    async def fulfill(self, actor, agreement_id, name=None, node="hall"):
        if self.hall is None:
            self.mount_hall()
        parameters = {"id": agreement_id}
        if name is not None:
            parameters["name"] = name
        return await self.h.call(
            node,
            "fulfill",
            parameters,
            actor=actor,
            channels=["agreements"],
        )

    async def values(self, node):
        result = await self.h.call(
            node,
            "read",
            {},
            module="records.store",
            channels=["records"],
        )
        self.assertEqual(result["status"], "ok", result)
        return result["data"]["values"]

    async def set_records(self, node, parameters):
        result = await self.h.call(
            node,
            "apply",
            parameters,
            module="records.store",
            channels=["records"],
        )
        self.assertEqual(result["status"], "ok", result)

    async def set_location(self, node, location):
        self.places[node].state["location"] = location

    async def test_same_tick_two_approvals_complete(self):
        first = await self.agree("a", "b", "marriage", "k-a")
        self.assertEqual(first["status"], "ok", first)
        self.assertEqual(first["data"]["status"], "open")
        second = await self.agree("b", "a", "marriage", "k-b")
        self.assertEqual(second["status"], "ok", second)
        self.assertEqual(second["data"]["status"], "completed")
        a_values = await self.values("a")
        b_values = await self.values("b")
        self.assertEqual(a_values["spouse"], "b")
        self.assertEqual(b_values["spouse"], "a")
        self.assertEqual(a_values["ap"], 9)
        self.assertEqual(b_values["ap"], 9)
        self.assertTrue(a_values["married"])

    async def test_single_approval_does_not_complete(self):
        result = await self.agree("a", "b", "marriage", "k-a")
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["status"], "open")
        self.assertIsNone((await self.values("a")).get("spouse"))
        self.assertIsNone((await self.values("b")).get("spouse"))
        self.assertEqual((await self.values("a"))["ap"], 9)
        self.assertEqual((await self.values("b"))["ap"], 10)

    async def test_old_tick_approval_not_reused(self):
        first = await self.agree("a", "b", "marriage", "k-a")
        agreement_id = first["data"]["id"]
        self.clock.state["tick"] = 1
        second = await self.agree("b", "a", "marriage", "k-b")
        self.assertEqual(second["status"], "ok", second)
        self.assertEqual(second["data"]["status"], "open")
        self.assertEqual(second["data"]["id"], agreement_id)
        approvals = second["data"]["approvals"]
        self.assertEqual([item["participant"] for item in approvals], ["b"])
        third = await self.agree("a", "b", "marriage", "k-a2")
        self.assertEqual(third["status"], "ok", third)
        self.assertEqual(third["data"]["status"], "completed")
        self.assertEqual((await self.values("a"))["ap"], 8)
        self.assertEqual((await self.values("b"))["ap"], 9)

    async def test_prerequisite_age_and_existing_spouse_rejected(self):
        await self.set_records("b", {"set": {"age": 17}})
        result = await self.agree("a", "b", "marriage", "age-key")
        self.assertEqual(result["status"], "error")
        self.assertIn("前提", result["error"])
        self.assertEqual((await self.values("a"))["ap"], 10)
        await self.set_records("b", {"set": {"age": 18}})
        await self.set_records(
            "a", {"references": [{"key": "spouse", "node_id": "c"}]}
        )
        result = await self.agree("a", "b", "marriage", "spouse-key")
        self.assertEqual(result["status"], "error")
        self.assertIn("关系", result["error"])
        self.assertEqual((await self.values("a"))["ap"], 10)

    async def test_insufficient_action_points_changes_nothing(self):
        await self.set_records("a", {"set": {"ap": 0}})
        result = await self.agree("a", "b", "marriage", "poor-key")
        self.assertEqual(result["status"], "error")
        self.assertIn("行动点", result["error"])
        self.assertFalse(self.hall.state.get("agreements"))
        self.assertFalse(self.hall.state.get("agree_receipts"))
        self.assertEqual((await self.values("a"))["ap"], 0)

    async def test_non_agent_and_disconnected_partner_rejected(self):
        self.mount_hall()
        normal = await self.h.call(
            "hall",
            "agree",
            {"partner": "b", "rule": "marriage", "key": "node-key"},
            actor="n1",
            channels=["agreements"],
        )
        self.assertEqual(normal["status"], "error", normal)
        self.assertIn("真实 Agent", normal["error"])
        missing = await self.agree("a", "d", "marriage", "missing-key")
        self.assertEqual(missing["status"], "error", missing)
        self.assertIn("不可达", missing["error"])
        self.assertEqual((await self.values("a"))["ap"], 10)

    async def test_concurrency_and_idempotency(self):
        requests = [
            ("a", "b", "marriage", "same-tick-a"),
            ("b", "a", "marriage", "same-tick-b"),
        ]
        results = await asyncio.gather(
            *[self.agree(*request) for request in requests]
        )
        for request, result in zip(requests, results):
            if result["status"] == "error" and "dependency cycle" in result["error"]:
                # 宿主明确要求锁依赖冲突时重试整个操作；重试键保持不变。
                result = await self.agree(*request)
            self.assertEqual(result["status"], "ok", result)
        self.assertEqual((await self.values("a"))["ap"], 9)
        self.assertEqual((await self.values("b"))["ap"], 9)
        agreements = self.hall.state["agreements"]
        self.assertEqual(len(agreements), 1)
        self.assertEqual(agreements[0]["status"], "completed")

        repeat = await self.agree("a", "b", "marriage", "same-tick-a")
        self.assertEqual(repeat["status"], "ok", repeat)
        self.assertTrue(repeat["data"]["duplicate"])
        self.assertEqual((await self.values("a"))["ap"], 9)
        conflict = await self.agree("a", "c", "marriage", "same-tick-a")
        self.assertEqual(conflict["status"], "error")
        self.assertIn("幂等键", conflict["error"])

    async def test_last_record_failure_rolls_back_whole_approval(self):
        self.mount_hall(
            rules=[
                {
                    "id": "risky",
                    "title": "末尾失败测试",
                    "cost": 1,
                    "set_values": {"ap": -5},
                    "delay_ticks": 0,
                }
            ]
        )
        first = await self.agree("a", "b", "risky", "risk-a")
        self.assertEqual(first["status"], "ok", first)
        self.assertEqual((await self.values("a"))["ap"], 9)
        second = await self.agree("b", "a", "risky", "risk-b")
        self.assertEqual(second["status"], "error", second)
        self.assertEqual((await self.values("a"))["ap"], 9)
        self.assertEqual((await self.values("b"))["ap"], 10)
        agreement = self.hall.state["agreements"][0]
        self.assertEqual(agreement["status"], "open")
        self.assertEqual([item["participant"] for item in agreement["approvals"]], ["a"])

    async def test_delay_cannot_be_fulfilled_early(self):
        first = await self.agree("a", "b", "family_plan", "plan-a")
        second = await self.agree("b", "a", "family_plan", "plan-b")
        self.assertEqual(second["status"], "ok", second)
        agreement_id = second["data"]["id"]
        self.assertEqual(second["data"]["status"], "pending")
        early = await self.fulfill("a", agreement_id)
        self.assertEqual(early["status"], "error", early)
        self.assertIn("尚未到", early["error"])
        self.clock.state["tick"] = 10
        done = await self.fulfill("a", agreement_id)
        self.assertEqual(done["status"], "ok", done)
        self.assertEqual(done["data"]["status"], "completed")
        self.assertTrue((await self.values("a"))["planning"])

    async def test_delivery_address_required(self):
        self.mount_hall(
            address="office",
            delivery_address="office",
            rules=[
                {
                    "id": "handover",
                    "title": "当面兑现",
                    "cost": 0,
                    "set_values": {"handover": True},
                    "delay_ticks": 3,
                }
            ],
        )
        await self.agree("a", "b", "handover", "h-a")
        second = await self.agree("b", "a", "handover", "h-b")
        agreement_id = second["data"]["id"]
        self.clock.state["tick"] = 3
        await self.set_location("a", "house")
        wrong = await self.fulfill("a", agreement_id)
        self.assertEqual(wrong["status"], "error", wrong)
        self.assertIn("兑现地点", wrong["error"])
        await self.set_location("a", "office")
        done = await self.fulfill("a", agreement_id)
        self.assertEqual(done["status"], "ok", done)
        self.assertTrue((await self.values("a"))["handover"])

    async def _install_template_port(self, behaviour, gate=False):
        self.template_calls = []
        self.port_entered = asyncio.Event()
        self.port_release = asyncio.Event()

        async def execute(actor, name, arguments):
            self.template_calls.append(
                {"actor": actor, "name": name, "arguments": arguments}
            )
            if gate:
                self.port_entered.set()
                await self.port_release.wait()
            return await behaviour(actor, name, arguments)

        self.h.register_tools(
            "templates",
            [
                {
                    "name": "instantiate",
                    "description": "测试模板端口",
                    "parameters": {"type": "object", "additionalProperties": True},
                }
            ],
            execute,
        )
        self.h.network.nodes["office"].offered_tools = [
            {
                "ref": "templates:instantiate",
                "channels": ["runtime.template"],
            }
        ]

    async def test_template_fulfill_and_retry_no_duplicate(self):
        created = []

        async def behaviour(actor, name, arguments):
            child = arguments["arguments"]
            created.append((child["name"], tuple(child["parents"]), child["home"]))
            return {"node_ids": ["child1"]}

        await self._install_template_port(behaviour, gate=True)
        self.mount_hall(
            delivery_address="office",
            rules=[
                {
                    "id": "birth",
                    "title": "共同家庭计划",
                    "cost": 1,
                    "require_values": {"age": 18},
                    "equal_fields": ["home"],
                    "set_values": {"parent": True},
                    "delay_ticks": 0,
                    "template": "family_member",
                }
            ],
        )
        await self.agree("a", "b", "birth", "b-a")
        second = await self.agree("b", "a", "birth", "b-b")
        agreement_id = second["data"]["id"]
        pending = asyncio.create_task(self.fulfill("a", agreement_id, name="宝宝"))
        await asyncio.wait_for(self.port_entered.wait(), timeout=2)
        probe = await asyncio.wait_for(
            self.h.call(
                "hall", "inspect", {}, actor="a", channels=["agreements"]
            ),
            timeout=2,
        )
        self.assertEqual(probe["status"], "ok", probe)
        self.port_release.set()
        done = await pending
        self.assertEqual(done["status"], "ok", done)
        self.assertEqual(done["data"]["status"], "completed")
        self.assertEqual(created, [("宝宝", ("a", "b"), "house")])
        payload = self.template_calls[0]["arguments"]
        self.assertEqual(payload["template"], "family_member")
        self.assertEqual(
            set(payload["arguments"]), {"name", "parents", "home"}
        )
        self.assertEqual(done["data"]["returned_node_ids"], [{"node_id": "child1"}])
        self.assertEqual((await self.values("a"))["child"], "child1")
        self.assertEqual((await self.values("b"))["child"], "child1")
        repeat = await self.fulfill("a", agreement_id, name="宝宝")
        self.assertEqual(repeat["status"], "ok", repeat)
        self.assertTrue(repeat["data"]["duplicate"])
        self.assertEqual(len(created), 1)
        self.assertEqual(len(self.template_calls), 1)

    async def test_template_failure_retry_same_key(self):
        attempts = {"count": 0}

        async def behaviour(actor, name, arguments):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("临时失败")
            return {"node_ids": ["child2"]}

        await self._install_template_port(behaviour)
        self.mount_hall(
            delivery_address="office",
            rules=[
                {
                    "id": "birth",
                    "title": "共同家庭计划",
                    "cost": 1,
                    "equal_fields": ["home"],
                    "delay_ticks": 0,
                    "template": "family_member",
                }
            ],
        )
        await self.agree("a", "b", "birth", "f-a")
        second = await self.agree("b", "a", "birth", "f-b")
        agreement_id = second["data"]["id"]
        failed = await self.fulfill("a", agreement_id, name="宝宝")
        self.assertEqual(failed["status"], "error", failed)
        self.assertEqual(self.hall.state["agreements"][0]["status"], "pending")
        done = await self.fulfill("a", agreement_id, name="宝宝")
        self.assertEqual(done["status"], "ok", done)
        self.assertEqual(done["data"]["status"], "completed")
        self.assertEqual(len(self.template_calls), 2)
        self.assertEqual(
            self.template_calls[0]["arguments"], self.template_calls[1]["arguments"]
        )
        self.assertEqual((await self.values("a"))["child"], "child2")

    async def test_sources_forward_requester_identity(self):
        self.h.add_node("source")
        self.source = self.h.mount(
            "source",
            config={
                "clock": "clock",
                "address": None,
                "delivery_address": None,
                "sources": [],
                "rules": [
                    {
                        "id": "delayed",
                        "title": "延后协议",
                        "cost": 0,
                        "set_values": {"source_done": True},
                        "delay_ticks": 2,
                    }
                ],
            },
            access={"strength": 3, "channels": CHANNELS},
        )
        for node_id in ("a", "b"):
            self.h.connect("source", node_id, channels=CHANNELS)
            self.h.connect(node_id, "source", channels=CHANNELS)
        self.h.connect("source", "clock", channels=["info"])
        self.h.connect("hall", "source", channels=["agreements"])
        self.mount_hall(
            sources=["source"],
            rules=[
                {
                    "id": "delayed",
                    "title": "延后协议",
                    "cost": 0,
                    "set_values": {"source_done": True},
                    "delay_ticks": 2,
                }
            ],
        )
        first = await self.h.call(
            "source",
            "agree",
            {"partner": "b", "rule": "delayed", "key": "s-a"},
            actor="a",
            channels=["agreements"],
        )
        second = await self.h.call(
            "source",
            "agree",
            {"partner": "a", "rule": "delayed", "key": "s-b"},
            actor="b",
            channels=["agreements"],
        )
        self.assertEqual(first["status"], "ok", first)
        self.assertEqual(second["status"], "ok", second)
        agreement_id = second["data"]["id"]
        self.clock.state["tick"] = 2
        forwarded = await self.fulfill("a", agreement_id, node="hall")
        self.assertEqual(forwarded["status"], "ok", forwarded)
        self.assertTrue(forwarded["data"]["forwarded"])
        agreement = self.source.state["agreements"][0]
        self.assertEqual(agreement["status"], "completed")
        self.assertTrue((await self.values("a"))["source_done"])

    async def test_framework_schema_rejects_bad_types(self):
        self.mount_hall()
        with self.assertRaises(ValidationError):
            await self.h.call(
                "hall",
                "agree",
                {"partner": "b", "rule": "marriage", "key": 123},
                actor="a",
                channels=["agreements"],
            )


if __name__ == "__main__":
    unittest.main()
