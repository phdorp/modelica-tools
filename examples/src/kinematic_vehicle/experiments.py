"""Experiment definitions shared by the candidate and reference registries."""

import numpy as np
from kinematic_vehicle.shared_config import KinematicVehicle, State

import mtools.hydra_registry as hydra_registry
import mtools.session_config as session_config

EXPERIMENTS = (
    hydra_registry.ExperimentSpec(
        name="standstill",
        overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=0.0, phi=0)},
    ),
    hydra_registry.ExperimentSpec(
        name="straight_driving",
        overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0)},
    ),
    hydra_registry.ExperimentSpec(
        name="turn_left",
        overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=10.0, phi=float(np.deg2rad(0.5)))},
    ),
    hydra_registry.ExperimentSpec(
        name="front_position",
        selections={"parameters/state_0": "front_position"},
    ),
    hydra_registry.ExperimentSpec(
        name="protected_output",
        overrides={"session/sim_configurations": session_config.Simulation(emit_protected=True)},
    ),
)
