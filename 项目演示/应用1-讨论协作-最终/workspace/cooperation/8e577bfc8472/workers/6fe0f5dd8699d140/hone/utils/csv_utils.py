"""CSV reading utilities for the :mod:`hone` package.

Only the Python standard library is used.  Parsing deliberately relies on the
default :class:`csv.reader` dialect:

* ``delimiter=','``
* ``quotechar='"'``
* ``doublequote=True``
* ``skipinitialspace=False``

Files are opened with ``encoding='utf-8'`` and ``newline=''``.  No further
unescaping, stripping or replacing of the parsed values is performed: the
values returned by :class:`csv.reader` are the values that end up in JSON.
"""

import csv
import sys
from contextlib import contextmanager


def _is_blank_row(row):
    """Return ``True`` for a row that carries no data at all.

    A blank line is returned by :class:`csv.reader` as an empty list; a line
    such as ``","`` produces a list of empty strings.  Both are considered
    blank and are skipped by :meth:`CSVUtils.get_data_rows`.
    """

    if not row:
        return True
    return all(cell == "" for cell in row)


class CSVUtils:
    """Lazy reader for a CSV file (or standard input when ``'-'``).

    All records are read at most once and cached on the instance.  This is
    important for standard input: after the first read the input stream is
    exhausted, so later calls must reuse the cache.
    """

    def __init__(self, csv_filepath):
        self.filepath = csv_filepath
        self._rows = None

    # ------------------------------------------------------------------
    # File handling
    # ------------------------------------------------------------------
    @contextmanager
    def open_csv(self, mode="r", newline=None):
        """Yield a text stream for the configured CSV path.

        ``'-'`` maps to standard input in read mode and to standard output in
        write mode.  Regular files are always opened as UTF-8.
        """

        reading = "r" in mode
        if self.filepath == "-":
            yield sys.stdin if reading else sys.stdout
            return

        with open(
            self.filepath, mode, encoding="utf-8", newline=newline
        ) as csv_file:
            yield csv_file

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _load_rows(self):
        if self._rows is None:
            with self.open_csv("r", newline="") as csv_file:
                self._rows = list(csv.reader(csv_file))
        return self._rows

    def get_all_rows(self):
        """Return every record in the CSV, including the header row."""

        return list(self._load_rows())

    def get_column_names(self):
        """Return the first record, i.e. the column names."""

        rows = self._load_rows()
        return list(rows[0]) if rows else []

    def get_data_rows(self):
        """Return all records after the header, skipping blank rows."""

        rows = self._load_rows()
        if not rows:
            return []
        return [list(row) for row in rows[1:] if not _is_blank_row(row)]


def parse_csv_file(csv_filepath):
    """Return every row of ``csv_filepath`` as a list of lists.

    ``'-'`` reads from standard input.
    """

    return CSVUtils(csv_filepath).get_all_rows()
