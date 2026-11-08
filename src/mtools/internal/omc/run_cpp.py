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


def drop_rows_before_start(data: pd.DataFrame, start_time: float | None, build: Build) -> pd.DataFrame:
    """Drop the rows Cpp writes before the start time.

    With a start time other than 0, the runtime writes its output grid from time 0, so
    the file has rows before the start time holding the initial or uninitialised values.
    """
    start = float(build.experiment.start_time if start_time is None else start_time)
    return data[data["time"] >= start - 1e-12 * max(1.0, abs(start))].reset_index(drop=True)
