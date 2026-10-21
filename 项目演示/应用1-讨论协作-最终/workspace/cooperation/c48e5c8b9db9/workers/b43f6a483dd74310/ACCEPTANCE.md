# hone 1.0.0 — Acceptance Record

Candidate: `v1.0.0-rc1` · Release: `v1.0.0`
Repository: `E:\DataNet-模块化成品\build\agent-learning-20261020\node-object-hone-03\project\workspace\cooperation\c48e5c8b9db9\main`
Rule: all four members must pass; any failure sends the issue back to the file
owner and the candidate is re-run (no majority vote).

## D — full test suite, acceptance runner, sample diff (owner of tests/README)

Commands and results:

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
| fixtures manifest (E16) | PASS | all 16 sha256 entries match; originals match copies |

Signed: **D / admin-a74b45** — PASS

## A — CLI `-` channels and smoke tests

To be completed with A's command output.

Signed: **A / admin-76b526** — ____

## B — schema/utils and E1/E2

To be completed with B's command output.

Signed: **B / admin-726762** — ____

## C — clean venv, out-of-repo import/CLI, demo

To be completed with C's command output.

Signed: **C / admin-3c5fde** — ____

## Final decision

- 4/4 cross-acceptance passed → merge to `main`, tag `v1.0.0`, build
  `dist/hone-1.0.0-py3-none-any.whl`.
