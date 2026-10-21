"""Golden-sample regression tests for the hone CSV -> nested JSON converter.

Owner: package D (tests / regression / README / acceptance).

All expected values are inline constants except for the ``data_file`` samples,
whose golden ``nested_dataset.json`` files are read through ``parse_json_file``.
Comparisons are done on parsed Python objects (``==``), never on raw text,
except where a test explicitly says it checks exact serialised output.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

import hone
from hone.hone import Hone
from hone.utils import parse_json_file
from tests import fixtures_dir, repo_root, task_root

EXPECTED_A = [
    {
        "adopted": "TRUE",
        "adopted_since": "2012",
        "age (years)": "5",
        "birth": {"day": "11", "month": "April", "year": "2011"},
        "name": "Tommy",
        "weight (kg)": "3.6",
    },
    {
        "adopted": "FALSE",
        "adopted_since": "N/A",
        "age (years)": "2",
        "birth": {"day": "6", "month": "May", "year": "2015"},
        "name": "Clara",
        "weight (kg)": "8.2",
    },
    {
        "adopted": "TRUE",
        "adopted_since": "2017",
        "age (years)": "6",
        "birth": {"day": "21", "month": "August", "year": "2011"},
        "name": "Catnip",
        "weight (kg)": "3.3",
    },
    {
        "adopted": "TRUE",
        "adopted_since": "2018",
        "age (years)": "3",
        "birth": {"day": "18", "month": "January", "year": "2015"},
        "name": "Ciel",
        "weight (kg)": "3.1",
    },
]

EXPECTED_B = [
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

EXPECTED_C = [
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


class GoldenDataFileTests(unittest.TestCase):
    """E1-E3: the three ``data_file`` sample folders."""

    def setUp(self):
        self.hone = Hone()
        self.fixtures = fixtures_dir()

    def test_e1_comma_test_matches_golden(self):
        folder = self.fixtures / "data_file" / "comma_test"
        actual = self.hone.convert(folder / "dataset.csv")
        expected = parse_json_file(folder / "nested_dataset.json")
        self.assertEqual(actual, expected)
        self.assertEqual(
            actual,
            [{" \"beep\"\"\"": '"2', '"test","ing"': '"1'}],
        )

    def test_e2_quotes_test_matches_golden(self):
        folder = self.fixtures / "data_file" / "quotes_test"
        actual = Hone().convert(folder / "dataset.csv")
        expected = parse_json_file(folder / "nested_dataset.json")
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 4)
        self.assertEqual(
            sorted(actual[0]["birth"]), ["day", "month", "year"]
        )
        # Full column names that must stay as flat leaves.
        for leaf in (
            "age (years)",
            "weight (kg)",
            "adopted_since",
            "some 'quoted\"' field\"",
        ):
            self.assertIn(leaf, actual[0])

    def test_e3_small_cats_matches_golden(self):
        folder = self.fixtures / "data_file" / "small_cats_dataset"
        expected = parse_json_file(folder / "nested_dataset.json")
        # (1) automatic inference
        self.assertEqual(Hone().convert(folder / "dataset.csv"), expected)
        # (2) explicit schema
        schema = parse_json_file(folder / "nested_schema.json")
        self.assertEqual(
            Hone().convert(folder / "dataset.csv", schema=schema), expected
        )
        # (3) get_schema == nested_schema.json
        self.assertEqual(Hone().get_schema(folder / "dataset.csv"), schema)


class GoldenExamplesTests(unittest.TestCase):
    """E4-E6: examples/*.csv with inline expected constants."""

    def setUp(self):
        self.root = fixtures_dir().parent.parent

    def test_e4_example_a(self):
        actual = Hone().convert(self.root / "examples" / "example_a.csv")
        self.assertEqual(actual, EXPECTED_A)

    def test_e5_example_b_readme_typo_upstream(self):
        # NOTE: examples/README.md shows b.d.f == "1" on the second row; that
        # is an upstream typo in the sample README. The true CSV value is
        # "12" and MUST NOT be changed to match the typo.
        actual = Hone().convert(self.root / "examples" / "example_b.csv")
        self.assertEqual(actual, EXPECTED_B)
        self.assertEqual(actual[1]["b"]["d"]["f"], "12")

    def test_e6_example_c(self):
        actual = Hone().convert(self.root / "examples" / "example_c.csv")
        self.assertEqual(actual, EXPECTED_C)
        self.assertIn("reference", actual[0])
        self.assertIn("reference name", actual[0])
        self.assertIsInstance(actual[0]["birth"], dict)


class GoldenStateAndPurityTests(unittest.TestCase):
    """E15 / E24: instance isolation and pure-function invariants."""

    def setUp(self):
        self.root = fixtures_dir().parent.parent

    def test_e15_state_isolation_between_convert_calls(self):
        h = Hone()
        first = h.convert(self.root / "examples" / "example_a.csv")
        second = h.convert(self.root / "examples" / "example_c.csv")
        self.assertEqual(first, EXPECTED_A)
        self.assertEqual(second, EXPECTED_C)
        # Repeated conversions must not share mutable objects.
        third = h.convert(self.root / "examples" / "example_a.csv")
        self.assertEqual(third, EXPECTED_A)
        self.assertIsNot(third, first)
        self.assertIsNot(third[0], first[0])
        self.assertIsNot(third[0]["birth"], first[0]["birth"])

    def test_e24_get_nested_structure_is_pure_deepcopy(self):
        h = Hone()
        source = {"name": "name", "birth": {"day": "birth day"}}
        snapshot = json.loads(json.dumps(source))
        result = h.get_nested_structure(source)
        self.assertEqual(result, source)
        self.assertIsNot(result, source)
        self.assertIsNot(result["birth"], source["birth"])
        self.assertEqual(source, snapshot)

    def test_e24_get_leaves_is_pure(self):
        h = Hone()
        structure = {"name": "name", "birth": {"day": "birth day"}}
        snapshot = json.loads(json.dumps(structure))
        leaves = h.get_leaves(structure)
        self.assertEqual(leaves, {("name",): "name", ("birth", "day"): "birth day"})
        self.assertEqual(structure, snapshot)

    def test_e24_generate_full_structure_returns_fresh_objects(self):
        h = Hone()
        cols = ["name", "birth day", "birth month", "birth year"]
        one = h.generate_full_structure(cols)
        two = h.generate_full_structure(cols)
        self.assertEqual(one, two)
        self.assertIsNot(one, two)
        self.assertIsNot(one["birth"], two["birth"])


class FixtureIntegrityTests(unittest.TestCase):
    """E16: committed fixture/example copies must be byte-identical."""

    def test_manifest_sha256_all_match(self):
        manifest = fixtures_dir() / "MANIFEST.sha256"
        entries = [
            line.split(maxsplit=1)
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertGreaterEqual(len(entries), 16)
        for expected_digest, rel in entries:
            path = repo_root() / rel
            self.assertTrue(path.is_file(), f"missing: {rel}")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(actual, expected_digest, rel)

    @unittest.skipUnless(
        os.environ.get("HONE_TASK_DIR"), "HONE_TASK_DIR not set for original-vs-copy check"
    )
    def test_original_task_files_match_committed_copies(self):
        original = task_root()
        fixtures = fixtures_dir()
        pairs = []
        for name in (
            "comma_test",
            "quotes_test",
            "small_cats_dataset",
        ):
            for filename in (
                "dataset.csv",
                "column_names.csv",
                "data_rows.csv",
                "nested_dataset.json",
            ):
                pairs.append(
                    (
                        original / "data_file" / name / filename,
                        fixtures / "data_file" / name / filename,
                    )
                )
        for filename in ("example_a.csv", "example_b.csv", "example_c.csv"):
            pairs.append((original / "examples" / filename, repo_root() / "examples" / filename))
        for source, copy in pairs:
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).hexdigest(),
                hashlib.sha256(copy.read_bytes()).hexdigest(),
                str(copy),
            )


class GoldenPackageTests(unittest.TestCase):
    def test_g1_package_import_surface(self):
        self.assertTrue(callable(hone.Hone))
        self.assertEqual(hone.__version__, "1.0.0")
        from hone.hone import Hone as HoneAgain

        self.assertIs(HoneAgain, hone.Hone)
        import importlib

        self.assertIsNotNone(importlib.import_module("hone.utils"))


if __name__ == "__main__":
    unittest.main()
