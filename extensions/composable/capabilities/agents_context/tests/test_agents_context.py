import unittest
from pathlib import Path

from jsonschema.exceptions import ValidationError

from datanet.studio.testing import ModuleHarness


SELF = ["self"]


class AgentsContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = ModuleHarness(Path(__file__).resolve().parents[1])
        self.h.add_node("town", name="镇广场")
        self.h.add_node("forest", name="北林")
        self.h.connect("town", "forest", channels=["movement"], threshold=1)
        self.place_instances = {}

    async def asyncTearDown(self):
        await self.h.close()

    async def mount_agent(
        self,
        node_id,
        *,
        persona="",
        common="",
        map_text="",
        opening="",
        clock=None,
        max_memories=100,
        initial=None,
        location="town",
        name=None,
        public_fields=None,
        knowledge=None,
    ):
        self.h.add_node(node_id, name=name or node_id, agent=True)
        self.h.mount(
            node_id,
            module="records.store",
            config={"initial": initial or {}},
            access={"strength": 1, "channels": ["records"]},
        )
        place_instance = self.h.mount(
            node_id,
            module="place.info",
            config={"location": location, "description": "角色位置"},
            access={"strength": 0, "channels": ["movement"]},
        )
        self.place_instances[node_id] = place_instance
        instance = self.h.mount(
            node_id,
            config={
                "persona": persona,
                "common": common,
                "map": map_text,
                "opening": opening,
                "clock": clock,
                "max_memories": max_memories,
                "public_fields": public_fields
                if public_fields is not None
                else ["name", "gender", "profession", "age_group"],
                "knowledge": knowledge or [],
            },
            access={"strength": 2, "channels": ["self", "records", "movement", "info"]},
        )
        self.h.connect(node_id, "town", channels=["movement", "info"], threshold=1)
        return instance

    def inputs(self, node_id):
        snapshot = self.h.network.nodes[node_id].inputs.snapshot()
        return snapshot["module:agents.context"]

    async def test_real_agent_assembly_and_prepare(self):
        await self.mount_agent(
            "a",
            persona="你是图书管理员。",
            common="回答保持简洁。",
            map_text="镇广场北接北林。",
            initial={"gold": 3, "role": "npc"},
            name="阿岚",
        )
        result = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(result["status"], "ok", result)
        data = result["data"]
        self.assertEqual(data["system_prompt"], "你是图书管理员。\n\n回答保持简洁。")
        self.assertEqual(data["context"], [{"id": "map", "text": "镇广场北接北林。"}])
        self.assertEqual(data["records"]["gold"], 3)
        self.assertEqual(data["location"], "town")
        self.assertIn("town", [item["id"] for item in data["nearby"]])
        self.assertTrue(any("个人记录" in line and "gold" in line for line in data["tail"]))
        snapshot = self.inputs("a")
        self.assertEqual(snapshot["system_prompt"], data["system_prompt"])
        self.assertEqual(snapshot["context"], data["context"])
        self.assertEqual(snapshot["tail"], data["tail"])

    async def test_private_memories_and_cross_agent_rejection(self):
        a_instance = await self.mount_agent("a", persona="甲")
        await self.mount_agent("b", persona="乙")
        self.h.connect("b", "a", channels=["self"], threshold=1)
        self.h.connect("a", "b", channels=["self"], threshold=1)

        saved = await self.h.call("a", "remember", {"text": "甲的秘密"}, actor="a", channels=SELF)
        self.assertEqual(saved["status"], "ok", saved)
        own = await self.h.call("a", "recall", {"query": "秘密"}, actor="a", channels=SELF)
        self.assertEqual(own["status"], "ok", own)
        self.assertEqual(own["data"]["count"], 1)

        denied = await self.h.call("a", "recall", {"query": "秘密"}, actor="b", channels=SELF)
        self.assertEqual(denied["status"], "error", denied)
        self.assertIn("自己", denied["error"])
        denied_look = await self.h.call("a", "look", {}, actor="b", channels=SELF)
        self.assertEqual(denied_look["status"], "error", denied_look)

        other = await self.h.call("b", "recall", {"query": ""}, actor="b", channels=SELF)
        self.assertEqual(other["status"], "ok", other)
        self.assertEqual(other["data"]["count"], 0)
        self.assertEqual(a_instance.state["memories"][0]["text"], "甲的秘密")

    async def test_tools_are_exported_and_cannot_read_other_agent(self):
        await self.mount_agent("a")
        await self.mount_agent("b")
        self.h.connect("b", "a", channels=["self"], threshold=1)

        entries = await self.h.tools.visit("a", "a", strength=1, channels=SELF)
        ids = {entry["tool_id"] for entry in entries}
        self.assertTrue({"remember", "recall", "look"}.issubset(ids), ids)
        entry = next(item for item in entries if item["tool_id"] == "remember")
        await self.h.tools.invoke("a", entry, {"text": "工具记忆"}, strength=1, channels=SELF)
        recall_entry = next(item for item in entries if item["tool_id"] == "recall")
        recalled = await self.h.tools.invoke("a", recall_entry, {"query": "工具"}, strength=1, channels=SELF)
        self.assertEqual(recalled["count"], 1)

        other_entries = await self.h.tools.visit("b", "a", strength=1, channels=SELF)
        other_recall = next(item for item in other_entries if item["tool_id"] == "recall")
        with self.assertRaises(Exception):
            await self.h.tools.invoke("b", other_recall, {"query": ""}, strength=1, channels=SELF)

    async def test_opening_is_queued_only_once(self):
        instance = await self.mount_agent("a", opening="故事从这里开始。")
        first = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(first["status"], "ok", first)
        self.assertTrue(first["data"]["opening_queued"])
        snapshot = self.inputs("a")
        opening_items = [item for item in snapshot["inputs"] if item.get("id") == "agents.context.opening"]
        self.assertEqual(len(opening_items), 1)
        self.assertEqual(opening_items[0]["text"], "故事从这里开始。")

        second = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(second["status"], "ok", second)
        snapshot = self.inputs("a")
        opening_items = [item for item in snapshot["inputs"] if item.get("id") == "agents.context.opening"]
        self.assertEqual(len(opening_items), 1)
        self.assertNotIn("故事从这里开始。", second["data"]["system_prompt"])
        self.assertEqual(instance.state["opening_queued"], True)

    async def test_remember_idempotency_and_retention_limit(self):
        await self.mount_agent("a", max_memories=2)
        one = await self.h.call("a", "remember", {"text": "第一条"}, actor="a", channels=SELF)
        self.assertEqual(one["status"], "ok", one)
        two = await self.h.call("a", "remember", {"text": "第二条"}, actor="a", channels=SELF)
        self.assertEqual(two["status"], "ok", two)
        three = await self.h.call("a", "remember", {"text": "第三条"}, actor="a", channels=SELF)
        self.assertEqual(three["status"], "ok", three)
        self.assertEqual([item["text"] for item in three["data"]["memories"]], ["第二条", "第三条"])
        self.assertEqual(three["data"]["count"], 2)

        keyed = await self.h.call("a", "remember", {"text": "带键内容", "key": "k1"}, actor="a", channels=SELF)
        self.assertEqual(keyed["status"], "ok", keyed)
        duplicate = await self.h.call("a", "remember", {"text": "带键内容", "key": "k1"}, actor="a", channels=SELF)
        self.assertEqual(duplicate["status"], "ok", duplicate)
        self.assertTrue(duplicate["data"]["duplicate"])
        self.assertEqual(duplicate["data"]["count"], 2)
        conflict = await self.h.call("a", "remember", {"text": "不同内容", "key": "k1"}, actor="a", channels=SELF)
        self.assertEqual(conflict["status"], "error", conflict)
        self.assertIn("不同内容", conflict["error"])
        with self.assertRaises(ValidationError):
            await self.h.call("a", "remember", {"text": ""}, actor="a", channels=SELF)

    async def test_map_context_and_empty_map(self):
        await self.mount_agent("a", map_text="工作组地图：A 组在二楼。")
        result = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["context"], [{"id": "map", "text": "工作组地图：A 组在二楼。"}])
        self.assertEqual(self.inputs("a")["context"], result["data"]["context"])

        await self.mount_agent("b")
        result = await self.h.call("b", "prepare", {}, actor="b", channels=SELF)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["context"], [])

    async def test_prepare_refreshes_tail_after_location_and_edges_change(self):
        await self.mount_agent("a")
        before = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(before["status"], "ok", before)
        self.assertTrue(any("当前位置：town" in line for line in before["data"]["tail"]))
        self.assertTrue(any("镇广场" in line for line in before["data"]["tail"]))

        self.h.connect("a", "forest", channels=["movement"], threshold=1)
        self.h.disconnect("a", "town")
        self.place_instances["a"].state["location"] = "forest"
        after = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(after["status"], "ok", after)
        after_tail = after["data"]["tail"]
        self.assertTrue(any("当前位置：forest" in line for line in after_tail))
        self.assertTrue(any("北林" in line for line in after_tail))
        self.assertNotEqual(before["data"]["tail"], after_tail)
        self.assertEqual(self.inputs("a")["tail"], after_tail)

    async def test_clock_is_read_from_configured_node(self):
        self.h.mount(
            "town",
            module="clock.counter",
            config={
                "initial_tick": 2,
                "labels": ["清晨", "上午", "下午"],
                "signal_channels": ["tick"],
            },
            access={"strength": 0, "channels": ["info", "tick", "demo"]},
        )
        await self.mount_agent("a", clock="town")
        result = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(result["status"], "ok", result)
        self.assertEqual(result["data"]["clock"], {"tick": 2, "day": 1, "slot": "上午"})
        self.assertTrue(any("第1天 上午" in line and "计数 2" in line for line in result["data"]["tail"]))
        looked = await self.h.call("a", "look", {}, actor="a", channels=SELF)
        self.assertEqual(looked["status"], "ok", looked)
        self.assertEqual(looked["data"]["clock"], result["data"]["clock"])

    async def test_only_configured_public_fields_are_published(self):
        await self.mount_agent(
            "a",
            opening="只属于甲的开场秘密",
            initial={
                "name": "阿岚",
                "gender": "女",
                "profession": "农夫",
                "age_group": "成年",
                "gold": 99,
                "secret": "不可公开的账目",
            },
            public_fields=["name", "profession"],
            name="阿岚",
        )
        await self.mount_agent("b", name="乙")
        self.h.connect("b", "a", channels=["movement"], threshold=1)
        saved = await self.h.call("a", "remember", {"text": "私人记忆不可发布"}, actor="a", channels=SELF)
        self.assertEqual(saved["status"], "ok", saved)

        prepared_a = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(prepared_a["status"], "ok", prepared_a)
        prepared_b = await self.h.call("b", "prepare", {}, actor="b", channels=SELF)
        self.assertEqual(prepared_b["status"], "ok", prepared_b)

        entry = next(item for item in prepared_b["data"]["nearby"] if item["id"] == "a")
        self.assertEqual(entry["profile"], {"name": "阿岚", "profession": "农夫"})
        serialized = repr(entry) + repr(prepared_b["data"]["tail"])
        for leaked in ("99", "gold", "不可公开的账目", "私人记忆不可发布", "开场秘密"):
            self.assertNotIn(leaked, serialized)

    async def test_same_location_profile_shows_in_tail_and_disappears_after_disconnect(self):
        await self.mount_agent(
            "a",
            initial={"name": "阿岚", "gender": "女", "profession": "农夫", "age_group": "成年"},
        )
        await self.mount_agent(
            "b",
            initial={"name": "小北", "gender": "男", "profession": "铁匠", "age_group": "青年"},
        )
        self.h.connect("b", "a", channels=["movement"], threshold=1)
        first_a = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(first_a["status"], "ok", first_a)
        first_b = await self.h.call("b", "prepare", {}, actor="b", channels=SELF)
        self.assertEqual(first_b["status"], "ok", first_b)

        entry = next(item for item in first_b["data"]["nearby"] if item["id"] == "a")
        self.assertEqual(
            entry["profile"],
            {"name": "阿岚", "gender": "女", "profession": "农夫", "age_group": "成年"},
        )
        tail_text = "\n".join(first_b["data"]["tail"])
        for expected in ("阿岚", "姓名：阿岚", "性别：女", "职业：农夫", "年龄段：成年"):
            self.assertIn(expected, tail_text)

        self.h.disconnect("b", "a")
        second_b = await self.h.call("b", "prepare", {}, actor="b", channels=SELF)
        self.assertEqual(second_b["status"], "ok", second_b)
        self.assertNotIn("a", [item["id"] for item in second_b["data"]["nearby"]])
        self.assertNotIn("阿岚", "\n".join(second_b["data"]["tail"]))

    async def test_knowledge_matches_own_records_and_other_agent_cannot_prepare(self):
        knowledge = [
            {"id": "farmer", "when": {"profession": "农夫"}, "text": "农夫懂得看节气。"},
            {"id": "doctor", "when": {"profession": "医生"}, "text": "医生熟悉药房。"},
            {"id": "female", "when": {"gender": "女"}, "text": "女性生理知识。"},
            {"id": "pregnant", "when": {"pregnant": True}, "text": "怀孕护理知识。"},
            {"id": "parent", "when": {"children": 2}, "text": "养育两个孩子的知识。"},
        ]
        await self.mount_agent(
            "a",
            initial={"profession": "农夫", "gender": "女", "pregnant": False, "children": 1},
            knowledge=knowledge,
        )
        await self.mount_agent(
            "b",
            initial={"profession": "医生", "gender": "男", "pregnant": False, "children": 0},
            knowledge=knowledge,
        )
        self.h.connect("b", "a", channels=["self"], threshold=1)

        first = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(first["status"], "ok", first)
        texts = [item["text"] for item in first["data"]["context"]]
        self.assertIn("农夫懂得看节气。", texts)
        self.assertIn("女性生理知识。", texts)
        self.assertNotIn("医生熟悉药房。", texts)
        self.assertNotIn("怀孕护理知识。", texts)
        self.assertNotIn("养育两个孩子的知识。", texts)
        ids = [item["id"] for item in first["data"]["context"]]
        self.assertEqual(ids, ["knowledge:farmer", "knowledge:female"])
        self.assertNotIn("map", ids)

        second = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(second["data"]["context"], first["data"]["context"])

        doctor = await self.h.call("b", "prepare", {}, actor="b", channels=SELF)
        self.assertEqual(doctor["status"], "ok", doctor)
        doctor_texts = [item["text"] for item in doctor["data"]["context"]]
        self.assertIn("医生熟悉药房。", doctor_texts)
        self.assertNotIn("农夫懂得看节气。", doctor_texts)

        denied = await self.h.call("a", "prepare", {}, actor="b", channels=SELF)
        self.assertEqual(denied["status"], "error", denied)
        self.assertIn("自己", denied["error"])

    async def test_record_change_refreshes_knowledge_keeps_map_and_opening(self):
        knowledge = [
            {"id": "farmer", "when": {"profession": "农夫"}, "text": "农夫懂得看节气。"},
            {"id": "doctor", "when": {"profession": "医生"}, "text": "医生熟悉药房。"},
        ]
        await self.mount_agent(
            "a",
            map_text="镇广场北接北林。",
            opening="唯一开场。",
            initial={"profession": "农夫"},
            knowledge=knowledge,
        )
        first = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(first["status"], "ok", first)
        self.assertEqual(
            first["data"]["context"],
            [
                {"id": "map", "text": "镇广场北接北林。"},
                {"id": "knowledge:farmer", "text": "农夫懂得看节气。"},
            ],
        )
        self.assertTrue(first["data"]["opening_queued"])

        changed = await self.h.call(
            "a",
            "apply",
            {"set": {"profession": "医生"}},
            actor="a",
            module="records.store",
            channels=["records"],
        )
        self.assertEqual(changed["status"], "ok", changed)

        second = await self.h.call("a", "prepare", {}, actor="a", channels=SELF)
        self.assertEqual(second["status"], "ok", second)
        self.assertEqual(
            second["data"]["context"],
            [
                {"id": "map", "text": "镇广场北接北林。"},
                {"id": "knowledge:doctor", "text": "医生熟悉药房。"},
            ],
        )
        self.assertTrue(second["data"]["opening_queued"])
        opening_items = [
            item
            for item in self.inputs("a")["inputs"]
            if item.get("id") == "agents.context.opening"
        ]
        self.assertEqual(len(opening_items), 1)
        self.assertEqual(opening_items[0]["text"], "唯一开场。")


if __name__ == "__main__":
    unittest.main()
