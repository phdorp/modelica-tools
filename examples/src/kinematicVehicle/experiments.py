from hydra_zen import make_config, MISSING
from kinematicVehicle.kinematicVehicle import run_default, store

experiment_store = store(group="experiment", package="_global_")

experiment_store(
    make_config(
        bases=(run_default,),
        model_name=MISSING,
        session=MISSING,
        hydra_defaults=["_self_", {"override /state_0": "front_position"}],
    ),
    name="front_position",
)
