import numpy as np
from kinematic_vehicle.kinematic_vehicle import KinematicVehicle, State, registry, run_default

import mtools.hydra_registry as hydra_registry
import mtools.session_config as session_config

register_experiment = hydra_registry.HydraZenRegistry.register_experiment


def register_experiments(registry_in: hydra_registry.HydraZenRegistry, run_config: type) -> None:
    """Register the shared experiments in ``registry_in``.

    The same definitions are applied to the candidate and the reference
    registry so both expose identical experiment names and overrides.

    Args:
        registry_in: Registry to register the experiments in.
        run_config: Run config the experiments derive from. It must already
            be registered in ``registry_in``.
    """
    register_experiment(
        registry_in,
        name="standstill",
        base_run_config=run_config,
        overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=0.0, phi=0)},
    )

    register_experiment(
        registry_in,
        name="straight_driving",
        base_run_config=run_config,
        overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0)},
    )

    register_experiment(
        registry_in,
        name="turn_left",
        base_run_config=run_config,
        overrides={"session/parameters": KinematicVehicle(state_0=State(), v_norm=10.0, phi=float(np.deg2rad(0.5)))},
    )

    register_experiment(
        registry_in,
        name="protected_output",
        base_run_config=run_config,
        overrides={
            "session/sim_configurations": session_config.Simulation(
                solver="rungekutta", output_format="csv", emit_protected=True
            )
        },
    )


register_experiments(registry, run_default)
