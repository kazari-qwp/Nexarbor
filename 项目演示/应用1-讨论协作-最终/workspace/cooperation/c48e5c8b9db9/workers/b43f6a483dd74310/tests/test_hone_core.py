"""Package A tests: nested structure generation, populate, helpers (stdlib unittest)."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from hone.hone import Hone

import tests


FIXTURES = tests.fixtures_dir()


def _expected(*parts):
    path = FIXTURES.joinpath(*parts)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _fixture(*parts):
    return str(FIXTURES.joinpath(*parts))


EXAMPLE_B_EXPECTED = [
    {
        "a": "1",
        "a_b": "2",
        "b": {"c": {"d": "3", "e": "4"}, "d": {"e": "5", "f": "6"}},
    },
    {
        "a": "7",
        "a_b": "8",
        # examples/README.md shows "1" for b.d.f here; that is an upstream typo,
        # the real CSV cell is "12" (kept as-is in the read-only sample).
        "b": {"c": {"d": "9", "e": "10"}, "d": {"e": "11", "f": "12"}},
    },
]

EXAMPLE_C_EXPECTED = [
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


class TestGenerateStructure(unittest.TestCase):
    def test_default_delimiters(self):
        self.assertEqual(Hone().delimiters, [",", "_", " "])
        self.assertEqual(Hone.DEFAULT_DELIMITERS, [",", "_", " "])

    def test_delimiters_override_and_validation(self):
        self.assertEqual(Hone(["::"]).delimiters, ["::"])
        with self.assertRaises(ValueError):
            Hone([])
        with self.assertRaises(ValueError):
            Hone(["", ","])
        with self.assertRaises(ValueError):
            Hone([1])

    def test_birth_nesting(self):
        hone = Hone()
        structure = hone.generate_full_structure(
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

    def test_whole_name_leaves(self):
        hone = Hone()
        structure = hone.generate_full_structure(
            ["a", "a_b", "b_c_d", "b_c_e", "b_d_e", "b_d_f"]
        )
        self.assertEqual(
            structure,
            {
                "a": "a",
                "a_b": "a_b",
                "b": {
                    "c": {"d": "b_c_d", "e": "b_c_e"},
                    "d": {"e": "b_d_e", "f": "b_d_f"},
                },
            },
        )

    def test_prefix_complete_column_blocks_split(self):
        hone = Hone()
        structure = hone.generate_full_structure(["adopted", "adopted_since"])
        self.assertEqual(
            structure, {"adopted": "adopted", "adopted_since": "adopted_since"}
        )

    def test_relative_context_counterexample(self):
        hone = Hone()
        structure = hone.generate_full_structure(["x_y", "x_y_z"])
        self.assertEqual(
            structure, {"x": {"y": "x_y", "y_z": "x_y_z"}}
        )

    def test_single_column_and_empty(self):
        self.assertEqual(Hone().generate_full_structure(["name"]), {"name": "name"})
        self.assertEqual(Hone().generate_full_structure([]), {})

    def test_every_leaf_once_and_non_leaf_has_two_keys(self):
        columns = [
            "name",
            "age (years)",
            "weight (kg)",
            "birth day",
            "birth month",
            "birth year",
            "adopted",
            "adopted_since",
        ]
        hone = Hone()
        structure = hone.generate_full_structure(columns)
        leaves = hone.get_leaves(structure)
        self.assertEqual(sorted(leaves.values()), sorted(columns))
        self.assertEqual(len(leaves.values()), len(columns))

        def walk(node):
            if isinstance(node, dict):
                self.assertGreaterEqual(len(node), 2)
                for value in node.values():
                    walk(value)

        walk(structure)


class TestConversion(unittest.TestCase):
    def test_small_cats_auto(self):
        expected = _expected("data_file", "small_cats_dataset", "nested_dataset.json")
        actual = Hone().convert(_fixture("data_file", "small_cats_dataset", "dataset.csv"))
        self.assertEqual(actual, expected)

    def test_comma_test(self):
        expected = _expected("data_file", "comma_test", "nested_dataset.json")
        actual = Hone().convert(_fixture("data_file", "comma_test", "dataset.csv"))
        self.assertEqual(actual, expected)

    def test_quotes_test(self):
        expected = _expected("data_file", "quotes_test", "nested_dataset.json")
        actual = Hone().convert(_fixture("data_file", "quotes_test", "dataset.csv"))
        self.assertEqual(actual, expected)

    def test_example_b(self):
        repo = tests.repo_root()
        actual = Hone().convert(str(repo / "examples" / "example_b.csv"))
        self.assertEqual(actual, EXAMPLE_B_EXPECTED)

    def test_example_c(self):
        repo = tests.repo_root()
        actual = Hone().convert(str(repo / "examples" / "example_c.csv"))
        self.assertEqual(actual, EXAMPLE_C_EXPECTED)

    def test_schema_dict_and_string(self):
        csv_path = _fixture("data_file", "small_cats_dataset", "dataset.csv")
        expected = _expected("data_file", "small_cats_dataset", "nested_dataset.json")
        schema = _expected("data_file", "small_cats_dataset", "nested_schema.json")
        self.assertEqual(Hone().convert(csv_path, schema=schema), expected)
        self.assertEqual(Hone().convert(csv_path, schema=json.dumps(schema)), expected)

    def test_get_schema_equals_nested_schema(self):
        csv_path = _fixture("data_file", "small_cats_dataset", "dataset.csv")
        schema = _expected("data_file", "small_cats_dataset", "nested_schema.json")
        self.assertEqual(Hone().get_schema(csv_path), schema)

    def test_convert_requires_path(self):
        with self.assertRaises(ValueError):
            Hone().convert(None)
        with self.assertRaises(ValueError):
            Hone().get_schema(None)

    def test_state_isolation(self):
        hone = Hone()
        first = hone.convert(_fixture("data_file", "small_cats_dataset", "dataset.csv"))
        second = hone.convert(str(tests.repo_root() / "examples" / "example_c.csv"))
        self.assertEqual(len(first), 4)
        self.assertEqual(second, EXAMPLE_C_EXPECTED)
        self.assertIsNot(first[0], second[0])
        self.assertIsNot(first[0]["birth"], second[0]["birth"])
        first[0]["birth"]["day"] = "MUTATED"
        self.assertEqual(second[0]["birth"]["day"], "7")

    def test_convert_rows_do_not_share_objects(self):
        rows = Hone().convert(_fixture("data_file", "small_cats_dataset", "dataset.csv"))
        self.assertIsNot(rows[0], rows[1])
        self.assertIsNot(rows[0]["birth"], rows[1]["birth"])


class TestPopulateAndHelpers(unittest.TestCase):
    def test_populate_omits_short_rows_and_missing_columns(self):
        hone = Hone()
        structure = {"name": "name", "birth": {"day": "birth day", "year": "birth year"}}
        columns = ["name", "birth day", "birth year"]
        rows = [["Tommy", "11", "2011"], ["Clara", "6"]]
        self.assertEqual(
            hone.populate_structure_with_data(structure, columns, rows),
            [
                {"name": "Tommy", "birth": {"day": "11", "year": "2011"}},
                {"name": "Clara", "birth": {"day": "6"}},
            ],
        )
        # schema column absent from CSV -> key omitted entirely
        missing = {"name": "name", "ghost": "ghost"}
        self.assertEqual(
            hone.populate_structure_with_data(missing, ["name"], [["Tommy"]]),
            [{"name": "Tommy"}],
        )

    def test_populate_duplicate_headers_last_wins(self):
        hone = Hone()
        result = hone.populate_structure_with_data(
            {"name": "name"}, ["name", "name"], [["first", "second"]]
        )
        self.assertEqual(result, [{"name": "second"}])

    def test_get_leaves(self):
        hone = Hone()
        structure = {"birth": {"day": "birth day"}, "name": "name"}
        self.assertEqual(
            hone.get_leaves(structure),
            {("birth", "day"): "birth day", ("name",): "name"},
        )
        result = {}
        returned = hone.get_leaves(structure, (), result)
        self.assertIs(returned, result)

    def test_get_nested_structure_deep_copies(self):
        hone = Hone()
        original = {"birth": {"day": "birth day"}}
        snapshot = copy.deepcopy(original)
        nested = hone.get_nested_structure(original)
        self.assertEqual(nested, original)
        self.assertIsNot(nested, original)
        self.assertIsNot(nested["birth"], original["birth"])
        nested["birth"]["day"] = "changed"
        self.assertEqual(original, snapshot)

    def test_generate_full_structure_isolated(self):
        hone = Hone()
        first = hone.generate_full_structure(["birth day", "birth year"])
        second = hone.generate_full_structure(["birth day", "birth year"])
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first["birth"], second["birth"])

    def test_escape_quotes(self):
        self.assertEqual(Hone().escape_quotes('a"b'), 'a""b')
        self.assertEqual(Hone().escape_quotes(5), 5)

    def test_clean_split(self):
        hone = Hone()
        self.assertEqual(hone.clean_split(["birth", "", "day"]), ["birth", "day"])
        self.assertEqual(hone.clean_split("birth day"), ["birth", "day"])
        self.assertEqual(hone.clean_split(["", " "]), [])

    def test_is_valid_prefix(self):
        hone = Hone()
        self.assertTrue(hone.is_valid_prefix("birth", "birth day"))
        self.assertFalse(hone.is_valid_prefix("birth", "birthday"))
        self.assertTrue(hone.is_valid_prefix("a", "a_b"))
        self.assertTrue(hone.is_valid_prefix("birth", "birth"))
        self.assertFalse(hone.is_valid_prefix("birth", "birthx day"))

    def test_get_valid_splits(self):
        hone = Hone()
        self.assertIn(["birth", "day"], hone.get_valid_splits("birth day"))
        self.assertIn(["age", "(years)"], hone.get_valid_splits("age (years)"))
        self.assertEqual(hone.get_valid_splits("name"), [])
        multichar = Hone(["::"])
        self.assertEqual(multichar.get_valid_splits("x::y"), [["x", "y"]])

    def test_get_split_suffix(self):
        hone = Hone()
        self.assertEqual(hone.get_split_suffix(["birth", "day"], "birth day"), "day")
        with self.assertRaises(ValueError):
            hone.get_split_suffix(["only"], "only")


if __name__ == "__main__":
    unittest.main()
