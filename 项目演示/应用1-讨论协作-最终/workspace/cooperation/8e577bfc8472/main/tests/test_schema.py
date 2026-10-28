"""Tests for schema generation and the public ``Hone`` helper methods."""

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data_file"
EXAMPLES_DIR = REPO_ROOT / "examples"


class HoneImportTests(unittest.TestCase):
    def test_ac1_package_imports(self):
        import hone
        from hone.hone import Hone

        self.assertIs(hone.Hone, Hone)

    def test_default_delimiters(self):
        from hone.hone import Hone

        self.assertEqual(Hone.DEFAULT_DELIMITERS, [",", "_", " "])
        self.assertEqual(Hone().delimiters, [",", "_", " "])
        self.assertEqual(Hone(delimiters=["-"]).delimiters, ["-"])

    def test_rejects_bad_delimiters(self):
        from hone.hone import Hone

        with self.assertRaises(TypeError):
            Hone(delimiters="_")
        with self.assertRaises(ValueError):
            Hone(delimiters=[])
        with self.assertRaises(ValueError):
            Hone(delimiters=[""])


class AutoSchemaTests(unittest.TestCase):
    def setUp(self):
        from hone.hone import Hone

        self.hone = Hone()

    def test_ac3_small_cats_schema_matches_fixture(self):
        schema = self.hone.get_schema(str(DATA_DIR / "small_cats_dataset" / "dataset.csv"))
        expected = json.loads(
            (DATA_DIR / "small_cats_dataset" / "nested_schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(schema, expected)

    def test_ac8_example_b_schema(self):
        schema = self.hone.get_schema(str(EXAMPLES_DIR / "example_b.csv"))
        expected = {
            "a": "a",
            "a_b": "a_b",
            "b": {
                "c": {"d": "b_c_d", "e": "b_c_e"},
                "d": {"e": "b_d_e", "f": "b_d_f"},
            },
        }
        self.assertEqual(schema, expected)

    def test_example_a_schema(self):
        schema = self.hone.get_schema(str(EXAMPLES_DIR / "example_a.csv"))
        self.assertEqual(schema["birth"], {
            "day": "birth day",
            "month": "birth month",
            "year": "birth year",
        })
        self.assertEqual(schema["name"], "name")
        self.assertEqual(schema["adopted_since"], "adopted_since")

    def test_example_c_schema(self):
        schema = self.hone.get_schema(str(EXAMPLES_DIR / "example_c.csv"))
        self.assertEqual(schema["birth"]["day"], "birth day")
        self.assertEqual(schema["reference"], "reference")
        self.assertEqual(schema["reference name"], "reference name")

    def test_no_nesting_without_delimiter(self):
        schema = self.hone.generate_full_structure(["alpha", "beta"])
        self.assertEqual(schema, {"alpha": "alpha", "beta": "beta"})

    def test_empty_column_names(self):
        self.assertEqual(self.hone.generate_full_structure([]), {})

    def test_head_that_is_also_a_column_blocks_split(self):
        schema = self.hone.generate_full_structure(["a", "a_b"])
        self.assertEqual(schema, {"a": "a", "a_b": "a_b"})

    def test_single_column_is_not_over_split(self):
        schema = self.hone.generate_full_structure(["only_one"])
        self.assertEqual(schema, {"only_one": "only_one"})

    def test_custom_delimiters_nest_recursively(self):
        from hone.hone import Hone

        hone = Hone(delimiters=["_", "-"])
        schema = hone.generate_full_structure(["x_y-z", "x_y-w"])
        self.assertEqual(
            schema, {"x": {"y": {"z": "x_y-z", "w": "x_y-w"}}}
        )

    def test_get_leaves(self):
        schema = self.hone.get_schema(str(EXAMPLES_DIR / "example_b.csv"))
        leaves = self.hone.get_leaves(schema)
        self.assertIn((["a"], "a"), leaves)
        self.assertIn((["a_b"], "a_b"), leaves)
        self.assertIn((["b", "c", "d"], "b_c_d"), leaves)
        self.assertIn((["b", "d", "f"], "b_d_f"), leaves)
        self.assertEqual(len(leaves), 6)

    def test_get_nested_structure_returns_dict(self):
        nested = self.hone.get_nested_structure({"p_q": "p_q", "p_r": "p_r"})
        self.assertEqual(nested, {"p": {"q": "p_q", "r": "p_r"}})
        with self.assertRaises(TypeError):
            self.hone.get_nested_structure(["p_q"])


class SplitHelperTests(unittest.TestCase):
    def setUp(self):
        from hone.hone import Hone

        self.hone = Hone()

    def test_get_valid_splits_order(self):
        self.assertEqual(self.hone.get_valid_splits("birth day"), [(5, " ")])
        self.assertEqual(self.hone.get_valid_splits("a_b c"), [(1, "_"), (3, " ")])
        self.assertEqual(self.hone.get_valid_splits("plain"), [])
        self.assertEqual(self.hone.get_valid_splits("_leading"), [])
        self.assertEqual(self.hone.get_valid_splits("trailing_"), [])

    def test_get_valid_splits_returns_all_candidates_in_order(self):
        from hone.hone import Hone

        hone = Hone(delimiters=["_", ","])
        self.assertEqual(hone.get_valid_splits("a_b,c"), [(1, "_"), (3, ",")])
        self.assertEqual(hone.get_valid_splits("a,b_c"), [(1, ","), (3, "_")])

    def test_get_split_suffix(self):
        self.assertEqual(self.hone.get_split_suffix(" ", "birth day"), "day")
        self.assertEqual(self.hone.get_split_suffix((5, " "), "birth day"), "day")
        self.assertEqual(self.hone.get_split_suffix("_", "plain"), "")

    def test_clean_split_and_prefix(self):
        self.assertEqual(self.hone.clean_split(["a", "", "b"]), ["a", "b"])
        self.assertEqual(self.hone.clean_split("a_b"), "a_b")
        self.assertTrue(self.hone.is_valid_prefix("b_", "b_c_d"))
        self.assertFalse(self.hone.is_valid_prefix("z_", "b_c_d"))
        self.assertFalse(self.hone.is_valid_prefix("", "b_c_d"))

    def test_escape_quotes_compatibility(self):
        self.assertEqual(self.hone.escape_quotes('say "hi"'), 'say "hi"')


if __name__ == "__main__":
    unittest.main()
