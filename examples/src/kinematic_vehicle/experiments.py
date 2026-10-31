"""Experiment definitions shared by the candidate and reference registries."""

import dataclasses
from typing import Any

import numpy as np
from kinematic_vehicle.shared_config import KinematicVehicle, State

import mtools.hydra_registry as hydra_registry
import mtools.session_config as session_config


@dataclasses.dataclass(frozen=True)
class ExperimentSpec:
    """A named experiment applied to both registries.

    Attributes:
        name: Experiment name registered under the ``experiment`` group.
        overrides: Mapping of hierarchy path to config instance, replacing
            the selected group's default.
        selections: Mapping of hierarchy path to group option name.
    """

    name: str
    overrides: dict[str, Any] | None = None
    selections: dict[str, str] | None = None


EXPERIMENTS = (
    ExperimentSpec(
        name="standstill",
        overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=0.0, phi=0)},
    ),
    ExperimentSpec(
        name="straight_driving",
        overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0)},
    ),
    ExperimentSpec(
        name="turn_left",
        overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=10.0, phi=float(np.deg2rad(0.5)))},
    ),
    ExperimentSpec(
        name="front_position",
        selections={"parameters/state_0": "front_position"},
    ),
    ExperimentSpec(
        name="protected_output",
        overrides={
            "session/sim_configurations": session_config.Simulation(
                solver="rungekutta", output_format="csv", emit_protected=True
            )
        },
    ),
)


def register_experiments(registry: hydra_registry.HydraZenRegistry, run_config: type) -> None:
    """Register the shared experiments in ``registry``.

    The same definitions are applied to the candidate and the reference
    registry so both expose identical experiment names and overrides.

    Args:
        registry: Registry to register the experiments in.
        run_config: Run config the experiments derive from. It must already
            be registered in ``registry``.
    """
    for experiment in EXPERIMENTS:
        hydra_registry.HydraZenRegistry.register_experiment(
            registry,
            name=experiment.name,
            base_run_config=run_config,
            selections=experiment.selections,
            overrides=experiment.overrides,
        )
