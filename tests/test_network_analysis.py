"""根工具的网络读取、条件查询和缺失输入验证。"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from datanet.nodes.node import Node, NodeResult
from datanet.nodes.sqlite_node import SqliteNode
from applications.experiment.network_setup import build_lab_network


class NetworkAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db_path = Path(self.directory.name) / "rules.db"
        self.csv_path = Path(self.directory.name) / "records.csv"
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                "CREATE TABLE rules (project_id TEXT PRIMARY KEY, rule_type TEXT, "
                "lower_bound REAL, upper_bound REAL)"
            )
            connection.executemany("INSERT INTO rules VALUES (?, ?, ?, ?)", [
                ("A", "at_least", 80, None),
                ("B", "between", 40, 60),
                ("C", "at_most", None, 20),
            ])
            connection.commit()
        finally:
            connection.close()
        self.csv_path.write_text(
            "记录编号,项目,测量值,是否有效\n"
            "001,A,80,是\n002,A,79,是\n003,A,,是\n"
            "004,A,95,否\n005,B,50,是\n", encoding="utf-8-sig"
        )
        self.network, self.root = build_lab_network(self.db_path, self.csv_path)

    def analyze(self, project_id="A"):
        return self.root.invoke_tool("analyze_project", project_id=project_id)

    def test_tool_reads_both_nodes_and_keeps_paths(self):
        result = self.analyze()
        self.assertEqual(result["valid_count"], 2)
        self.assertEqual(result["passed_count"], 1)
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["pass_rate"], 0.5)
        self.assertEqual(result["sources"]["rules"][0]["retrieval_path"], ["root", "lab_rules"])
        self.assertEqual(result["sources"]["records"][0]["retrieval_path"], ["root", "lab_records"])

    def test_query_filters_are_combined_with_and(self):
        result = self.network.query(
            "root", {"项目": "A", "是否有效": "是"}, "integrated", "experiment_record"
        )
        self.assertEqual(len(result.items), 3)

    def test_null_filter(self):
        result = self.network.query(
            "root", {"测量值": None}, "integrated", "experiment_record"
        )
        self.assertEqual(result.items[0]["记录编号"], "003")

    def test_successful_empty_query_differs_from_no_destination(self):
        result = self.network.query("root", {"项目": "C"}, "integrated", "experiment_record")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.items, [])
        self.assertTrue(result.sources)
        self.root.strong_read_interfaces = [self.network.nodes["lab_rules"].interface]
        result = self.network.query("root", {"项目": "C"}, "integrated", "experiment_record")
        self.assertEqual(result.status, "not_found")

    def test_no_records_has_null_pass_rate(self):
        result = self.analyze("C")
        self.assertEqual(result["valid_count"], 0)
        self.assertIsNone(result["pass_rate"])

    def test_removing_either_input_connection_prevents_analysis(self):
        original = list(self.root.strong_read_interfaces)
        for interface in original:
            with self.subTest(target=interface.target_node_id):
                self.root.strong_read_interfaces = [interface]
                with self.assertRaises(ValueError):
                    self.analyze()

    def test_querying_missing_column_is_error(self):
        result = self.network.query("root", {"不存在": "A"}, "integrated", "experiment_record")
        self.assertEqual(result.status, "error")

    def test_schema_error_even_when_no_rows_match(self):
        self.csv_path.write_text("记录编号,项目\n001,B\n", encoding="utf-8-sig")
        with self.assertRaisesRegex(ValueError, "缺少字段"):
            self.analyze()

    def test_duplicate_rules_are_rejected(self):
        duplicate = SqliteNode("other_rules", "其他规则", "experiment_rule", self.db_path, "rules", "project_id")
        self.network.add_node(duplicate)
        self.root.strong_read_interfaces.append(duplicate.interface)
        with self.assertRaisesRegex(ValueError, "恰好一条"):
            self.analyze()

    def test_broken_record_file_prevents_partial_analysis(self):
        self.network.nodes["lab_records"].file_path = self.csv_path.parent / "missing.csv"
        with self.assertRaisesRegex(ValueError, "记录读取失败"):
            self.analyze()

    def test_unknown_project_and_unknown_tool(self):
        with self.assertRaises(ValueError):
            self.analyze("Z")
        with self.assertRaisesRegex(ValueError, "工具不存在"):
            self.root.invoke_tool("missing")

    def test_query_cycle_reads_node_once(self):
        node = self.network.nodes["lab_records"]
        node.strong_read_interfaces.append(self.root.interface)
        self.root.weak_read_interfaces.append(node.interface)
        result = self.network.query("root", {"项目": "A"}, "federated", "experiment_record")
        self.assertEqual(len(result.items), 4)
        self.assertEqual(len(result.sources), 1)

    def test_unsupported_query_is_an_error(self):
        result = self.network.query("root", {}, "integrated", "experiment_rule")
        self.assertEqual(result.status, "error")

    def test_error_without_message_is_not_silently_ignored(self):
        class BrokenNode(Node):
            def get(self, key):
                return NodeResult(status="error")
        broken = BrokenNode("broken", "坏节点", "broken")
        self.network.add_node(broken)
        self.assertEqual(self.network.get("broken", "A").status, "error")


if __name__ == "__main__":
    unittest.main()
