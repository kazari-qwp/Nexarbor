"""Core CSV-to-nested-JSON conversion logic for the ``hone`` package.

The :class:`Hone` class turns a flat CSV file into a list of nested
dictionaries.  Nesting is inferred from the column names by repeatedly
splitting each remaining column name at the *left-most legal* delimiter.

A split of ``column_name`` at delimiter ``d`` is legal when:

* ``head`` (the part before ``d``) and ``tail`` (the part after ``d``) are
  both non-empty;
* ``head`` is not itself one of the remaining column names at the current
  recursion level (otherwise ``a`` / ``a_b`` would wrongly nest);
* at least two remaining column names share the prefix ``head + d`` (so a
  single column is never over-split).

Among all legal candidates the one with the smallest ``column_name.find(d)``
wins; ties are broken by the order of ``delimiters``.
"""

import json

__all__ = ["Hone"]


class Hone:
    """Convert CSV data into automatically nested JSON structures."""

    DEFAULT_DELIMITERS = [",", "_", " "]

    def __init__(self, delimiters=None):
        if delimiters is None:
            delimiters = list(self.DEFAULT_DELIMITERS)
        else:
            if isinstance(delimiters, str):
                raise TypeError("delimiters must be a list of strings, not a string")
            delimiters = list(delimiters)
            if not delimiters:
                raise ValueError("delimiters must not be empty")
            for delimiter in delimiters:
                if not isinstance(delimiter, str) or not delimiter:
                    raise ValueError("each delimiter must be a non-empty string")
        self.delimiters = delimiters
        self.csv_filepath = None
        self.csv = None

    # ------------------------------------------------------------------
    # CSV plumbing
    # ------------------------------------------------------------------
    def set_csv_filepath(self, csv_filepath):
        """Point this instance at ``csv_filepath`` and return a ``CSVUtils``.

        The ``CSVUtils`` instance is created once per filepath and reused, so
        standard input (``'-'``) is only consumed a single time even when
        :meth:`get_schema` and :meth:`convert` are called one after another.
        """
        if self.csv is None or self.csv_filepath != csv_filepath:
            from hone.utils.csv_utils import CSVUtils

            self.csv = CSVUtils(csv_filepath)
            self.csv_filepath = csv_filepath
        return self.csv

    # ------------------------------------------------------------------
    # Public conversion API
    # ------------------------------------------------------------------
    def get_schema(self, csv_filepath):
        """Return the automatically generated nested schema for a CSV file."""
        csv_utils = self.set_csv_filepath(csv_filepath)
        column_names = csv_utils.get_column_names()
        return self.generate_full_structure(column_names)

    def convert(self, csv_filepath, schema=None):
        """Convert ``csv_filepath`` to a list of nested dictionaries.

        ``schema`` may be ``None`` (infer the structure), a ``dict`` or a
        JSON object encoded as a string.
        """
        csv_utils = self.set_csv_filepath(csv_filepath)
        column_names = csv_utils.get_column_names()
        data_rows = csv_utils.get_data_rows()
        if schema is None:
            structure = self.generate_full_structure(column_names)
        else:
            structure = self._normalise_schema(schema)
        return self.populate_structure_with_data(structure, column_names, data_rows)

    def generate_full_structure(self, column_names):
        """Build the complete (schema-like) nested structure for column names."""
        flat_structure = {}
        for column_name in column_names:
            flat_structure[column_name] = column_name
        return self.get_nested_structure(flat_structure)

    def populate_structure_with_data(self, structure, column_names, data_rows):
        """Fill ``structure`` with the values of ``data_rows``."""
        if not isinstance(structure, dict):
            raise TypeError("structure must be a dict")
        column_indexes = {}
        for index, column_name in enumerate(column_names):
            column_indexes.setdefault(column_name, index)
        result = []
        for row in data_rows:
            result.append(self._populate_one_row(structure, row, column_indexes))
        return result

    def _populate_one_row(self, structure, row, column_indexes):
        populated = {}
        for key, value in structure.items():
            if isinstance(value, dict):
                populated[key] = self._populate_one_row(value, row, column_indexes)
            else:
                index = column_indexes.get(value)
                if index is None or index >= len(row):
                    populated[key] = ""
                else:
                    populated[key] = row[index]
        return populated

    @staticmethod
    def _normalise_schema(schema):
        if isinstance(schema, str):
            schema = json.loads(schema)
        if not isinstance(schema, dict):
            raise TypeError(
                "schema must be a dict, a JSON object encoded as a string, or None"
            )
        return schema

    # ------------------------------------------------------------------
    # Nesting helpers
    # ------------------------------------------------------------------
    def get_nested_structure(self, parent_structure):
        """Return ``parent_structure`` with one nesting level applied.

        ``parent_structure`` maps the column names *as seen at the current
        recursion level* to the original column names (the leaf payload).
        Every group found at this level is recursively nested.
        """
        if not isinstance(parent_structure, dict):
            raise TypeError("parent_structure must be a dict")
        remaining = list(parent_structure.keys())
        remaining_set = set(remaining)

        nested = {}
        chosen_splits = {}
        for name in remaining:
            split = self._choose_split(name, remaining_set)
            if split is None:
                nested[name] = parent_structure[name]
            else:
                chosen_splits[name] = split

        grouped_heads = []
        head_delimiters = {}
        for name in remaining:
            split = chosen_splits.get(name)
            if split is None:
                continue
            _, delimiter, head, _ = split
            if head not in grouped_heads:
                grouped_heads.append(head)
                head_delimiters[head] = delimiter

        for head in grouped_heads:
            delimiter = head_delimiters[head]
            prefix = head + delimiter
            child_structure = {}
            for name in remaining:
                if name in chosen_splits and chosen_splits[name][2] != head:
                    continue
                if name.startswith(prefix) and len(name) > len(prefix):
                    child_structure[name[len(prefix):]] = parent_structure[name]
            nested[head] = self.get_nested_structure(child_structure)

        return nested

    def _choose_split(self, column_name, remaining_set):
        """Return ``(idx, delimiter, head, tail)`` for the best legal split."""
        for index, delimiter in self.get_valid_splits(column_name):
            head = column_name[:index]
            tail = column_name[index + len(delimiter):]
            if head in remaining_set:
                continue
            prefix = head + delimiter
            matching = 0
            for other in remaining_set:
                if len(other) > len(prefix) and other.startswith(prefix):
                    matching += 1
            if matching >= 2:
                return index, delimiter, head, tail
        return None

    def get_valid_splits(self, column_name):
        """Return every syntactically possible ``(idx, delimiter)`` split.

        Candidates are ordered by position and then by the configured
        delimiter order; both parts must be non-empty.
        """
        splits = []
        if not isinstance(column_name, str):
            return splits
        for order, delimiter in enumerate(self.delimiters):
            index = column_name.find(delimiter)
            if index <= 0:
                continue
            if index + len(delimiter) >= len(column_name):
                continue
            splits.append((index, order, delimiter))
        splits.sort()
        return [(index, delimiter) for index, _, delimiter in splits]

    def get_split_suffix(self, split, column_name):
        """Return the part of ``column_name`` after ``split``."""
        if isinstance(split, tuple):
            for part in split:
                if isinstance(part, str) and part and part in column_name:
                    index = column_name.find(part)
                    if index != -1:
                        return column_name[index + len(part):]
            return ""
        if isinstance(split, list):
            return self.get_split_suffix(tuple(split), column_name)
        delimiter = str(split)
        index = column_name.find(delimiter)
        if index == -1:
            return ""
        return column_name[index + len(delimiter):]

    def clean_split(self, split):
        """Drop empty fragments from a split result (compatibility helper)."""
        if isinstance(split, (list, tuple)):
            return [part for part in split if part]
        return split

    def is_valid_prefix(self, prefix, base):
        """Return ``True`` when ``base`` starts with the non-empty ``prefix``."""
        if not prefix or not base:
            return False
        return base.startswith(prefix)

    def get_leaves(self, structure, path=None, result=None):
        """Collect ``(path_list, leaf_value)`` pairs from a nested structure."""
        if path is None:
            path = []
        if result is None:
            result = []
        for key, value in structure.items():
            current_path = path + [key]
            if isinstance(value, dict):
                self.get_leaves(value, current_path, result)
            else:
                result.append((current_path, value))
        return result

    def escape_quotes(self, string):
        """Retained for API compatibility only; the parser never calls this."""
        return string
