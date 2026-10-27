"""Agent 节点继承、记忆策略和本节点工具行为。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from domain.agent import AgentNode, MarkdownAgentNode
from domain.agent.memory import EmptyMemoryStrategy, MarkdownMemoryStrategy
from domain.core import CallableTool, DataNode, Link, MarkdownNode, Network, Node, NodeInfo


class AgentNodeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.agent-node-', dir=Path(__file__).resolve().parents[1] / 'build')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.path = self.directory / 'memory.md'
        self.original = '# 记忆\r\n\r\n喜欢: 茶\r\n工作: 软件开发\r\n'
        self.path.write_bytes(self.original.encode('utf-8'))
        self.node = MarkdownAgentNode(NodeInfo('agent', 'Agent'), self.path, save_data=False)
        self.network = Network([self.node])

    def tools(self):
        return {tool.name: tool for tool in self.node.available_tools()['agent']}

    def test_markdown_agent_inherits_data_node_and_has_agent_type(self):
        self.assertIsInstance(self.node, AgentNode)
        self.assertIsInstance(self.node, MarkdownNode)
        self.assertIsInstance(self.node, DataNode)
        self.assertEqual(self.node.node_type, 'agent')
        self.assertEqual(list(self.node.modules), [])
        self.assertIsInstance(self.node.memory_strategy, MarkdownMemoryStrategy)
        self.assertIsNone(self.node.auto_memory)
        self.assertEqual(set(self.tools()), {'memory_query', 'memory_modify', 'memory_append'})

    def test_query_supports_full_text_and_matching_lines(self):
        query = self.tools()['memory_query']
        self.assertEqual(query.invoke(), {'agent': self.original})
        self.assertEqual(query.invoke(query='茶'), {'agent': '喜欢: 茶\r\n'})
        self.assertEqual(query.invoke(query='不存在'), {'agent': ''})

    def test_modify_replaces_only_selected_fragment(self):
        modify = self.tools()['memory_modify']
        self.assertEqual(modify.invoke(old_text='喜欢: 茶', new_text='喜欢: 咖啡'), {'agent': 1})
        self.assertEqual(self.path.read_bytes().decode('utf-8'), self.original.replace('喜欢: 茶', '喜欢: 咖啡'))
        self.assertEqual(modify.invoke(old_text='喜欢: 咖啡', new_text=''), {'agent': 1})
        self.assertNotIn('喜欢:', self.node.dataer.read())

    def test_modify_rejects_missing_empty_or_ambiguous_fragment(self):
        modify = self.tools()['memory_modify']
        for content, old_text in [(self.original, ''), (self.original, '不存在'), ('重复 重复', '重复')]:
            self.path.write_bytes(content.encode('utf-8'))
            before = self.path.read_bytes()
            with self.subTest(old_text=old_text), self.assertRaises(ValueError):
                modify.invoke(old_text=old_text, new_text='修改')
            self.assertEqual(self.path.read_bytes(), before)

    def test_append_does_not_read_or_return_full_memory(self):
        with patch.object(self.node.dataer, 'read', side_effect=AssertionError('不读取全文')):
            self.assertEqual(self.tools()['memory_append'].invoke(content='新增'), {'agent': 2})
        self.assertEqual(self.path.read_bytes(), (self.original + '新增').encode('utf-8'))

    def test_invalid_append_does_not_change_file(self):
        before = self.path.read_bytes()
        with self.assertRaises(TypeError):
            self.tools()['memory_append'].invoke(content=None)
        self.assertEqual(self.path.read_bytes(), before)

    def test_memory_tools_read_current_local_dataer(self):
        with patch.object(self.node.dataer, 'query', return_value='当前访问器') as query:
            self.assertEqual(self.tools()['memory_query'].invoke(query='关键字'), {'agent': '当前访问器'})
        query.assert_called_once_with('关键字')

    def test_unmatched_agent_uses_empty_strategy(self):
        node = AgentNode(NodeInfo('empty', '无数据 Agent'))
        self.assertIsInstance(node, Node)
        self.assertNotIsInstance(node, DataNode)
        self.assertEqual(node.node_type, 'agent')
        self.assertIsInstance(node.memory_strategy, EmptyMemoryStrategy)
        self.assertIsNone(node.auto_memory)
        self.assertEqual(list(node.tools), [])
        action = CallableTool('action', lambda: 'ok')
        node.install(action)
        self.assertEqual(list(node.available_tools()['empty']), [action])

    def test_other_data_node_can_be_an_agent_with_empty_strategy(self):
        class OtherDataAgent(AgentNode, DataNode):
            pass
        node = OtherDataAgent(NodeInfo('other', '其他数据 Agent'), dataer=self.node.dataer, saver=self.node.saver)
        self.assertIsInstance(node, DataNode)
        self.assertEqual(node.node_type, 'agent')
        self.assertIsInstance(node.memory_strategy, EmptyMemoryStrategy)

    def test_markdown_subclass_keeps_markdown_memory_strategy(self):
        class CustomMarkdown(MarkdownNode):
            pass
        class CustomAgent(AgentNode, CustomMarkdown):
            pass
        node = CustomAgent(NodeInfo('custom', '自定义'), self.path)
        self.assertEqual(node.node_type, 'agent')
        self.assertIsInstance(node.memory_strategy, MarkdownMemoryStrategy)

    def test_memory_tools_only_operate_on_own_node(self):
        path = self.directory / 'other.md'
        path.write_text('远端记忆', encoding='utf-8')
        other = MarkdownAgentNode(NodeInfo('other', 'Other'), path)
        self.network.add(other)
        self.node.links.add(Link('other'))
        self.assertEqual(self.tools()['memory_append'].invoke(content='新增'), {'agent': 2})
        self.assertEqual(path.read_text(encoding='utf-8'), '远端记忆')

    def test_runner_receives_local_tools_and_new_input(self):
        calls = []
        self.node.runner = lambda message, tools: calls.append((message, [t.name for t in tools])) or 'done'
        self.assertEqual(self.node.run('新输入'), 'done')
        self.assertEqual(calls, [('新输入', ['memory_query', 'memory_modify', 'memory_append'])])

    def test_runner_is_not_connected_by_default(self):
        with self.assertRaises(NotImplementedError):
            self.node.run('新输入')
