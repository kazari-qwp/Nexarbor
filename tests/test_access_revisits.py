"""access 可选去重；关闭时保留频道/强度、同层汇合及分层屏障。"""

import asyncio
import unittest

from domain.core import Link, Module, Network, Node, NodeInfo, access


def pair(*, attenuation=True):
    a = Node(NodeInfo('a', 'A'), bias=-1 if attenuation else 0)
    b = Node(NodeInfo('b', 'B'), bias=-1 if attenuation else 0)
    a.links.add(Link('b', 'x'))
    b.links.add(Link('a', 'x'))
    return Network([a, b])


class AccessRevisitTests(unittest.TestCase):
    def test_default_and_explicit_true_visit_each_node_once(self):
        calls = []
        class Reader(Module):
            @access(channels='x', strength=3)
            def default(self, node):
                calls.append(node.info.node_id)
            @access(channels='x', strength=3, deduplicate=True)
            def explicit(self, node):
                calls.append(node.info.node_id)
        network = pair()
        reader = Reader('reader')
        network.get('a').install(reader)
        for operation in (reader.default, reader.explicit):
            calls.clear()
            operation()
            self.assertEqual(calls, ['a', 'b'])

    def test_false_revisits_until_strength_is_blocked_and_keeps_last_results(self):
        calls, counts = [], {}
        class Reader(Module):
            @access(channels='x', strength=3, deduplicate=False)
            def read(self, node):
                key = node.info.node_id
                calls.append(key)
                counts[key] = counts.get(key, 0) + 1
                return counts[key]
        network = pair()
        reader = Reader('reader')
        network.get('a').install(reader)
        self.assertEqual(reader.read(), {'a': 2, 'b': 2})
        self.assertEqual(calls, ['a', 'b', 'a', 'b'])

    def test_false_keeps_same_layer_fanin_as_one_execution(self):
        counts = {}
        class Reader(Module):
            @access(channels='x', strength=1, deduplicate=False)
            def read(self, node):
                key = node.info.node_id
                counts[key] = counts.get(key, 0) + 1
        nodes = {key: Node(NodeInfo(key, key)) for key in 'abcd'}
        for source, target in [('a', 'b'), ('a', 'c'), ('b', 'd'), ('c', 'd')]:
            nodes[source].links.add(Link(target, 'x'))
        network = Network(nodes.values())
        reader = Reader('reader')
        nodes['a'].install(reader)
        reader.read()
        self.assertEqual(counts, dict(a=1, b=1, c=1, d=1))

    def test_false_does_not_add_cycle_detection_or_a_hidden_stop_rule(self):
        class ProbeFinished(Exception):pass
        calls = []
        class Reader(Module):
            @access(channels='x', strength=1, deduplicate=False)
            def read(self, node):
                calls.append(node.info.node_id)
                if len(calls) == 6:raise ProbeFinished()
        network = pair(attenuation=False)
        reader = Reader('reader')
        network.get('a').install(reader)
        with self.assertRaises(ProbeFinished):reader.read()
        self.assertEqual(calls, ['a', 'b', 'a', 'b', 'a', 'b'])

    def test_false_with_no_channels_still_only_visits_local_node_once(self):
        calls = []
        class Reader(Module):
            @access(deduplicate=False)
            def read(self, node):calls.append(node.info.node_id)
        network = pair(attenuation=False)
        reader = Reader('reader')
        network.get('a').install(reader)
        reader.read()
        self.assertEqual(calls, ['a'])


class AsyncAccessRevisitTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_false_revisits_the_origin_and_other_nodes(self):
        calls = []
        class Reader(Module):
            @access(channels='x', strength=3, deduplicate=False)
            async def read(self, node):
                await asyncio.sleep(0)
                calls.append(node.info.node_id)
                return calls.count(node.info.node_id)
        network = pair()
        reader = Reader('reader')
        network.get('a').install(reader)
        self.assertEqual(await reader.read(), {'a': 2, 'b': 2})
        self.assertEqual(calls, ['a', 'b', 'a', 'b'])

    async def test_cross_layer_revisit_waits_for_every_previous_layer_operation(self):
        events, counts = [], {}
        class Reader(Module):
            @access(channels='x', strength=3, deduplicate=False)
            async def read(self, node):
                key = node.info.node_id
                counts[key] = counts.get(key, 0) + 1
                event = key + str(counts[key])
                events.append('start:' + event)
                await asyncio.sleep(.01 if key == 'b' else 0)
                events.append('end:' + event)
        nodes = {key: Node(NodeInfo(key, key)) for key in 'abc'}
        for source, target in [('a', 'b'), ('a', 'c'), ('b', 'c')]:
            nodes[source].links.add(Link(target, 'x'))
        network = Network(nodes.values())
        reader = Reader('reader')
        nodes['a'].install(reader)
        await reader.read()
        self.assertEqual(counts, dict(a=1, b=1, c=2))
        self.assertLess(events.index('start:b1'), events.index('end:c1'))
        self.assertLess(events.index('end:b1'), events.index('start:c2'))
        self.assertLess(events.index('end:c1'), events.index('start:c2'))
