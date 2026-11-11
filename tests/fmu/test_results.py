"""Typed result columns of a given-FMU run."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mtools import sim_tools
from mtools.errors import SimulationError
from mtools.internal.fmu.result import cast_column
from tests.fmu.helpers import reference_fmu, simulate_given


@pytest.mark.parametrize("version", ["2.0", "3.0"])
def test_stair_counter_is_int64(version: str) -> None:
    result = simulate_given(reference_fmu("Stair", version))["Stair"]
    assert list(result.columns) == ["time", "counter"] and result["counter"].dtype == "int64"


def test_fmi3_fmus_run() -> None:
    for name in ["BouncingBall", "Dahlquist", "VanDerPol"]:
        result = simulate_given(reference_fmu(name, "3.0"), model_name=name)[name]
        assert result["time"].dtype == "float64" and list(result.columns)[0] == "time"


@pytest.mark.parametrize(
    "fmi_type, values, dtype",
    [
        ("Float32", np.array([1.5], np.float32), "float64"),
        ("Int8", np.array([3], np.int8), "int64"),
        ("UInt32", np.array([7], np.uint32), "int64"),
        ("Enumeration", np.array([2], np.int32), "int64"),
        ("Boolean", np.array([1], np.int32), "bool"),
        ("UInt64", np.array([2**62], np.uint64), "int64"),
    ],
)
def test_every_fmi_type_maps_to_a_native_dtype(fmi_type: str, values: np.ndarray, dtype: str) -> None:
    assert cast_column("y", values, fmi_type, "M").dtype == dtype


def test_uint64_overflow_names_the_column() -> None:
    with pytest.raises(SimulationError, match="'big'"):
        cast_column("big", np.array([2**63], np.uint64), "UInt64", "M")


def test_save_round_trip(tmp_path: Path) -> None:
    results = simulate_given(reference_fmu("Stair"))
    sim_tools.save_solutions(results, tmp_path, "mat")
    pd.testing.assert_frame_equal(sim_tools.load_solution(tmp_path / "Stair.mat"), results["Stair"])
