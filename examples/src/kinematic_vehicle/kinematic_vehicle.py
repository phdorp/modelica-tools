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

MODEL_NAME = "kinematic_vehicle.WrapperKinematicVehicle"

#: OMC flags used by every run config in this example. The Cpp simulation target
#: exercises pydelica's Cpp support.
CPP_OMC_BUILD_FLAGS = {"-q": None, "--simCodeTarget": "Cpp"}


def cpp_build_options(model_name: str) -> dict:
    """Return pydelica build options for a model using the Cpp target."""
    return {
        "model_addr": model_name,
        "omc_build_flags": dict(CPP_OMC_BUILD_FLAGS),
    }


#: The Cpp runtime does not implement the deprecated ``rungekutta`` solver.
simulation_default = session_config.Simulation(solver="dassl")


@dataclasses.dataclass
class WrapperKinematicVehicle:
    v_norm: float = 10.0
    phi: float = 0.0
    wheelbase: float = 2.0


vehicle_default = WrapperKinematicVehicle()


registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())

# Register `vehicle_default` as the default option for `session.parameters`.
# The defaults list entry can be overridden by an experiment.
registry.register_group_options("session/parameters", {"default": vehicle_default}, default="default")

# Register a default option for `session.sim_configurations` so experiments
# can override the runtime options.
registry.register_group_options(
    "session/sim_configurations", {"default": simulation_default}, default="default"
)

# Parameters and simulation settings come from the registered group defaults,
# so only the model name, source, and Cpp build options are supplied here.
run_default = registry.create_run(
    model_name=MODEL_NAME,
    model_path=(Path(__file__).parent / "package.mo").resolve(),
    build_options=cpp_build_options(MODEL_NAME),
    include_experiment_group=True,
    name="default",
)

# Register the experiments directly. Each is bound to every experiment-capable
# run config in the registry, now and in the future.
registry.register_experiment(
    name="standstill",
    base_run_config=run_default,
    overrides={
        "session/parameters": WrapperKinematicVehicle(v_norm=0.0, phi=0.0, wheelbase=2.0)
    },
)
registry.register_experiment(
    name="straight_driving",
    base_run_config=run_default,
    overrides={
        "session/parameters": WrapperKinematicVehicle(v_norm=10.0, phi=0.0, wheelbase=2.0)
    },
)
registry.register_experiment(
    name="turn_left",
    base_run_config=run_default,
    overrides={
        "session/parameters": WrapperKinematicVehicle(
            v_norm=10.0, phi=float(np.deg2rad(0.5)), wheelbase=2.0
        )
    },
)
registry.register_experiment(
    name="protected_output",
    base_run_config=run_default,
    overrides={
        "session/sim_configurations": dataclasses.replace(
            simulation_default, emit_protected=True
        )
    },
)

registry.add_to_hydra_store()

# Re-exported for convenience.
__all__ = [
    "CPP_OMC_BUILD_FLAGS",
    "MODEL_NAME",
    "cpp_build_options",
    "registry",
    "run_default",
    "simulation_default",
]
