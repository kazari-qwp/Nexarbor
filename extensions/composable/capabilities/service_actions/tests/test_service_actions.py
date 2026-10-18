import asyncio
import unittest
from pathlib import Path

from datanet.studio.testing import ModuleHarness
from jsonschema.exceptions import ValidationError


def gather_action(**extra):
    action = {
        "id": "gather",
        "title": "采集",
        "description": "从场所库存取得材料。",
        "actor_deltas": {"wood": 2},
        "local_deltas": {"wood": -2},
        "cost": 1,
    }
    action.update(extra)
    return action


def buy_action(**extra):
    action = {
        "id": "buy",
        "title": "购买",
        "description": "用金币换取场所库存。",
        "actor_deltas": {"wood": 1, "gold": -3},
        "local_deltas": {"wood": -1, "gold": 3},
        "cost": 1,
    }
    action.update(extra)
    return action


class ServiceActionsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])

    async def asyncTearDown(self):
        await self.h.close()

    def add_actor(self, node, initial, location="market", name=None):
        self.h.add_node(node, agent=True, name=name)
        self.h.mount(
            node,
            module="records.store",
            config={"initial": initial},
            access={"strength": 1, "channels": ["records"]},
        )
        self.h.mount(
            node,
            module="place.info",
            config={"location": location},
            access={"strength": 1, "channels": ["movement"]},
        )

    def add_service(self, config, inventory, address=None, node="shop", name="服务场所"):
        self.h.add_node(node, name=name)
        self.h.mount(
            node,
            config=config,
            access={"strength": 2, "channels": ["service", "records", "movement"]},
        )
        self.h.mount(
            node,
            module="records.store",
            config={"initial": inventory},
            access={"strength": 1, "channels": ["records"]},
        )
        self.h.mount(
            node,
            module="place.info",
            config={"description": "业务场所", "location": address},
            access={"strength": 1, "channels": ["movement"]},
        )

    def connect_actor(self, node, shop="shop"):
        self.h.connect(node, shop, channels=["service", "records", "movement"])
        self.h.connect(shop, node, channels=["service", "records", "movement"])

    async def call(self, actor, parameters, operation="perform", shop="shop"):
        return await self.h.call(
            shop,
            operation,
            parameters,
            actor=actor,
            strength=2,
            channels=["service"],
        )

    async def values(self, node):
        result = await self.h.call(
            node,
            "read",
            {},
            module="records.store",
            strength=1,
            channels=["records"],
        )
        self.assertEqual(result["status"], "ok", result)
        return result["data"]["values"]

    async def test_same_config_collect_and_trade(self):
        self.add_actor("alice", {"wood": 0, "gold": 10, "ap": 5})
        self.add_service(
            {"address": "market", "actions": [gather_action(), buy_action()]},
            {"wood": 10, "gold": 0},
            address="market",
        )
        self.connect_actor("alice")

        inspected = await self.call("alice", {}, operation="inspect")
        self.assertEqual(inspected["status"], "ok", inspected)
        self.assertEqual([a["id"] for a in inspected["data"]["actions"]], ["gather", "buy"])
        self.assertEqual(inspected["data"]["inventory"]["wood"], 10)

        gathered = await self.call("alice", {"action": "gather", "quantity": 2, "key": "g-1"})
        self.assertEqual(gathered["status"], "ok", gathered)
        self.assertFalse(gathered["data"]["duplicate"])
        self.assertEqual(gathered["data"]["actor"], "alice")
        self.assertEqual(gathered["data"]["values"]["wood"], 4)
        self.assertEqual((await self.values("alice"))["ap"], 4)
        self.assertEqual((await self.values("shop"))["wood"], 6)

        bought = await self.call("alice", {"action": "buy", "quantity": 1, "key": "b-1"})
        self.assertEqual(bought["status"], "ok", bought)
        alice = await self.values("alice")
        shop = await self.values("shop")
        self.assertEqual((alice["wood"], alice["gold"], alice["ap"]), (5, 7, 3))
        self.assertEqual((shop["wood"], shop["gold"]), (5, 3))

    async def test_action_point_cost_fixed_and_per_unit(self):
        self.add_actor("alice", {"energy": 0, "ap": 9})
        self.add_service(
            {
                "actions": [
                    gather_action(id="fixed", cost=2, per_unit_cost=False),
                    gather_action(
                        id="rest",
                        title="休息",
                        actor_deltas={"energy": 1},
                        local_deltas={},
                        cost=2,
                        per_unit_cost=True,
                    ),
                ]
            },
            {"wood": 10},
        )
        self.connect_actor("alice")

        fixed = await self.call("alice", {"action": "fixed", "quantity": 3})
        self.assertEqual(fixed["status"], "ok", fixed)
        self.assertEqual((await self.values("alice"))["ap"], 7)

        rested = await self.call("alice", {"action": "rest", "quantity": 3})
        self.assertEqual(rested["status"], "ok", rested)
        self.assertEqual((await self.values("alice"))["ap"], 1)
        self.assertEqual((await self.values("alice"))["energy"], 3)

        refused = await self.call("alice", {"action": "rest", "quantity": 1})
        self.assertEqual(refused["status"], "error", refused)
        self.assertIn("ap", refused["error"])
        self.assertEqual((await self.values("alice"))["ap"], 1)

    async def test_insufficient_inventory_and_funds_unchanged(self):
        self.add_actor("alice", {"wood": 0, "gold": 1, "ap": 5})
        self.add_service(
            {
                "actions": [gather_action(), buy_action()],
                "events": [
                    {"id": "bonus", "text": "测试奖励", "probability": 1, "limit": 5, "rewards": {"gold": 1}}
                ],
            },
            {"wood": 2, "gold": 0},
        )
        self.connect_actor("alice")

        before_actor = await self.values("alice")
        before_shop = await self.values("shop")

        no_stock = await self.call("alice", {"action": "gather", "quantity": 2, "key": "stock-fail"})
        self.assertEqual(no_stock["status"], "error", no_stock)
        self.assertIn("wood", no_stock["error"])
        self.assertEqual(await self.values("alice"), before_actor)
        self.assertEqual(await self.values("shop"), before_shop)

        no_money = await self.call("alice", {"action": "buy", "quantity": 1, "key": "money-fail"})
        self.assertEqual(no_money["status"], "error", no_money)
        self.assertIn("gold", no_money["error"])
        self.assertEqual(await self.values("alice"), before_actor)
        self.assertEqual(await self.values("shop"), before_shop)

    async def test_wrong_location_rejected(self):
        self.add_actor("alice", {"wood": 0, "ap": 5}, location="home")
        self.add_service(
            {"address": "market", "actions": [gather_action()]},
            {"wood": 5},
            address="market",
        )
        self.connect_actor("alice")

        rejected = await self.call("alice", {"action": "gather", "key": "wrong-place"})
        self.assertEqual(rejected["status"], "error", rejected)
        self.assertIn("业务地址", rejected["error"])
        self.assertEqual((await self.values("alice"))["wood"], 0)
        self.assertEqual((await self.values("shop"))["wood"], 5)

    async def test_required_home_rejected(self):
        self.add_actor("alice", {"wood": 0, "ap": 5, "home": "home-b"})
        self.add_service(
            {"actions": [gather_action(required_home="home-a")]},
            {"wood": 5},
        )
        self.connect_actor("alice")

        rejected = await self.call("alice", {"action": "gather", "key": "wrong-home"})
        self.assertEqual(rejected["status"], "error", rejected)
        self.assertIn("住所", rejected["error"])
        self.assertEqual((await self.values("alice"))["wood"], 0)
        self.assertEqual((await self.values("shop"))["wood"], 5)

    async def test_plain_node_requester_rejected(self):
        self.h.add_node("kiosk", name="普通节点")
        self.h.mount(
            "kiosk",
            module="records.store",
            config={"initial": {"wood": 0, "ap": 5}},
            access={"strength": 1, "channels": ["records"]},
        )
        self.add_service({"actions": [gather_action()]}, {"wood": 5})
        self.connect_actor("kiosk")

        rejected = await self.call("kiosk", {"action": "gather", "key": "plain-node"})
        self.assertEqual(rejected["status"], "error", rejected)
        self.assertIn("Agent", rejected["error"])
        self.assertEqual((await self.values("kiosk"))["wood"], 0)
        self.assertEqual((await self.values("shop"))["wood"], 5)

    async def test_unreachable_requester_rejected(self):
        self.add_actor("alice", {"wood": 0, "ap": 5})
        self.add_service({"actions": [gather_action()]}, {"wood": 5})
        # 只允许请求者到服务，服务无法回查请求者元数据。
        self.h.connect("alice", "shop", channels=["service", "records", "movement"])

        rejected = await self.call("alice", {"action": "gather", "key": "unreachable"})
        self.assertEqual(rejected["status"], "error", rejected)
        self.assertIn("无法核验请求者 Agent 身份", rejected["error"])
        self.assertEqual((await self.values("alice"))["wood"], 0)
        self.assertEqual((await self.values("shop"))["wood"], 5)

    async def test_two_agents_compete_without_overselling(self):
        self.add_actor("alice", {"wood": 0, "ap": 5})
        self.add_actor("bob", {"wood": 0, "ap": 5})
        self.add_service(
            {"actions": [gather_action(actor_deltas={"wood": 1}, local_deltas={"wood": -1})]},
            {"wood": 1},
        )
        self.connect_actor("alice")
        self.connect_actor("bob")

        first, second = await asyncio.gather(
            self.call("alice", {"action": "gather", "key": "race-a"}),
            self.call("bob", {"action": "gather", "key": "race-b"}),
        )
        statuses = sorted([first["status"], second["status"]])
        self.assertEqual(statuses, ["error", "ok"], (first, second))
        shop = await self.values("shop")
        self.assertEqual(shop["wood"], 0)
        total = (await self.values("alice"))["wood"] + (await self.values("bob"))["wood"]
        self.assertEqual(total, 1)

    async def test_late_failure_rolls_back_both_nodes_and_event_count(self):
        self.add_actor("alice", {"wood": 0, "ap": 5, "flag": "文本"})
        self.add_service(
            {
                "actions": [gather_action(actor_deltas={"wood": 1}, local_deltas={"wood": -1})],
                "events": [
                    {
                        "id": "bad-reward",
                        "text": "错误奖励",
                        "probability": 1,
                        "limit": 5,
                        "rewards": {"flag": 1},
                    }
                ],
            },
            {"wood": 5},
        )
        self.connect_actor("alice")

        before_actor = await self.values("alice")
        before_shop = await self.values("shop")
        failed = await self.call("alice", {"action": "gather", "key": "late-fail"})
        self.assertEqual(failed["status"], "error", failed)
        self.assertIn("flag", failed["error"])

        self.assertEqual(await self.values("alice"), before_actor)
        self.assertEqual(await self.values("shop"), before_shop)

        service = self.h.modules.get("shop", "service.actions")
        self.assertEqual(service.state.get("event_counts", {}), {})
        self.assertEqual(service.state.get("receipts", []), [])

        # 失败不消耗事件次数；修正数据后同一事件仍可触发。
        await self.h.call(
            "alice",
            "apply",
            {"set": {"flag": 0}},
            module="records.store",
            actor="alice",
            strength=1,
            channels=["records"],
        )
        retried = await self.call("alice", {"action": "gather", "key": "late-fail-2"})
        self.assertEqual(retried["status"], "ok", retried)
        service = self.h.modules.get("shop", "service.actions")
        self.assertEqual(service.state["event_counts"]["bad-reward"], 1)

    async def test_probability_zero_one_and_shared_limit(self):
        self.add_actor("alice", {"wood": 0, "gold": 0, "ap": 9})
        self.add_service(
            {
                "actions": [gather_action()],
                "events": [
                    {"id": "never", "text": "不会发生", "probability": 0, "limit": None, "rewards": {"gold": 100}},
                    {"id": "always", "text": "必然发生", "probability": 1, "limit": 1, "rewards": {"gold": 1}},
                ],
            },
            {"wood": 10},
        )
        self.connect_actor("alice")

        first = await self.call("alice", {"action": "gather", "key": "event-1"})
        self.assertEqual(first["status"], "ok", first)
        self.assertIn("必然发生", first["data"]["observation"])
        self.assertNotIn("不会发生", first["data"]["observation"])
        self.assertEqual((await self.values("alice"))["gold"], 1)

        second = await self.call("alice", {"action": "gather", "key": "event-2"})
        self.assertEqual(second["status"], "ok", second)
        self.assertNotIn("必然发生", second["data"]["observation"])
        self.assertEqual((await self.values("alice"))["gold"], 1)

        service = self.h.modules.get("shop", "service.actions")
        self.assertEqual(service.state["event_counts"], {"always": 1})

    async def test_retry_with_same_key_is_idempotent(self):
        self.add_actor("alice", {"wood": 0, "gold": 10, "ap": 5})
        self.add_service(
            {
                "actions": [gather_action()],
                "events": [
                    {"id": "once", "text": "一次性奖励", "probability": 1, "limit": 1, "rewards": {"gold": 2}}
                ],
            },
            {"wood": 10},
        )
        self.connect_actor("alice")

        first = await self.call("alice", {"action": "gather", "quantity": 2, "key": "same"})
        self.assertEqual(first["status"], "ok", first)
        after_first_actor = await self.values("alice")
        after_first_shop = await self.values("shop")

        repeated = await self.call("alice", {"action": "gather", "quantity": 2, "key": "same"})
        self.assertEqual(repeated["status"], "ok", repeated)
        self.assertTrue(repeated["data"]["duplicate"])
        self.assertEqual(repeated["data"]["values"], first["data"]["values"])
        self.assertEqual(await self.values("alice"), after_first_actor)
        self.assertEqual(await self.values("shop"), after_first_shop)

        different_quantity = await self.call("alice", {"action": "gather", "quantity": 1, "key": "same"})
        self.assertEqual(different_quantity["status"], "error", different_quantity)
        self.assertIn("幂等键", different_quantity["error"])
        self.assertEqual(await self.values("alice"), after_first_actor)
        self.assertEqual(await self.values("shop"), after_first_shop)

    async def test_schema_rejects_bad_quantity_and_actor_id_spoof(self):
        self.add_actor("alice", {"wood": 0, "ap": 5})
        self.add_service({"actions": [gather_action()]}, {"wood": 10})
        self.connect_actor("alice")

        for parameters in (
            {"action": "gather", "quantity": "2"},
            {"action": "gather", "quantity": 0},
            {"action": "gather", "quantity": 101},
            {"action": "gather", "actor_id": "bob"},
            {"action": "gather", "request_key": "old-alias"},
        ):
            with self.assertRaises(ValidationError):
                await self.call("alice", parameters)

        self.assertEqual((await self.values("alice"))["wood"], 0)
        self.assertEqual((await self.values("shop"))["wood"], 10)

    async def test_agent_tools_expose_inspect_and_perform(self):
        self.add_actor("alice", {"wood": 0, "ap": 5}, name="Alice")
        self.add_service({"actions": [gather_action()]}, {"wood": 10})
        self.connect_actor("alice")

        entries = await self.h.tools.visit(
            "alice",
            "shop",
            strength=2,
            channels=["service", "records", "movement"],
        )
        by_id = {entry["tool_id"]: entry for entry in entries}
        self.assertIn("inspect", by_id)
        self.assertIn("perform", by_id)

        inspected = await self.h.tools.invoke(
            "alice",
            by_id["inspect"],
            {},
            strength=2,
            channels=["service", "records", "movement"],
        )
        self.assertEqual(inspected["inventory"]["wood"], 10)

        performed = await self.h.tools.invoke(
            "alice",
            by_id["perform"],
            {"action": "gather", "quantity": 1, "key": "tool-1"},
            strength=2,
            channels=["service", "records", "movement"],
        )
        self.assertEqual(performed["actor"], "alice")
        self.assertEqual(performed["values"]["wood"], 2)

    async def test_same_key_isolated_across_two_shops_and_two_agents(self):
        self.add_actor("alice", {"wood": 0, "gold": 10, "ap": 5})
        self.add_actor("bob", {"wood": 0, "gold": 10, "ap": 5})
        shops = ("shop-a", "shop-b")
        for shop in shops:
            self.add_service(
                {"actions": [buy_action()]},
                {"wood": 10, "gold": 0},
                node=shop,
                name=f"服务场所{shop}",
            )
            for actor in ("alice", "bob"):
                self.connect_actor(actor, shop=shop)

        user_key = "same-user-key"
        firsts = {}
        for actor in ("alice", "bob"):
            for shop in shops:
                result = await self.call(
                    actor,
                    {"action": "buy", "quantity": 1, "key": user_key},
                    shop=shop,
                )
                self.assertEqual(result["status"], "ok", result)
                self.assertFalse(result["data"]["duplicate"], result)
                self.assertEqual(result["data"]["actor"], actor)
                firsts[(actor, shop)] = result["data"]

        # 每个 Agent 在两家商店各买 1 份，跨实例同键不能复用扣费回执。
        for actor, expected_gold in (("alice", 4), ("bob", 4)):
            values = await self.values(actor)
            self.assertEqual((values["wood"], values["gold"], values["ap"]), (2, expected_gold, 3))
        for shop in shops:
            stock = await self.values(shop)
            self.assertEqual((stock["wood"], stock["gold"]), (8, 6))

        totals = {node: await self.values(node) for node in ("alice", "bob", *shops)}
        self.assertEqual(sum(values["gold"] for values in totals.values()), 20)
        self.assertEqual(sum(values["wood"] for values in totals.values()), 20)

        # 同一实例内部用相同键重试，只返回旧结果，不再次扣费或减库存。
        for actor in ("alice", "bob"):
            for shop in shops:
                repeated = await self.call(
                    actor,
                    {"action": "buy", "quantity": 1, "key": user_key},
                    shop=shop,
                )
                self.assertEqual(repeated["status"], "ok", repeated)
                self.assertTrue(repeated["data"]["duplicate"], repeated)
                self.assertEqual(repeated["data"]["values"], firsts[(actor, shop)]["values"])

        for actor in ("alice", "bob"):
            values = await self.values(actor)
            self.assertEqual((values["wood"], values["gold"], values["ap"]), (2, 4, 3))
        for shop in shops:
            stock = await self.values(shop)
            self.assertEqual((stock["wood"], stock["gold"]), (8, 6))
        totals = {node: await self.values(node) for node in ("alice", "bob", *shops)}
        self.assertEqual(sum(values["gold"] for values in totals.values()), 20)
        self.assertEqual(sum(values["wood"] for values in totals.values()), 20)


    async def test_require_values_and_items_allow_adult_with_pickaxe(self):
        self.add_actor("alice", {"adult": True, "pickaxe": 1, "wood": 0, "ap": 5})
        self.add_actor("child", {"adult": False, "pickaxe": 1, "wood": 0, "ap": 5})
        self.add_service(
            {
                "actions": [
                    {
                        "id": "mine",
                        "title": "采矿",
                        "require_values": {"adult": True},
                        "require_items": {"pickaxe": 1},
                        "actor_deltas": {"wood": 2},
                        "local_deltas": {"wood": -2},
                        "cost": 1,
                    }
                ]
            },
            {"wood": 10},
        )
        self.connect_actor("alice")
        self.connect_actor("child")

        mined = await self.call("alice", {"action": "mine", "key": "adult-mine"})
        self.assertEqual(mined["status"], "ok", mined)
        alice = await self.values("alice")
        self.assertEqual((alice["wood"], alice["pickaxe"], alice["ap"]), (2, 1, 4))
        self.assertEqual((await self.values("shop"))["wood"], 8)

        before_child = await self.values("child")
        before_shop = await self.values("shop")
        refused = await self.call("child", {"action": "mine", "key": "child-mine"})
        self.assertEqual(refused["status"], "error", refused)
        self.assertIn("adult", refused["error"])
        self.assertEqual(await self.values("child"), before_child)
        self.assertEqual(await self.values("shop"), before_shop)

    async def test_require_items_scales_with_quantity_and_does_not_consume(self):
        self.add_actor("alice", {"pickaxe": 1, "wood": 0, "ap": 5})
        self.add_service(
            {
                "actions": [
                    {
                        "id": "mine",
                        "title": "采矿",
                        "require_items": {"pickaxe": 1},
                        "actor_deltas": {"wood": 1},
                        "local_deltas": {"wood": -1},
                        "cost": 0,
                    }
                ]
            },
            {"wood": 10},
        )
        self.connect_actor("alice")

        refused = await self.call(
            "alice", {"action": "mine", "quantity": 2, "key": "need-two"}
        )
        self.assertEqual(refused["status"], "error", refused)
        self.assertIn("pickaxe", refused["error"])
        self.assertEqual((await self.values("alice"))["wood"], 0)
        self.assertEqual((await self.values("shop"))["wood"], 10)

        await self.h.call(
            "alice",
            "apply",
            {"set": {"pickaxe": 2}},
            module="records.store",
            actor="alice",
            strength=1,
            channels=["records"],
        )
        mined = await self.call(
            "alice", {"action": "mine", "quantity": 2, "key": "have-two"}
        )
        self.assertEqual(mined["status"], "ok", mined)
        alice = await self.values("alice")
        self.assertEqual((alice["wood"], alice["pickaxe"]), (2, 2))
        self.assertEqual((await self.values("shop"))["wood"], 8)

    async def test_borrow_and_repay_are_configuration_with_debt_cap(self):
        self.add_actor("alice", {"wood": 0, "gold": 5, "debt": 0, "ap": 6})
        self.add_service(
            {
                "actions": [
                    {
                        "id": "borrow",
                        "title": "借贷购买木材",
                        "actor_deltas": {"wood": 1, "debt": 2},
                        "local_deltas": {"wood": -1, "receivable": 2},
                        "actor_maximums": {"debt": 8},
                        "cost": 1,
                    },
                    {
                        "id": "repay",
                        "title": "还款",
                        "actor_deltas": {"gold": -2, "debt": -2},
                        "local_deltas": {"gold": 2, "receivable": -2},
                        "cost": 1,
                    },
                ]
            },
            {"wood": 10, "gold": 0, "receivable": 0},
        )
        self.connect_actor("alice")

        for index in range(4):
            borrowed = await self.call(
                "alice", {"action": "borrow", "key": f"borrow-{index}"}
            )
            self.assertEqual(borrowed["status"], "ok", borrowed)

        alice = await self.values("alice")
        shop = await self.values("shop")
        self.assertEqual((alice["wood"], alice["gold"], alice["debt"], alice["ap"]), (4, 5, 8, 2))
        self.assertEqual((shop["wood"], shop["gold"], shop["receivable"]), (6, 0, 8))

        before_actor = await self.values("alice")
        before_shop = await self.values("shop")
        over_limit = await self.call(
            "alice", {"action": "borrow", "key": "borrow-over-limit"}
        )
        self.assertEqual(over_limit["status"], "error", over_limit)
        self.assertIn("上限", over_limit["error"])
        self.assertEqual(await self.values("alice"), before_actor)
        self.assertEqual(await self.values("shop"), before_shop)

        repaid = await self.call("alice", {"action": "repay", "key": "repay-1"})
        self.assertEqual(repaid["status"], "ok", repaid)
        alice = await self.values("alice")
        shop = await self.values("shop")
        self.assertEqual((alice["gold"], alice["debt"], alice["ap"]), (3, 6, 1))
        self.assertEqual((shop["gold"], shop["receivable"]), (2, 6))

    async def test_event_rewards_cannot_bypass_actor_maximum(self):
        self.add_actor("alice", {"wood": 0, "debt": 0, "ap": 5})
        self.add_service(
            {
                "actions": [
                    {
                        "id": "capped",
                        "title": "额度二",
                        "actor_deltas": {"debt": 2},
                        "local_deltas": {"wood": -1},
                        "actor_maximums": {"debt": 2},
                        "cost": 1,
                    },
                    {
                        "id": "exact",
                        "title": "额度三",
                        "actor_deltas": {"debt": 2},
                        "local_deltas": {"wood": -1},
                        "actor_maximums": {"debt": 3},
                        "cost": 1,
                    },
                ],
                "events": [
                    {
                        "id": "debt-bonus",
                        "text": "额外债务奖励",
                        "probability": 1,
                        "limit": 1,
                        "rewards": {"debt": 1},
                    }
                ],
            },
            {"wood": 5},
        )
        self.connect_actor("alice")

        before_actor = await self.values("alice")
        before_shop = await self.values("shop")
        failed = await self.call("alice", {"action": "capped", "key": "max-fail"})
        self.assertEqual(failed["status"], "error", failed)
        self.assertIn("debt", failed["error"])
        self.assertIn("上限", failed["error"])
        self.assertEqual(await self.values("alice"), before_actor)
        self.assertEqual(await self.values("shop"), before_shop)
        service = self.h.modules.get("shop", "service.actions")
        self.assertEqual(service.state.get("event_counts", {}), {})
        self.assertEqual(service.state.get("receipts", []), [])

        succeeded = await self.call("alice", {"action": "exact", "key": "max-ok"})
        self.assertEqual(succeeded["status"], "ok", succeeded)
        self.assertEqual((await self.values("alice"))["debt"], 3)
        self.assertEqual(service.state["event_counts"], {"debt-bonus": 1})

        before_actor = await self.values("alice")
        before_shop = await self.values("shop")
        second = await self.call("alice", {"action": "exact", "key": "max-again"})
        self.assertEqual(second["status"], "error", second)
        self.assertIn("上限", second["error"])
        self.assertEqual(await self.values("alice"), before_actor)
        self.assertEqual(await self.values("shop"), before_shop)
        self.assertEqual(service.state["event_counts"], {"debt-bonus": 1})

    async def test_repair_uses_actor_set_without_multiplying_and_set_before_delta(self):
        self.add_actor(
            "alice",
            {"gold": 5, "pickaxe_state": "磨损", "repair_count": 0, "score": 0, "ap": 5},
        )
        self.add_service(
            {
                "actions": [
                    {
                        "id": "repair",
                        "title": "修理",
                        "require_values": {"pickaxe_state": "磨损"},
                        "actor_set": {"pickaxe_state": "良好", "repair_count": 1},
                        "actor_deltas": {"gold": -1},
                        "local_deltas": {"gold": 1},
                        "cost": 0,
                    },
                    {
                        "id": "adjust",
                        "title": "调整分数",
                        "actor_set": {"score": 10},
                        "actor_deltas": {"score": 2},
                        "cost": 0,
                    },
                ]
            },
            {"gold": 0},
        )
        self.connect_actor("alice")

        repaired = await self.call(
            "alice", {"action": "repair", "quantity": 2, "key": "repair-2"}
        )
        self.assertEqual(repaired["status"], "ok", repaired)
        alice = await self.values("alice")
        self.assertEqual(alice["pickaxe_state"], "良好")
        self.assertEqual(alice["repair_count"], 1)
        self.assertEqual(alice["gold"], 3)
        self.assertEqual((await self.values("shop"))["gold"], 2)

        adjusted = await self.call("alice", {"action": "adjust", "key": "adjust-1"})
        self.assertEqual(adjusted["status"], "ok", adjusted)
        self.assertEqual((await self.values("alice"))["score"], 12)


if __name__ == "__main__":
    unittest.main()
