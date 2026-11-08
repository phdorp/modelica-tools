"""The Cpp target at the backend interface: what differs from C, against real OMC.

Behaviour shared with C runs on both targets in the other test modules.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pytest

from mtools.errors import ConfigError, SimulationError
from mtools.internal.omc import run_cpp
from mtools.internal.omc.build import Build, build
from mtools.internal.omc.config import BuildConfig, RunSettings
from mtools.internal.omc.run_cpp import error_lines, validate_settings

DECAY = (
    "model Decay\n  parameter Real k = 1;\n  Real x(start = 1, fixed = true);\n  Real y(start = 0, fixed = true);\n"
    "equation\n  der(x) = -k * x;\n  der(y) = x - y;\n"
    "  annotation(experiment(StartTime = 0, StopTime = 3, Interval = 0.25, Tolerance = 1e-10));\nend Decay;\n"
)
EULER_ANNOTATION = DECAY.replace(
    "annotation(", 'annotation(__OpenModelica_simulationFlags(s = "euler"), '
)
FAILS = (
    "model Fails\n  Real x(start = 0, fixed = true);\nequation\n  der(x) = 1;\n"
    '  assert(x < 0.5, "x exceeded its limit");\nend Fails;\n'
)


def _build(tmp_path: Path, name: str, source: str) -> Build:
    path = tmp_path / f"{name}.mo"
    path.write_text(source)
    return build(BuildConfig(model_path=path, model_name=name, target="Cpp"))


def _config(tmp_path: Path, target="Cpp") -> BuildConfig:
    return BuildConfig(model_path=tmp_path / "Decay.mo", model_name="Decay", target=target)


@pytest.fixture(scope="module")
def decay(tmp_path_factory: pytest.TempPathFactory) -> Build:
    return _build(tmp_path_factory.mktemp("decay"), "Decay", DECAY)


def test_annotation_values_apply_and_nothing_falls_back_to_cpp_defaults(decay: Build):
    result = decay.simulate(RunSettings(solver="cvode"))

    assert result["time"].iloc[0] == 0.0
    assert result["time"].iloc[-1] == pytest.approx(3.0)
    assert sorted(set(result["time"].round(9)))[:3] == pytest.approx([0.0, 0.25, 0.5])
    assert result["x"].iloc[-1] == pytest.approx(np.exp(-3.0), rel=1e-6)


def test_start_time_drops_the_rows_cpp_writes_before_it(decay: Build):
    result = decay.simulate(RunSettings(solver="ida", start_time=1.0, stop_time=2.0, interval=0.5))

    assert result["time"].min() == 1.0
    assert sorted(set(result["time"])) == pytest.approx([1.0, 1.5, 2.0])
    assert (result["x"] > 0).all() and (result["x"] <= 1.0).all()


@pytest.mark.parametrize("solver", ["euler", "rungekutta", "nosuch"])
def test_explicit_unsupported_solver_is_rejected_before_building(tmp_path: Path, solver: str):
    with pytest.raises(ConfigError, match=f"settings.solver.*not '{solver}'") as raised:
        validate_settings(_config(tmp_path), RunSettings(solver=solver))

    assert raised.value.model_name == "Decay"


@pytest.mark.parametrize("solver", [None, "dassl", "cvode", "ida"])
def test_supported_or_unset_solvers_pass_validation(tmp_path: Path, solver: str | None):
    validate_settings(_config(tmp_path), RunSettings(solver=solver))


def test_validation_has_no_opinion_on_c(tmp_path: Path):
    validate_settings(_config(tmp_path, "C"), RunSettings(solver="euler"))


def test_unsupported_solver_from_the_annotation_is_rejected_before_the_run(tmp_path: Path, monkeypatch):
    built = _build(tmp_path, "Decay", EULER_ANNOTATION)
    assert built.experiment.solver == "euler"
    executed: list[object] = []
    monkeypatch.setattr("mtools.internal.omc.run.execute", lambda *args: executed.append(args))

    with pytest.raises(ConfigError, match="__OpenModelica_simulationFlags.*not 'euler'") as raised:
        built.simulate(RunSettings())

    assert raised.value.model_name == "Decay"
    assert not executed


def test_a_supported_solver_setting_replaces_the_unsupported_annotation_solver(tmp_path: Path):
    built = _build(tmp_path, "Decay", EULER_ANNOTATION)

    result = built.simulate(RunSettings(solver="cvode"))

    assert result["x"].iloc[-1] == pytest.approx(np.exp(-3.0), rel=1e-6)


def test_dassl_with_an_interval_warns_that_the_grid_is_ignored(decay: Build, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.INFO):
        decay.simulate(RunSettings(solver="dassl", interval=0.5))

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert "dassl" in warnings[0] and "ignores the output interval" in warnings[0]


@pytest.mark.parametrize("settings", [RunSettings(solver="cvode", interval=0.5), RunSettings(solver="dassl")])
def test_no_grid_warning_when_the_grid_is_honoured_or_unset(decay: Build, caplog, settings: RunSettings):
    with caplog.at_level(logging.INFO):
        decay.simulate(settings)

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("abort", [True, False])
def test_abort_on_chattering_has_no_effect_and_is_not_an_error(decay: Build, abort: bool):
    result = decay.simulate(RunSettings(solver="cvode", abort_on_chattering=abort))

    assert result["x"].iloc[-1] == pytest.approx(np.exp(-3.0), rel=1e-6)


def test_run_failure_lists_each_error_line_once_despite_the_kinsol_retry(tmp_path: Path, caplog):
    built = _build(tmp_path, "Fails", FAILS)

    with caplog.at_level(logging.INFO), pytest.raises(SimulationError) as raised:
        built.simulate(RunSettings(solver="cvode"))

    lines = str(raised.value).splitlines()
    assert lines[0] == "Simulation of 'Fails' failed:"
    assert any("x exceeded its limit" in line for line in lines)
    assert all(line.startswith("ERROR") for line in lines[1:])
    assert len(lines) == len(set(lines))
    assert "Recovering with nonlinear solver kinsol" in str(raised.value)


def test_crash_names_its_signal_in_the_header(tmp_path: Path, monkeypatch):
    built = _build(tmp_path, "Decay", DECAY)
    # Cpp's fixed-step solvers segfault; mtools rejects them, so lift the rule for this test.
    monkeypatch.setattr(run_cpp, "CPP_SOLVERS", ("dassl", "cvode", "ida", "euler"))

    with pytest.raises(SimulationError) as raised:
        built.simulate(RunSettings(solver="euler"))

    assert str(raised.value).startswith("Simulation of 'Decay' crashed with SIGSEGV:")


def test_error_lines_are_distinct_in_order_and_ignore_other_output():
    output = (
        "some stdout\nERROR  : solver: A\nWARNING: not an error\nERROR  : solver: B\n"
        "ERROR  : solver: A\nERROR  : solver: B\n"
    )

    assert error_lines(output) == ["ERROR  : solver: A", "ERROR  : solver: B"]


@pytest.mark.parametrize("solver", ["ida", "cvode"])
def test_c_and_cpp_results_agree_closely(tmp_path: Path, solver: str):
    path = tmp_path / "Decay.mo"
    path.write_text(DECAY)
    settings = RunSettings(solver=solver, parameters={"k": 2.0})

    results = {
        target: build(BuildConfig(model_path=path, model_name="Decay", target=target))  # type: ignore[arg-type]
        .simulate(settings)
        .drop_duplicates("time", ignore_index=True)
        for target in ("C", "Cpp")
    }

    assert list(results["C"].columns) == list(results["Cpp"].columns)
    np.testing.assert_allclose(results["Cpp"].to_numpy(), results["C"].to_numpy(), rtol=1e-7, atol=1e-9)
