"""Turn a run of an FMU into the values FMPy runs with, checked against its model description."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mtools.errors import ConfigError
from mtools.internal.fmu.description import FmuDescription, FmuVariable
from mtools.internal.omc.config import RunSettings

#: The FMU types a run can use.
FMU_TYPES = ("me", "cs")
#: What the problem messages call each FMU type.
_INTERFACE_NAMES = {"me": "Model Exchange", "cs": "Co-Simulation"}

#: OMC's defaults for what neither the settings nor the ``DefaultExperiment`` give.
DEFAULT_START_TIME = 0.0
DEFAULT_STOP_TIME = 1.0
DEFAULT_TOLERANCE = 1e-6
#: OMC's default number of output intervals.
DEFAULT_INTERVALS = 500
#: Variables that never become result columns.
DROPPED_CAUSALITIES = frozenset({"independent", "parameter", "calculatedParameter"})
DROPPED_TYPES = frozenset({"String", "Binary"})


@dataclass(frozen=True)
class ResolvedRun:
    """Everything one FMU run needs, with every default filled in.

    Attributes:
        model_name: Name the results are keyed by and errors name.
        fmu_type: The FMU type that runs, ``"me"`` or ``"cs"``.
        start_time: Simulation start time.
        stop_time: Simulation stop time.
        interval: Output interval, also the step size.
        tolerance: Relative tolerance.
        solver: FMPy's solver name, ``"CVode"`` or ``"Euler"``; ``None`` for Co-Simulation.
        start_values: Start values by FMU name, set once before initialisation.
        columns: FMU name to result column name, in model-description order, without ``time``.
        cvode_guard: Whether the child guards CVODE's steps.
    """

    model_name: str
    fmu_type: str
    start_time: float
    stop_time: float
    interval: float
    tolerance: float
    solver: str | None
    start_values: Mapping[str, Any]
    columns: Mapping[str, str]
    cvode_guard: bool


def resolve(
    description: FmuDescription,
    settings: RunSettings,
    *,
    model_name: str,
    fmu_type: str | None,
    name_map: Mapping[str, str],
    exported: bool,
) -> ResolvedRun:
    """Check ``settings`` against ``description`` and resolve every run value.

    Unset times, interval and tolerance come from ``settings``, then the FMU's
    ``DefaultExperiment``, then OMC's defaults.

    Raises:
        ConfigError: Listing every problem by its config path.
    """
    start_time = _first(settings.start_time, description.start_time, DEFAULT_START_TIME)
    stop_time = _first(settings.stop_time, description.stop_time, DEFAULT_STOP_TIME)
    default_interval = (stop_time - start_time) / DEFAULT_INTERVALS
    problems: list[str] = []
    resolved_type = _resolve_type(description, fmu_type, model_name, problems)
    if problems:
        raise ConfigError(f"Invalid run settings for '{model_name}':", model_name=model_name, diagnostics="\n".join(problems))
    return ResolvedRun(
        model_name=model_name,
        fmu_type=resolved_type,
        start_time=start_time,
        stop_time=stop_time,
        interval=_first(settings.interval, description.interval, default_interval),
        tolerance=_first(settings.tolerance, description.tolerance, DEFAULT_TOLERANCE),
        solver="CVode" if resolved_type == "me" else None,
        start_values={},
        columns={variable.name: variable.name for variable in description.variables if _is_column(variable)},
        cvode_guard=False,
    )


def _resolve_type(description: FmuDescription, requested: str | None, model_name: str, problems: list[str]) -> str:
    """Return the FMU type that runs: ``requested``, else Model Exchange if offered, else Co-Simulation.

    Appends to ``problems`` when ``requested`` isn't offered."""
    if requested is None:
        return "me" if "me" in description.fmu_types else "cs"
    if requested not in description.fmu_types:
        problems.append(f"build.fmu_type: '{model_name}' has no {_INTERFACE_NAMES[requested]} interface")
    return requested


def _is_column(variable: FmuVariable) -> bool:
    """Whether ``variable`` becomes a result column: the independent variable, whatever
    its name, is the ``time`` column that comes first anyway, and parameters, constants,
    strings and binaries are dropped as in native results."""
    return (
        variable.name != "time"
        and variable.causality not in DROPPED_CAUSALITIES
        and variable.variability != "constant"
        and variable.type not in DROPPED_TYPES
    )


def _first(*values: float | None) -> float:
    return float(next(value for value in values if value is not None))
