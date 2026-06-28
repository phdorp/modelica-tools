import dataclasses
from pathlib import Path

import hydra_zen

import mtools.hydra_registry as hydra_registry
import mtools.session_config as session_config

registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())


@dataclasses.dataclass
class State:
    px: float = 0.0
    py: float = 0.0
    theta: float = 0.0


# Register a group of name "parameters/state_0" to override parameters at "session.parameters.state_0".
registry.register_group_name("session.parameters.state_0", "parameters/state_0")
# Register group options that can be referenced to override "session.parameters.state_0".
registry.register_group_option("parameters/state_0", name="zero_state", config=State(), default=True)
registry.register_group_option("parameters/state_0", name="front_position", config=State(px=1.0))


@dataclasses.dataclass
class KinematicVehicle:
    state_0: State
    v_norm: float = 10.0
    phi: float = 0.0
    l: float = 2.0


vehicle_default = KinematicVehicle(state_0=State())

# Register `vehicle_default` as group option for `session.parameters` and add it to the defaults list.
# The default list entry can be overridden by an experiment.
registry.register_group_option("session/parameters", "default", vehicle_default, default=True)

simulation_default = session_config.Simulation(
    solver="rungekutta",
    output_format="csv",
)


session_default = hydra_zen.make_config(
    bases=(session_config.Session,),
    parameters=vehicle_default,
    model_configurations={"KinematicVehicle": session_config.Model.from_parameters("KinematicVehicle")},
    sim_configurations=simulation_default,
    model=Path("src/kinematic_vehicle/kinematic_vehicle.mo").resolve(),
)

# Create and register the run config in one step.
run_default = registry.build_run_config(
    base=session_config.SimulationRun,
    model_name="KinematicVehicle",
    session=session_default,
    include_experiment_group=True,
    name="default",
)
registry.add_to_hydra_store()
