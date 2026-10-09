"""节点描述、动态结构、轻量目录与配置兼容。"""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
from datanet.network import Network
from datanet.nodes import Node, ValueNode, CsvNode, SqliteNode
from datanet.serialization import save_network, load_network
from datanet.nodes.local_tools import attach_local_tools
from datanet.tool_access import list_nodes


class SchemaTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)

    def test_base_description_and_no_local_schema(self):
        node = Node("root", "根", None, description="组合其他节点")
        self.assertEqual(node.describe()["description"], "组合其他节点")
        self.assertIsNone(node.schema)
        self.assertIsNone(node.get_schema())
        with self.assertRaises(TypeError):
            Node("bad", "bad", None, description=None)

    def test_value_schema_changes_with_value_without_exposing_content(self):
        node = ValueNode("v", "单值", "value", 42)
        self.assertEqual(node.schema["value_type"], "integer")
        schema = node.schema
        schema["key"] = "bad"
        self.assertEqual(node.schema["key"], "value")
        for value, expected in ((True, "boolean"), (None, "null"), ({"secret": "private"}, "object")):
            node.write("value", value)
            self.assertEqual(node.schema["value_type"], expected)
        self.assertNotIn("private", json.dumps(node.schema))

    def test_csv_uses_header_and_configured_types_only(self):
        path = self.base / "records.csv"
        path.write_text("id,amount,unknown\n001,not-an-integer,text\n", encoding="utf-8")
        node = CsvNode("c", "CSV", "records", path, "id", {"amount": "Int64"})
        with patch("datanet.nodes.csv_node.csv_node.pd.read_csv", wraps=pd.read_csv) as read:
            schema = node.schema
            self.assertEqual(read.call_args.kwargs["nrows"], 0)
        self.assertEqual(schema["fields"]["id"]["type"], "string")
        self.assertEqual(schema["fields"]["amount"]["type"], "Int64")
        self.assertIsNone(schema["fields"]["unknown"]["type"])
        self.assertEqual(node.get("001").status, "error")

    def test_sqlite_schema_tracks_actual_table_changes(self):
        path = self.base / "db.sqlite"
        with closing(sqlite3.connect(path)) as connection:
            with connection:
                connection.execute("CREATE TABLE records (id TEXT PRIMARY KEY, amount INTEGER NOT NULL DEFAULT 0)")
        node = SqliteNode("s", "SQL", "records", path, "records", "id")
        before = path.read_bytes()
        schema = node.get_schema()
        self.assertEqual(schema["fields"]["id"]["primary_key_order"], 1)
        self.assertTrue(schema["fields"]["amount"]["not_null"])
        self.assertEqual(schema["fields"]["amount"]["default"], "0")
        self.assertEqual(path.read_bytes(), before)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("ALTER TABLE records ADD COLUMN note TEXT")
        self.assertIn("note", node.get_schema()["fields"])

    def test_missing_storage_has_explicit_schema_error_without_creation(self):
        for node in (CsvNode("c", "CSV", "records", self.base / "missing.csv", "id"),
                     SqliteNode("s", "SQL", "records", self.base / "missing.db", "records", "id")):
            description = node.describe()
            self.assertIsNone(description["schema"])
            self.assertTrue(description["schema_error"])
            attach_local_tools(node)
            self.assertEqual(node.invoke_tool("get_schema").status, "error")
        self.assertFalse((self.base / "missing.db").exists())
        self.assertFalse((self.base / "missing.csv").exists())

    def test_description_roundtrip_without_stored_schema(self):
        network = Network()
        node = ValueNode("v", "单值", "number", 1, description="测试数字")
        network.add_node(node)
        path = self.base / "network.json"
        save_network(network, path)
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["nodes"][0]["description"], "测试数字")
        self.assertNotIn("schema", document["nodes"][0])
        self.assertEqual(load_network(path).nodes["v"].describe(), node.describe())
        document["nodes"][0].pop("description")
        path.write_text(json.dumps(document), encoding="utf-8")
        self.assertEqual(load_network(path).nodes["v"].description, "")
        document["nodes"][0]["description"] = None
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_network(path)

    def test_directory_does_not_load_schemas(self):
        network = Network()
        node = Node("root", "根", None, description="轻量目录")
        node.get_schema = Mock(side_effect=RuntimeError("不应读取"))
        network.add_node(node)
        result = list_nodes(network, "root")
        self.assertEqual(result.items[0]["description"], "轻量目录")
        self.assertNotIn("schema", result.items[0])
        node.get_schema.assert_not_called()

    def test_csv_missing_key_is_not_a_successful_schema(self):
        path = self.base / "bad.csv"
        path.write_text("other\n1\n", encoding="utf-8")
        node = CsvNode("c", "CSV", "records", path, "id")
        self.assertIn("缺少主键", node.describe()["schema_error"])


if __name__ == "__main__":
    unittest.main()
