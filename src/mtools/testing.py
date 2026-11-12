"""Generic pytest base classes for Modelica experiment tests.

Requires the ``testing`` extra (``pip install modelica-tools[testing]``)
for the ``pytest``/``numpy`` imports used below.

Test classes inherit the aliases directly and provide model-specific wiring
via pytest fixtures; this module contains no model imports::

    class TestStandstill(Experiment):
        name = "standstill"

        def test_position_unchanged(self):
            ...

Required fixtures (provided once per test module; ``scope="module"``
suffices, and a per-class fixture definition overrides the module-level
one for that class)::

    @pytest.fixture(scope="module")
    def registry():
        return kinematic_registry

Which fixtures each alias needs:

- :data:`Experiment` / :data:`Experiments`: ``registry``.
- :data:`ExperimentSweep` / :data:`ExperimentSweeps`: ``registry``.
- :data:`ExperimentReference` / :data:`ExperimentsReference`:
  ``registry`` + ``reference_run_config``.
- :data:`ExperimentSweepReference` / :data:`ExperimentSweepsReference`:
  ``registry`` + ``reference_run_config``.

A run config holds exactly one ``build.model_name``, so each base reads the
simulated model's name from its composed config instead of a separate fixture.
The reference comparison bases simulate the candidate model composed from the
experiment's registered (default) run config and the reference model composed
from the same ``registry`` with ``reference_run_config``. The two run configs
own their own build config (model name, source, target, libraries) and run
settings. The bases then expose both result sets
and ``assert_matches_reference()``.

Experiments are resolved by name: single runs compose via
``registry.compose_experiment(name)`` (and
``registry.compose_experiment(name, run_config=reference_run_config)`` for the
reference) and read the selected model name from the composed config; sweeps
use ``registry.get_experiment_run_config(name)`` (and the
``run_config=reference_run_config`` overload) as multirun base and read each
job's model name from its composed config.
"""

from __future__ import annotations

import dataclasses
from abc import ABC
from collections.abc import Hashable, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import (TYPE_CHECKING, Any, ClassVar, Generic, Protocol, TypeAlias,
                    TypeVar, cast, runtime_checkable)

import numpy as np
import pandas as pd
import pytest

import mtools.internal.testing as _internal
from mtools import sim_tools

if TYPE_CHECKING:
    from omegaconf import DictConfig

    import mtools.session_config as session_config
    from mtools.hydra_registry import RunConfig

__all__ = [
    "DataclassInstance",
    "Experiment",
    "ExperimentReference",
    "ExperimentSweep",
    "ExperimentSweepReference",
    "ExperimentSweeps",
    "ExperimentSweepsReference",
    "Experiments",
    "ExperimentsReference",
    "Registry",
    "SweepScalar",
    "SweepValue",
]

#: Scalar types expressible as Hydra override primitives.
SweepScalar: TypeAlias = bool | int | float | str | None


@runtime_checkable
class DataclassInstance(Protocol):
    """Structural type for dataclass instances accepted as sweep values."""

    __dataclass_fields__: ClassVar[dict[str, dataclasses.Field[Any]]]


#: All sweep value types expressible in Hydra override grammar: scalars,
#: lists/tuples (list containers), string-keyed dicts (dict containers),
#: and dataclass instances (coerced via ``asdict``, e.g. ``State``).
SweepValue: TypeAlias = (
    SweepScalar | DataclassInstance | list["SweepValue"] | tuple["SweepValue", ...] | dict[str, "SweepValue"]
)

NameType = TypeVar("NameType", bound="str | list[str]")
ResultType = TypeVar("ResultType")
SweepResultType = TypeVar("SweepResultType")


def _format_model_names(model_names: Mapping[str, str | Sequence[str]]) -> str:
    """Return quoted, distinct model names from an experiment-to-names mapping.

    Values are either a single model name (single-run bases) or a sequence of
    names (sweep bases, where every job is inspected).
    """
    names: set[str] = set()
    for value in model_names.values():
        if isinstance(value, str):
            names.add(value)
        else:
            names.update(value)
    return ", ".join(repr(name) for name in sorted(names))


@runtime_checkable
class Registry(Protocol):
    """Registry seam required by the experiment test bases.

    :class:`mtools.hydra_registry.HydraZenRegistry` satisfies it; test doubles
    only need to implement these three methods.
    """

    def activated(self) -> AbstractContextManager[None]:
        """Let Hydra see exactly this registry's configs inside the block."""
        ...

    def compose_experiment(
        self,
        name: str,
        run_config: RunConfig | str | None = None,
        overrides: list[str] | None = None,
    ) -> DictConfig:
        """Compose the config for experiment ``name``."""
        ...

    def get_experiment_run_config(
        self, name: str, run_config: RunConfig | str | None = None
    ) -> RunConfig:
        """Return the run config experiment ``name`` is swept with."""
        ...


class ExperimentBase(ABC):
    """Shared config for experiment tests.

    Requires the ``registry`` pytest fixture (the Hydra registry experiments
    are composed from and sweeps resolve their base config from). Test modules
    provide it once, e.g.::

        @pytest.fixture(scope="module")
        def registry():
            return kinematic_registry
    """

    #: Absolute tolerance used by test assertions.
    eps: ClassVar[float] = np.finfo(float).eps
    #: Relative tolerance used by test assertions.
    rtol: ClassVar[float] = 0.0
    #: Compare reference tests on the reference's time points (see
    #: :meth:`_ReferenceComparisonMixin.assert_matches_reference`).
    interpolate: ClassVar[bool] = False


class _ReferenceComparisonMixin(Generic[ResultType]):
    """Compare candidate results against reference results on demand."""

    #: Absolute tolerance used by :meth:`assert_matches_reference`.
    eps: ClassVar[float]
    #: Relative tolerance used by :meth:`assert_matches_reference`.
    rtol: ClassVar[float]
    #: Align the candidate onto the reference's time points first.
    interpolate: ClassVar[bool]
    results: ResultType
    reference_results: ResultType

    def _comparison_context(self) -> str:
        """Return the failure context naming the test class and model pair.

        The model pair is included when the fetch phase recorded it on the
        class (``_candidate_model_names`` / ``_reference_model_names``);
        direct calls that never ran a fetch fall back to the class and
        experiment name only.
        """
        context = f"{type(self).__name__}(name={getattr(self, 'name', None)!r}"
        candidate = getattr(type(self), "_candidate_model_names", None)
        reference = getattr(type(self), "_reference_model_names", None)
        if candidate and reference:
            context += (
                f", candidate={_format_model_names(candidate)}"
                f" vs reference={_format_model_names(reference)}"
            )
        return f"{context})"

    def assert_matches_reference(self) -> None:
        """Assert that every candidate solution matches its reference solution."""
        _internal.assert_solutions_match(
            cast("_internal.Solution", self.results),
            cast("_internal.Solution", self.reference_results),
            atol=self.eps,
            rtol=self.rtol,
            interpolate=self.interpolate,
            context=self._comparison_context(),
        )


class ExperimentT(ExperimentBase, Generic[NameType, ResultType]):
    """Run one experiment per name via ``registry.compose_experiment`` + single-run simulate.

    Requires the ``registry`` pytest fixture (see :class:`ExperimentBase`); the
    simulated model's name is read from each composed config.

    Subclasses set ``name`` to a single experiment name (via
    :data:`Experiment`) or a list of names (via :data:`Experiments`); after
    the class-scoped ``run_experiment`` fixture runs, ``results`` holds the
    solution table (single name) or a mapping of name to solution table.
    """

    #: Experiment name(s) to run.
    name: NameType
    #: Solution table(s) populated by the ``run_experiment`` fixture.
    results: ResultType
    #: Model name per experiment recorded by the fetch phase (private).
    _candidate_model_names: ClassVar[dict[str, str]]

    @classmethod
    def fetch_experiment(cls, registry: Registry):
        """Run each experiment in ``cls.name`` and store solution tables in ``cls.results``.

        Args:
            registry: Hydra registry used to compose each run config. The
                composed config's ``build.model_name`` keys the model's
                solution table.
        """
        names = [cls.name] if isinstance(cls.name, str) else cls.name
        results = {}
        candidate_model_names = {}
        for name in names:
            config = registry.compose_experiment(name)
            candidate_model_names[name] = config.build.model_name
            results[name] = sim_tools.simulate(cast("session_config.SimulationRun", config))[
                config.build.model_name
            ]
        cls._candidate_model_names = candidate_model_names
        cls.results = cast(ResultType, results[cls.name] if isinstance(cls.name, str) else results)

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_experiment(cls, registry: Registry):
        """Class-scoped fixture populating ``results`` before any test runs."""
        cls.fetch_experiment(registry)


# Single experiment: ``name`` is one experiment name, ``results`` its solution table.
Experiment = ExperimentT[str, pd.DataFrame]
# Multiple experiments: ``name`` is a list of names, ``results`` maps name to solution table.
Experiments = ExperimentT[list[str], dict[str, pd.DataFrame]]


class ExperimentReferenceT(
    ExperimentT[NameType, ResultType], _ReferenceComparisonMixin[ResultType]
):
    """Run an experiment for a candidate and a reference model.

    Requires the ``registry`` and ``reference_run_config`` pytest fixtures.
    The candidate experiment is composed from ``registry``'s default run
    config; the reference experiment with the same name is composed from the
    same ``registry`` with ``run_config=reference_run_config``. The two run
    configs own their own build config and run settings. Each side's model name is
    read from its composed config.
    """

    reference_results: ResultType
    #: Reference model name per experiment recorded by the fetch phase (private).
    _reference_model_names: ClassVar[dict[str, str]]

    @classmethod
    def fetch_reference_experiment(
        cls,
        registry: Registry,
        reference_run_config: RunConfig,
    ) -> None:
        """Run the experiment for both the candidate and reference models.

        Args:
            registry: Hydra registry used to compose both run configs.
            reference_run_config: Run config composing the reference experiment.
        """
        super().fetch_experiment(registry)
        names = [cls.name] if isinstance(cls.name, str) else cls.name
        reference_results = {}
        reference_model_names = {}
        for name in names:
            config = registry.compose_experiment(name, run_config=reference_run_config)
            reference_model_names[name] = config.build.model_name
            reference_results[name] = sim_tools.simulate(cast("session_config.SimulationRun", config))[
                config.build.model_name
            ]
        cls._reference_model_names = reference_model_names
        cls.reference_results = cast(
            ResultType,
            reference_results[cls.name] if isinstance(cls.name, str) else reference_results,
        )

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_experiment(
        cls,
        registry: Registry,
        reference_run_config: RunConfig,
    ):
        """Class-scoped fixture populating candidate and reference results."""
        cls.fetch_reference_experiment(registry, reference_run_config)


# Single reference comparison: ``results`` and ``reference_results`` are solution tables.
ExperimentReference = ExperimentReferenceT[str, pd.DataFrame]
# Multiple reference comparisons: each result attribute maps name to solution table.
ExperimentsReference = ExperimentReferenceT[list[str], dict[str, pd.DataFrame]]


class ExperimentSweepT(ExperimentBase, Generic[NameType, SweepResultType]):
    """Sweep parameters across ``sweep_params`` via multirun simulate.

    Requires the ``registry`` pytest fixture (see :class:`ExperimentBase`);
    the multirun base config is the run config the swept experiment was
    registered with, resolved via ``registry.get_experiment_run_config(name)``.
    Each job's model name is read from its composed config.

    Subclasses set ``name`` to a single experiment name (via
    :data:`ExperimentSweep`) or a list of names (via
    :data:`ExperimentSweeps`) plus ``sweep_params`` mapping each swept
    parameter name to its values; after the class-scoped ``run_sweep``
    fixture runs, ``results`` maps each cartesian-product tuple (in
    ``sweep_params`` insertion order) to its solution table (single name)
    or each name to such a mapping.
    """

    #: Hydra package prefix of swept parameters, i.e. overrides are
    #: ``"<prefix>.<param>=<comma-separated values>"`` (one per entry).
    sweep_param_prefix: ClassVar[str] = "settings.parameters"
    #: Swept parameter names (relative to ``sweep_param_prefix``) mapped to
    #: the values swept over. Values must be Hydra-expressible: scalars
    #: (``bool``, ``int``, ``float``, ``str``, ``None``), ``dict`` (dict
    #: container, e.g. ``State`` as ``{"px": ..., "py": ..., "theta": ...}``),
    #: dataclass instances (coerced via ``asdict``, e.g. ``State(...)``),
    #: or ``tuple``/``list`` — mapped positionally onto the target's field
    #: names for mapping targets (e.g. ``(px, py, theta)`` for ``state_0``),
    #: serialized as a list container otherwise.
    sweep_params: ClassVar[dict[str, list[SweepValue]]]

    #: Experiment name(s) to sweep.
    name: NameType
    #: Per-value solution table(s) populated by the ``run_sweep`` fixture.
    results: SweepResultType
    #: Candidate model names per experiment recorded by the sweep phase (private).
    _candidate_model_names: ClassVar[dict[str, list[str]]]
    #: Reference model names per experiment recorded by a reference sweep (private).
    _reference_model_names: ClassVar[dict[str, list[str]]]

    @classmethod
    def run_single_sweep(
        cls,
        name: str,
        registry: Registry,
        tmp_path_factory: pytest.TempPathFactory,
        run_config: RunConfig | None = None,
    ) -> dict[tuple[Hashable, ...], pd.DataFrame]:
        """Run one multirun sweep and map each parameter combination to its solution table.

        Args:
            name: Experiment name to sweep.
            registry: Hydra registry providing the experiment's base run
                config via ``get_experiment_run_config(name)``.
            tmp_path_factory: Pytest factory used for the sweep directory.
            run_config: Optional run config whose experiment is swept;
                ``None`` uses the registry's default.

        Returns:
            Mapping of cartesian-product tuple (in ``sweep_params``
            insertion order) to solution table. Each table is attributed
            via its own job's composed config, so Hydra launch order does
            not affect the mapping.

        Raises:
            AssertionError: If the number of sweep results differs from
                the cartesian-product size.
            ValueError: If distinct sweep values freeze to the same result
                key (e.g. ``True`` vs ``1``, or ``1`` vs ``1.0``, which
                compare equal as dict keys); if normalized sweep values
                are ambiguous; if a job's composed config matches no
                swept combination or matches twice; or if a job's composed
                config lacks ``build.model_name``.
        """
        plan = _internal._SweepPlan(cls.sweep_params, cls.sweep_param_prefix, name, registry, run_config=run_config)
        sweep_results = plan.launch(registry, tmp_path_factory)
        assert len(sweep_results) == len(plan.combos), (
            f"expected {len(plan.combos)} sweep results, got {len(sweep_results)}"
        )
        results = plan.attribute(sweep_results)
        if run_config is None:
            candidate_model_names = dict(getattr(cls, "_candidate_model_names", {}))
            candidate_model_names[name] = plan.model_names
            cls._candidate_model_names = candidate_model_names
        else:
            reference_model_names = dict(getattr(cls, "_reference_model_names", {}))
            reference_model_names[name] = plan.model_names
            cls._reference_model_names = reference_model_names
        return results

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_sweep(cls, registry: Registry, tmp_path_factory: pytest.TempPathFactory):
        """Class-scoped fixture populating ``results`` before any test runs."""
        cls.fetch_sweep(registry, tmp_path_factory)

    @classmethod
    def fetch_sweep(cls, registry: Registry, tmp_path_factory: pytest.TempPathFactory) -> None:
        """Sweep each experiment in ``cls.name`` and store per-combination solution tables in ``cls.results``.

        Args:
            registry: Hydra registry providing each experiment's base run
                config via ``get_experiment_run_config(name)``.
            tmp_path_factory: Pytest factory used for the sweep directory.
        """
        names = [cls.name] if isinstance(cls.name, str) else cls.name
        results = {name: cls.run_single_sweep(name, registry, tmp_path_factory) for name in names}
        cls.results = cast(SweepResultType, results[cls.name] if isinstance(cls.name, str) else results)


# Single sweep: ``results`` maps each cartesian-product tuple to its solution table.
ExperimentSweep = ExperimentSweepT[str, dict[tuple[Hashable, ...], pd.DataFrame]]
# Multiple sweeps: ``results`` maps each experiment name to such a per-combination mapping.
ExperimentSweeps = ExperimentSweepT[list[str], dict[str, dict[tuple[Hashable, ...], pd.DataFrame]]]


class ExperimentSweepReferenceT(
    ExperimentSweepT[NameType, SweepResultType], _ReferenceComparisonMixin[SweepResultType]
):
    """Sweep an experiment for a candidate and a reference model.

    Requires the ``registry`` and ``reference_run_config`` pytest fixtures plus
    the builtin ``tmp_path_factory``. The reference sweep uses the same
    parameter combinations and result attribution as the candidate sweep but
    composes its base run config from the same ``registry`` with
    ``run_config=reference_run_config`` and writes to its own temporary sweep
    directory. Each job's model name is read from its composed config. The two
    run configs own their own build config and run settings.
    """

    reference_results: SweepResultType

    @classmethod
    def run_single_reference_sweep(
        cls,
        name: str,
        registry: Registry,
        reference_run_config: RunConfig,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> dict[tuple[Hashable, ...], pd.DataFrame]:
        """Run one reference sweep by reusing the candidate sweep with a different base run config.

        Args:
            name: Experiment name to sweep in ``registry``.
            registry: Hydra registry providing the reference experiment's
                base run config via
                ``get_experiment_run_config(name, run_config=reference_run_config)``.
            reference_run_config: Run config composing the reference sweep.
            tmp_path_factory: Pytest factory used for the sweep directory.

        Returns:
            Mapping of cartesian-product tuple to reference solution table.
        """
        return super().run_single_sweep(
            name, registry, tmp_path_factory, run_config=reference_run_config
        )

    @classmethod
    def fetch_reference_sweep(
        cls,
        registry: Registry,
        reference_run_config: RunConfig,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """Sweep the experiment for both the candidate and reference models.

        Args:
            registry: Hydra registry providing each experiment's base run
                config via ``get_experiment_run_config(name)``.
            reference_run_config: Run config composing each reference
                experiment's base run config.
            tmp_path_factory: Pytest factory used for the sweep directories.
        """
        super().fetch_sweep(registry, tmp_path_factory)
        names = [cls.name] if isinstance(cls.name, str) else cls.name
        reference_results = {
            name: cls.run_single_reference_sweep(name, registry, reference_run_config, tmp_path_factory)
            for name in names
        }
        cls.reference_results = cast(
            SweepResultType,
            reference_results[cls.name] if isinstance(cls.name, str) else reference_results,
        )

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_sweep(
        cls,
        registry: Registry,
        reference_run_config: RunConfig,
        tmp_path_factory: pytest.TempPathFactory,
    ):
        """Class-scoped fixture populating candidate and reference sweep results."""
        cls.fetch_reference_sweep(registry, reference_run_config, tmp_path_factory)


# Single reference sweep: both result attributes map each combination to its table.
ExperimentSweepReference = ExperimentSweepReferenceT[str, dict[tuple[Hashable, ...], pd.DataFrame]]
# Multiple reference sweeps: both result attributes map name to such a mapping.
ExperimentSweepsReference = ExperimentSweepReferenceT[
    list[str], dict[str, dict[tuple[Hashable, ...], pd.DataFrame]]
]
