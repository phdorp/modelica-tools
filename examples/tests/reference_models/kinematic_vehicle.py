"""Run configuration for the reference kinematic vehicle.

The reference model lives in this `tests`-side Modelica package while the
candidate registry is owned by `kinematic_vehicle.kinematic_vehicle`. Adding the
reference run config to that registry binds it to the registry's experiments
automatically.

The reference model extends the candidate interface, so the reference build
also has to load the candidate package. pydelica resolves ``extra_models``
relative to the built model source, and loading the package (rather than the
interface file alone) is what lets OMC resolve the interface's
``within kinematic_vehicle`` clause.
"""

import os
from pathlib import Path

from kinematic_vehicle.kinematic_vehicle import cpp_build_options, registry

REFERENCE_MODEL_NAME = "reference_models.WrapperKinematicVehicle"
REFERENCE_MODEL_PATH = (Path(__file__).parent / "package.mo").resolve()

CANDIDATE_PACKAGE_PATH = (
    Path(__file__).parents[2] / "src" / "kinematic_vehicle" / "package.mo"
).resolve()

run_reference = registry.create_run(
    model_name=REFERENCE_MODEL_NAME,
    model_path=REFERENCE_MODEL_PATH,
    build_options={
        **cpp_build_options(REFERENCE_MODEL_NAME),
        "extra_models": [
            os.path.relpath(CANDIDATE_PACKAGE_PATH, REFERENCE_MODEL_PATH.parent)
        ],
    },
    include_experiment_group=True,
    name="reference",
)

__all__ = ["REFERENCE_MODEL_NAME", "run_reference"]
