"""Solver, interval, tolerance and ``variable_filter`` for FMU runs."""

import pytest

from mtools.errors import ConfigError
from tests.fmu.helpers import (capture_request, edited_fmu, reference_fmu,
                               remove_element, set_attribute, simulate_given)


@pytest.mark.parametrize("solver", ["dassl", "ida", "rungekutta"])
def test_other_me_solvers_are_config_errors(solver):
    with pytest.raises(ConfigError) as error:
        simulate_given(reference_fmu("Dahlquist"), solver=solver)
    assert (
        f"settings.solver: Model Exchange FMU runs support 'cvode' and 'euler', got '{solver}'"
        in error.value.diagnostics
    )


def test_euler_runs_once_per_interval(monkeypatch):
    request = capture_request(monkeypatch, reference_fmu("Dahlquist"), solver="euler", interval=0.5)
    assert request.solver == "Euler" and request.interval == 0.5


def test_co_simulation_solver_warns(caplog):
    simulate_given(reference_fmu("Dahlquist"), fmu_type="cs", solver="cvode")
    assert (
        "Co-Simulation FMU 'Dahlquist' runs its built-in solver; settings.solver 'cvode' is ignored" in caplog.text
    )


def test_interval_that_misses_stop_time_is_rejected_without_variable_step(tmp_path):
    fmu = edited_fmu(
        reference_fmu("Dahlquist"),
        tmp_path,
        set_attribute("CoSimulation", "canHandleVariableCommunicationStepSize", "false"),
    )
    with pytest.raises(ConfigError) as error:
        simulate_given(fmu, fmu_type="cs", stop_time=1.0, interval=0.3)
    assert (
        "settings.interval: 0.3 doesn't divide the run's 1 s and 'Dahlquist' can't change its communication step size"
        in error.value.diagnostics
    )


def test_dividing_interval_is_accepted_without_variable_step(tmp_path):
    fmu = edited_fmu(
        reference_fmu("Dahlquist"),
        tmp_path,
        set_attribute("CoSimulation", "canHandleVariableCommunicationStepSize", "false"),
    )
    assert len(simulate_given(fmu, fmu_type="cs", stop_time=1.0, interval=0.25)["Dahlquist"]) == 5


def test_variable_filter_full_match_keeps_time():
    result = simulate_given(reference_fmu("BouncingBall"), variable_filter="h|v")["BouncingBall"]
    assert list(result.columns) == ["time", "h", "v"]


@pytest.mark.parametrize("fmu_type", ["me", "cs"])
def test_tolerance_goes_to_both_fmu_types(monkeypatch, caplog, fmu_type):
    request = capture_request(monkeypatch, reference_fmu("Dahlquist"), fmu_type=fmu_type, tolerance=1e-8)
    assert request.tolerance == 1e-8
    assert "tolerance" not in caplog.text


def test_all_step4_problems_come_in_one_error(tmp_path):
    fmu = edited_fmu(reference_fmu("Dahlquist"), tmp_path, remove_element("ModelExchange"))
    with pytest.raises(ConfigError, match="Invalid run settings for 'Dahlquist'") as error:
        simulate_given(fmu, fmu_type="me", solver="dassl")
    assert error.value.diagnostics.splitlines() == [
        "build.fmu_type: 'Dahlquist' has no Model Exchange interface",
        "settings.solver: Model Exchange FMU runs support 'cvode' and 'euler', got 'dassl'",
    ]


def test_invalid_variable_filter_is_a_config_error():
    with pytest.raises(ConfigError) as error:
        simulate_given(reference_fmu("Dahlquist"), variable_filter="(")
    assert "settings.variable_filter: invalid regular expression '(': missing ), unterminated subpattern at position 0" in (
        error.value.diagnostics
    )


@pytest.mark.parametrize("fmu_type", ["me", "cs"])
@pytest.mark.parametrize("interval", [0.0, -0.5])
def test_non_positive_interval_is_a_config_error(fmu_type, interval):
    with pytest.raises(ConfigError) as error:
        simulate_given(reference_fmu("Dahlquist"), fmu_type=fmu_type, interval=interval)
    assert f"settings.interval: expected a positive number, got {interval}" in error.value.diagnostics
