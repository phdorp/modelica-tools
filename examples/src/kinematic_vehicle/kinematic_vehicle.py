import dataclasses
from pathlib import Path

import hydra_zen

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


vehicle = KinematicVehicle(state_0=State())

simulation = session_config.Simulation(
    solver="rungekutta",
    output_format="csv",
)


def apply_shared_group_options(registry_in: hydra_registry.HydraZenRegistry) -> None:
    """Apply shared group options to the given registry.

    This function is used to apply shared group options to both the candidate and reference registries.
    """
    registry_in.register_group_name("session.parameters.state_0", "parameters/state_0")
    registry_in.register_group_option("parameters/state_0", name="zero_state", config=State(), default=True)
    registry_in.register_group_option("parameters/state_0", name="front_position", config=State(px=1.0))

    # Register `vehicle` as group option for `session.parameters` and add it to the defaults list.
    # The default list entry can be overridden by an experiment.
    registry_in.register_group_option("session/parameters", "default", vehicle, default=True)

    # Register `simulation` as a group option for `session.sim_configurations`
    # so experiments can override the runtime options.
    registry_in.register_group_option("session/sim_configurations", "default", simulation, default=True)


registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())
apply_shared_group_options(registry)

MODEL_NAME = "kinematic_vehicle.KinematicVehicle"


def create_run(
    registry_in: hydra_registry.HydraZenRegistry,
    *,
    model_name: str = MODEL_NAME,
    parameters: KinematicVehicle = vehicle,
    simulation: session_config.Simulation = simulation,
    model_path: Path = Path("src/kinematic_vehicle/package.mo").resolve(),
    include_experiment_group: bool = True,
    name: str = "default",
) -> type:
    """Create and register a run configuration for a kinematic vehicle registry.

    The run config is registered in ``registry_in`` (which must already have
    the shared group options applied) so candidate and reference registries
    can share the option definitions while using their own model source.

    Args:
        registry_in: Registry to create and register the run config in.
        model_name: Modelica model name, used for the solution table name.
        parameters: Default model parameters.
        simulation: Default simulation configuration.
        model_path: Path to the Modelica package containing the model.
        include_experiment_group: Whether to allow experiment selection.
        name: Name to register the run config under.

    Returns:
        The created run config type.
    """
    return registry_in.create_run(
        model_name=model_name,
        parameters=parameters,
        simulation=simulation,
        model_path=model_path,
        include_experiment_group=include_experiment_group,
        name=name,
    )


# Create and register the run config in one step.
run_default = create_run(registry)
registry.add_to_hydra_store()
