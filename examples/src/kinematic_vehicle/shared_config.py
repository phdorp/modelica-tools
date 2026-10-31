"""Shared parameter schema, group options, and run configuration helpers.

Both the candidate and the reference registry import these definitions so
their Hydra option names and defaults stay in sync, while each registry still
owns its Modelica source and run configuration.
"""

import dataclasses
from pathlib import Path

import mtools.hydra_registry as hydra_registry
import mtools.session_config as session_config


@dataclasses.dataclass
class State:
    px: float = 0.0
    py: float = 0.0
    theta: float = 0.0


@dataclasses.dataclass
class KinematicVehicle:
    state_0: State
    v_norm: float = 10.0
    phi: float = 0.0
    l: float = 2.0


vehicle_default = KinematicVehicle(state_0=State())

simulation_default = session_config.Simulation(
    solver="rungekutta",
    output_format="csv",
)


def apply_shared_group_options(registry: hydra_registry.HydraZenRegistry) -> None:
    """Register the group options shared by the candidate and reference registries.

    Args:
        registry: Registry to register the group options in.
    """
    # Register a group of name "parameters/state_0" to override parameters at "session.parameters.state_0".
    registry.register_group_name("session.parameters.state_0", "parameters/state_0")
    # Register group options that can be referenced to override "session.parameters.state_0".
    registry.register_group_option("parameters/state_0", name="zero_state", config=State(), default=True)
    registry.register_group_option("parameters/state_0", name="front_position", config=State(px=1.0))

    # Register `vehicle_default` as group option for `session.parameters` and add it to the defaults list.
    # The default list entry can be overridden by an experiment.
    registry.register_group_option("session/parameters", "default", vehicle_default, default=True)

    # Register `simulation_default` as a group option for `session.sim_configurations`
    # so experiments can override the runtime options.
    registry.register_group_option("session/sim_configurations", "default", simulation_default, default=True)


def create_run(
    registry: hydra_registry.HydraZenRegistry,
    *,
    model_name: str,
    model_path: Path,
    parameters: KinematicVehicle = vehicle_default,
    simulation: session_config.Simulation = simulation_default,
    include_experiment_group: bool = True,
    name: str = "default",
) -> type:
    """Create and register a run config for a kinematic vehicle registry.

    ``registry`` must already have the shared group options applied via
    :func:`apply_shared_group_options`.

    Args:
        registry: Registry to create and register the run config in.
        model_name: Modelica model name, used for the solution table name.
        model_path: Path to the Modelica package containing the model.
        parameters: Default model parameters.
        simulation: Default simulation configuration.
        include_experiment_group: Whether to allow experiment selection.
        name: Name to register the run config under.

    Returns:
        The created run config type.
    """
    return registry.create_run(
        model_name=model_name,
        parameters=parameters,
        simulation=simulation,
        model_path=model_path,
        include_experiment_group=include_experiment_group,
        name=name,
    )
