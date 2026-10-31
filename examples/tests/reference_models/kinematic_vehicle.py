"""Hydra registry and run configuration for the reference kinematic vehicle.

The reference model reuses the candidate's parameter schema and shared group
option definitions, but owns its own registry, run configuration, and Modelica
source. Experiments are defined once in ``tests.experiments`` and applied to
both registries.
"""

from pathlib import Path

import hydra_zen
from kinematic_vehicle.kinematic_vehicle import apply_shared_group_options, create_run
from tests.experiments import register_experiments

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
