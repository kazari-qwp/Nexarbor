"""Boundary / edge-case tests for the hone CSV -> nested JSON converter.

Owner: package D. Covers plan CONTRACT.md §2.4 items 1-15 and test-matrix
E12, E13, E17, E19, E20 and E21.

Every file this module writes goes to a temporary directory; the committed
fixtures and examples are never modified.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hone.hone import Hone
from tests import fixtures_dir, repo_root

from tests.test_golden_samples import EXPECTED_A


def _write(directory: Path, name: str, data, *, encoding: str = "utf-8") -> Path:
    path = Path(directory) / name
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_bytes(data.encode(encoding))
    return path


def _run_cli(args, *, stdin_text=None, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "hone", *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(cwd or repo_root()),
    )


class BoundaryConversionTests(unittest.TestCase):
    """§2.4 items 1-11: tiny malformed / unusual CSV documents."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_1_empty_file(self):
        path = _write(self.tmp, "empty.csv", "")
        self.assertEqual(Hone().convert(path), [])

    def test_2_header_only(self):
        path = _write(self.tmp, "header_only.csv", "a,b,c\n")
        self.assertEqual(Hone().convert(path), [])

    def test_3_first_physical_line_is_header(self):
        path = _write(self.tmp, "one_col.csv", "a\n1\n2\n")
        self.assertEqual(Hone().convert(path), [{"a": "1"}, {"a": "2"}])

    def test_4_short_row_omits_missing_keys(self):
        path = _write(self.tmp, "short.csv", "a,b,c\n1,2\n")
        self.assertEqual(Hone().convert(path), [{"a": "1", "b": "2"}])

    def test_5_long_row_drops_extra_cells(self):
        path = _write(self.tmp, "long.csv", "a,b\n1,2,3\n")
        self.assertEqual(Hone().convert(path), [{"a": "1", "b": "2"}])

    def test_6_duplicate_header_last_wins(self):
        path = _write(self.tmp, "dup.csv", "a,a,b\n1,2,3\n")
        self.assertEqual(Hone().convert(path), [{"a": "2", "b": "3"}])

    def test_7_empty_header_name_is_a_key(self):
        path = _write(self.tmp, "empty_header.csv", ",b\nx,y\n")
        self.assertEqual(Hone().convert(path), [{"": "x", "b": "y"}])

    def test_8_shared_prefix_becomes_nested(self):
        path = _write(
            self.tmp,
            "birth.csv",
            "name,birth day,birth month,birth year\nBob,7,May,1985\n",
        )
        self.assertEqual(
            Hone().convert(path),
            [
                {
                    "name": "Bob",
                    "birth": {"day": "7", "month": "May", "year": "1985"},
                }
            ],
        )

    def test_9_prefix_that_is_a_full_column_stays_flat(self):
        path = _write(
            self.tmp,
            "flat.csv",
            "a,a_b,adopted,adopted_since,reference,reference name\n"
            "1,2,TRUE,2012,TRUE,Smith\n",
        )
        self.assertEqual(
            Hone().convert(path),
            [
                {
                    "a": "1",
                    "a_b": "2",
                    "adopted": "TRUE",
                    "adopted_since": "2012",
                    "reference": "TRUE",
                    "reference name": "Smith",
                }
            ],
        )

    def test_10_schema_referencing_missing_column_omits_key(self):
        path = _write(self.tmp, "two.csv", "a,b\n1,2\n")
        schema = {"a": "a", "ghost": "not_a_column"}
        self.assertEqual(Hone().convert(path, schema=schema), [{"a": "1"}])

    def test_11_columns_not_referenced_by_schema_are_dropped(self):
        path = _write(self.tmp, "two.csv", "a,b\n1,2\n")
        self.assertEqual(
            Hone().convert(path, schema={"b": "b"}), [{"b": "2"}]
        )

    def test_13_missing_path_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            Hone().convert(self.tmp / "does_not_exist.csv")


class SchemaAndDelimiterTests(unittest.TestCase):
    """E19 / E21: multi-character delimiters and mixed schema."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_e19_multi_character_delimiter(self):
        path = _write(self.tmp, "multi.csv", "x::y,x::z\n1,2\n")
        self.assertEqual(
            Hone(delimiters=["::"]).convert(path), [{"x": {"y": "1", "z": "2"}}]
        )
        # Default delimiters do NOT split on "::" the same way.
        self.assertNotEqual(Hone().convert(path), [{"x": {"y": "1", "z": "2"}}])

    def test_e19_get_valid_splits_multichar_offsets(self):
        h = Hone(delimiters=["::"])
        self.assertEqual(h.get_valid_splits("x::y"), [["x", "y"]])

    def test_e21_schema_accepts_json_string(self):
        path = _write(self.tmp, "two.csv", "a,b\n1,2\n")
        schema_text = json.dumps({"outer": {"inner": "b"}})
        self.assertEqual(
            Hone().convert(path, schema=schema_text),
            [{"outer": {"inner": "2"}}],
        )

    def test_e21_schema_nested_dict_with_missing_and_unused_columns(self):
        path = _write(self.tmp, "three.csv", "a,b,c\n1,2,3\n")
        schema = {"keep": "a", "nested": {"x": "b", "y": "nope"}}
        self.assertEqual(
            Hone().convert(path, schema=schema),
            [{"keep": "1", "nested": {"x": "2"}}],
        )


class HelperUnitTests(unittest.TestCase):
    """E13: pure helper functions from the Hone contract."""

    def setUp(self):
        self.h = Hone()

    def test_escape_quotes(self):
        self.assertEqual(self.h.escape_quotes('a"b'), 'a""b')
        self.assertEqual(self.h.escape_quotes("plain"), "plain")
        self.assertEqual(self.h.escape_quotes(123), 123)

    def test_clean_split(self):
        self.assertEqual(self.h.clean_split(["birth", "", "day"]), ["birth", "day"])
        self.assertEqual(self.h.clean_split(["  ", ""]), [])
        self.assertEqual(self.h.clean_split("birth day"), ["birth", "day"])

    def test_is_valid_prefix(self):
        self.assertTrue(self.h.is_valid_prefix("birth", "birth day"))
        self.assertFalse(self.h.is_valid_prefix("birth", "birthday"))
        self.assertTrue(self.h.is_valid_prefix("a", "a_b"))
        self.assertTrue(self.h.is_valid_prefix("same", "same"))

    def test_get_valid_splits_is_purely_syntactic(self):
        splits = self.h.get_valid_splits("birth day")
        self.assertIn(["birth", "day"], splits)
        self.assertIn(["age", "(years)"], self.h.get_valid_splits("age (years)"))

    def test_get_split_suffix(self):
        self.assertEqual(self.h.get_split_suffix(["birth", "day"], "birth day"), "day")
        with self.assertRaises(ValueError):
            self.h.get_split_suffix(["only"], "only")

    def test_get_leaves_shape(self):
        structure = {"name": "name", "birth": {"day": "birth day"}}
        self.assertEqual(
            self.h.get_leaves(structure),
            {("name",): "name", ("birth", "day"): "birth day"},
        )

    def test_generate_full_structure_contract(self):
        structure = self.h.generate_full_structure(
            ["name", "birth day", "birth month", "birth year"]
        )
        self.assertEqual(
            structure,
            {
                "name": "name",
                "birth": {
                    "day": "birth day",
                    "month": "birth month",
                    "year": "birth year",
                },
            },
        )


class EncodingAndNewlineTests(unittest.TestCase):
    """§2.4 item 14 / E20: BOM, CRLF and non-ASCII values."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_utf8_bom_is_stripped_from_first_header(self):
        path = _write(self.tmp, "bom.csv", "\ufeffname,age\nBob,7\n", encoding="utf-8")
        # Explicit BOM byte sequence.
        path.write_bytes(b"\xef\xbb\xbfname,age\r\nBob,7\r\n")
        self.assertEqual(Hone().convert(path), [{"name": "Bob", "age": "7"}])

    def test_crlf_input(self):
        path = _write(self.tmp, "crlf.csv", "a,b\r\n1,2\r\n3,4\r\n")
        self.assertEqual(
            Hone().convert(path), [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
        )

    def test_non_ascii_values_roundtrip(self):
        path = _write(self.tmp, "unicode.csv", "name,city\nJosé,東京\n")
        self.assertEqual(
            Hone().convert(path), [{"name": "José", "city": "東京"}]
        )


class CliBoundaryTests(unittest.TestCase):
    """E17: exact stdout bytes for file->stdout and empty input."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_e17_exact_stdout_for_example_a(self):
        result = _run_cli(["examples/example_a.csv", "-"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        expected_text = (
            json.dumps(EXPECTED_A, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        )
        self.assertEqual(result.stdout, expected_text)

    def test_e17_empty_input_stdout_is_empty_list(self):
        path = _write(self.tmp, "empty.csv", "")
        result = _run_cli([str(path), "-"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "[]\n")
        self.assertEqual(result.stderr, "")

    def test_e17_file_to_file_exact_text(self):
        out = self.tmp / "out.json"
        result = _run_cli(
            [str(fixtures_dir() / "data_file" / "small_cats_dataset" / "dataset.csv"), str(out)]
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        text = out.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        obj = json.loads(text)
        self.assertEqual(
            text,
            json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )


if __name__ == "__main__":
    unittest.main()
