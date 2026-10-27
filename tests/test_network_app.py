"""网络配置存取与内存运行生命周期的验证。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import unittest

from domain.core import AverageAggregation, MaxAggregation, MinAggregation, SumAggregation
from app.network_runner import NetworkRunner
from app.network_saver import NetworkSaver
from domain.core import DEFAULT_CHANNEL, Link, Multiplier
from domain.core import Network
from domain.core import Node
from domain.core import NodeInfo


class NetworkAppTests(unittest.TestCase):
    def setUp(self):
        self.project = Path(__file__).resolve().parents[1]
        self.temporary = TemporaryDirectory(prefix=".network-test-", dir=self.project)
        self.directory = Path(self.temporary.name).resolve()
        if not self.directory.is_relative_to(self.project):
            raise RuntimeError("测试临时目录不在项目内")
        self.addCleanup(self.temporary.cleanup)
        self.path = self.directory / "network.json"

    def make_network(self):
        first = Node(NodeInfo('first', '第一个节点', '说明'))
        second = Node(NodeInfo('second', '第二个节点'))
        first.links.add(Link('second', 'chat', threshold=3, processor=Multiplier(2)))
        return Network([first, second])

    def test_network_reuses_same_node_and_rejects_duplicate_ids(self):
        network = self.make_network()
        network.add(network.get('first'))
        self.assertEqual(len(network), 2)
        with self.assertRaises(ValueError):
            network.add(Node(NodeInfo('first', '另一个节点')))

    def test_a_node_cannot_silently_switch_its_access_resolver_to_another_network(self):
        network = self.make_network()
        first = network.get('first')
        with self.assertRaisesRegex(ValueError, '不能同时属于两个网络'):
            Network([first])
        self.assertIs(network.get('first'), first)

    def test_save_and_load_preserve_node_information_and_links(self):
        saver = NetworkSaver()
        original = self.make_network()
        saver.save(original, self.path)
        loaded = saver.load(self.path)
        self.assertEqual([node.info for node in loaded], [node.info for node in original])
        link = loaded.get('first').links.list()[0]
        self.assertEqual(link.target_id, 'second')
        self.assertEqual(link.channels, ('chat',))
        self.assertIsNone(link.transmit(2, 'chat'))
        self.assertEqual(link.transmit(3, 'chat'), 6)
        self.assertEqual(len(loaded.get('first').modules), 0)

    def test_minimal_config_uses_default_connection_values(self):
        config = {"nodes": [
            {"node_id": "a", "name": "A", "links": [{"target_id": "b"}]},
            {"node_id": "b", "name": "B"},
        ]}
        self.path.write_text(json.dumps(config), encoding='utf-8')
        network = NetworkSaver().load(self.path)
        link = next(iter(network.get('a').links))
        self.assertEqual(link.channels, (DEFAULT_CHANNEL,))
        self.assertEqual(link.transmit(4), 4)

    def test_all_builtin_aggregation_strategies_survive_save_and_load(self):
        strategies = [SumAggregation, MaxAggregation, MinAggregation, AverageAggregation]
        nodes = [Node(NodeInfo(str(index), str(index)), aggregation=strategy(), bias=index - 1)
                 for index, strategy in enumerate(strategies)]
        saver = NetworkSaver()
        saver.save(Network(nodes), self.path)
        document = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual([item['aggregation'] for item in document['nodes']], ['sum', 'max', 'min', 'average'])
        loaded = saver.load(self.path)
        self.assertEqual([type(node.aggregation) for node in loaded], strategies)
        self.assertEqual([node.bias for node in loaded], [-1, 0, 1, 2])

    def test_unknown_aggregation_is_rejected_on_load(self):
        self.path.write_text(json.dumps({"nodes": [
            {"node_id": "a", "name": "A", "aggregation": "unknown"},
        ]}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '未知的节点汇合方法'):
            NetworkSaver().load(self.path)

    def test_failed_save_preserves_previous_file(self):
        saver = NetworkSaver()
        network = self.make_network()
        saver.save(network, self.path)
        previous = self.path.read_bytes()
        network.get('first').links.add(Link('second', processor=lambda value: value))
        with self.assertRaisesRegex(ValueError, '自定义处理函数'):
            saver.save(network, self.path)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.directory.glob('*.tmp')), [])

    def test_invalid_targets_and_duplicate_node_ids_are_rejected_on_load(self):
        self.path.write_text(json.dumps({"nodes": [
            {"node_id": "a", "name": "A", "links": [{"target_id": "missing"}]},
        ]}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '目标不存在'):
            NetworkSaver().load(self.path)
        self.path.write_text(json.dumps({"nodes": [
            {"node_id": "a", "name": "A"},
            {"node_id": "a", "name": "Other A"},
        ]}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '节点 ID 冲突'):
            NetworkSaver().load(self.path)

    def test_unknown_processor_is_rejected(self):
        self.path.write_text(json.dumps({"nodes": [
            {"node_id": "a", "name": "A", "links": [
                {"target_id": "a", "processor": {"type": "unknown"}},
            ]},
        ]}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '未知'):
            NetworkSaver().load(self.path)

    def test_runner_loads_once_and_triggers_in_memory(self):
        NetworkSaver().save(self.make_network(), self.path)
        runner = NetworkRunner.from_file(self.path)
        self.addCleanup(runner.close)
        self.path.write_text('invalid json after loading', encoding='utf-8')
        result = runner.trigger(lambda network: network.get('first').info.name)
        self.assertEqual(result, '第一个节点')
        runner.trigger(lambda network: network.add(Node(NodeInfo('third', '第三个节点'))))
        self.assertEqual(len(runner.network), 3)

    def test_run_waits_for_close_and_rejects_later_operations(self):
        runner = NetworkRunner(self.make_network())
        exited = Event()

        def run():
            runner.run()
            exited.set()

        thread = Thread(target=run, daemon=True)
        thread.start()
        try:
            self.assertFalse(exited.wait(0.02))
            self.assertEqual(runner.trigger(len), 2)
        finally:
            runner.close()
            thread.join(timeout=1)
        self.assertTrue(exited.is_set())
        self.assertFalse(thread.is_alive())
        with self.assertRaises(RuntimeError):
            runner.trigger(len)
        runner.close()

    def test_trigger_error_is_returned_to_caller_without_closing_runner(self):
        runner = NetworkRunner(self.make_network())
        self.addCleanup(runner.close)

        def fail(network):
            raise ValueError('operation failed')

        with self.assertRaisesRegex(ValueError, 'operation failed'):
            runner.trigger(fail)
        self.assertEqual(runner.trigger(len), 2)
        self.assertFalse(runner.closed)


if __name__ == '__main__':
    unittest.main()
