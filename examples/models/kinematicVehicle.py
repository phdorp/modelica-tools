import dataclasses
from pathlib import Path
from typing import Dict

import hydra_zen
import pydelica

from sessionTools import SessionDirector


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


@dataclasses.dataclass
class TimeRange:
    model_name: str
    start_time: float = 0.0
    stop_time: float = 10.0


@dataclasses.dataclass
class Tolerance:
    model_name: str
    tolerance: float = 1e-9


@dataclasses.dataclass
class VariableFilter:
    model_name: str
    filter_str: str = "*"


@dataclasses.dataclass
class ModelConfig:
    time_range: TimeRange
    tolerance: Tolerance
    variable_filter: VariableFilter


@dataclasses.dataclass
class SimulationConfig:
    solver: pydelica.Solver = pydelica.Solver.RUNGE_KUTTA
    output_format: pydelica.OutputFormat = pydelica.OutputFormat.CSV


@hydra_zen.hydrated_dataclass(SessionDirector, populate_full_signature=True)
class SessionConfig:
    parameters: KinematicVehicle
    sim_configurations: SimulationConfig
    model_configurations: Dict[str, ModelConfig] = dataclasses.field(default_factory=dict)
    model = Path("tests/sessionTools/models/kinematicVehicle.mo").resolve()


session_default = SessionConfig(
    parameters=KinematicVehicle(state_0=State()),
    model_configurations={
        "KinematicVehicle": ModelConfig(
            time_range=TimeRange(model_name="KinematicVehicle"),
            tolerance=Tolerance(model_name="KinematicVehicle"),
            variable_filter=VariableFilter(model_name="KinematicVehicle"),
        )
    },
    sim_configurations=SimulationConfig(),
)
