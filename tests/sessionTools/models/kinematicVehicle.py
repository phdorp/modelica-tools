import dataclasses
from pathlib import Path

import hydra_zen

from sessionTools.sessionBuilder import Director


@dataclasses.dataclass
class State:
    px: float = 0.0
    py: float = 0.0
    theta: float = 0.0


@dataclasses.dataclass
class KinematicVehicle:
    state_0: State
    v_norm: float = 10.0
    phi: float = 0.0
    l: float = 2.0


@hydra_zen.hydrated_dataclass(Director, populate_full_signature=True)
class Simulation:
    parameters: KinematicVehicle
    model = Path("tests/sessionTools/models/kinematicVehicle.mo").resolve()


simConfig = Simulation(parameters=KinematicVehicle(state_0=State()))
