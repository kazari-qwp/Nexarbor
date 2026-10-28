#!/usr/bin/env python3
"""Independent acceptance harness for the hone project (AC1-AC15).

Run from anywhere:

    python scripts/verify_acceptance.py            # full run (includes wheel/venv)
    python scripts/verify_acceptance.py --quick    # skip AC14/AC15 heavy parts

The script only uses the standard library, locates the repository root from its
own path (never from the current working directory), and prints one PASS/FAIL
line per check.  Exit code 0 means every non-skipped check passed.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

_state = {"passed": 0, "failed": 0, "skipped": 0, "failures": []}


def report(check_id, fn, quick_ok=True, quick=False):
    if quick and quick_ok:
        _state["skipped"] += 1
        print("SKIP %-4s (quick mode)" % check_id)
        return
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001 - acceptance harness reports everything
        _state["failed"] += 1
        _state["failures"].append(check_id)
        print("FAIL %-4s %s: %s" % (check_id, type(exc).__name__, exc))
        if os.environ.get("HONE_VERBOSE"):
            traceback.print_exc()
    else:
        _state["passed"] += 1
        print("PASS %-4s%s" % (check_id, (" - " + detail) if detail else ""))


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("PYTHONHOME", None)
    return env


def run(cmd, stdin_bytes=None, timeout=180, cwd=ROOT):
    return subprocess.run(
        cmd,
        input=stdin_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd),
        env=_env(),
        timeout=timeout,
    )


def _load(path):
    with io.open(str(path), encoding="utf-8") as fh:
        return json.load(fh)


def _data(*parts):
    return ROOT.joinpath("data_file", *parts)


def _examples(*parts):
    return ROOT.joinpath("examples", *parts)


def _import_hone():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import hone  # noqa: F401
    from hone.hone import Hone  # noqa: F401
    return hone, Hone


def ac1_import():
    hone, Hone = _import_hone()
    assert hone.Hone is Hone, "hone.Hone is not hone.hone.Hone"
    assert Hone.DEFAULT_DELIMITERS == [",", "_", " "], Hone.DEFAULT_DELIMITERS
    inst = Hone(delimiters=None)
    assert inst.delimiters == [",", "_", " "]
    return "hone.Hone is Hone; DEFAULT_DELIMITERS ok"


def ac2_csv_utils():
    _import_hone()
    from hone.utils.csv_utils import CSVUtils

    comma = _data("comma_test")
    utils = CSVUtils(str(comma / "column_names.csv"))
    assert utils.get_column_names() == ['"test","ing"', ' "beep"""'], utils.get_column_names()

    names = CSVUtils(str(comma / "column_names.csv"))
    dataset = CSVUtils(str(comma / "dataset.csv"))
    # get_all_rows returns list[list] (all records); get_column_names is the
    # flat first row, so compare the first record against the column names.
    assert names.get_all_rows() == [dataset.get_column_names()], names.get_all_rows()
    assert names.get_all_rows() == [['"test","ing"', ' "beep"""']], names.get_all_rows()

    rows = CSVUtils(str(comma / "data_rows.csv"))
    assert rows.get_data_rows() == [], rows.get_data_rows()
    assert rows.get_all_rows() == dataset.get_data_rows()
    assert rows.get_all_rows() == [['"1', '"2']]

    # caching: reading twice must not consume a stream twice
    utils2 = CSVUtils(str(comma / "dataset.csv"))
    first = utils2.get_all_rows()
    second = utils2.get_all_rows()
    assert first is second or first == second
    assert len(second) == 2

    # '-' means stdin; the instance parses lazily and caches all rows
    from unittest import mock

    fake = io.StringIO("a,b\n1,2\n")
    with mock.patch("sys.stdin", fake):
        su = CSVUtils("-")
        assert su.get_column_names() == ["a", "b"], su.get_column_names()
        assert su.get_data_rows() == [["1", "2"]], su.get_data_rows()
        assert su.get_all_rows() == [["a", "b"], ["1", "2"]], su.get_all_rows()
    return "column names/data rows/empty filter/cache/stdin ok"


def ac3_auto_schema():
    _, Hone = _import_hone()
    got = Hone().get_schema(str(_data("small_cats_dataset", "dataset.csv")))
    want = _load(_data("small_cats_dataset", "nested_schema.json"))
    assert got == want, "schema mismatch: %r" % (got,)
    return "small_cats auto schema equals nested_schema.json"


def ac4_auto_convert():
    _, Hone = _import_hone()
    for folder in ("comma_test", "quotes_test", "small_cats_dataset"):
        got = Hone().convert(str(_data(folder, "dataset.csv")))
        want = _load(_data(folder, "nested_dataset.json"))
        assert got == want, "%s mismatch: %r" % (folder, got)
    return "comma_test/quotes_test/small_cats auto conversion ok"


def ac5_explicit_schema():
    _, Hone = _import_hone()
    schema = _load(_data("small_cats_dataset", "nested_schema.json"))
    csv_path = str(_data("small_cats_dataset", "dataset.csv"))
    want = _load(_data("small_cats_dataset", "nested_dataset.json"))
    inst = Hone()
    got = inst.convert(csv_path, schema=schema)
    assert got == want, "dict schema mismatch"
    got_json = inst.convert(csv_path, schema=json.dumps(schema))
    assert got_json == want, "JSON-string schema mismatch"
    generated = inst.get_schema(csv_path)
    assert inst.convert(csv_path, schema=generated) == want
    return "dict/JSON-str/generated schema conversions ok"


def ac6_comma_exact():
    _import_hone()
    from hone.utils.csv_utils import CSVUtils

    comma = _data("comma_test")
    assert CSVUtils(str(comma / "column_names.csv")).get_column_names() == [
        '"test","ing"',
        ' "beep"""',
    ]
    assert CSVUtils(str(comma / "data_rows.csv")).get_data_rows() == []
    assert CSVUtils(str(comma / "data_rows.csv")).get_all_rows() == [['"1', '"2']]
    _, Hone = _import_hone()
    got = Hone().convert(str(comma / "dataset.csv"))
    want = _load(comma / "nested_dataset.json")
    assert got == want, "comma_test output mismatch: %r" % (got,)
    return "no second unescaping; exact fixture output"


def ac7_quotes_and_empty():
    _, Hone = _import_hone()
    got = Hone().convert(str(_data("quotes_test", "dataset.csv")))
    want = _load(_data("quotes_test", "nested_dataset.json"))
    assert got == want, "quotes_test mismatch"
    key = "some 'quoted\"' field\""
    assert got[1][key] == "one double \" and one single ' quote"
    assert got[1]["adopted_since"] == "N/A"
    assert got[2][key] == "two \"double\" and two 'single' quotes"

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "empty_cell.csv"
        path.write_text("a,b,c\n1,,3\n", encoding="utf-8")
        out = Hone().convert(str(path))
        assert out == [{"a": "1", "b": "", "c": "3"}], out
    return "quotes, N/A, empty cell -> ''"


def ac8_example_b():
    _, Hone = _import_hone()
    got = Hone().convert(str(_examples("example_b.csv")))
    # Expected per examples/README.md, except its typo "1" for row 2 b.d.f:
    # the CSV input contains 12, so the conversion must yield "12".
    want = [
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
    assert got == want, "example_b mismatch: %r" % (got,)
    assert got[1]["b"]["d"]["f"] == "12"
    return "b.c.{d,e}, b.d.{e,f}; row2 b.d.f == '12'"


def _expected_example_a():
    rows = [
        ("Tommy", "5", "3.6", "11", "April", "2011", "TRUE", "2012"),
        ("Clara", "2", "8.2", "6", "May", "2015", "FALSE", "N/A"),
        ("Catnip", "6", "3.3", "21", "August", "2011", "TRUE", "2017"),
        ("Ciel", "3", "3.1", "18", "January", "2015", "TRUE", "2018"),
    ]
    return [
        {
            "adopted": r[6],
            "adopted_since": r[7],
            "age (years)": r[1],
            "birth": {"day": r[3], "month": r[4], "year": r[5]},
            "name": r[0],
            "weight (kg)": r[2],
        }
        for r in rows
    ]


def _expected_example_c():
    rows = [
        ("Bob", "7", "May", "1985", "TRUE", "Smith"),
        ("Julia", "21", "January", "1997", "FALSE", "N/A"),
        ("Rick", "12", "June", "1996", "TRUE", "Clara"),
    ]
    return [
        {
            "birth": {"day": r[1], "month": r[2], "year": r[3]},
            "name": r[0],
            "reference": r[4],
            "reference name": r[5],
        }
        for r in rows
    ]


def ac9_examples():
    _, Hone = _import_hone()
    # Expected values come from examples/README.md, which is the published spec
    # for these samples (the repository has no example_*.json files).
    got = Hone().convert(str(_examples("example_a.csv")))
    assert got == _expected_example_a(), "example_a mismatch: %r" % (got,)
    got = Hone().convert(str(_examples("example_c.csv")))
    assert got == _expected_example_c(), "example_c mismatch: %r" % (got,)
    proc = run([PY, "examples/demo.py"])
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    demo_text = proc.stdout.decode("utf-8", "replace")
    assert demo_text.strip().startswith("["), "demo output not JSON"
    assert json.loads(demo_text) == _expected_example_a()
    return "example_a/c match examples/README; examples/demo.py runs"


def ac10_cli_file():
    _, Hone = _import_hone()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.json"
        proc = run([PY, "-m", "hone", str(_examples("example_a.csv")), str(out)])
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
        assert out.exists(), "output file missing"
        text = out.read_text(encoding="utf-8")
        got = json.loads(text)
        want = Hone().convert(str(_examples("example_a.csv")))
        assert got == want, "CLI output differs from API"
        expected_text = json.dumps(want, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        assert text == expected_text, "text is not indent=2/sort_keys with trailing newline"
    return "CLI file output equals API; indent=2/sort_keys/trailing newline"


def ac11_cli_stdio():
    _, Hone = _import_hone()
    proc = run([PY, "-m", "hone", str(_examples("example_a.csv")), "-"])
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    got = json.loads(proc.stdout.decode("utf-8"))
    assert got == _expected_example_a(), "stdout conversion differs"

    csv_bytes = _examples("example_b.csv").read_bytes()
    proc = run([PY, "-m", "hone", "-", "-"], stdin_bytes=csv_bytes)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    got = json.loads(proc.stdout.decode("utf-8"))
    assert got == Hone().convert(str(_examples("example_b.csv"))), "stdin conversion differs"
    assert got[1]["b"]["d"]["f"] == "12"
    return "stdout and stdin ('- -') round-trips ok"


def ac12_help():
    proc = run([PY, "-m", "hone", "--help"])
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    text = proc.stdout.decode("utf-8")
    for token in ("csv_filepath", "json_filepath", "-d", "--delimiters", "-s", "--schema"):
        assert token in text, "help missing %r" % token
    return "help exit 0 and documents positionals/-d/-s"


def ac13_error_codes():
    cases = [
        ([PY, "-m", "hone", str(_examples("does_not_exist.csv")), "-"], 1),
        ([PY, "-m", "hone", "-d", "not a list", str(_examples("example_a.csv")), "-"], 2),
        ([PY, "-m", "hone", "-s", "{bad}", str(_examples("example_a.csv")), "-"], 2),
        ([PY, "-m", "hone", "-s", "[]", str(_examples("example_a.csv")), "-"], 2),
    ]
    for cmd, want in cases:
        proc = run(cmd)
        err = proc.stderr.decode("utf-8", "replace")
        assert proc.returncode == want, "%r -> %d (want %d): %s" % (cmd[3:], proc.returncode, want, err)
        assert "hone: error:" in err, "missing hone: error: prefix: %r" % err
        assert "Traceback" not in err, "traceback leaked: %r" % err
    return "1 for missing file; 2 for bad -d/-s; single-line hone: error:"


def ac14_packaging(quick=False):
    clean_env = dict(os.environ)
    clean_env.pop("PYTHONPATH", None)
    clean_env.pop("PYTHONHOME", None)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        proc = run([PY, "-m", "pip", "wheel", ".", "--no-build-isolation", "-w", str(tmp)], timeout=600)
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")[-3000:] + proc.stderr.decode("utf-8", "replace")[-3000:]
        wheels = sorted(tmp.glob("hone-*.whl"))
        assert wheels, "no wheel produced"
        wheel = wheels[-1]

        # Build/install in a *clean* environment: exporting PYTHONPATH=<repo>
        # would make pip see the source tree's hone.egg-info as an installed
        # distribution and silently skip the wheel.
        venv = tmp / "venv"
        proc = subprocess.run(
            [PY, "-m", "venv", str(venv)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(tmp), env=clean_env, timeout=300,
        )
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
        vpy = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        assert vpy.exists(), "venv python missing"
        proc = subprocess.run(
            [str(vpy), "-m", "pip", "install", "--no-index", "--no-deps", "--force-reinstall", str(wheel)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(tmp), env=clean_env, timeout=300,
        )
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
        assert b"Successfully installed" in proc.stdout, "wheel was not installed: " + proc.stdout.decode("utf-8", "replace")

        proc = subprocess.run(
            [str(vpy), "-c", "import hone; from hone.hone import Hone; print(hone.Hone is Hone)"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(tmp), env=clean_env, timeout=120,
        )
        assert proc.returncode == 0 and b"True" in proc.stdout, proc.stderr.decode("utf-8", "replace")

        hone_exe = venv / ("Scripts/hone.exe" if os.name == "nt" else "bin/hone")
        assert hone_exe.exists(), "hone console script missing"
        for cmd in ([str(hone_exe), "--help"], [str(vpy), "-m", "hone", "--help"]):
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(tmp), env=clean_env, timeout=120)
            assert proc.returncode == 0, "%r: %s" % (cmd, proc.stderr.decode("utf-8", "replace"))
    dist_wheels = sorted((ROOT / "dist").glob("hone-*.whl"))
    return "wheel builds/installs; import + hone --help + python -m hone ok; dist=%s" % (
        [w.name for w in dist_wheels] or "MISSING",
    )


def ac15_full(quick=False):
    # Run the documented command exactly as a user would: cwd=repo root puts
    # the root on sys.path, so no PYTHONPATH injection is needed.  Injecting
    # it would also make pip inside test_packaging see hone.egg-info as an
    # installed distribution and skip the wheel install.
    clean_env = dict(os.environ)
    clean_env.pop("PYTHONPATH", None)
    clean_env.pop("PYTHONHOME", None)
    proc = subprocess.run(
        [PY, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(ROOT), env=clean_env, timeout=900,
    )
    out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, "unittest failed:\n" + out[-4000:]
    ok_lines = [ln for ln in out.splitlines() if ln.startswith("OK")]
    proc = run([PY, "examples/demo.py"])
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")

    if shutil.which("git"):
        proc = run(["git", "diff", "--exit-code", "HEAD", "--", "docs", "data_file", "examples"])
        assert proc.returncode == 0, "docs/data_file/examples modified:\n" + proc.stdout.decode("utf-8", "replace")
        proc = run(["git", "status", "--porcelain"])
        assert proc.returncode == 0
        assert not proc.stdout.strip(), "git status not clean:\n" + proc.stdout.decode("utf-8", "replace")
    return "unittest all green (%s); demo ok; samples untouched; git clean" % (ok_lines or "OK",)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    quick = "--quick" in argv
    print("hone acceptance harness")
    print("repo root : %s" % ROOT)
    print("python    : %s" % sys.version.split()[0])
    print("mode      : %s" % ("quick" if quick else "full"))
    print("-" * 72)
    report("AC1", ac1_import)
    report("AC2", ac2_csv_utils)
    report("AC3", ac3_auto_schema)
    report("AC4", ac4_auto_convert)
    report("AC5", ac5_explicit_schema)
    report("AC6", ac6_comma_exact)
    report("AC7", ac7_quotes_and_empty)
    report("AC8", ac8_example_b)
    report("AC9", ac9_examples)
    report("AC10", ac10_cli_file)
    report("AC11", ac11_cli_stdio)
    report("AC12", ac12_help)
    report("AC13", ac13_error_codes)
    report("AC14", ac14_packaging, quick_ok=True, quick=quick)
    report("AC15", ac15_full, quick_ok=False, quick=quick)
    print("-" * 72)
    total = _state["passed"] + _state["failed"]
    print(
        "RESULT: %d passed, %d failed, %d skipped (of %d executed)"
        % (_state["passed"], _state["failed"], _state["skipped"], total)
    )
    if _state["failures"]:
        print("FAILED CHECKS: " + ", ".join(_state["failures"]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
