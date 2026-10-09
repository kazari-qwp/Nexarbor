"""配置往返、路径恢复、非法配置和应用装配验证。"""

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

from datanet.network import Network
from datanet.nodes import Node, ValueNode, CsvNode, SqliteNode
from datanet.serialization import load_network, save_network
from datanet.nodes.value_node.demo_network import build_number_network
from applications.experiment.network_setup import build_lab_network
from config import NETWORK_PATH


class SerializationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.path = self.base / "config" / "network.json"

    def test_numeric_results_and_paths_survive_roundtrip(self):
        network = build_number_network()
        network.nodes["n1"].strong_write_interfaces.append(network.nodes["n6"].interface)
        network.nodes["n1"].weak_write_interfaces.append(network.nodes["n2"].interface)
        save_network(network, self.path)
        restored = load_network(self.path)
        for node_id in network.nodes:
            for operation in ("weak_read", "strong_read"):
                self.assertEqual(asdict(getattr(network, operation)(node_id, "value")),
                                 asdict(getattr(restored, operation)(node_id, "value")))
        self.assertIs(restored.nodes["n1"].strong_write_interfaces[0], restored.nodes["n6"].interface)
        self.assertIs(restored.nodes["n1"].weak_write_interfaces[0], restored.nodes["n2"].interface)

    def test_storage_paths_dtypes_and_reads_survive_roundtrip(self):
        csv = self.base / "记录.csv"
        csv.write_text("id,value\n001,7\n", encoding="utf-8")
        db = self.base / "rules.db"
        with closing(sqlite3.connect(db)) as connection:
            with connection:
                connection.execute("CREATE TABLE rules (id TEXT, value INTEGER)")
                connection.execute("INSERT INTO rules VALUES ('A', 80)")
        network = Network()
        for node in (CsvNode("csv", "记录", "record", csv, "id", {"value": "Int64"}),
                     SqliteNode("sql", "规则", "rule", db, "rules", "id")):
            network.add_node(node)
        save_network(network, self.path)
        document = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(document["nodes"][0]["parameters"]["file_path"], "../记录.csv")
        restored = load_network(self.path)
        self.assertEqual(restored.nodes["csv"].dtype, network.nodes["csv"].dtype)
        for node_id, key in (("csv", "001"), ("sql", "A")):
            self.assertEqual(asdict(network.get(node_id, key)), asdict(restored.get(node_id, key)))

    def test_value_null_and_nested_data(self):
        network = Network()
        for index, value in enumerate((None, {"text": "中文", "values": [1, True, None]})):
            network.add_node(ValueNode(str(index), "单值", "value", value))
        save_network(network, self.path)
        restored = load_network(self.path)
        for node_id in network.nodes:
            self.assertEqual(network.get(node_id, "value"), restored.get(node_id, "value"))

    def test_runtime_objects_are_excluded(self):
        network = Network()
        node = Node("root", "入口", None)
        node.agent = object()
        node.tools["hello"] = lambda: "hello"
        network.add_node(node)
        save_network(network, self.path)
        restored = load_network(self.path).nodes["root"]
        self.assertIsNone(restored.agent)
        self.assertEqual(restored.tools, {})

    def test_invalid_configs_are_rejected(self):
        save_network(build_number_network(), self.path)
        original = json.loads(self.path.read_text(encoding="utf-8"))
        mutations = (
            lambda d: d.update(version=2),
            lambda d: d["nodes"][0].update(type="custom"),
            lambda d: d["nodes"].append(d["nodes"][0]),
            lambda d: d["nodes"][0]["connections"]["strong_read_interfaces"].append("missing"),
            lambda d: d["nodes"][0].update(agent={"key": "unexpected"}),
            lambda d: d["nodes"][0]["connections"].update(weak_read_interfaces="n2"),
        )
        for mutate in mutations:
            document = json.loads(json.dumps(original))
            mutate(document)
            self.path.write_text(json.dumps(document), encoding="utf-8")
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                load_network(self.path)

    def test_invalid_values_do_not_overwrite_existing_file(self):
        self.path.parent.mkdir()
        self.path.write_text("existing", encoding="utf-8")
        for value in ((1, 2), {1: "key"}, float("nan"), object()):
            network = Network()
            network.add_node(ValueNode("v", "单值", "value", value))
            with self.subTest(value=value), self.assertRaises(ValueError):
                save_network(network, self.path)
            self.assertEqual(self.path.read_text(encoding="utf-8"), "existing")

    def test_duplicate_json_fields_and_nonfinite_numbers_are_rejected(self):
        self.path.parent.mkdir()
        for content in ('{"version":1,"version":1,"nodes":[]}',
                        '{"version":NaN,"nodes":[]}'):
            self.path.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_network(self.path)

    def test_load_missing_storage_does_not_create_it(self):
        network = Network()
        db = self.base / "missing.db"
        network.add_node(SqliteNode("s", "数据库", "rule", db, "rules", "id"))
        save_network(network, self.path)
        restored = load_network(self.path)
        self.assertFalse(db.exists())
        self.assertEqual(restored.get("s", "A").status, "error")
        self.assertFalse(db.exists())

    def test_experiment_structure_comes_from_config(self):
        document = json.loads(NETWORK_PATH.read_text(encoding="utf-8"))
        for entry in document["nodes"]:
            if entry["node_id"] == "root":
                entry["connections"]["strong_read_interfaces"] = ["lab_rules"]
            elif entry["type"] == "csv":
                entry["parameters"]["file_path"] = str(self.base / "records.csv")
            elif entry["type"] == "sqlite":
                entry["parameters"]["db_path"] = str(self.base / "rules.db")
        self.path.parent.mkdir()
        self.path.write_text(json.dumps(document), encoding="utf-8")
        network, root = build_lab_network(config_path=self.path)
        self.assertEqual([i.target_node_id for i in root.strong_read_interfaces], ["lab_rules"])
        self.assertIn("analyze_project", root.tools)
        self.assertEqual(network.query("root", {}, "integrated", "experiment_record").status, "not_found")


if __name__ == "__main__":
    unittest.main()
