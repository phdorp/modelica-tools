"""Hydra registry for the kinematic vehicle example.

The parameter schema, group options, and experiments are all attached directly
to the single registry here: the group options are shared by every run config
in the registry, and the experiments are automatically bound to every
experiment-capable run config. The reference run config in
``tests/reference_models`` adds itself to this same registry, so it inherits the
shared options and experiments.
"""

import dataclasses
from pathlib import Path

import hydra_zen
import numpy as np

import mtools.hydra_registry as hydra_registry
import mtools.session_config as session_config

MODEL_NAME = "kinematic_vehicle.KinematicVehicle"


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


registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())

# Register a group named "parameters/state_0" to override parameters at "session.parameters.state_0".
registry.register_group_name("session.parameters.state_0", "parameters/state_0")
# Register the interchangeable initial states and select "zero_state" by default.
registry.register_group_options(
    "parameters/state_0",
    {"zero_state": State(), "front_position": State(px=1.0)},
    default="zero_state",
)

# Register `vehicle_default` as the default option for `session.parameters`.
# The defaults list entry can be overridden by an experiment.
registry.register_group_options("session/parameters", {"default": vehicle_default}, default="default")

# Register a default option for `session.sim_configurations` so experiments
# can override the runtime options.
registry.register_group_options(
    "session/sim_configurations", {"default": session_config.Simulation()}, default="default"
)

# Parameters and simulation settings come from the registered group defaults,
# so only the model name and source are supplied here.
run_default = registry.create_run(
    model_name=MODEL_NAME,
    model_path=(Path(__file__).parent / "package.mo").resolve(),
    include_experiment_group=True,
    name="default",
)

# Register the experiments directly. Each is bound to every experiment-capable
# run config in the registry, now and in the future.
hydra_registry.HydraZenRegistry.register_experiment(
    registry,
    name="standstill",
    base_run_config=run_default,
    overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=0.0, phi=0)},
)
hydra_registry.HydraZenRegistry.register_experiment(
    registry,
    name="straight_driving",
    base_run_config=run_default,
    overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0)},
)
hydra_registry.HydraZenRegistry.register_experiment(
    registry,
    name="turn_left",
    base_run_config=run_default,
    overrides={
        "session/parameters": KinematicVehicle(state_0=State(), v_norm=10.0, phi=float(np.deg2rad(0.5)))
    },
)
hydra_registry.HydraZenRegistry.register_experiment(
    registry,
    name="front_position",
    base_run_config=run_default,
    selections={"parameters/state_0": "front_position"},
)
hydra_registry.HydraZenRegistry.register_experiment(
    registry,
    name="protected_output",
    base_run_config=run_default,
    overrides={"session/sim_configurations": session_config.Simulation(emit_protected=True)},
)

registry.add_to_hydra_store()

# Re-exported for convenience.
__all__ = ["MODEL_NAME", "registry", "run_default"]