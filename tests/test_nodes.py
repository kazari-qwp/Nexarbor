"""通用 SQLite 节点测试；使用独立数据库，不请求 API。"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from datanet.nodes.sqlite_node import SqliteNode


class SqliteNodeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "sample.db"
        self.execute("CREATE TABLE facts (id TEXT, value TEXT)")
        self.execute("INSERT INTO facts VALUES (?, ?)", ("001", "hello"))
        self.node = self.make_node()

    def execute(self, sql, parameters=()):
        connection = sqlite3.connect(self.path)
        try:
            connection.execute(sql, parameters)
            connection.commit()
        finally:
            connection.close()

    def make_node(self, table_name="facts", key_column="id", db_path=None):
        return SqliteNode(
            "facts_node", "事实", "fact", db_path or self.path, table_name, key_column
        )

    def test_read_returns_row_and_source(self):
        result = self.node.get("001")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.items, [{"id": "001", "value": "hello"}])
        self.assertEqual(result.sources[0]["database"], self.path.resolve().as_posix())
        self.assertEqual(result.sources[0]["key_column"], "id")

    def test_unknown_key_is_not_found(self):
        self.assertEqual(self.node.get("missing").status, "not_found")

    def test_key_is_not_sql(self):
        self.assertEqual(self.node.get("001' OR 1=1 --").status, "not_found")

    def test_duplicate_key_is_error(self):
        self.execute("INSERT INTO facts VALUES (?, ?)", ("001", "second"))
        self.assertEqual(self.node.get("001").status, "error")

    def test_missing_database_does_not_create_file(self):
        path = Path(self.directory.name) / "missing.db"
        self.assertEqual(self.make_node(db_path=path).get("001").status, "error")
        self.assertFalse(path.exists())

    def test_missing_table_is_error(self):
        self.assertEqual(self.make_node(table_name="missing").get("001").status, "error")

    def test_missing_column_is_error(self):
        self.assertEqual(self.make_node(key_column="missing").get("001").status, "error")

    def test_null_value_stays_none(self):
        self.execute("INSERT INTO facts VALUES (?, NULL)", ("null",))
        self.assertIsNone(self.node.get("null").items[0]["value"])

    def test_other_table_and_key_can_be_configured(self):
        self.execute("CREATE TABLE contacts (username TEXT PRIMARY KEY, phone TEXT)")
        self.execute("INSERT INTO contacts VALUES ('alice', '012345')")
        result = self.make_node("contacts", "username").get("alice")
        self.assertEqual(result.items[0]["phone"], "012345")

    def test_identifiers_with_quotes_and_chinese(self):
        self.execute('CREATE TABLE "资料" ("编""号" TEXT, "内容" TEXT)')
        self.execute('INSERT INTO "资料" VALUES (?, ?)', ("A", "测试"))
        self.assertEqual(self.make_node("资料", '编"号').get("A").status, "ok")

    def test_table_name_is_not_sql(self):
        result = self.make_node(table_name='facts"; DROP TABLE facts; --').get("001")
        self.assertEqual(result.status, "error")
        self.assertEqual(self.node.get("001").status, "ok")

    def test_non_string_key_is_rejected(self):
        with self.assertRaises(TypeError):
            self.node.get(1)


if __name__ == "__main__":
    unittest.main()
