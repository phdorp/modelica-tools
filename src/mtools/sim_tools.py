import dataclasses
import logging
import re
from pathlib import Path
from typing import Literal, overload

import hydra_zen
import pandas
from hydra.core.hydra_config import HydraConfig
from hydra.core.utils import JobReturn

import mtools.internal.session_tools as session_tools
import mtools.session_config as session_config

logger = logging.getLogger(__name__)


def _canonical_name(name: str) -> str:
    """Return a normalized form for comparing model and solution names."""
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()


def _normalize_solution_keys(
    solutions: dict[str, pandas.DataFrame], model_name: str | None = None
) -> dict[str, pandas.DataFrame]:
    """Normalize simulation result keys to match the requested model name.

    Backend-generated solution names may differ from the configured model name
    (for example ``pkg.SubModel`` vs ``pkg_SubModel``). When a single result can
    be unambiguously associated with the requested model, expose it under the
    configured model name so downstream code can rely on a stable key.
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
        raise ValueError(
            f"No solution matches the requested model '{model_name}'. "
        )

    return solutions


def simulate_run(config: session_config.SimulationRun):
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


@dataclasses.dataclass
class SweepResult:
    """Per-job result of a multirun sweep launched via :func:`simulate`."""

    #: Composed job config for this sweep point.
    config: session_config.SimulationRun
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
        return simulate_run(config)  # type: ignore[arg-type]
    if overrides is None:
        raise ValueError("Multirun simulate() requires 'overrides' with sweep values.")
    full_overrides = list(overrides)
    if sweep_dir is not None:
        full_overrides.append(f"hydra.sweep.dir={sweep_dir}")
    full_overrides.append("hydra.job.chdir=False")

    launched = hydra_zen.launch(
        config, lambda config: simulate_run(config), overrides=full_overrides, multirun=True, version_base=None
    )
    first = launched[0]
    job_iter = first if isinstance(first, (list, tuple)) else launched
    return [SweepResult(config=job.cfg, solutions=job.return_value) for job in job_iter]


def save_solutions(solutions: dict[str, pandas.DataFrame], output_path: str):
    """Write each solution data frame to CSV in the configured output path.

    Args:
        solutions: Mapping of solution names to pandas data frames.
        output_path: Directory path where CSV files are written.
    """
    for name, solution in solutions.items():
        solution.to_csv(f"{output_path}/{name}.csv", index=False)
