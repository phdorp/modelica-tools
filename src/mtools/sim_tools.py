import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Literal, overload

import pandas
from omegaconf import DictConfig

import mtools.internal.result_files as result_files
import mtools.internal.sim_tools as _internal
import mtools.session_config as session_config

if TYPE_CHECKING:
    from mtools.internal.hydra_state import ActivatableRegistry

__all__ = ["SweepResult", "load_solution", "save_solutions", "simulate"]


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
    registry: "ActivatableRegistry | None" = None,
) -> list[SweepResult]: ...


def simulate(
    config: session_config.SimulationRun | type[session_config.SimulationRun],
    *,
    overrides: list[str] | None = None,
    multirun: bool = False,
    sweep_dir: str | Path | None = None,
    registry: "ActivatableRegistry | None" = None,
) -> dict[str, pandas.DataFrame] | list[SweepResult]:
    """Run a single simulation or a multirun sweep.

    Single-run: ``simulate(config)`` validates the run config, builds the model
    (or reuses a cached build), runs it and returns the result keyed by
    ``build.model_name``. A given FMU (``FmuFile``) needs no build; its result is
    keyed by ``build.model_name``, or by the FMU's ``modelName`` when that is unset.

    Multirun: ``simulate(run_config_type, overrides=[...], multirun=True,
    registry=registry)`` fans out via ``hydra_zen.launch``; each job runs the
    single-run path. The sweep sees only ``registry``'s configs and leaves
    Hydra's global config store, the registry and logging as it found them.

    Args:
        config: Composed run config (single-run) or run config type
            (multirun, e.g. ``run_default`` from the registry).
        overrides: Sweep overrides for multirun (e.g.
            ``["settings.parameters.phi=0.1,0.2"]``). Required if multirun.
        multirun: Whether to launch a Hydra multirun sweep.
        sweep_dir: Optional ``hydra.sweep.dir`` value for the sweep.
        registry: Registry the sweep resolves config groups (settings,
            experiments) from. Without one, the sweep resolves them from
            Hydra's global config store, filled by ``add_to_hydra_store()``.

    Returns:
        Single-run solution mapping, or a list of per-job sweep results.

    Raises:
        ImportError: The run is an FMU run (a given or exported FMU) and FMPy isn't
            installed (``modelica-tools[fmu]``).
    """
    if not multirun:
        return _internal.simulate_run(config)  # type: ignore[arg-type]
    if overrides is None:
        raise ValueError("Multirun simulate() requires 'overrides' with sweep values.")
    full_overrides = _internal.build_multirun_overrides(overrides, sweep_dir)
    job_iter = _internal.launch_sweep(config, full_overrides, registry)  # type: ignore[arg-type]
    results = []
    for job in job_iter:
        # A multirun job always carries its composed config; hydra-zen types it
        # as optional because single-run returns may omit it.
        assert job.cfg is not None
        results.append(SweepResult(config=job.cfg, solutions=job.return_value))
    return results


def save_solutions(
    solutions: dict[str, pandas.DataFrame],
    output_path: str | Path,
    output_format: session_config.OutputFormat = "mat",
) -> None:
    """Write each solution to ``<output_path>/<name>.<output_format>``.

    ``mat`` writes OMC's MATLAB v4 result layout with the column types stored alongside,
    so the file reads back with ``bool`` and ``int64`` columns; OpenModelica's
    ``readSimulationResult`` opens it too. ``csv`` writes Booleans as ``True``/``False``.
    The plotting tool reads both.

    Args:
        solutions: Mapping of solution names to pandas data frames, as ``simulate``
            returns them.
        output_path: Existing directory the files are written to.
        output_format: ``"mat"`` (default) or ``"csv"``; a run config carries it as
            ``output_format``.

    Raises:
        ValueError: ``output_format`` is neither ``"mat"`` nor ``"csv"``, or a
            solution has no rows and is saved as ``mat``.
    """
    result_files.write_solutions(solutions, output_path, output_format)


def load_solution(path: str | Path) -> pandas.DataFrame:
    """Read one solution file that ``save_solutions`` wrote, chosen by its suffix.

    A ``.mat`` file reads back exactly as it was saved, with ``bool`` and ``int64``
    columns. A ``.csv`` file reads back with pandas' type inference: ``True``/``False``
    columns become ``bool``, and Real columns stay ``float64`` because CSV writes them
    with a decimal point (``2.0``). An OMC ``_res.mat`` file is read with every column
    as ``float64``.

    Args:
        path: A ``.mat`` or ``.csv`` file.

    Raises:
        ValueError: The suffix is neither ``.mat`` nor ``.csv``, or a ``.mat`` file is
            not in OMC's result layout.
    """
    return result_files.read_result_file(path)
