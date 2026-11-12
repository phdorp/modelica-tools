"""Registry for the FMU reference comparison.

Both sides are exported from the C target as Model Exchange FMUs and run on FMPy. The
registry is separate from the candidate registry: it carries the vehicle's parameter and
settings groups and the ``turn_left`` experiment, but only the two FMU run configs.
"""

import hydra_zen
import numpy as np
from kinematic_vehicle.kinematic_vehicle import (MODEL_NAME,
                                                 WrapperKinematicVehicle,
                                                 settings_fmu)

import mtools.hydra_registry as hydra_registry
import mtools.session_config as session_config
from tests.reference_models.kinematic_vehicle import (CANDIDATE_PACKAGE_PATH,
                                                      REFERENCE_MODEL_NAME,
                                                      REFERENCE_MODEL_PATH)

fmu_registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())

fmu_registry.register_group_options("settings/parameters", {"default": WrapperKinematicVehicle()}, default="default")
fmu_registry.register_group_options("settings", {"default": settings_fmu}, default="default")

run_fmu_candidate = fmu_registry.create_run(
    model_name=MODEL_NAME,
    model_path=CANDIDATE_PACKAGE_PATH,
    target="C",
    fmu=session_config.FmuExport(),
    include_experiment_group=True,
    name="default",
)

run_fmu_reference = fmu_registry.create_run(
    model_name=REFERENCE_MODEL_NAME,
    model_path=REFERENCE_MODEL_PATH,
    target="C",
    extra_sources=[CANDIDATE_PACKAGE_PATH],
    fmu=session_config.FmuExport(),
    include_experiment_group=True,
    name="reference",
)

fmu_registry.register_experiment(
    name="turn_left",
    base_run_config=run_fmu_candidate,
    overrides={
        "settings/parameters": WrapperKinematicVehicle(phi=float(np.deg2rad(0.5)))
    },
)
