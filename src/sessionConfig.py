import dataclasses
from typing import Any, ClassVar, Dict, Protocol

import hydra_zen
import pydantic
import pydelica

import sessionTools


@dataclasses.dataclass
class TimeRange:
    model_name: str
    start_time: float
    stop_time: float


@dataclasses.dataclass
class Tolerance:
    model_name: str
    tolerance: float


@dataclasses.dataclass
class VariableFilter:
    model_name: str
    filter_str: str = "*"


class DataclassType(Protocol):
    __dataclass_fields__: ClassVar[Dict[str, Any]]


@dataclasses.dataclass
class Model:
    time_range: TimeRange
    tolerance: Tolerance
    variable_filter: VariableFilter


@dataclasses.dataclass
class Simulation:
    solver: pydelica.Solver
    output_format: pydelica.OutputFormat


@hydra_zen.hydrated_dataclass(sessionTools.SessionDirector, populate_full_signature=True)
class Session:
    parameters: DataclassType
    sim_configurations: Simulation
    model: pydantic.FilePath
    model_configurations: Dict[str, Model] = dataclasses.field(default_factory=dict)
