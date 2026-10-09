"""模拟模型响应，验证节点持有 Agent 与工具反馈；不请求 API。"""

import json
import unittest
import tempfile
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock

from openai.types.chat import ChatCompletion

from datanet.agent import Agent
from datanet.nodes.node import Node
from applications.experiment.agent_setup import build_agent_network


def reply(content="完成", calls=None, finish_reason=None):
    message = {"role": "assistant", "content": content}
    if calls is not None:
        message["tool_calls"] = calls
    return ChatCompletion(
        id="mock", object="chat.completion", created=0, model="mock",
        choices=[{"index": 0, "finish_reason": finish_reason or (
            "tool_calls" if calls else "stop"
        ), "message": message}],
    )


def tool_call(arguments='{"project_id": "B"}', name="analyze_project"):
    return {"id": "call_1", "type": "function", "function": {
        "name": name, "arguments": arguments,
    }}


class AgentTests(unittest.TestCase):
    def make_prompt(self, content):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "prompt.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_real_network_tool_feedback_and_final_history(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            reply(None, [tool_call()]), reply("B 的合格率已按工具结果计算。"),
        ]
        network, root = build_agent_network(client, "mock")
        result = root.invoke_agent("查询 B")
        self.assertIn("B", result)
        history = root.agent.messages
        feedback = json.loads(next(m["content"] for m in history if m["role"] == "tool"))
        expected = root.invoke_tool("analyze_project", project_id="B")
        self.assertEqual(feedback["pass_rate"], expected["pass_rate"])
        self.assertEqual(feedback["sources"]["records"][0]["retrieval_path"], ["root", "lab_records"])
        self.assertEqual(history[-1]["role"], "assistant")
        self.assertIsNone(network.nodes["lab_records"].agent)

    def test_missing_agent_fails_before_request(self):
        root = Node("root", "入口", None)
        with self.assertRaisesRegex(RuntimeError, "尚未配置"):
            root.invoke_agent("你好")

    def make_empty_agent(self, responses, max_rounds=5):
        client = Mock()
        client.chat.completions.create.side_effect = responses
        node = Node("root", "入口", None)
        node.agent = Agent(client, "mock", self.make_prompt("系统提示"), [], max_rounds=max_rounds)
        return client, node

    def test_detach_and_reattach_agent(self):
        client, node = self.make_empty_agent([reply("一"), reply("二")])
        agent = node.agent
        self.assertTrue(node.describe()["has_agent"])
        node.invoke_agent("第一问")
        node.agent = None
        self.assertFalse(node.describe()["has_agent"])
        with self.assertRaisesRegex(RuntimeError, "尚未配置"):
            node.invoke_agent("不能调用")
        self.assertEqual(client.chat.completions.create.call_count, 1)
        node.agent = agent
        self.assertEqual(node.invoke_agent("第二问"), "二")
        self.assertEqual(len(agent.messages), 5)

    def test_agent_rejects_unbound_node(self):
        client, node = self.make_empty_agent([])
        other = Node("other", "其他节点", None)
        with self.assertRaisesRegex(RuntimeError, "绑定到当前节点"):
            node.agent.run("你好", node=other)
        client.chat.completions.create.assert_not_called()

    def test_restart_reloads_file_replaces_instance_and_clears_history(self):
        client, node = self.make_empty_agent([reply("完成")])
        previous = node.agent
        node.invoke_agent("第一问")
        previous.prompt_path.write_text("新的职责", encoding="utf-8")
        node.tools["local"] = lambda: 1
        interfaces = node.strong_read_interfaces
        node.restart_agent()
        self.assertIsNot(node.agent, previous)
        self.assertIs(node.agent.client, client)
        self.assertEqual(node.agent.messages, [{"role": "system", "content": "新的职责"}])
        self.assertEqual(previous.system_prompt, "系统提示")
        self.assertIn("local", node.tools)
        self.assertIs(node.strong_read_interfaces, interfaces)
        self.assertEqual(node.agent.max_rounds, previous.max_rounds)

    def test_restart_failure_keeps_old_instance_and_history(self):
        _, node = self.make_empty_agent([reply("完成")])
        node.invoke_agent("问题")
        previous = node.agent
        for content in ("", "  \n"):
            previous.prompt_path.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                node.restart_agent()
            self.assertIs(node.agent, previous)
            self.assertEqual(len(node.agent.messages), 3)
        previous.prompt_path.unlink()
        with self.assertRaises(FileNotFoundError):
            node.restart_agent()
        self.assertIs(node.agent, previous)

    def test_restart_missing_agent_and_self_restart_fail(self):
        with self.assertRaisesRegex(RuntimeError, "尚未配置"):
            Node("empty", "空", None).restart_agent()
        client, node = self.make_empty_agent([])
        client.chat.completions.create.side_effect = lambda **kwargs: node.restart_agent()
        with self.assertRaisesRegex(RuntimeError, "自身任务"):
            node.invoke_agent("问题")
        self.assertIsNone(node.agent._running_thread)

    def test_restart_waits_for_running_task(self):
        client, node = self.make_empty_agent([])
        previous = node.agent
        entered, release, restarting, done = Event(), Event(), Event(), Event()
        errors = []
        def response(**kwargs):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("测试任务等待超时")
            return reply("旧任务完成")
        def run():
            try:
                node.invoke_agent("正在执行")
            except Exception as error:
                errors.append(error)
        def restart():
            restarting.set()
            try:
                node.restart_agent()
            except Exception as error:
                errors.append(error)
            finally:
                done.set()
        client.chat.completions.create.side_effect = response
        task = Thread(target=run)
        worker = Thread(target=restart)
        task.start()
        try:
            self.assertTrue(entered.wait(2))
            previous.prompt_path.write_text("重启后的职责", encoding="utf-8")
            worker.start()
            self.assertTrue(restarting.wait(2))
            self.assertFalse(done.wait(0.05))
            self.assertIs(node.agent, previous)
        finally:
            release.set()
            task.join(3)
            if worker.ident is not None:
                worker.join(3)
        self.assertFalse(task.is_alive())
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(previous.messages[-1]["content"], "旧任务完成")
        self.assertEqual(node.agent.messages, [{"role": "system", "content": "重启后的职责"}])

    def test_history_persists_and_reset_is_local(self):
        _, node = self.make_empty_agent([reply("一"), reply("二")])
        node.invoke_agent("第一问")
        node.invoke_agent("第二问")
        self.assertEqual(len(node.agent.messages), 5)
        other = Agent(Mock(), "mock", self.make_prompt("另一个提示"), [])
        node.agent.reset()
        self.assertEqual(len(node.agent.messages), 1)
        self.assertEqual(other.messages[0]["content"], "另一个提示")

    def test_empty_and_truncated_replies_do_not_commit_history(self):
        for response in (reply(""), reply("部分回答", finish_reason="length")):
            with self.subTest(response=response):
                _, node = self.make_empty_agent([response])
                with self.assertRaises(RuntimeError):
                    node.invoke_agent("问题")
                self.assertEqual(len(node.agent.messages), 1)

    def test_bad_arguments_return_tool_error(self):
        client = Mock()
        client.chat.completions.create.side_effect = [
            reply(None, [tool_call("[]")]), reply("参数错误"),
        ]
        _, root = build_agent_network(client, "mock")
        root.invoke_agent("查询")
        feedback = json.loads(next(m["content"] for m in root.agent.messages if m["role"] == "tool"))
        self.assertIn("error", feedback)

    def test_unregistered_definition_fails_before_request(self):
        client = Mock()
        _, root = build_agent_network(client, "mock")
        root.tools.clear()
        with self.assertRaisesRegex(ValueError, "未在节点注册"):
            root.invoke_agent("查询")
        client.chat.completions.create.assert_not_called()

    def test_round_limit(self):
        client = Mock()
        client.chat.completions.create.return_value = reply(None, [tool_call()])
        _, root = build_agent_network(client, "mock")
        root.agent.max_rounds = 1
        with self.assertRaisesRegex(RuntimeError, "达到 1 轮"):
            root.invoke_agent("查询")
        self.assertEqual(len(root.agent.messages), 1)


if __name__ == "__main__":
    unittest.main()
