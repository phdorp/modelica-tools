"""Dedicated Hydra registry for the reference model used in comparison tests."""

from pathlib import Path

import hydra_zen
import numpy as np
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
    model_path=(Path(__file__).parent / "reference_models" / "package.mo").resolve(),
    include_experiment_group=True,
    name="default",
)

registry.register_experiment(
    name="standstill",
    base_run_config=run_default,
    overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=0.0, phi=0)},
)

registry.register_experiment(
    name="straight_driving",
    base_run_config=run_default,
    overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0)},
)

registry.register_experiment(
    name="turn_left",
    base_run_config=run_default,
    overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=10.0, phi=float(np.deg2rad(0.5)))},
)
