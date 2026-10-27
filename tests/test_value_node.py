"""真实 JSON 数据文件、原单值查询写入规则、复制及跨节点访问。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.network_saver import NetworkSaver
from domain.core import DataNode, Link, Module, Network, NodeInfo, access
from projects.knowledge_archive.nodes.value import ValueNode


class ValueNodeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.value-test-', dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)

    def node(self, key, value, *, save_data=True):
        file = self.home / (key + '.json')
        file.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return ValueNode(NodeInfo(key, key), file, save_data=save_data)

    def read(self, node):
        return node.dataer.read({'method': 'key', 'key': 'value'}).items[0]['value']

    def saver(self):
        saver = NetworkSaver()
        saver.node_types['value'] = ValueNode
        return saver

    def test_file_is_the_live_source_and_result_values_are_independent(self):
        node = self.node('value', {'count': 7, 'nested': ['原始']})
        self.assertIsInstance(node, DataNode)
        result = self.read(node)
        result['nested'].append('只改结果')
        self.assertEqual(self.read(node), {'count': 7, 'nested': ['原始']})
        node.saver.path.write_text('44', encoding='utf-8')
        self.assertEqual(self.read(node), 44)
        self.assertEqual(node.dataer.get_schema()['value_type'], 'integer')
        self.assertEqual(node.dataer.read({'method': 'key', 'key': 'value'}).sources[0]['storage'], 'file')

    def test_path_strings_are_values_and_never_read_as_documents(self):
        other = self.home / 'other.md'
        other.write_text('不应读取此正文', encoding='utf-8')
        node = self.node('value', str(other))
        self.assertEqual(self.read(node), str(other))
        result = node.dataer.write('value', {'file_path': str(other), 'node_id': 'another'})
        self.assertEqual(result.items[0]['value'], {'file_path': str(other), 'node_id': 'another'})
        self.assertEqual(other.read_text(encoding='utf-8'), '不应读取此正文')

    def test_original_key_mode_and_schema_rules(self):
        node = self.node('value', 7)
        self.assertEqual(node.dataer.read({'method': 'key', 'key': 'other'}).status, 'not_found')
        self.assertEqual(node.dataer.write('other', 99).status, 'not_found')
        self.assertEqual(node.dataer.write('value', 99, mode='insert').status, 'conflict')
        self.assertEqual(self.read(node), 7)
        result = node.dataer.write('value', [1, 2], mode='update')
        self.assertEqual(result.items, [{'value': [1, 2]}])
        self.assertEqual(result.sources[0]['operation'], 'write')
        self.assertEqual(node.dataer.get_schema()['value_type'], 'array')
        self.assertEqual(node.dataer.read({'method': 'filter', 'filters': {}}).status, 'unsupported')
        self.assertEqual(node.dataer.read({'method': 'semantic', 'query': 'x'}).status, 'unsupported')
        with self.assertRaises(TypeError):
            node.dataer.write(1, 0)
        with self.assertRaises(ValueError):
            node.dataer.read({'method': 'key', 'key': 'value', 'filters': {}})

    def test_failed_encoding_or_replacement_preserves_old_file_and_cleans_temporary(self):
        node = self.node('value', {'old': True})
        before = node.saver.path.read_bytes()
        for invalid in (float('nan'), object()):
            with self.assertRaises((ValueError, TypeError)):
                node.dataer.write('value', invalid)
            self.assertEqual(node.saver.path.read_bytes(), before)
        with patch.object(Path, 'replace', side_effect=OSError('simulated disk error')):
            with self.assertRaises(OSError):
                node.dataer.write('value', 'new')
        self.assertEqual(node.saver.path.read_bytes(), before)
        self.assertEqual(list(self.home.glob('.value-*.tmp')), [])

    def test_full_save_copies_exact_file_and_restores_an_independent_node(self):
        node = self.node('value', {'count': 7})
        node.saver.path.write_bytes(b'\xef\xbb\xbf{ "count" : 7 }\r\n')
        before = node.saver.path.read_bytes()
        file = self.home / 'network.json'
        saver = self.saver()
        saver.save(Network([node]), file)
        node.dataer.write('value', 99)
        loaded = saver.load(file).get('value')
        self.assertIsInstance(loaded, DataNode)
        self.assertIsInstance(loaded, ValueNode)
        self.assertNotEqual(loaded.saver.path, node.saver.path)
        self.assertEqual(loaded.saver.path.read_bytes(), before)
        loaded.dataer.write('value', {'count': 33})
        self.assertEqual(self.read(node), 99)
        self.assertEqual(self.read(loaded), {'count': 33})

    def test_reference_save_does_not_read_or_copy_the_file(self):
        node = self.node('value', 7, save_data=False)
        file = self.home / 'network.json'
        saver = self.saver()
        with patch.object(node.saver, 'save', side_effect=AssertionError('不能复制')):
            with patch.object(node.dataer, 'read', side_effect=AssertionError('不能读取')):
                saver.save(Network([node]), file)
        node.dataer.write('value', 33)
        loaded = saver.load(file).get('value')
        self.assertEqual(loaded.saver.path, node.saver.path)
        self.assertEqual(self.read(loaded), 33)

    def test_cross_node_reads_obey_channels_and_strength(self):
        class Reader(Module):
            @access(channels='data', strength=2)
            def numbers(self, node):
                return node.dataer.read({'method': 'key', 'key': 'value'}).items[0]['value']

        nodes = {key: self.node(key, value) for key, value in zip('abcde', [11, 23, 47, 89, 131])}
        for node in nodes.values():
            node.bias = -1
        for source, target in [('a', 'b'), ('b', 'c'), ('c', 'd')]:
            nodes[source].links.add(Link(target, 'data'))
        nodes['a'].links.add(Link('e', 'secret'))
        network = Network(nodes.values())
        reader = Reader('reader')
        nodes['a'].install(reader)
        self.assertEqual(reader.numbers(), {'a': 11, 'b': 23, 'c': 47})


if __name__ == '__main__':
    unittest.main()
