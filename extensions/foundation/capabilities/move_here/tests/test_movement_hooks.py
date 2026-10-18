import unittest
from pathlib import Path

from datanet.studio.testing import ModuleHarness
from jsonschema.exceptions import ValidationError

CHANNELS = ['movement', 'tools', 'records']
LOCAL_CHANNELS = ['movement', 'tools', 'records', 'info', 'service']


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

    async def new_harness(
        self, before_hooks=None, ap=10, old_info=True, destination_info=True,
        module_config=None, access_channels=None, location_edge_channels=None,
    ):
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
        old_edge_channels = location_edge_channels or CHANNELS
        harness.connect('npc', 'a', channels=old_edge_channels, attributes={'relation': 'location'})
        harness.connect('a', 'npc', channels=old_edge_channels, attributes={'relation': 'location'})
        harness.connect('a', 'b', channels=CHANNELS, attributes={'relation': 'road'})
        harness.connect('b', 'a', channels=CHANNELS, attributes={'relation': 'road'})
        config = dict(module_config or {})
        config['before_hooks'] = before_hooks or []
        harness.mount(
            'b', config=config,
            access={'strength': 2, 'channels': access_channels or CHANNELS},
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
        self.assertEqual(
            result['data']['before_results'],
            [{
                'target': 'requester',
                'module': 'records.store',
                'operation': 'apply',
                'data': {'values': {'ap': 7}, 'duplicate': False},
            }],
        )
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
        self.assertEqual(again['data'], {'moved': False, 'location': 'b', 'before_results': []})
        self.assertEqual(records.state['values']['ap'], 7)

    async def test_successful_hook_json_results_are_visible_in_order(self):
        harness, _npc_info, _b_info, records = await self.new_harness(
            before_hooks=[
                {
                    'target': 'requester',
                    'module': 'records.store',
                    'operation': 'apply',
                    'arguments': {'set': {'抵达事件': '雾中传来三声钟响'}},
                },
                hook({'ap': -3}),
            ],
        )

        result = await self.move(harness)

        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(records.state['values']['ap'], 7)
        self.assertEqual(records.state['values']['抵达事件'], '雾中传来三声钟响')
        self.assertEqual(
            [entry['target'] for entry in result['data']['before_results']],
            ['requester', 'requester'],
        )
        self.assertEqual(
            [entry['module'] for entry in result['data']['before_results']],
            ['records.store', 'records.store'],
        )
        self.assertEqual(
            [entry['operation'] for entry in result['data']['before_results']],
            ['apply', 'apply'],
        )
        self.assertEqual(
            result['data']['before_results'][0]['data']['values']['抵达事件'],
            '雾中传来三声钟响',
        )
        self.assertEqual(
            result['data']['before_results'][1]['data'],
            {'values': {'ap': 7, '抵达事件': '雾中传来三声钟响'}, 'duplicate': False},
        )

    async def test_configured_location_channels_keep_new_service_and_drop_old(self):
        harness, npc_info, b_info, _records = await self.new_harness(
            module_config={'location_channels': LOCAL_CHANNELS},
            access_channels=LOCAL_CHANNELS,
            location_edge_channels=LOCAL_CHANNELS,
        )
        harness.mount(
            'a', module='records.store',
            config={'initial': {'stock': 5}},
            access={'strength': 1, 'channels': ['records']},
        )
        harness.mount(
            'b', module='records.store',
            config={'initial': {'stock': 5}},
            access={'strength': 1, 'channels': ['records']},
        )
        harness.mount(
            'a', module='service.actions',
            config={
                'address': 'a',
                'actions': [{'id': 'old', 'title': '旧服务', 'cost': 0}],
            },
            access={'strength': 2, 'channels': ['service', 'records', 'movement']},
        )
        harness.mount(
            'b', module='service.actions',
            config={
                'address': 'b',
                'actions': [{'id': 'new', 'title': '新服务', 'cost': 0}],
            },
            access={'strength': 2, 'channels': ['service', 'records', 'movement']},
        )

        old_before = await harness.call(
            'a', 'perform', {'action': 'old'}, actor='npc',
            module='service.actions', strength=2, channels=['service'],
        )
        self.assertEqual(old_before['status'], 'ok', old_before)

        result = await self.move(harness)

        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['data']['location'], 'b')
        self.assertEqual(npc_info.state['location'], 'b')
        self.assertIn('npc', b_info.state['visitors'])
        self.assertEqual(
            [edge.target_node_id for edge in self.location_edges(harness, 'npc')],
            ['b'],
        )
        self.assertNotIn(
            'npc',
            [edge.target_node_id for edge in self.location_edges(harness, 'a')],
        )
        npc_edge = self.location_edges(harness, 'npc')[0]
        destination_edge = next(
            edge for edge in self.location_edges(harness, 'b')
            if edge.target_node_id == 'npc'
        )
        self.assertEqual(list(npc_edge.metadata.channels), LOCAL_CHANNELS)
        self.assertEqual(list(destination_edge.metadata.channels), LOCAL_CHANNELS)

        new_service = await harness.call(
            'b', 'perform', {'action': 'new'}, actor='npc',
            module='service.actions', strength=2, channels=['service'],
        )
        self.assertEqual(new_service['status'], 'ok', new_service)
        self.assertEqual(new_service['data']['action'], 'new')
        self.assertEqual(new_service['data']['actor'], 'npc')

        # 旧位置边已精确删除；绕行道路没有 service 频道，旧服务不可达。
        with self.assertRaises(PermissionError):
            await harness.call(
                'a', 'perform', {'action': 'old'}, actor='npc',
                module='service.actions', strength=2, channels=['service'],
            )

    async def test_channel_outside_access_rolls_back_whole_move(self):
        configured = CHANNELS + ['service']
        harness, npc_info, b_info, records = await self.new_harness(
            before_hooks=[hook({'ap': -3})],
            module_config={'location_channels': configured},
            access_channels=CHANNELS,
        )
        before_npc_edges = sorted(
            (edge.target_node_id, repr(edge.metadata))
            for edge in self.location_edges(harness, 'npc')
        )
        before_old_edges = sorted(
            (edge.target_node_id, repr(edge.metadata))
            for edge in self.location_edges(harness, 'a')
        )

        result = await self.move(harness)

        self.assertEqual(result['status'], 'error', result)
        self.assertIn('移动未完成', result['error'])
        after_records = await harness.call(
            'npc', 'read', {}, module='records.store', channels=['records'],
        )
        self.assertEqual(after_records['data']['values']['ap'], 10)
        after_npc = await harness.call(
            'npc', 'read', {}, module='place.info', channels=['movement'],
        )
        self.assertEqual(after_npc['data']['location'], 'a')
        self.assertNotIn('npc', b_info.state.get('visitors', []))
        self.assertEqual(
            sorted(
                (edge.target_node_id, repr(edge.metadata))
                for edge in self.location_edges(harness, 'npc')
            ),
            before_npc_edges,
        )
        self.assertEqual(
            sorted(
                (edge.target_node_id, repr(edge.metadata))
                for edge in self.location_edges(harness, 'a')
            ),
            before_old_edges,
        )

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
        self.assertEqual(result['data']['before_results'], [])
        self.assertEqual(npc_info.state['location'], 'b')
        npc_edges = self.location_edges(harness, 'npc')
        destination_edges = [
            edge for edge in self.location_edges(harness, 'b')
            if edge.target_node_id == 'npc'
        ]
        self.assertEqual([edge.target_node_id for edge in npc_edges], ['b'])
        self.assertEqual(list(npc_edges[0].metadata.channels), ['movement', 'tools'])
        self.assertEqual(
            list(destination_edges[0].metadata.channels),
            ['movement', 'tools'],
        )

    async def test_wrong_channel_is_rejected(self):
        harness, _npc_info, _b_info, _records = await self.new_harness()

        with self.assertRaises(PermissionError):
            await harness.call(
                'b', 'move', {}, actor='npc', strength=2, channels=['tools'],
            )

    async def test_location_channels_schema_rejects_invalid_values(self):
        harness = ModuleHarness(Path(__file__).resolve().parents[1])
        self.extra_harnesses.append(harness)
        cases = [
            ('empty', []),
            ('missing_movement', ['tools']),
            ('duplicate', ['movement', 'movement']),
            ('self', ['movement', 'self']),
            ('wrong_type', ['movement', 1]),
        ]
        for index, (name, channels) in enumerate(cases):
            node = 'bad%d' % index
            harness.add_node(node)
            with self.subTest(name):
                with self.assertRaises(ValidationError):
                    harness.mount(
                        node,
                        config={'location_channels': channels},
                        access={'strength': 2, 'channels': LOCAL_CHANNELS},
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
