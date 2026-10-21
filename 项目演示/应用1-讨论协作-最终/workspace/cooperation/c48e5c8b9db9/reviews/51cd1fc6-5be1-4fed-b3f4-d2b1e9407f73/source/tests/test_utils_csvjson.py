"""Unit tests for hone.utils (package B): CSV/JSON helpers and IO."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from hone.utils import CSVUtils
from hone.utils import assert_json_equal
from hone.utils import normalize
from hone.utils import output_json
from hone.utils import parse_csv_file
from hone.utils import parse_json_file
from tests import fixtures_dir


class CSVUtilsTests(unittest.TestCase):
    def _dataset(self, name, filename="dataset.csv"):
        return str(fixtures_dir() / "data_file" / name / filename)

    def test_three_dataset_shapes(self):
        cases = [
            ("comma_test", 2, 1),
            ("quotes_test", 9, 4),
            ("small_cats_dataset", 8, 4),
        ]
        for name, columns, rows in cases:
            with self.subTest(name=name):
                csv_utils = CSVUtils(self._dataset(name))
                self.assertEqual(len(csv_utils.get_column_names()), columns)
                self.assertEqual(len(csv_utils.get_data_rows()), rows)

    def test_comma_headers_preserve_quotes(self):
        csv_utils = CSVUtils(self._dataset("comma_test", "column_names.csv"))
        self.assertEqual(csv_utils.get_column_names(), ['"test","ing"', ' "beep"""'])

    def test_column_names_are_fresh_lists(self):
        csv_utils = CSVUtils(self._dataset("quotes_test"))
        first = csv_utils.get_column_names()
        second = csv_utils.get_column_names()
        self.assertIsNot(first, second)
        self.assertEqual(first, second)
        first.append("mutated")
        self.assertNotEqual(csv_utils.get_column_names(), first)

    def test_data_rows_are_fresh_lists(self):
        csv_utils = CSVUtils(self._dataset("small_cats_dataset"))
        first = csv_utils.get_data_rows()
        second = csv_utils.get_data_rows()
        self.assertIsNot(first, second)
        self.assertIsNot(first[0], second[0])
        self.assertEqual(first, second)
        first[0][0] = "mutated"
        self.assertNotEqual(csv_utils.get_data_rows()[0][0], "mutated")

    def test_parse_csv_file(self):
        columns, rows = parse_csv_file(self._dataset("small_cats_dataset"))
        self.assertEqual(columns[0], "name")
        self.assertEqual(rows[0][0], "Tommy")
        self.assertEqual(len(rows), 4)

    def test_stdin_consumed_once(self):
        original = sys.stdin
        sys.stdin = io.StringIO("a,b\n1,2\n3,4\n")
        try:
            csv_utils = CSVUtils("-")
            self.assertEqual(csv_utils.get_column_names(), ["a", "b"])
            self.assertEqual(csv_utils.get_data_rows(), [["1", "2"], ["3", "4"]])
            # A second call must hit the cache, not the (now exhausted) stream.
            self.assertEqual(csv_utils.get_data_rows(), [["1", "2"], ["3", "4"]])
        finally:
            sys.stdin = original

    def test_bom_and_crlf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bom.csv")
            with open(path, "wb") as handle:
                handle.write("\ufeffname,age\r\nTommy,5\r\n".encode("utf-8"))
            csv_utils = CSVUtils(path)
            self.assertEqual(csv_utils.get_column_names(), ["name", "age"])
            self.assertEqual(csv_utils.get_data_rows(), [["Tommy", "5"]])

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.csv")
            open(path, "w", encoding="utf-8").close()
            csv_utils = CSVUtils(path)
            self.assertEqual(csv_utils.get_column_names(), [])
            self.assertEqual(csv_utils.get_data_rows(), [])

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            CSVUtils(os.path.join("does", "not", "exist.csv")).get_column_names()


class JSONUtilsTests(unittest.TestCase):
    def test_output_json_file_roundtrip(self):
        payload = [{"b": "2", "a": {"d": "4", "c": "3"}}]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.json")
            output_json(payload, path)
            self.assertEqual(parse_json_file(path), payload)
            with open(path, "r", encoding="utf-8", newline="") as handle:
                text = handle.read()
            self.assertEqual(
                text,
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            )

    def test_output_json_stdout(self):
        payload = [{"k": "v"}]
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            output_json(payload, "-")
        self.assertEqual(
            buffer.getvalue(),
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )

    def test_parse_json_file_fixture(self):
        expected = parse_json_file(
            str(fixtures_dir() / "data_file" / "small_cats_dataset" / "nested_dataset.json")
        )
        self.assertIsInstance(expected, list)
        self.assertEqual(expected[0]["name"], "Tommy")

    def test_parse_json_file_stdin(self):
        original = sys.stdin
        sys.stdin = io.StringIO('{"a": "1"}')
        try:
            self.assertEqual(parse_json_file("-"), {"a": "1"})
        finally:
            sys.stdin = original


class TestUtilsTests(unittest.TestCase):
    def test_normalize_and_assert_json_equal(self):
        self.assertEqual(normalize({"b": (1, 2)}), {"b": [1, 2]})
        assert_json_equal(self, {"a": [1, {"b": 2}]}, {"a": [1, {"b": 2}]})

    def test_non_ascii_roundtrip(self):
        payload = [{"名字": "猫", "note": "café"}]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "unicode.json")
            output_json(payload, path)
            self.assertEqual(parse_json_file(path), payload)


if __name__ == "__main__":
    unittest.main()
