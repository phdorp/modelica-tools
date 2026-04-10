import hydra_zen
import numpy as np
from models.kinematicVehicle import Simulation, simConfig
from omegaconf import OmegaConf
from omegaconf.dictconfig import DictConfig
import pytest
from _pytest.fixtures import SubRequest
from typing import List

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
    def job_return(self, request: SubRequest):
        overrides: List[str] = request.param
        return hydra_zen.launch(simConfig, simulate, overrides)

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
