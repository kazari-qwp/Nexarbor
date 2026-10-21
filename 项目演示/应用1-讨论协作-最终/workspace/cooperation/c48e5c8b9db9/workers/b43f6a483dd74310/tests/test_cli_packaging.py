from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "data_file")
EXAMPLES = os.path.join(ROOT, "examples")

EXAMPLE_B_EXPECTED = [
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


def run_cli(args, input_text=None, cwd=ROOT):
    """Run ``python -m hone`` in a subprocess and return the completed process."""
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    return subprocess.run(
        [sys.executable, "-m", "hone", *args],
        input=input_text,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


class CliFileToFileTests(unittest.TestCase):
    def test_dataset_file_to_file(self):
        csv_path = os.path.join(FIXTURES, "small_cats_dataset", "dataset.csv")
        expected_path = os.path.join(
            FIXTURES, "small_cats_dataset", "nested_dataset.json"
        )
        with open(expected_path, encoding="utf-8") as handle:
            expected = json.load(handle)
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            proc = run_cli([csv_path, out_path])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stderr, "")
            with open(out_path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), expected)
            with open(out_path, encoding="utf-8", newline="") as handle:
                text = handle.read()
            self.assertEqual(
                text,
                json.dumps(expected, indent=2, sort_keys=True, ensure_ascii=False)
                + "\n",
            )


class CliStdoutTests(unittest.TestCase):
    def test_csv_to_stdout(self):
        proc = run_cli([os.path.join(EXAMPLES, "example_c.csv"), "-"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")
        self.assertEqual(json.loads(proc.stdout), EXAMPLE_C_EXPECTED)

    def test_exact_stdout_text(self):
        proc = run_cli([os.path.join(EXAMPLES, "example_c.csv"), "-"])
        self.assertEqual(
            proc.stdout,
            json.dumps(
                EXAMPLE_C_EXPECTED, indent=2, sort_keys=True, ensure_ascii=False
            )
            + "\n",
        )


class CliStdinTests(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(EXAMPLES, "example_b.csv"), encoding="utf-8") as handle:
            self.csv_text = handle.read()

    def test_stdin_to_stdout(self):
        proc = run_cli(["-", "-"], input_text=self.csv_text)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), EXAMPLE_B_EXPECTED)

    def test_stdin_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            proc = run_cli(["-", out_path], input_text=self.csv_text)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out_path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), EXAMPLE_B_EXPECTED)


class CliOptionTests(unittest.TestCase):
    def test_schema_option(self):
        dataset = os.path.join(FIXTURES, "small_cats_dataset", "dataset.csv")
        schema_path = os.path.join(
            FIXTURES, "small_cats_dataset", "nested_schema.json"
        )
        expected_path = os.path.join(
            FIXTURES, "small_cats_dataset", "nested_dataset.json"
        )
        with open(schema_path, encoding="utf-8") as handle:
            schema_text = handle.read()
        with open(expected_path, encoding="utf-8") as handle:
            expected = json.load(handle)
        proc = run_cli(["-s", schema_text, dataset, "-"])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), expected)

    def test_delimiters_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "data.csv")
            with open(csv_path, "w", encoding="utf-8", newline="") as handle:
                handle.write("x_y,x_z\n1,2\n")
            proc = run_cli(["-d", "['_']", csv_path, "-"])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(
                json.loads(proc.stdout), [{"x": {"y": "1", "z": "2"}}]
            )
            out_path = os.path.join(tmp, "out.json")
            proc = run_cli(["-d", "['::']", csv_path, out_path])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with open(out_path, encoding="utf-8") as handle:
                self.assertEqual(
                    json.load(handle), [{"x_y": "1", "x_z": "2"}]
                )

    def test_help(self):
        proc = run_cli(["-h"])
        self.assertEqual(proc.returncode, 0)
        self.assertIn("csv_filepath", proc.stdout)
        self.assertIn("json_filepath", proc.stdout)


class CliErrorTests(unittest.TestCase):
    def test_bad_schema(self):
        proc = run_cli(
            ["-s", "{bad", os.path.join(EXAMPLES, "example_c.csv"), "-"]
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", proc.stderr)

    def test_schema_not_object(self):
        proc = run_cli(
            ["-s", "[1,2]", os.path.join(EXAMPLES, "example_c.csv"), "-"]
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", proc.stderr)

    def test_bad_delimiters(self):
        proc = run_cli(
            ["-d", "notalist[", os.path.join(EXAMPLES, "example_c.csv"), "-"]
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", proc.stderr)

    def test_missing_positional(self):
        proc = run_cli([])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("error", proc.stderr)

    def test_missing_csv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "out.json")
            proc = run_cli([os.path.join(tmp, "does_not_exist.csv"), out_path])
            self.assertEqual(proc.returncode, 1)
            self.assertIn("error", proc.stderr)


class DemoAndPackagingTests(unittest.TestCase):
    def test_demo_script_runs(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = ROOT
        proc = subprocess.run(
            [sys.executable, os.path.join(EXAMPLES, "demo.py")],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIsInstance(json.loads(proc.stdout), list)

    def test_pyproject_declares_console_script(self):
        pyproject = os.path.join(ROOT, "pyproject.toml")
        with open(pyproject, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn('[project.scripts]', text)
        self.assertIn('hone = "hone.__main__:main"', text)
        self.assertIn('name = "hone"', text)
        self.assertIn('version = "1.0.0"', text)


if __name__ == "__main__":
    unittest.main()
