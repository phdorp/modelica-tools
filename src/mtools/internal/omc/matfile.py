"""Read OMC result files (MATLAB v4, ``binTrans`` layout) into DataFrames.

OMC writes four matrices after the ``Aclass`` header: ``name`` and ``description``
(one string per column), ``dataInfo`` (per variable: data matrix, signed 1-based row,
interpolation, extrapolation), ``data_1`` (parameters, two time points) and ``data_2``
(trajectories, one column per time point). A negative row marks a negated alias.
Everything is stored as double; the caller's Modelica types restore the column dtypes.

:func:`write_result` saves a result DataFrame in the same layout, with the Modelica type
of each column in a trailing ``mtools_types`` matrix that OMC's own reader ignores, so a
saved result reads back typed without the build's ``_init.xml``.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO

import numpy as np
import pandas as pd

_PRECISIONS = {0: "<f8", 1: "<f4", 2: "<i4", 3: "<i2", 4: "<u2", 5: "<u1"}

_DTYPES = {"Real": "float64", "Integer": "int64", "Enumeration": "int64", "Boolean": "bool"}

_TRAJECTORY_MATRIX = 2
_ABSCISSA_MATRIX = 0

#: Name of the matrix holding one Modelica type per column in files mtools writes.
_TYPES_MATRIX = "mtools_types"

# MATLAB v4 ``mopt`` values: little-endian double, int32 and text matrices.
_MOPT_DOUBLE, _MOPT_INT32, _MOPT_TEXT = 0, 20, 51


def read_result(path: Path, types: Mapping[str, str] | None = None) -> pd.DataFrame:
    """Read the trajectories of an OMC ``.mat`` result file.

    Args:
        path: The result file.
        types: Modelica type (``Real``, ``Integer``, ``Enumeration``, ``Boolean``) per
            variable name. Variables without an entry stay ``float64``. ``None`` uses
            the types :func:`write_result` stored in the file, if any.

    Returns:
        ``time`` followed by one column per time-varying variable, in file order, with
        every row as written, including the repeated time points at events.
    """
    matrices = _read_matrices(path)
    names = _strings(matrices["name"])
    data_info = matrices["dataInfo"]
    trajectories = matrices["data_2"]
    if types is None:
        types = _stored_types(matrices, names)

    columns: dict[str, np.ndarray] = {}
    for column, name in enumerate(names):
        matrix, row = int(data_info[0, column]), int(data_info[1, column])
        if matrix not in (_ABSCISSA_MATRIX, _TRAJECTORY_MATRIX):
            continue
        values = np.sign(row) * trajectories[abs(row) - 1]
        columns[name] = _cast(values, types.get(name))
    return pd.DataFrame(columns)


def write_result(path: Path, result: pd.DataFrame) -> Path:
    """Save a result in OMC's binTrans layout, with the column types stored alongside.

    Args:
        path: The file to write.
        result: ``time`` first, then ``float64``, ``int64`` or ``bool`` columns.

    Returns:
        ``path``.

    Raises:
        ValueError: The result has no rows, does not start with ``time``, or has a
            column that is not numeric or Boolean.
    """
    if result.empty:
        raise ValueError(f"{path}: cannot save a result with no rows as .mat")
    if str(result.columns[0]) != "time":
        raise ValueError(f"{path}: the first column must be 'time', got {result.columns[0]!r}")
    names = [str(name) for name in result.columns]
    types = [_modelica_type(name, result[name]) for name in names]
    # Column 0 is the abscissa (time); every other column is its own trajectory row.
    info = np.array([[0 if i == 0 else 2, i + 1, 0, -1 if i == 0 else 0] for i in range(len(names))], "<i4").T
    data = result.to_numpy(dtype="<f8")
    aclass = _text(["Atrajectory", "1.1", "", "binTrans"]).T
    with open(path, "wb") as handle:
        _write_matrix(handle, "Aclass", aclass, _MOPT_TEXT)
        _write_matrix(handle, "name", _text(names), _MOPT_TEXT)
        _write_matrix(handle, "description", _text([""] * len(names)), _MOPT_TEXT)
        _write_matrix(handle, "dataInfo", info, _MOPT_INT32)
        _write_matrix(handle, "data_1", data[[0, -1], :1].T, _MOPT_DOUBLE)
        _write_matrix(handle, "data_2", data.T, _MOPT_DOUBLE)
        _write_matrix(handle, _TYPES_MATRIX, _text(types), _MOPT_TEXT)
    return path


def is_result_file(path: Path) -> bool:
    """Whether ``path`` starts with OMC's binTrans ``Aclass`` header; reads only that matrix."""
    try:
        with open(path, "rb") as handle:
            header = handle.read(20)
            if len(header) < 20:
                return False
            mopt, rows, cols, _imaginary, name_length = struct.unpack("<5i", header)
            if mopt != _MOPT_TEXT or not 0 < name_length <= 64 or not 0 < rows * cols <= 1024:
                return False
            if handle.read(name_length).rstrip(b"\0") != b"Aclass":
                return False
            aclass = np.frombuffer(handle.read(rows * cols), np.uint8)
    except OSError:
        return False
    if aclass.size != rows * cols:
        return False
    return len(strings := _strings(aclass.reshape(cols, rows))) == 4 and strings[3] == "binTrans"


def _modelica_type(name: str, column: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(column):
        return "Boolean"
    if pd.api.types.is_integer_dtype(column):
        return "Integer"
    if pd.api.types.is_float_dtype(column):
        return "Real"
    raise ValueError(f"column {name!r}: cannot save {column.dtype} values as .mat")


def _stored_types(matrices: Mapping[str, np.ndarray], names: list[str]) -> dict[str, str]:
    if _TYPES_MATRIX not in matrices:
        return {}
    return dict(zip(names, _strings(matrices[_TYPES_MATRIX])))


def _text(strings: list[str]) -> np.ndarray:
    """One string per column, padded with NUL bytes, as OMC stores ``name``."""
    encoded = [s.encode() for s in strings]
    width = max(1, *(len(e) for e in encoded))
    return np.array([list(e.ljust(width, b"\0")) for e in encoded], dtype=np.uint8).T


def _write_matrix(handle: BinaryIO, name: str, matrix: np.ndarray, mopt: int) -> None:
    rows, cols = matrix.shape
    encoded = name.encode() + b"\0"
    handle.write(struct.pack("<5i", mopt, rows, cols, 0, len(encoded)))
    handle.write(encoded)
    handle.write(np.asfortranarray(matrix).tobytes(order="F"))


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
