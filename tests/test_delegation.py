"""配置持久化、父子任务隔离、许可/循环/预算与装配保护。"""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

from openai.types.chat import ChatCompletion
from datanet.serialization import load_network, save_network
from datanet.agent.configuration import assemble_agents
from datanet.agent.delegation import call_chain, request_budget, MAX_DEPTH, MAX_DELEGATIONS
from datanet.nodes.local_tools import attach_local_tools
from applications.multi_agent.setup import CONFIG_PATH, build_agent_network


def call(name, args, ident="call"):
    return {"id": ident, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def reply(content=None, calls=None):
    return ChatCompletion(id="mock", object="chat.completion", created=0, model="mock", choices=[{
        "index": 0, "finish_reason": "tool_calls" if calls else "stop", "message": {
            "role": "assistant", "content": content, **({"tool_calls": calls} if calls else {})}}])


class DelegationTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.network, self.root = build_agent_network(self.client, "mock")
        self.worker = self.network.nodes["worker"]
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)

    def ask(self):
        return self.root.invoke_tool("ask_agent", target_node_id="worker", message="读取数字")

    def test_parent_child_tools_and_reply_with_isolated_history(self):
        self.client.chat.completions.create.side_effect = [
            reply(calls=[call("ask_agent", {"target_node_id": "worker", "message": "读取数字"})]),
            reply(calls=[call("get_value", {})]), reply("worker 的数字是 42。"), reply("子节点返回 42。"),
        ]
        original = deepcopy(self.worker.agent.messages)
        self.assertIn("42", self.root.invoke_agent("请委托 worker"))
        self.assertEqual(self.worker.agent.messages, original)
        feedback = json.loads(next(m["content"] for m in self.root.agent.messages if m["role"] == "tool"))
        self.assertEqual(feedback["status"], "ok")
        self.assertEqual(feedback["sources"][0]["call_chain"], ["root", "worker"])
        requests = self.client.chat.completions.create.call_args_list
        self.assertIn("worker Agent", requests[1].kwargs["messages"][0]["content"])
        self.assertNotIn("root 协调", requests[1].kwargs["messages"][0]["content"])

    def test_separate_requests_do_not_share_child_task_context(self):
        self.client.chat.completions.create.side_effect = [reply("第一次"), reply("第二次")]
        self.assertEqual(self.ask().status, "ok")
        self.assertEqual(self.ask().status, "ok")
        requests = self.client.chat.completions.create.call_args_list
        self.assertEqual(len(requests[0].kwargs["messages"]), 2)
        self.assertEqual(len(requests[1].kwargs["messages"]), 2)
        self.assertEqual(len(self.worker.agent.messages), 1)

    def test_delegation_does_not_send_existing_child_history(self):
        self.worker.agent.messages.extend([
            {"role": "user", "content": "原会话私密上下文"},
            {"role": "assistant", "content": "原会话回复"},
        ])
        previous = deepcopy(self.worker.agent.messages)
        self.client.chat.completions.create.return_value = reply("独立任务回复")
        self.assertEqual(self.ask().status, "ok")
        sent = self.client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(len(sent), 2)
        self.assertNotIn("原会话", json.dumps(sent, ensure_ascii=False))
        self.assertEqual(self.worker.agent.messages, previous)

    def test_permission_and_reachability_are_both_required(self):
        self.network.delegation_permissions.clear()
        self.assertEqual(self.ask().status, "forbidden")
        self.network.delegation_permissions = {"root": ["worker"]}
        self.root.strong_read_interfaces.clear()
        self.assertEqual(self.ask().status, "forbidden")
        self.client.chat.completions.create.assert_not_called()

    def test_missing_agent_is_reported(self):
        self.worker.agent = None
        self.assertEqual(self.ask().status, "not_found")
        self.client.chat.completions.create.assert_not_called()

    def test_cycle_is_rejected_before_locking_parent(self):
        self.network.delegation_permissions["worker"] = ["root"]
        self.worker.strong_read_interfaces.append(self.root.interface)
        self.client.chat.completions.create.side_effect = [
            reply(calls=[call("ask_agent", {"target_node_id": "worker", "message": "任务"})]),
            reply(calls=[call("ask_agent", {"target_node_id": "root", "message": "循环"})]),
            reply("已拒绝循环"), reply("任务结束"),
        ]
        self.root.invoke_agent("任务")
        child_feedback = self.client.chat.completions.create.call_args_list[2].kwargs["messages"][-1]
        result = json.loads(child_feedback["content"])
        self.assertEqual(result["status"], "error")
        self.assertIn("循环", result["errors"][0])

    def test_depth_limit(self):
        token = call_chain.set(tuple([f"ancestor{i}" for i in range(MAX_DEPTH - 1)] + ["root"]))
        try:
            result = self.ask()
            self.assertIn("深度", result.errors[0])
        finally:
            call_chain.reset(token)
        self.client.chat.completions.create.assert_not_called()

    def test_request_budget_limit(self):
        token = request_budget.set({"calls": MAX_DELEGATIONS})
        try:
            result = self.ask()
            self.assertIn("次数", result.errors[0])
        finally:
            request_budget.reset(token)
        self.client.chat.completions.create.assert_not_called()

    def test_busy_target_returns_without_waiting(self):
        self.worker.agent._lifecycle_lock.acquire()
        try:
            result = self.ask()
            self.assertEqual(result.status, "error")
            self.assertIn("正忙", result.errors[0])
        finally:
            self.worker.agent._lifecycle_lock.release()
        self.client.chat.completions.create.assert_not_called()

    def test_child_failure_returns_error_and_cleans_context(self):
        self.client.chat.completions.create.side_effect = RuntimeError("子任务失败")
        self.assertEqual(self.ask().status, "error")
        self.assertEqual(call_chain.get(), ())
        self.assertIsNone(request_budget.get())
        self.assertEqual(len(self.worker.agent.messages), 1)

    def test_v2_roundtrip_preserves_config_permissions_and_excludes_history(self):
        path = self.base / "network.json"
        save_network(self.network, path)
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["version"], 2)
        self.assertEqual(document["delegations"], [{"source": "root", "target": "worker"}])
        self.assertNotIn("api_key", path.read_text(encoding="utf-8"))
        restored = load_network(path)
        self.assertIsNone(restored.nodes["root"].agent)
        self.assertEqual(restored.nodes["worker"].agent_config["model"], "mock")
        for node in restored.nodes.values():
            attach_local_tools(node)
        assemble_agents(restored, self.client)
        self.assertEqual(len(restored.nodes["worker"].agent.messages), 1)
        self.assertIn("worker Agent", restored.nodes["worker"].agent.system_prompt)

    def test_invalid_config_permission_and_secret_field_rejected(self):
        original = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        mutations = (
            lambda d: d["nodes"][0]["agent"].update(api_key="never-save"),
            lambda d: d["nodes"][0]["agent"].update(max_rounds=True),
            lambda d: d["delegations"].append({"source": "root", "target": "missing"}),
            lambda d: d["delegations"].append(d["delegations"][0]),
        )
        for mutate in mutations:
            document = deepcopy(original)
            mutate(document)
            path = self.base / "invalid.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_network(path)

    def test_assembly_failure_does_not_replace_existing_agents(self):
        previous_root, previous_worker = self.root.agent, self.worker.agent
        self.worker.agent_config["prompt_path"] = str(self.base / "missing.md")
        with self.assertRaises(FileNotFoundError):
            assemble_agents(self.network, self.client)
        self.assertIs(self.root.agent, previous_root)
        self.assertIs(self.worker.agent, previous_worker)

    def test_v1_remains_loadable_without_agents(self):
        document = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        document["version"] = 1
        document.pop("delegations")
        for node in document["nodes"]:
            node.pop("agent")
        path = self.base / "legacy.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        network = load_network(path)
        self.assertFalse(network.delegation_permissions)
        self.assertTrue(all(node.agent_config is None for node in network.nodes.values()))


if __name__ == "__main__":
    unittest.main()
