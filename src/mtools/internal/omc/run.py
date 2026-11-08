"""Run a build's simulation binary in its own run directory."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from mtools.errors import SimulationError
from mtools.internal.omc.config import RunSettings
from mtools.internal.omc.matfile import read_result
from mtools.internal.omc.parameters import (resolve_parameters,
                                            write_override_file)

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
        logger.debug("Running %s in %s", command, directory)
        completed = subprocess.run(
            command, cwd=directory, capture_output=True, text=True, errors="replace", check=False
        )
        logger.debug(
            "Run exited with %d.\nstdout:\n%s\nstderr:\n%s", completed.returncode, completed.stdout, completed.stderr
        )
        if completed.returncode != 0:
            raise SimulationError(
                f"Simulation of '{build.model_name}' failed:",
                model_name=build.model_name,
                diagnostics=(completed.stdout + completed.stderr).strip(),
            )
        types = {name: variable.type for name, variable in build.variables.items()}
        return read_result(directory / f"{build.file_name_prefix}_res.mat", types)


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
    ]


def _number(value: float | None, default: float) -> str:
    return repr(float(default if value is None else value))
