"""数据节点与真实 Markdown 文件的读写验证。"""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from domain.data_node import DataNode
from domain.link import Link
from domain.markdown_data import MarkdownData
from domain.markdownNode import MarkdownDataer, MarkdownNode, MarkdownSaver
from domain.module import Module
from domain.node import Node
from domain.node_info import NodeInfo
from domain.tool import CallableTool


class DataNodeTests(unittest.TestCase):
    def setUp(self):
        project = Path(__file__).resolve().parents[1]
        temporary = TemporaryDirectory(prefix='.markdown-test-', dir=project)
        self.directory = Path(temporary.name).resolve()
        if not self.directory.is_relative_to(project):
            raise RuntimeError('测试临时目录不在项目内')
        self.addCleanup(temporary.cleanup)
        self.path = self.directory / 'source.md'
        self.path.write_bytes('# 标题\r\n\r\n中文段落。\r\n'.encode('utf-8'))

    def test_markdown_reads_and_writes_the_real_file(self):
        data = MarkdownData(self.path)
        dataer = MarkdownDataer(data)
        node = DataNode(NodeInfo('document', '文档'), dataer=dataer, saver=MarkdownSaver(data))
        self.assertIsInstance(node, Node)
        self.assertEqual(dataer.read(), self.path.read_bytes().decode('utf-8'))
        replacement = '## 新标题\n\n- 第一项\n- 第二项\n'
        node.dataer.write(replacement)
        self.assertEqual(self.path.read_bytes(), replacement.encode('utf-8'))
        self.path.write_bytes('外部修改'.encode('utf-8'))
        self.assertEqual(node.dataer.read(), '外部修改')
        node.dataer.write('')
        self.assertEqual(self.path.read_bytes(), b'')

    def test_data_node_requires_access_and_save_implementations(self):
        data = MarkdownData(self.path)
        with self.assertRaises(TypeError):
            DataNode(NodeInfo('document', '文档'), dataer=None, saver=MarkdownSaver(data))
        with self.assertRaises(TypeError):
            DataNode(NodeInfo('document', '文档'), dataer=MarkdownDataer(data), saver=None)

    def test_markdown_node_shares_a_file_between_its_components(self):
        node = MarkdownNode(NodeInfo('document', '文档'), self.path, save_data=False)
        self.assertIs(node.dataer.data, node.saver.data)
        self.assertFalse(node.save_data)
        snapshot = self.directory / 'copies' / 'snapshot.md'
        node.saver.save(snapshot)
        self.assertEqual(snapshot.read_bytes(), self.path.read_bytes())
        node.dataer.write('源文件的新内容')
        self.assertNotEqual(snapshot.read_bytes(), self.path.read_bytes())

    def test_data_node_retains_module_tool_and_link_capabilities(self):
        node = MarkdownNode(NodeInfo('document', '文档'), self.path)
        action = CallableTool('read_document', node.dataer.read)
        module = Module('document_tools', tools=[action])
        link = Link('other')
        node.install(module)
        node.links.add(link)
        node.dataer.write('# 内容')
        self.assertEqual(node.tools.list()[0].invoke(), '# 内容')
        self.assertEqual(list(node.links), [link])
        self.assertTrue(node.remove(module))
        self.assertEqual(list(node.tools), [])
        self.assertEqual(node.dataer.read(), '# 内容')


if __name__ == '__main__':
    unittest.main()
