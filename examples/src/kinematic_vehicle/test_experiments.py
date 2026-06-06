from kinematic_vehicle.kinematic_vehicle import KinematicVehicle, State, registry, run_default

registry.register_experiment(
    name="standstill",
    base_run_config=run_default,
    selections={
        "parameters/state_0": "zero_state",
    },
    parameters=KinematicVehicle(state_0=State(), v_norm=0.0, phi=0.0),
)

registry.register_experiment(
    name="straight_driving",
    base_run_config=run_default,
    selections={
        "parameters/state_0": "zero_state",
    },
    parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0),
)

registry.register_experiment(
    name="turn_left",
    base_run_config=run_default,
    selections={
        "parameters/state_0": "zero_state",
    },
    parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.5),
)
