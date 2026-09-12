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

import dataclasses
import json
import re
from abc import ABC
from collections.abc import Hashable, Mapping
from itertools import product
from typing import (TYPE_CHECKING, Any, ClassVar, Generic, TypeAlias, TypeVar,
                    cast)

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

from mtools import sim_tools
from mtools.hydra_registry import EXPERIMENT_GROUP

if TYPE_CHECKING:
    from mtools.hydra_registry import HydraZenRegistry

__all__ = [
    "Experiment",
    "ExperimentSweep",
    "ExperimentSweeps",
    "Experiments",
    "SweepScalar",
    "SweepValue",
]

#: Scalar types expressible as Hydra override primitives.
SweepScalar: TypeAlias = bool | int | float | str | None
#: All sweep value types expressible in Hydra override grammar: scalars,
#: lists/tuples (list containers), string-keyed dicts (dict containers),
#: and dataclass instances (coerced via ``asdict``, e.g. ``State``).
SweepValue: TypeAlias = SweepScalar | list["SweepValue"] | tuple["SweepValue", ...] | dict[str, "SweepValue"]

NameType = TypeVar("NameType", bound="str | list[str]")
ResultType = TypeVar("ResultType")
SweepResultType = TypeVar("SweepResultType")


def _to_hydra_value(value: Any) -> str:
    """Serialize a sweep value to Hydra override grammar.

    Args:
        value: Sweep value; one of ``bool``, ``int``, ``float``, ``str``,
            ``None``, ``list``/``tuple`` (list container), ``dict``
            (dict container, values serialized recursively), or a dataclass
            instance (coerced via ``asdict``, e.g. ``State``).

    Returns:
        Hydra override value string (e.g. ``true``, ``5``, ``[0.0,0.0]``,
        ``{px:0.0,py:0.0}``).

    Raises:
        TypeError: If the value type is not expressible in Hydra overrides.
        ValueError: If a dict key is not a valid Hydra identifier (quoting
            keys is not supported by the Hydra override grammar).
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _to_hydra_value(dataclasses.asdict(value))
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return f"[{','.join(_to_hydra_value(item) for item in value)}]"
    if isinstance(value, dict):
        for key in value:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ValueError(
                    f"dict key {key!r} is not expressible in Hydra overrides "
                    "(keys must match [A-Za-z_][A-Za-z0-9_]*; quoting keys "
                    "is not supported by the Hydra override grammar)"
                )
        return f"{{{','.join(f'{key}:{_to_hydra_value(item)}' for key, item in value.items())}}}"
    raise TypeError(f"sweep value of type {type(value).__name__!r} is not supported by Hydra overrides")


def _freeze_value(value: Any) -> Hashable:
    """Return a hashable form of a sweep value for use in result keys.

    ``list``/``tuple`` become ``tuple`` (recursively frozen); ``dict``
    becomes a sorted tuple of ``(key, frozen value)`` pairs; dataclass
    instances are coerced via ``asdict`` and frozen as dicts; other values
    are returned unchanged.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _freeze_value(dataclasses.asdict(value))
    if isinstance(value, dict):
        return tuple(sorted(((key, _freeze_value(item)) for key, item in value.items()), key=str))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _resolve_field_names(registry: Any, experiment_name: str, param: str, prefix: str) -> list[str] | None:
    """Return the config keys of the node targeted by a sweep param, if mapping-like.

    Used to map positional ``tuple`` sweep values onto field names (e.g.
    ``(px, py, theta)`` onto ``state_0``). Returns ``None`` when the target
    cannot be inspected (e.g. test doubles without composed configs) or is
    not mapping-like (scalar/list targets need no conversion).

    Args:
        registry: Hydra registry used to compose the experiment config.
        experiment_name: Experiment name to compose for inspection.
        param: Sweep parameter name relative to ``prefix``.
        prefix: Hydra package prefix of swept parameters.

    Returns:
        Field names in config order, or ``None``.
    """
    try:
        base = registry.compose_experiment(experiment_name)
    except Exception:
        return None
    node = base
    try:
        for part in f"{prefix}.{param}".split("."):
            if OmegaConf.is_config(node):
                node = node[part]
            elif isinstance(node, Mapping):
                node = node[part]
            else:
                node = getattr(node, part)
        if OmegaConf.is_dict(node):
            return list(node.keys())
        if isinstance(node, Mapping):
            return list(node.keys())
    except Exception:
        return None
    return None


def _normalize_sweep_value(value: SweepValue, field_names: list[str] | None, param: str) -> SweepValue:
    """Map a positional ``tuple``/``list`` onto field names for mapping targets.

    Args:
        value: Raw sweep value from ``sweep_params``.
        field_names: Target field names from :func:`_resolve_field_names`,
            or ``None`` when the target is not mapping-like.
        param: Sweep parameter name (used in error messages).

    Returns:
        ``dict`` for positional values with known field names, otherwise the
        value unchanged (scalars, dicts, and list-targeted values).

    Raises:
        ValueError: If a positional value's arity differs from the field count.
    """
    if isinstance(value, (list, tuple)) and field_names is not None:
        if len(value) != len(field_names):
            raise ValueError(
                f"sweep param {param!r}: expected {len(field_names)} values "
                f"({', '.join(field_names)}), got {len(value)}"
            )
        return dict(zip(field_names, value, strict=True))
    return value


#: Sentinel marking a sweep path absent from a job's composed config.
_JOB_VALUE_MISSING = object()


def _ensure_unique(keys: list, message: str) -> None:
    """Raise ``ValueError`` with ``message`` unless all ``keys`` are distinct."""
    if len(set(keys)) != len(keys):
        raise ValueError(message)


def _select_job_value(config: Any, path: str) -> Any:
    """Extract the swept value at ``path`` from a job's composed config.

    Handles Hydra ``DictConfig``/``ListConfig`` nodes (via
    :func:`OmegaConf.select`, converting containers with
    :func:`OmegaConf.to_container`), plain mappings, and attribute-style
    config objects.

    Args:
        config: A sweep job's composed config.
        path: Dot-separated config path (e.g. ``"session.parameters.phi"``).

    Returns:
        The plain-Python value at ``path``.

    Raises:
        ValueError: If ``path`` is absent from the job config.
    """
    if OmegaConf.is_config(config):
        value = OmegaConf.select(config, path, default=_JOB_VALUE_MISSING)
        if value is _JOB_VALUE_MISSING:
            raise ValueError(f"sweep path {path!r} not found in sweep job config")
        if OmegaConf.is_config(value):
            return OmegaConf.to_container(value, resolve=True)
        return value
    node = config
    try:
        for part in path.split("."):
            node = node[part] if isinstance(node, Mapping) else getattr(node, part)
    except (KeyError, AttributeError, TypeError) as exc:
        raise ValueError(f"sweep path {path!r} not found in sweep job config") from exc
    return node


class _SweepPlan:
    """Per-sweep state and steps for one multirun parameter sweep.

    Owns the sweep's raw and normalized combinations, the Hydra override
    strings, and the normalized-to-raw key map, so
    :meth:`ExperimentSweepT.run_single_sweep` reads as plain orchestration:
    build a plan, launch it, attribute its jobs.
    """

    def __init__(
        self,
        sweep_params: dict[str, list[SweepValue]],
        prefix: str,
        experiment: str,
        registry: Any,
    ):
        """Freeze combinations and normalize values up front.

        Args:
            sweep_params: Swept parameter names mapped to their values.
            prefix: Hydra package prefix of swept parameters.
            experiment: Experiment name being swept.
            registry: Hydra registry used to resolve mapping targets.
        """
        self.params = list(sweep_params)
        self.prefix = prefix
        self.experiment = experiment
        self.combos = list(product(*sweep_params.values()))
        self.frozen_combos = [tuple(_freeze_value(value) for value in combo) for combo in self.combos]
        _ensure_unique(
            self.frozen_combos,
            "sweep values collapse to duplicate result keys "
            "(e.g. True == 1 and 1 == 1.0 as dict keys); "
            "use distinct types or stringify ambiguous choices",
        )
        self.normalized_per_param = [
            self._normalize_param(param, values, registry, experiment)
            for param, values in sweep_params.items()
        ]
        self.norm_combos = [
            tuple(_freeze_value(value) for value in combo) for combo in product(*self.normalized_per_param)
        ]
        _ensure_unique(
            self.norm_combos,
            "swept values are ambiguous after positional-to-field normalization; "
            "use distinct values or hand-written dicts with distinct fields",
        )
        self.norm_to_raw = dict(zip(self.norm_combos, self.frozen_combos))

    def _normalize_param(
        self, param: str, values: list[SweepValue], registry: Any, experiment: str
    ) -> list[SweepValue]:
        """Map positional values of one param onto field names when its target is mapping-like."""
        needs_fields = any(isinstance(value, (list, tuple)) for value in values)
        field_names = (
            _resolve_field_names(registry, experiment, param, self.prefix) if needs_fields else None
        )
        return [_normalize_sweep_value(value, field_names, param) for value in values]

    def build_overrides(self) -> list[str]:
        """Return the Hydra override strings selecting the experiment and sweeping each param."""
        return [
            f"{EXPERIMENT_GROUP}={self.experiment}",
            *(
                f"{self.prefix}.{param}={','.join(_to_hydra_value(value) for value in normalized)}"
                for param, normalized in zip(self.params, self.normalized_per_param, strict=True)
            ),
        ]

    def launch(self, registry: HydraZenRegistry, tmp_path_factory: Any) -> list:
        """Fan out via multirun simulate and return the per-job results."""
        return sim_tools.simulate(
            registry.get_experiment_run_config(self.experiment),
            overrides=self.build_overrides(),
            multirun=True,
            sweep_dir=str(tmp_path_factory.mktemp(f"{self.experiment}_sweep")),
        )

    def key_of(self, job: Any) -> tuple:
        """Attribute one job to its raw combination via its own composed config."""
        job_key = tuple(
            _freeze_value(_select_job_value(job.config, f"{self.prefix}.{param}")) for param in self.params
        )
        try:
            return self.norm_to_raw[job_key]
        except KeyError:
            raise ValueError(
                f"sweep job config {job_key!r} matches no swept combination for params {self.params}"
            ) from None

    def attribute(self, sweep_results: list, model_name: str) -> dict:
        """Map each job's solution table to its raw combination key."""
        results = {}
        for job in sweep_results:
            raw_key = self.key_of(job)
            if raw_key in results:
                raise ValueError(f"duplicate sweep job for combination {raw_key!r}")
            results[raw_key] = job.solutions[model_name]
        assert len(results) == len(self.combos), (
            f"expected {len(self.combos)} sweep results, got {len(results)}"
        )
        return results


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
        plan = _SweepPlan(cls.sweep_params, cls.sweep_param_prefix, name, registry)
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
