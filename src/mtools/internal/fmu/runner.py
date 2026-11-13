"""Run a given or exported FMU in a child process in its own run directory.

The run directory is deleted when the run ends, however it ended, unless
``MTOOLS_KEEP_RUNS`` is set.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from mtools.errors import SimulationError, SimulationTimeout
from mtools.internal.fmu import child
from mtools.internal.fmu.config import FmuFileConfig
from mtools.internal.fmu.description import FMI_TYPES, read_description
from mtools.internal.fmu.diagnostics import (cvode_hint, failure_diagnostics,
                                             warning_entries)
from mtools.internal.fmu.request import RunRequest
from mtools.internal.fmu.resolve import ResolvedRun, resolve
from mtools.internal.fmu.result import to_frame
from mtools.internal.omc import build as omc_build
from mtools.internal.omc import workdir
from mtools.internal.omc.build import Build
from mtools.internal.omc.config import RunSettings
from mtools.internal.omc.parameters import flatten_parameters
from mtools.internal.omc.process import ProcessResult, execute

logger = logging.getLogger(__name__)

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
        build_variables={},
    )
    return run.model_name, _run(config.fmu_path, run, settings)


def simulate_export(build: Build, settings: RunSettings) -> pd.DataFrame:
    """Run the FMU exported by ``build`` with ``settings``; return its result.

    A requested parameter OMC fixed while exporting is exported into a variant FMU
    first, which is cached like any build; the other parameters are set on the variant
    per run, as ``Build.simulate`` does for native builds (ADR 0001).

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
        build_variables=build.variables,
    )
    if run.build_values:
        omc_build.log_variant(build.model_name, run.build_values)
        run_parameters = {
            key: value
            for key, value in flatten_parameters(settings.parameters).items()
            if key not in run.build_values
        }
        # A variant keeps the values it was built with, should it need a further variant.
        with omc_build.build(build.config, {**build.build_values, **run.build_values}) as variant:
            return simulate_export(variant, replace(settings, parameters=run_parameters))
    return _run(build.fmu_path, run, settings)


def _run(fmu_path: Path, run: ResolvedRun, settings: RunSettings) -> pd.DataFrame:
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
            partial = _read_partial(directory, run)
            raise _simulation_error(run, settings, result, directory, failure_diagnostics(result.output), partial)
        if warnings := warning_entries(result.output):
            logger.warning("Simulation of '%s' reported warnings:\n%s", run.model_name, "\n".join(warnings))
        array = np.load(directory / child.RESULT_FILE_NAME, allow_pickle=False)
        return to_frame(array, run)
    finally:
        workdir.discard(directory)


def _read_partial(directory: Path, run: ResolvedRun) -> pd.DataFrame | None:
    """Return the partial result the child saved in ``directory``, or ``None`` if there is none or it is unreadable."""
    try:
        array = np.load(directory / child.PARTIAL_FILE_NAME, allow_pickle=False)
        return to_frame(array, run) if array.size else None
    # OSError: no file; EOFError/ValueError: an empty or cut-off file, or a column missing from the
    # rows; IndexError: a non-structured array; SimulationError: rows to_frame can't convert.
    except (OSError, EOFError, ValueError, IndexError, SimulationError):
        logger.debug("No usable partial result in %s", directory, exc_info=True)
        return None


def _simulation_error(
    run: ResolvedRun,
    settings: RunSettings,
    result: ProcessResult,
    directory: Path,
    diagnostics: str,
    partial: pd.DataFrame | None,
) -> SimulationError:
    """Build the exception for a failed, crashed or timed-out FMU run.

    The one place where FMU run errors are assembled.
    """
    name = run.model_name
    if hint := cvode_hint(result.output, run.fmu_type):
        diagnostics = "\n".join(filter(None, [diagnostics, hint]))
    diagnostics = workdir.with_run_directory(diagnostics, directory)
    if result.timed_out:
        return SimulationTimeout(
            f"Simulation of '{name}' timed out after {settings.timeout:g} s:",
            model_name=name,
            diagnostics=diagnostics,
            partial_result=partial,
        )
    signal = result.signal
    header = f"Simulation of '{name}' crashed with {signal.name}:" if signal else f"Simulation of '{name}' failed:"
    return SimulationError(header, model_name=name, diagnostics=diagnostics, partial_result=partial)
