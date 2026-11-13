"""Hydra registry for the kinematic vehicle example.

The parameter schema, group options, and experiments are all attached directly
to the single registry here: the group options are shared by every run config
in the registry, and the experiments are automatically bound to every
experiment-capable run config. The reference run config in
``tests/reference_models`` adds itself to this same registry, so it inherits the
shared options and experiments.
"""

import dataclasses
from pathlib import Path

import hydra_zen
import numpy as np
from hydra_zen import MISSING

import mtools.hydra_registry as hydra_registry
import mtools.session_config as session_config

MODEL_NAME = "kinematic_vehicle.WrapperKinematicVehicle"
MODEL_PATH = (Path(__file__).parent / "package.mo").resolve()

#: Simulation target of every run config in this example: OpenModelica's C++ runtime.
TARGET = "Cpp"

#: Run settings shared by every run config; the parameters come from the
#: ``settings/parameters`` group. The model has no experiment annotation, so the time
#: range and tolerance are set here. The Cpp runtime runs only dassl, cvode and ida.
settings_default = session_config.RunSettings(parameters=MISSING, stop_time=10.0, tolerance=1e-9, solver="dassl")


#: Run settings of the FMU run config. An exported FMU runs on FMPy, whose Model Exchange
#: solvers are cvode and euler, so the Cpp-only ``dassl`` of ``settings_default`` doesn't apply.
settings_fmu = dataclasses.replace(settings_default, solver="cvode")


@dataclasses.dataclass
class WrapperKinematicVehicle:
    v_norm: float = 10.0
    phi: float = 0.0
    wheelbase: float = 2.0


vehicle_default = WrapperKinematicVehicle()

#: Parameters of the ``turn_left`` experiment, shared with the FMU reference test's registry.
vehicle_turn_left = WrapperKinematicVehicle(v_norm=10.0, phi=float(np.deg2rad(0.5)), wheelbase=2.0)


registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())

# Register `vehicle_default` as the default option for `settings.parameters`.
# The defaults list entry can be overridden by an experiment.
registry.register_group_options("settings/parameters", {"default": vehicle_default}, default="default")

# Register a default option for `settings` so experiments can override the run
# settings; the parameters above are merged into it.
registry.register_group_options(
    "settings", {"default": settings_default, "fmu": settings_fmu}, default="default"
)

# Parameters and run settings come from the registered group defaults, so only
# the model name, source, and target are supplied here.
run_default = registry.create_run(
    model_name=MODEL_NAME,
    model_path=MODEL_PATH,
    target=TARGET,
    include_experiment_group=True,
    name="default",
)

# The same model exported as a Model Exchange FMU from the C target and run on FMPy
# (`python -m kinematic_vehicle --config-name fmu`).
run_fmu = registry.create_run(
    model_name=MODEL_NAME,
    model_path=MODEL_PATH,
    target="C",
    fmu=session_config.FmuExport(),
    selections={"settings": "fmu"},
    include_experiment_group=True,
    name="fmu",
)

# Register the experiments directly. Each is bound to every experiment-capable
# run config in the registry, now and in the future.
registry.register_experiment(
    name="standstill",
    base_run_config=run_default,
    overrides={
        "settings/parameters": WrapperKinematicVehicle(v_norm=0.0, phi=0.0, wheelbase=2.0)
    },
)
registry.register_experiment(
    name="straight_driving",
    base_run_config=run_default,
    overrides={
        "settings/parameters": WrapperKinematicVehicle(v_norm=10.0, phi=0.0, wheelbase=2.0)
    },
)
registry.register_experiment(
    name="turn_left",
    base_run_config=run_default,
    overrides={"settings/parameters": vehicle_turn_left},
)
registry.register_experiment(
    name="protected_output",
    base_run_config=run_default,
    overrides={
        # No solver, so the run takes its own default: dassl natively (the model has no
        # solver annotation) and CVode on an FMU, where dassl is not a solver.
        "settings": dataclasses.replace(settings_default, solver=None, emit_protected=True)
    },
)

# Re-exported for convenience.
__all__ = [
    "MODEL_NAME",
    "MODEL_PATH",
    "TARGET",
    "registry",
    "run_default",
    "run_fmu",
    "settings_default",
    "settings_fmu",
    "vehicle_default",
    "vehicle_turn_left",
]
