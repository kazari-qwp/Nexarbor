"""验证网络管理工具和 Agent 的真实本地工具反馈。"""

import json
import unittest
from unittest.mock import Mock

from openai.types.chat import ChatCompletion

from applications.network_demo.setup import build_agent_network, build_demo_network


class NetworkDemoTests(unittest.TestCase):
    def setUp(self):
        self.network, self.root = build_demo_network()

    def test_describe_connections_and_tools(self):
        result = self.root.invoke_tool("describe_node", node_id="n1")
        self.assertEqual(result["strong_read_targets"], ["n2"])
        self.assertEqual(result["weak_read_targets"], ["n3", "n2"])
        self.assertEqual(set(self.root.tools), {"describe_node", "weak_read", "strong_read", "weak_write", "strong_write", "list_nodes", "list_tools", "invoke_tool"})
        self.assertFalse(any(n.agent is not None for n in self.network.nodes.values()))

    def test_scope_cycle_and_arbitrary_origin(self):
        for origin, tool, expected in (
            ("n1", "weak_read", [1, 2, 4]),
            ("n1", "strong_read", [1, 2, 3, 4, 5, 6]),
            ("n5", "weak_read", [5, 6]),
            ("n5", "strong_read", [5, 6, 2, 4, 1, 3]),
        ):
            with self.subTest(origin=origin, tool=tool):
                result = self.root.invoke_tool(tool, node_id=origin, key="value")
                self.assertEqual(result["status"], "ok")
                self.assertEqual([i["value"] for i in result["items"]], expected)
                self.assertEqual(len(result["sources"]), len(expected))
                self.assertTrue(all(s["retrieval_path"][0] == origin for s in result["sources"]))

    def test_missing_node_and_key(self):
        result = self.root.invoke_tool("strong_read", node_id="n99", key="value")
        self.assertEqual(result["status"], "error")
        self.assertTrue(result["errors"])
        with self.assertRaises(ValueError):
            self.root.invoke_tool("describe_node", node_id="n99")
        for origin, key in (("root", "missing"), ("n1", "missing")):
            result = self.root.invoke_tool("weak_read", node_id=origin, key=key)
            self.assertEqual(result["status"], "not_found")

    def test_omitted_origin_defaults_to_owner_and_can_be_overridden(self):
        for tool, expected in (("weak_read", [1, 2, 4]), ("strong_read", [1, 2, 3, 4, 5, 6])):
            result = self.root.invoke_tool(tool, key="value")
            self.assertEqual([i["value"] for i in result["items"]], expected)
            self.assertTrue(all(s["retrieval_path"][0] == "root" for s in result["sources"]))
        explicit = self.root.invoke_tool("weak_read", node_id="n5", key="value")
        self.assertEqual([i["value"] for i in explicit["items"]], [5, 6])
        self.assertTrue(all(s["retrieval_path"][0] == "n5" for s in explicit["sources"]))

    def test_model_schema_allows_omitting_origin(self):
        _, root = build_agent_network(Mock(), "mock")
        for definition in root.agent.tool_definitions:
            if definition["function"]["name"] in ("weak_read", "strong_read"):
                schema = definition["function"]["parameters"]
                self.assertEqual(schema["required"], ["key"])
                self.assertIn("node_id", schema["properties"])

    def test_arguments_must_be_strings(self):
        with self.assertRaises(TypeError):
            self.root.invoke_tool("describe_node", node_id=1)
        with self.assertRaises(TypeError):
            self.root.invoke_tool("strong_read", node_id="n1", key=None)

    def test_agent_receives_each_tool_result(self):
        calls = []
        for index, name in enumerate(("describe_node", "weak_read", "strong_read")):
            args = {"node_id": "n1"}
            if name != "describe_node":
                args["key"] = "value"
            calls.append({"id": str(index), "type": "function", "function": {
                "name": name, "arguments": json.dumps(args),
            }})
        def response(message, reason):
            return ChatCompletion(id="mock", object="chat.completion", created=0,
                model="mock", choices=[{"index": 0, "finish_reason": reason, "message": message}])
        client = Mock()
        client.chat.completions.create.side_effect = [
            response({"role": "assistant", "content": None, "tool_calls": calls}, "tool_calls"),
            response({"role": "assistant", "content": "弱读三个，强读六个。"}, "stop"),
        ]
        network, root = build_agent_network(client, "mock")
        self.assertEqual(root.invoke_agent("比较读取范围"), "弱读三个，强读六个。")
        self.assertEqual([n.node_id for n in network.nodes.values() if n.agent is not None], ["root"])
        feedback = {m["tool_call_id"]: json.loads(m["content"])
                    for m in root.agent.messages if m["role"] == "tool"}
        self.assertEqual([i["value"] for i in feedback["1"]["items"]], [1, 2, 4])
        self.assertEqual([i["value"] for i in feedback["2"]["items"]], [1, 2, 3, 4, 5, 6])
        self.assertEqual(feedback["2"]["sources"][-1]["retrieval_path"], ["n1", "n2", "n5", "n6"])


if __name__ == "__main__":
    unittest.main()
