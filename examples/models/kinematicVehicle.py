import dataclasses
from pathlib import Path

import hydra_zen

from sessionTools import SessionDirector


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


@hydra_zen.hydrated_dataclass(SessionDirector, populate_full_signature=True)
class Simulation:
    parameters: KinematicVehicle
    model = Path("examples/models/kinematicVehicle.mo").resolve()


simConfig = Simulation(parameters=KinematicVehicle(state_0=State()))
