import unittest
from pathlib import Path

from datanet.studio.testing import ModuleHarness
from jsonschema.exceptions import ValidationError

CHANNELS = ['movement', 'tools', 'records']


def hook(deltas):
    return {
        'target': 'requester',
        'module': 'records.store',
        'operation': 'apply',
        'arguments': {'deltas': deltas},
    }


class MovementHooksTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.extra_harnesses = []

    async def asyncTearDown(self):
        for harness in self.extra_harnesses:
            await harness.close()

    async def new_harness(self, before_hooks=None, ap=10, old_info=True, destination_info=True):
        harness = ModuleHarness(Path(__file__).resolve().parents[1])
        self.extra_harnesses.append(harness)
        harness.add_node('npc', name='旅人', agent=True)
        harness.add_node('a', name='旧镇', description='出发的小镇')
        harness.add_node('b', name='新镇', description='到达的小镇')
        npc_info = harness.mount(
            'npc', module='place.info',
            config={'description': '旅人', 'location': 'a'},
        )
        if old_info:
            harness.mount('a', module='place.info', config={'description': '出发的小镇'})
        b_info = None
        if destination_info:
            b_info = harness.mount('b', module='place.info', config={'description': '到达的小镇'})
        records = harness.mount(
            'npc', module='records.store',
            config={'initial': {'ap': ap}, 'minimum': {'ap': 0}},
        )
        harness.connect('npc', 'a', channels=CHANNELS, attributes={'relation': 'location'})
        harness.connect('a', 'npc', channels=CHANNELS, attributes={'relation': 'location'})
        harness.connect('a', 'b', channels=CHANNELS, attributes={'relation': 'road'})
        harness.connect('b', 'a', channels=CHANNELS, attributes={'relation': 'road'})
        harness.mount(
            'b', config={'before_hooks': before_hooks or []},
            access={'strength': 2, 'channels': CHANNELS},
        )
        return harness, npc_info, b_info, records

    def location_edges(self, harness, node):
        result = []
        for edge in harness.network.nodes[node].interfaces:
            attributes = getattr(edge.metadata, 'attributes', {}) or {}
            if attributes.get('relation') == 'location':
                result.append(edge)
        return result

    async def move(self, harness):
        return await harness.call(
            'b', 'move', {}, actor='npc', strength=2, channels=['movement'],
        )

    async def test_legal_move_deducts_three_ap_and_updates_both_places(self):
        harness, npc_info, b_info, records = await self.new_harness(
            before_hooks=[hook({'ap': -3})],
        )

        result = await self.move(harness)

        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['data']['moved'], True)
        self.assertEqual(result['data']['from_location'], 'a')
        self.assertEqual(result['data']['location'], 'b')
        self.assertEqual(records.state['values']['ap'], 7)
        self.assertEqual(npc_info.state['location'], 'b')
        self.assertEqual(
            [edge.target_node_id for edge in self.location_edges(harness, 'npc')],
            ['b'],
        )
        self.assertIn('npc', b_info.state['visitors'])

        # 再次调到同一地点不移动，也不重复执行扣费钩子。
        again = await self.move(harness)
        self.assertEqual(again['status'], 'ok', again)
        self.assertEqual(again['data'], {'moved': False, 'location': 'b'})
        self.assertEqual(records.state['values']['ap'], 7)

    async def test_insufficient_ap_leaves_edges_visitors_and_ap_unchanged(self):
        harness, npc_info, b_info, records = await self.new_harness(
            before_hooks=[hook({'ap': -3})], ap=2,
        )
        before_edges = sorted(
            (edge.target_node_id, repr(edge.metadata))
            for edge in self.location_edges(harness, 'npc')
        )

        result = await self.move(harness)

        self.assertEqual(result['status'], 'error', result)
        self.assertIn('低于最低值', result['error'])
        after_records = await harness.call(
            'npc', 'read', {}, module='records.store', channels=['records'],
        )
        self.assertEqual(after_records['data']['values']['ap'], 2)
        after_npc = await harness.call(
            'npc', 'read', {}, module='place.info', channels=['movement'],
        )
        self.assertEqual(after_npc['data']['location'], 'a')
        self.assertEqual(
            sorted(
                (edge.target_node_id, repr(edge.metadata))
                for edge in self.location_edges(harness, 'npc')
            ),
            before_edges,
        )
        after_destination = await harness.call(
            'b', 'read', {}, module='place.info', channels=['movement'],
        )
        self.assertNotIn('npc', after_destination['data'].get('visitors', []))

    async def test_late_old_place_failure_rolls_back_hook_deduction(self):
        harness, npc_info, b_info, records = await self.new_harness(
            before_hooks=[hook({'ap': -3})], old_info=False,
        )
        before_edges = sorted(
            (edge.target_node_id, repr(edge.metadata))
            for edge in self.location_edges(harness, 'npc')
        )

        result = await self.move(harness)

        self.assertEqual(result['status'], 'error', result)
        after = await harness.call(
            'npc', 'read', {}, module='records.store', channels=['records'],
        )
        self.assertEqual(after['status'], 'ok', after)
        self.assertEqual(after['data']['values']['ap'], 10)
        after_npc = await harness.call(
            'npc', 'read', {}, module='place.info', channels=['movement'],
        )
        self.assertEqual(after_npc['data']['location'], 'a')
        self.assertEqual(
            sorted(
                (edge.target_node_id, repr(edge.metadata))
                for edge in self.location_edges(harness, 'npc')
            ),
            before_edges,
        )
        after_destination = await harness.call(
            'b', 'read', {}, module='place.info', channels=['movement'],
        )
        self.assertNotIn('npc', after_destination['data'].get('visitors', []))

    async def test_empty_default_hooks_keep_original_move(self):
        harness, npc_info, _b_info, records = await self.new_harness(before_hooks=[])

        result = await self.move(harness)

        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['data']['location'], 'b')
        self.assertEqual(npc_info.state['location'], 'b')
        self.assertEqual(
            [edge.target_node_id for edge in self.location_edges(harness, 'npc')],
            ['b'],
        )

    async def test_wrong_channel_is_rejected(self):
        harness, _npc_info, _b_info, _records = await self.new_harness()

        with self.assertRaises(PermissionError):
            await harness.call(
                'b', 'move', {}, actor='npc', strength=2, channels=['tools'],
            )

    async def test_hook_target_is_limited_to_declared_enum(self):
        harness = ModuleHarness(Path(__file__).resolve().parents[1])
        self.extra_harnesses.append(harness)
        harness.add_node('b', name='新镇')
        with self.assertRaises(ValidationError):
            harness.mount(
                'b',
                config={'before_hooks': [{
                    'target': 'actor',
                    'module': 'records.store',
                    'operation': 'apply',
                    'arguments': {},
                }]},
                access={'strength': 2, 'channels': CHANNELS},
            )
