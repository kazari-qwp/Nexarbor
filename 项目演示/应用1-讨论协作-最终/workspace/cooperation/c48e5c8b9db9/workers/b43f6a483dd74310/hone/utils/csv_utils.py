from __future__ import annotations

import contextlib
import csv
import sys


def parse_csv_file(csv_filepath):
    """Return ``(column_names, data_rows)`` reading the CSV file exactly once."""
    csv_utils = CSVUtils(csv_filepath)
    return csv_utils.get_column_names(), csv_utils.get_data_rows()


class CSVUtils:
    """Read CSV column names and data rows lazily, loading the file once.

    The special filepath ``"-"`` reads from standard input.  ``_load`` consumes
    the stream a single time and caches both column names and data rows, so
    repeated calls never re-read stdin.
    """

    def __init__(self, csv_filepath):
        self.filepath = csv_filepath
        self._column_names = None
        self._data_rows = None
        self._loaded = False

    @contextlib.contextmanager
    def open_csv(self, mode="r", newline=""):
        """Yield an open CSV stream; standard input is never closed."""
        if self.filepath == "-":
            yield sys.stdin
            return
        with open(
            self.filepath, mode, newline=newline, encoding="utf-8-sig"
        ) as csv_file:
            yield csv_file

    def _load(self):
        if self._loaded:
            return
        with self.open_csv("r", newline="") as csv_file:
            rows = list(csv.reader(csv_file))
        self._column_names = rows[0] if rows else []
        self._data_rows = [row for row in rows[1:] if row != []]
        self._loaded = True

    def get_column_names(self):
        """Return a fresh copy of the header row (first physical line)."""
        self._load()
        return list(self._column_names)

    def get_data_rows(self):
        """Return fresh copies of the data rows (header excluded, no blanks)."""
        self._load()
        return [list(row) for row in self._data_rows]
