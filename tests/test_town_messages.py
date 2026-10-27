"""消息箱与私信中继的原业务：身份、扣费事务、去重和同层通知。"""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from adapt.harness.executor import NativeExecutor
from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from app.runtime.requester import as_requester, requester_id
from app.runtime.signal_work import LayerWork, current_work
from domain.agent import AgentNode
from domain.core import Link, Module, Network, Node, NodeInfo
from modules.tool_discovery import ToolDiscoveryModule
from projects.npc_town.modules.messages_box import MessagesBoxModule
from projects.npc_town.modules.messages_relay import MessagesRelayModule
from projects.npc_town.modules.records_store import RecordsStoreModule

ROOT = Path(__file__).resolve().parents[1]


class TownMessagesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.town-messages-', dir=ROOT / 'build')
        self.addCleanup(self.temporary.cleanup)
        self.alice = AgentNode(NodeInfo('alice', 'Alice'))
        self.bob = AgentNode(NodeInfo('bob', 'Bob'))
        self.account = RecordsStoreModule({'initial': {'ap': 3}, 'minimum': {'ap': 0}})
        self.relay = MessagesRelayModule(channels=('chat', 'records'), strength=2)
        self.box = MessagesBoxModule(self.transaction, channels=('chat', 'records'), strength=2)
        self.alice.install(self.account)
        self.alice.install(self.relay)
        self.bob.install(self.box)
        self.edge = Link('bob', 'chat')
        self.alice.links.add(self.edge)
        self.bob.links.add(Link('alice', 'chat'))
        self.network = Network([self.alice, self.bob])
        self.saver = NetworkSaver()
        self.saver.tables.module_types.update({
            'records.store': lambda spec: RecordsStoreModule(),
            'messages.relay': lambda spec: MessagesRelayModule(),
            'messages.box': lambda spec: MessagesBoxModule(self.transaction),
        })
        self.backend = Backend(self.temporary.name, network=self.network, saver=self.saver)
        self.addCleanup(self.backend.close)

    def transaction(self, nodes, **options):
        return self.backend.node_locks.transaction(nodes, **options)

    async def ap(self):return (await self.account.read())['values']['ap']

    async def test_relay_preserves_original_sender_and_does_not_keep_a_copy(self):
        result = await self.relay.send_to('bob', 'hello', topic='note', key='one')
        self.assertEqual((result['from'], result['to'], result['text']), ('alice', 'bob', 'hello'))
        self.assertEqual(self.relay.state, {})
        self.assertEqual((await self.box.read())['messages'][0]['id'], result['id'])
        self.assertEqual(await self.ap(), 3)

    async def test_fee_and_idempotent_message_are_committed_together_once(self):
        self.box.config['send_cost'] = 1
        first = await self.relay.send_to('bob', 'hello', key='one')
        second = await self.relay.send_to('bob', 'hello', key='one')
        self.assertEqual(first['ap'], 2)
        self.assertIsNone(second['ap'])
        self.assertTrue(second['duplicate'])
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(await self.ap(), 2)
        self.assertEqual(len((await self.box.read())['messages']), 1)
        with self.assertRaises(ValueError):await self.relay.send_to('bob', 'changed', key='one')
        self.assertEqual(await self.ap(), 2)

    async def test_failure_after_debit_restores_both_records_and_mailbox(self):
        self.box.config['send_cost'] = 1
        original = self.account.apply
        async def fail(**parameters):
            await original(**parameters)
            raise RuntimeError('after debit fixture')
        with patch.object(self.account, 'apply', side_effect=fail):
            with self.assertRaises(ValueError):await self.relay.send_to('bob', 'hello', key='one')
        self.assertEqual(await self.ap(), 3)
        self.assertEqual(self.box.state, {})
        self.assertEqual((await self.relay.send_to('bob', 'hello', key='one'))['ap'], 2)

    async def test_insufficient_ap_cannot_initialize_mailbox_or_receipts(self):
        self.box.config['send_cost'] = 4
        with self.assertRaises(ValueError):await self.relay.send_to('bob', 'hello', key='one')
        self.assertEqual(await self.ap(), 3)
        self.assertEqual(self.account.state, {})
        self.assertEqual(self.box.state, {})

    async def test_private_read_clear_and_reachable_read_policy(self):
        await self.relay.send_to('bob', 'hello')
        with as_requester('alice'):
            with self.assertRaises(PermissionError):await self.box.read()
            with self.assertRaises(PermissionError):await self.box.clear()
            self.box.config['read_policy'] = 'reachable'
            self.assertEqual(len((await self.box.read())['messages']), 1)
        self.assertEqual(await self.box.clear(), {'cleared': 1})
        self.assertEqual(self.box.state, {'messages': [], 'seen': []})

    async def test_concurrent_duplicate_delivery_does_not_charge_twice(self):
        self.box.config['send_cost'] = 1
        results = await asyncio.gather(*(self.relay.send_to('bob', 'same', key='one') for _ in range(8)))
        self.assertEqual(sum(not result['duplicate'] for result in results), 1)
        self.assertEqual(await self.ap(), 2)
        self.assertEqual(len(self.box.state['messages']), 1)

    async def test_channel_or_target_type_cannot_be_bypassed_by_relay(self):
        with self.assertRaises(ValueError):await self.relay.send_to('alice', 'self')
        self.edge.channels = ('wrong',)
        with self.assertRaisesRegex(ValueError, '不可达'):await self.relay.send_to('bob', 'blocked')
        self.edge.channels = ('chat',)
        ordinary = Node(NodeInfo('ordinary', 'Ordinary'))
        self.backend.network.add(ordinary)
        self.alice.links.add(Link('ordinary', 'chat'))
        with self.assertRaisesRegex(ValueError, '真实 Agent'):await self.relay.send_to('ordinary', 'blocked')
        self.assertEqual(self.box.state, {})

    async def test_public_box_tools_have_unique_real_names_and_private_agents_stay_skipped(self):
        for key in ('board1', 'board2'):
            node = Node(NodeInfo(key, key))
            node.install(MessagesBoxModule(self.transaction, {'read_policy': 'reachable'}, channels='chat', strength=2))
            node.links.add(Link('alice', 'chat'))
            self.backend.network.add(node)
            self.alice.links.add(Link(key, 'chat'))
        self.alice.install(ToolDiscoveryModule('chat', 2))
        executor = NativeExecutor(self.network, None, bindings={'alice': {}})
        definitions = (await executor.prepare({'actor': 'alice'}))['tools']
        public = [definition for definition in definitions if definition['name'].startswith('mod_')]
        self.assertEqual(len(public), 4)
        self.assertEqual(len({definition['name'] for definition in public}), 4)
        self.assertFalse(any('bob ·' in definition['description'] for definition in public))
        read = next(definition for definition in public if 'board1 · 读取' in definition['description'])
        self.assertEqual(await executor.invoke(dict(actor='alice', name=read['name'])), {'messages': []})

    async def test_notification_runs_in_the_same_layer_as_receiver_identity(self):
        observed = []
        class Activity(Module):
            def __init__(self):super().__init__('agents.activity')
            async def notify(self, key):
                observed.append((key, requester_id.get()))
                return {'queued': True}
        self.bob.install(Activity())
        self.saver.tables.module_types['agents.activity'] = lambda spec: Activity()
        self.box.config['notify_activity'] = True
        work = LayerWork(SimpleNamespace(signal_id='tick-1', max_deliveries=10), time.monotonic() + 10, {})
        token = current_work.set(work)
        try:
            result = await self.relay.send_to('bob', 'hello')
            self.assertTrue(result['notification']['queued'])
            await work.drain()
        finally:current_work.reset(token)
        self.assertEqual(observed, [('tick-1', 'bob')])
        self.assertEqual(work.record['deferred'][0]['status'], 'processed')

    async def test_notification_failure_keeps_delivered_message_and_debit(self):
        self.box.config.update(notify_activity=True, send_cost=1)
        work = LayerWork(SimpleNamespace(signal_id='tick-1', max_deliveries=10), time.monotonic() + 10, {})
        token = current_work.set(work)
        try:result = await self.relay.send_to('bob', 'hello')
        finally:current_work.reset(token)
        self.assertFalse(result['notification']['queued'])
        self.assertEqual(len(self.box.state['messages']), 1)
        self.assertEqual(await self.ap(), 2)

    async def test_log_restore_keeps_messages_tool_bindings_and_relay_sender(self):
        self.box.config['send_cost'] = 1
        await self.relay.send_to('bob', 'before', key='one')
        self.backend.save()
        names = [tool.name for tool in self.box.tools]
        self.backend.restore(self.backend.store.latest())
        self.box = self.backend.network.get('bob').modules.get('messages.box')
        self.relay = self.backend.network.get('alice').modules.get('messages.relay')
        self.account = self.backend.network.get('alice').modules.get('records.store')
        self.assertEqual([tool.name for tool in self.box.tools], names)
        self.assertEqual((await self.box.read())['messages'][0]['text'], 'before')
        duplicate = await self.relay.send_to('bob', 'before', key='one')
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(await self.ap(), 2)
