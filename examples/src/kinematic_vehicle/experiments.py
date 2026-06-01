from kinematic_vehicle.kinematic_vehicle import registry, run_default

registry.register_experiment(
    name="front_position",
    base_run_config=run_default,
    selections={"parameters/state_0": "front_position"},
)
