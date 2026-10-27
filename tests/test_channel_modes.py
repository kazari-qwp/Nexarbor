"""原 allow/deny 行为在新连接、模块、装饰器与保存恢复中的等价验证。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.network_saver import NetworkSaver
from domain.core import Link, Module, Network, Node, NodeInfo, access
from domain.core.channel_filters import matches, resolve
from modules.tool_discovery import ToolDiscoveryModule
from domain.core import CallableTool


def node(key):
    return Node(NodeInfo(key, key))


class ChannelModeTests(unittest.TestCase):
    def test_allow_and_deny_use_any_matching_candidate(self):
        cases = [
            ([], [], 'allow', False), ([], ['a'], 'allow', False),
            ([], ['a'], 'deny', True), (['a'], ['a'], 'deny', False),
            (['a'], ['b'], 'deny', True), (['a'], ['a', 'b'], 'deny', True),
            (['a'], ['b', 'a'], 'allow', True), (['a'], ['b'], 'allow', False),
        ]
        for items, candidates, policy, expected in cases:
            with self.subTest(items=items, candidates=candidates, policy=policy):
                self.assertEqual(matches(items, candidates, policy), expected)
        self.assertEqual(resolve(['b'], 'deny', ['a', 'b', 'c']), ('a', 'c'))

    def test_denied_link_passes_other_channels_and_still_checks_threshold(self):
        calls = []
        link = Link('b', ['secret'], threshold=2, channel_mode='deny',
                    processor=lambda value: calls.append(value) or value * 2)
        self.assertIsNone(link.transmit(2, 'secret'))
        self.assertIsNone(link.transmit(1, 'public'))
        self.assertEqual(link.transmit(2, 'public'), 4)
        self.assertEqual(calls, [2])
        self.assertTrue(Link('b', (), channel_mode='deny').allows(0, 'anything'))
        with self.assertRaises(ValueError):
            Link('b', channel_mode='invalid')

    def test_access_uses_link_matching_instead_of_prefiltering_its_channel_list(self):
        class Reader(Module):
            @access(channels=['secret', 'public'], strength=2)
            def read(self, current):
                return current.info.name

        a, b = node('a'), node('b')
        calls = []
        a.links.add(Link('b', ['secret'], channel_mode='deny',
                         processor=lambda value: calls.append(value) or value))
        network = Network([a, b])
        reader = Reader('reader')
        a.install(reader)
        self.assertEqual(reader.read(), {'a': 'a', 'b': 'b'})
        self.assertEqual(calls, [2])

    def test_module_deny_filter_uses_the_current_declared_channel_universe(self):
        class Reader(Module):
            @access()
            def read(self, current):
                return current.info.name

            @access(channels=())
            def local(self, current):
                return current.info.name

            @access(channels='secret')
            def explicit_allow(self, current):
                return current.info.name

        a, b, c, d = [node(key) for key in 'abcd']
        a.links.add(Link('b', 'public'))
        b.links.add(Link('c', 'secret'))
        a.links.add(Link('d', 'secret'))
        network = Network([a, b, c, d])
        reader = Reader('reader', channels=['secret'], channel_mode='deny', strength=3)
        a.install(reader)
        self.assertEqual(reader.read(), {'a': 'a', 'b': 'b'})
        self.assertEqual(reader.local(), {'a': 'a'})
        self.assertEqual(reader.explicit_allow(), {'a': 'a', 'd': 'd'})
        e = node('e')
        network.add(e)
        a.links.add(Link('e', 'new-channel'))
        self.assertEqual(reader.read(), {'a': 'a', 'b': 'b', 'e': 'e'})

    def test_tool_discovery_inherits_its_blacklist(self):
        a, b, c = [node(key) for key in 'abc']
        a.links.add(Link('b', 'public'))
        a.links.add(Link('c', 'secret'))
        network = Network([a, b, c])
        for item in network:
            item.install(CallableTool(item.info.node_id, lambda: None))
        discovery = ToolDiscoveryModule(['secret'], 2, channel_mode='deny')
        a.install(discovery)
        self.assertEqual([tool.name for tool in discovery.discover()], ['a', 'b'])

    def test_link_mode_survives_save_and_load(self):
        project = Path(__file__).resolve().parents[1]
        with TemporaryDirectory(prefix='.channel-test-', dir=project) as temporary:
            directory = Path(temporary).resolve()
            if not directory.is_relative_to(project):
                raise RuntimeError('测试临时目录不在项目内')
            a, b = node('a'), node('b')
            a.links.add(Link('b', ['secret'], channel_mode='deny'))
            config = directory / 'network.json'
            saver = NetworkSaver()
            saver.save(Network([a, b]), config)
            record = json.loads(config.read_text(encoding='utf-8'))
            self.assertEqual(record['nodes'][0]['links'][0]['channel_mode'], 'deny')
            loaded = saver.load(config)
            link = next(iter(loaded.get('a').links))
            self.assertIsNone(link.transmit(1, 'secret'))
            self.assertEqual(link.transmit(1, 'public'), 1)


if __name__ == '__main__':
    unittest.main()
