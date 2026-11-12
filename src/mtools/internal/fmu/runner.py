"""Run a given or exported FMU in a child process in its own run directory.

The run directory is deleted when the run ends, however it ended, unless
``MTOOLS_KEEP_RUNS`` is set.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from mtools.errors import SimulationError
from mtools.internal.fmu import child
from mtools.internal.fmu.config import FmuFileConfig
from mtools.internal.fmu.description import FmuDescription, read_description
from mtools.internal.fmu.request import RunRequest
from mtools.internal.fmu.resolve import ResolvedRun, resolve
from mtools.internal.fmu.result import to_frame
from mtools.internal.omc import workdir
from mtools.internal.omc.build import Build
from mtools.internal.omc.config import RunSettings
from mtools.internal.omc.process import execute

FMI_TYPES = {"me": "ModelExchange", "cs": "CoSimulation"}


def simulate_file(config: FmuFileConfig, settings: RunSettings) -> tuple[str, pd.DataFrame]:
    """Run the given FMU ``config`` with ``settings``; return its model name and result.

    Raises:
        ConfigError: The settings don't fit the FMU's model description.
        SimulationError: The run failed.
    """
    description = read_description(config.fmu_path)
    run = resolve(
        description,
        settings,
        model_name=config.model_name or description.model_name,
        fmu_type=config.fmu_type,
        name_map=config.name_map,
        exported=False,
    )
    return run.model_name, _run(config.fmu_path, description, run, settings)


def simulate_export(build: Build, settings: RunSettings) -> pd.DataFrame:
    """Run the FMU exported by ``build`` with ``settings``; return its result.

    Raises:
        ConfigError: The settings don't fit the FMU's model description.
        SimulationError: The run failed.
    """
    if build.config.fmu is None:
        raise ValueError(f"The build of '{build.model_name}' exported no FMU")
    description = read_description(build.fmu_path)
    run = resolve(
        description,
        settings,
        model_name=build.model_name,
        fmu_type=build.config.fmu.fmu_type,
        name_map={},
        exported=True,
    )
    return _run(build.fmu_path, description, run, settings)


def _run(fmu_path: Path, description: FmuDescription, run: ResolvedRun, settings: RunSettings) -> pd.DataFrame:
    """Run ``fmu_path`` as resolved in ``run`` in a child process; return its result."""
    directory = workdir.new_run_directory("fmu-")
    try:
        RunRequest(
            fmu_path=str(fmu_path.absolute()),
            unzip_dir=str(directory / "fmu"),
            fmi_type=FMI_TYPES[run.fmu_type],
            start_time=run.start_time,
            stop_time=run.stop_time,
            interval=run.interval,
            tolerance=run.tolerance,
            solver=run.solver,
            start_values=dict(run.start_values),
            output=list(run.columns),
            cvode_guard=run.cvode_guard,
        ).write(directory)
        command = [sys.executable, "-m", "mtools.internal.fmu.child", str(directory)]
        result = execute(command, directory, settings.timeout)
        if result.returncode != 0:
            raise SimulationError(
                f"Simulation of '{run.model_name}' failed:",
                model_name=run.model_name,
                diagnostics=result.output.strip(),
            )
        array = np.load(directory / child.RESULT_FILE_NAME, allow_pickle=False)
        return to_frame(array, run)
    finally:
        workdir.discard(directory)
