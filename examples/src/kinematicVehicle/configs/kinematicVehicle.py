import dataclasses
from pathlib import Path

import hydra_zen

import sessionConfig


store = hydra_zen.ZenStore()


@dataclasses.dataclass
class State:
    px: float = 0.0
    py: float = 0.0
    theta: float = 0.0


state_store = store(group="state_0", package="parameters.state_0")
state_store(State(), name="zero_state")
state_store(State(px=1.0), name="front_position")


@dataclasses.dataclass
class KinematicVehicle:
    state_0: State
    v_norm: float = 10.0
    phi: float = 0.0
    l: float = 2.0


vehicle_default = KinematicVehicle(state_0=State())


def model_default(model_name: str) -> sessionConfig.Model:
    return sessionConfig.Model(
        time_range=sessionConfig.TimeRange(model_name=model_name, start_time=0.0, stop_time=10.0),
        tolerance=sessionConfig.Tolerance(model_name=model_name, tolerance=1e-9),
        variable_filter=sessionConfig.VariableFilter(model_name=model_name),
    )


simulation_default = sessionConfig.Simulation(
    solver="rungekutta",
    output_format="csv",
)


session_default = hydra_zen.make_config(
    bases=(sessionConfig.Session,),
    hydra_defaults=["_self_", {"state_0": "zero_state"}],
    parameters=vehicle_default,
    model_configurations={"KinematicVehicle": model_default("KinematicVehicle")},
    sim_configurations=simulation_default,
    model=Path("src/models/kinematicVehicle.mo").resolve(),
)

run_default = hydra_zen.make_config(
    bases=(sessionConfig.SimulationRun,),
    hydra_defaults=["_self_"],
    model_name="KinematicVehicle",
    session=session_default,
)

store(run_default, name="default")
