"""原私人记忆业务和原始请求者隔离，不借工具发现访问其他 Agent。"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from adapt.harness.executor import NativeExecutor
from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.requester import as_requester, requester_id
from domain.agent import AgentNode
from domain.core import CallableTool, Network, NodeInfo
from projects.npc_town.modules.agents_memory import AgentsMemoryModule

ROOT = Path(__file__).resolve().parents[1]


class TownMemoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.node = AgentNode(NodeInfo('actor', 'Actor'))
        self.module = AgentsMemoryModule({'max_memories': 2})
        self.node.install(self.module)
        self.network = Network([self.node])

    async def test_original_memory_limit_duplicate_key_and_casefold_query_rules(self):
        first = await self.module.remember('Hello WORLD', key='one')
        self.assertEqual(first['count'], 1)
        self.assertTrue((await self.module.remember('Hello WORLD', key='one'))['duplicate'])
        with self.assertRaises(ValueError):await self.module.remember('different', key='one')
        self.assertEqual((await self.module.recall('world'))['memories'], [{'text': 'Hello WORLD', 'key': 'one'}])
        await self.module.remember('two')
        await self.module.remember('three')
        self.assertEqual((await self.module.recall())['memories'], [{'text': 'two'}, {'text': 'three'}])

    async def test_other_requester_cannot_read_or_write_private_memory(self):
        await self.module.remember('private')
        before = await self.module.recall()
        with as_requester('other'):
            with self.assertRaises(PermissionError):await self.module.recall()
            with self.assertRaises(PermissionError):await self.module.remember('must not write')
        self.assertIsNone(requester_id.get())
        self.assertEqual(await self.module.recall(), before)

    async def test_native_invocation_carries_and_resets_requester_across_await(self):
        observed = []
        async def inspect():
            await asyncio.sleep(.01)
            observed.append(requester_id.get())
            return requester_id.get()
        self.node.install(CallableTool('inspect', inspect))
        executor = NativeExecutor(self.network, None, bindings={'actor': {}})
        await executor.prepare({'actor': 'actor'})
        self.assertEqual(await executor.invoke(dict(actor='actor', name='inspect')), 'actor')
        self.assertIsNone(requester_id.get())
        self.assertEqual(observed, ['actor'])

    async def test_parallel_actors_do_not_share_requester_identity(self):
        other = AgentNode(NodeInfo('other', 'Other'))
        other_memory = AgentsMemoryModule()
        other.install(other_memory)
        self.network.add(other)
        executor = NativeExecutor(self.network, None, bindings={'actor': {}, 'other': {}})
        await asyncio.gather(executor.prepare({'actor': 'actor'}), executor.prepare({'actor': 'other'}))
        results = await asyncio.gather(*(executor.invoke(dict(actor=actor, name='remember', arguments={'text': actor}))
                                        for actor in ('actor', 'other')))
        self.assertEqual([result['count'] for result in results], [1, 1])
        self.assertEqual((await self.module.recall())['memories'], [{'text': 'actor'}])
        self.assertEqual((await other_memory.recall())['memories'], [{'text': 'other'}])
        self.assertIsNone(requester_id.get())

    async def test_native_tool_reference_does_not_change_original_requester(self):
        other = AgentNode(NodeInfo('other', 'Other'))
        other.install(CallableTool('leaked_reference', self.module.recall))
        self.network.add(other)
        executor = NativeExecutor(self.network, None, bindings={'other': {}})
        await executor.prepare({'actor': 'other'})
        with self.assertRaises(PermissionError):await executor.invoke(dict(actor='other', name='leaked_reference'))
        self.assertIsNone(requester_id.get())

    async def test_memory_is_restored_by_node_transaction_and_log_reopen(self):
        with TemporaryDirectory(prefix='.town-memory-', dir=ROOT / 'build') as directory:
            saver = NetworkSaver()
            saver.tables.module_types['agents.memory'] = lambda spec: AgentsMemoryModule()
            backend = Backend(directory, network=self.network, saver=saver)
            try:
                await self.module.remember('before')
                backend.save()
                try:
                    async with backend.node_locks.transaction(['actor']):
                        await self.module.remember('rollback')
                        raise ValueError('rollback')
                except ValueError:pass
                self.assertEqual((await self.module.recall())['memories'], [{'text': 'before'}])
                backend.restore(backend.store.latest())
                restored = backend.network.get('actor').modules.get('agents.memory')
                self.assertEqual((await restored.recall())['memories'], [{'text': 'before'}])
                self.assertEqual([tool.name for tool in backend.network.get('actor').tools], ['remember', 'recall'])
                self.assertEqual((await next(iter(restored.tools)).invoke(text='after'))['count'], 2)
            finally:backend.close()
