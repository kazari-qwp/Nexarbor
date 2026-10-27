"""原 pandas/SQLite 规则、真实文件、参数恢复与 WAL 一致快照。"""

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from app.network_saver import NetworkSaver
from domain.core import DataNode, Network, NodeInfo
from projects.knowledge_archive.nodes.csv import CsvNode
from projects.knowledge_archive.nodes.sqlite import SqliteNode


class RecordNodeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix='.record-test-', dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)

    def csv(self, content='id,text,count\n001,NA,1\n002,,2\n'):
        path = self.home / 'records.csv'
        path.write_text(content, encoding='utf-8-sig')
        return CsvNode(NodeInfo('csv', 'csv'), path, 'id', {'text': 'string', 'count': 'Int64'})

    def sql(self):
        path = self.home / 'records.sqlite3'
        connection = sqlite3.connect(path)
        with connection:
            connection.execute('CREATE TABLE records(id TEXT PRIMARY KEY, text TEXT, metadata TEXT)')
            connection.execute('INSERT INTO records VALUES (?,?,?)', ('one', '原始记录', '{"tag":"a"}'))
        connection.close()
        return SqliteNode(NodeInfo('sql', 'sql'), path, 'records', 'id')

    def read(self, node, key):
        return node.dataer.read({'method': 'key', 'key': key})

    def saver(self):
        saver = NetworkSaver()
        saver.node_types.update(csv=CsvNode, sqlite=SqliteNode)
        return saver

    def test_csv_preserves_key_strings_na_text_and_nullable_types(self):
        node = self.csv()
        self.assertIsInstance(node, DataNode)
        self.assertEqual(self.read(node, '001').items[0], {'id': '001', 'text': 'NA', 'count': 1})
        self.assertIsNone(self.read(node, '002').items[0]['text'])
        self.assertEqual(node.dataer.get_schema()['fields']['count']['type'], 'Int64')
        filtered = node.dataer.read({'method': 'filter', 'filters': {'text': None, 'count': 2}})
        self.assertEqual(filtered.items[0]['id'], '002')

    def test_csv_write_modes_and_failed_conversion_leave_original_file(self):
        node = self.csv()
        before = node.saver.path.read_bytes()
        self.assertEqual(node.dataer.write('001', {'text': 'duplicate'}, mode='insert').status, 'conflict')
        self.assertEqual(node.dataer.write('missing', {'text': 'x'}, mode='update').status, 'not_found')
        self.assertEqual(node.dataer.write('001', {'count': 'not a number'}).status, 'error')
        self.assertEqual(node.saver.path.read_bytes(), before)
        result = node.dataer.write('001', {'count': 9, 'text': '更新'})
        self.assertEqual(result.items[0]['count'], 9)
        self.assertEqual(self.read(node, '001').items[0]['text'], '更新')

    def test_csv_duplicate_keys_and_batch_rules_are_retained(self):
        node = self.csv('id,text,count\nx,first,1\nx,second,2\n')
        self.assertEqual(self.read(node, 'x').status, 'error')
        self.assertEqual(node.dataer.write('x', {'text': 'changed'}).status, 'error')
        node = self.csv()
        before = node.saver.path.read_bytes()
        self.assertEqual(node.dataer.write_many([{'id': 'x'}, {'id': 'x'}]).status, 'error')
        self.assertEqual(node.saver.path.read_bytes(), before)
        result = node.dataer.write_many([{'id': '001', 'text': 'batch', 'count': 3},
                                        {'id': '003', 'text': 'new', 'count': 4}])
        self.assertEqual(result.items, [{'written': 2}])
        self.assertEqual(self.read(node, '003').items[0]['count'], 4)

    def test_csv_unknown_fields_and_non_scalar_filters_are_rejected(self):
        node = self.csv()
        with self.assertRaises(ValueError):
            node.dataer.write('001', {'unknown': 1})
        with self.assertRaises(TypeError):
            node.dataer.read({'method': 'filter', 'filters': {'id': ['001']}})
        self.assertEqual(node.dataer.read({'method': 'filter', 'filters': {'unknown': 1}}).status, 'error')

    def test_sqlite_parameterized_keys_and_write_modes(self):
        node = self.sql()
        self.assertIsInstance(node, DataNode)
        self.assertEqual(node.dataer.write('one', {'text': 'x'}, mode='insert').status, 'conflict')
        self.assertEqual(node.dataer.write('missing', {'text': 'x'}, mode='update').status, 'not_found')
        key = "x' OR 1=1; --"
        self.assertEqual(node.dataer.write(key, {'text': '安全参数'}).status, 'ok')
        self.assertEqual(self.read(node, key).items[0]['text'], '安全参数')
        self.assertEqual(self.read(node, 'one').items[0]['text'], '原始记录')
        self.assertTrue(node.dataer.get_schema()['fields']['id']['primary_key_order'])

    def test_sqlite_filters_metadata_null_and_rejected_columns(self):
        node = self.sql()
        node.dataer.write('two', {'text': None, 'metadata': '{"tag":"b"}'})
        result = node.dataer.read({'method': 'filter', 'filters': {'metadata.tag': 'b', 'text': None}})
        self.assertEqual(result.items[0]['id'], 'two')
        self.assertEqual(node.dataer.read({'method': 'filter', 'filters': {'unknown': 'x'}}).status, 'error')
        self.assertEqual(node.dataer.read({'method': 'filter', 'filters': {'metadata.x) OR': 'x'}}).status, 'error')

    def test_sqlite_batch_failure_rolls_back_all_rows(self):
        node = self.sql()
        connection = sqlite3.connect(node.saver.path)
        with connection:
            connection.execute('CREATE UNIQUE INDEX unique_text ON records(text)')
        connection.close()
        result = node.dataer.write_many([{'id': 'first', 'text': 'same'}, {'id': 'second', 'text': 'same'}])
        self.assertEqual(result.status, 'error')
        self.assertEqual(self.read(node, 'first').status, 'not_found')
        self.assertEqual(self.read(node, 'one').items[0]['text'], '原始记录')

    def test_csv_and_sqlite_network_roundtrip_preserves_parameters_and_independent_files(self):
        csv, sql = self.csv(), self.sql()
        config = self.home / 'network.json'
        saver = self.saver()
        saver.save(Network([csv, sql]), config)
        loaded = saver.load(config)
        for original in (csv, sql):
            copied = loaded.get(original.info.node_id)
            self.assertIsInstance(copied, DataNode)
            self.assertNotEqual(original.saver.path, copied.saver.path)
            self.assertEqual(copied.parameters, original.parameters)
        copied_csv, copied_sql = loaded.get('csv'), loaded.get('sql')
        copied_csv.dataer.write('001', {'text': '仅副本'})
        copied_sql.dataer.write('one', {'text': '仅副本'})
        self.assertEqual(self.read(csv, '001').items[0]['text'], 'NA')
        self.assertEqual(self.read(sql, 'one').items[0]['text'], '原始记录')

    def test_sqlite_snapshot_includes_committed_wal_pages(self):
        node = self.sql()
        connection = sqlite3.connect(node.saver.path)
        self.addCleanup(connection.close)
        connection.execute('PRAGMA journal_mode=WAL')
        with connection:
            connection.execute('INSERT INTO records VALUES (?,?,?)', ('wal', 'WAL已提交', '{}'))
        self.assertTrue(Path(str(node.saver.path) + '-wal').exists())
        config = self.home / 'network.json'
        saver = self.saver()
        saver.save(Network([node]), config)
        copied = saver.load(config).get('sql')
        self.assertEqual(self.read(copied, 'wal').items[0]['text'], 'WAL已提交')

    def test_missing_sources_fail_reads_without_creating_empty_sqlite_files(self):
        node = SqliteNode(NodeInfo('missing', 'missing'), self.home / 'missing.db', 'records', 'id')
        self.assertEqual(self.read(node, 'one').status, 'error')
        self.assertFalse(node.saver.path.exists())


if __name__ == '__main__':
    unittest.main()
