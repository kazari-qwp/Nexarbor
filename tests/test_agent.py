"""模拟模型响应，验证节点持有 Agent 与工具反馈；不请求 API。"""

import json
import unittest
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
        self.assertFalse(network.nodes["lab_records"].agent_enabled)

    def test_disabled_and_missing_agent_fail_before_request(self):
        root = Node("root", "入口", None)
        with self.assertRaisesRegex(RuntimeError, "未开启"):
            root.invoke_agent("你好")
        root.set_agent_enabled(True)
        with self.assertRaisesRegex(RuntimeError, "尚未配置"):
            root.invoke_agent("你好")

    def make_empty_agent(self, responses, max_rounds=5):
        client = Mock()
        client.chat.completions.create.side_effect = responses
        node = Node("root", "入口", None)
        node.agent = Agent(client, "mock", "系统提示", [], max_rounds=max_rounds)
        node.set_agent_enabled(True)
        return client, node

    def test_history_persists_and_reset_is_local(self):
        _, node = self.make_empty_agent([reply("一"), reply("二")])
        node.invoke_agent("第一问")
        node.invoke_agent("第二问")
        self.assertEqual(len(node.agent.messages), 5)
        other = Agent(Mock(), "mock", "另一个提示", [])
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
