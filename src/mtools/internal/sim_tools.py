"""Internal simulation helpers backing :mod:`mtools.sim_tools`.

This module contains implementation details not intended for direct use:
solution-key normalization, single-run execution, multirun sweep plumbing,
and solution persistence. Public entry points live in
:mod:`mtools.sim_tools` and delegate here.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import hydra_zen
import pandas
from hydra.core.utils import JobReturn

import mtools.internal.session_tools as session_tools

if TYPE_CHECKING:
    import mtools.session_config as session_config

logger = logging.getLogger(__name__)


def _canonical_name(name: str) -> str:
    """Return a normalized form for comparing model and solution names.

    Args:
        name: Model or solution name to normalize.

    Returns:
        Lowercase name with non-alphanumeric runs collapsed to single
        underscores and surrounding underscores stripped.
    """
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()


def _normalize_solution_keys(
    solutions: dict[str, pandas.DataFrame], model_name: str | None = None
) -> dict[str, pandas.DataFrame]:
    """Normalize simulation result keys to match the requested model name.

    Backend-generated solution names may differ from the configured model name
    (for example ``pkg.SubModel`` vs ``pkg_SubModel``). When a single result can
    be unambiguously associated with the requested model, expose it under the
    configured model name so downstream code can rely on a stable key.

    Args:
        solutions: Mapping of solution names to simulation result data frames.
        model_name: Requested model name to normalize keys against. When
            ``None`` or empty, or when ``solutions`` is empty, the mapping is
            returned unchanged.

    Returns:
        Solution mapping keyed by the requested model name when a single
        result can be unambiguously associated with it, otherwise the input
        mapping unchanged.

    Raises:
        ValueError: If no solution key matches the requested model name.
    """
    if not model_name or not solutions:
        return solutions

    if model_name in solutions:
        return solutions

    canonical_model_name = _canonical_name(model_name)
    matching_keys = [
        key
        for key in solutions
        if _canonical_name(key) == canonical_model_name
        or _canonical_name(key) == _canonical_name(model_name.split(".")[-1])
    ]

    # Drops solutions if multiple models are in solutions.
    # Current API does only support simulation of a single model at at time.
    # TODO: Modify `pydelica` to not alter model names.
    if len(matching_keys) == 1:
        if len(solutions) > 1:
            logger.warning(
                "Simulation returned multiple solutions; only '%s' matches the "
                "requested model. Other solutions are discarded.",
                matching_keys[0],
            )
        return {model_name: solutions[matching_keys[0]]}

    if len(matching_keys) == 0:
        raise ValueError(f"No solution matches the requested model '{model_name}'. ")

    return solutions


def simulate_run(config: session_config.SimulationRun) -> dict[str, pandas.DataFrame]:
    """Run a configured simulation session and persist all solution tables.

    Args:
        config: Simulation run configuration including session factory settings
            and the model name to simulate.

    Returns:
        Mapping of solution names to simulation result data frames.
    """
    director: session_tools.SessionDirector = hydra_zen.instantiate(config.session)
    session = director.make_session()
    session.simulate(model_name=config.model_name)
    solutions = session.get_solutions()
    return _normalize_solution_keys(solutions, model_name=config.model_name)


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
