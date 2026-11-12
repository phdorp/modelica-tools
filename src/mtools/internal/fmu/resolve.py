"""Turn a run of an FMU into the values FMPy runs with, checked against its model description."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mtools.errors import ConfigError
from mtools.internal.fmu.description import FmuDescription, FmuVariable
from mtools.internal.fmu.parameters import start_values
from mtools.internal.omc.config import RunSettings
from mtools.internal.omc.init_xml import Variable

logger = logging.getLogger(__name__)

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
#: The solvers a Model Exchange run supports: the settings' name to FMPy's.
ME_SOLVERS = {"cvode": "CVode", "euler": "Euler"}
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
        column_types: FMU name to its FMI type name (``Real``, ``Int32``, ...), for the
            same variables as ``columns``.
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
    column_types: Mapping[str, str]
    cvode_guard: bool


def resolve(
    description: FmuDescription,
    settings: RunSettings,
    *,
    model_name: str,
    fmu_type: str | None,
    name_map: Mapping[str, str],
    exported: bool,
    build_variables: Mapping[str, Variable],
) -> ResolvedRun:
    """Check ``settings`` against ``description`` and resolve every run value.

    Unset times, interval and tolerance come from ``settings``, then the FMU's
    ``DefaultExperiment``, then OMC's defaults. ``build_variables`` are the variables of
    the build that exported the FMU (``model_init.xml``), empty for a given FMU.

    Raises:
        ConfigError: Listing every problem by its config path.
    """
    start_time = _first(settings.start_time, description.start_time, DEFAULT_START_TIME)
    stop_time = _first(settings.stop_time, description.stop_time, DEFAULT_STOP_TIME)
    default_interval = (stop_time - start_time) / DEFAULT_INTERVALS
    problems: list[str] = []
    resolved_type = _resolve_type(description, fmu_type, model_name, problems)
    if not exported and settings.emit_protected:
        logger.warning("settings.emit_protected has no effect on the given FMU '%s'", model_name)
    solver = _resolve_solver(settings.solver, resolved_type, model_name, problems)
    interval = _first(settings.interval, description.interval, default_interval)
    if interval <= 0:
        problems.append(f"settings.interval: expected a positive number, got {interval}")
    elif resolved_type == "cs" and not description.can_handle_variable_step:
        _check_interval(interval, start_time, stop_time, model_name, problems)
    column_filter = _compile_filter(settings.variable_filter, problems)
    values, parameter_problems, _ = start_values(
        settings.parameters,
        {variable.name: variable for variable in description.variables},
        model_name=model_name,
        to_fmu=lambda name: name,
        exported=exported,
        build_variables=build_variables,
    )
    problems.extend(parameter_problems)
    if problems:
        raise ConfigError(f"Invalid run settings for '{model_name}':", model_name=model_name, diagnostics="\n".join(problems))
    kept = [
        variable
        for variable in description.variables
        if _is_column(variable) and column_filter.fullmatch(variable.name)
    ]
    return ResolvedRun(
        model_name=model_name,
        fmu_type=resolved_type,
        start_time=start_time,
        stop_time=stop_time,
        interval=interval,
        tolerance=_first(settings.tolerance, description.tolerance, DEFAULT_TOLERANCE),
        solver=solver,
        start_values=values,
        columns={variable.name: variable.name for variable in kept},
        column_types={variable.name: variable.type for variable in kept},
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


def _compile_filter(pattern: str, problems: list[str]) -> re.Pattern[str]:
    """Return the compiled ``variable_filter``; appends to ``problems`` when it isn't a regular expression."""
    try:
        return re.compile(pattern)
    except re.error as error:
        problems.append(f"settings.variable_filter: invalid regular expression {pattern!r}: {error}")
        return re.compile("")


def _resolve_solver(requested: str | None, fmu_type: str, model_name: str, problems: list[str]) -> str | None:
    """Return FMPy's solver name for a Model Exchange run (CVode unless ``requested``), ``None`` for
    Co-Simulation, which runs its built-in solver; ``requested`` there is warned about.

    Appends to ``problems`` when ``requested`` isn't a Model Exchange solver."""
    if fmu_type == "cs":
        if requested is not None:
            logger.warning(
                "Co-Simulation FMU '%s' runs its built-in solver; settings.solver '%s' is ignored", model_name, requested
            )
        return None
    if requested is None:
        return ME_SOLVERS["cvode"]
    if requested.lower() not in ME_SOLVERS:
        problems.append(f"settings.solver: Model Exchange FMU runs support 'cvode' and 'euler', got '{requested}'")
        return None
    return ME_SOLVERS[requested.lower()]


def _check_interval(interval: float, start_time: float, stop_time: float, model_name: str, problems: list[str]) -> None:
    """Append to ``problems`` when ``interval`` doesn't divide the span into whole steps."""
    steps = (stop_time - start_time) / interval
    if abs(steps - round(steps)) > 1e-9 * max(1.0, steps):
        problems.append(
            f"settings.interval: {interval:g} doesn't divide the run's {stop_time - start_time:g} s "
            f"and '{model_name}' can't change its communication step size"
        )


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
