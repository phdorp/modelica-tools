import re

import hydra_zen
import pandas
from hydra.core.hydra_config import HydraConfig
import logging

import mtools.session_config as session_config
import mtools.internal.session_tools as session_tools

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

    if len(solutions) == 1:
        only_key, only_value = next(iter(solutions.items()))
        return {model_name: only_value}

    return solutions


def simulate(config: session_config.SimulationRun):
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

def save_solutions(solutions: dict[str, pandas.DataFrame], output_path: str):
    """Write each solution data frame to CSV in the configured output path.

    Args:
        solutions: Mapping of solution names to pandas data frames.
        output_path: Directory path where CSV files are written.
    """
    for name, solution in solutions.items():
        solution.to_csv(f"{output_path}/{name}.csv", index=False)
