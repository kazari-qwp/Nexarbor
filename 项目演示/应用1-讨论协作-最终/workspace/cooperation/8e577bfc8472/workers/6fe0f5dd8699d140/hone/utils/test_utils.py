"""Helpers shared by the test suite and by the bundled examples.

These functions are intentionally dependency free so they can also be used
from ``python -m unittest`` and from ad-hoc scripts.
"""

import csv
import json


class TestUtils:
    """Small collection of file parsing helpers for tests."""

    @staticmethod
    def parse_json_file(json_filepath):
        with open(json_filepath, "r", encoding="utf-8") as json_file:
            return json.load(json_file)

    @staticmethod
    def parse_csv_file(csv_filepath):
        with open(csv_filepath, "r", encoding="utf-8", newline="") as csv_file:
            return list(csv.reader(csv_file))

    @staticmethod
    def json_files_equal(first_filepath, second_filepath):
        return TestUtils.parse_json_file(first_filepath) == TestUtils.parse_json_file(
            second_filepath
        )


def parse_json_file(json_filepath):
    return TestUtils.parse_json_file(json_filepath)


def parse_csv_file(csv_filepath):
    return TestUtils.parse_csv_file(csv_filepath)
