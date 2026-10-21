from __future__ import annotations

import argparse
import ast
import json
import sys

from .hone import Hone
from .utils import output_json


def build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser for ``python -m hone`` / ``hone``."""
    parser = argparse.ArgumentParser(
        prog="hone",
        description="Convert CSV to automatically nested JSON.",
    )
    parser.add_argument(
        "csv_filepath",
        help=(
            "Specify the filepath for the file to read CSV data from. "
            'To read from standard input, use a dash ("-") as the value'
        ),
    )
    parser.add_argument(
        "json_filepath",
        help=(
            "Specify the filepath for the file to output JSON data to. "
            'To write to standard output, use a dash ("-") as the value.'
        ),
    )
    parser.add_argument(
        "-d",
        "--delimiters",
        nargs="?",
        const=None,
        default=None,
        help=(
            "Override the default delimiters for generating a nested structure "
            "from column names. [DELIMITERS] must be a Python-compatible list "
            'of strings. The default value is [",", "_", " "].'
        ),
    )
    parser.add_argument(
        "-s",
        "--schema",
        nargs="?",
        const=None,
        default=None,
        help=(
            "Manually specify the schema that defines the structure of the "
            "generated JSON, instead of having it automatically generated. "
            "[SCHEMA] must be a valid JSON object encoded as a string."
        ),
    )
    return parser


def parse_delimiters(parser: argparse.ArgumentParser, raw: str):
    """Parse the ``-d`` value: ``ast.literal_eval`` first, ``json.loads`` second."""
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            parser.error(
                "argument -d/--delimiters: invalid value {!r}; expected a "
                "Python-compatible list of strings".format(raw)
            )
            raise SystemExit(2)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) for item in value)
    ):
        parser.error(
            "argument -d/--delimiters: value must be a non-empty list of strings"
        )
    return value


def parse_schema(parser: argparse.ArgumentParser, raw: str):
    """Parse the ``-s`` value: it must be a JSON object encoded as a string."""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        parser.error(
            "argument -s/--schema: invalid JSON object encoded as a string"
        )
        raise SystemExit(2)
    if not isinstance(value, dict):
        parser.error("argument -s/--schema: value must be a JSON object")
    return value


def main(argv=None) -> int:
    """Run the hone command line interface and return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    delimiters = None
    if args.delimiters is not None:
        delimiters = parse_delimiters(parser, args.delimiters)

    schema = None
    if args.schema is not None:
        schema = parse_schema(parser, args.schema)

    try:
        hone = Hone(delimiters)
        json_struct = hone.convert(args.csv_filepath, schema=schema)
        output_json(json_struct, args.json_filepath)
    except (OSError, ValueError) as exc:
        sys.stderr.write("hone: error: {}\n".format(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
