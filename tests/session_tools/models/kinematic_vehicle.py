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


def model_default(model_name: str) -> session_config.Model:
    return session_config.Model(
        time_range=session_config.TimeRange(model_name=model_name, start_time=0.0, stop_time=10.0),
        tolerance=session_config.Tolerance(model_name=model_name, tolerance=1e-9),
        variable_filter=session_config.VariableFilter(model_name=model_name),
    )


simulation_default = session_config.Simulation(
    solver="rungekutta",
    output_format="csv",
)

session_default = session_config.Session(
    parameters=vehicle_default,
    model_configurations={"KinematicVehicle": model_default("KinematicVehicle")},
    sim_configurations=simulation_default,
    model=Path("tests/session_tools/models/kinematic_vehicle.mo").resolve(),
)

run_default = hydra_zen.make_config(
    bases=(session_config.SimulationRun,),
    hydra_defaults=["_self_"],
    model_name="KinematicVehicle",
    session=session_default,
)
