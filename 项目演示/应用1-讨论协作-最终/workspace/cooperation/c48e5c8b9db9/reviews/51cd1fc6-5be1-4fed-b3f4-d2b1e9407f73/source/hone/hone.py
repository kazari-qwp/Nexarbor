"""Core CSV -> nested JSON conversion (package A).

Contract: CONTRACT.md (FINAL plan sections 2/3). Public signatures are frozen.

Design notes (plan sections 3.1-3.8):
* Leaves store the *full original column name*; ``get_schema`` is a deep copy
  of ``generate_full_structure`` and feeds back into ``populate_structure_with_data``.
* Nesting decisions use only the *relative names of the current level*, never a
  global header table (see ``_choose``); this keeps ``a_b``/``adopted_since``/
  ``reference name`` as whole-name leaves.
* ``comma_test`` audit: ``csv.reader`` parses 2 columns ``"test","ing"`` and
  a leading-space then quoted beep field.  The first has an internal comma
  producing prefix ``"test"``,
  but no other same-level column starts with ``"test",`` so it is not shared and
  stays a leaf; the second only has a leading space producing an empty prefix,
  which is discarded.  No quote special-casing is needed.
"""

from __future__ import annotations

import copy


class Hone:
    """Convert flat CSV data into automatically nested JSON structures."""

    DEFAULT_DELIMITERS = [",", "_", " "]

    def __init__(self, delimiters=None):
        """Create a Hone instance.

        ``delimiters`` is ``None`` (copy of :attr:`DEFAULT_DELIMITERS`) or a
        non-empty list of non-empty strings; anything else raises ValueError.
        Initialises ``self.delimiters``, ``self.csv_filepath=None``,
        ``self.csv=None`` and ``self.column_names=[]``.
        """
        if delimiters is None:
            self.delimiters = list(self.DEFAULT_DELIMITERS)
        else:
            if not isinstance(delimiters, list) or not delimiters:
                raise ValueError("delimiters must be a non-empty list of strings")
            for delimiter in delimiters:
                if not isinstance(delimiter, str) or delimiter == "":
                    raise ValueError("delimiters must be a non-empty list of strings")
            self.delimiters = list(delimiters)
        self.csv_filepath = None
        self.csv = None
        self.column_names = []

    def set_csv_filepath(self, csv_filepath) -> None:
        """Store ``csv_filepath`` (``"-"`` is valid) and load column names.

        Builds ``self.csv = CSVUtils(csv_filepath)`` and stores
        ``self.column_names = self.csv.get_column_names()``; the CSV data itself
        is read once and cached by :class:`CSVUtils`.
        """
        from .utils import CSVUtils

        self.csv_filepath = csv_filepath
        self.csv = CSVUtils(csv_filepath)
        self.column_names = self.csv.get_column_names()

    def convert(self, csv_filepath, schema=None) -> list[dict]:
        """Convert ``csv_filepath`` into a list of nested dicts, one per data row.

        ``csv_filepath`` is required (``None`` raises ValueError).  ``schema``
        may be ``None`` (auto-generate), a JSON object string, or a dict.
        Leaves are always strings; row order follows the CSV.
        """
        if csv_filepath is None:
            raise ValueError("csv_filepath must not be None")
        self.set_csv_filepath(csv_filepath)
        column_names = self.column_names
        data_rows = self.csv.get_data_rows()
        if schema is None:
            structure = self.generate_full_structure(column_names)
        elif isinstance(schema, str):
            import json

            structure = json.loads(schema)
        else:
            structure = schema
        return self.populate_structure_with_data(structure, column_names, data_rows)

    def get_schema(self, csv_filepath) -> dict:
        """Return the auto-generated nested schema for ``csv_filepath``.

        Leaves hold the full original column name, e.g.
        ``{"birth": {"day": "birth day"}}``.
        """
        if csv_filepath is None:
            raise ValueError("csv_filepath must not be None")
        self.set_csv_filepath(csv_filepath)
        return copy.deepcopy(self.generate_full_structure(self.column_names))

    def generate_full_structure(self, column_names) -> dict:
        """Build the nested structure of one record from ``column_names``.

        Each leaf value is the *full original column name*.  Every original
        column name appears exactly once as a leaf value; non-leaf nodes hold at
        least two keys.
        """
        entries = [(column_name, column_name) for column_name in column_names]
        return self._build(entries)

    def get_nested_structure(self, parent_structure) -> dict:
        """Deep-copy ``parent_structure`` into a purely nested dict.

        String leaves are preserved (not replaced by None), key names and leaf
        values are untouched, and the input is never modified.
        """
        return self._normalize(copy.deepcopy(parent_structure))

    def populate_structure_with_data(self, structure, column_names, data_rows) -> list[dict]:
        """Fill a deep copy of ``structure`` for every row of ``data_rows``.

        Column lookup uses a name->index map (duplicate headers: last wins).
        When a row is shorter than the header, or the schema references a
        missing column, that key is omitted from that row's dict (never
        ``null``/``""``); extra cells are dropped.
        """
        index = {}
        for position, column_name in enumerate(column_names):
            index[column_name] = position
        result = []
        for row in data_rows:
            result.append(self._fill(copy.deepcopy(structure), index, row))
        return result

    def get_leaves(self, structure, path=(), result=None) -> dict[tuple[str, ...], str]:
        """Return ``{(path tuple): leaf string}`` for every leaf of ``structure``.

        The path includes the leaf key itself, e.g.
        ``{("birth", "day"): "birth day", ("name",): "name"}``.  ``result``
        defaults to a new dict; the input is not modified.
        """
        if result is None:
            result = {}
        if isinstance(structure, dict):
            for key, value in structure.items():
                if isinstance(value, dict):
                    self.get_leaves(value, path + (key,), result)
                else:
                    result[path + (key,)] = value
        return result

    def get_valid_splits(self, column_name) -> list[list[str]]:
        """Return purely syntactic two-part split candidates for ``column_name``.

        For each delimiter (in order) and each occurrence (left to right), the
        candidate ``[prefix, remainder]`` is kept when both sides are non-empty
        after stripping.  No header context is used here: semantic filtering
        happens in the per-level chooser.
        """
        splits = []
        if not isinstance(column_name, str):
            return splits
        for delimiter in self.delimiters:
            start = 0
            while True:
                position = column_name.find(delimiter, start)
                if position < 0:
                    break
                prefix = column_name[:position]
                remainder = column_name[position + len(delimiter):]
                start = position + len(delimiter)
                if prefix.strip() and remainder.strip():
                    splits.append([prefix, remainder])
        return splits

    def get_split_suffix(self, split, column_name) -> str:
        """Return the suffix of a two-part ``split`` (``split[1]``).

        A split with a length other than two raises ValueError.  ``column_name``
        is accepted for signature compatibility and is not re-validated here.
        """
        if len(split) != 2:
            raise ValueError("split must contain exactly two parts")
        return split[1]

    def clean_split(self, split) -> list[str]:
        """Strip every segment and drop empty ones, returning a list of strings.

        A plain string is first split on any configured delimiter.
        """
        if isinstance(split, str):
            segments = [split]
            for delimiter in sorted(self.delimiters, key=len, reverse=True):
                expanded = []
                for segment in segments:
                    expanded.extend(segment.split(delimiter))
                segments = expanded
        else:
            segments = list(split)
        return [segment.strip() for segment in segments if segment.strip()]

    def is_valid_prefix(self, prefix, base) -> bool:
        """Pure string predicate: is ``prefix`` a delimiter-prefix of ``base``?

        True when ``base == prefix`` or ``base`` starts with ``prefix +
        delimiter`` for some configured delimiter.  Header semantics (do not
        split when the prefix is itself a complete column) live in the chooser.
        """
        if base == prefix:
            return True
        return any(base.startswith(prefix + delimiter) for delimiter in self.delimiters)

    def escape_quotes(self, string) -> str:
        """Double every double quote (CSV escaping); non-strings pass through."""
        if isinstance(string, str):
            return string.replace('"', '""')
        return string

    # ------------------------------------------------------------------
    # Internal helpers (not part of the frozen public contract)
    # ------------------------------------------------------------------
    def _choose(self, relative_name, relatives):
        """Pick the one split to apply at this level, or ``None`` for a leaf.

        ``relatives`` are the relative names of the current level only.  A
        prefix that is itself a complete same-level column blocks splitting
        (rule b); a split is used only when at least one *other* same-level
        column shares ``prefix + delimiter`` (rule a).
        """
        for delimiter in self.delimiters:
            start = 0
            while True:
                position = relative_name.find(delimiter, start)
                if position < 0:
                    break
                if position == 0:
                    start = position + len(delimiter)
                    continue
                prefix = relative_name[:position]
                remainder = relative_name[position + len(delimiter):]
                start = position + len(delimiter)
                if not prefix.strip() or not remainder.strip():
                    continue
                if prefix in relatives:
                    continue
                if any(
                    other != relative_name and other.startswith(prefix + delimiter)
                    for other in relatives
                ):
                    return prefix, remainder
        return None

    def _build(self, entries):
        """Recursively build the structure from ``[(relative, original), ...]``."""
        relatives = [relative for relative, _ in entries]
        structure = {}
        groups = {}
        group_order = []
        for relative, original in entries:
            split = self._choose(relative, relatives)
            if split is None:
                structure[relative] = original
            else:
                prefix, remainder = split
                if prefix not in groups:
                    groups[prefix] = []
                    group_order.append(prefix)
                groups[prefix].append((remainder, original))
        for prefix in group_order:
            structure[prefix] = self._build(groups[prefix])
        return structure

    def _normalize(self, node):
        if isinstance(node, dict):
            return {key: self._normalize(value) for key, value in node.items()}
        if isinstance(node, list):
            return [self._normalize(value) for value in node]
        return node

    def _fill(self, node, index, row):
        if isinstance(node, dict):
            filled = {}
            for key, value in node.items():
                if isinstance(value, dict):
                    filled[key] = self._fill(value, index, row)
                elif isinstance(value, str):
                    position = index.get(value)
                    if position is not None and position < len(row):
                        filled[key] = row[position]
                else:
                    filled[key] = value
            return filled
        return node
