"""Run a build's simulation binary in its own run directory."""

from __future__ import annotations

import logging
import shutil
import struct
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from mtools.errors import SimulationError, SimulationTimeout
from mtools.internal.omc.config import RunSettings
from mtools.internal.omc.matfile import read_result
from mtools.internal.omc.parameters import (resolve_parameters,
                                            write_override_file)
from mtools.internal.omc.process import ProcessResult, execute
from mtools.internal.omc.run_diagnostics import (failure_diagnostics,
                                                 notable_entries)

if TYPE_CHECKING:
    from mtools.internal.omc.build import Build

logger = logging.getLogger(__name__)

OVERRIDE_FILE_NAME = "overrides.txt"


def simulate(build: Build, settings: RunSettings) -> pd.DataFrame:
    """Run ``build`` once with ``settings`` and return the result."""
    if build.target != "C":
        raise NotImplementedError(f"Running the {build.target} target is not supported yet")

    overrides = resolve_parameters(settings.parameters, build.parameters, build.model_name)

    with _run_directory() as directory:
        command = _c_command(build, settings, directory)
        if overrides:
            override_file = directory / OVERRIDE_FILE_NAME
            write_override_file(override_file, overrides)
            command.append(f"-overrideFile={override_file}")
        result = execute(command, directory, settings.timeout)
        result_file = directory / f"{build.file_name_prefix}_res.mat"
        types = {name: variable.type for name, variable in build.variables.items()}
        if result.timed_out or result.returncode != 0:
            raise _simulation_error(build, settings, result, _partial_result(result_file, types))
        if not result_file.exists():
            raise _simulation_error(build, settings, result, None, missing=result_file.name)
        if warnings := notable_entries(result.output):
            logger.warning("Simulation of '%s' reported warnings:\n%s", build.model_name, "\n".join(warnings))
        return read_result(result_file, types)


def _simulation_error(
    build: Build,
    settings: RunSettings,
    result: ProcessResult,
    partial_result: pd.DataFrame | None,
    missing: str | None = None,
) -> SimulationError:
    """Build the exception for a failed, timed-out or result-less run.

    The one place where run diagnostics are assembled.
    """
    name = build.model_name
    diagnostics = failure_diagnostics(result.output, result.signal.name if result.signal and not result.timed_out else None)
    if missing:
        diagnostics = "\n".join(filter(None, [diagnostics, f"The run finished without writing '{missing}'."]))
    if result.timed_out:
        return SimulationTimeout(
            f"Simulation of '{name}' timed out after {settings.timeout:g} s:",
            model_name=name,
            diagnostics=diagnostics,
            partial_result=partial_result,
        )
    header = f"Simulation of '{name}' failed:"
    return SimulationError(header, model_name=name, diagnostics=diagnostics, partial_result=partial_result)


def _partial_result(path: Path, types: Mapping[str, str]) -> pd.DataFrame | None:
    """Read what an unfinished run wrote, or ``None`` if there is nothing to read."""
    try:
        partial = read_result(path, types)
    except (OSError, ValueError, KeyError, IndexError, struct.error):
        return None
    return None if partial.empty else partial


@contextmanager
def _run_directory() -> Iterator[Path]:
    """Create a new run directory and delete it when the run ends."""
    directory = Path(tempfile.mkdtemp(prefix="mtools-run-"))
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _c_command(build: Build, settings: RunSettings, directory: Path) -> list[str]:
    """Return the C runtime command line with every run setting as an explicit flag."""
    experiment = build.experiment
    return [
        str(build.directory / build.file_name_prefix),
        f"-inputPath={build.directory}",
        f"-outputPath={directory}",
        "-outputFormat=mat",
        f"-startTime={_number(settings.start_time, experiment.start_time)}",
        f"-stopTime={_number(settings.stop_time, experiment.stop_time)}",
        f"-stepSize={_number(settings.interval, experiment.interval)}",
        f"-tolerance={_number(settings.tolerance, experiment.tolerance)}",
        f"-s={settings.solver or experiment.solver}",
        f"-variableFilter={settings.variable_filter}",
        *(["-emit_protected"] if settings.emit_protected else []),
        *(["-abortSlowSimulation"] if settings.abort_on_chattering else []),
    ]


def _number(value: float | None, default: float) -> str:
    return repr(float(default if value is None else value))
