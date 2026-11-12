"""Name map between experiment names and a given FMU's variables."""

from __future__ import annotations

import numpy as np
import pytest

from mtools.errors import ConfigError
from mtools.internal import run_config
from mtools.session_config import FmuFile, RunSettings, SimulationRun
from tests.fmu.helpers import reference_fmu, simulate_given


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


@pytest.mark.parametrize(
    "name_map, lines",
    [
        pytest.param({"a": "time"}, ["build.name_map: 'time' can't be mapped"], id="time-as-fmu-name"),
        pytest.param({"x": "time"}, ["build.name_map: 'time' can't be mapped"], id="fmu-variable-to-time"),
        pytest.param(
            {"a": "x", "b": "x", "c": "x"},
            ["build.name_map: 'a', 'b' and 'c' all map to FMU name 'x'"],
            id="three-keys-one-name",
        ),
    ],
)
def test_map_problem_is_reported_once(name_map, lines):
    with pytest.raises(ConfigError) as error:
        simulate_given(reference_fmu("Dahlquist"), name_map=name_map)
    assert error.value.diagnostics.splitlines() == lines


def test_collision_is_checked_whatever_the_filter_keeps():
    with pytest.raises(ConfigError) as error:
        simulate_given(reference_fmu("Dahlquist"), name_map={"x": "k"}, variable_filter="nothing")
    assert "build.name_map.x: 'x' is also the name of an FMU variable that isn't renamed" in error.value.diagnostics


@pytest.mark.parametrize("name_map", [{"a": 1}, ["a"], {1: "x"}])
def test_name_map_must_map_strings_to_strings(name_map):
    run = SimulationRun(
        build=FmuFile(fmu_path=reference_fmu("Dahlquist"), name_map=name_map),  # type: ignore[arg-type]
        settings=RunSettings(parameters={}),
    )
    with pytest.raises(ConfigError) as error:
        run_config.validate_fmu_file(run)
    assert "build.name_map: expected a mapping of experiment names to FMU names, got" in error.value.diagnostics


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
