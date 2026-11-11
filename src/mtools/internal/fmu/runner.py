"""Run an FMU in a child process in its own run directory."""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from mtools.errors import SimulationError
from mtools.internal.fmu import child
from mtools.internal.fmu.config import FmuFileConfig
from mtools.internal.fmu.description import read_description
from mtools.internal.fmu.request import RunRequest
from mtools.internal.fmu.resolve import resolve
from mtools.internal.fmu.result import to_frame
from mtools.internal.omc import workdir
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
    directory = workdir.new_run_directory("fmu-")
    RunRequest(
        fmu_path=str(config.fmu_path.absolute()),
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
    result = execute([sys.executable, "-m", "mtools.internal.fmu.child", str(directory)], directory, settings.timeout)
    if result.returncode != 0:
        raise SimulationError(
            f"Simulation of '{run.model_name}' failed:", model_name=run.model_name, diagnostics=result.output.strip()
        )
    array = np.load(directory / child.RESULT_FILE_NAME, allow_pickle=False)
    return run.model_name, to_frame(array, run)
