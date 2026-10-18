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

    async def test_eligible_field_rejects_when_neither_participant_eligible(self):
        self.mount_hall(
            rules=[
                {
                    "id": "carry",
                    "title": "共同孕育",
                    "cost": 1,
                    "delay_ticks": 5,
                    "eligible_field": "can_carry",
                    "participant_effects": [
                        {
                            "when": {"can_carry": True},
                            "on_start": {"pregnant": True},
                            "on_finish": {"pregnant": False},
                        }
                    ],
                    "set_values": {"is_parent": True},
                }
            ]
        )
        result = await self.agree("a", "b", "carry", "carry-a")
        self.assertEqual(result["status"], "error", result)
        self.assertIn("资格", result["error"])
        self.assertEqual((await self.values("a"))["ap"], 10)
        self.assertEqual(len(self.hall.state.get("agreements") or []), 0)

    async def test_only_eligible_participant_receives_on_start(self):
        await self.set_records("b", {"set": {"can_carry": True}})
        self.mount_hall(
            rules=[
                {
                    "id": "carry",
                    "title": "共同孕育",
                    "cost": 1,
                    "delay_ticks": 5,
                    "eligible_field": "can_carry",
                    "participant_effects": [
                        {
                            "when": {"can_carry": True},
                            "on_start": {"pregnant": True},
                            "on_finish": {"pregnant": False},
                        }
                    ],
                    "set_values": {"is_parent": True},
                }
            ]
        )
        first = await self.agree("a", "b", "carry", "only-a")
        self.assertEqual(first["status"], "ok", first)
        self.assertIsNone((await self.values("a")).get("pregnant"))
        self.assertIsNone((await self.values("b")).get("pregnant"))
        second = await self.agree("b", "a", "carry", "only-b")
        self.assertEqual(second["status"], "ok", second)
        self.assertEqual(second["data"]["status"], "pending")
        a_values = await self.values("a")
        b_values = await self.values("b")
        self.assertIsNone(a_values.get("pregnant"))
        self.assertTrue(b_values.get("pregnant"))
        self.assertEqual(a_values["ap"], 9)
        self.assertEqual(b_values["ap"], 9)

    async def test_fulfill_require_values_uses_only_requester_records(self):
        self.mount_hall(
            rules=[
                {
                    "id": "handover",
                    "title": "条件交接",
                    "cost": 0,
                    "delay_ticks": 2,
                    "fulfill_require_values": {"ready": True},
                    "set_values": {"handed": True},
                }
            ]
        )
        await self.agree("a", "b", "handover", "req-a")
        second = await self.agree("b", "a", "handover", "req-b")
        agreement_id = second["data"]["id"]
        self.clock.state["tick"] = 2
        await self.set_records("b", {"set": {"ready": True}})
        rejected = await self.fulfill("a", agreement_id)
        self.assertEqual(rejected["status"], "error", rejected)
        self.assertIn("兑现前提", rejected["error"])
        self.assertIsNone((await self.values("a")).get("handed"))
        self.assertEqual(self.hall.state["agreements"][0]["status"], "pending")
        await self.set_records("a", {"set": {"ready": True}})
        done = await self.fulfill("a", agreement_id)
        self.assertEqual(done["status"], "ok", done)
        self.assertEqual(done["data"]["status"], "completed")
        self.assertTrue((await self.values("a"))["handed"])

    async def test_delayed_on_finish_runs_only_at_actual_completion(self):
        await self.set_records("b", {"set": {"can_carry": True}})
        self.mount_hall(
            rules=[
                {
                    "id": "carry",
                    "title": "共同孕育",
                    "cost": 1,
                    "delay_ticks": 5,
                    "eligible_field": "can_carry",
                    "participant_effects": [
                        {
                            "when": {"can_carry": True},
                            "on_start": {"pregnant": True},
                            "on_finish": {"pregnant": False},
                        }
                    ],
                    "set_values": {"is_parent": True},
                }
            ]
        )
        await self.agree("a", "b", "carry", "finish-a")
        second = await self.agree("b", "a", "carry", "finish-b")
        agreement_id = second["data"]["id"]
        self.assertTrue((await self.values("b")).get("pregnant"))
        early = await self.fulfill("a", agreement_id)
        self.assertEqual(early["status"], "error", early)
        self.assertIn("尚未到", early["error"])
        self.assertTrue((await self.values("b")).get("pregnant"))
        self.assertIsNone((await self.values("a")).get("is_parent"))
        self.clock.state["tick"] = 5
        done = await self.fulfill("a", agreement_id)
        self.assertEqual(done["status"], "ok", done)
        self.assertEqual(done["data"]["status"], "completed")
        a_values = await self.values("a")
        b_values = await self.values("b")
        self.assertFalse(b_values.get("pregnant"))
        self.assertTrue(a_values.get("is_parent"))
        self.assertTrue(b_values.get("is_parent"))

    async def test_start_effect_failure_rolls_back_second_approval_and_fee(self):
        await self.set_records("b", {"set": {"can_carry": True}})
        self.mount_hall(
            rules=[
                {
                    "id": "carry",
                    "title": "共同孕育",
                    "cost": 1,
                    "delay_ticks": 5,
                    "eligible_field": "can_carry",
                    "participant_effects": [
                        {
                            "when": {},
                            "on_start": {"start_marker": True},
                            "on_finish": {},
                        },
                        {
                            "when": {"can_carry": True},
                            "on_start": {"ap": -5},
                            "on_finish": {"done": True},
                        },
                    ],
                }
            ]
        )
        first = await self.agree("a", "b", "carry", "rollback-a")
        self.assertEqual(first["status"], "ok", first)
        second = await self.agree("b", "a", "carry", "rollback-b")
        self.assertEqual(second["status"], "error", second)
        a_values = await self.values("a")
        b_values = await self.values("b")
        self.assertEqual(a_values["ap"], 9)
        self.assertEqual(b_values["ap"], 10)
        self.assertIsNone(a_values.get("start_marker"))
        self.assertIsNone(b_values.get("start_marker"))
        agreement = self.hall.state["agreements"][0]
        self.assertEqual(agreement["status"], "open")
        self.assertEqual(
            [item["participant"] for item in agreement["approvals"]], ["a"]
        )

    async def test_on_start_and_on_finish_not_repeated_on_retries(self):
        self.mount_hall(
            rules=[
                {
                    "id": "effect_once",
                    "title": "效果幂等",
                    "cost": 1,
                    "delay_ticks": 5,
                    "participant_effects": [
                        {
                            "when": {},
                            "on_start": {"started": True},
                            "on_finish": {"finished": True},
                        }
                    ],
                    "set_values": {"both_done": True},
                }
            ]
        )
        first = await self.agree("a", "b", "effect_once", "once-a")
        self.assertEqual(first["status"], "ok", first)
        self.assertIsNone((await self.values("a")).get("started"))
        second = await self.agree("b", "a", "effect_once", "once-b")
        agreement_id = second["data"]["id"]
        self.assertEqual(second["data"]["status"], "pending")
        self.assertTrue((await self.values("a")).get("started"))
        self.assertTrue((await self.values("b")).get("started"))
        repeat = await self.agree("a", "b", "effect_once", "once-a")
        self.assertEqual(repeat["status"], "ok", repeat)
        self.assertTrue(repeat["data"]["duplicate"])
        self.assertEqual((await self.values("a"))["ap"], 9)
        self.assertEqual((await self.values("b"))["ap"], 9)
        self.clock.state["tick"] = 5
        done = await self.fulfill("a", agreement_id)
        self.assertEqual(done["status"], "ok", done)
        self.assertEqual(done["data"]["status"], "completed")
        self.assertTrue((await self.values("a")).get("finished"))
        self.assertTrue((await self.values("b")).get("finished"))
        repeated = await self.fulfill("a", agreement_id)
        self.assertEqual(repeated["status"], "ok", repeated)
        self.assertTrue(repeated["data"]["duplicate"])
        self.assertEqual((await self.values("a"))["ap"], 9)
        self.assertEqual((await self.values("b"))["ap"], 9)

    async def _mount_birth_rule(self, fulfill_cost=0):
        self.mount_hall(
            delivery_address="office",
            rules=[
                {
                    "id": "birth",
                    "title": "共同家庭计划",
                    "cost": 1,
                    "fulfill_cost": fulfill_cost,
                    "equal_fields": ["home"],
                    "delay_ticks": 0,
                    "template": "family_member",
                }
            ],
        )
        await self.agree("a", "b", "birth", "dict-a")
        second = await self.agree("b", "a", "birth", "dict-b")
        self.assertEqual(second["status"], "ok", second)
        return second["data"]["id"]

    async def test_template_official_dict_response_creates_typed_child_references(self):
        async def behaviour(actor, name, arguments):
            return {
                "node_ids": {"child": "child-dict"},
                "duplicate": False,
                "created": 1,
            }

        await self._install_template_port(behaviour)
        agreement_id = await self._mount_birth_rule()
        done = await self.fulfill("a", agreement_id, name="宝宝")
        self.assertEqual(done["status"], "ok", done)
        self.assertEqual(done["data"]["status"], "completed")
        self.assertEqual(
            done["data"]["returned_node_ids"], [{"node_id": "child-dict"}]
        )
        self.assertEqual((await self.values("a"))["child"], "child-dict")
        self.assertEqual((await self.values("b"))["child"], "child-dict")
        for node_id in ("a", "b"):
            references = self.records[node_id].state.get("references") or []
            self.assertIn(
                {"key": "child", "node_id": "child-dict"}, references
            )

    async def test_template_failure_retry_charges_fulfill_cost_once(self):
        attempts = {"count": 0}

        async def behaviour(actor, name, arguments):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("临时失败")
            return {"node_ids": {"child": "child-cost"}, "duplicate": False}

        await self._install_template_port(behaviour)
        agreement_id = await self._mount_birth_rule(fulfill_cost=2)
        self.assertEqual((await self.values("a"))["ap"], 9)
        self.assertEqual((await self.values("b"))["ap"], 9)
        failed = await self.fulfill("a", agreement_id, name="宝宝")
        self.assertEqual(failed["status"], "error", failed)
        self.assertEqual((await self.values("a"))["ap"], 7)
        self.assertEqual((await self.values("b"))["ap"], 9)
        self.assertEqual(self.hall.state["agreements"][0]["status"], "pending")
        done = await self.fulfill("a", agreement_id, name="宝宝")
        self.assertEqual(done["status"], "ok", done)
        self.assertEqual(done["data"]["status"], "completed")
        self.assertEqual((await self.values("a"))["ap"], 7)
        self.assertEqual((await self.values("b"))["ap"], 9)
        self.assertEqual(len(self.template_calls), 2)
        repeat = await self.fulfill("a", agreement_id, name="宝宝")
        self.assertEqual(repeat["status"], "ok", repeat)
        self.assertTrue(repeat["data"]["duplicate"])
        self.assertEqual((await self.values("a"))["ap"], 7)

    async def test_template_empty_node_ids_cannot_complete(self):
        responses = [
            {"node_ids": {}, "duplicate": False},
            {"node_ids": {"child": "child-late"}, "duplicate": False},
        ]

        async def behaviour(actor, name, arguments):
            return responses.pop(0)

        await self._install_template_port(behaviour)
        agreement_id = await self._mount_birth_rule()
        failed = await self.fulfill("a", agreement_id, name="宝宝")
        self.assertEqual(failed["status"], "error", failed)
        self.assertIn("节点 ID", failed["error"])
        agreement = self.hall.state["agreements"][0]
        self.assertEqual(agreement["status"], "pending")
        self.assertEqual(agreement["returned_node_ids"], [])
        self.assertIsNone((await self.values("a")).get("child"))
        done = await self.fulfill("a", agreement_id, name="宝宝")
        self.assertEqual(done["status"], "ok", done)
        self.assertEqual(done["data"]["status"], "completed")
        self.assertEqual((await self.values("a"))["child"], "child-late")

    def mount_source(self, node_id, rules, **overrides):
        self.h.add_node(node_id)
        config = {
            "clock": "clock",
            "address": None,
            "delivery_address": None,
            "sources": [],
            "rules": rules,
        }
        config.update(overrides)
        source = self.h.mount(
            node_id,
            config=config,
            access={"strength": 3, "channels": CHANNELS},
        )
        for agent in ("a", "b"):
            self.h.connect(node_id, agent, channels=CHANNELS)
            self.h.connect(agent, node_id, channels=CHANNELS)
        self.h.connect(node_id, "clock", channels=["info"])
        self.h.connect("hall", node_id, channels=["agreements"])
        return source

    async def agree_on(self, node, actor, partner, rule, key):
        return await self.h.call(
            node,
            "agree",
            {"partner": partner, "rule": rule, "key": key},
            actor=actor,
            channels=["agreements"],
        )

    def source_rule(self, rule_id="shared", **overrides):
        rule = {
            "id": rule_id,
            "title": "来源共同计划",
            "cost": 0,
            "set_values": {"source_done": True},
            "delay_ticks": 2,
        }
        rule.update(overrides)
        return [rule]

    async def test_sources_inspect_merges_requester_visible_agreements_and_rules(self):
        source = self.mount_source("source1", self.source_rule())
        first = await self.agree_on("source1", "a", "b", "shared", "inspect-a")
        second = await self.agree_on("source1", "b", "a", "shared", "inspect-b")
        self.assertEqual(first["status"], "ok", first)
        self.assertEqual(second["status"], "ok", second)
        agreement_id = second["data"]["id"]

        self.mount_hall(sources=["source1"], rules=[])
        found = await self.h.call(
            "hall", "inspect", {}, actor="a", channels=["agreements"]
        )
        self.assertEqual(found["status"], "ok", found)
        matches = [
            item
            for item in found["data"]["agreements"]
            if item["id"] == agreement_id
        ]
        self.assertEqual(len(matches), 1, found)
        self.assertEqual(matches[0]["source"], "source1")
        self.assertIn(
            "shared", [item["id"] for item in found["data"]["rules"]]
        )

        hidden = await self.h.call(
            "hall", "inspect", {}, actor="c", channels=["agreements"]
        )
        self.assertEqual(hidden["status"], "ok", hidden)
        self.assertFalse(
            any(
                item["id"] == agreement_id
                for item in hidden["data"]["agreements"]
            ),
            hidden,
        )
        self.assertEqual(source.state["agreements"][0]["status"], "pending")

    async def test_sources_fulfill_routes_unique_match_and_missing_is_clear(self):
        source = self.mount_source("source1", self.source_rule())
        self.mount_source("source2", self.source_rule())
        first = await self.agree_on("source1", "a", "b", "shared", "route-a")
        second = await self.agree_on("source1", "b", "a", "shared", "route-b")
        self.assertEqual(first["status"], "ok", first)
        self.assertEqual(second["status"], "ok", second)
        agreement_id = second["data"]["id"]

        self.mount_hall(sources=["source1", "source2"], rules=[])
        self.clock.state["tick"] = 2
        forwarded = await self.fulfill("a", agreement_id, node="hall")
        self.assertEqual(forwarded["status"], "ok", forwarded)
        self.assertTrue(forwarded["data"]["forwarded"])
        self.assertEqual(forwarded["data"]["source"], "source1")
        self.assertEqual(
            source.state["agreements"][0]["status"], "completed"
        )
        self.assertTrue((await self.values("a"))["source_done"])

        missing = await self.fulfill("a", "agr-never-exists", node="hall")
        self.assertEqual(missing["status"], "error", missing)
        self.assertIn("没有来源找到该协议", missing["error"])
        self.assertEqual(len(source.state["agreements"]), 1)
        self.assertEqual(
            source.state["agreements"][0]["status"], "completed"
        )

    async def test_sources_fulfill_same_id_is_ambiguous_and_runs_no_source(self):
        first_source = self.mount_source("source1", self.source_rule())
        second_source = self.mount_source("source2", self.source_rule())
        for node in ("source1", "source2"):
            await self.agree_on(node, "a", "b", "shared", node + "-a")
            await self.agree_on(node, "b", "a", "shared", node + "-b")
        first_id = first_source.state["agreements"][0]["id"]
        second_id = second_source.state["agreements"][0]["id"]
        self.assertEqual(first_id, second_id)

        self.mount_hall(sources=["source1", "source2"], rules=[])
        self.clock.state["tick"] = 2
        result = await self.fulfill("a", first_id, node="hall")
        self.assertEqual(result["status"], "error", result)
        self.assertIn("歧义", result["error"])
        for source in (first_source, second_source):
            self.assertEqual(
                source.state["agreements"][0]["status"], "pending"
            )
        self.assertIsNone((await self.values("a")).get("source_done"))

    async def test_sources_fulfill_surfaces_downstream_business_failure(self):
        rules = self.source_rule(
            "guarded",
            set_values={"guarded_done": True},
            fulfill_require_values={"ready": True},
        )
        source = self.mount_source("source1", rules)
        await self.agree_on("source1", "a", "b", "guarded", "fail-a")
        second = await self.agree_on(
            "source1", "b", "a", "guarded", "fail-b"
        )
        agreement_id = second["data"]["id"]

        self.mount_hall(sources=["source1"], rules=[])
        self.clock.state["tick"] = 2
        failed = await self.fulfill("a", agreement_id, node="hall")
        self.assertEqual(failed["status"], "error", failed)
        self.assertIn("兑现前提", failed["error"])
        self.assertNotIn("forwarded", failed.get("data") or {})
        self.assertEqual(
            source.state["agreements"][0]["status"], "pending"
        )
        self.assertIsNone((await self.values("a")).get("guarded_done"))

        await self.set_records("a", {"set": {"ready": True}})
        done = await self.fulfill("a", agreement_id, node="hall")
        self.assertEqual(done["status"], "ok", done)
        self.assertEqual(done["data"]["source"], "source1")
        self.assertTrue((await self.values("a"))["guarded_done"])

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
