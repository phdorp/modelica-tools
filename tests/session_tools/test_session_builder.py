"""``sim_tools.simulate`` through Hydra configs: override paths, result keys and run settings."""

from typing import List

import hydra_zen
import numpy as np
import pytest
from _pytest.fixtures import SubRequest
from models.kinematic_vehicle import run_default
from omegaconf import DictConfig

from mtools.sim_tools import simulate

NO_OVERRIDE: List[str] = []
OVERRIDE: List[str] = [
    "settings.parameters.state_0.px=5.0",
    "settings.parameters.v_norm=20.0",
    "settings.stop_time=20.0",
]


def _launch(tmp_path, overrides: List[str]):
    return hydra_zen.launch(
        run_default,
        simulate,
        [*overrides, f"hydra.run.dir={tmp_path}", "hydra.job.chdir=False"],
        with_log_configuration=False,
        version_base=None,
    )


class TestSimulate:
    @pytest.fixture(params=[NO_OVERRIDE, OVERRIDE])
    def job_return(self, request: SubRequest, tmp_path):
        return _launch(tmp_path, request.param)

    def test_results_are_keyed_by_the_build_model_name(self, job_return):
        assert list(job_return.return_value) == ["KinematicVehicle"]

    def test_parameters_and_settings_take_effect(self, job_return):
        configuration: DictConfig = job_return.cfg
        parameters = configuration.settings.parameters

        solution = job_return.return_value["KinematicVehicle"]
        assert solution["state.px"][0] == parameters.state_0.px
        assert solution["state.py"][0] == parameters.state_0.py
        assert solution["state.theta"][0] == parameters.state_0.theta
        assert np.allclose(
            solution["time"].values[-1] * parameters.v_norm + parameters.state_0.px,
            solution["state.px"].values[-1],
        )
        assert solution["time"].values[-1] == configuration.settings.stop_time

    def test_protected_variables_hidden_by_default(self, tmp_path):
        solution = _launch(tmp_path, []).return_value["KinematicVehicle"]
        for column in ("px_dot", "py_dot", "theta_dot"):
            assert column not in solution.columns

    def test_protected_variables_emitted_when_enabled(self, tmp_path):
        solution = _launch(tmp_path, ["settings.emit_protected=true"]).return_value["KinematicVehicle"]
        for column in ("px_dot", "py_dot", "theta_dot"):
            assert column in solution.columns
        assert np.allclose(solution["px_dot"], solution["der(state.px)"])

    def test_unset_settings_come_from_the_experiment_annotation(self, tmp_path):
        # The fixture model has no experiment annotation, so OMC's defaults apply: 0 to 1 s.
        solution = _launch(tmp_path, ["settings.stop_time=null"]).return_value["KinematicVehicle"]
        assert solution["time"].values[0] == 0.0
        assert solution["time"].values[-1] == 1.0

    def test_variable_filter_selects_columns_and_keeps_time(self, tmp_path):
        solution = _launch(tmp_path, ["settings.variable_filter=state\\.px"]).return_value["KinematicVehicle"]
        assert list(solution.columns) == ["time", "state.px"]
