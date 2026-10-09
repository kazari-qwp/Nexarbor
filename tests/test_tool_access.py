"""按需发现、读取范围、工具重名、参数和真实本地执行反馈。"""

import json
import unittest
from unittest.mock import Mock

from openai.types.chat import ChatCompletion
from datanet.nodes import Node
from datanet.tool_access import attach_discovery_tools, invoke_tool
from applications.network_demo.setup import build_agent_network, build_demo_network
from applications.experiment.network_setup import build_lab_network


class ToolAccessTests(unittest.TestCase):
    def setUp(self):
        self.network, self.root = build_demo_network()

    def test_directory_is_scoped_without_parameter_definitions(self):
        result = self.root.invoke_tool("list_nodes")
        self.assertEqual([i["node_id"] for i in result.items], ["root", "n1", "n2", "n4"])
        self.assertTrue(all("parameters" not in i for i in result.items))
        strong = self.root.invoke_tool("list_nodes", scope="federated")
        self.assertEqual(len(strong.items), 7)

    def test_requires_discovery_then_uses_target_context(self):
        arguments = {"target_node_id": "n2", "tool_name": "get_value", "arguments": {}}
        self.assertEqual(self.root.invoke_tool("invoke_tool", **arguments).status, "forbidden")
        definition = self.root.invoke_tool("list_tools", target_node_id="n2").items[0]
        self.assertEqual(definition["name"], "get_value")
        self.assertEqual(definition["parameters"]["properties"], {})
        result = self.root.invoke_tool("invoke_tool", **arguments)
        self.assertEqual(result.items, [{"value": 2}])
        self.assertEqual(result.sources[-1]["retrieval_path"], ["root", "n1", "n2"])
        self.assertIsNone(self.network.nodes["n2"].agent)

    def test_identical_names_are_distinguished_by_node(self):
        for node_id, expected in (("n1", 1), ("n2", 2)):
            self.root.invoke_tool("list_tools", target_node_id=node_id)
            result = self.root.invoke_tool("invoke_tool", target_node_id=node_id, tool_name="get_value", arguments={})
            self.assertEqual(result.items[0]["value"], expected)

    def test_scope_rechecked_after_discovery(self):
        self.assertEqual(self.root.invoke_tool("list_tools", target_node_id="n3").status, "forbidden")
        self.root.invoke_tool("list_tools", target_node_id="n3", scope="federated")
        args = {"target_node_id": "n3", "tool_name": "get_value", "arguments": {}}
        self.assertEqual(self.root.invoke_tool("invoke_tool", **args).status, "forbidden")
        self.assertEqual(self.root.invoke_tool("invoke_tool", **args, scope="federated").items[0]["value"], 3)
        self.root.strong_read_interfaces.clear()
        self.assertEqual(self.root.invoke_tool("invoke_tool", **args, scope="federated").status, "forbidden")

    def test_write_and_undeclared_tools_cannot_be_called(self):
        node = self.network.nodes["n2"]
        function = Mock()
        node.register_tool("write", function, description="写入", parameters={"type": "object"})
        node.tools["unregistered"] = function
        listed = self.root.invoke_tool("list_tools", target_node_id="n2")
        self.assertEqual([item["name"] for item in listed.items], ["get_value", "get_schema"])
        self.assertEqual(invoke_tool(self.network, "root", "n2", "write", {}).status, "forbidden")
        self.assertEqual(invoke_tool(self.network, "root", "n2", "unregistered", {}).status, "not_found")
        function.assert_not_called()

    def test_invalid_parameters_are_rejected_before_execution(self):
        node = self.network.nodes["n2"]
        function = Mock()
        node.register_tool("echo", function, description="读", read_only=True, parameters={
            "type": "object", "properties": {"text": {"type": "string"}},
            "required": ["text"], "additionalProperties": False})
        self.root.invoke_tool("list_tools", target_node_id="n2")
        for arguments in ({}, {"text": 1}, {"text": "ok", "extra": 1}):
            with self.assertRaises((ValueError, TypeError)):
                self.root.invoke_tool("invoke_tool", target_node_id="n2", tool_name="echo", arguments=arguments)
        function.assert_not_called()

    def test_owner_context_cannot_be_overridden(self):
        with self.assertRaises(TypeError):
            self.root.invoke_tool("list_nodes", node_id="n3")
        child = self.network.nodes["n5"]
        attach_discovery_tools(self.network, child)
        result = child.invoke_tool("list_nodes")
        self.assertEqual([i["node_id"] for i in result.items], ["n5", "n6"])

    def test_experiment_local_and_composite_tool_placement(self):
        network, root = build_lab_network()
        self.assertIn("analyze_project", root.tools)
        self.assertEqual(set(network.nodes["lab_records"].tools), {"get_record", "query_records", "get_schema"})
        self.assertEqual(set(network.nodes["lab_rules"].tools), {"get_record", "get_schema"})
        root.invoke_tool("list_tools", target_node_id="lab_rules")
        result = root.invoke_tool("invoke_tool", target_node_id="lab_rules", tool_name="get_record", arguments={"key": "A"})
        self.assertEqual(result.items[0]["project_id"], "A")
        self.assertEqual(result.sources[-1]["retrieval_path"], ["root", "lab_rules"])

    def test_agent_discovers_then_invokes_without_preloaded_child_tools(self):
        def call(name, args, ident):
            return {"id": ident, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        def reply(calls=None, content=None):
            return ChatCompletion(id="mock", object="chat.completion", created=0, model="mock", choices=[{
                "index": 0, "finish_reason": "tool_calls" if calls else "stop", "message": {
                "role": "assistant", "content": content, **({"tool_calls": calls} if calls else {})}}])
        client = Mock()
        client.chat.completions.create.side_effect = [
            reply([call("list_nodes", {}, "nodes")]),
            reply([call("list_tools", {"target_node_id": "n2"}, "tools")]),
            reply([call("invoke_tool", {"target_node_id": "n2", "tool_name": "get_value", "arguments": {}}, "invoke")]),
            reply(content="n2 的值为 2。"),
        ]
        _, root = build_agent_network(client, "mock")
        initial_names = {t["function"]["name"] for t in root.agent.tool_definitions}
        self.assertNotIn("get_value", initial_names)
        self.assertIn("2", root.invoke_agent("发现并调用 n2 的本地工具"))
        feedback = [m for m in root.agent.messages if m["role"] == "tool"]
        self.assertEqual(json.loads(feedback[1]["content"])["items"][0]["name"], "get_value")
        self.assertEqual(json.loads(feedback[2]["content"])["items"], [{"value": 2}])


if __name__ == "__main__":
    unittest.main()
