"""实际 CSV、SQLite 与知识目录在节点事务中的恢复。"""

from pathlib import Path
import sqlite3
import json
from tempfile import TemporaryDirectory
import unittest

from app.transactions import NodeLocks, NodeSnapshots
from domain.core import Network, NodeInfo
from projects.knowledge_archive.nodes.value import ValueNode
from projects.knowledge_archive.nodes.csv import CsvNode
from projects.knowledge_archive.nodes.sqlite import SqliteNode
from projects.knowledge_archive.nodes.collection import CollectionNode


class NodeResourceRollbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.resource-rollback-', dir=Path(__file__).resolve().parents[1] / 'build')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def locks(self, *nodes):
        network = Network(nodes)
        snapshots = NodeSnapshots(network, self.directory)
        return NodeLocks(network, snapshots)

    async def test_csv_file_and_configuration_restore(self):
        path = self.directory / 'records.csv'
        path.write_text('id,text,count\n001,原始,1\n', encoding='utf-8-sig')
        node = CsvNode(NodeInfo('csv', 'CSV'), path, 'id', {'text': 'string', 'count': 'Int64'})
        locks = self.locks(node)
        before, dtype = path.read_bytes(), node.dataer.dtype
        with self.assertRaises(ValueError):
            async with locks.transaction(['csv']):
                self.assertEqual(node.dataer.write('001', {'text': '修改', 'count': 9}).status, 'ok')
                node.dataer.dtype['count'] = 'string'
                raise ValueError('abort')
        self.assertEqual(path.read_bytes(), before)
        self.assertIs(node.dataer.dtype, dtype)
        self.assertEqual(node.dataer.dtype['count'], 'Int64')
        self.assertEqual(node.dataer.read({'method': 'key', 'key': '001'}).items[0]['text'], '原始')

    async def test_sqlite_committed_rows_restore(self):
        path = self.directory / 'records.sqlite3'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE records(id TEXT PRIMARY KEY, text TEXT)')
            db.execute('INSERT INTO records VALUES (?,?)', ('one', '原始'))
        db.close()
        node = SqliteNode(NodeInfo('sql', 'SQL'), path, 'records', 'id')
        locks = self.locks(node)
        with self.assertRaises(ValueError):
            async with locks.transaction(['sql']):
                self.assertEqual(node.dataer.write('one', {'text': '修改'}).status, 'ok')
                self.assertEqual(node.dataer.write('two', {'text': '新增'}).status, 'ok')
                raise ValueError('abort')
        self.assertEqual(node.dataer.read({'method': 'key', 'key': 'one'}).items[0]['text'], '原始')
        self.assertEqual(node.dataer.read({'method': 'key', 'key': 'two'}).status, 'not_found')

    async def test_collection_directory_restores_revision_and_invalidates_store_cache(self):
        node = CollectionNode(NodeInfo('wiki', 'Wiki'), self.directory / 'wiki', storage='wiki')
        command = lambda **args: node.dataer.write('$command', {'operation': 'put', 'arguments': args})
        self.assertEqual(command(key='guide', value='原始正文').status, 'ok')
        locks = self.locks(node)
        old_store = node.dataer.store
        with self.assertRaises(ValueError):
            async with locks.transaction(['wiki']):
                self.assertEqual(command(key='guide', value='修改正文', expected_version=1).status, 'ok')
                (node.saver.path / 'new-resource.txt').write_text('new', encoding='utf-8')
                raise ValueError('abort')
        self.assertIsNone(node.dataer._store)
        record = node.dataer.read({'method': 'key', 'key': 'guide'}).items[0]
        self.assertEqual(record['content'], '原始正文')
        self.assertEqual(record['version'], 1)
        self.assertFalse((node.saver.path / 'new-resource.txt').exists())
        self.assertIsNot(node.dataer.store, old_store)

    async def test_shared_file_requires_both_nodes_in_the_same_group(self):
        path = self.directory / 'records.csv'
        path.write_text('id,text\n001,原始\n', encoding='utf-8-sig')
        a = CsvNode(NodeInfo('a', 'A'), path, 'id')
        b = CsvNode(NodeInfo('b', 'B'), path, 'id')
        locks = self.locks(a, b)
        with self.assertRaisesRegex(ValueError, 'locked together'):
            async with locks.transaction(['a']):
                pass
        async with locks.transaction(['a', 'b']):
            self.assertEqual(a.dataer.write('001', {'text': '提交'}).status, 'ok')
        self.assertEqual(b.dataer.read({'method': 'key', 'key': '001'}).items[0]['text'], '提交')

    async def test_value_json_file_restores(self):
        path = self.directory / 'value.json'
        path.write_text('{"number":1}', encoding='utf-8')
        node = ValueNode(NodeInfo('value', 'Value'), path)
        locks = self.locks(node)
        with self.assertRaises(ValueError):
            async with locks.transaction(['value']):
                self.assertEqual(node.dataer.write('value', {'number': 2}).status, 'ok')
                raise ValueError('abort')
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'number': 1})
