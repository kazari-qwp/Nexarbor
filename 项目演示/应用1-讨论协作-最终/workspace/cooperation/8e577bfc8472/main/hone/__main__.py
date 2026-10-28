"""Command line interface for the :mod:`hone` package.

``python -m hone`` and the installed ``hone`` console script both call
:func:`main`.  Argument parsing errors are reported by :mod:`argparse`
(exit code 2), while runtime failures are reported on a single stderr line
prefixed with ``hone: error:`` (exit code 1).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from typing import Any, List, Optional

from hone.hone import Hone
from hone.utils.json_utils import output_json


def _parse_delimiters(value: str) -> List[str]:
    """Parse the ``--delimiters`` value into a non-empty list of strings.

    A Python literal is preferred (as documented), with JSON as a fallback.
    """

    parsed: Any
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            raise argparse.ArgumentTypeError(
                "delimiters must be a non-empty Python/JSON list of strings"
            )
    if (
        not isinstance(parsed, list)
        or not parsed
        or not all(isinstance(item, str) for item in parsed)
    ):
        raise argparse.ArgumentTypeError(
            "delimiters must be a non-empty Python/JSON list of strings"
        )
    return parsed


def _parse_schema(value: str) -> dict:
    """Parse the ``--schema`` value into a JSON object."""

    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("schema must be a valid JSON object")
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("schema must be a valid JSON object")
    return parsed


def build_parser() -> argparse.ArgumentParser:
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
        default=None,
        type=_parse_delimiters,
        metavar="DELIMITERS",
        help=(
            "Override the default delimiters for generating a nested "
            "structure from column names. [DELIMITERS] must be a "
            "Python-compatible list of strings. The default value is "
            "[',', '_', ' ']."
        ),
    )
    parser.add_argument(
        "-s",
        "--schema",
        nargs="?",
        default=None,
        type=_parse_schema,
        metavar="SCHEMA",
        help=(
            "Manually specify the schema that defines the structure of the "
            "generated JSON, instead of having it automatically generated. "
            "[SCHEMA] must be a valid JSON object encoded as a string."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Run the ``hone`` command line interface.

    Returns the process exit code (``0`` on success, ``1`` on a runtime
    error).  Argument errors are handled by :mod:`argparse` and exit with
    code ``2``.
    """

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        hone = Hone(delimiters=args.delimiters)
        structure = hone.convert(args.csv_filepath, schema=args.schema)
        output_json(structure, args.json_filepath)
    except Exception as exc:  # noqa: BLE001 - CLI boundary, no traceback wanted.
        print("hone: error: {}".format(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via ``-m hone``.
    sys.exit(main())
