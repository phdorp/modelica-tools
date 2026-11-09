import dataclasses
from pathlib import Path

import hydra_zen

import mtools.session_config as session_config

MODEL_PATH = Path(__file__).with_name("kinematic_vehicle.mo").resolve()


@dataclasses.dataclass
class State:
    px: float = 0.0
    py: float = 0.0
    theta: float = 0.0


@dataclasses.dataclass
class KinematicVehicle:
    state_0: State
    v_norm: float = 10.0
    phi: float = 0.0
    l: float = 2.0


vehicle_default = KinematicVehicle(state_0=State())

build_default = session_config.Build(model_path=MODEL_PATH, model_name="KinematicVehicle")

settings_default = session_config.RunSettings(parameters=vehicle_default, stop_time=10.0)

run_default = hydra_zen.make_config(
    bases=(session_config.SimulationRun,),
    hydra_defaults=["_self_"],
    build=build_default,
    settings=settings_default,
)
