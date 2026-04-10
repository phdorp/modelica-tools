from typing import List

import hydra_zen
import numpy as np
import pytest
from _pytest.fixtures import SubRequest
from models.kinematicVehicle import Simulation, sim_config
from omegaconf import OmegaConf
from omegaconf.dictconfig import DictConfig

from sessionTools import SessionDirector, flatten_nested_dict


def simulate(sim_config: Simulation):
    director: SessionDirector = hydra_zen.instantiate(sim_config)
    session = director.make_session()
    session.simulate()
    return session.get_solutions()


NO_OVERRIDE: List[str] = []
OVERRIDE: List[str] = [
    "parameters.state_0.px=5.0",
    "parameters.v_norm=20.0",
    "model_configurations.KinematicVehicle.time_range.stop_time=20.0",
]


class TestSessionBuilder:
    @pytest.fixture(params=[NO_OVERRIDE, OVERRIDE])
    def job_return(self, request: SubRequest, tmp_path):
        overrides: List[str] = request.param
        extra_overrides = [f"hydra.run.dir={tmp_path}", "hydra.job.chdir=False"]
        return hydra_zen.launch(
            sim_config,
            simulate,
            overrides + extra_overrides,
            with_log_configuration=False,
        )

    def test_simulation(self, job_return):
        configuration: DictConfig = job_return.cfg
        parameters = flatten_nested_dict(OmegaConf.structured(configuration.parameters))

        solution = job_return.return_value["KinematicVehicle"]
        assert solution["state.px"][0] == parameters["state_0.px"]
        assert solution["state.py"][0] == parameters["state_0.py"]
        assert solution["state.theta"][0] == parameters["state_0.theta"]
        assert np.allclose(
            solution["time"].values[-1] * parameters["v_norm"] + parameters["state_0.px"],
            solution["state.px"].values[-1],
        )
        assert (
            solution["time"].values[-1]
            == configuration.model_configurations["KinematicVehicle"].time_range["stop_time"]
        )
