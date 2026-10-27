"""执行器接入等待式访问；外部模型工作不占住节点。"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from adapt.harness.executor import NativeExecutor
from app.transactions import NodeLocks, NodeSnapshots
from domain.agent import MarkdownAgentNode
from domain.core import CallableTool, Link, Module, Network, Node, NodeInfo, access
from modules.tool_discovery import ToolDiscoveryModule


class NativeExecutorLockTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.executor-locks-', dir=Path(__file__).resolve().parents[1] / 'build')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        file = self.directory / 'memory.md'
        file.write_text('OLD', encoding='utf-8')
        self.actor = MarkdownAgentNode(NodeInfo('actor', 'Actor'), file)
        self.actor.install(ToolDiscoveryModule('tools', 2))
        self.target = Node(NodeInfo('target', 'Target'))
        self.network = Network([self.actor, self.target])
        self.states = {}
        snapshots = NodeSnapshots(self.network, self.directory, execution=self.states)
        self.locks = NodeLocks(self.network, snapshots)
        self.executor = NativeExecutor(self.network, None, bindings={'actor': {}}, states=self.states, locks=self.locks)

    def tearDown(self):
        for name in ('exclusive', 'active', 'waiters', 'dependencies', 'leases', 'suspended', 'tickets'):
            self.assertFalse(getattr(self.locks, name), name)

    async def test_prepare_waits_for_actor_without_blocking_the_loop(self):
        held, release = asyncio.Event(), asyncio.Event()
        async def writer():
            async with self.locks.transaction(['actor']):
                self.actor.update_inputs('host', tail=['NEW'])
                held.set()
                await release.wait()
        owner = asyncio.create_task(writer())
        await held.wait()
        prepared = asyncio.create_task(self.executor.prepare({'actor': 'actor'}))
        await asyncio.sleep(.01)
        self.assertFalse(prepared.done())
        async with self.locks.access(['target']):
            self.assertFalse(prepared.done())
        release.set()
        await owner
        self.assertEqual((await prepared)['tail'], ['NEW'])

    async def test_model_wait_yields_admission_and_reenters_after_transaction(self):
        entered, returned = Event(), Event()
        requests = []
        class Transport:
            def host(inner, method, parameters):
                requests.append((method, parameters))
                if method == 'agent-run':
                    entered.set()
                    if not returned.wait(2):
                        raise TimeoutError('model fixture deadline')
                    return dict(status='completed', session_id='session', output='done')
                return {}
        self.executor.transport = Transport()
        run = asyncio.create_task(self.executor.run('actor'))
        self.assertTrue(await asyncio.to_thread(entered.wait, 2))
        async with self.locks.transaction(['actor']):
            self.actor.dataer.write('NEW')
            returned.set()
            await asyncio.sleep(.02)
            self.assertFalse(run.done())
            async with self.locks.access(['target'], mutable=False):
                pass
        self.assertEqual((await run)['output'], 'done')
        self.assertIn('node_access_ticket', requests[0][1])
        self.assertEqual(self.actor.dataer.read(), 'NEW')

    async def test_obtained_remote_tool_waits_for_its_node_without_rediscovery(self):
        class Reader(Module):
            def __init__(self):
                super().__init__('reader')
                self.tools._add(CallableTool('read_target', self.read))
            @access(channels=())
            async def read(self, node):
                return node.info.name
        self.target.install(Reader())
        self.actor.links.add(Link('target', 'tools'))
        await self.executor.prepare({'actor': 'actor'})
        held, release = asyncio.Event(), asyncio.Event()
        async def writer():
            async with self.locks.transaction(['target']):
                self.target.info.name = 'Committed target'
                held.set()
                await release.wait()
        owner = asyncio.create_task(writer())
        await held.wait()
        discovery = self.actor.modules.get('tool_discovery')
        with patch.object(discovery, 'discover', side_effect=AssertionError('不能重新发现')):
            invoked = asyncio.create_task(self.executor.invoke(dict(actor='actor', name='read_target')))
            await asyncio.sleep(.01)
            self.assertFalse(invoked.done())
            release.set()
            await owner
            self.assertEqual(await invoked, {'target': 'Committed target'})

    async def test_native_context_port_uses_original_capture_and_restore_messages(self):
        calls = []
        class Transport:
            def host(inner, method, parameters):
                calls.append((method, parameters))
                if method == 'agent-context-capture':
                    return {'actor': dict(session_id='session', event_count=3)}
                return {'contexts': {'actor': dict(session_id='session', event_count=4)}}
        self.executor.transport = Transport()
        self.executor.bind(dict(actor='actor', session_id='session'))
        self.locks.contexts = self.executor
        with self.assertRaises(ValueError):
            async with self.locks.transaction(['actor']):
                raise ValueError('rollback')
        self.assertEqual(calls[0], ('agent-context-capture', {'bindings': {'actor': 'session'}}))
        self.assertEqual(calls[1][0], 'agent-context-restore')
        self.assertTrue(calls[1][1]['transactional'])
        self.assertEqual(self.states['actor']['context_cursor']['event_count'], 4)
