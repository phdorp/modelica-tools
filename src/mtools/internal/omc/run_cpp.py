"""Run a Cpp simulation binary: its command line, per-run input and stderr filter, and its solver rules.

The Cpp runtime has no override flag, so parameters go into a per-run copy of the
build's ``_init.xml``. Every setting is passed as an explicit flag, so the defaults
compiled into the binary never apply.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from mtools.errors import ConfigError
from mtools.internal.omc.config import BuildConfig, RunSettings
from mtools.internal.omc.parameters import format_value

if TYPE_CHECKING:
    from mtools.internal.omc.build import Build

logger = logging.getLogger(__name__)

#: Solvers the Cpp runtime runs reliably; others segfault or are not installed.
CPP_SOLVERS = ("dassl", "cvode", "ida")

INPUT_DIRECTORY_NAME = "input"

_ERROR_LINE = re.compile(r"^ERROR\s*:")


def validate_settings(config: BuildConfig, settings: RunSettings) -> None:
    """Check what is known before building: an explicitly requested Cpp solver.

    Call this before :func:`mtools.internal.omc.build.build`; it needs no build.

    Raises:
        ConfigError: The target is Cpp and ``settings.solver`` is not one of
            ``dassl``, ``cvode`` and ``ida``.
    """
    if config.target == "Cpp" and settings.solver is not None:
        _check_solver(settings.solver, config.model_name, "settings.solver")


def validate_build(build: Build, settings: RunSettings) -> None:
    """Check what needs the build: a Cpp solver that comes from the annotation.

    Raises:
        ConfigError: The target is Cpp, no solver is set, and the model's annotation
            names a solver Cpp cannot run. Nothing is substituted.
    """
    if build.target == "Cpp":
        if settings.solver is None:
            _check_solver(build.experiment.solver, build.model_name, "the model's __OpenModelica_simulationFlags annotation")
        else:  # also caught by validate_settings; kept for callers that skip it
            _check_solver(settings.solver, build.model_name, "settings.solver")


def _check_solver(solver: str, model_name: str, origin: str) -> None:
    if solver not in CPP_SOLVERS:
        raise ConfigError(
            f"Invalid run settings for '{model_name}':",
            model_name=model_name,
            diagnostics=f"{origin}: the Cpp target runs only {', '.join(CPP_SOLVERS)}, not '{solver}'",
        )


def warn_if_grid_is_ignored(build: Build, settings: RunSettings) -> None:
    """Warn when Cpp ``dassl`` is given an output interval, which it ignores."""
    solver = settings.solver or build.experiment.solver
    if solver == "dassl" and settings.interval is not None:
        logger.warning(
            "Simulation of '%s': the Cpp solver dassl ignores the output interval and writes every internal step",
            build.model_name,
        )


def write_input(build: Build, overrides: Mapping[str, Any], directory: Path) -> Path:
    """Write the run's copy of ``_init.xml`` with ``overrides`` as start values.

    Returns:
        The input directory to pass as ``--input-path``.
    """
    tree = ET.parse(build.directory / f"{build.file_name_prefix}_init.xml")
    for element in tree.getroot().iter("ScalarVariable"):
        name = element.attrib["name"]
        if name in overrides:
            element[0].set("start", format_value(overrides[name]))
    input_directory = directory / INPUT_DIRECTORY_NAME
    input_directory.mkdir()
    tree.write(input_directory / f"{build.file_name_prefix}_init.xml", encoding="utf-8", xml_declaration=True)
    return input_directory


def command(build: Build, settings: RunSettings, directory: Path, input_directory: Path, result_file: Path) -> list[str]:
    """Return the Cpp runtime command line with every run setting as an explicit flag."""
    experiment = build.experiment
    return [
        str(build.directory / build.file_name_prefix),
        # The binary defaults -M to the directory it was built in, which a cached build no longer is.
        "-M", str(build.directory),
        "--input-path", str(input_directory),
        "-F", str(result_file),
        "-P", "mat",
        "-S", _number(settings.start_time, experiment.start_time),
        "-E", _number(settings.stop_time, experiment.stop_time),
        "-H", _number(settings.interval, experiment.interval),
        "-T", _number(settings.tolerance, experiment.tolerance),
        "-I", settings.solver or experiment.solver,
        "-B", settings.variable_filter,
        "-U", "protected" if settings.emit_protected else "public",
    ]


def _number(value: float | None, default: float) -> str:
    return repr(float(default if value is None else value))


def error_lines(output: str) -> list[str]:
    """Return each distinct ``ERROR  :`` line of the Cpp runtime's stderr once, in order.

    The runtime repeats the whole run with a fallback nonlinear solver after a failure,
    so every error appears twice.
    """
    seen: dict[str, None] = {}
    for line in output.splitlines():
        if _ERROR_LINE.match(line):
            seen.setdefault(line.strip())
    return list(seen)


def match_c_result(data: pd.DataFrame, settings: RunSettings, build: Build) -> pd.DataFrame:
    """Give a Cpp result, finished or partial, the columns and rows C writes for the same run.

    - Drops the rows written before the start time. With a start time other than 0, the
      runtime writes its output grid from time 0 with initial or uninitialised values.
    - Drops the columns C stores as parameters: aliases of a parameter.
    - Writes the repeated time points at the start, at events and at the stop time as C does.
    """
    experiment = build.experiment
    start = float(experiment.start_time if settings.start_time is None else settings.start_time)
    stop = float(experiment.stop_time if settings.stop_time is None else settings.stop_time)
    data = data[data["time"] >= start - _tolerance(start)]
    data = data.drop(columns=[name for name in data.columns if name in _parameter_aliases(build)])
    discrete = [name for name in data.columns if name in build.variables and build.variables[name].variability == "discrete"]
    return data.iloc[_c_rows(data["time"].tolist(), data[discrete].to_numpy(), start, stop)].reset_index(drop=True)


def _tolerance(time: float) -> float:
    return 1e-12 * max(1.0, abs(time))


def _parameter_aliases(build: Build) -> set[str]:
    """Return the variables that alias a parameter.

    Cpp's ``_init.xml`` names no alias target; an alias shares its target's value
    reference, which is counted per type.
    """
    variables = build.variables.values()
    fixed = {
        (variable.type, variable.value_reference)
        for variable in variables
        if variable.alias == "noAlias" and variable.variability == "parameter"
    }
    return {
        variable.name
        for variable in variables
        if variable.alias != "noAlias" and (variable.type, variable.value_reference) in fixed
    }


def _c_rows(times: list[float], discrete: np.ndarray, start: float, stop: float) -> list[int]:
    """Return the row positions that repeat each time point as C does.

    ======================  ===============================  ==============================
    time point              Cpp writes                       C writes
    ======================  ===============================  ==============================
    start, no event         init, init                       init
    start, event            init, after event                init, init, after event
    grid point              row                              row
    event between points    before, after                    before, after
    event on a grid point   before, before, after, after     before, after
    stop, no event          row, row, row                    row, row
    stop, event             before, before, after, after     before, after, after
    ======================  ===============================  ==============================

    An event at the start time is told apart by a change in a discrete variable.
    Rows at one time point may differ in the last bit of their time.
    """
    rows: list[int] = []
    first = 0
    while first < len(times):
        end = first + 1
        while end < len(times) and abs(times[end] - times[end - 1]) <= _tolerance(times[end]):
            end += 1
        point = list(range(first, end))
        if first == 0 and abs(times[0] - start) <= _tolerance(start):
            event = not np.array_equal(discrete[first], discrete[end - 1])
            rows += [first, first, *point[1:]] if event else [first]
        elif end == len(times) and abs(times[first] - stop) <= _tolerance(stop):
            rows += [*point[1::2], end - 1]
        else:
            rows += point if len(point) <= 2 else point[1::2]
        first = end
    return rows
