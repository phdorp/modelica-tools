"""Run configuration for the reference kinematic vehicle.

The reference model lives in the ``tests`` Modelica package, addressed from the
tests root as ``tests.reference_models``. The candidate registry is owned by
``kinematic_vehicle.kinematic_vehicle``; adding the reference run config to that
registry binds it to the registry's experiments automatically.

The reference model extends the candidate interface, so the reference build
also has to load the candidate package. Loading the package (rather than the
interface file alone) is what lets OMC resolve the interface's
``within kinematic_vehicle`` clause.
"""

from pathlib import Path

from kinematic_vehicle.kinematic_vehicle import cpp_build_options, registry

#: Root of the ``examples`` project, used to address Modelica packages relative
#: to the project rather than to this module.
PROJECT_ROOT = Path(__file__).parents[2]

REFERENCE_MODEL_NAME = "tests.reference_models.WrapperKinematicVehicle"
REFERENCE_MODEL_PATH = (PROJECT_ROOT / "tests" / "package.mo").resolve()

CANDIDATE_PACKAGE_PATH = (
    PROJECT_ROOT / "src" / "kinematic_vehicle" / "package.mo"
).resolve()

run_reference = registry.create_run(
    model_name=REFERENCE_MODEL_NAME,
    model_path=REFERENCE_MODEL_PATH,
    build_options={
        **cpp_build_options(REFERENCE_MODEL_NAME),
        "extra_models": [str(CANDIDATE_PACKAGE_PATH)],
    },
    include_experiment_group=True,
    name="reference",
)

__all__ = ["REFERENCE_MODEL_NAME", "run_reference"]
