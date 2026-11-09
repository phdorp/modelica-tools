"""``save_solutions`` writes each result as `.mat` (default) or `.csv`; both read back."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mtools.sim_tools import load_solution, save_solutions


@pytest.fixture
def solutions() -> dict[str, pd.DataFrame]:
    return {
        "pkg.M": pd.DataFrame(
            {
                "time": [0.0, 0.5, 0.5, 1.0],
                "x": [1.0, 0.5, 0.5, 0.25],
                "count": np.array([0, 0, 1, 1], dtype="int64"),
                "on": [False, False, True, True],
            }
        )
    }


def test_results_are_saved_as_mat_by_default(tmp_path: Path, solutions):
    save_solutions(solutions, str(tmp_path))

    assert sorted(p.name for p in tmp_path.iterdir()) == ["pkg.M.mat"]


@pytest.mark.parametrize("output_format", ["mat", "csv"])
def test_saved_results_read_back_unchanged(tmp_path: Path, solutions, output_format):
    save_solutions(solutions, tmp_path, output_format)

    pd.testing.assert_frame_equal(load_solution(tmp_path / f"pkg.M.{output_format}"), solutions["pkg.M"])


def test_csv_writes_booleans_as_true_false(tmp_path: Path, solutions):
    save_solutions(solutions, tmp_path, "csv")

    assert (tmp_path / "pkg.M.csv").read_text().splitlines()[1] == "0.0,1.0,0,False"


def test_an_unknown_format_is_rejected(tmp_path: Path, solutions):
    with pytest.raises(ValueError, match="'json'"):
        save_solutions(solutions, tmp_path, "json")  # type: ignore[arg-type]
    assert list(tmp_path.iterdir()) == []


def test_reading_an_unknown_suffix_is_rejected(tmp_path: Path):
    path = tmp_path / "notes.txt"
    path.write_text("x")

    with pytest.raises(ValueError, match="notes.txt"):
        load_solution(path)
