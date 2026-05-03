from kinematicVehicle.kinematicVehicle import registry, run_default

registry.register_experiment(
    name="front_position",
    base_run_config=run_default,
    selections={"session.parameters.state_0": "front_position"},
)
