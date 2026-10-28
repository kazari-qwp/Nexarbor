"""JSON helpers (reference implementation for harness self-check only)."""

import json
import sys


def output_json(json_struct, json_filepath):
    if json_filepath == "-":
        json.dump(json_struct, sys.stdout, indent=2, sort_keys=True, ensure_ascii=False)
        sys.stdout.write("\n")
        return
    with open(json_filepath, "w", encoding="utf-8", newline="") as handle:
        json.dump(json_struct, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


def parse_json_file(json_filepath):
    if json_filepath == "-":
        return json.load(sys.stdin)
    with open(json_filepath, encoding="utf-8") as handle:
        return json.load(handle)


def parse_csv_file(csv_filepath):
    from hone.utils.csv_utils import CSVUtils

    return CSVUtils(csv_filepath).get_all_rows()
