"""Agent 类型在收集边界隔离工具和 Markdown 记忆，并保留本节点能力。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from app.network_saver import NetworkSaver
from domain.agent import AgentNode, MarkdownAgentNode
from domain.core import CallableTool, Link, MarkdownNode, Network, Node, NodeInfo
from modules.context_assembler import ContextAssemblerModule
from modules.tool_discovery import ToolDiscoveryModule


class AgentVisibilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.agent-visibility-', dir=Path(__file__).resolve().parents[1] / 'build')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def markdown(self, key, text, *, agent=False):
        path = self.folder / (key + '.md')
        path.write_text(text, encoding='utf-8')
        node_type = MarkdownAgentNode if agent else MarkdownNode
        return node_type(NodeInfo(key, key), path, save_data=False)

    async def test_discovery_excludes_agent_tools_and_does_not_invoke_its_relay(self):
        root = self.markdown('root', '我的记忆', agent=True)
        other = self.markdown('other', '别人的记忆', agent=True)
        public = Node(NodeInfo('public', 'Public'))
        hidden = Node(NodeInfo('hidden', 'Hidden'))
        public.install(CallableTool('public_tool', lambda: 42))
        hidden.install(CallableTool('hidden_tool', lambda: 'hidden'))
        other.install(CallableTool('other_agent_tool', lambda: 'other'))
        root.links.add(Link('other', 'tools'))
        other.links.add(Link('public', 'tools'))
        other.links.add(Link('hidden', 'secret'))
        network = Network([root, other, public, hidden])
        discovery = ToolDiscoveryModule('tools', 2)
        relay = ToolDiscoveryModule('secret', 10)
        root.install(discovery)
        other.install(relay)
        with patch.object(relay, 'discover', side_effect=AssertionError('不调用其他 Agent 的发现器')):
            with patch.object(relay, '_discover', side_effect=AssertionError('不串联其他 Agent')):
                found = discovery.discover()
                self.assertEqual([tool.name for tool in found], ['public_tool'])
                own = list(root.available_tools()['root'])
        self.assertEqual([tool.name for tool in own], ['memory_query', 'memory_modify', 'memory_append', 'public_tool'])
        self.assertEqual(next(tool for tool in own if tool.name == 'memory_query').invoke(), {'root': '我的记忆'})
        self.assertEqual(next(tool for tool in own if tool.name == 'public_tool').invoke(), 42)
        self.assertEqual(len(network), 4)

    async def test_plain_discovery_also_skips_an_empty_memory_agent(self):
        root = Node(NodeInfo('root', 'root'))
        other = AgentNode(NodeInfo('other', 'other'))
        other.install(CallableTool('private', lambda: 'private'))
        root.links.add(Link('other', 'tools'))
        network = Network([root, other])
        discovery = ToolDiscoveryModule('tools', 1)
        root.install(discovery)
        self.assertEqual(list(discovery.discover()), [])
        self.assertEqual(list(other.available_tools()['other'])[0].name, 'private')

    async def test_context_only_reads_markdown_type_and_ignores_agent_memory(self):
        root = self.markdown('root', '我的记忆', agent=True)
        other = self.markdown('other', '别人的记忆', agent=True)
        document = self.markdown('document', '共享文档')
        root.links.add(Link('other', 'context.assembler.context'))
        other.links.add(Link('document', 'context.assembler.context'))
        network = Network([root, other, document])
        assembler = ContextAssemblerModule(strength=2)
        root.install(assembler)
        self.assertIsInstance(other, MarkdownNode)
        self.assertEqual(other.node_type, 'agent')
        with patch.object(root.dataer, 'read', side_effect=AssertionError('不读取本 Agent 记忆')):
            with patch.object(other.dataer, 'read', side_effect=AssertionError('不读取其他 Agent 记忆')):
                packet = await assembler.assemble()
        self.assertEqual(packet['patch']['context'], [{'id': 'node:document', 'text': '共享文档'}])
        self.assertEqual(packet['errors'], [])
        self.assertEqual([source['source'] for source in packet['sources']], ['document'])

    async def test_markdown_agent_save_load_keeps_agent_type_memory_and_inputs(self):
        node = self.markdown('actor', '记忆', agent=True)
        node.save_data = True
        node.update_inputs('host', inputs=[dict(id='done', text='已完成'), dict(id='pending', text='待完成')])
        node.inputs.acknowledge('host', 'done')
        path = self.folder / 'network.json'
        saver = NetworkSaver()
        saver.save(Network([node]), path)
        record = json.loads(path.read_text(encoding='utf-8'))['nodes'][0]
        self.assertEqual(record['type'], 'agent')
        self.assertEqual(record['data']['type'], 'markdown')
        loaded = saver.load(path).get('actor')
        self.assertIsInstance(loaded, MarkdownAgentNode)
        self.assertEqual(loaded.node_type, 'agent')
        self.assertEqual(loaded.dataer.read(), '记忆')
        self.assertNotEqual(loaded.saver.path, node.saver.path)
        self.assertEqual(loaded.inputs.snapshot(), node.inputs.snapshot())
        self.assertEqual([event['id'] for _, event in loaded.inputs.pending()], ['pending'])
        self.assertEqual(next(iter(loaded.tools)).invoke(), {'actor': '记忆'})

    async def test_empty_memory_agent_save_load(self):
        node = AgentNode(NodeInfo('empty', 'Empty'))
        node.update_inputs('host', system_prompt='规则')
        path = self.folder / 'empty.json'
        saver = NetworkSaver()
        saver.save(Network([node]), path)
        loaded = saver.load(path).get('empty')
        self.assertIs(type(loaded), AgentNode)
        self.assertEqual(loaded.node_type, 'agent')
        self.assertEqual(loaded.inputs.snapshot(), node.inputs.snapshot())
        self.assertEqual(list(loaded.tools), [])
