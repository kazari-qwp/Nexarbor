"""装饰器统一处理访问条件、节点汇合、生命周期与返回值。"""

import asyncio
import unittest

from domain.core import access
from domain.core import (
    Aggregation, AverageAggregation, MaxAggregation, MinAggregation, SumAggregation,
)
from domain.core import DEFAULT_CHANNEL, Link, Multiplier
from domain.core import Module
from domain.core import Network
from domain.core import Node
from domain.core import NodeInfo
from domain.core import CallableTool


def node(node_id, aggregation=None):
    return Node(NodeInfo(node_id, node_id), aggregation=aggregation)


def reader(origin, *, channels='default', strength=1):
    class Reader(Module):
        @access(channels=channels, strength=strength)
        def read(self, current, prefix=''):
            return prefix + current.info.name

    module = Reader('reader')
    origin.install(module)
    return module


class AccessTests(unittest.TestCase):
    def test_bare_and_empty_decorators_execute_once_on_the_local_node(self):
        calls = []

        class Reader(Module):
            @access
            def bare(self, current, suffix):
                calls.append(current.info.node_id)
                return current.info.name + suffix

            @access()
            def local(self, current, suffix):
                calls.append(current.info.node_id)
                return current.info.name + suffix

            @access(strength=100)
            def strength_only(self, current, suffix):
                calls.append(current.info.node_id)
                return current.info.name + suffix

        def forbidden_processor(value):
            raise AssertionError('本节点操作不能触发出边处理器')

        a, b = node('a'), node('b')
        a.links.add(Link('b', processor=forbidden_processor))
        a.links.add(Link('missing', processor=forbidden_processor))
        network = Network([a, b])
        module = Reader('reader')
        a.install(module)
        for method in (module.bare, module.local, module.strength_only):
            with self.subTest(method=method.__name__):
                calls.clear()
                self.assertEqual(method('!'), {'a': 'a!'})
                self.assertEqual(calls, ['a'])

    def test_empty_async_decorator_only_executes_once_on_the_local_node(self):
        calls = []

        class Reader(Module):
            @access()
            async def read(self, current):
                await asyncio.sleep(0)
                calls.append(current.info.node_id)
                return current.info.name

        a, b = node('a'), node('b')
        a.links.add(Link('b'))
        network = Network([a, b])
        module = Reader('reader')
        a.install(module)
        self.assertEqual(asyncio.run(module.read()), {'a': 'a'})
        self.assertEqual(calls, ['a'])

    def test_default_and_bare_decorators_inherit_module_access_settings(self):
        class Reader(Module):
            @access()
            def read(self, current):
                return current.info.name

            @access
            def bare(self, current):
                return current.info.name

        a, b, c = [node(key) for key in 'abc']
        a.links.add(Link('b', 'a', threshold=2))
        a.links.add(Link('c', 'b'))
        network = Network([a, b, c])
        module = Reader('reader', channels='a', strength=2)
        a.install(module)
        self.assertEqual(module.channels, ('a',))
        self.assertEqual(module.strength, 2)
        self.assertEqual(module.read(), {'a': 'a', 'b': 'b'})
        self.assertEqual(module.bare(), {'a': 'a', 'b': 'b'})

    def test_explicit_parameters_override_module_defaults_including_empty_and_zero(self):
        class Reader(Module):
            @access(channels='b', strength=3)
            def override(self, current):
                return current.info.name

            @access(channels=())
            def local(self, current):
                return current.info.name

            @access(strength=0)
            def zero(self, current):
                return current.info.name

        a, b, c = [node(key) for key in 'abc']
        a.links.add(Link('b', 'a', threshold=2))
        a.links.add(Link('c', 'b', threshold=3))
        network = Network([a, b, c])
        module = Reader('reader', channels='a', strength=2)
        a.install(module)
        self.assertEqual(module.override(), {'a': 'a', 'c': 'c'})
        self.assertEqual(module.local(), {'a': 'a'})
        self.assertEqual(module.zero(), {'a': 'a'})

    def test_partial_parameters_inherit_the_unspecified_module_setting(self):
        class Reader(Module):
            @access(strength=3)
            def strength_only(self, current):
                return current.info.name

            @access(channels='b')
            def channels_only(self, current):
                return current.info.name

        a, b, c = [node(key) for key in 'abc']
        a.links.add(Link('b', 'a', threshold=3))
        a.links.add(Link('c', 'b', threshold=2))
        network = Network([a, b, c])
        module = Reader('reader', channels='a', strength=2)
        a.install(module)
        self.assertEqual(module.strength_only(), {'a': 'a', 'b': 'b'})
        self.assertEqual(module.channels_only(), {'a': 'a', 'c': 'c'})

    def test_inherited_settings_are_resolved_at_call_time(self):
        class Reader(Module):
            @access()
            def read(self, current):
                return current.info.name

        a, b, c = [node(key) for key in 'abc']
        a.links.add(Link('b', 'a', threshold=2))
        a.links.add(Link('c', 'b', threshold=3))
        network = Network([a, b, c])
        module = Reader('reader', channels='a', strength=2)
        a.install(module)
        self.assertEqual(module.read(), {'a': 'a', 'b': 'b'})
        module.channels = 'b'
        module.strength = 3
        self.assertEqual(module.read(), {'a': 'a', 'c': 'c'})
        module.strength = -1
        with self.assertRaises(ValueError):
            module.read()

    def test_module_configuration_is_validated_when_constructed(self):
        with self.assertRaises(ValueError):
            Module('bad', channels=[''])
        for strength in (-1, True, float('inf')):
            with self.subTest(strength=strength), self.assertRaises(ValueError):
                Module('bad', strength=strength)

    def test_non_module_object_without_settings_keeps_default_local_behavior(self):
        class Signal:
            def __init__(self, origin):
                self._access_origin = origin

            @access()
            def deliver(self, current):
                return current.info.name

        a, b = node('a'), node('b')
        a.links.add(Link('b'))
        network = Network([a, b])
        self.assertEqual(Signal(a).deliver(), {'a': 'a'})

    def test_single_node_body_is_called_in_bfs_order_and_parameters_are_forwarded(self):
        a, b, c, d = [node(key) for key in 'abcd']
        a.links.add(Link('b'))
        a.links.add(Link('c'))
        b.links.add(Link('d'))
        network = Network([a, b, c, d])
        module = reader(a)
        expected = {'a': 'name:a', 'b': 'name:b', 'c': 'name:c', 'd': 'name:d'}
        self.assertEqual(module.read(prefix='name:'), expected)
        self.assertEqual(module.read('name:'), expected)
        self.assertEqual(list(module.read()), ['a', 'b', 'c', 'd'])

    def test_channels_match_by_intersection_and_process_each_link_once(self):
        a, b, c = [node(key) for key in 'abc']
        calls = []
        a.links.add(Link('b', ['read', 'write'], processor=lambda value: calls.append(value) or value))
        a.links.add(Link('c', 'secret'))
        network = Network([a, b, c])
        module = reader(a, channels=['read', 'write', 'read'], strength=3)
        self.assertEqual(module.read(), {'a': 'a', 'b': 'b'})
        self.assertEqual(calls, [3])

    def test_empty_channels_only_access_the_local_node_even_without_a_network(self):
        a = node('a')
        a.links.add(Link('missing'))
        self.assertEqual(reader(a, channels=[]).read(), {'a': 'a'})

    def test_transmitted_strength_is_used_at_each_hop(self):
        a, b, c, d = [node(key) for key in 'abcd']
        a.links.add(Link('b', 'read', threshold=5, processor=Multiplier(0.5)))
        b.links.add(Link('c', 'read', threshold=3, processor=Multiplier(2)))
        b.links.add(Link('d', 'read', threshold=4))
        network = Network([a, b, c, d])
        module = reader(a, channels='read', strength=6)
        self.assertEqual(list(module.read()), ['a', 'b', 'c'])
        a.remove(module)
        self.assertEqual(reader(a, channels='read', strength=4).read(), {'a': 'a'})

    def test_all_aggregation_strategies_affect_further_access(self):
        for aggregation, expected in [
            (SumAggregation(), 10), (MaxAggregation(), 8),
            (MinAggregation(), 2), (AverageAggregation(), 5),
        ]:
            with self.subTest(aggregation=type(aggregation).__name__):
                a, b, c, d, e = [node(key) for key in 'abcde']
                d.aggregation = aggregation
                a.links.add(Link('b', processor=Multiplier(2)))
                a.links.add(Link('c', processor=Multiplier(8)))
                b.links.add(Link('d'))
                c.links.add(Link('d'))
                strengths = []
                d.links.add(Link('e', processor=lambda value: strengths.append(value) or value))
                network = Network([a, b, c, d, e])
                module = reader(a)
                self.assertEqual(list(module.read()), ['a', 'b', 'c', 'd', 'e'])
                self.assertEqual(strengths, [expected])
                d.links.list()[0].threshold = 6
                expected_ids = ['a', 'b', 'c', 'd', 'e'] if expected >= 6 else ['a', 'b', 'c', 'd']
                self.assertEqual(list(module.read()), expected_ids)

    def test_bias_is_applied_once_after_aggregation_and_negative_receivers_are_blocked(self):
        a, b, c, d, e, f = [node(key) for key in 'abcdef']
        for item in (a, b, c, d, e, f):
            item.bias = -1
        a.links.add(Link('b'))
        a.links.add(Link('c'))
        b.links.add(Link('d'))
        c.links.add(Link('d'))
        d.links.add(Link('e'))
        e.links.add(Link('f'))
        network = Network([a, b, c, d, e, f])
        # 起点 2；b=c=1；d=(1+1)-1=1；e=0；f=-1，不执行。
        self.assertEqual(reader(a, strength=2).read(), {'a': 'a', 'b': 'b', 'c': 'c', 'd': 'd', 'e': 'e'})

    def test_bias_defaults_to_zero_and_requires_a_finite_number(self):
        item = node('a')
        self.assertEqual(item.bias, 0)
        self.assertEqual(Node(NodeInfo('b', 'b'), bias=-1).bias, -1)
        item.bias = 0.5
        self.assertEqual(item.bias, 0.5)
        for value in (True, '1', None, float('inf'), float('nan')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                item.bias = value
        self.assertEqual(item.bias, 0.5)

    def test_parallel_edges_merge_but_cycles_and_later_arrivals_do_not_repeat_operations(self):
        a, b, c, d = [node(key) for key in 'abcd']
        a.links.add(Link('a', processor=Multiplier(100)))
        a.links.add(Link('b', processor=Multiplier(2)))
        a.links.add(Link('b', processor=Multiplier(3)))
        a.links.add(Link('c'))
        b.links.add(Link('a', processor=Multiplier(100)))
        c.links.add(Link('b', processor=Multiplier(100)))
        b.links.add(Link('d', threshold=5))
        network = Network([a, b, c, d])
        self.assertEqual(list(reader(a).read()), ['a', 'b', 'c', 'd'])

    def test_zero_strength_crosses_zero_threshold(self):
        a, b = node('a'), node('b')
        a.links.add(Link('b'))
        network = Network([a, b])
        self.assertEqual(reader(a, strength=0).read(), {'a': 'a', 'b': 'b'})

    def test_default_aggregation_is_sum_and_custom_aggregation_receives_all_inputs(self):
        a, b = node('a'), node('b')
        self.assertIsInstance(a.aggregation, SumAggregation)
        self.assertIsNot(a.aggregation, b.aggregation)

        class RecordingAggregation(Aggregation):
            def __init__(self):
                self.inputs = []

            def combine(self, strengths):
                self.inputs.append(tuple(strengths))
                return 7

        aggregation = RecordingAggregation()
        b.aggregation = aggregation
        c = node('c')
        a.links.add(Link('b', processor=Multiplier(2)))
        a.links.add(Link('b', processor=Multiplier(3)))
        b.links.add(Link('c', threshold=7))
        network = Network([a, b, c])
        self.assertEqual(list(reader(a).read()), ['a', 'b', 'c'])
        self.assertEqual(aggregation.inputs, [(2, 3)])

    def test_reachable_missing_targets_raise_and_blocked_edges_are_ignored(self):
        a = node('a')
        a.links.add(Link('missing', 'secret'))
        module = reader(a)
        self.assertEqual(module.read(), {'a': 'a'})
        a.remove(module)
        with self.assertRaisesRegex(ValueError, '节点不存在'):
            reader(a, channels='secret').read()

    def test_invalid_policies_and_processor_outputs_are_rejected(self):
        for strength in (-1, float('nan'), float('inf'), True, '1'):
            with self.subTest(strength=strength), self.assertRaises(ValueError):
                access(strength=strength)
        with self.assertRaises(ValueError):
            access(channels=[''])
        a, b = node('a'), node('b')
        a.links.add(Link('b', processor=lambda value: -1))
        network = Network([a, b])
        with self.assertRaisesRegex(ValueError, '有限非负数'):
            reader(a).read()

    def test_module_accesses_other_modules_inside_a_single_node_body(self):
        class Reader(Module):
            @access(channels='read', strength=2)
            def values(self, current):
                provider = current.modules.get('provider')
                return next(iter(provider.tools)).invoke() if provider is not None else None

        a, b, hidden = node('a'), node('b'), node('hidden')
        a.links.add(Link('b', 'read', threshold=2))
        a.links.add(Link('hidden', 'secret'))
        b.install(Module('provider', tools=[CallableTool('value', lambda: 'remote')]))
        hidden.install(Module('provider', tools=[CallableTool('secret', lambda: 'secret')]))
        network = Network([a, b, hidden])
        module = Reader('reader')
        a.install(module)
        self.assertEqual(module.values(), {'a': None, 'b': 'remote'})

    def test_distinct_instances_bind_to_different_nodes_and_uninstallation_disables_access(self):
        class Reader(Module):
            @access(channels=[])
            def read(self, current):
                return current.info.node_id

        a, b = node('a'), node('b')
        first, second = Reader('reader'), Reader('second')
        with self.assertRaisesRegex(RuntimeError, '尚未绑定节点'):
            first.read()
        a.install(first)
        b.install(second)
        self.assertEqual(first.read(), {'a': 'a'})
        self.assertEqual(second.read(), {'b': 'b'})
        with self.assertRaisesRegex(ValueError, '已经安装到其他节点'):
            b.install(first)
        self.assertEqual(first.read(), {'a': 'a'})
        a.remove(first)
        with self.assertRaisesRegex(RuntimeError, '尚未绑定节点'):
            first.read()
        a.install(first)
        self.assertEqual(first.read(), {'a': 'a'})

    def test_dependency_modules_are_bound_and_failed_installation_unbinds_new_modules(self):
        a = node('a')
        dependency = reader(a, channels=[])
        a.remove(dependency)
        action = CallableTool('action', lambda: 'ok', modules=(dependency,))
        a.install(action)
        self.assertEqual(dependency.read(), {'a': 'a'})
        a.remove(action)
        a.remove(dependency)
        a.install(CallableTool('same', lambda: 'existing'))
        with self.assertRaisesRegex(ValueError, '工具名称冲突'):
            a.install(CallableTool('same', lambda: 'new', modules=(dependency,)))
        self.assertEqual(list(a.modules), [])
        with self.assertRaisesRegex(RuntimeError, '尚未绑定节点'):
            dependency.read()

    def test_async_operations_are_awaited_in_bfs_order(self):
        calls = []

        class Reader(Module):
            @access(channels=DEFAULT_CHANNEL)
            async def read(self, current, suffix):
                await asyncio.sleep(0)
                calls.append(current.info.node_id)
                return current.info.name + suffix

        a, b = node('a'), node('b')
        a.links.add(Link('b'))
        network = Network([a, b])
        module = Reader('reader')
        a.install(module)
        self.assertEqual(asyncio.run(module.read('!')), {'a': 'a!', 'b': 'b!'})
        self.assertEqual(calls, ['a', 'b'])

    def test_async_peers_run_concurrently_and_the_next_layer_waits_for_all_peers(self):
        async def scenario():
            started = {key: asyncio.Event() for key in 'bc'}
            release = {key: asyncio.Event() for key in 'bc'}
            finished = {key: asyncio.Event() for key in 'bc'}
            next_layer = asyncio.Event()
            completion_order = []
            merged = []

            class RecordingSum(SumAggregation):
                def combine(self, strengths):
                    merged.append(tuple(strengths))
                    return super().combine(strengths)

            class Reader(Module):
                @access()
                async def read(self, current):
                    key = current.info.node_id
                    if key in started:
                        started[key].set()
                        await release[key].wait()
                        finished[key].set()
                    if key == 'd':
                        next_layer.set()
                    completion_order.append(key)
                    return key

            a, b, c, d, e = [node(key) for key in 'abcde']
            d.aggregation = RecordingSum()
            a.links.add(Link('b', processor=Multiplier(2)))
            a.links.add(Link('c', processor=Multiplier(8)))
            b.links.add(Link('d'))
            c.links.add(Link('d'))
            d.links.add(Link('e', threshold=10))
            network = Network([a, b, c, d, e])
            module = Reader('reader', channels=DEFAULT_CHANNEL, strength=1)
            a.install(module)
            task = asyncio.create_task(module.read())
            try:
                await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values())), 1)
                release['c'].set()
                await asyncio.wait_for(finished['c'].wait(), 1)
                await asyncio.sleep(0)
                self.assertFalse(next_layer.is_set())
                self.assertEqual(merged, [])
                release['b'].set()
                result = await asyncio.wait_for(task, 1)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self.assertEqual(list(result), ['a', 'b', 'c', 'd', 'e'])
            self.assertEqual(completion_order, ['a', 'c', 'b', 'd', 'e'])
            self.assertEqual(merged, [(2, 8)])

        asyncio.run(scenario())

    def test_async_failure_cleans_up_siblings_and_does_not_advance(self):
        async def scenario():
            sibling_started = asyncio.Event()
            sibling_cleaned = asyncio.Event()
            visited = []

            class Reader(Module):
                @access(channels=DEFAULT_CHANNEL)
                async def read(self, current):
                    key = current.info.node_id
                    visited.append(key)
                    if key == 'b':
                        await sibling_started.wait()
                        raise ValueError('read failed')
                    if key == 'c':
                        sibling_started.set()
                        try:
                            await asyncio.Event().wait()
                        finally:
                            sibling_cleaned.set()

            a, b, c, d = [node(key) for key in 'abcd']
            a.links.add(Link('b'))
            a.links.add(Link('c'))
            b.links.add(Link('d'))
            network = Network([a, b, c, d])
            module = Reader('reader')
            a.install(module)
            with self.assertRaisesRegex(ValueError, 'read failed'):
                await asyncio.wait_for(module.read(), 1)
            self.assertTrue(sibling_cleaned.is_set())
            self.assertEqual(visited, ['a', 'b', 'c'])

        asyncio.run(scenario())

    def test_async_caller_cancellation_waits_for_sibling_cleanup(self):
        async def scenario():
            started = {key: asyncio.Event() for key in 'bc'}
            cleaned = []

            class Reader(Module):
                @access(channels=DEFAULT_CHANNEL)
                async def read(self, current):
                    key = current.info.node_id
                    if key in started:
                        started[key].set()
                        try:
                            await asyncio.Event().wait()
                        finally:
                            cleaned.append(key)

            a, b, c = [node(key) for key in 'abc']
            a.links.add(Link('b'))
            a.links.add(Link('c'))
            network = Network([a, b, c])
            module = Reader('reader')
            a.install(module)
            task = asyncio.create_task(module.read())
            try:
                await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values())), 1)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertCountEqual(cleaned, ['b', 'c'])
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        asyncio.run(scenario())

    def test_decorator_can_be_reused_by_an_object_other_than_a_module(self):
        class Signal:
            def __init__(self, origin):
                self._access_origin = origin

            @access(channels=DEFAULT_CHANNEL)
            def deliver(self, current, message):
                return current.info.name + ':' + message

        a, b = node('a'), node('b')
        a.links.add(Link('b'))
        network = Network([a, b])
        self.assertEqual(Signal(a).deliver('hello'), {'a': 'a:hello', 'b': 'b:hello'})

    def test_operation_errors_stop_subsequent_nodes(self):
        calls = []

        class Writer(Module):
            @access(channels=DEFAULT_CHANNEL)
            def write(self, current):
                calls.append(current.info.node_id)
                if current.info.node_id == 'b':
                    raise ValueError('write failed')

        a, b, c = [node(key) for key in 'abc']
        a.links.add(Link('b'))
        a.links.add(Link('c'))
        network = Network([a, b, c])
        module = Writer('writer')
        a.install(module)
        with self.assertRaisesRegex(ValueError, 'write failed'):
            module.write()
        self.assertEqual(calls, ['a', 'b'])


if __name__ == '__main__':
    unittest.main()
