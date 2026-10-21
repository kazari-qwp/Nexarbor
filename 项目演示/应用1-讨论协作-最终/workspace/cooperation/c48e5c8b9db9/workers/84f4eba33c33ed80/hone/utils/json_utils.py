from __future__ import annotations

import json
import sys


def output_json(json_struct, json_filepath):
    """Write *json_struct* as indent=2, sorted-key JSON plus a trailing newline.

    ``json_filepath == "-"`` writes to standard output; standard output is not
    closed.  Files are written as UTF-8 with ``newline="\\n"``.
    """
    text = json.dumps(json_struct, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if json_filepath == "-":
        sys.stdout.write(text)
        return
    with open(json_filepath, "w", encoding="utf-8", newline="\n") as json_file:
        json_file.write(text)


def parse_json_file(json_filepath):
    """Parse a JSON file, or standard input when *json_filepath* is ``"-"``."""
    if json_filepath == "-":
        return json.load(sys.stdin)
    with open(json_filepath, "r", encoding="utf-8") as json_file:
        return json.load(json_file)
