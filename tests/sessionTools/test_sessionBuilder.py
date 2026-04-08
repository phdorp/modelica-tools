import sys
sys.path.append("..")

import hydra_zen
from omegaconf import OmegaConf

from sessionTools.sessionBuilder import Director, flatten_nested_dict
from models.kinematicVehicle import simConfig, Simulation


def simulate(simConfig: Simulation):
    director: Director = hydra_zen.instantiate(simConfig)
    session = director.make_session()
    session.simulate()
    return session.get_solutions()


class TestSessionBuilder:

    def test_simulation_default(self):
        job_return = hydra_zen.launch(simConfig, simulate)

        parameters = flatten_nested_dict(OmegaConf.structured(simConfig.parameters))
        solution = job_return.return_value["KinematicVehicle"]
        assert solution["state.px"][0] == parameters["state_0.px"]
        assert solution["state.py"][0] == parameters["state_0.py"]
        assert solution["state.theta"][0] == parameters["state_0.theta"]
        assert solution["time"].values[-1] * parameters["v_norm"] + parameters["state_0.px"] == solution["state.px"].values[-1]

    def test_simulation_override(self):
        job_return = hydra_zen.launch(simConfig, simulate, overrides=["++parameters.state_0.px=5.0", "++parameters.v_norm=20.0"])

        assert job_return.cfg is not None
        parameters = flatten_nested_dict(OmegaConf.structured(job_return.cfg.parameters))

        solution = job_return.return_value["KinematicVehicle"]
        assert solution["state.px"][0] == parameters["state_0.px"]
        assert solution["state.py"][0] == parameters["state_0.py"]
        assert solution["state.theta"][0] == parameters["state_0.theta"]
        assert solution["time"].values[-1] * parameters["v_norm"] + parameters["state_0.px"] == solution["state.px"].values[-1]

