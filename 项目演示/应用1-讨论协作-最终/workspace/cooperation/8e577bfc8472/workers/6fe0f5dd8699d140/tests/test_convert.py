"""Tests for automatic conversion, schema-driven conversion and population."""

import json
import tempfile
import unittest
from pathlib import Path

from hone.hone import Hone

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data_file"
EXAMPLES_DIR = REPO_ROOT / "examples"

DATASETS = ["comma_test", "quotes_test", "small_cats_dataset"]


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class AutomaticConversionTests(unittest.TestCase):
    def setUp(self):
        self.hone = Hone()

    def test_ac4_every_dataset_matches_expected_json(self):
        for dataset in DATASETS:
            with self.subTest(dataset=dataset):
                csv_path = DATA_DIR / dataset / "dataset.csv"
                expected = load_json(DATA_DIR / dataset / "nested_dataset.json")
                self.assertEqual(self.hone.convert(str(csv_path)), expected)

    def test_ac8_example_b_full_result(self):
        result = self.hone.convert(str(EXAMPLES_DIR / "example_b.csv"))
        expected = [
            {
                "a": "1",
                "a_b": "2",
                "b": {"c": {"d": "3", "e": "4"}, "d": {"e": "5", "f": "6"}},
            },
            {
                "a": "7",
                "a_b": "8",
                "b": {"c": {"d": "9", "e": "10"}, "d": {"e": "11", "f": "12"}},
            },
        ]
        self.assertEqual(result, expected)
        self.assertEqual(result[1]["b"]["d"]["f"], "12")

    def test_example_a_matches_small_cats_fixture(self):
        result = self.hone.convert(str(EXAMPLES_DIR / "example_a.csv"))
        expected = load_json(DATA_DIR / "small_cats_dataset" / "nested_dataset.json")
        self.assertEqual(result, expected)

    def test_example_c_matches_readme(self):
        result = self.hone.convert(str(EXAMPLES_DIR / "example_c.csv"))
        expected = [
            {
                "birth": {"day": "7", "month": "May", "year": "1985"},
                "name": "Bob",
                "reference": "TRUE",
                "reference name": "Smith",
            },
            {
                "birth": {"day": "21", "month": "January", "year": "1997"},
                "name": "Julia",
                "reference": "FALSE",
                "reference name": "N/A",
            },
            {
                "birth": {"day": "12", "month": "June", "year": "1996"},
                "name": "Rick",
                "reference": "TRUE",
                "reference name": "Clara",
            },
        ]
        self.assertEqual(result, expected)


class SchemaDrivenConversionTests(unittest.TestCase):
    def setUp(self):
        self.hone = Hone()

    def test_ac5_explicit_schema_file(self):
        dataset = DATA_DIR / "small_cats_dataset"
        schema = load_json(dataset / "nested_schema.json")
        expected = load_json(dataset / "nested_dataset.json")
        self.assertEqual(
            self.hone.convert(str(dataset / "dataset.csv"), schema=schema), expected
        )

    def test_ac5_schema_returned_by_get_schema_round_trips(self):
        dataset = DATA_DIR / "small_cats_dataset"
        schema = self.hone.get_schema(str(dataset / "dataset.csv"))
        expected = load_json(dataset / "nested_dataset.json")
        self.assertEqual(
            self.hone.convert(str(dataset / "dataset.csv"), schema=schema), expected
        )

    def test_schema_accepted_as_json_string(self):
        dataset = DATA_DIR / "small_cats_dataset"
        schema_text = (dataset / "nested_schema.json").read_text(encoding="utf-8")
        expected = load_json(dataset / "nested_dataset.json")
        self.assertEqual(
            self.hone.convert(str(dataset / "dataset.csv"), schema=schema_text), expected
        )

    def test_invalid_schema_raises(self):
        csv_path = str(EXAMPLES_DIR / "example_b.csv")
        with self.assertRaises(TypeError):
            self.hone.convert(csv_path, schema=["not", "a", "dict"])
        with self.assertRaises(json.JSONDecodeError):
            self.hone.convert(csv_path, schema="{bad}")

    def test_custom_delimiters(self):
        hone = Hone(delimiters=["|"])
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "custom.csv"
            csv_path.write_text("p|q,p|r\n1,2\n", encoding="utf-8", newline="")
            self.assertEqual(
                hone.convert(str(csv_path)), [{"p": {"q": "1", "r": "2"}}]
            )


class PopulationTests(unittest.TestCase):
    def setUp(self):
        self.hone = Hone()

    def test_populate_structure_with_data(self):
        structure = {"a": "a", "b": {"c": "b_c"}}
        result = self.hone.populate_structure_with_data(
            structure, ["a", "b_c"], [["1", "2"], ["3", "4"]]
        )
        self.assertEqual(
            result,
            [{"a": "1", "b": {"c": "2"}}, {"a": "3", "b": {"c": "4"}}],
        )

    def test_empty_cells_and_missing_values(self):
        structure = {"a": "a", "b": {"c": "b_c"}}
        result = self.hone.populate_structure_with_data(
            structure, ["a", "b_c"], [["", ""], ["x"]]
        )
        self.assertEqual(result, [{"a": "", "b": {"c": ""}}, {"a": "x", "b": {"c": ""}}])

    def test_no_data_rows_yields_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "headers_only.csv"
            csv_path.write_text("a,b\n", encoding="utf-8", newline="")
            self.assertEqual(self.hone.convert(str(csv_path)), [])

    def test_stdin_schema_then_convert_reads_only_once(self):
        import io
        from unittest import mock

        stdin_text = "a_b,a_c\n1,2\n"
        with mock.patch("sys.stdin", io.StringIO(stdin_text)):
            hone = Hone()
            schema = hone.get_schema("-")
            result = hone.convert("-", schema=schema)
        self.assertEqual(schema, {"a": {"b": "a_b", "c": "a_c"}})
        self.assertEqual(result, [{"a": {"b": "1", "c": "2"}}])

    def test_csv_utils_instance_is_reused(self):
        csv_path = str(EXAMPLES_DIR / "example_b.csv")
        self.hone.convert(csv_path)
        first = self.hone.csv
        self.hone.convert(csv_path)
        self.assertIs(self.hone.csv, first)
        self.assertEqual(self.hone.csv_filepath, csv_path)


if __name__ == "__main__":
    unittest.main()
