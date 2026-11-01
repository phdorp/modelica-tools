"""Hydra registry and run configuration for the candidate kinematic vehicle.

The parameter schema and group options are shared with the reference model via
:mod:`kinematic_vehicle.shared_config`; the experiments are shared via
:mod:`kinematic_vehicle.experiments`.
"""

from pathlib import Path

import hydra_zen
from kinematic_vehicle import shared_config
from kinematic_vehicle.experiments import EXPERIMENTS

import mtools.hydra_registry as hydra_registry

MODEL_NAME = "kinematic_vehicle.KinematicVehicle"

registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())
shared_config.apply_shared_group_options(registry)

# Parameters and simulation settings come from the registered group defaults,
# so only the model name and source are supplied here.
run_default = registry.create_run(
    model_name=MODEL_NAME,
    model_path=(Path(__file__).parent / "package.mo").resolve(),
    include_experiment_group=True,
    name="default",
)
registry.register_experiments(EXPERIMENTS, base_run_config=run_default)

registry.add_to_hydra_store()

# Re-exported for convenience.
__all__ = ["MODEL_NAME", "registry", "run_default"]
