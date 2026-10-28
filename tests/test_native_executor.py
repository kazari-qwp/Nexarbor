"""原执行器输入/工具/会话协议接入新核心；不代替三应用验收。"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from adapt.harness.executor import NativeExecutor
from app.runtime.async_runtime import AsyncRuntime
from app.runtime.context_packets import apply_context_packet
from domain.core import CallableTool, Link, MarkdownNode, Network, Node, NodeInfo
from domain.agent import AgentNode, MarkdownAgentNode
from modules.context_assembler import ContextAssemblerModule, DEFAULT_CHANNELS
from modules.tool_discovery import ToolDiscoveryModule


class NativeExecutorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.native-executor-', dir=Path(__file__).resolve().parents[1] / 'build')
        self.addCleanup(self.temporary.cleanup)
        file = Path(self.temporary.name) / 'memory.md'
        file.write_text('记忆正文', encoding='utf-8')
        self.node = MarkdownAgentNode(NodeInfo('actor', 'A'), file)
        self.agent = self.node
        self.discovery = ToolDiscoveryModule('tools', 2)
        self.node.install(self.discovery)
        self.network = Network([self.node])
        self.binding = dict(executor='harness', strength=2, channels=['tools', *DEFAULT_CHANNELS], prepare=[])
        self.executor = NativeExecutor(self.network, None, bindings={'actor': self.binding})
        self.parameters = dict(actor='actor')

    async def test_each_prepare_refreshes_discovery_after_location_or_edge_changes(self):
        before = Node(NodeInfo('before','Before'))
        after = Node(NodeInfo('after','After'))
        calls = []
        before.install(CallableTool('old_place',lambda:calls.append('old')))
        after.install(CallableTool('new_place',lambda:calls.append('new')))
        self.network.add(before);self.network.add(after)
        edge = Link('before','tools');self.node.links.add(edge)
        first = await self.executor.prepare(self.parameters)
        self.assertIn('old_place',{tool['name'] for tool in first['tools']})
        self.node.links.remove(edge);self.node.links.add(Link('after','tools'))
        second = await self.executor.prepare(self.parameters)
        self.assertIn('new_place',{tool['name'] for tool in second['tools']})
        self.assertNotIn('old_place',{tool['name'] for tool in second['tools']})
        self.assertIn('old_place',second['unavailable'])
        forbidden = await self.executor.invoke(dict(actor='actor',name='old_place'))
        self.assertEqual(forbidden['status'],'forbidden')
        await self.executor.invoke(dict(actor='actor',name='new_place'))
        self.assertEqual(calls,['new'])

    def mount_context(self, node=None):
        node = self.node if node is None else node
        module = ContextAssemblerModule({'sources': [
            dict(id='rule', kind='system_prompt', type='text', text='规则'),
            dict(id='doc', kind='context', type='text', text='资料'),
            dict(id='event', kind='inputs', type='text', text='一次事件', event_id='opening'),
            dict(id='clock', kind='tail', type='text', text='当前时刻'),
        ]})
        node.install(module)
        self.binding['prepare'] = [dict(node=node.info.node_id, module='context.assembler', operation='assemble')]
        return module

    async def test_preparation_applies_four_surfaces_and_ack_is_preserved(self):
        self.mount_context()
        first = await self.executor.prepare(self.parameters)
        self.assertEqual(first['system_prompt'], '规则')
        self.assertEqual(first['context'][0]['text'], '资料')
        self.assertEqual(first['tail'], ['当前时刻'])
        self.assertEqual(len(first['inputs']), 1)
        self.assertEqual((await self.executor.prepare(self.parameters))['inputs'], first['inputs'])
        self.executor.ack(dict(actor='actor', events=[dict(source=item['source'], id=item['id']) for item in first['inputs']]))
        self.assertEqual((await self.executor.prepare(self.parameters))['inputs'], [])
        self.assertEqual(self.node.dataer.read(), '记忆正文')

    async def test_removed_prepare_source_clears_snapshots_and_keeps_event_history(self):
        self.mount_context()
        await self.executor.prepare(self.parameters)
        self.binding['prepare'] = []
        view = await self.executor.prepare(self.parameters)
        self.assertEqual(view['system_prompt'], '')
        self.assertEqual(view['context'], [])
        self.assertEqual(view['tail'], [])
        self.assertEqual(len(view['inputs']), 1)

    async def test_cross_node_preparation_uses_actual_access(self):
        other = Node(NodeInfo('other', 'Other'), bias=-1)
        self.network.add(other)
        self.mount_context(other)
        with self.assertRaises(KeyError):
            await self.executor.prepare(self.parameters)
        edge = Link('other', 'wrong')
        self.node.links.add(edge)
        with self.assertRaises(KeyError):
            await self.executor.prepare(self.parameters)
        edge.channels = ('context.assembler',)
        view = await self.executor.prepare(self.parameters)
        self.assertEqual(view['system_prompt'], '规则')
        edge.threshold = 3
        with self.assertRaises(KeyError):
            await self.executor.prepare(self.parameters)

    async def test_direct_iteration_preserves_tool_names_and_uses_obtained_references(self):
        target = Node(NodeInfo('numbers', 'Numbers'))
        target.install(CallableTool('read_number', lambda: 42, parameters={'type': 'object'}))
        self.network.add(target)
        edge = Link('numbers', 'tools')
        self.node.links.add(edge)
        view = await self.executor.prepare(self.parameters)
        self.assertEqual({tool['name'] for tool in view['tools']},
                         {'memory_query', 'memory_modify', 'memory_append', 'read_number'})
        self.node.links.remove(edge)
        with patch.object(self.discovery, 'discover', side_effect=AssertionError('调用时不再发现')):
            with patch.object(self.network, 'get', side_effect=AssertionError('调用时不再寻路')):
                self.assertEqual(await self.executor.invoke(dict(actor='actor', name='read_number')), 42)

    async def test_existing_tool_tables_are_live_and_history_supports_compaction(self):
        await self.executor.prepare(self.parameters)
        extra = CallableTool('extra', lambda: 'done')
        self.node.install(extra)
        view = await self.executor.prepare(self.parameters)
        self.assertIn('extra', {tool['name'] for tool in view['tools']})
        self.node.remove(extra)
        view = await self.executor.prepare(self.parameters)
        self.assertNotIn('extra', {tool['name'] for tool in view['tools']})
        self.assertIn('extra', {tool['name'] for tool in view['retained_tools']})
        self.assertIn('extra', view['unavailable'])
        self.assertEqual((await self.executor.invoke(dict(actor='actor', name='extra')))['status'], 'forbidden')
        self.assertIn('extra', self.executor.prune(dict(actor='actor', referenced=['extra'])))
        self.assertNotIn('extra', self.executor.prune(dict(actor='actor', referenced=[])))

    async def test_sync_async_and_dataclass_tool_results(self):
        @dataclass
        class Value:
            number: int
        async def calculate(number):
            await asyncio.sleep(0)
            return Value(number * 2)
        self.node.install(CallableTool('calculate', calculate, parameters={'type': 'object'}))
        await self.executor.prepare(self.parameters)
        result = await self.executor.invoke(dict(actor='actor', name='calculate', arguments={'number': 21}))
        self.assertEqual(result, {'number': 42})
        result = await self.executor.invoke(dict(actor='actor', name='memory_query', arguments={}))
        self.assertEqual(result, {'actor': '记忆正文'})

    async def test_stale_session_callbacks_are_rejected(self):
        self.executor.bind(dict(actor='actor', session_id='new', context_cursor={'event_count': 4}))
        self.assertEqual(self.executor.states['actor']['context_cursor'], {'event_count': 4})
        parameters = dict(actor='actor', executor_session_id='old', name='memory_query')
        for method in (self.executor.prepare, self.executor.invoke):
            with self.subTest(method=method.__name__), self.assertRaises(PermissionError):
                await method(parameters)
        for method in (self.executor.ack, self.executor.prune):
            with self.subTest(method=method.__name__), self.assertRaises(PermissionError):
                method(parameters)

    async def test_run_passes_saved_session_and_opaque_cursor_to_native_host(self):
        calls = []
        class Transport:
            def host(self, method, parameters):
                calls.append((method, parameters))
                return dict(status='completed', session_id='continued', output='done')
        self.executor.transport = Transport()
        self.executor.bind(dict(actor='actor', session_id='saved', model_signature='sig', context_cursor={'prefix_hash': 'hash'}))
        result = await self.executor.run('actor', 'continue')
        self.assertEqual(result['output'], 'done')
        method, request = calls[0]
        self.assertEqual(method, 'agent-run')
        self.assertEqual(request['session_id'], 'saved')
        self.assertEqual(request['context_cursor'], {'prefix_hash': 'hash'})
        self.assertEqual(request['model_signature'], 'sig')
        self.assertEqual(self.executor.states['actor']['session_id'], 'continued')

    async def test_replaced_actor_does_not_commit_an_old_run_result(self):
        executor = self.executor
        replacement = AgentNode(NodeInfo('actor', 'Replacement'))
        class Transport:
            def host(inner, method, parameters):
                executor.network._nodes.pop('actor')
                executor.network.add(replacement)
                return dict(status='completed', session_id='stale-session', output='stale')
        executor.transport = Transport()
        with self.assertRaisesRegex(RuntimeError, 'replaced'):
            await executor.run('actor')
        self.assertNotIn('session_id', executor.states['actor'])

    async def test_cancel_is_forwarded_to_native_host(self):
        entered, release = Event(), Event()
        calls = []
        class Transport:
            def host(self, method, parameters):
                calls.append(method)
                if method == 'agent-run':
                    entered.set()
                    if not release.wait(2):
                        raise TimeoutError('取消未送达')
                    return dict(status='failed', error='cancelled')
                release.set()
                return {'ok': True}
        self.executor.transport = Transport()
        task = asyncio.create_task(self.executor.run('actor'))
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(calls, ['agent-run', 'agent-cancel'])
        self.assertTrue(release.is_set())

    async def test_agent_runner_uses_the_tools_already_supplied_by_agent(self):
        runtime = AsyncRuntime()
        self.addCleanup(runtime.close)
        executor = self.executor
        class Transport:
            def host(self, method, parameters):
                executor.bind(dict(actor='actor', session_id='session'))
                view = runtime.run(executor.prepare(dict(actor='actor', executor_session_id='session')))
                self.tools = [tool['name'] for tool in view['tools']]
                result = runtime.run(executor.invoke(dict(actor='actor', name='memory_query')))
                return dict(status='completed', session_id='session', output=result['actor'])
        transport = self.executor.transport = Transport()
        self.executor.attach('actor', runtime)
        self.assertEqual(await asyncio.to_thread(self.agent.run, '读取记忆'), '记忆正文')
        self.assertEqual(set(transport.tools), {'memory_query', 'memory_modify', 'memory_append'})


class ContextPacketTests(unittest.TestCase):
    def setUp(self):
        self.agent = AgentNode(NodeInfo('actor', 'A'))
        self.state = {}

    def test_real_input_contract_and_error_location(self):
        packet = dict(format='nexarbor-context/v1', patch=dict(system_prompt='rule',
            context=[dict(id='doc', text='fact')], inputs=[dict(id='opening', text='once')], tail=['current']),
            errors=[dict(error='one failed source')])
        self.assertTrue(apply_context_packet(self.agent, self.state, 'prepare', packet))
        self.assertEqual(self.agent.inputs.tail(), ['current'])
        self.assertEqual(len(self.agent.inputs.pending()), 1)
        self.assertEqual(self.state['context_assembly_errors'], packet['errors'])
        self.agent.inputs.acknowledge('prepare', 'opening')
        apply_context_packet(self.agent, self.state, 'prepare', packet)
        self.assertEqual(self.agent.inputs.pending(), [])

    def test_unknown_patch_field_rejected_before_source_update(self):
        with self.assertRaisesRegex(ValueError, 'Unknown Agent input field'):
            apply_context_packet(self.agent, self.state, 'prepare',
                                 dict(format='nexarbor-context/v1', patch=dict(context=[], errors=['wrong location'])))
        self.assertEqual(self.agent.inputs.snapshot(), {})

    def test_other_preparation_result_is_not_misclassified(self):
        self.assertFalse(apply_context_packet(self.agent, self.state, 'prepare', {'format': 'different'}))


class ModelRequestEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_is_delivered_to_mounted_modules_and_stale_sessions_are_rejected(self):
        from domain.core import Module
        events = []
        class Observer(Module):
            async def on_model_request(self, event):
                events.append(event)
        node = AgentNode(NodeInfo("actor", "Actor"))
        node.install(Observer("observer"))
        executor = NativeExecutor(Network([node]), None, bindings={"actor": {"executor": "harness"}}, states={"actor": {"session_id": "current"}})
        await executor.request(dict(actor="actor", executor_session_id="current", request_index=1))
        self.assertEqual(events, [dict(actor="actor", session_id="current", request_index=1)])
        with self.assertRaises(PermissionError):
            await executor.request(dict(actor="actor", executor_session_id="stale", request_index=2))
        self.assertEqual(len(events), 1)
