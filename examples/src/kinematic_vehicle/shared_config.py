"""Shared parameter schema and group options for the kinematic vehicle registry.

The candidate and reference run configs of the single shared registry import
these definitions so their Hydra option names and defaults stay in sync, while
each run config still owns its Modelica source.
"""

import dataclasses

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


def apply_shared_group_options(registry: hydra_registry.HydraZenRegistry) -> None:
    """Register the group options shared by the candidate and reference registries.

    Args:
        registry: Registry to register the group options in.
    """
    # Register a group named "parameters/state_0" to override parameters at "session.parameters.state_0".
    registry.register_group_name("session.parameters.state_0", "parameters/state_0")
    # Register the interchangeable initial states and select "zero_state" by default.
    registry.register_group_options(
        "parameters/state_0",
        {"zero_state": State(), "front_position": State(px=1.0)},
        default="zero_state",
    )

    # Register `vehicle_default` as the default option for `session.parameters`.
    # The defaults list entry can be overridden by an experiment.
    registry.register_group_options("session/parameters", {"default": vehicle_default}, default="default")

    # Register a default option for `session.sim_configurations` so experiments
    # can override the runtime options.
    registry.register_group_options(
        "session/sim_configurations", {"default": session_config.Simulation()}, default="default"
    )
