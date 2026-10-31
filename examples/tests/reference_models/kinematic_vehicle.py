"""Hydra registry and run configuration for the reference kinematic vehicle.

The reference model reuses the candidate's parameter schema, shared group
option definitions, and shared experiments, but owns its own registry, run
configuration, and Modelica source.
"""

from pathlib import Path

import hydra_zen
from kinematic_vehicle.experiments import register_experiments
from kinematic_vehicle.shared_config import apply_shared_group_options, create_run

import mtools.hydra_registry as hydra_registry

MODEL_NAME = "reference_models.KinematicVehicle"

registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())
apply_shared_group_options(registry)

run_default = create_run(
    registry,
    model_name=MODEL_NAME,
    model_path=(Path(__file__).parent / "package.mo").resolve(),
)
register_experiments(registry, run_default)
