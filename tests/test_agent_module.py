"""Agent 装配、记忆策略和 Markdown 文件操作的集成验证。"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from modules.agent import AgentModule
from domain.core import DataNode
from domain.core import DependencyError
from domain.core import MarkdownNode
from modules.agent.memory import EmptyMemoryStrategy, MarkdownMemoryStrategy
from domain.core import Network
from domain.core import Node
from domain.core import NodeInfo
from domain.core import CallableTool


class AgentModuleTests(unittest.TestCase):
    def setUp(self):
        project = Path(__file__).resolve().parents[1]
        temporary = TemporaryDirectory(prefix='.agent-test-', dir=project)
        self.directory = Path(temporary.name).resolve()
        if not self.directory.is_relative_to(project):
            raise RuntimeError('测试临时目录不在项目内')
        self.addCleanup(temporary.cleanup)
        self.path = self.directory / 'memory.md'
        self.original = '# 记忆\r\n\r\n喜欢: 茶\r\n工作: 软件开发\r\n'
        self.path.write_bytes(self.original.encode('utf-8'))
        self.node = MarkdownNode(NodeInfo('agent_node', '带记忆的节点'), self.path, save_data=False)
        self.network = Network([self.node])
        self.agent = AgentModule()

    def install_agent(self):
        self.node.install(self.agent)
        return {tool.name: tool for tool in self.agent.available_tools()['agent_node']}

    def test_agent_binds_memory_when_installed_and_uses_access(self):
        tools = self.install_agent()
        self.assertEqual(list(self.node.modules), [self.agent])
        self.assertEqual(set(tools), {'memory_query', 'memory_modify', 'memory_append'})
        self.assertIs(self.agent.available_tools()['agent_node'], self.node.tools)
        self.assertIsInstance(self.agent.memory_strategy, MarkdownMemoryStrategy)
        self.assertIsNone(self.agent.auto_memory)

    def test_query_supports_full_text_and_matching_lines(self):
        query = self.install_agent()['memory_query']
        self.assertEqual(query.invoke(), {'agent_node': self.original})
        self.assertEqual(query.invoke(query='茶'), {'agent_node': '喜欢: 茶\r\n'})
        self.assertEqual(query.invoke(query='不存在的内容'), {'agent_node': ''})

    def test_modify_replaces_only_the_selected_fragment(self):
        modify = self.install_agent()['memory_modify']
        self.assertEqual(modify.invoke(old_text='喜欢: 茶', new_text='喜欢: 咖啡'), {'agent_node': 1})
        expected = self.original.replace('喜欢: 茶', '喜欢: 咖啡')
        self.assertEqual(self.path.read_bytes().decode('utf-8'), expected)
        self.assertEqual(modify.invoke(old_text='喜欢: 咖啡', new_text=''), {'agent_node': 1})
        self.assertNotIn('喜欢:', self.node.dataer.read())

    def test_modify_rejects_missing_empty_or_ambiguous_text_without_writing(self):
        modify = self.install_agent()['memory_modify']
        cases = [(self.original, ''), (self.original, '不存在'), ('重复 重复', '重复')]
        for content, old_text in cases:
            self.path.write_bytes(content.encode('utf-8'))
            before = self.path.read_bytes()
            with self.subTest(old_text=old_text):
                with self.assertRaises(ValueError):
                    modify.invoke(old_text=old_text, new_text='修改')
                self.assertEqual(self.path.read_bytes(), before)

    def test_append_does_not_read_or_return_the_whole_memory(self):
        append = self.install_agent()['memory_append']
        content = '新增: 学习 Python'
        with patch.object(self.node.dataer, 'read', side_effect=AssertionError('must not read full memory')):
            result = append.invoke(content=content)
        self.assertEqual(result, {'agent_node': len(content)})
        self.assertIsInstance(result['agent_node'], int)
        self.assertEqual(self.path.read_bytes(), (self.original + content).encode('utf-8'))

    def test_invalid_append_does_not_change_the_file(self):
        append = self.install_agent()['memory_append']
        before = self.path.read_bytes()
        with self.assertRaises(TypeError):
            append.invoke(content=None)
        self.assertEqual(self.path.read_bytes(), before)

    def test_memory_tools_resolve_local_dataer_through_access_when_invoked(self):
        tools = self.install_agent()
        with patch.object(self.node.dataer, 'query', return_value='当前访问器') as query:
            self.assertEqual(tools['memory_query'].invoke(query='关键字'), {'agent_node': '当前访问器'})
        query.assert_called_once_with('关键字')

    def test_removing_agent_removes_its_memory_tools(self):
        self.install_agent()
        self.assertTrue(self.node.remove(self.agent))
        self.assertEqual(list(self.node.modules), [])
        self.assertEqual(list(self.node.tools), [])
        with self.assertRaisesRegex(RuntimeError, '尚未绑定节点'):
            self.agent.available_tools()

    def test_installing_a_memory_tool_also_installs_its_agent(self):
        append = self.install_agent()['memory_append']
        self.node.remove(self.agent)
        self.node.install(append)
        self.assertEqual(list(self.node.modules), [self.agent])
        with self.assertRaises(DependencyError):
            self.node.remove(self.agent)
        self.assertTrue(self.node.remove(append))
        self.assertTrue(self.node.remove(self.agent))

    def test_markdown_subclasses_reuse_the_markdown_strategy(self):
        class CustomMarkdownNode(MarkdownNode):
            pass

        node = CustomMarkdownNode(NodeInfo('custom', 'Markdown 子类'), self.path)
        self.network.add(node)
        agent = AgentModule()
        node.install(agent)
        self.assertIsInstance(agent.memory_strategy, MarkdownMemoryStrategy)

    def test_every_unmatched_node_type_uses_empty_memory(self):
        nodes = [
            Node(NodeInfo('plain', '普通节点')),
            DataNode(NodeInfo('other', '其他数据节点'), dataer=self.node.dataer, saver=self.node.saver),
        ]
        for node in nodes:
            with self.subTest(node_type=type(node).__name__):
                self.network.add(node)
                agent = AgentModule()
                node.install(agent)
                self.assertIsInstance(agent.memory_strategy, EmptyMemoryStrategy)
                self.assertIsNone(agent.auto_memory)
                self.assertEqual(list(agent.tools), [])
                self.assertEqual(list(node.modules), [agent])
                action = CallableTool('action', lambda: 'ok')
                node.install(action)
                self.assertEqual(list(agent.available_tools()[node.info.node_id]), [action])

    def test_agent_memory_tools_only_operate_on_the_local_node(self):
        from domain.core import Link

        other_path = self.directory / 'other.md'
        other_path.write_text('远端记忆', encoding='utf-8')
        other = MarkdownNode(NodeInfo('other', '其他节点'), other_path, save_data=False)
        self.network.add(other)
        self.node.links.add(Link('other'))
        self.agent.channels = 'default'
        self.agent.strength = 2
        tools = self.install_agent()
        self.assertEqual(tools['memory_append'].invoke(content='新增'), {'agent_node': 2})
        self.assertEqual(other_path.read_text(encoding='utf-8'), '远端记忆')

    def test_failed_agent_installation_unbinds_and_can_be_retried(self):
        conflict = CallableTool('memory_query', lambda: 'conflict')
        self.node.install(conflict)
        with self.assertRaisesRegex(ValueError, '工具名称冲突'):
            self.node.install(self.agent)
        self.assertEqual(list(self.node.modules), [])
        self.assertEqual(list(self.node.tools), [conflict])
        with self.assertRaisesRegex(RuntimeError, '尚未绑定节点'):
            self.agent.available_tools()
        self.node.remove(conflict)
        self.install_agent()

    def test_model_execution_is_explicitly_not_connected(self):
        self.node.install(self.agent)
        with self.assertRaises(NotImplementedError):
            self.agent.run('新输入')


if __name__ == '__main__':
    unittest.main()
