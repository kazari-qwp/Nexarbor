import io
import unittest
from pathlib import Path
from unittest import mock

from hone.utils.csv_utils import CSVUtils, parse_csv_file

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data_file"


class CSVUtilsColumnNamesTest(unittest.TestCase):
    def test_get_column_names_small_cats(self):
        csv = CSVUtils(DATA / "small_cats_dataset" / "column_names.csv")
        self.assertEqual(
            csv.get_column_names(),
            [
                "name",
                "age (years)",
                "weight (kg)",
                "birth day",
                "birth month",
                "birth year",
                "adopted",
                "adopted_since",
            ],
        )

    def test_get_column_names_quotes(self):
        csv = CSVUtils(DATA / "quotes_test" / "column_names.csv")
        self.assertEqual(
            csv.get_column_names(),
            [
                "name",
                "age (years)",
                "weight (kg)",
                "birth day",
                "birth month",
                "birth year",
                "adopted",
                "adopted_since",
                "some 'quoted\"' field\"",
            ],
        )

    def test_get_data_rows_small_cats(self):
        csv = CSVUtils(DATA / "small_cats_dataset" / "dataset.csv")
        self.assertEqual(
            csv.get_data_rows(),
            [
                ["Tommy", "5", "3.6", "11", "April", "2011", "TRUE", "2012"],
                ["Clara", "2", "8.2", "6", "May", "2015", "FALSE", "N/A"],
                ["Catnip", "6", "3.3", "21", "August", "2011", "TRUE", "2017"],
                ["Ciel", "3", "3.1", "18", "January", "2015", "TRUE", "2018"],
            ],
        )

    def test_all_rows_equals_split_files(self):
        names = CSVUtils(DATA / "small_cats_dataset" / "column_names.csv")
        rows = CSVUtils(DATA / "small_cats_dataset" / "data_rows.csv")
        dataset = CSVUtils(DATA / "small_cats_dataset" / "dataset.csv")
        self.assertEqual(names.get_all_rows(), [dataset.get_column_names()])
        self.assertEqual(rows.get_all_rows(), dataset.get_data_rows())

    def test_data_rows_file_alone_has_no_data_rows(self):
        # A file whose only record is the header has no data rows.
        self.assertEqual(
            CSVUtils(DATA / "comma_test" / "data_rows.csv").get_all_rows(),
            [['"1', '"2']],
        )
        self.assertEqual(
            CSVUtils(DATA / "comma_test" / "data_rows.csv").get_column_names(),
            ['"1', '"2'],
        )
        self.assertEqual(
            CSVUtils(DATA / "comma_test" / "data_rows.csv").get_data_rows(), []
        )

    def test_parse_csv_file_helper(self):
        self.assertEqual(
            parse_csv_file(DATA / "comma_test" / "dataset.csv"),
            [['"test","ing"', ' "beep"""'], ['"1', '"2']],
        )


class CSVUtilsBlankAndCacheTest(unittest.TestCase):
    def test_blank_rows_are_filtered(self):
        with mock.patch("sys.stdin", io.StringIO("a,b\n\n1,2\n\n3,4\n")):
            csv = CSVUtils("-")
            self.assertEqual(csv.get_column_names(), ["a", "b"])
            self.assertEqual(csv.get_data_rows(), [["1", "2"], ["3", "4"]])

    def test_stdin_is_read_only_once(self):
        # A second read of sys.stdin would be empty.  These three calls all
        # returning real data proves the records were cached after one read.
        with mock.patch("sys.stdin", io.StringIO("a,b\n1,2\n3,4\n")):
            csv = CSVUtils("-")
            self.assertEqual(csv.get_column_names(), ["a", "b"])
            self.assertEqual(csv.get_data_rows(), [["1", "2"], ["3", "4"]])
            self.assertEqual(
                csv.get_all_rows(),
                [["a", "b"], ["1", "2"], ["3", "4"]],
            )

    def test_open_csv_context_manager(self):
        csv = CSVUtils(DATA / "comma_test" / "dataset.csv")
        with csv.open_csv("r", newline="") as handle:
            lines = handle.read().splitlines()
        self.assertEqual(len(lines), 2)
