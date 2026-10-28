"""Acceptance tests for the ``hone`` command line interface (AC10-AC13)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hone.__main__ import main
from hone.hone import Hone

ROOT = Path(__file__).resolve().parents[1]


def _run(args, input_bytes=None, cwd=None):
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + existing if existing else "")
    return subprocess.run(
        [sys.executable, "-m", "hone"] + list(args),
        cwd=str(cwd or ROOT),
        env=env,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


class TestCliFileOutput(unittest.TestCase):
    def test_file_output_equals_convert_and_is_sorted_indented(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.json"
            proc = _run([str(ROOT / "examples" / "example_a.csv"), str(output)])
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
            expected = Hone().convert(str(ROOT / "examples" / "example_a.csv"))
            with output.open(encoding="utf-8") as handle:
                parsed = json.load(handle)
            self.assertEqual(parsed, expected)
            text = output.read_text(encoding="utf-8")
            self.assertEqual(
                text,
                json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False)
                + "\n",
            )

    def test_schema_and_delimiters_options(self):
        schema = json.loads(
            (ROOT / "data_file" / "small_cats_dataset" / "nested_schema.json").read_text(
                encoding="utf-8"
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.json"
            proc = _run(
                [
                    "-d",
                    "[' ', '_', ',']",
                    "-s",
                    json.dumps(schema),
                    str(ROOT / "data_file" / "small_cats_dataset" / "dataset.csv"),
                    str(output),
                ]
            )
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
            expected = json.loads(
                (ROOT / "data_file" / "small_cats_dataset" / "nested_dataset.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), expected)


class TestCliStandardStreams(unittest.TestCase):
    def test_stdout_dash(self):
        proc = _run(["examples/example_a.csv", "-"])
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
        parsed = json.loads(proc.stdout.decode("utf-8"))
        expected = Hone().convert(str(ROOT / "examples" / "example_a.csv"))
        self.assertEqual(parsed, expected)

    def test_stdin_and_stdout_dash(self):
        csv_bytes = (ROOT / "examples" / "example_b.csv").read_bytes()
        proc = _run(["-", "-"], input_bytes=csv_bytes)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
        parsed = json.loads(proc.stdout.decode("utf-8"))
        expected = Hone().convert(str(ROOT / "examples" / "example_b.csv"))
        self.assertEqual(parsed, expected)
        # Input is authoritative: examples/README.md's second row b.d.f is "12".
        self.assertEqual(parsed[1]["b"]["d"]["f"], "12")

    def test_stdin_only(self):
        csv_bytes = (ROOT / "examples" / "example_c.csv").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.json"
            proc = _run(["-", str(output)], input_bytes=csv_bytes)
            self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8"))
            expected = Hone().convert(str(ROOT / "examples" / "example_c.csv"))
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), expected)


class TestCliHelp(unittest.TestCase):
    def test_help_exit_zero_and_mentions_options(self):
        proc = _run(["--help"])
        self.assertEqual(proc.returncode, 0)
        text = proc.stdout.decode("utf-8")
        for token in ["csv_filepath", "json_filepath", "-d", "--delimiters", "-s", "--schema"]:
            self.assertIn(token, text)
        self.assertIn("usage: hone", text)


class TestCliErrors(unittest.TestCase):
    def test_missing_input_file_exits_one_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run([str(Path(tmp) / "does_not_exist.csv"), str(Path(tmp) / "out.json")])
            stderr = proc.stderr.decode("utf-8")
            self.assertEqual(proc.returncode, 1, stderr)
            self.assertIn("hone: error:", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_bad_delimiters_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run(
                [
                    "-d",
                    "not a list",
                    str(ROOT / "examples" / "example_a.csv"),
                    str(Path(tmp) / "out.json"),
                ]
            )
            stderr = proc.stderr.decode("utf-8")
            self.assertEqual(proc.returncode, 2, stderr)
            self.assertIn("hone: error:", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_bad_schema_json_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run(
                [
                    "-s",
                    "{bad}",
                    str(ROOT / "examples" / "example_a.csv"),
                    str(Path(tmp) / "out.json"),
                ]
            )
            stderr = proc.stderr.decode("utf-8")
            self.assertEqual(proc.returncode, 2, stderr)
            self.assertIn("hone: error:", stderr)

    def test_schema_list_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = _run(
                [
                    "-s",
                    "[]",
                    str(ROOT / "examples" / "example_a.csv"),
                    str(Path(tmp) / "out.json"),
                ]
            )
            stderr = proc.stderr.decode("utf-8")
            self.assertEqual(proc.returncode, 2, stderr)
            self.assertIn("hone: error:", stderr)


class TestMainFunction(unittest.TestCase):
    def test_main_returns_zero_for_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out.json"
            code = main([str(ROOT / "examples" / "example_a.csv"), str(output)])
            self.assertEqual(code, 0)
            self.assertTrue(output.is_file())

    def test_main_returns_one_for_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = main([str(Path(tmp) / "missing.csv"), str(Path(tmp) / "out.json")])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
