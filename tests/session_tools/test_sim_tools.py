import pandas as pd
import pytest

import mtools.internal.sim_tools as internal_sim_tools
import mtools.sim_tools as sim_tools


def test_simulate_multirun_fans_out_over_phi(tmp_path, monkeypatch):
    captured: dict = {}

    class FakeJob:
        def __init__(self, phi):
            self.cfg = {"session": {"parameters": {"phi": phi}}}
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
        overrides=["session.parameters.phi=0.0017,0.0087"],
        multirun=True,
        sweep_dir=str(tmp_path),
    )

    assert captured["multirun"] is True
    assert "session.parameters.phi=0.0017,0.0087" in captured["overrides"]
    assert [r.config["session"]["parameters"]["phi"] for r in results] == [0.0017, 0.0087]
    assert list(results[0].solutions.keys()) == ["model"]


def test_normalize_solution_match():
    solutions = {"kinematic_vehicle_KinematicVehicle": pd.DataFrame({"time": [0.0, 1.0]})}

    normalized = internal_sim_tools._normalize_solution_keys(solutions, model_name="kinematic_vehicle.KinematicVehicle")

    assert list(normalized.keys()) == ["kinematic_vehicle.KinematicVehicle"]
    assert normalized["kinematic_vehicle.KinematicVehicle"].equals(solutions["kinematic_vehicle_KinematicVehicle"])


def test_normalize_solution_no_match():
    solutions = {"backend_generated_result": pd.DataFrame({"time": [0.0, 1.0]})}

    with pytest.raises(ValueError, match="No solution matches the requested model"):
        internal_sim_tools._normalize_solution_keys(solutions, model_name="some.package.ModelName")
