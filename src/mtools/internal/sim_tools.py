"""Internal simulation helpers backing :mod:`mtools.sim_tools`.

This module contains implementation details not intended for direct use:
single-run execution, multirun sweep plumbing, and solution persistence.
Public entry points live in :mod:`mtools.sim_tools` and delegate here.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import hydra_zen
import pandas
from hydra.core.utils import JobReturn
from omegaconf import DictConfig

import mtools.internal.omc.build as omc_build
import mtools.internal.run_config as run_config

if TYPE_CHECKING:
    import mtools.session_config as session_config


def simulate_run(config: session_config.SimulationRun | DictConfig) -> dict[str, pandas.DataFrame]:
    """Validate a run config, build its model (or take the build from the cache) and run it.

    ``hydra_zen.instantiate`` only turns the config into config objects; building and
    running happen afterwards, so their exceptions reach the caller unwrapped. Builds
    and run directories this call creates without caching them are deleted when it ends.

    Args:
        config: Run config, as config objects or as a composed Hydra config.

    Returns:
        The result keyed by ``build.model_name``.

    Raises:
        mtools.errors.ConfigError: The config is invalid; nothing was built.
        mtools.errors.BuildError: Translating or compiling the model failed.
        mtools.errors.SimulationError: The run failed or timed out.
    """
    run = run_config.instantiate(config)
    build_config, settings = run_config.validate(run)
    with omc_build.build(build_config) as built:
        return {build_config.model_name: built.simulate(settings)}


def build_multirun_overrides(overrides: list[str], sweep_dir: str | Path | None) -> list[str]:
    """Build the full override list for a Hydra multirun sweep.

    Args:
        overrides: Sweep overrides provided by the caller.
        sweep_dir: Optional ``hydra.sweep.dir`` value to append.

    Returns:
        A new override list with the sweep directory (when given) and
        ``hydra.job.chdir=False`` appended.
    """
    full_overrides = list(overrides)
    if sweep_dir is not None:
        full_overrides.append(f"hydra.sweep.dir={sweep_dir}")
    full_overrides.append("hydra.job.chdir=False")
    return full_overrides


def launch_sweep(
    config: type[session_config.SimulationRun], overrides: list[str]
) -> list[JobReturn]:
    """Launch a Hydra multirun sweep and return the flat job list.

    Args:
        config: Run config type to fan out via ``hydra_zen.launch``.
        overrides: Full override list including sweep values.

    Returns:
        Flat list of per-job results, unwrapping the nested list that
        ``hydra_zen.launch`` returns for multirun sweeps.
    """
    launched = hydra_zen.launch(
        config, lambda job_config: simulate_run(job_config), overrides=overrides, multirun=True, version_base=None
    )
    first = launched[0]
    job_iter = first if isinstance(first, (list, tuple)) else launched
    return list(job_iter)


def write_solutions(solutions: dict[str, pandas.DataFrame], output_path: str) -> None:
    """Write each solution data frame to CSV in the configured output path.

    Args:
        solutions: Mapping of solution names to pandas data frames.
        output_path: Directory path where CSV files are written.
    """
    for name, solution in solutions.items():
        solution.to_csv(f"{output_path}/{name}.csv", index=False)
