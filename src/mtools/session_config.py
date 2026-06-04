from __future__ import annotations
import dataclasses
from typing import Any, ClassVar, Dict, Protocol

import hydra_zen
import pydantic

import mtools.internal.session_tools as session_tools


@dataclasses.dataclass
class TimeRange:
    """Simulation time bounds for a specific model."""

    #: Name of the model these time bounds apply to.
    model_name: str
    #: Simulation start time.
    start_time: float
    #: Simulation stop time.
    stop_time: float


@dataclasses.dataclass
class Tolerance:
    """Numerical tolerance configuration for a specific model."""

    #: Name of the model this tolerance applies to.
    model_name: str
    #: Solver tolerance value.
    tolerance: float


@dataclasses.dataclass
class VariableFilter:
    """Variable selection pattern for simulation outputs of a model."""

    #: Name of the model this variable filter applies to.
    model_name: str
    #: Wildcard pattern used to select output variables.
    filter_str: str = "*"


class DataclassType(Protocol):
    """Protocol describing objects that expose dataclass field metadata."""

    #: Dataclass field definitions exposed by dataclass instances.
    __dataclass_fields__: ClassVar[Dict[str, Any]]


@dataclasses.dataclass
class Model:
    """Grouped per-model configuration sections used by session setup."""

    #: Time range settings for the model.
    time_range: TimeRange
    #: Numerical tolerance settings for the model.
    tolerance: Tolerance
    #: Output variable filtering settings for the model.
    variable_filter: VariableFilter

    @classmethod
    def from_parameters(
        cls, model_name: str, start_time: float = 0.0, stop_time: float = 10.0, tolerance: float = 1e-9
    ) -> Model:
        return cls(
            TimeRange(model_name, start_time, stop_time),
            Tolerance(model_name, tolerance),
            VariableFilter(model_name),
        )


@dataclasses.dataclass
class Simulation:
    """Global simulation runtime settings."""

    #: Solver backend name used for simulation.
    solver: str
    #: Output format emitted by the simulation runtime.
    output_format: str


@hydra_zen.hydrated_dataclass(
    session_tools.SessionDirector, populate_full_signature=True, hydra_convert="object", hydra_recursive=None
)
class Session:
    """Hydra-instantiable session configuration for building a simulation session."""

    #: Dataclass object containing model parameter values.
    parameters: DataclassType
    #: Simulation-wide runtime configuration.
    sim_configurations: Simulation
    #: Path to the model source file to build.
    model: pydantic.FilePath
    #: Per-model configuration blocks keyed by model name.
    model_configurations: Dict[str, Model] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class SimulationRun:
    """Top-level run configuration for simulating a model with a session."""

    #: Name of the model to simulate.
    model_name: str
    #: Session configuration used to construct the simulation session.
    session: Session
