"""Hydra registry and run configuration for the reference kinematic vehicle.

The reference model uses the candidate's parameter schema but owns its own
registry, group options, run configuration, and Modelica source. Experiments are
defined once in ``tests.experiments`` and applied to both registries.
"""

from pathlib import Path

import hydra_zen
from kinematic_vehicle.kinematic_vehicle import KinematicVehicle, State

import mtools.hydra_registry as hydra_registry
import mtools.session_config as session_config

MODEL_NAME = "reference_models.KinematicVehicle"

registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())

vehicle_default = KinematicVehicle(state_0=State())
registry.register_group_option("session/parameters", "default", vehicle_default, default=True)

simulation_default = session_config.Simulation(
    solver="rungekutta",
    output_format="csv",
)
registry.register_group_option("session/sim_configurations", "default", simulation_default, default=True)

run_default = registry.create_run(
    model_name=MODEL_NAME,
    parameters=vehicle_default,
    simulation=simulation_default,
    model_path=(Path(__file__).parent / "package.mo").resolve(),
    include_experiment_group=True,
    name="default",
)
