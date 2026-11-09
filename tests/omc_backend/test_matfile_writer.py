"""The `.mat` result writer: saved results in OMC's binTrans layout that read back typed."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mtools.internal.omc.matfile import read_result, write_result


@pytest.fixture
def solution() -> pd.DataFrame:
    # Repeated event rows at t=0.5, and names as OMC writes them.
    return pd.DataFrame(
        {
            "time": [0.0, 0.5, 0.5, 1.0],
            "x": [1.0, 0.5, 0.5, 0.25],
            "der(x)": [-1.0, -0.5, -0.5, -0.25],
            "body.m[1,2]": [2.0, 2.0, 2.0, 2.0],
            "count": np.array([0, 0, 1, 1], dtype="int64"),
            "on": [False, False, True, True],
        }
    )


def test_saved_result_reads_back_with_columns_rows_and_types(tmp_path: Path, solution: pd.DataFrame):
    path = write_result(tmp_path / "M.mat", solution)

    pd.testing.assert_frame_equal(read_result(path), solution)


def test_reals_keep_full_double_precision(tmp_path: Path):
    solution = pd.DataFrame({"time": [0.0, 1.0], "x": [1 / 3, np.pi]})

    result = read_result(write_result(tmp_path / "M.mat", solution))

    assert result["x"].tolist() == [1 / 3, np.pi]


def test_explicit_types_override_the_stored_ones(tmp_path: Path, solution: pd.DataFrame):
    result = read_result(write_result(tmp_path / "M.mat", solution), {})

    assert (result.dtypes == np.dtype("float64")).all()


def test_a_result_without_rows_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="no rows"):
        write_result(tmp_path / "M.mat", pd.DataFrame({"time": pd.Series([], dtype="float64")}))


def test_a_non_numeric_column_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="'label'"):
        write_result(tmp_path / "M.mat", pd.DataFrame({"time": [0.0], "label": ["a"]}))


@pytest.mark.skipif(shutil.which("omc") is None, reason="needs omc")
def test_openmodelica_reads_the_saved_result(tmp_path: Path, solution: pd.DataFrame):
    path = write_result(tmp_path / "M.mat", solution)
    script = tmp_path / "read.mos"
    script.write_text(f'readSimulationResult("{path}", {{time, x, on}});\ngetErrorString();\n')

    output = subprocess.run(["omc", str(script)], capture_output=True, text=True, check=True).stdout

    assert output.splitlines() == ["{{0.0, 0.5, 0.5, 1.0}, {1.0, 0.5, 0.5, 0.25}, {0.0, 0.0, 1.0, 1.0}}", '""']
