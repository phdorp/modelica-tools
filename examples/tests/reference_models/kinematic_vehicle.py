"""Run configuration for the reference kinematic vehicle.

The reference model lives in this `tests`-side Modelica package while the
candidate registry is owned by `kinematic_vehicle.kinematic_vehicle`. Adding the
reference run config to that registry binds it to the registry's experiments
automatically.
"""

from pathlib import Path

from kinematic_vehicle.kinematic_vehicle import registry

REFERENCE_MODEL_NAME = "reference_models.KinematicVehicle"

run_reference = registry.create_run(
    model_name=REFERENCE_MODEL_NAME,
    model_path=(Path(__file__).parent / "package.mo").resolve(),
    include_experiment_group=True,
    name="reference",
)

__all__ = ["REFERENCE_MODEL_NAME", "run_reference"]
