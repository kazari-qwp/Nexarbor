import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hone.hone import Hone
from hone.utils.csv_utils import CSVUtils
from hone.utils.json_utils import output_json, parse_json_file

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data_file"


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


class CommaTest(unittest.TestCase):
    def test_exact_comma_fixture_values(self):
        csv = CSVUtils(DATA / "comma_test" / "dataset.csv")
        self.assertEqual(csv.get_column_names(), ['"test","ing"', ' "beep"""'])
        self.assertEqual(csv.get_data_rows(), [['"1', '"2']])

    def test_comma_conversion_matches_fixture(self):
        actual = Hone().convert(DATA / "comma_test" / "dataset.csv")
        expected = load_json(DATA / "comma_test" / "nested_dataset.json")
        self.assertEqual(actual, expected)


class QuotesTest(unittest.TestCase):
    def test_quotes_conversion_matches_fixture(self):
        actual = Hone().convert(DATA / "quotes_test" / "dataset.csv")
        expected = load_json(DATA / "quotes_test" / "nested_dataset.json")
        self.assertEqual(actual, expected)

    def test_quotes_fields_are_not_unescaped_twice(self):
        rows = CSVUtils(DATA / "quotes_test" / "dataset.csv").get_data_rows()
        self.assertEqual(rows[0][-1], "no quotes")
        self.assertEqual(
            rows[1][-1], "one double \" and one single ' quote"
        )
        self.assertEqual(
            rows[2][-1], "two \"double\" and two 'single' quotes"
        )
        self.assertEqual(rows[1][5], "2015")
        self.assertEqual(rows[1][7], "N/A")

    def test_quoted_header_field(self):
        names = CSVUtils(DATA / "quotes_test" / "dataset.csv").get_column_names()
        self.assertEqual(names[-1], "some 'quoted\"' field\"")

    def test_empty_cell_outputs_empty_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "empty.csv"
            csv_path.write_text(
                "name,address,city\nBob,,Paris\n", encoding="utf-8"
            )
            result = Hone().convert(str(csv_path))
        self.assertEqual(result, [{"name": "Bob", "address": "", "city": "Paris"}])


class JsonOutputTest(unittest.TestCase):
    def test_output_json_formatting_and_roundtrip(self):
        data = [{"b": 1, "a": "héllo"}]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            output_json(data, str(out))
            text = out.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertIn("\n  {", text)
            self.assertIn('"a": "héllo"', text)
            # sort_keys: "a" before "b"
            self.assertLess(text.index('"a"'), text.index('"b"'))
            self.assertEqual(parse_json_file(str(out)), data)

    def test_output_json_dash_writes_stdout(self):
        buffer = io.StringIO()
        with mock.patch("sys.stdout", buffer):
            output_json([{"x": "1"}], "-")
        self.assertEqual(json.loads(buffer.getvalue()), [{"x": "1"}])
        self.assertTrue(buffer.getvalue().endswith("\n"))
