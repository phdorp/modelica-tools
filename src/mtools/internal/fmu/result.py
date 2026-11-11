"""Turn FMPy's structured result array into a result DataFrame like a native one."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mtools.internal.fmu.resolve import ResolvedRun


def to_frame(array: np.ndarray, run: ResolvedRun) -> pd.DataFrame:
    """Return ``time``, then ``run.columns`` in their order, under their result names."""
    columns = {"time": array["time"].astype(np.float64)}
    for fmu_name, column in run.columns.items():
        columns[column] = array[fmu_name].astype(np.float64)
    return pd.DataFrame(columns)
