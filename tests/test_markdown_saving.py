"""验证网络保存开关对 Markdown 源文件和副本的实际影响。"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from app.network_saver import NetworkSaver
from domain.link import Link
from domain.markdownNode import MarkdownNode
from domain.network import Network
from domain.node import Node
from domain.node_info import NodeInfo


class MarkdownSavingTests(unittest.TestCase):
    def setUp(self):
        project = Path(__file__).resolve().parents[1]
        temporary = TemporaryDirectory(prefix='.markdown-save-test-', dir=project)
        self.directory = Path(temporary.name).resolve()
        if not self.directory.is_relative_to(project):
            raise RuntimeError('测试临时目录不在项目内')
        self.addCleanup(temporary.cleanup)
        self.source = self.directory / 'source.md'
        self.original = '# 源文件\r\n\r\n**中文内容**\r\n'.encode('utf-8')
        self.source.write_bytes(self.original)
        self.config = self.directory / 'network.json'
        self.saver = NetworkSaver()

    def read_record(self):
        return json.loads(self.config.read_text(encoding='utf-8'))['nodes'][0]

    def test_true_copies_the_file_and_loads_an_independent_markdown_node(self):
        node = MarkdownNode(NodeInfo('document', '文档'), self.source, save_data=True)
        node.links.add(Link('document'))
        # 网络保存应直接复制文件，不依赖访问器返回的任何内存文本。
        with patch.object(node.dataer, 'read', return_value='not the source file'):
            self.saver.save(Network([node]), self.config)
        data = self.read_record()['data']
        self.assertTrue(data['save_data'])
        self.assertFalse(Path(data['path']).is_absolute())
        snapshot = self.config.parent / data['path']
        self.assertNotEqual(snapshot.resolve(), self.source.resolve())
        self.assertEqual(snapshot.read_bytes(), self.original)
        self.assertEqual(node.saver.path, self.source.resolve())
        self.source.write_bytes('保存后修改原文件'.encode('utf-8'))
        loaded = self.saver.load(self.config).get('document')
        self.assertIsInstance(loaded, MarkdownNode)
        self.assertTrue(loaded.save_data)
        self.assertEqual(loaded.dataer.read().encode('utf-8'), self.original)
        self.assertEqual(next(iter(loaded.links)).target_id, 'document')
        loaded.dataer.write('修改副本')
        self.assertEqual(snapshot.read_bytes(), '修改副本'.encode('utf-8'))
        self.assertEqual(self.source.read_bytes(), '保存后修改原文件'.encode('utf-8'))

    def test_false_only_records_the_source_path(self):
        node = MarkdownNode(NodeInfo('document', '文档'), self.source, save_data=False)
        node.bias = -1
        with patch.object(node.saver, 'save', side_effect=AssertionError('must not save data')):
            with patch.object(node.dataer, 'read', side_effect=AssertionError('must not read data')):
                self.saver.save(Network([node]), self.config)
        data = self.read_record()['data']
        self.assertFalse(data['save_data'])
        self.assertEqual(Path(data['path']), self.source.resolve())
        self.assertFalse((self.directory / 'network_data').exists())
        self.assertEqual(self.source.read_bytes(), self.original)
        self.source.write_bytes('外部文件的最新内容'.encode('utf-8'))
        loaded = self.saver.load(self.config).get('document')
        self.assertFalse(loaded.save_data)
        self.assertEqual(loaded.bias, -1)
        self.assertEqual(loaded.dataer.read(), '外部文件的最新内容')
        self.assertEqual(loaded.saver.path, self.source.resolve())

    def test_each_full_save_creates_a_new_copy(self):
        node = MarkdownNode(NodeInfo('document', '文档'), self.source)
        network = Network([node])
        self.saver.save(network, self.config)
        first = self.directory / self.read_record()['data']['path']
        node.dataer.write('第二次保存的内容')
        self.saver.save(network, self.config)
        second = self.directory / self.read_record()['data']['path']
        self.assertNotEqual(first, second)
        self.assertEqual(first.read_bytes(), self.original)
        self.assertEqual(second.read_bytes(), self.source.read_bytes())

    def test_failed_save_keeps_old_config_and_copies_and_removes_new_copy(self):
        document = MarkdownNode(NodeInfo('document', '文档'), self.source)
        other = Node(NodeInfo('other', '另一个节点'))
        network = Network([document, other])
        self.saver.save(network, self.config)
        previous = self.config.read_bytes()
        directory = self.directory / 'network_data'
        old_copies = set(directory.iterdir())
        other.links.add(Link('document', processor=lambda value: value))
        with self.assertRaisesRegex(ValueError, '自定义处理函数'):
            self.saver.save(network, self.config)
        self.assertEqual(self.config.read_bytes(), previous)
        self.assertEqual(set(directory.iterdir()), old_copies)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(list(self.directory.glob('*.tmp')), [])

    def test_missing_source_is_reported_on_load(self):
        node = MarkdownNode(NodeInfo('document', '文档'), self.source, save_data=False)
        self.saver.save(Network([node]), self.config)
        self.source.unlink()
        with self.assertRaises(FileNotFoundError):
            self.saver.load(self.config)

    def test_bad_write_does_not_truncate_the_source_file(self):
        node = MarkdownNode(NodeInfo('document', '文档'), self.source)
        with self.assertRaises(TypeError):
            node.dataer.write(None)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_save_flag_requires_a_boolean(self):
        with self.assertRaises(TypeError):
            MarkdownNode(NodeInfo('document', '文档'), self.source, save_data='false')


if __name__ == '__main__':
    unittest.main()
