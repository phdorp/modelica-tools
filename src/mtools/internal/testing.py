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
from typing import TYPE_CHECKING, Any

from omegaconf import OmegaConf

from mtools import sim_tools
from mtools.hydra_registry import EXPERIMENT_GROUP

if TYPE_CHECKING:
    from mtools.hydra_registry import HydraZenRegistry
    from mtools.testing import SweepValue


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


def _to_hashable(value: Any) -> Hashable:
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
    ``ExperimentSweepT.run_single_sweep`` reads as plain orchestration:
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
            _to_hashable(_select_job_value(job.config, f"{self.prefix}.{param}")) for param in self.params
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
