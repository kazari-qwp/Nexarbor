"""Hone core (reference implementation for harness self-check only)."""

import json

from hone.utils.csv_utils import CSVUtils


class Hone(object):
    DEFAULT_DELIMITERS = [",", "_", " "]

    def __init__(self, delimiters=None):
        if delimiters is None:
            delimiters = list(self.DEFAULT_DELIMITERS)
        self.delimiters = list(delimiters)
        self.csv_filepath = None
        self.csv = None

    # -- plumbing ---------------------------------------------------------
    def set_csv_filepath(self, csv_filepath):
        if self.csv_filepath != csv_filepath or self.csv is None:
            self.csv_filepath = csv_filepath
            self.csv = CSVUtils(csv_filepath)
        return self.csv

    def escape_quotes(self, string):
        return string.replace('"', '""') if isinstance(string, str) else string

    # -- compatibility helpers -------------------------------------------
    def is_valid_prefix(self, prefix, base):
        return bool(prefix) and isinstance(base, str) and base.startswith(prefix)

    def clean_split(self, split):
        return split

    def get_split_suffix(self, split, column_name):
        return column_name[len(split):] if column_name.startswith(split) else column_name

    def get_valid_splits(self, column_name):
        splits = []
        for delimiter in self.delimiters:
            start = 0
            while True:
                index = column_name.find(delimiter, start)
                if index < 0:
                    break
                head = column_name[:index]
                tail = column_name[index + len(delimiter):]
                if head and tail:
                    splits.append((head, tail, delimiter, index))
                start = index + 1
        return splits

    def get_leaves(self, structure, path=None, result=None):
        if path is None:
            path = []
        if result is None:
            result = {}
        for key, value in structure.items():
            if isinstance(value, dict):
                self.get_leaves(value, path + [key], result)
            else:
                result[".".join(path + [key])] = value
        return result

    def get_nested_structure(self, parent_structure):
        if isinstance(parent_structure, dict):
            names = list(parent_structure.keys())
        else:
            names = list(parent_structure)
        return self.generate_full_structure(names)

    # -- schema generation ------------------------------------------------
    def _split_for(self, column_name, remaining):
        best = None
        for order, delimiter in enumerate(self.delimiters):
            index = column_name.find(delimiter)
            while index >= 0:
                head = column_name[:index]
                tail = column_name[index + len(delimiter):]
                if head and tail and head not in remaining:
                    prefix = head + delimiter
                    count = sum(1 for item in remaining if item.startswith(prefix))
                    if count >= 2:
                        candidate = (index, order, head, delimiter)
                        if best is None or candidate[:2] < best[:2]:
                            best = candidate
                index = column_name.find(delimiter, index + 1)
        return best

    def generate_full_structure(self, column_names):
        items = [(name, name) for name in column_names]
        return self._build_structure(items)

    def _build_structure(self, items):
        remaining = [relative for relative, _ in items]
        structure = {}
        groups = {}
        for relative, original in items:
            split = self._split_for(relative, remaining)
            if split is None:
                structure[relative] = original
            else:
                _, _, head, delimiter = split
                groups.setdefault(head, []).append(
                    (relative[len(head) + len(delimiter):], original)
                )
        for head, members in groups.items():
            structure[head] = self._build_structure(members)
        return structure

    # -- population -------------------------------------------------------
    def _populate(self, structure, column_names, row):
        result = {}
        for key, value in structure.items():
            if isinstance(value, dict):
                result[key] = self._populate(value, column_names, row)
            else:
                index = column_names.index(value)
                result[key] = row[index] if index < len(row) else ""
        return result

    def populate_structure_with_data(self, structure, column_names, data_rows):
        return [self._populate(structure, column_names, row) for row in data_rows]

    # -- public API -------------------------------------------------------
    def get_schema(self, csv_filepath):
        csv = self.set_csv_filepath(csv_filepath)
        return self.generate_full_structure(csv.get_column_names())

    def convert(self, csv_filepath, schema=None):
        csv = self.set_csv_filepath(csv_filepath)
        column_names = csv.get_column_names()
        data_rows = csv.get_data_rows()
        if schema is None:
            structure = self.generate_full_structure(column_names)
        elif isinstance(schema, str):
            structure = json.loads(schema)
        else:
            structure = schema
        return self.populate_structure_with_data(structure, column_names, data_rows)
