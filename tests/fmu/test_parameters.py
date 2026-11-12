"""Parameters of given FMUs: names, value types and start values."""

import numpy as np
import pytest

from mtools import sim_tools
from mtools.errors import ConfigError
from mtools.hydra_registry import HydraZenRegistry
from mtools.session_config import RunSettings
from tests.fmu.fmu_models import DahlquistParameters
from tests.fmu.helpers import capture_request, reference_fmu, simulate_given

PARAMS = "FmuTests.Params"


def test_parameters_are_flattened_and_set():
    result = simulate_given(reference_fmu("Dahlquist"), parameters={"k": 0.5})["Dahlquist"]
    np.testing.assert_allclose(result["x"], np.exp(-0.5 * result["time"]), rtol=1e-4, atol=1e-6)


def test_array_elements_are_expanded(exported_fmu):
    result = simulate_given(exported_fmu(PARAMS), parameters={"y0": [3.0, 4.0]})[PARAMS]
    assert result["x"].iloc[0] == pytest.approx(3.0)
    assert result["total"].iloc[0] == pytest.approx(2 + 4.0 + 2 * 1 + 3 + 1 + 0 + 1)


def test_every_problem_is_reported_once(exported_fmu):
    with pytest.raises(ConfigError) as error:
        simulate_given(
            exported_fmu(PARAMS), parameters={"nope": 1, "k": "x", "n": 2.7, "on": 1, "mode": "low"}
        )
    lines = error.value.diagnostics.splitlines()
    assert "settings.parameters.nope: 'FmuTests.Params' has no parameter 'nope'" in lines
    assert "settings.parameters.k: expected a Real, got 'x'" in lines
    assert "settings.parameters.n: expected an Integer, got 2.7" in lines
    assert "settings.parameters.on: expected a Boolean, got 1" in lines
    assert (
        "settings.parameters.mode: expected an enumeration item or a qualified literal such as 'Mode.high', got 'low'"
        in lines
    )
    assert len(lines) == 5


def test_problems_join_the_other_run_setting_problems(exported_fmu):
    with pytest.raises(ConfigError) as error:
        simulate_given(exported_fmu(PARAMS), parameters={"nope": 1}, solver="rk4")
    assert error.value.diagnostics.count("settings.solver:") == 1
    assert "settings.parameters.nope:" in error.value.diagnostics


def test_fixed_parameter_says_the_fmu_cannot_be_rebuilt(exported_fmu):
    with pytest.raises(ConfigError) as error:
        simulate_given(exported_fmu(PARAMS), parameters={"twice": 4.0})
    assert (
        "settings.parameters.twice: 'FmuTests.Params' parameter 'twice' is fixed in the FMU (calculatedParameter); "
        "a given FMU can't be rebuilt" in error.value.diagnostics
    )


def test_integer_parameter_accepts_integral_float_and_rejects_bool(exported_fmu, monkeypatch):
    fmu = exported_fmu(PARAMS)
    request = capture_request(monkeypatch, fmu, parameters={"n": 3.0})
    assert request.start_values == {"n": 3} and isinstance(request.start_values["n"], int)
    result = simulate_given(fmu, parameters={"n": 3.0})[PARAMS]
    assert result["total"].iloc[0] == pytest.approx(3 + 2 + 2 + 3 + 1 + 0 + 1)
    with pytest.raises(ConfigError) as error:
        simulate_given(fmu, parameters={"k": True, "n": True})
    lines = error.value.diagnostics.splitlines()
    assert "settings.parameters.k: expected a Real, got True" in lines
    assert "settings.parameters.n: expected an Integer, got True" in lines


def test_enumeration_takes_integer_or_qualified_literal(exported_fmu):
    fmu = exported_fmu(PARAMS)
    for value in (2, "Mode.high"):
        result = simulate_given(fmu, parameters={"mode": value})[PARAMS]
        assert result["total"].iloc[0] == pytest.approx(2 + 2 + 2 + 3 + 1 + 1 + 1), value


def test_unit_tuple_is_rejected(exported_fmu):
    with pytest.raises(ConfigError) as error:
        simulate_given(exported_fmu(PARAMS), parameters={"k": (1.0, "m")})
    assert "settings.parameters.k: expected a Real" in error.value.diagnostics


def test_boolean_and_string_parameters_are_set(exported_fmu):
    result = simulate_given(exported_fmu(PARAMS), parameters={"on": False, "label": "b"})[PARAMS]
    assert result["total"].iloc[0] == pytest.approx(2 + 2 + 2 + 3 + 0 + 0 + 0)


def test_sweep_over_a_given_fmu_parameter(tmp_path):
    run = HydraZenRegistry().create_fmu_run(
        fmu_path=reference_fmu("Dahlquist"), settings=RunSettings(parameters=DahlquistParameters())
    )
    results = sim_tools.simulate(
        run, overrides=["settings.parameters.k=0.5,2.0"], multirun=True, sweep_dir=str(tmp_path)
    )
    by_rate = {r.config.settings.parameters.k: r.solutions["Dahlquist"] for r in results}
    assert sorted(by_rate) == [0.5, 2.0]
    for rate, solution in by_rate.items():
        np.testing.assert_allclose(solution["x"], np.exp(-rate * solution["time"]), rtol=1e-4, atol=1e-6)
