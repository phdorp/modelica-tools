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
    def model_name():
        return MODEL_NAME

    @pytest.fixture(scope="module")
    def registry():
        return kinematic_registry

Which fixtures each alias needs:

- :data:`Experiment` / :data:`Experiments`: ``model_name`` + ``registry``.
- :data:`ExperimentSweep` / :data:`ExperimentSweeps`: ``model_name`` + ``registry``.

Experiments are resolved by name: single runs compose via
``registry.compose_experiment(name)``, sweeps use
``registry.get_experiment_run_config(name)`` as multirun base.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Hashable
from typing import (TYPE_CHECKING, Any, ClassVar, Generic, Protocol, TypeAlias,
                    TypeVar, cast, runtime_checkable)

import numpy as np
import pandas as pd
import pytest

import mtools.internal.testing as _internal
from mtools import sim_tools

if TYPE_CHECKING:
    from mtools.hydra_registry import HydraZenRegistry

__all__ = [
    "DataclassInstance",
    "Experiment",
    "ExperimentSweep",
    "ExperimentSweeps",
    "Experiments",
    "SweepScalar",
    "SweepValue",
]

#: Scalar types expressible as Hydra override primitives.
SweepScalar: TypeAlias = bool | int | float | str | None


@runtime_checkable
class DataclassInstance(Protocol):
    """Structural type for dataclass instances accepted as sweep values."""

    __dataclass_fields__: ClassVar[dict[str, Any]]


#: All sweep value types expressible in Hydra override grammar: scalars,
#: lists/tuples (list containers), string-keyed dicts (dict containers),
#: and dataclass instances (coerced via ``asdict``, e.g. ``State``).
SweepValue: TypeAlias = (
    SweepScalar | DataclassInstance | list["SweepValue"] | tuple["SweepValue", ...] | dict[str, "SweepValue"]
)

NameType = TypeVar("NameType", bound="str | list[str]")
ResultType = TypeVar("ResultType")
SweepResultType = TypeVar("SweepResultType")


class ExperimentBase(ABC):
    """Shared config for experiment tests.

    Requires the ``model_name`` pytest fixture (the simulated model name
    used to select solution tables) and the ``registry`` pytest fixture
    (the Hydra registry experiments are composed from and sweeps resolve
    their base config from). Test modules provide each fixture once, e.g.::

        @pytest.fixture(scope="module")
        def model_name():
            return MODEL_NAME
    """

    #: Absolute tolerance used by test assertions.
    eps: ClassVar[float] = np.finfo(float).eps


class ExperimentT(ExperimentBase, Generic[NameType, ResultType]):
    """Run one experiment per name via ``registry.compose_experiment`` + single-run simulate.

    Requires the ``model_name`` and ``registry`` pytest fixtures (see
    :class:`ExperimentBase`).

    Subclasses set ``name`` to a single experiment name (via
    :data:`Experiment`) or a list of names (via :data:`Experiments`); after
    the class-scoped ``run_experiment`` fixture runs, ``results`` holds the
    solution table (single name) or a mapping of name to solution table.
    """

    #: Experiment name(s) to run.
    name: NameType
    #: Solution table(s) populated by the ``run_experiment`` fixture.
    results: ResultType

    @classmethod
    def fetch_experiment(cls, registry: HydraZenRegistry, model_name: str):
        """Run each experiment in ``cls.name`` and store solution tables in ``cls.results``.

        Args:
            registry: Hydra registry used to compose the run config.
            model_name: Simulated model name selecting the solution table.
        """
        names = [cls.name] if isinstance(cls.name, str) else cls.name
        results = {name: sim_tools.simulate(registry.compose_experiment(name))[model_name] for name in names}
        cls.results = cast(ResultType, results[cls.name] if isinstance(cls.name, str) else results)

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_experiment(cls, registry: HydraZenRegistry, model_name: str):
        """Class-scoped fixture populating ``results`` before any test runs."""
        cls.fetch_experiment(registry, model_name)


# Single experiment: ``name`` is one experiment name, ``results`` its solution table.
Experiment = ExperimentT[str, pd.DataFrame]
# Multiple experiments: ``name`` is a list of names, ``results`` maps name to solution table.
Experiments = ExperimentT[list[str], dict[str, pd.DataFrame]]


class ExperimentSweepT(ExperimentBase, Generic[NameType, SweepResultType]):
    """Sweep parameters across ``sweep_params`` via multirun simulate.

    Requires the ``model_name`` and ``registry`` pytest fixtures (see
    :class:`ExperimentBase`); the multirun base config is the run config
    the swept experiment was registered with, resolved via
    ``registry.get_experiment_run_config(name)``.

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
    sweep_param_prefix: ClassVar[str] = "session.parameters"
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

    @classmethod
    def run_single_sweep(
        cls, name: str, model_name: str, registry: HydraZenRegistry, tmp_path_factory: Any
    ):
        """Run one multirun sweep and map each parameter combination to its solution table.

        Args:
            name: Experiment name to sweep.
            model_name: Simulated model name selecting the solution table.
            registry: Hydra registry providing the experiment's base run
                config via ``get_experiment_run_config(name)``.
            tmp_path_factory: Pytest factory used for the sweep directory.

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
                are ambiguous; or if a job's composed config matches no
                swept combination or matches twice.
        """
        plan = _internal._SweepPlan(cls.sweep_params, cls.sweep_param_prefix, name, registry)
        sweep_results = plan.launch(registry, tmp_path_factory)
        assert len(sweep_results) == len(plan.combos), (
            f"expected {len(plan.combos)} sweep results, got {len(sweep_results)}"
        )
        return plan.attribute(sweep_results, model_name)

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_sweep(cls, model_name: str, registry: HydraZenRegistry, tmp_path_factory):
        """Class-scoped fixture populating ``results`` before any test runs."""
        cls.fetch_sweep(model_name, registry, tmp_path_factory)

    @classmethod
    def fetch_sweep(cls, model_name: str, registry: HydraZenRegistry, tmp_path_factory):
        """Sweep each experiment in ``cls.name`` and store per-combination solution tables in ``cls.results``.

        Args:
            model_name: Simulated model name selecting the solution table.
            registry: Hydra registry providing each experiment's base run
                config via ``get_experiment_run_config(name)``.
            tmp_path_factory: Pytest factory used for the sweep directory.
        """
        names = [cls.name] if isinstance(cls.name, str) else cls.name
        results = {name: cls.run_single_sweep(name, model_name, registry, tmp_path_factory) for name in names}
        cls.results = cast(SweepResultType, results[cls.name] if isinstance(cls.name, str) else results)


# Single sweep: ``results`` maps each cartesian-product tuple to its solution table.
ExperimentSweep = ExperimentSweepT[str, dict[tuple[Hashable, ...], pd.DataFrame]]
# Multiple sweeps: ``results`` maps each experiment name to such a per-combination mapping.
ExperimentSweeps = ExperimentSweepT[list[str], dict[str, dict[tuple[Hashable, ...], pd.DataFrame]]]
