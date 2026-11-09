import dataclasses
import logging

import hydra_zen
import pandas as pd
import pytest
from models.kinematic_vehicle import (build_default, run_default,
                                      settings_default)
from omegaconf import OmegaConf

import mtools.internal.sim_tools as internal_sim_tools
import mtools.sim_tools as sim_tools
from mtools.errors import SimulationError, TranslationError
from mtools.internal.omc.workdir import NO_CACHE_VARIABLE, WORK_DIR_VARIABLE
from mtools.session_config import Build, RunSettings, SimulationRun


def test_simulate_multirun_fans_out_over_phi(tmp_path, monkeypatch):
    captured: dict = {}

    class FakeJob:
        def __init__(self, phi):
            self.cfg = {"settings": {"parameters": {"phi": phi}}}
            self.return_value = {"model": pd.DataFrame({"phi": [phi]})}

    def fake_launch(run_cfg, task, overrides, multirun, version_base):
        captured["overrides"] = list(overrides)
        captured["multirun"] = multirun
        assert run_cfg is fake_run_config
        return [[FakeJob(0.0017), FakeJob(0.0087)]]

    monkeypatch.setattr("hydra_zen.launch", fake_launch)

    fake_run_config = object()

    results = sim_tools.simulate(
        fake_run_config,  # type: ignore[arg-type]
        overrides=["settings.parameters.phi=0.0017,0.0087"],
        multirun=True,
        sweep_dir=str(tmp_path),
    )

    assert captured["multirun"] is True
    assert "settings.parameters.phi=0.0017,0.0087" in captured["overrides"]
    assert [r.config["settings"]["parameters"]["phi"] for r in results] == [0.0017, 0.0087]
    assert list(results[0].solutions.keys()) == ["model"]


def test_multirun_sweep_runs_each_point_on_the_backend(tmp_path):
    results = sim_tools.simulate(
        run_default,
        overrides=["settings.parameters.v_norm=1.0,2.0", "build.target=C"],
        multirun=True,
        sweep_dir=str(tmp_path),
    )

    by_speed = {r.config.settings.parameters.v_norm: r.solutions["KinematicVehicle"] for r in results}
    assert sorted(by_speed) == [1.0, 2.0]
    for speed, solution in by_speed.items():
        assert solution["state.px"].iloc[-1] == pytest.approx(speed * solution["time"].iloc[-1])


@dataclasses.dataclass
class _NoParameters:
    pass


def test_broken_package_through_hydra_reports_diagnostics_once_and_readably(tmp_path, caplog, capsys):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "package.mo").write_text("package pkg\nend pkg;\n")
    (package / "M.mo").write_text("within pkg;\nmodel M\n  Real x(start=1)\nequation\n  der(x) = -x;\nend M;\n")
    config = OmegaConf.structured(
        SimulationRun(
            build=Build(model_path=package / "M.mo", model_name="pkg.M"),
            settings=RunSettings(parameters=_NoParameters()),
        )
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(TranslationError) as exc:
        internal_sim_tools.simulate_run(config)

    message = str(exc.value)
    assert message.count("Missing token: SEMICOLON") == 1
    assert "\\n" not in message
    assert f"Modelica translation failed for 'pkg.M' ({package / 'M.mo'}):\n[" in message
    assert "Failed to load package" not in message
    assert repr(exc.value) == message
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert capsys.readouterr().out == ""


@pytest.fixture
def private_work_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(WORK_DIR_VARIABLE, str(tmp_path / "work"))
    monkeypatch.setenv(NO_CACHE_VARIABLE, "1")
    return tmp_path / "work"


def _leftovers(work_dir):
    return sorted(path.relative_to(work_dir) for path in work_dir.rglob("*"))


def test_uncached_builds_and_runs_are_deleted_after_a_successful_run(private_work_dir):
    run = SimulationRun(build=build_default, settings=settings_default)

    assert "KinematicVehicle" in sim_tools.simulate(run)

    assert [path for path in _leftovers(private_work_dir) if len(path.parts) > 1] == []


def test_uncached_builds_and_runs_are_deleted_after_a_failed_run(private_work_dir):
    run = SimulationRun(build=build_default, settings=dataclasses.replace(settings_default, solver="no_such_solver"))

    with pytest.raises(SimulationError):
        sim_tools.simulate(run)

    assert [path for path in _leftovers(private_work_dir) if len(path.parts) > 1] == []


def test_explicit_cpp_solver_is_rejected_before_anything_is_built(private_work_dir):
    run = SimulationRun(
        build=dataclasses.replace(build_default, target="Cpp"),
        settings=dataclasses.replace(settings_default, solver="euler"),
    )

    with pytest.raises(ValueError, match=r"settings\.solver: the Cpp target runs only dassl, cvode, ida"):
        sim_tools.simulate(run)

    assert _leftovers(private_work_dir) == []
