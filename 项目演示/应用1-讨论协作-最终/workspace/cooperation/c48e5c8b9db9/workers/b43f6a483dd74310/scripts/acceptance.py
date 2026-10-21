#!/usr/bin/env python3
"""One-click acceptance runner for the hone project (G1-G13).

Owner: package D. Prints a PASS/FAIL table and exits non-zero if anything
fails. Run from anywhere:

    python scripts/acceptance.py

The script only writes to a temporary directory and ``dist/`` (build output);
the committed fixtures/examples are never modified.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS: list[tuple[str, str, bool, str]] = []


def _run(args, *, cwd=ROOT, stdin_text=None, timeout=300):
    return subprocess.run(
        [str(a) for a in args],
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd),
        timeout=timeout,
    )


def _py():
    return sys.executable


def check(gid: str, title: str, fn):
    try:
        detail = fn() or "ok"
        RESULTS.append((gid, title, True, str(detail)))
        print(f"PASS  {gid:<3} {title}  ({detail})")
    except Exception as exc:  # noqa: BLE001 - acceptance runner reports everything
        RESULTS.append((gid, title, False, f"{type(exc).__name__}: {exc}"))
        print(f"FAIL  {gid:<3} {title}  ({type(exc).__name__}: {exc})")


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def _load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def g1_import():
    code = (
        "import hone; from hone.hone import Hone; import hone.utils; "
        "print(hone.Hone, hone.__version__)"
    )
    result = _run([_py(), "-c", code])
    _assert(result.returncode == 0, result.stderr)
    _assert("1.0.0" in result.stdout, result.stdout)
    return result.stdout.strip().splitlines()[-1]


def _fixtures():
    return ROOT / "tests" / "fixtures" / "data_file"


def g2_small_cats():
    sys.path.insert(0, str(ROOT))
    from hone.hone import Hone

    folder = _fixtures() / "small_cats_dataset"
    actual = Hone().convert(folder / "dataset.csv")
    expected = _load_json(folder / "nested_dataset.json")
    _assert(actual == expected, "small_cats output mismatch")
    return f"{len(actual)} rows"


def g3_comma_quotes():
    sys.path.insert(0, str(ROOT))
    from hone.hone import Hone

    for name, rows in (("comma_test", 1), ("quotes_test", 4)):
        folder = _fixtures() / name
        actual = Hone().convert(folder / "dataset.csv")
        expected = _load_json(folder / "nested_dataset.json")
        _assert(actual == expected, f"{name} mismatch")
        _assert(len(actual) == rows, f"{name} expected {rows} rows")
    return "comma_test + quotes_test match"


def g4_examples():
    sys.path.insert(0, str(ROOT))
    from hone.hone import Hone
    from tests.test_golden_samples import EXPECTED_A, EXPECTED_B, EXPECTED_C

    pairs = (
        ("example_a.csv", EXPECTED_A),
        ("example_b.csv", EXPECTED_B),
        ("example_c.csv", EXPECTED_C),
    )
    for name, expected in pairs:
        actual = Hone().convert(ROOT / "examples" / name)
        _assert(actual == expected, f"{name} mismatch")
    _assert(
        Hone().convert(ROOT / "examples" / "example_b.csv")[1]["b"]["d"]["f"] == "12",
        "example_b second-row b.d.f must be 12",
    )
    return "a/b/c inline expectations"


def g5_schema():
    sys.path.insert(0, str(ROOT))
    from hone.hone import Hone
    from hone.utils import parse_json_file

    folder = _fixtures() / "small_cats_dataset"
    expected = parse_json_file(folder / "nested_dataset.json")
    schema = parse_json_file(folder / "nested_schema.json")
    _assert(Hone().convert(folder / "dataset.csv", schema=schema) == expected, "schema convert")
    _assert(Hone().get_schema(folder / "dataset.csv") == schema, "get_schema")
    return "schema mapping + get_schema"


def g6_cli_file_to_file():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.json"
        result = _run(
            [_py(), "-m", "hone", _fixtures() / "small_cats_dataset" / "dataset.csv", out]
        )
        _assert(result.returncode == 0, result.stderr)
        expected = _load_json(_fixtures() / "small_cats_dataset" / "nested_dataset.json")
        obj = _load_json(out)
        _assert(obj == expected, "file output mismatch")
        text = out.read_text(encoding="utf-8")
        _assert(
            text == json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            "file output serialisation mismatch",
        )
    return "python -m hone csv out.json"


def g7_cli_dash_channels():
    example = ROOT / "examples" / "example_c.csv"
    # csv -> "-"
    r1 = _run([_py(), "-m", "hone", example, "-"])
    _assert(r1.returncode == 0 and not r1.stderr, r1.stderr)
    _assert(isinstance(json.loads(r1.stdout), list), "stdout is not JSON")
    # "-" -> "-" via stdin
    text = example.read_text(encoding="utf-8")
    r2 = _run([_py(), "-m", "hone", "-", "-"], stdin_text=text)
    _assert(r2.returncode == 0 and not r2.stderr, r2.stderr)
    _assert(json.loads(r2.stdout) == json.loads(r1.stdout), "stdin/stdout mismatch")
    # "-" -> file
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.json"
        r3 = _run([_py(), "-m", "hone", "-", out], stdin_text=text)
        _assert(r3.returncode == 0 and not r3.stderr, r3.stderr)
        _assert(_load_json(out) == json.loads(r1.stdout), "stdin->file mismatch")
    return "csv->-, -->-, -->file"


def g8_boundaries():
    sys.path.insert(0, str(ROOT))
    from hone.hone import Hone

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        empty = tmp / "empty.csv"
        empty.write_bytes(b"")
        header = tmp / "header.csv"
        header.write_text("a,b\n", encoding="utf-8")
        _assert(Hone().convert(empty) == [], "empty file should convert to []")
        _assert(Hone().convert(header) == [], "header-only should convert to []")
        short = tmp / "short.csv"
        short.write_text("a,b,c\n1,2\n", encoding="utf-8")
        _assert(Hone().convert(short) == [{"a": "1", "b": "2"}], "short row")
    return "empty/header-only/short-row"


def g9_self_tests():
    compile_result = _run([_py(), "-m", "compileall", "-q", "hone"])
    _assert(compile_result.returncode == 0, compile_result.stderr)
    result = _run([_py(), "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"])
    _assert(result.returncode == 0, result.stderr[-3000:])
    tail = [line for line in result.stderr.strip().splitlines() if line.startswith("Ran ")]
    return tail[-1] if tail else "unittest discover"


def _build_wheel():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    result = _run(
        [_py(), "-m", "pip", "wheel", ".", "-w", str(dist), "--no-deps"], timeout=600
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr[-3000:])
    wheels = sorted(dist.glob("hone-1.0.0-*.whl"))
    _assert(wheels, "wheel not produced")
    return wheels[-1]


def g10_wheel_and_venv():
    wheel = _build_wheel()
    import zipfile

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    _assert(not any(n.startswith("tests/") for n in names), "wheel contains tests/")
    _assert(not any(n.startswith("scripts/") for n in names), "wheel contains scripts/")

    with tempfile.TemporaryDirectory() as tmp:
        env_dir = Path(tmp) / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        py = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _assert(py.exists(), f"venv python missing: {py}")
        install = _run([py, "-m", "pip", "install", "--no-index", wheel], timeout=600)
        _assert(install.returncode == 0, install.stderr[-3000:])
        outside = Path(tmp) / "outside"
        outside.mkdir()
        imported = _run([py, "-c", "import hone; print(hone.__version__)"], cwd=outside)
        _assert(imported.returncode == 0 and "1.0.0" in imported.stdout, imported.stderr)
        help_result = _run([py, "-m", "hone", "--help"], cwd=outside)
        _assert(help_result.returncode == 0, help_result.stderr)
        script = env_dir / ("Scripts/hone.exe" if os.name == "nt" else "bin/hone")
        _assert(script.exists(), "console script hone missing")
        script_help = _run([script, "--help"], cwd=outside)
        _assert(script_help.returncode == 0, script_help.stderr)
    return wheel.name


def _find_bash():
    exe = shutil.which("bash")
    if exe:
        return exe
    git = shutil.which("git")
    candidates = []
    if git:
        git_root = Path(git).resolve().parent.parent
        candidates.extend([git_root / "bin" / "bash.exe", git_root / "usr" / "bin" / "bash.exe"])
    for env_var in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_var)
        if base:
            candidates.append(Path(base) / "Git" / "bin" / "bash.exe")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Programs" / "Git" / "bin" / "bash.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def g11_demo():
    demo = _run([_py(), "examples/demo.py"])
    _assert(demo.returncode == 0, demo.stderr)
    json.loads(demo.stdout)
    bash = _find_bash()
    _assert(bash, "bash not found for examples/demo.sh")
    shell = _run([bash, "examples/demo.sh"], cwd=ROOT)
    _assert(shell.returncode == 0, shell.stderr)
    json.loads(shell.stdout)
    return "demo.py + demo.sh"


def g12_readme():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    required = ["pip install", "python -m hone", "-d", "-s", "--delimiters", "--schema"]
    missing = [token for token in required if token not in text]
    _assert(not missing, f"README missing: {missing}")
    return "README usage sections present"


def g13_dependencies():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    _assert("dependencies" not in pyproject.lower(), "pyproject declares dependencies")
    banned = ("import requests", "import pandas", "import numpy", "import yaml")
    for path in (ROOT / "hone").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in banned:
            _assert(token not in source, f"{path} uses non-stdlib {token}")
    return "stdlib only, no dependencies"


def main() -> int:
    print(f"hone acceptance runner  (repo: {ROOT})")
    print("-" * 78)
    for gid, title, fn in (
        ("G1", "importable package", g1_import),
        ("G2", "automatic nesting / small_cats", g2_small_cats),
        ("G3", "comma & quotes extremes", g3_comma_quotes),
        ("G4", "examples a/b/c (b.d.f=12)", g4_examples),
        ("G5", "schema mapping", g5_schema),
        ("G6", "CLI file -> file", g6_cli_file_to_file),
        ("G7", 'CLI "-" channels', g7_cli_dash_channels),
        ("G8", "boundary behaviour", g8_boundaries),
        ("G9", "self tests + compileall", g9_self_tests),
        ("G10", "wheel + clean venv install", g10_wheel_and_venv),
        ("G11", "examples demo", g11_demo),
        ("G12", "README usage", g12_readme),
        ("G13", "stdlib only", g13_dependencies),
    ):
        check(gid, title, fn)

    print("-" * 78)
    passed = sum(1 for _, _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"RESULT: {passed}/{total} passed")
    failed = [gid for gid, _, ok, _ in RESULTS if not ok]
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
