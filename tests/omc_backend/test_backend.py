"""Integration tests at the backend interface, `build()` and `Build.simulate()`, against real OMC."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

from mtools.errors import (CompileError, ConfigError, SimulationError,
                           TranslationError)
from mtools.internal.omc.build import Build, build
from mtools.internal.omc.config import BuildConfig, RunSettings
from mtools.internal.omc.script import Experiment, LoadedLibrary

MODELS = Path(__file__).parent / "models"


@pytest.fixture(scope="module")
def backend_build() -> Build:
    return build(BuildConfig(model_path=MODELS / "Backend.mo", model_name="Backend"))


def test_result_has_time_first_and_one_column_per_public_time_varying_variable(backend_build: Build):
    result = backend_build.simulate(RunSettings())

    assert result.columns[0] == "time"
    assert set(result.columns) == {
        "time",
        "x",
        "der(x)",
        "negx",
        "v[1]",
        "v[2]",
        "g",
        "mm",
        "s",
        "count",
        "late",
        "mode",
    }


def test_build_records_the_experiment_annotation(backend_build: Build):
    assert backend_build.experiment == Experiment(
        start_time=0.0, stop_time=1.0, interval=0.1, tolerance=1e-8, solver="dassl"
    )


def test_unset_time_range_and_interval_come_from_the_annotation(backend_build: Build):
    result = backend_build.simulate(RunSettings())

    grid = sorted(set(result["time"].round(12)))
    assert grid == pytest.approx([0.0, 0.1, 0.2, 0.25, 0.3, 0.4, 0.5, 0.55, 0.6, 0.7, 0.8, 0.9, 1.0])


def test_time_range_and_interval_settings_override_the_annotation(backend_build: Build):
    result = backend_build.simulate(RunSettings(start_time=0.5, stop_time=2.0, interval=0.5))

    assert sorted(set(result["time"])) == pytest.approx([0.5, 0.55, 1.0, 1.5, 2.0])


def test_solver_setting_selects_the_integration_method(backend_build: Build):
    exact = math.exp(-2.0)

    dassl = backend_build.simulate(RunSettings())
    euler = backend_build.simulate(RunSettings(solver="euler"))

    assert dassl["x"].iloc[-1] == pytest.approx(exact, rel=1e-6)
    assert euler["x"].iloc[-1] == pytest.approx(0.8**10, rel=0.05)


def test_tolerance_setting_controls_the_solver_error(backend_build: Build):
    loose = backend_build.simulate(RunSettings(tolerance=1e-2))

    assert abs(loose["x"].iloc[-1] - math.exp(-2.0)) > 1e-4


def test_columns_keep_their_modelica_types(backend_build: Build):
    result = backend_build.simulate(RunSettings())

    assert result["x"].dtype == np.dtype("float64")
    assert result["count"].dtype == np.dtype("int64")
    assert result["mode"].dtype == np.dtype("int64")
    assert result["late"].dtype == np.dtype("bool")
    assert result["late"].iloc[-1]
    assert result["mode"].iloc[-1] == 2  # Mode.high


def test_negated_alias_is_resolved(backend_build: Build):
    result = backend_build.simulate(RunSettings())

    assert (result["negx"] == -result["x"]).all()


def test_repeated_event_rows_are_kept(backend_build: Build):
    result = backend_build.simulate(RunSettings())

    event_rows = result[(result["time"] - 0.25).abs() < 1e-6]
    assert len(event_rows) == 2
    assert event_rows["count"].tolist() == [0, 1]


@dataclass
class SubParameters:
    gain: float = 1.0


@dataclass
class BackendParameters:
    k: float = 2.0
    y0: list[float] = field(default_factory=lambda: [1.0, 2.0])
    m: list[list[float]] = field(default_factory=lambda: [[1.0, 2.0], [3.0, 4.0]])
    flip: bool = False
    offset: int = 0
    sub: SubParameters = field(default_factory=SubParameters)


def test_parameters_from_a_nested_dataclass_take_effect(backend_build: Build):
    parameters = BackendParameters(
        k=1 / 3, y0=[5.0, 6.0], m=[[1.0, 7.0], [3.0, 4.0]], flip=True, offset=2, sub=SubParameters(gain=5.0)
    )

    result = backend_build.simulate(RunSettings(parameters=parameters))

    end = result.iloc[-1]
    assert result["der(x)"].iloc[0] == -(1 / 3)  # full precision
    assert end["v[1]"] == pytest.approx(5.0) and end["v[2]"] == pytest.approx(6.0)
    assert end["mm"] == pytest.approx(7.0)
    assert end["s"] == pytest.approx(-1.0)
    assert end["count"] == 3
    assert end["g"] == pytest.approx(5.0)


def test_parameters_from_a_mapping_take_effect(backend_build: Build):
    result = backend_build.simulate(RunSettings(parameters={"k": 3.0, "sub": {"gain": 4.0}}))

    assert result["x"].iloc[-1] == pytest.approx(math.exp(-3.0), rel=1e-6)
    assert result["g"].iloc[-1] == pytest.approx(4.0)


@pytest.mark.parametrize(
    ("parameters", "config_path"),
    [
        ({"nope": 1.0}, "settings.parameters.nope"),
        ({"sub": {"nope": 1.0}}, "settings.parameters.sub.nope"),
        ({"y0": [1.0, 2.0, 3.0]}, "settings.parameters.y0"),
    ],
    ids=["top-level", "nested", "array-too-long"],
)
def test_unknown_parameter_raises_config_error_naming_its_config_path(backend_build: Build, parameters, config_path):
    with pytest.raises(ConfigError, match=re.escape(config_path)) as raised:
        backend_build.simulate(RunSettings(parameters=parameters))

    assert raised.value.model_name == "Backend"


def test_variable_filter_selects_columns_and_keeps_time(backend_build: Build):
    result = backend_build.simulate(RunSettings(variable_filter=r"x|v\[[0-9]\]"))

    assert set(result.columns) == {"time", "x", "v[1]", "v[2]"}


def test_protected_variables_are_hidden_by_default_and_emitted_on_request(backend_build: Build):
    hidden = backend_build.simulate(RunSettings())
    emitted = backend_build.simulate(RunSettings(emit_protected=True))

    assert "hidden" not in hidden.columns
    assert (emitted["hidden"] == 2 * emitted["x"]).all()


def test_build_records_its_parameter_list(backend_build: Build):
    parameters = backend_build.parameters

    assert {name: parameters[name].type for name in ("k", "offset", "flip", "m[1,2]", "sub.gain")} == {
        "k": "Real",
        "offset": "Integer",
        "flip": "Boolean",
        "m[1,2]": "Real",
        "sub.gain": "Real",
    }
    assert parameters["k"].changeable
    assert not parameters["twice"].changeable
    assert "der(x)" not in parameters


def _snapshot(directory: Path) -> dict[str, tuple[int, int]]:
    return {
        str(path.relative_to(directory)): (path.stat().st_size, path.stat().st_mtime_ns)
        for path in directory.rglob("*")
    }


def test_runs_write_nothing_into_the_build(backend_build: Build):
    before = _snapshot(backend_build.directory)

    backend_build.simulate(RunSettings(parameters={"k": 3.0}, emit_protected=True))

    assert _snapshot(backend_build.directory) == before


def test_syntax_error_raises_translation_error(tmp_path: Path):
    source = tmp_path / "Broken.mo"
    source.write_text("model Broken\n  Real x\nequation\n  x = 1;\nend Broken;\n")

    with pytest.raises(TranslationError, match="Missing token") as raised:
        build(BuildConfig(model_path=source, model_name="Broken"))

    assert raised.value.model_name == "Broken"
    assert str(raised.value).startswith(f"Modelica translation failed for 'Broken' ({source}):")


def test_translation_failure_raises_translation_error(tmp_path: Path):
    source = tmp_path / "TypeMismatch.mo"
    source.write_text("model TypeMismatch\n  Integer t = 1.5;\nend TypeMismatch;\n")

    with pytest.raises(TranslationError, match="Type mismatch in binding t = 1.5"):
        build(BuildConfig(model_path=source, model_name="TypeMismatch"))


def test_c_compile_failure_raises_compile_error(tmp_path: Path):
    source = tmp_path / "CBuild.mo"
    source.write_text(
        "model CBuild\n  function f\n    input Real x;\n    output Real y;\n"
        '    external "C" y = missingF(x) annotation(Include="#include \\"no_such_header.h\\"");\n'
        "  end f;\n  Real v = f(time);\nend CBuild;\n"
    )

    with pytest.raises(CompileError, match="no_such_header.h") as raised:
        build(BuildConfig(model_path=source, model_name="CBuild"))

    assert raised.value.model_name == "CBuild"


def test_failed_run_raises_simulation_error(tmp_path: Path):
    source = tmp_path / "Fails.mo"
    source.write_text(
        "model Fails\n  Real x(start = 0, fixed = true);\nequation\n  der(x) = 1;\n"
        '  assert(x < 0.5, "x exceeded its limit");\nend Fails;\n'
    )
    failing = build(BuildConfig(model_path=source, model_name="Fails"))

    with pytest.raises(SimulationError, match="x exceeded its limit") as raised:
        failing.simulate(RunSettings())

    assert str(raised.value).startswith("Simulation of 'Fails' failed:")


def test_backend_logs_under_module_named_loggers_and_attaches_no_handlers(
    backend_build: Build, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.DEBUG, logger="mtools"):
        backend_build.simulate(RunSettings())

    assert caplog.records
    assert all(record.name.startswith("mtools.internal.omc.") for record in caplog.records)
    mtools_loggers = [name for name in logging.root.manager.loggerDict if name.split(".")[0] == "mtools"]
    assert not any(logging.getLogger(name).handlers for name in mtools_loggers)


def test_build_records_the_loaded_libraries(backend_build: Build):
    assert LoadedLibrary("Backend", MODELS) in backend_build.loaded_libraries
