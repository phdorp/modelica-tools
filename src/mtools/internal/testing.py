"""Internal sweep helpers backing :mod:`mtools.testing`.

This module contains implementation details not intended for direct use:
sweep-value serialization, result-key hashing, positional-to-field
normalization, per-job config inspection, and the sweep planner. Public
entry points (experiment base classes, aliases, sweep types) live in
:mod:`mtools.testing` and delegate here.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Hashable, Mapping
from itertools import product
from typing import TYPE_CHECKING, TypeAlias, cast

import numpy as np
import pandas as pd
import pytest
from omegaconf import DictConfig, OmegaConf

from mtools import sim_tools
from mtools.hydra_registry import EXPERIMENT_GROUP

if TYPE_CHECKING:
    from mtools.hydra_registry import RunConfig
    from mtools.testing import Registry, SweepValue

#: A solution structure: one solution table, or a mapping (by experiment name
#: or sweep combination) to further solution structures.
Solution: TypeAlias = pd.DataFrame | dict[Hashable, "Solution"]


def _to_hydra_value(value: SweepValue) -> str:
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


def _to_hashable(value: SweepValue) -> Hashable:
    """Return a hashable form of a sweep value for use in result keys.

    ``list``/``tuple`` become ``tuple`` (recursively frozen); ``dict``
    becomes a sorted tuple of ``(key, frozen value)`` pairs; dataclass
    instances are coerced via ``asdict`` and frozen as dicts; other values
    are returned unchanged.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _to_hashable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return tuple(sorted(((key, _to_hashable(item)) for key, item in value.items()), key=str))
    if isinstance(value, (list, tuple)):
        return tuple(_to_hashable(item) for item in value)
    return cast(Hashable, value)


def _resolve_field_names(
    registry: Registry,
    experiment_name: str,
    param: str,
    prefix: str,
    run_config: RunConfig | None = None,
) -> list[str] | None:
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
        run_config: Optional run config the experiment is composed with;
            ``None`` composes the registry's default run config.

    Returns:
        Field names in config order, or ``None``.
    """
    try:
        base = registry.compose_experiment(experiment_name, run_config=run_config)
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
            return cast(list[str], list(node.keys()))
        if isinstance(node, Mapping):
            return cast(list[str], list(node.keys()))
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


#: Sentinel marking a config path absent from a job's composed config.
_JOB_VALUE_MISSING = object()


def _ensure_unique(keys: list, message: str) -> None:
    """Raise ``ValueError`` with ``message`` unless all ``keys`` are distinct."""
    if len(set(keys)) != len(keys):
        raise ValueError(message)


def pick_solution(solutions: Mapping[str, pd.DataFrame], model_name: str | None) -> tuple[str, pd.DataFrame]:
    """Return ``(name, table)`` of the model ``model_name`` from one run's ``solutions``.

    A given FMU configured without ``build.model_name`` has ``None`` here; its run
    returns a single table keyed by the FMU's own ``modelName``, which is taken instead.
    """
    keys = list(solutions)
    if model_name is None:
        assert len(keys) == 1, (
            f"expected one solution table when build.model_name is unset, got {len(keys)}: {keys}; set build.model_name"
        )
        model_name = keys[0]
    assert model_name in solutions, f"no solution for build.model_name {model_name!r}; the run returned {keys}"
    return model_name, solutions[model_name]


def _select_job_value(config: object, path: str) -> object:
    """Extract the value at ``path`` from a job's composed config.

    Handles Hydra ``DictConfig``/``ListConfig`` nodes (via
    :func:`OmegaConf.select`, converting containers with
    :func:`OmegaConf.to_container`), plain mappings, and attribute-style
    config objects.

    Args:
        config: A sweep job's composed config.
        path: Dot-separated config path (e.g. ``"settings.parameters.phi"``,
            or ``"build.model_name"`` for the simulated model's name).

    Returns:
        The plain-Python value at ``path``. The type is whatever the config
        holds, so callers narrow it to what they expect.

    Raises:
        ValueError: If ``path`` is absent from the job config.
    """
    if OmegaConf.is_config(config):
        value = OmegaConf.select(cast("DictConfig", config), path, default=_JOB_VALUE_MISSING)
        if value is _JOB_VALUE_MISSING:
            raise ValueError(f"config path {path!r} not found in sweep job config")
        if OmegaConf.is_config(value):
            return OmegaConf.to_container(value, resolve=True)
        return value
    node = config
    try:
        for part in path.split("."):
            node = node[part] if isinstance(node, Mapping) else getattr(node, part)
    except (KeyError, AttributeError, TypeError) as exc:
        raise ValueError(f"config path {path!r} not found in sweep job config") from exc
    return node


def align(
    actual: pd.DataFrame, reference: pd.DataFrame, context: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the candidate on the reference's time points and the deduplicated reference.

    Where a time repeats, only the last row (the value after an event) is
    kept on both sides. Real columns are interpolated linearly; all other
    columns take the last value at or before each reference time.

    Raises:
        AssertionError: If either table is empty, or a reference time lies
            outside the candidate's span.
    """
    actual = actual.drop_duplicates("time", keep="last")
    reference = reference.drop_duplicates("time", keep="last")
    for side, frame in (("candidate", actual), ("reference", reference)):
        if frame.empty:
            raise AssertionError(f"{context}: {side} solution is empty; nothing to interpolate")
    times = actual["time"].to_numpy(dtype=float)
    targets = reference["time"].to_numpy(dtype=float)
    low, high = times[0], times[-1]
    for target in targets:
        if target < low or target > high:
            raise AssertionError(
                f"{context}: reference time {target:g} lies outside the candidate's "
                f"time span [{low:g}, {high:g}]"
            )
    index = np.searchsorted(times, targets, side="right") - 1
    aligned = {}
    for column in actual.columns:
        values = actual[column].to_numpy()
        if pd.api.types.is_float_dtype(actual[column]):
            aligned[column] = np.interp(targets, times, values)
        else:
            aligned[column] = values[index]
    return pd.DataFrame(aligned), reference


def assert_solutions_match(
    actual: Solution,
    reference: Solution,
    *,
    atol: float,
    context: str,
    rtol: float = 0.0,
    interpolate: bool = False,
) -> None:
    """Recursively assert that candidate solutions match reference solutions.

    By default, data frame references are compared by column set, row count,
    and positionally per column. The ``time`` column is compared like any
    other column: both models must be simulated under the same conditions, so
    a time mismatch indicates a differing simulation setup. With
    ``interpolate`` the candidate is first aligned onto the reference's time
    points (see :func:`align`); row counts then need not match and ``time``
    isn't compared. Dict references require the same key set and are compared
    recursively; ``context`` is extended with each key so failures identify
    the offending experiment or sweep combination.

    Args:
        actual: Candidate solution structure (data frame or dict of them).
        reference: Reference solution structure to compare against.
        atol: Absolute tolerance passed to ``numpy.testing.assert_allclose``.
        context: Human-readable location prefix used in failure messages.
        rtol: Relative tolerance passed to ``numpy.testing.assert_allclose``.
        interpolate: Align the candidate onto the reference's time points
            instead of comparing row by row.

    Raises:
        AssertionError: If the structures, signal sets, lengths, or values
            differ.
        TypeError: If ``reference`` is not a supported solution structure.
    """
    if isinstance(reference, pd.DataFrame):
        if not isinstance(actual, pd.DataFrame):
            raise TypeError(f"{context}: expected a solution table, got {type(actual).__name__!r}")
        missing = [column for column in reference.columns if column not in actual.columns]
        extra = [column for column in actual.columns if column not in reference.columns]
        if missing or extra:
            raise AssertionError(
                f"{context}: output signals differ; missing {missing!r}, unexpected {extra!r}"
            )
        if interpolate:
            actual, reference = align(actual, reference, context)
        elif len(actual) != len(reference):
            raise AssertionError(
                f"{context}: solution length differs ({len(actual)} != {len(reference)}); "
                "set interpolate = True to compare on the reference's time points"
            )
        for column in reference.columns:
            if interpolate and column == "time":
                continue
            np.testing.assert_allclose(
                actual[column],
                reference[column],
                rtol=rtol,
                atol=atol,
                err_msg=f"{context}: signal {column!r} differs",
            )
        return
    if isinstance(reference, dict):
        if not isinstance(actual, dict):
            raise TypeError(f"{context}: expected a result mapping, got {type(actual).__name__!r}")
        missing_keys = [key for key in reference if key not in actual]
        extra_keys = [key for key in actual if key not in reference]
        if missing_keys or extra_keys:
            raise AssertionError(
                f"{context}: result keys differ; missing {missing_keys!r}, unexpected {extra_keys!r}"
            )
        for key, reference_solution in reference.items():
            assert_solutions_match(
                actual[key],
                reference_solution,
                atol=atol,
                context=f"{context}[{key!r}]",
                rtol=rtol,
                interpolate=interpolate,
            )
        return
    raise TypeError(f"{context}: unsupported reference solution type {type(reference).__name__!r}")


class _SweepPlan:
    """Per-sweep state and steps for one multirun parameter sweep.

    Owns the sweep's raw and normalized combinations, the Hydra override
    strings, and the normalized-to-raw key map, so
    ``ExperimentSweepT.run_single_sweep`` reads as plain orchestration:
    build a plan, launch it, attribute its jobs. An optional ``run_config``
    selects the base run config composed and launched against, defaulting
    to the registry's default for the swept experiment.
    """

    def __init__(
        self,
        sweep_params: dict[str, list[SweepValue]],
        prefix: str,
        experiment: str,
        registry: Registry,
        run_config: RunConfig | None = None,
    ):
        """Freeze combinations and normalize values up front.

        Args:
            sweep_params: Swept parameter names mapped to their values.
            prefix: Hydra package prefix of swept parameters.
            experiment: Experiment name being swept.
            registry: Hydra registry used to resolve mapping targets.
            run_config: Optional run config the experiment is composed and
                launched against; ``None`` uses the registry's default.
        """
        self.params = list(sweep_params)
        self.prefix = prefix
        self.experiment = experiment
        self.run_config = run_config
        #: Distinct model names seen while attributing sweep jobs.
        self.model_names: list[str] = []
        for param, values in sweep_params.items():
            if not values:
                raise ValueError(
                    f"sweep param {param!r} has no values; provide at least one value to sweep over"
                )
        self.combos = list(product(*sweep_params.values()))
        self.frozen_combos = [tuple(_to_hashable(value) for value in combo) for combo in self.combos]
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
            tuple(_to_hashable(value) for value in combo) for combo in product(*self.normalized_per_param)
        ]
        _ensure_unique(
            self.norm_combos,
            "swept values are ambiguous after positional-to-field normalization; "
            "use distinct values or hand-written dicts with distinct fields",
        )
        self.norm_to_raw = dict(zip(self.norm_combos, self.frozen_combos))

    def _normalize_param(
        self, param: str, values: list[SweepValue], registry: Registry, experiment: str
    ) -> list[SweepValue]:
        """Map positional values of one param onto field names when its target is mapping-like."""
        needs_fields = any(isinstance(value, (list, tuple)) for value in values)
        field_names = (
            _resolve_field_names(registry, experiment, param, self.prefix, run_config=self.run_config)
            if needs_fields
            else None
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

    def launch(
        self, registry: Registry, tmp_path_factory: pytest.TempPathFactory
    ) -> list[sim_tools.SweepResult]:
        """Fan out via multirun simulate and return the per-job results.

        Args:
            registry: Hydra registry providing the multirun base run config.
            tmp_path_factory: Pytest factory used for the sweep directory.
        """
        return sim_tools.simulate(
            registry.get_experiment_run_config(self.experiment, run_config=self.run_config),
            overrides=self.build_overrides(),
            multirun=True,
            sweep_dir=str(tmp_path_factory.mktemp(f"{self.experiment}_sweep")),
            registry=registry,
        )

    def key_of(self, job: sim_tools.SweepResult) -> tuple[Hashable, ...]:
        """Attribute one job to its raw combination via its own composed config."""
        job_key = tuple(
            _to_hashable(cast("SweepValue", _select_job_value(job.config, f"{self.prefix}.{param}")))
            for param in self.params
        )
        try:
            return self.norm_to_raw[job_key]
        except KeyError:
            raise ValueError(
                f"sweep job config {job_key!r} matches no swept combination for params {self.params}"
            ) from None

    def attribute(
        self, sweep_results: list[sim_tools.SweepResult]
    ) -> dict[tuple[Hashable, ...], pd.DataFrame]:
        """Map each job's solution table to its raw combination key.

        The model name keying a job's solutions is read from that job's own
        composed config; a job whose ``build.model_name`` is unset (a given FMU) takes
        the single table its run returned, and any other job whose name is absent from
        its solutions fails here rather than returning a mis-keyed table. The distinct names seen are
        exposed on :attr:`model_names` for failure-context reporting.
        """
        results = {}
        for job in sweep_results:
            raw_key = self.key_of(job)
            if raw_key in results:
                raise ValueError(f"duplicate sweep job for combination {raw_key!r}")
            configured = _select_job_value(job.config, "build.model_name")
            if configured is not None and not isinstance(configured, str):
                raise ValueError("config path 'build.model_name' is neither a string nor unset in sweep job config")
            model_name, results[raw_key] = pick_solution(job.solutions, configured)
            if model_name not in self.model_names:
                self.model_names.append(model_name)
        assert len(results) == len(self.combos), (
            f"expected {len(self.combos)} sweep results, got {len(results)}"
        )
        return results
