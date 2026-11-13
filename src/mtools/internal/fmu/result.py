"""Turn FMPy's structured result array into a result DataFrame like a native one."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mtools.errors import SimulationError
from mtools.internal.fmu.description import VALUE_KINDS
from mtools.internal.fmu.resolve import ResolvedRun

_INT64_MAX = np.iinfo(np.int64).max


def to_frame(array: np.ndarray, run: ResolvedRun) -> pd.DataFrame:
    """Return ``time``, then ``run.columns`` in their order, under their result names."""
    columns = {"time": array["time"].astype(np.float64)}
    for fmu_name, column in run.columns.items():
        columns[column] = cast_column(column, array[fmu_name], run.column_types[fmu_name], run.model_name)
    return pd.DataFrame(columns)


def cast_column(name: str, values: np.ndarray, fmi_type: str, model_name: str) -> np.ndarray:
    """Return ``values`` as the native dtype of ``fmi_type``.

    Real types become ``float64``, Boolean ``bool``, and Integer, every sized
    integer and Enumeration ``int64``. Any other type keeps FMPy's dtype.

    Raises:
        SimulationError: A ``UInt64`` value is above the ``int64`` range.
    """
    kind = VALUE_KINDS.get(fmi_type)
    if kind == "Real":
        return values.astype(np.float64)
    if kind == "Boolean":
        return values.astype(np.bool_)
    if kind not in ("Integer", "Enumeration"):
        return values
    if fmi_type == "UInt64" and values.size and values.max() > _INT64_MAX:
        raise SimulationError(
            f"Simulation of '{model_name}' failed:",
            model_name=model_name,
            diagnostics=f"column '{name}' holds a UInt64 value above the int64 range",
        )
    return values.astype(np.int64)
