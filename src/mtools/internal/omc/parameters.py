"""Turn run-setting parameters into OMC parameter names and values."""

from __future__ import annotations

import dataclasses
import numbers
from collections.abc import Collection, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from mtools.errors import ConfigError


def flatten_parameters(parameters: Any) -> dict[str, Any]:
    """Flatten a (nested) parameter dataclass instance or mapping to dotted names.

    Array values are kept whole; :func:`expand_parameters` splits them into elements.
    """
    if dataclasses.is_dataclass(parameters) and not isinstance(parameters, type):
        parameters = dataclasses.asdict(parameters)
    return _flatten(parameters, "")


def _flatten(parameters: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in parameters.items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping):
            flat.update(_flatten(value, f"{name}."))
        else:
            flat[name] = value
    return flat


def expand_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """Expand array values to one entry per element, named as OMC names them.

    Indexes are 1-based and row-major, with dimensions separated by commas without
    spaces: ``x = [a, b]`` becomes ``x[1] = a, x[2] = b`` and ``m = [[a, b], [c, d]]``
    becomes ``m[1,1] = a, m[1,2] = b, m[2,1] = c, m[2,2] = d``. Scalars pass through.

    Raises:
        ValueError: If an array value has no elements.
    """
    expanded: dict[str, Any] = {}
    for name, value in parameters.items():
        if is_array_like(value):
            expanded.update(_expand_array(name, (), value))
        else:
            expanded[name] = value
    return expanded


def is_array_like(value: Any) -> bool:
    return hasattr(value, "__iter__") and not isinstance(value, (str, bytes, Mapping))


def _expand_array(name: str, indices: tuple[int, ...], value: Any) -> dict[str, Any]:
    if len(value) == 0:
        raise ValueError(f"Parameter '{name}' has an empty array value; nothing to set")
    expanded: dict[str, Any] = {}
    for index, element in enumerate(value, start=1):
        element_indices = (*indices, index)
        if is_array_like(element):
            expanded.update(_expand_array(name, element_indices, element))
        else:
            expanded[f"{name}[{','.join(map(str, element_indices))}]"] = element
    return expanded


def resolve_parameters(parameters: Any, known: Collection[str], model_name: str) -> dict[str, Any]:
    """Flatten and expand ``parameters`` and check every name against the build.

    Args:
        parameters: The run settings' parameters (dataclass instance or mapping).
        known: The names a run of the build may set.
        model_name: The model, for the error message.

    Returns:
        Values by OMC variable name.

    Raises:
        ConfigError: A name is not in ``known``; the diagnostics name its config path
            ``settings.parameters.<name>``.
    """
    values: dict[str, Any] = {}
    problems: list[str] = []
    for key, value in flatten_parameters(parameters).items():
        expanded = expand_parameters({key: value})
        unknown = [name for name in expanded if name not in known]
        if unknown:
            names = ", ".join(f"'{name}'" for name in unknown)
            problems.append(f"settings.parameters.{key}: '{model_name}' has no parameter {names}")
        values.update(expanded)
    if problems:
        raise ConfigError(
            f"Invalid run settings for '{model_name}':", model_name=model_name, diagnostics="\n".join(problems)
        )
    return values


def write_override_file(path: Path, values: Mapping[str, Any]) -> None:
    """Write ``values`` as a C runtime override file (``-overrideFile``).

    Every line is ``name=value`` and newline-terminated, because the runtime drops a
    last line without a newline. Reals are written at full precision.
    """
    path.write_text("".join(f"{name}={format_value(value)}\n" for name, value in values.items()))


def format_value(value: Any) -> str:
    if isinstance(value, (bool, np.bool_)):
        return "true" if value else "false"
    if isinstance(value, numbers.Integral):
        return str(int(value))
    if isinstance(value, numbers.Real):
        return repr(float(value))
    return str(value)
