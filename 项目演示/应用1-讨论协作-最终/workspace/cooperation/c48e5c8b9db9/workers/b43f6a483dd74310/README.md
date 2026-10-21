# hone

Convert CSV to automatically nested JSON.

`hone` reads a flat CSV file, infers a nested structure from column names
(`birth day` / `birth month` / `birth year` → `{"birth": {"day": ..., "month": ...}}`),
and writes indented, key-sorted JSON. A schema can also be supplied manually.
The core uses only the Python standard library.

## Table of Contents

- [Installation](#installation)
- [Usage: Command Line](#usage-command-line)
  - [Write JSON to a file](#1-write-json-to-a-file)
  - [Write JSON to standard output](#2-write-json-to-standard-output)
- [Usage: Python Module](#usage-python-module)
- [Custom delimiters and schemas (`-d` / `-s`)](#custom-delimiters-and-schemas--d--s)
- [Output format](#output-format)
- [Running tests](#running-tests)
- [Known limitations](#known-limitations)
- [License](#license)

## Installation

From a checkout:

```console
pip install .
```

From a built wheel:

```console
pip install dist/hone-1.0.0-py3-none-any.whl
```

No third-party runtime dependencies are required (Python >= 3.8).

## Usage: Command Line

```console
$ hone --help
usage: hone [-h] [-d [DELIMITERS]] [-s [SCHEMA]] csv_filepath json_filepath

positional arguments:
  csv_filepath          Path to the input CSV file. Use "-" to read standard
                        input.
  json_filepath         Path to the output JSON file. Use "-" to write standard
                        output.

options:
  -h, --help            show this help message and exit
  -d [DELIMITERS], --delimiters [DELIMITERS]
                        Override the default delimiters used to infer nesting
                        from column names. Must be a Python-compatible list of
                        strings. Default: [',', '_', ' '].
  -s [SCHEMA], --schema [SCHEMA]
                        Manually specify the JSON schema as a JSON object
                        encoded in a string, instead of inferring it.
```

### 1. Write JSON to a file

```console
python -m hone examples/example_a.csv out.json
```

This writes a JSON array (one object per data row) to `out.json`.

### 2. Write JSON to standard output

Use `-` as the output path:

```console
python -m hone examples/example_a.csv -
```

Read from standard input and write to standard output:

```console
cat examples/example_a.csv | python -m hone - -
```

or, on PowerShell:

```powershell
Get-Content examples/example_a.csv | python -m hone - -
```

Read from standard input and write to a file:

```console
python -m hone - out.json < examples/example_a.csv
```

The exit code is `0` on success, `2` for argument errors, and `1` for runtime
errors (for example a missing input file).

## Usage: Python Module

```python
import hone

Hone = hone.Hone()
result = Hone.convert("examples/example_a.csv")
print(result)

schema = Hone.get_schema("examples/example_a.csv")
result = Hone.convert("examples/example_a.csv", schema=schema)
```

Custom delimiters are passed to the constructor and **completely replace** the
defaults (`[",", "_", " "]`):

```python
import hone

Hone = hone.Hone(delimiters=["::"])
result = Hone.convert("my_file.csv")
```

## Custom delimiters and schemas (`-d` / `-s`)

Both options use `nargs="?"`, so **when you provide a value it must be written
as one complete quoted argument**, otherwise the following positional argument
is swallowed as the option value and `argparse` exits with code 2:

```console
# Correct: whole value quoted
python -m hone -d "['_', ' ', ',']" examples/example_a.csv -
python -m hone -s '{"birth": {"year": "birth year"}, "name": "name"}' examples/example_a.csv -
```

Do **not** write `-d in.csv out.json` expecting the default delimiters: the
value after `-d` will be consumed as the delimiter list. If you only want the
defaults, simply omit `-d` and `-s`.

`-d` values are parsed with `ast.literal_eval` first and `json.loads` second;
the result must be a non-empty list of strings. `-s` values are parsed with
`json.loads` only (a JSON object encoded as a string); a file path is not
accepted.

## Output format

- A JSON array with one object per CSV data row, in CSV row order.
- Keys are sorted (`sort_keys=True`) and indented with two spaces
  (`indent=2`).
- The file/stdout always ends with exactly one newline.
- Every leaf value is a string; no type inference is performed.

## Running tests

From the repository root:

```console
python -m unittest discover -s tests -t . -v
```

Or simply:

```console
python -m unittest
```

One-click acceptance (G1–G13, including wheel build and a clean virtualenv
install):

```console
python scripts/acceptance.py
```

The committed sample data lives in `tests/fixtures/data_file/**` and
`examples/*.csv`. Set `HONE_TASK_DIR` to point at the original read-only task
material directory to run the same suite against the originals.

## Known limitations

- Nested keys are inferred from column-name delimiters. When two different
  column names collapse to the same nested path at the same level, the later
  column wins.
- Values are always strings; `TRUE`/`FALSE`/numbers are not converted to native
  JSON booleans/numbers.
- `examples/README.md` contains an upstream typo: it shows `b.d.f` as `"1"` for
  the second row of `example_b.csv`. The real CSV value is `"12"`; the converter
  (and the tests) correctly produce `"12"`. The sample files are kept unchanged.

## License

MIT. See [LICENSE](LICENSE).
