# hone 1.0.0 — Release Notes

Release date: 2026-10-20
Tag: `v1.0.0` (release candidate: `v1.0.0-rc1`)

`hone` converts flat CSV files into automatically nested JSON. The package is
importable as `hone`, ships a `python -m hone` / `hone` command line interface,
and depends only on the Python standard library (Python >= 3.8).

## Deliverables

| Item | Path |
|---|---|
| Package | `hone/` (`hone/hone.py`, `hone/__init__.py`, `hone/__main__.py`, `hone/utils/`) |
| CLI | `python -m hone` / console script `hone` (`hone.__main__:main`) |
| Tests | `tests/` (stdlib `unittest`, includes byte-identical `tests/fixtures/**`) |
| Acceptance runner | `scripts/acceptance.py` (G1–G13) |
| Docs | `README.md`, `CONTRACT.md`, `RELEASE_NOTES.md`, `ACCEPTANCE.md` |
| Packaging | `pyproject.toml`, `LICENSE` (MIT) |
| Wheel | `dist/hone-1.0.0-py3-none-any.whl` |

## How to verify

```console
# full test suite (from repository root)
python -m unittest discover -s tests -t . -v

# same suite against the original read-only task material
HONE_TASK_DIR=<task dir> python -m unittest discover -s tests -t . -v

# one-click acceptance G1-G13 (includes wheel build + clean venv install)
python scripts/acceptance.py

# build the wheel
python -m pip wheel . -w dist
```

## Acceptance evidence (recorded on the integrated repository)

- `python -m unittest discover -s tests -t . -v` → **Ran 100 tests, OK**
  (1 optional test skipped only when `HONE_TASK_DIR` is unset).
- `HONE_TASK_DIR=E:\...\project\workspace\task python -m unittest discover -s tests -t . -v`
  → **Ran 100 tests, OK** (original task bytes match the committed copies).
- `python -m compileall -q hone` → exit 0.
- `python scripts/acceptance.py` → **13/13 PASS**: import (G1), small_cats
  nesting (G2), comma/quotes extremes (G3), examples a/b/c (G4), schema (G5),
  CLI file→file (G6), CLI `-` channels (G7), boundaries (G8), self tests (G9),
  wheel + clean venv install + console script (G10), demos (G11), README (G12),
  stdlib only (G13).
- Sample comparisons: `comma_test`, `quotes_test`, `small_cats_dataset` all
  equal their committed `nested_dataset.json`; `examples/example_a|c.csv`
  reproduce the documented structures; `examples/example_b.csv` reproduces
  `b.c.{d,e}` / `b.d.{e,f}` with second-row `b.d.f == "12"`.
- Fixtures/examples integrity: `tests/fixtures/MANIFEST.sha256` covers all
  committed copies (13 fixture files + 3 example CSVs) and matches. The
  read-only originals under `workspace/task/**` are unchanged.

### 4/4 cross-acceptance (see `ACCEPTANCE.md`)

| Reviewer | Focus | Result |
|---|---|---|
| A (admin-76b526) | CLI `-` channels (E8/E9/E18) + 3 smoke tests | PASS |
| B (admin-726762) | schema/utils (E3/E14/E21) + E1/E2 | PASS |
| C (admin-3c5fde) | clean venv, out-of-repo import/CLI (E22) + E23 | PASS |
| D (admin-a74b45) | full unittest + acceptance.py + E16/E17 + sample diff | PASS |

## Known limitations

- Values are always strings; no type inference (`TRUE`, numbers stay strings).
- Nesting is inferred only from the delimiters `[',', '_', ' ']` unless `-d`
  overrides them. Two different column names that collapse to the same nested
  path at the same level resolve last-one-wins.
- `-d` / `-s` use `nargs="?"`; a value must be a complete quoted argument,
  otherwise argparse consumes the following positional argument (exit code 2).
  This is documented in README.
- **Upstream typo, unchanged:** `examples/README.md` shows `b.d.f == "1"` for
  the second row of `example_b.csv`. The true CSV value is `"12"`; the converter
  and tests deliberately use `"12"`. The sample CSV is read-only and was not
  edited.
- No streaming: the whole CSV is read once into memory (required so `-` stdin
  is consumed exactly once).

## Release checklist

- [x] base → `b-utils` → `a-core` → `c-cli` → `d-tests` merged in order.
- [x] `v1.0.0-rc1` candidate built; 4/4 cross-acceptance passed.
- [x] `v1.0.0` tag; wheel built from a clean tree and installed in a fresh venv.
- [x] `README.md`, `CONTRACT.md`, `ACCEPTANCE.md` included.

Signed: A admin-76b526 · B admin-726762 · C admin-3c5fde · D admin-a74b45
