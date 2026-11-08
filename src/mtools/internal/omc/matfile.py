"""Read OMC result files (MATLAB v4, ``binTrans`` layout) into DataFrames.

OMC writes four matrices after the ``Aclass`` header: ``name`` and ``description``
(one string per column), ``dataInfo`` (per variable: data matrix, signed 1-based row,
interpolation, extrapolation), ``data_1`` (parameters, two time points) and ``data_2``
(trajectories, one column per time point). A negative row marks a negated alias.
Everything is stored as double; the caller's Modelica types restore the column dtypes.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

_PRECISIONS = {0: "<f8", 1: "<f4", 2: "<i4", 3: "<i2", 4: "<u2", 5: "<u1"}

_DTYPES = {"Real": "float64", "Integer": "int64", "Enumeration": "int64", "Boolean": "bool"}

_TRAJECTORY_MATRIX = 2
_ABSCISSA_MATRIX = 0


def read_result(path: Path, types: Mapping[str, str]) -> pd.DataFrame:
    """Read the trajectories of an OMC ``.mat`` result file.

    Args:
        path: The result file.
        types: Modelica type (``Real``, ``Integer``, ``Enumeration``, ``Boolean``) per
            variable name. Variables without an entry stay ``float64``.

    Returns:
        ``time`` followed by one column per time-varying variable, in file order, with
        every row as written, including the repeated time points at events.
    """
    matrices = _read_matrices(path)
    names = _strings(matrices["name"])
    data_info = matrices["dataInfo"]
    trajectories = matrices["data_2"]

    columns: dict[str, np.ndarray] = {}
    for column, name in enumerate(names):
        matrix, row = int(data_info[0, column]), int(data_info[1, column])
        if matrix not in (_ABSCISSA_MATRIX, _TRAJECTORY_MATRIX):
            continue
        values = np.sign(row) * trajectories[abs(row) - 1]
        columns[name] = _cast(values, types.get(name))
    return pd.DataFrame(columns)


def _cast(values: np.ndarray, modelica_type: str | None) -> np.ndarray:
    dtype = _DTYPES.get(modelica_type or "Real", "float64")
    if dtype == "bool":
        return values != 0
    if dtype == "int64":
        return np.rint(values).astype("int64")
    return values.astype("float64")


def _read_matrices(path: Path) -> dict[str, np.ndarray]:
    """Return every matrix of a little-endian MATLAB v4 file as ``rows x cols``."""
    matrices: dict[str, np.ndarray] = {}
    with open(path, "rb") as handle:
        while header := handle.read(20):
            mopt, rows, cols, _imaginary, name_length = struct.unpack("<5i", header)
            if mopt // 1000 != 0:
                raise ValueError(f"{path}: only little-endian MATLAB v4 files are supported")
            name = handle.read(name_length).rstrip(b"\0").decode()
            dtype = np.dtype(_PRECISIONS[(mopt // 10) % 10])
            column_size = rows * dtype.itemsize
            # An unfinished file (killed run) declares 0 columns; keep every complete one
            # in the remaining bytes. A short last matrix is cut to its complete columns.
            data = handle.read(rows * cols * dtype.itemsize if cols else -1)
            cols = len(data) // column_size if column_size else 0
            flat = np.frombuffer(data[: cols * column_size], dtype)
            matrices[name] = flat.reshape(cols, rows).T  # stored column-major
    if "Aclass" not in matrices or _strings(matrices["Aclass"].T)[3] != "binTrans":
        raise ValueError(f"{path}: not an OMC result file in binTrans layout")
    return matrices


def _strings(matrix: np.ndarray) -> list[str]:
    """Decode a character matrix that holds one string per column."""
    return [bytes(column.astype(np.uint8)).decode().rstrip("\0 ") for column in matrix.T]
