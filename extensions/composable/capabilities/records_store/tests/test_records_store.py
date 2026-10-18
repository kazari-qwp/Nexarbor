import asyncio
import unittest
from pathlib import Path

from jsonschema.exceptions import ValidationError

from datanet.core.json_values import thaw
from datanet.studio.testing import ModuleHarness

ACCESS = {'strength': 1, 'channels': ['records']}


class RecordsStoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        relay = Path(__file__).resolve().parent / 'fixtures' / 'relay'
        self.h = ModuleHarness(
            Path(__file__).resolve().parents[1],
            dependencies={'test.relay': relay},
        )

    async def asyncTearDown(self):
        await self.h.close()

    def mount(self, node, initial, minimum=None, agent=False, references=None):
        self.h.add_node(node, agent=agent)
        return self.h.mount(
            node,
            config={
                'initial': initial,
                'minimum': minimum or {},
                'references': references or [],
            },
            access=ACCESS,
        )

    async def read_values(self, node):
        result = await self.h.call(node, 'read', {}, channels=['records'])
        self.assertEqual(result['status'], 'ok', result)
        return result['data']['values']

    async def apply(self, node, parameters):
        return await self.h.call(node, 'apply', parameters, channels=['records'])

    async def test_read_returns_copy_and_apply_sets_and_deltas(self):
        self.mount(
            'a',
            {'金币': 10, '身份': '商人', '标签': ['可靠'], '备注': None},
            {'金币': 0},
        )
        values = await self.read_values('a')
        self.assertEqual(values, {'金币': 10, '身份': '商人', '标签': ['可靠'], '备注': None})

        result = await self.apply(
            'a',
            {
                'set': {'身份': '守卫'},
                'deltas': {'金币': -3},
                'expected': {'金币': 10, '身份': '商人'},
            },
        )
        self.assertEqual(result['status'], 'ok', result)
        self.assertFalse(result['data']['duplicate'])
        self.assertEqual(result['data']['values']['金币'], 7)
        self.assertEqual(result['data']['values']['身份'], '守卫')

        # 返回值不可反向修改仓内状态。
        snapshot = await self.read_values('a')
        snapshot['标签'].append('被篡改')
        snapshot['备注'] = '被篡改'
        self.assertEqual(
            await self.read_values('a'),
            {'金币': 7, '身份': '守卫', '标签': ['可靠'], '备注': None},
        )

    async def test_instances_are_isolated(self):
        self.mount('a', {'金币': 10}, {'金币': 0})
        self.mount('b', {'金币': 3}, {'金币': 0})
        result = await self.apply('a', {'deltas': {'金币': -4}})
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual((await self.read_values('a'))['金币'], 6)
        self.assertEqual((await self.read_values('b'))['金币'], 3)

    async def test_below_minimum_rejects_whole_request(self):
        self.mount('a', {'体力': 5, '魔力': 7}, {'体力': 0})
        result = await self.apply(
            'a',
            {'set': {'魔力': 99}, 'deltas': {'体力': -6}},
        )
        self.assertEqual(result['status'], 'error', result)
        self.assertIn('最低值', result['error'])
        self.assertEqual(await self.read_values('a'), {'体力': 5, '魔力': 7})

    async def test_non_numeric_record_and_boolean_delta_are_rejected(self):
        self.mount('a', {'体力': 5}, {'体力': 0})
        result = await self.apply('a', {'set': {'体力': '五'}, 'deltas': {'体力': 1}})
        self.assertEqual(result['status'], 'error', result)

        result = await self.apply('a', {'set': {'体力': True}, 'deltas': {'体力': 1}})
        self.assertEqual(result['status'], 'error', result)
        self.assertEqual((await self.read_values('a'))['体力'], 5)

        with self.assertRaises(ValidationError):
            await self.apply('a', {'deltas': {'体力': True}})

    async def test_expected_conflict_changes_nothing(self):
        self.mount('a', {'体力': 5, '身份': '商人'})
        result = await self.apply(
            'a',
            {'set': {'身份': '守卫'}, 'expected': {'体力': 4}},
        )
        self.assertEqual(result['status'], 'error', result)
        self.assertIn('expected', result['error'])
        self.assertEqual(await self.read_values('a'), {'体力': 5, '身份': '商人'})

        result = await self.apply(
            'a',
            {'set': {'身份': '守卫'}, 'expected': {'不存在': None}},
        )
        self.assertEqual(result['status'], 'error', result)

    async def test_key_is_idempotent_and_rejects_different_request(self):
        self.mount('a', {'金币': 10}, {'金币': 0})
        first = await self.apply('a', {'deltas': {'金币': -3}, 'key': '买面包-1'})
        self.assertEqual(first['status'], 'ok', first)
        self.assertFalse(first['data']['duplicate'])
        self.assertEqual(first['data']['values']['金币'], 7)

        repeat = await self.apply('a', {'deltas': {'金币': -3}, 'key': '买面包-1'})
        self.assertEqual(repeat['status'], 'ok', repeat)
        self.assertTrue(repeat['data']['duplicate'])
        self.assertEqual(repeat['data']['values']['金币'], 7)
        self.assertEqual((await self.read_values('a'))['金币'], 7)

        conflict = await self.apply('a', {'deltas': {'金币': -4}, 'key': '买面包-1'})
        self.assertEqual(conflict['status'], 'error', conflict)
        self.assertIn('不同请求', conflict['error'])
        self.assertEqual((await self.read_values('a'))['金币'], 7)

    async def test_agent_node_is_mounted_and_can_deduct(self):
        self.mount('npc', {'金币': 10, '身份': '商人'}, {'金币': 0}, agent=True)
        result = await self.apply(
            'npc',
            {
                'deltas': {'金币': -4},
                'expected': {'金币': 10, '身份': '商人'},
                'key': 'npc-买水-1',
            },
        )
        self.assertEqual(result['status'], 'ok', result)
        self.assertFalse(result['data']['duplicate'])
        self.assertEqual(result['data']['values']['金币'], 6)
        self.assertEqual((await self.read_values('npc'))['金币'], 6)

    async def test_other_real_module_forwards_apply_with_key_idempotency(self):
        self.mount('target', {'金币': 20}, {'金币': 0})
        self.h.add_node('front')
        self.h.mount(
            'front',
            module='test.relay',
            config={},
            access={'strength': 1, 'channels': ['relay', 'records']},
        )
        self.h.connect('front', 'target', channels=['relay', 'records'], threshold=1)

        first = await self.h.call(
            'front',
            'forward',
            {'target': 'target', 'deltas': {'金币': -5}, 'key': '转调扣款-1'},
            module='test.relay',
            strength=1,
            channels=['relay'],
        )
        self.assertEqual(first['status'], 'ok', first)
        self.assertFalse(first['data']['duplicate'])
        self.assertEqual(first['data']['values']['金币'], 15)

        repeat = await self.h.call(
            'front',
            'forward',
            {'target': 'target', 'deltas': {'金币': -5}, 'key': '转调扣款-1'},
            module='test.relay',
            strength=1,
            channels=['relay'],
        )
        self.assertEqual(repeat['status'], 'ok', repeat)
        self.assertTrue(repeat['data']['duplicate'])
        self.assertEqual(repeat['data']['values']['金币'], 15)
        self.assertEqual((await self.read_values('target'))['金币'], 15)

    async def test_concurrent_deductions_do_not_overdraw(self):
        self.mount('a', {'金币': 10}, {'金币': 0})
        results = await asyncio.gather(
            *[self.apply('a', {'deltas': {'金币': -1}}) for _ in range(20)]
        )
        successes = [item for item in results if item['status'] == 'ok']
        failures = [item for item in results if item['status'] == 'error']
        self.assertEqual(len(successes), 10, results)
        self.assertEqual(len(failures), 10, results)
        self.assertEqual((await self.read_values('a'))['金币'], 0)

    async def test_outer_lock_rolls_back_both_nodes_on_trailing_failure(self):
        self.mount('a', {'金币': 10}, {'金币': 0})
        self.mount('b', {'金币': 2}, {'金币': 0})
        self.h.connect('a', 'b', channels=['records'], threshold=1)
        try:
            async with self.h.network.node_locks.transaction(
                'a', ['a', 'b'], strength=1, channels=['records'], timeout=20
            ):
                first = await self.apply('a', {'deltas': {'金币': -4}})
                self.assertEqual(first['status'], 'ok', first)
                second = await self.apply('b', {'deltas': {'金币': 4}})
                self.assertEqual(second['status'], 'ok', second)
                raise RuntimeError('故意让事务末尾失败')
        except RuntimeError as error:
            self.assertIn('故意', str(error))
        else:
            self.fail('测试事务应当抛出末尾失败')

        self.assertEqual((await self.read_values('a'))['金币'], 10)
        self.assertEqual((await self.read_values('b'))['金币'], 2)


    async def test_agent_home_and_spouse_references_read_and_write(self):
        instance = self.mount(
            'npc',
            {'金币': 10, '身份': '商人'},
            {'金币': 0},
            agent=True,
            references=[
                {'key': 'home', 'node_id': 'house-1'},
                {'key': 'spouse', 'node_id': 'npc-b'},
            ],
        )
        values = await self.read_values('npc')
        self.assertEqual(values['home'], 'house-1')
        self.assertEqual(values['spouse'], 'npc-b')
        self.assertEqual(values['金币'], 10)

        result = await self.apply(
            'npc',
            {'set': {'home': 'house-2', 'spouse': None, '金币': 8}},
        )
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['data']['values']['home'], 'house-2')
        self.assertIsNone(result['data']['values']['spouse'])
        self.assertEqual(result['data']['values']['金币'], 8)

        # 引用与普通值分开持久化，不会把节点 ID 写成普通 values 字段。
        state_values = thaw(instance.state['values'])
        self.assertNotIn('home', state_values)
        self.assertNotIn('spouse', state_values)
        self.assertEqual(state_values['金币'], 8)
        state_refs = {item['key']: item['node_id'] for item in thaw(instance.state['references'])}
        self.assertEqual(state_refs, {'home': 'house-2', 'spouse': None})

    async def test_apply_adds_child_reference(self):
        instance = self.mount(
            'npc',
            {'金币': 10},
            references=[{'key': 'home', 'node_id': 'house-1'}],
        )
        result = await self.apply(
            'npc',
            {
                'references': [{'key': 'child', 'node_id': 'child-1'}],
                'set': {'金币': 9, '备注': '普通文本'},
                'expected': {'home': 'house-1', '金币': 10},
            },
        )
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['data']['values']['child'], 'child-1')
        self.assertEqual(result['data']['values']['home'], 'house-1')
        self.assertEqual(result['data']['values']['金币'], 9)
        self.assertEqual(result['data']['values']['备注'], '普通文本')
        self.assertEqual((await self.read_values('npc'))['child'], 'child-1')

        # 未声明的新字段即使值是字符串，也不会被猜成节点引用。
        state_values = thaw(instance.state['values'])
        self.assertEqual(state_values['备注'], '普通文本')
        state_keys = {item['key'] for item in thaw(instance.state['references'])}
        self.assertNotIn('备注', state_keys)

    async def test_reference_types_duplicates_and_plain_conflicts_are_rejected(self):
        self.mount(
            'dup-config',
            {},
            references=[
                {'key': 'home', 'node_id': 'h1'},
                {'key': 'home', 'node_id': 'h2'},
            ],
        )
        config_duplicate = await self.h.call('dup-config', 'read', {}, channels=['records'])
        self.assertEqual(config_duplicate['status'], 'error', config_duplicate)
        self.assertIn('重复', config_duplicate['error'])

        self.mount(
            'plain-config',
            {'home': '旧文本'},
            references=[{'key': 'home', 'node_id': 'h1'}],
        )
        config_conflict = await self.h.call('plain-config', 'read', {}, channels=['records'])
        self.assertEqual(config_conflict['status'], 'error', config_conflict)
        self.assertIn('initial', config_conflict['error'])

        self.mount(
            'a',
            {'金币': 5, '备注': '旧'},
            references=[{'key': 'home', 'node_id': 'h1'}],
        )
        duplicate = await self.apply(
            'a',
            {'references': [{'key': 'child', 'node_id': 'c1'}, {'key': 'child', 'node_id': 'c2'}]},
        )
        self.assertEqual(duplicate['status'], 'error', duplicate)
        self.assertIn('重复', duplicate['error'])

        conflict = await self.apply('a', {'references': [{'key': '备注', 'node_id': 'x'}]})
        self.assertEqual(conflict['status'], 'error', conflict)
        self.assertIn('同名', conflict['error'])

        wrong_type = await self.apply('a', {'set': {'home': 42}})
        self.assertEqual(wrong_type['status'], 'error', wrong_type)
        self.assertIn('节点 ID', wrong_type['error'])

        wrong_delta = await self.apply('a', {'deltas': {'home': 1}})
        self.assertEqual(wrong_delta['status'], 'error', wrong_delta)
        self.assertIn('不能做数值增减', wrong_delta['error'])

        with self.assertRaises(ValidationError):
            await self.apply('a', {'references': [{'key': 'child', 'node_id': 123}]})

        self.assertEqual(
            await self.read_values('a'),
            {'金币': 5, '备注': '旧', 'home': 'h1'},
        )

    async def test_expected_uses_merged_view_and_duplicate_returns_snapshot(self):
        instance = self.mount(
            'a',
            {'金币': 10},
            references=[{'key': 'home', 'node_id': 'h1'}],
        )
        first = await self.apply(
            'a',
            {
                'set': {'金币': 5},
                'references': [{'key': 'home', 'node_id': 'h2'}],
                'expected': {'home': 'h1', '金币': 10},
                'key': '设置住所-1',
            },
        )
        self.assertEqual(first['status'], 'ok', first)
        self.assertFalse(first['data']['duplicate'])
        self.assertEqual(first['data']['values']['home'], 'h2')

        moved = await self.apply('a', {'set': {'home': 'h3'}})
        self.assertEqual(moved['status'], 'ok', moved)

        repeat = await self.apply(
            'a',
            {
                'set': {'金币': 5},
                'references': [{'key': 'home', 'node_id': 'h2'}],
                'expected': {'home': 'h1', '金币': 10},
                'key': '设置住所-1',
            },
        )
        self.assertEqual(repeat['status'], 'ok', repeat)
        self.assertTrue(repeat['data']['duplicate'])
        # 幂等回执返回原快照的合并视图，而不是当前最新引用。
        self.assertEqual(repeat['data']['values']['home'], 'h2')
        self.assertEqual((await self.read_values('a'))['home'], 'h3')

        # 回执把普通 values 与显式 references 分开保存。
        receipt = thaw(instance.state['receipts'][-1])
        self.assertNotIn('home', receipt['values'])
        self.assertEqual(
            {item['key']: item['node_id'] for item in receipt['references']},
            {'home': 'h2'},
        )

        conflict = await self.apply(
            'a',
            {
                'set': {'金币': 4, 'home': 'h2'},
                'expected': {'home': 'h1', '金币': 10},
                'key': '设置住所-1',
            },
        )
        self.assertEqual(conflict['status'], 'error', conflict)
        self.assertIn('不同请求', conflict['error'])
        self.assertEqual((await self.read_values('a'))['home'], 'h3')

        mismatch = await self.apply(
            'a',
            {'set': {'金币': 1}, 'expected': {'home': 'h1'}},
        )
        self.assertEqual(mismatch['status'], 'error', mismatch)
        self.assertIn('expected', mismatch['error'])
        self.assertEqual((await self.read_values('a'))['金币'], 5)

    async def test_outer_transaction_rolls_back_references_on_both_nodes(self):
        self.mount('a', {'金币': 10}, references=[{'key': 'home', 'node_id': 'house-a'}])
        self.mount('b', {'金币': 2}, references=[{'key': 'spouse', 'node_id': 'npc-a'}])
        self.h.connect('a', 'b', channels=['records'], threshold=1)
        try:
            async with self.h.network.node_locks.transaction(
                'a', ['a', 'b'], strength=1, channels=['records'], timeout=20
            ):
                first = await self.apply(
                    'a',
                    {'set': {'home': 'house-new'}, 'references': [{'key': 'child', 'node_id': 'child-a'}]},
                )
                self.assertEqual(first['status'], 'ok', first)
                second = await self.apply(
                    'b',
                    {'set': {'spouse': 'npc-new'}, 'references': [{'key': 'parent', 'node_id': 'npc-a'}]},
                )
                self.assertEqual(second['status'], 'ok', second)
                raise RuntimeError('故意让事务末尾失败')
        except RuntimeError as error:
            self.assertIn('故意', str(error))
        else:
            self.fail('测试事务应当抛出末尾失败')

        a_values = await self.read_values('a')
        b_values = await self.read_values('b')
        self.assertEqual(a_values, {'金币': 10, 'home': 'house-a'})
        self.assertEqual(b_values, {'金币': 2, 'spouse': 'npc-a'})


    async def test_set_then_deltas_stack_on_same_plain_field(self):
        self.mount('a', {'gold': 10}, {'gold': 0})
        result = await self.apply(
            'a',
            {
                'expected': {'gold': 10},
                'set': {'gold': 5},
                'deltas': {'gold': 2},
            },
        )
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['data']['values']['gold'], 7)
        self.assertEqual((await self.read_values('a'))['gold'], 7)

    async def test_expected_checks_original_reference_before_reference_update(self):
        self.mount('a', {}, references=[{'key': 'home', 'node_id': 'h1'}])
        first = await self.apply(
            'a',
            {
                'expected': {'home': 'h1'},
                'references': [{'key': 'home', 'node_id': 'h2'}],
            },
        )
        self.assertEqual(first['status'], 'ok', first)
        self.assertEqual(first['data']['values']['home'], 'h2')
        self.assertEqual((await self.read_values('a'))['home'], 'h2')

        second = await self.apply(
            'a',
            {
                'expected': {'home': 'h2'},
                'references': [{'key': 'home', 'node_id': 'h3'}],
            },
        )
        self.assertEqual(second['status'], 'ok', second)
        self.assertEqual(second['data']['values']['home'], 'h3')

        mismatch = await self.apply(
            'a',
            {
                'expected': {'home': 'h1'},
                'references': [{'key': 'home', 'node_id': 'h4'}],
            },
        )
        self.assertEqual(mismatch['status'], 'error', mismatch)
        self.assertIn('expected', mismatch['error'])
        self.assertEqual((await self.read_values('a'))['home'], 'h3')


if __name__ == '__main__':
    unittest.main()
