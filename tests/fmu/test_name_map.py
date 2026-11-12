"""Name map between experiment names and a given FMU's variables."""

from __future__ import annotations

import numpy as np
import pytest

from mtools.errors import ConfigError
from tests.fmu.helpers import reference_fmu, simulate_given

pytestmark = pytest.mark.fmu


def test_map_renames_parameters_in_and_columns_out():
    result = simulate_given(
        reference_fmu("Dahlquist"), name_map={"decay.k": "k", "state": "x"}, parameters={"decay": {"k": 0.5}}
    )["Dahlquist"]
    assert list(result.columns) == ["time", "state", "der(x)"]
    np.testing.assert_allclose(result["state"], np.exp(-0.5 * result["time"]), rtol=1e-4, atol=1e-6)


def test_filter_matches_experiment_names():
    result = simulate_given(reference_fmu("Dahlquist"), name_map={"state": "x"}, variable_filter="state")
    assert list(result["Dahlquist"].columns) == ["time", "state"]


@pytest.mark.parametrize(
    "name_map, line",
    [
        ({"a": "nope"}, "build.name_map.a: 'Dahlquist' has no variable 'nope'"),
        ({"a": "x", "b": "x"}, "build.name_map: 'a' and 'b' both map to FMU name 'x'"),
        ({"time": "x"}, "build.name_map: 'time' can't be mapped"),
        ({"x": "k"}, "build.name_map.x: 'x' is also the name of an FMU variable that isn't renamed"),
    ],
)
def test_map_problems(name_map, line):
    with pytest.raises(ConfigError) as error:
        simulate_given(reference_fmu("Dahlquist"), name_map=name_map, variable_filter="x")
    assert line in error.value.diagnostics  # collision checked regardless of variable_filter


def test_swap_is_legal():
    result = simulate_given(
        reference_fmu("Dahlquist"), name_map={"x": "k", "k": "x"}, parameters={"x": 0.5}, variable_filter="x|k"
    )["Dahlquist"]
    assert list(result.columns) == ["time", "k"]  # the FMU's state x is the experiment's k
    np.testing.assert_allclose(result["k"], np.exp(-0.5 * result["time"]), rtol=1e-4, atol=1e-6)


def test_mapped_parameter_problem_names_the_fmu_name():
    with pytest.raises(ConfigError) as error:
        simulate_given(reference_fmu("Dahlquist"), name_map={"ctrl.k": "k"}, parameters={"ctrl": {"k": "fast"}})
    assert "settings.parameters.ctrl.k (FMU name 'k'): expected a Real, got 'fast'" in error.value.diagnostics
