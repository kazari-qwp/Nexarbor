import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from hone.hone import Hone

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class ExampleConversionTest(unittest.TestCase):
    def test_example_a_matches_readme(self):
        expected = [
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
        self.assertEqual(Hone().convert(EXAMPLES / "example_a.csv"), expected)

    def test_example_b_matches_expected_structure(self):
        expected = [
            {
                "a": "1",
                "a_b": "2",
                "b": {"c": {"d": "3", "e": "4"}, "d": {"e": "5", "f": "6"}},
            },
            {
                "a": "7",
                "a_b": "8",
                # examples/README.md shows "1" here; the CSV value "12" wins.
                "b": {"c": {"d": "9", "e": "10"}, "d": {"e": "11", "f": "12"}},
            },
        ]
        result = Hone().convert(EXAMPLES / "example_b.csv")
        self.assertEqual(result, expected)
        self.assertEqual(result[1]["b"]["d"]["f"], "12")
        self.assertEqual(result[0]["a"], "1")
        self.assertEqual(result[0]["a_b"], "2")

    def test_example_c_matches_readme(self):
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
        self.assertEqual(Hone().convert(EXAMPLES / "example_c.csv"), expected)


class DemoTest(unittest.TestCase):
    def test_demo_script_runs(self):
        import os

        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, "examples/demo.py"],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        parsed = json.loads(completed.stdout)
        self.assertEqual(len(parsed), 4)
        self.assertEqual(parsed[0]["name"], "Tommy")


class SampleFilesUnchangedTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_public_samples_and_docs_are_untouched(self):
        diff = subprocess.run(
            ["git", "diff", "--exit-code", "HEAD", "--", "docs", "data_file", "examples"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(diff.returncode, 0, diff.stdout + diff.stderr)
        status = subprocess.run(
            ["git", "status", "--porcelain", "--", "docs", "data_file", "examples"],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(status.stdout.strip(), "")


class ReadmeTest(unittest.TestCase):
    def test_readme_covers_required_topics(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for needle in [
            "pip install .",
            "python -m hone examples/example_a.csv -",
            "python -m hone - - < examples/example_b.csv",
            "get_schema",
            "convert",
            "python -m unittest discover -s tests -t . -v",
            "Behavior and limitations",
        ]:
            self.assertIn(needle, readme)
