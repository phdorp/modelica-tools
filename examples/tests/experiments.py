from kinematic_vehicle.kinematic_vehicle import KinematicVehicle, State, run_default, registry
import numpy as np

# Registers experiments that override the parameter group at `session.parameters`.
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
registry.add_to_hydra_store()
