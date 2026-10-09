"""独立 CSV 文件测试；不修改项目实验记录。"""

import json
import tempfile
import unittest
from pathlib import Path

from datanet.nodes.csv_node import CsvNode


class CsvNodeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "sample.csv"
        self.node = CsvNode("sample", "示例", "sample_record", self.path, "编号")

    def write_csv(self, text):
        self.path.write_text(text, encoding="utf-8-sig")

    def test_read_preserves_key_and_returns_source(self):
        self.write_csv("编号,内容\n001,测试\n")
        result = self.node.get("001")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.items, [{"编号": "001", "内容": "测试"}])
        self.assertEqual(result.sources[0]["key"], "001")
        self.assertEqual(result.sources[0]["file"], self.path.resolve().as_posix())
        self.assertEqual(self.node.get("1").status, "not_found")

    def test_unknown_key_returns_empty_result(self):
        self.write_csv("编号,内容\n001,测试\n")
        result = self.node.get("002")
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.items, [])
        self.assertEqual(result.errors, [])

    def test_duplicate_key_is_error(self):
        self.write_csv("编号,内容\n001,甲\n001,乙\n")
        self.assertEqual(self.node.get("001").status, "error")

    def test_missing_key_column_is_error(self):
        self.write_csv("其他列,内容\n001,测试\n")
        result = self.node.get("001")
        self.assertEqual(result.status, "error")
        self.assertIn("缺少主键列", result.errors[0])

    def test_missing_file_is_error_without_creating_file(self):
        result = self.node.get("001")
        self.assertEqual(result.status, "error")
        self.assertFalse(self.path.exists())

    def test_empty_file_is_error(self):
        self.write_csv("")
        self.assertEqual(self.node.get("001").status, "error")

    def test_invalid_numeric_value_is_error(self):
        self.write_csv("编号,数值\n001,非数字\n")
        self.node = CsvNode(
            "sample", "示例", "sample_record", self.path, "编号", {"数值": "Int64"}
        )
        self.assertEqual(self.node.get("001").status, "error")

    def test_missing_value_becomes_json_null(self):
        self.write_csv("编号,内容\n001,\n")
        result = self.node.get("001")
        self.assertIsNone(result.items[0]["内容"])
        json.dumps(result.items, allow_nan=False)

    def test_na_literal_is_a_valid_key(self):
        self.write_csv("编号,内容\nNA,测试\n")
        self.assertEqual(self.node.get("NA").status, "ok")

    def test_constructor_does_not_modify_supplied_dtype(self):
        dtype = {"内容": "string"}
        CsvNode("sample", "示例", "sample_record", self.path, "编号", dtype)
        self.assertEqual(dtype, {"内容": "string"})

    def test_non_string_key_is_rejected(self):
        with self.assertRaises(TypeError):
            self.node.get(1)


if __name__ == "__main__":
    unittest.main()
