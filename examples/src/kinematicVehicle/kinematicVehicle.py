import dataclasses
from pathlib import Path

import hydra_zen

import mtools.hydraRegistry as hydraRegistry
import mtools.sessionConfig as sessionConfig

registry = hydraRegistry.HydraZenRegistry()


@dataclasses.dataclass
class State:
    px: float = 0.0
    py: float = 0.0
    theta: float = 0.0

registry.register_group_name("session.parameters.state_0", "parameters/state_0")
registry.register_group_option("parameters/state_0", name="zero_state", config=State())
registry.register_group_option("parameters/state_0", name="front_position", config=State(px=1.0))


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
    parameters=vehicle_default,
    model_configurations={"KinematicVehicle": model_default("KinematicVehicle")},
    sim_configurations=simulation_default,
    model=Path("src/kinematicVehicle/kinematicVehicle.mo").resolve(),
)

# Create and register the run config in one step.
run_default = registry.build_run_config(
    base=sessionConfig.SimulationRun,
    model_name="KinematicVehicle",
    session=session_default,
    selections={"parameters/state_0": "zero_state"},
    include_experiment_group=True,
    name="default",
)
