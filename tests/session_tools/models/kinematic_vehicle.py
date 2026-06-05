import dataclasses
from pathlib import Path

import hydra_zen
import pydelica

import mtools.session_config as session_config


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


vehicle_default = KinematicVehicle(state_0=State())


simulation_default = session_config.Simulation(
    solver="rungekutta",
    output_format="csv",
)

session_default = session_config.Session(
    parameters=vehicle_default,
    model_configurations={"KinematicVehicle": session_config.Model.from_parameters("KinematicVehicle")},
    sim_configurations=simulation_default,
    model=Path("tests/session_tools/models/kinematic_vehicle.mo").resolve(),
)

run_default = hydra_zen.make_config(
    bases=(session_config.SimulationRun,),
    hydra_defaults=["_self_"],
    model_name="KinematicVehicle",
    session=session_default,
)
