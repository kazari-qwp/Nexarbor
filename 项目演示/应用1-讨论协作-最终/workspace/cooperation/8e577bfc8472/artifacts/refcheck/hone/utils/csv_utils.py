"""CSV helpers (reference implementation for harness self-check only)."""

import csv
import sys
from contextlib import contextmanager


class CSVUtils(object):
    def __init__(self, csv_filepath):
        self.filepath = csv_filepath
        self._records = None

    @contextmanager
    def open_csv(self, mode="r", newline=""):
        if self.filepath == "-":
            yield sys.stdin
        else:
            handle = open(self.filepath, mode, encoding="utf-8", newline=newline)
            try:
                yield handle
            finally:
                handle.close()

    def _load(self):
        if self._records is None:
            with self.open_csv() as handle:
                self._records = list(csv.reader(handle))
        return self._records

    def get_all_rows(self):
        return list(self._load())

    def get_column_names(self):
        records = self._load()
        return list(records[0]) if records else []

    def get_data_rows(self):
        return [row for row in self._load()[1:] if row]
