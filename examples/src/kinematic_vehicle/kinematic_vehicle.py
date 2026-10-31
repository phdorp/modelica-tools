"""Hydra registry and run configuration for the candidate kinematic vehicle.

The parameter schema and group options are shared with the reference model via
:mod:`kinematic_vehicle.shared_config`; the experiments are shared via
:mod:`kinematic_vehicle.experiments`.
"""

from pathlib import Path

import hydra_zen
from kinematic_vehicle.experiments import register_experiments
from kinematic_vehicle.shared_config import (
    KinematicVehicle,
    State,
    apply_shared_group_options,
    create_run,
)

import mtools.hydra_registry as hydra_registry

MODEL_NAME = "kinematic_vehicle.KinematicVehicle"

registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())
apply_shared_group_options(registry)

run_default = create_run(
    registry,
    model_name=MODEL_NAME,
    model_path=(Path(__file__).parent / "package.mo").resolve(),
)
register_experiments(registry, run_default)

registry.add_to_hydra_store()

# Re-exported for convenience; the candidate schema lives in `shared_config`.
__all__ = [
    "KinematicVehicle",
    "MODEL_NAME",
    "State",
    "apply_shared_group_options",
    "create_run",
    "registry",
    "run_default",
]
