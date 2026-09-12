import dataclasses
from pathlib import Path
from typing import Literal, overload

import pandas
from omegaconf import DictConfig

import mtools.internal.sim_tools as _internal
import mtools.session_config as session_config

__all__ = ["SweepResult", "save_solutions", "simulate"]


@dataclasses.dataclass
class SweepResult:
    """Per-job result of a multirun sweep launched via :func:`simulate`."""

    #: Composed job config for this sweep point.
    config: DictConfig
    #: Simulation solutions for this sweep point.
    solutions: dict[str, pandas.DataFrame]


@overload
def simulate(config: session_config.SimulationRun) -> dict[str, pandas.DataFrame]: ...


@overload
def simulate(
    config: type[session_config.SimulationRun],
    *,
    overrides: list[str],
    multirun: Literal[True],
    sweep_dir: str | Path | None = None,
) -> list[SweepResult]: ...


def simulate(
    config: session_config.SimulationRun | type[session_config.SimulationRun],
    *,
    overrides: list[str] | None = None,
    multirun: bool = False,
    sweep_dir: str | Path | None = None,
) -> dict[str, pandas.DataFrame] | list[SweepResult]:
    """Run a single simulation or a multirun sweep.

    Single-run: ``simulate(composed_config)`` instantiates the session and
    returns solution tables.

    Multirun: ``simulate(run_config_type, overrides=[...], multirun=True)``
    fans out via ``hydra_zen.launch``; each job runs the single-run path.

    Args:
        config: Composed run config (single-run) or run config type
            (multirun, e.g. ``run_default`` from the registry).
        overrides: Sweep overrides for multirun (e.g.
            ``["session.parameters.phi=0.1,0.2"]``). Required if multirun.
        multirun: Whether to launch a Hydra multirun sweep.
        sweep_dir: Optional ``hydra.sweep.dir`` value for the sweep.

    Returns:
        Single-run solution mapping, or a list of per-job sweep results.
    """
    if not multirun:
        return _internal.simulate_run(config)  # type: ignore[arg-type]
    if overrides is None:
        raise ValueError("Multirun simulate() requires 'overrides' with sweep values.")
    full_overrides = _internal.build_multirun_overrides(overrides, sweep_dir)
    job_iter = _internal.launch_sweep(config, full_overrides)  # type: ignore[arg-type]
    return [SweepResult(config=job.cfg, solutions=job.return_value) for job in job_iter]


def save_solutions(solutions: dict[str, pandas.DataFrame], output_path: str):
    """Write each solution data frame to CSV in the configured output path.

    Args:
        solutions: Mapping of solution names to pandas data frames.
        output_path: Directory path where CSV files are written.
    """
    _internal.write_solutions(solutions, output_path)
