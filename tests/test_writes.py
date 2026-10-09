"""本地写入、定向网络路由和 Agent 写后读验证。"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from contextlib import closing

from openai.types.chat import ChatCompletion
from datanet.network import Network
from datanet.nodes import Node, ValueNode, CsvNode, SqliteNode
from applications.network_demo.setup import build_agent_network


class WriteTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.csv = self.base / "records.csv"
        self.csv.write_text("id,amount,note\n001,80,old\n", encoding="utf-8-sig")
        self.db = self.base / "rules.db"
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute('CREATE TABLE records (id TEXT PRIMARY KEY, amount INTEGER NOT NULL CHECK(amount >= 0), note TEXT)')
                connection.execute("INSERT INTO records VALUES ('001',80,'old')")
        self.nodes = [CsvNode("csv", "CSV", "record", self.csv, "id", {"amount": "Int64"}),
                      SqliteNode("sql", "SQLite", "record", self.db, "records", "id")]

    def test_record_insert_update_and_upsert(self):
        for node in self.nodes:
            with self.subTest(node=node.node_id):
                self.assertEqual(node.write("002", {"amount": 12, "note": "new"}, mode="insert").status, "ok")
                self.assertEqual(node.write("002", {"amount": 9}, mode="update").status, "ok")
                self.assertEqual(node.get("002").items[0], {"id": "002", "amount": 9, "note": "new"})
                self.assertEqual(node.write("003", {"amount": 5}, mode="upsert").status, "ok")
                result = node.write("001", {"amount": 90})
                self.assertEqual(result.items[0]["note"], "old")
                self.assertEqual(result.sources[0]["operation"], "write")

    def test_conflicts_and_missing_update_do_not_modify(self):
        for node in self.nodes:
            self.assertEqual(node.write("001", {"amount": 99}, mode="insert").status, "conflict")
            self.assertEqual(node.write("404", {"amount": 99}, mode="update").status, "not_found")
            self.assertEqual(node.get("001").items[0]["amount"], 80)
            self.assertEqual(node.get("404").status, "not_found")

    def test_invalid_fields_keys_and_modes_do_not_modify(self):
        for node in self.nodes:
            for value in ({"unknown": 1}, {"id": "other"}, []):
                with self.subTest(node=node.node_id, value=value), self.assertRaises((TypeError, ValueError)):
                    node.write("001", value)
            for key, mode in ((None, "update"), ("", "upsert"), ("001", "wrong")):
                with self.assertRaises((TypeError, ValueError)):
                    node.write(key, {"amount": 99}, mode=mode)
            self.assertEqual(node.get("001").items[0]["amount"], 80)

    def test_csv_dtype_failure_preserves_file(self):
        before = self.csv.read_bytes()
        self.assertEqual(self.nodes[0].write("001", {"amount": "invalid"}).status, "error")
        self.assertEqual(self.csv.read_bytes(), before)
        self.assertEqual(list(self.base.glob("*.csv")), [self.csv])

    def test_sqlite_constraint_failure_rolls_back(self):
        self.assertEqual(self.nodes[1].write("001", {"amount": -1}).status, "error")
        self.assertEqual(self.nodes[1].get("001").items[0]["amount"], 80)
        self.assertEqual(self.nodes[1].write("002", {"note": "missing amount"}).status, "error")
        self.assertEqual(self.nodes[1].get("002").status, "not_found")

    def test_csv_replace_failure_preserves_original_and_cleans_temp(self):
        from unittest.mock import patch
        before = self.csv.read_bytes()
        with patch("datanet.nodes.csv_node.csv_node.os.replace", side_effect=PermissionError("locked")):
            self.assertEqual(self.nodes[0].write("001", {"amount": 99}).status, "error")
        self.assertEqual(self.csv.read_bytes(), before)
        self.assertEqual(list(self.base.glob("*.csv")), [self.csv])

    def test_duplicate_primary_keys_are_rejected_without_changes(self):
        self.csv.write_text("id,amount,note\n001,80,a\n001,81,b\n", encoding="utf-8-sig")
        with closing(sqlite3.connect(self.db)) as connection:
            with connection:
                connection.execute("CREATE TABLE duplicates (id TEXT, amount INTEGER)")
                connection.executemany("INSERT INTO duplicates VALUES (?, ?)", [("001",80),("001",81)])
        sqlite_node = SqliteNode("dup", "duplicates", "record", self.db, "duplicates", "id")
        before = self.csv.read_bytes()
        for node in (self.nodes[0], sqlite_node):
            self.assertEqual(node.write("001", {"amount": 99}).status, "error")
        self.assertEqual(self.csv.read_bytes(), before)
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute("SELECT amount FROM duplicates").fetchall(), [(80,), (81,)])

    def test_missing_storages_are_not_created(self):
        for node in (CsvNode("c", "csv", "record", self.base / "missing.csv", "id"),
                     SqliteNode("s", "sql", "record", self.base / "missing.db", "records", "id")):
            self.assertEqual(node.write("001", {"amount": 1}).status, "error")
        self.assertFalse((self.base / "missing.db").exists())
        self.assertFalse((self.base / "missing.csv").exists())

    def test_value_write_is_isolated_and_null_already_exists(self):
        node = ValueNode("v", "value", "value", None)
        self.assertEqual(node.write("value", 1, mode="insert").status, "conflict")
        value = {"items": [1]}
        result = node.write("value", value, mode="update")
        value["items"].append(2)
        result.items[0]["value"]["items"].append(3)
        self.assertEqual(node.get("value").items[0]["value"], {"items": [1]})
        self.assertEqual(node.write("other", 99).status, "not_found")

    def test_network_scope_cycles_and_single_target(self):
        network = Network()
        root = Node("root", "root", None)
        a, b = ValueNode("a", "a", "number", 1), ValueNode("b", "b", "number", 2)
        for node in (root, a, b):
            network.add_node(node)
        root.strong_write_interfaces.append(a.interface)
        root.weak_write_interfaces.append(b.interface)
        a.strong_write_interfaces.append(root.interface)
        root.weak_write_interfaces.append(a.interface)
        self.assertEqual(network.weak_write("root", "b", "value", 9).status, "forbidden")
        result = network.strong_write("root", "b", "value", 9)
        self.assertEqual(result.sources[0]["write_path"], ["root", "b"])
        self.assertEqual(a.get("value").items[0]["value"], 1)
        self.assertEqual(b.get("value").items[0]["value"], 9)
        self.assertEqual(network.weak_write("a", "a", "value", 8).status, "ok")
        self.assertEqual(network.strong_write("root", "missing", "value", 0).status, "error")
        self.assertEqual(network.weak_write("root", "root", "value", 1).status, "unsupported")

    def test_read_connections_do_not_grant_write_access(self):
        network = Network()
        root, target = Node("root", "root", None), ValueNode("t", "target", "number", 1)
        for node in (root, target):
            network.add_node(node)
        root.strong_read_interfaces.append(target.interface)
        self.assertEqual(network.strong_write("root", "t", "value", 2).status, "forbidden")
        self.assertEqual(target.get("value").items[0]["value"], 1)

    def test_network_routes_to_record_nodes(self):
        network = Network()
        root = Node("root", "root", None)
        network.add_node(root)
        for node in self.nodes:
            network.add_node(node)
            root.strong_write_interfaces.append(node.interface)
            result = network.weak_write("root", node.node_id, "001", {"amount": 91})
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.sources[0]["write_path"], ["root", node.node_id])
            self.assertEqual(node.get("001").items[0]["amount"], 91)

    def test_agent_writes_then_reads_feedback(self):
        def reply(calls=None, content=None):
            return ChatCompletion(id="test", object="chat.completion", created=0, model="mock",
                choices=[{"index": 0, "finish_reason": "tool_calls" if calls else "stop",
                    "message": {"role": "assistant", "content": content, **({"tool_calls": calls} if calls else {})}}])
        def call(name, arguments, call_id):
            return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
        client = Mock()
        client.chat.completions.create.side_effect = [
            reply([call("weak_write", {"target_node_id": "n2", "key": "value", "value": 42, "mode": "update"}, "write")]),
            reply([call("weak_read", {"node_id": "n2", "key": "value"}, "read")]),
            reply(content="n2 已更新为 42。"),
        ]
        network, root = build_agent_network(client, "mock")
        self.assertIn("42", root.invoke_agent("把 n2 改成 42，然后核对"))
        feedback = {m["tool_call_id"]: json.loads(m["content"]) for m in root.agent.messages if m["role"] == "tool"}
        self.assertEqual(feedback["write"]["sources"][0]["write_path"], ["root", "n1", "n2"])
        self.assertEqual(feedback["read"]["items"][0]["value"], 42)
        self.assertEqual(network.nodes["n2"].get("value").items[0]["value"], 42)
        denied = root.invoke_tool("weak_write", target_node_id="n3", key="value", value=99, mode="update")
        self.assertEqual(denied["status"], "forbidden")


if __name__ == "__main__":
    unittest.main()
