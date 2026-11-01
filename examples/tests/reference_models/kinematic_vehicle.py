"""Hydra registry and run configuration for the reference kinematic vehicle.

The reference model reuses the candidate's parameter schema, shared group
option definitions, and shared experiments, but owns its own registry, run
configuration, and Modelica source.
"""

from pathlib import Path

import hydra_zen
from kinematic_vehicle.experiments import EXPERIMENTS
from kinematic_vehicle.shared_config import apply_shared_group_options

import mtools.hydra_registry as hydra_registry

MODEL_NAME = "reference_models.KinematicVehicle"

registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())
apply_shared_group_options(registry)

# Parameters and simulation settings come from the registered group defaults,
# so only the model name and source are supplied here.
run_default = registry.create_run(
    model_name=MODEL_NAME,
    model_path=(Path(__file__).parent / "package.mo").resolve(),
    include_experiment_group=True,
    name="default",
)
registry.register_experiments(EXPERIMENTS, base_run_config=run_default)
