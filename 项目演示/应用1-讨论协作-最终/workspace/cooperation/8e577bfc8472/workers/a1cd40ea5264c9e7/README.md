# hone

Convert CSV to automatically nested JSON.

`hone` reads a flat CSV file and produces a JSON list of objects. Column names
are split on configurable delimiters (by default `,`, `_` and a space) so that
names such as `birth day`, `birth month` and `birth year` become a single
`birth` object. A schema can also be supplied explicitly.

Only the Python standard library is used. Python 3.8 or newer is required.

## Installation

From the repository root:

```shell
pip install .
```

For an offline/local build you can also produce a wheel and install it:

```shell
python -m pip wheel . --no-build-isolation -w dist
pip install dist/hone-*.whl
```

## Usage: Command line

```shell
hone [-h] [-d [DELIMITERS]] [-s [SCHEMA]] csv_filepath json_filepath
```

* `csv_filepath` – input CSV file; use `-` to read from standard input.
* `json_filepath` – output JSON file; use `-` to write to standard output.
* `-d`, `--delimiters` – Python-compatible list of string delimiters, e.g.
  `"['_', ' ']"`. Defaults to `[',', '_', ' ']`.
* `-s`, `--schema` – a JSON object encoded as a string describing the desired
  output structure.

### File output

```shell
python -m hone examples/example_c.csv output.json
```

or, after installation:

```shell
hone examples/example_c.csv output.json
```

The output is written with `indent=2` and sorted keys:

```json
[
  {
    "birth": {
      "day": "7",
      "month": "May",
      "year": "1985"
    },
    "name": "Bob",
    "reference": "TRUE",
    "reference name": "Smith"
  }
]
```

### Standard output and standard input

Write JSON to standard output with `-`:

```shell
python -m hone examples/example_a.csv -
```

Read CSV from standard input and write JSON to standard output:

```shell
python -m hone - - < examples/example_b.csv
```

Piping to another program works as expected:

```shell
cat examples/example_c.csv | python -m hone - - | python -m json.tool
```

## Usage: Python module

```python
import hone

# Optional: override the delimiters used to detect nesting.
Hone = hone.Hone(delimiters=[" ", "_", ","])

# Automatically generated nested JSON schema for a CSV file.
schema = Hone.get_schema("path/to/input.csv")

# Final nested structure, generated from that schema.
result = Hone.convert("path/to/input.csv", schema=schema)

# A schema may also be a dict or a JSON string.
result = hone.Hone().convert("path/to/input.csv", schema=schema)
```

`Hone.convert(csv_filepath, schema=None)` accepts `None` (generate the schema
automatically), a `dict`, or a JSON string. `Hone.get_schema()` returns the
automatically generated structure as a `dict`.

Lower level helpers are available as well:

```python
from hone.utils.csv_utils import CSVUtils
from hone.utils.json_utils import output_json

csv = CSVUtils("path/to/input.csv")   # "-" reads standard input
column_names = csv.get_column_names()
data_rows = csv.get_data_rows()
all_rows = csv.get_all_rows()

output_json(result, "output.json")     # "-" writes standard output
```

## Examples

The `examples/` directory contains `example_a.csv`, `example_b.csv`,
`example_c.csv`, their expected JSON in `examples/README.md`, and a runnable
demo:

```shell
pip install .          # or: PYTHONPATH=. python examples/demo.py
python examples/demo.py
```

`demo.py` imports the package by name, so either install the package first
(`pip install .`) or run it with the repository root on `PYTHONPATH`, e.g.
`PYTHONPATH=. python examples/demo.py` (Windows PowerShell:
`$env:PYTHONPATH="."; python examples/demo.py`).

`example_b.csv` demonstrates the "leftmost valid split" rule: `b_c_d` becomes
`b.c.d` rather than `b_c.d`, while `a` and `a_b` stay top-level keys. The
second row's `b.d.f` value is `"12"`; the expected output in
`examples/README.md` shows `"1"`, which is a typo in the documentation – the
CSV input is authoritative.

## Development

Run the complete test suite from the repository root:

```shell
python -m unittest discover -s tests -t . -v
```

or simply:

```shell
python -m unittest
```

Build the wheel:

```shell
python -m pip wheel . --no-build-isolation -w dist
```

## Behavior and limitations

* CSV parsing uses the default `csv.reader` dialect: delimiter `,`, quote
  character `"`, double-quote escaping, no space skipping. Files are opened as
  UTF-8 with `newline=""`. Values are never unescaped, stripped or replaced a
  second time, so quoted values are preserved exactly as parsed.
* Automatic nesting chooses the leftmost valid split at every level. A split
  is valid when both parts are non-empty, the head is not itself one of the
  remaining column names, and at least two remaining column names share the
  `head + delimiter` prefix. All prefix groups are processed recursively.
* All values in the output JSON are strings; no type inference is performed.
* Blank lines between records are ignored. A header-only CSV produces an empty
  list.
* `-` means standard input for CSV paths and standard output for JSON paths.
  Standard input is read only once and cached.
* JSON output uses `indent=2`, sorted keys, UTF-8 (no ASCII escaping) and a
  trailing newline.
* Command line argument errors exit with status 2; runtime errors are printed
  to stderr as a single `hone: error: ...` line and exit with status 1.
* `python examples/demo.py` runs from the repository root only after
  `pip install .`, or with the repository root on `PYTHONPATH`
  (`PYTHONPATH=. python examples/demo.py`); the demo script itself is a
  read-only public sample and is not modified.

## License

`hone` is licensed under the MIT license. See `LICENSE`.
