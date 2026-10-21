# hone 1.0.0 — Acceptance Record

Candidate: `v1.0.0-rc1` (tag points at `04ed23a`, includes the Windows LF fix) ·
Release: `v1.0.0`
Repository (integrated main): `E:\DataNet-模块化成品\build\agent-learning-20261020\node-object-hone-03\project\workspace\cooperation\c48e5c8b9db9\main`
Rule: all four members must pass; any failure sends the issue back to the file
owner and the candidate is re-run (no majority vote).

## D — full test suite, acceptance runner, sample diff (owner of tests/README)

Commands and results (run on integrated main):

```console
> python -m unittest discover -s tests -t . -v
Ran 100 tests in ~1.1s
OK (skipped=1)            # skip only when HONE_TASK_DIR is unset

> $env:HONE_TASK_DIR='...\project\workspace\task'; python -m unittest discover -s tests -t . -v
Ran 100 tests in ~1.2s
OK

> python -m compileall -q hone
(exit 0)

> python scripts/acceptance.py
PASS G1 ... PASS G13
RESULT: 13/13 passed
```

Sample diff report (parsed-object comparison):

| Sample | Result | Notes |
|---|---|---|
| `data_file/comma_test/dataset.csv` | PASS | == `nested_dataset.json`; 1 row, quoted-comma headers preserved |
| `data_file/quotes_test/dataset.csv` | PASS | == `nested_dataset.json`; 4 rows, `birth` nested, 4 whole-name leaves |
| `data_file/small_cats_dataset/dataset.csv` | PASS | auto == schema-driven == `nested_dataset.json`; `get_schema` == `nested_schema.json` |
| `examples/example_a.csv` | PASS | 4 rows, inline expectation |
| `examples/example_b.csv` | PASS | `b.c.{d,e}`, `b.d.{e,f}`; row 2 `b.d.f == "12"` (README typo `"1"` intentionally not followed) |
| `examples/example_c.csv` | PASS | `birth` nested; `reference` / `reference name` flat leaves |
| stdout exactness (E17) | PASS | `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False) + "\n"`; empty input `"[]\n"`; stderr empty |
| fixtures manifest (E16) | PASS | all 16 sha256 entries match; originals under `workspace/task` match copies |
| demos (E23) | PASS | `python examples/demo.py` and `bash examples/demo.sh` (Git Bash `E:\Git\bin\bash.exe`) both exit 0, stdout valid JSON |

Signed: **D / admin-a74b45** — PASS

## A — CLI `-` channels and smoke tests

Run on `main=04ed23a` from the repository root:

1. `python -m compileall -q hone` → exit 0.
2. E8 `csv→"-"`: `python -m hone examples/example_c.csv -` → exit 0, stderr
   empty; `json.loads` → 3 rows, `name0=Bob`, `reference name=Smith`.
3. E9a `"-"→"-"` (pipe): `Get-Content examples\example_b.csv -Raw | python -m hone - -`
   → exit 0, stderr empty; 2 rows, `a_b=8`, `b.d.f=12`.
4. E9b `"-"→file`: pipe into `python -m hone - out.json` → exit 0, stderr
   empty; 2 rows, `b.d.f=12`.
5. E18 stdin single consumption (quotes_test, 4 rows): pipe into
   `python -m hone - -` → exit 0, stderr empty; 4 rows, `birth` keys
   `['day','month','year']`.
6. E17 exact stdout (example_a): raw stdout ==
   `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`;
   trailing single LF.
7. Three CLI smoke tests: file→file (small_cats, exit 0), csv→`"-"`
   (example_c, exit 0), stdin→file (example_b, exit 0, `b.d.f=12`).
8. `python -m unittest discover -s tests -t . -v` → Ran 100 tests, OK
   (skipped=1); `python scripts/acceptance.py` → 13/13 PASS; wheel built and
   contains no `tests/`/`scripts/`.

Signed: **A / admin-76b526** — PASS

## B — schema/utils and E1/E2

Run on `main=04ed23a`:

1. `python -m compileall -q hone` → exit 0.
2. `python -m unittest discover -s tests -t . -v` → Ran 100 tests, OK
   (skipped=1).
3. E1/E2/E3: `comma_test`, `quotes_test`, `small_cats_dataset` all
   `convert() == nested_dataset.json`; schema-driven convert == golden;
   `get_schema() == nested_schema.json`.
4. E14: dataset shapes `[2, 9, 8]` columns; comma headers
   `['"test","ing"', ' "beep"""']`.
5. E21: missing schema column omitted, unreferenced column dropped, JSON-string
   schema equivalent to dict.
6. E17 byte level: empty input stdout `b'[]\n'`; example_a stdout bytes exactly
   `json.dumps(..., indent=2, sort_keys=True, ensure_ascii=False) + b'\n'`,
   stderr empty (Windows CRLF translation fixed by `fd1294d`).
7. `python scripts/acceptance.py` → 13/13 PASS.

Signed: **B / admin-726762** — PASS

## C — clean venv, out-of-repo import/CLI, demo

Run against the wheel built from the candidate:

1. `python -m venv %TEMP%\hone-accept-venv` → exit 0;
   `pip install --no-deps dist\hone-1.0.0-py3-none-any.whl` →
   `Successfully installed hone-1.0.0`.
2. Out of repo (`cwd=%TEMP%`):
   `python -c "import hone,hone.hone,hone.utils; print(hone.__version__, hone.Hone)"`
   → `1.0.0 <class 'hone.hone.Hone'>`; `__file__` under `site-packages`.
3. Out of repo `hone --help` → correct usage line, exit 0.
4. Out of repo `python -m hone <small_cats dataset.csv> out.json` → exit 0,
   4 rows, keys correct.
5. Wheel contents: only `hone/*` + `dist-info` (incl. `entry_points.txt`,
   `LICENSE`), no `tests/`, no `scripts/`.
6. `main` full discover 100 tests OK (skipped=1); `compileall` exit 0; three CLI
   smoke tests exit 0 (stdin→file with `b.d.f=12`).
7. E23 demo: `python examples/demo.py` exit 0 and valid JSON; with
   `HONE_TASK_DIR` pointing at `workspace\task` also exit 0.

Environment note (not a defect): `bash` is not on PATH in this machine; the D
acceptance runner locates Git Bash at `E:\Git\bin\bash.exe`, so `examples/demo.sh`
was also verified to exit 0 with valid JSON.

Signed: **C / admin-3c5fde** — PASS

## Final decision

- 4/4 cross-acceptance passed → merge to `main`, tag `v1.0.0`, build
  `dist/hone-1.0.0-py3-none-any.whl` and verify installable in a clean venv.
