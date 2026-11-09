"""``sim_tools.simulate`` validates a run config once, before building, naming the config path."""

import dataclasses
import logging

import hydra_zen
import pytest
from models.kinematic_vehicle import (MODEL_PATH, build_default, run_default,
                                      settings_default)
from omegaconf import OmegaConf

from mtools.errors import ConfigError
from mtools.session_config import Library, SimulationRun
from mtools.sim_tools import simulate


def _run(build_changes=None, settings_changes=None) -> SimulationRun:
    return SimulationRun(
        build=dataclasses.replace(build_default, **(build_changes or {})),
        settings=dataclasses.replace(settings_default, **(settings_changes or {})),
    )


def _built(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(("Built", "Reused"))]


@pytest.mark.parametrize(
    ("build_changes", "settings_changes", "path"),
    [
        pytest.param({"omc_flags": {"--simCodeTarget": "Cpp"}}, {}, "build.omc_flags", id="simCodeTarget"),
        pytest.param({"omc_flags": {"+simCodeTarget": "C"}}, {}, "build.omc_flags", id="simCodeTarget-plus"),
        pytest.param({"target": "Java"}, {}, "build.target", id="target"),
        pytest.param({"model_path": MODEL_PATH.with_name("missing.mo")}, {}, "build.model_path", id="model_path"),
        pytest.param({"model_name": ""}, {}, "build.model_name", id="model_name"),
        pytest.param(
            {"extra_sources": [MODEL_PATH.with_name("missing.mo")]}, {}, "build.extra_sources[0]", id="extra_sources"
        ),
        pytest.param(
            {"libraries": [Library("Lib", directory=MODEL_PATH.with_name("missing"))]},
            {},
            "build.libraries[0].directory",
            id="library_directory",
        ),
        pytest.param({}, {"stop_time": "abc"}, "settings.stop_time", id="stop_time"),
        pytest.param({}, {"tolerance": True}, "settings.tolerance", id="tolerance-bool"),
        pytest.param({}, {"emit_protected": "yes"}, "settings.emit_protected", id="emit_protected"),
        pytest.param({}, {"variable_filter": 1}, "settings.variable_filter", id="variable_filter"),
        pytest.param({}, {"parameters": 3}, "settings.parameters", id="parameters"),
        pytest.param({"target": "Cpp"}, {"solver": "euler"}, "settings.solver", id="cpp-solver"),
    ],
)
def test_invalid_config_fails_before_building_and_names_the_path(build_changes, settings_changes, path, caplog):
    with caplog.at_level(logging.INFO), pytest.raises(ConfigError) as exc:
        simulate(_run(build_changes, settings_changes))

    assert f"{path}:" in exc.value.diagnostics
    assert exc.value.model_name == (build_changes.get("model_name", "KinematicVehicle"))
    assert isinstance(exc.value, ValueError)
    assert _built(caplog) == []


def test_every_invalid_value_is_reported_at_once():
    with pytest.raises(ConfigError) as exc:
        simulate(_run({"target": "Java"}, {"stop_time": "abc"}))

    assert "build.target:" in exc.value.diagnostics
    assert "settings.stop_time:" in exc.value.diagnostics


def test_the_simcodetarget_error_points_at_build_target():
    with pytest.raises(ConfigError, match="build.target"):
        simulate(_run({"omc_flags": {"--simCodeTarget": "Cpp"}}))


def test_invalid_target_from_a_hydra_override_is_a_config_error():
    config = hydra_zen.launch(run_default, lambda cfg: cfg, ["build.target=Java"], version_base=None).cfg
    with pytest.raises(ConfigError, match="build.target"):
        simulate(config)


def test_missing_parameters_are_a_config_error():
    config = OmegaConf.structured(run_default)
    config.settings.parameters = "???"
    with pytest.raises(ConfigError, match="settings.parameters"):
        simulate(config)


def test_unknown_parameter_name_is_a_config_error_naming_its_path():
    with pytest.raises(ConfigError, match=r"settings\.parameters\.bogus"):
        simulate(_run(settings_changes={"parameters": {"bogus": 1.0}}))


def test_an_unknown_output_format_fails_before_building(caplog):
    run = SimulationRun(build=build_default, settings=settings_default, output_format="json")  # type: ignore[arg-type]

    with caplog.at_level(logging.INFO), pytest.raises(ConfigError) as exc:
        simulate(run)

    assert "output_format: expected one of 'mat', 'csv', got 'json'" in exc.value.diagnostics
    assert _built(caplog) == []


def test_output_format_defaults_to_mat_and_is_overridable():
    assert hydra_zen.launch(run_default, lambda cfg: cfg, [], version_base=None).cfg.output_format == "mat"
    config = hydra_zen.launch(run_default, lambda cfg: cfg, ["output_format=csv"], version_base=None).cfg
    assert config.output_format == "csv"
