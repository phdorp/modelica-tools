"""Which FMU variables a run can set, and the values it sets them to."""

from __future__ import annotations

import numbers
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

from mtools.internal.fmu.description import FmuVariable
from mtools.internal.omc.init_xml import Variable
from mtools.internal.omc.parameters import (_is_array_like, expand_parameters,
                                            flatten_parameters)

#: The value kind each FMI type name takes: ``Real``, ``Integer``, ``Boolean``, ``String`` or ``Enumeration``.
_KINDS = {
    "Real": "Real",
    "Float32": "Real",
    "Float64": "Real",
    "Integer": "Integer",
    **{f"{prefix}Int{width}": "Integer" for prefix in ("", "U") for width in (8, 16, 32, 64)},
    "Boolean": "Boolean",
    "String": "String",
    "Enumeration": "Enumeration",
}
_ARTICLES = {"Integer": "an"}


def is_settable(variable: FmuVariable) -> bool:
    """Whether a run can set ``variable``'s start value before initialisation."""
    if variable.causality == "parameter" and variable.variability in ("fixed", "tunable"):
        return True
    return variable.variability != "constant" and variable.initial == "exact" and variable.causality != "input"


def start_values(
    parameters: Any,
    variables: Mapping[str, FmuVariable],
    *,
    model_name: str,
    to_fmu: Callable[[str], str],
    exported: bool,
    build_variables: Mapping[str, Variable],
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    """Check ``parameters`` against ``variables`` and return what a run sets.

    For an exported FMU a requested name is protected first, as ``build_variables``
    marks it; the model description doesn't tell.

    Args:
        parameters: The run settings' parameters (dataclass instance or mapping).
        variables: The FMU's variables by name.
        model_name: The model, for the messages.
        to_fmu: Translates an experiment name to the FMU's name.
        exported: Whether the FMU was exported by this run.
        build_variables: For an exported FMU, the variables of the build that exported
            it (``model_init.xml``) by name; empty for a given FMU.

    Returns:
        The start values by FMU name, the problems by config path, and the build-time
        candidates by key (none for a given FMU).
    """
    values: dict[str, Any] = {}
    problems: list[str] = []
    for key, value in flatten_parameters(parameters).items():
        path = f"settings.parameters.{key}"
        if exported and (protected := _protected(key, value, build_variables)):
            problems.append(f"{path}: '{model_name}' parameter '{protected}' is protected")
            continue
        variable = variables.get(to_fmu(key))
        if variable is not None and _is_array_like(value):
            problems.append(f"{path}: expected {_expectation(variable)}, got {_show(value)}")
            continue
        try:
            expanded = expand_parameters({key: value})
        except ValueError:
            problems.append(f"{path}: '{key}' has an empty array value; nothing to set")
            continue
        unknown = [name for name in expanded if to_fmu(name) not in variables]
        if unknown:
            names = ", ".join(f"'{name}'" for name in unknown)
            problems.append(f"{path}: '{model_name}' has no parameter {names}")
            continue
        for name, element in expanded.items():
            fmu_name = to_fmu(name)
            problem = _check(variables[fmu_name], element, model_name)
            if problem is None:
                values[fmu_name] = _convert(variables[fmu_name], element)
            else:
                problems.append(f"{path}: {problem}")
    return values, problems, {}


def _protected(key: str, value: Any, build_variables: Mapping[str, Variable]) -> str | None:
    """Return the first protected name ``key`` expands to, or ``None``."""
    try:
        names = expand_parameters({key: value})
    except ValueError:
        return None
    return next((name for name in names if name in build_variables and build_variables[name].protected), None)


def _check(variable: FmuVariable, value: Any, model_name: str) -> str | None:
    """Return why ``value`` can't be set on ``variable``, or ``None``."""
    if not is_settable(variable):
        state = variable.variability if variable.causality == "local" else variable.causality
        return (
            f"'{model_name}' parameter '{variable.name}' is fixed in the FMU ({state}); "
            "a given FMU can't be rebuilt"
        )
    if _accepts(variable, value):
        return None
    return f"expected {_expectation(variable)}, got {_show(value)}"


def _accepts(variable: FmuVariable, value: Any) -> bool:
    kind = _KINDS.get(variable.type)
    if kind == "Real":
        return isinstance(value, numbers.Real) and not isinstance(value, (bool, np.bool_))
    if kind == "Integer":
        return _integer(value) is not None
    if kind == "Boolean":
        return isinstance(value, (bool, np.bool_))
    if kind == "String":
        return isinstance(value, str)
    if kind == "Enumeration":
        return _enumeration(variable, value) is not None
    return False


def _integer(value: Any) -> int | None:
    """Return ``value`` as an ``int`` if it is an integer or an integral float, else ``None``."""
    if isinstance(value, (bool, np.bool_)):
        return None
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real) and float(value).is_integer():
        return int(float(value))
    return None


def _enumeration(variable: FmuVariable, value: Any) -> int | None:
    """Return the integer of an enumeration ``value``: an integer, or ``Type.item`` of the variable's type."""
    if isinstance(value, str):
        type_name, _, item = value.rpartition(".")
        declared = variable.declared_type
        if declared is not None and type_name and (type_name == declared or declared.endswith(f".{type_name}")):
            return variable.items.get(item)
        return None
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Integral):
        return None
    return int(value) if int(value) in variable.items.values() else None


def _convert(variable: FmuVariable, value: Any) -> Any:
    """Return ``value`` as the plain Python type FMPy takes; ``value`` has passed :func:`_accepts`."""
    kind = _KINDS[variable.type]
    if kind == "Real":
        return float(value)
    if kind == "Integer":
        return _integer(value)
    if kind == "Boolean":
        return bool(value)
    if kind == "Enumeration":
        return _enumeration(variable, value)
    return value


def _expectation(variable: FmuVariable) -> str:
    kind = _KINDS.get(variable.type, variable.type)
    if kind != "Enumeration":
        return f"{_ARTICLES.get(kind, 'a')} {kind}"
    type_name = (variable.declared_type or "Type").rpartition(".")[2]
    item = list(variable.items)[-1] if variable.items else "item"
    return f"an enumeration item or a qualified literal such as '{type_name}.{item}'"


def _show(value: Any) -> str:
    return repr(value)
