from pathlib import Path

import pytest

from mtools.internal.plotTools import find_results


class TestFindResults:
    @staticmethod
    def _write_csv(path: Path, value: int) -> Path:
        """Write a minimal CSV result file.

        Args:
            path: File path to create.
            value: Value to place in the CSV content.

        Returns:
            The created CSV path.
        """

        path.write_text(f"time,value\n0,{value}\n")
        return path

    def test_missing_directory(self, tmp_path: Path):
        """Verify that missing result directories raise FileNotFoundError.

        Args:
            tmp_path: Temporary directory used to build a missing path.
        """

        missing_directory = tmp_path / "missing"

        with pytest.raises(FileNotFoundError, match=str(missing_directory)):
            find_results(missing_directory)

    def test_non_directory_path(self, tmp_path: Path):
        """Verify that file paths raise NotADirectoryError.

        Args:
            tmp_path: Temporary directory used to create a CSV file path.
        """

        result_file = self._write_csv(tmp_path / "results.csv", 1)

        with pytest.raises(NotADirectoryError, match=str(result_file)):
            find_results(result_file)

    def test_discovers_csv_files(self, tmp_path: Path):
        """Verify that CSV files are discovered recursively under a directory.

        Args:
            tmp_path: Temporary directory used to create nested CSV files.
        """

        top_level_result = self._write_csv(tmp_path / "b.csv", 1)
        nested_directory = tmp_path / "nested" / "deeper"
        nested_directory.mkdir(parents=True)
        nested_result = self._write_csv(nested_directory / "a.csv", 2)
        ignored_file = nested_directory / "notes.txt"
        ignored_file.write_text("ignore me\n")

        results = find_results(tmp_path)

        assert results == [str(top_level_result), str(nested_result)]

    def test_returns_sorted_paths(self, tmp_path: Path):
        """Verify that discovered result paths are returned in sorted order.

        Args:
            tmp_path: Temporary directory used to create unsorted CSV files.
        """

        later_result = self._write_csv(tmp_path / "zeta.csv", 1)
        earlier_result = self._write_csv(tmp_path / "alpha.csv", 2)

        results = find_results(tmp_path)

        assert results == [str(earlier_result), str(later_result)]