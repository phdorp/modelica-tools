"""The `.mat` result reader, on hand-made MATLAB v4 files in OMC's binTrans layout."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mtools.internal.omc.matfile import read_result


def _text_matrix(strings: list[str]) -> np.ndarray:
    """One string per column, padded with NUL characters, as OMC stores ``name``."""
    width = max(len(s) for s in strings)
    return np.array([[ord(c) for c in s.ljust(width, "\0")] for s in strings], dtype=np.uint8).T


def _write_matrix(handle, name: str, matrix: np.ndarray, mopt: int) -> None:
    rows, cols = matrix.shape
    encoded = name.encode() + b"\0"
    handle.write(struct.pack("<5i", mopt, rows, cols, 0, len(encoded)))
    handle.write(encoded)
    handle.write(matrix.flatten(order="F").tobytes())


def write_omc_mat(
    path: Path,
    variables: list[tuple[str, int, int]],
    data_1: list[list[float]],
    data_2: list[list[float]],
) -> Path:
    """Write ``variables`` as ``(name, matrix, signed 1-based row)`` with rows of time points."""
    aclass = np.array(
        [[ord(c) for c in s.ljust(11, "\0")] for s in ("Atrajectory", "1.1", "", "binTrans")], dtype=np.uint8
    )
    info = np.array([[matrix, row, 0, -1 if matrix == 0 else 0] for _, matrix, row in variables], dtype="<i4").T
    with open(path, "wb") as handle:
        _write_matrix(handle, "Aclass", aclass, 51)
        _write_matrix(handle, "name", _text_matrix([name for name, _, _ in variables]), 51)
        _write_matrix(handle, "description", _text_matrix([" "] * len(variables)), 51)
        _write_matrix(handle, "dataInfo", info, 20)
        _write_matrix(handle, "data_1", np.array(data_1, dtype="<f8").T, 0)
        _write_matrix(handle, "data_2", np.array(data_2, dtype="<f8").T, 0)
    return path


@pytest.fixture
def result_file(tmp_path: Path) -> Path:
    # time | x | count | on, plus parameter k in data_1, and negx = -x.
    return write_omc_mat(
        tmp_path / "model_res.mat",
        variables=[("time", 0, 1), ("x", 2, 2), ("count", 2, 3), ("on", 2, 4), ("k", 1, 2), ("negx", 2, -2)],
        data_1=[[0.0, 2.0], [1.0, 2.0]],
        data_2=[
            [0.0, 1.0, 0.0, 0.0],
            [0.5, 0.5, 0.0, 0.0],
            [0.5, 0.5, 1.0, 1.0],
            [1.0, 0.25, 1.0, 1.0],
        ],
    )


def test_columns_are_time_then_time_varying_variables_in_file_order(result_file: Path):
    result = read_result(result_file, {})

    assert list(result.columns) == ["time", "x", "count", "on", "negx"]


def test_negated_alias_is_the_negated_original(result_file: Path):
    result = read_result(result_file, {})

    assert result["negx"].tolist() == [-1.0, -0.5, -0.5, -0.25]


def test_repeated_event_rows_are_kept(result_file: Path):
    result = read_result(result_file, {})

    assert result["time"].tolist() == [0.0, 0.5, 0.5, 1.0]
    assert result["count"].tolist() == [0, 0, 1, 1]


def test_columns_are_cast_from_modelica_types(result_file: Path):
    result = read_result(result_file, {"x": "Real", "count": "Integer", "on": "Boolean", "negx": "Real"})

    assert result.dtypes.to_dict() == {
        "time": np.dtype("float64"),
        "x": np.dtype("float64"),
        "count": np.dtype("int64"),
        "on": np.dtype("bool"),
        "negx": np.dtype("float64"),
    }
    assert result["on"].tolist() == [False, False, True, True]


def test_enumeration_columns_are_int64(tmp_path: Path):
    path = write_omc_mat(
        tmp_path / "enum_res.mat",
        variables=[("time", 0, 1), ("mode", 2, 2)],
        data_1=[[0.0], [1.0]],
        data_2=[[0.0, 1.0], [1.0, 2.0]],
    )

    result = read_result(path, {"mode": "Enumeration"})

    assert result["mode"].dtype == np.dtype("int64")
    assert result["mode"].tolist() == [1, 2]


def test_result_is_a_dataframe_with_a_default_index(result_file: Path):
    result = read_result(result_file, {})

    assert isinstance(result, pd.DataFrame)
    assert list(result.index) == [0, 1, 2, 3]
