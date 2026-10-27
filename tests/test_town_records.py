"""原记录仓规则迁到新 Module/access，供小镇交易和行动点共用。"""

import asyncio
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.network_saver import NetworkSaver
from app.runtime.backend import Backend
from domain.core import Network, Node, NodeInfo
from projects.npc_town.modules.records_store import RecordsStoreModule

ROOT = Path(__file__).resolve().parents[1]


class TownRecordsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.node = Node(NodeInfo('actor', 'Actor'))
        self.module = RecordsStoreModule({'initial': {'gold': 10, 'ap': 3}, 'minimum': {'gold': 0, 'ap': 0},
                                         'references': [{'key': 'home', 'node_id': 'old'}]})
        self.node.install(self.module)
        self.network = Network([self.node])

    async def test_combined_reference_and_value_update_preserves_receipt_snapshot(self):
        request = dict(set={'gold': 5}, deltas={'gold': 2}, expected={'home': 'old'},
                       references=[{'key': 'home', 'node_id': 'new'}], key='one')
        first = await self.module.apply(**request)
        self.assertEqual(first, {'values': {'gold': 7, 'ap': 3, 'home': 'new'}, 'duplicate': False})
        await self.module.apply(deltas={'gold': 1})
        duplicate = await self.module.apply(**request)
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(duplicate['values']['gold'], 7)
        self.assertEqual((await self.module.read())['values']['gold'], 8)
        before = deepcopy(self.module.state)
        with self.assertRaises(ValueError):await self.module.apply(**dict(request, set={'gold': 6}))
        self.assertEqual(self.module.state, before)

    async def test_failed_expected_minimum_or_reference_math_does_not_initialize_state(self):
        for request in (dict(expected={'gold': True}), dict(expected={'gold': 11}),
                        dict(deltas={'gold': -11}), dict(deltas={'ap': float('inf')}),
                        dict(deltas={'home': 1}), dict(references=[{'key': 'gold', 'node_id': 'x'}]),
                        dict(set={'home': 7}), dict(unset=['gold'], set={'gold': 0})):
            with self.subTest(request=request), self.assertRaises(ValueError):await self.module.apply(**request)
            self.assertEqual(self.module.state, {})

    async def test_unset_and_explicit_references_remain_distinct_from_plain_strings(self):
        await self.module.apply(set={'note': 'old'}, references=[{'key': 'spouse', 'node_id': 'person'}])
        await self.module.apply(unset=['home', 'gold'])
        self.assertEqual((await self.module.read())['values'], {'ap': 3, 'note': 'old', 'spouse': 'person'})
        self.assertEqual(self.module.state['references'], [{'key': 'spouse', 'node_id': 'person'}])

    async def test_concurrent_event_loop_updates_do_not_lose_increments(self):
        await asyncio.gather(*(self.module.apply(deltas={'gold': 1}) for _ in range(20)))
        self.assertEqual((await self.module.read())['values']['gold'], 30)

    async def test_receipt_limit_and_read_do_not_publish_mutable_state_references(self):
        for index in range(205):await self.module.apply(set={'items': [index]}, key=str(index))
        self.assertEqual(len(self.module.state['receipts']), 200)
        value = await self.module.read()
        value['values']['items'].append('outside')
        self.assertEqual((await self.module.read())['values']['items'], [204])

    async def test_persistent_transaction_restores_record_state_and_blocks_outside_group_write(self):
        with TemporaryDirectory(prefix='.town-records-', dir=ROOT / 'build') as directory:
            codec = NetworkSaver()
            codec.tables.module_types['records.store'] = lambda spec: RecordsStoreModule(spec.get('config'), spec.get('state'))
            backend = Backend(directory, network=self.network, saver=codec)
            try:
                other = Node(NodeInfo('other', 'Other'))
                backend.network.add(other)
                try:
                    async with backend.node_locks.transaction(['actor']):
                        await self.module.apply(deltas={'gold': -4})
                        raise RuntimeError('business rollback')
                except RuntimeError:pass
                self.assertEqual((await self.module.read())['values']['gold'], 10)
                async with backend.node_locks.transaction(['other']):
                    with self.assertRaises(PermissionError):await self.module.apply(deltas={'gold': -1})
                await self.module.apply(set={'ap': 2})
                backend.save()
                backend.restore(backend.store.latest())
                restored = backend.network.get('actor').modules.get('records.store')
                self.assertEqual((await restored.read())['values']['ap'], 2)
                self.assertIsNot(restored, self.module)
            finally:backend.close()
