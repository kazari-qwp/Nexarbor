"""JSON input/output helpers for the :mod:`hone` package."""

import json
import sys


def output_json(json_struct, json_filepath):
    """Write ``json_struct`` to ``json_filepath``.

    Output is formatted with ``indent=2``, ``sort_keys=True`` and
    ``ensure_ascii=False`` and always ends with a trailing newline.  When
    ``json_filepath`` is ``'-'`` the JSON is written to standard output.
    """

    if json_filepath == "-":
        json.dump(
            json_struct,
            sys.stdout,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        sys.stdout.write("\n")
        return

    with open(json_filepath, "w", encoding="utf-8", newline="") as json_file:
        json.dump(
            json_struct,
            json_file,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        json_file.write("\n")


def parse_json_file(json_filepath):
    """Load and return the JSON document stored in ``json_filepath``.

    ``'-'`` reads from standard input.
    """

    if json_filepath == "-":
        return json.load(sys.stdin)
    with open(json_filepath, "r", encoding="utf-8") as json_file:
        return json.load(json_file)
