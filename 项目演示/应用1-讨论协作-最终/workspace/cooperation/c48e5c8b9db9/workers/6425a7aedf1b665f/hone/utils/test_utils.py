from __future__ import annotations

from .csv_utils import CSVUtils
from .csv_utils import parse_csv_file
from .json_utils import output_json
from .json_utils import parse_json_file


def normalize(obj):
    """Return a plain JSON-compatible copy of *obj* for structural comparison."""
    if isinstance(obj, dict):
        return {key: normalize(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [normalize(value) for value in obj]
    return obj


def assert_json_equal(tc, actual, expected):
    """Assert two JSON-like structures are structurally equal."""
    tc.assertEqual(normalize(actual), normalize(expected))


__all__ = [
    "CSVUtils",
    "parse_csv_file",
    "output_json",
    "parse_json_file",
    "normalize",
    "assert_json_equal",
]
