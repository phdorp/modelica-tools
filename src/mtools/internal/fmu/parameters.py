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
from mtools.internal.omc.variants import fixed_at_build, literal

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

    For an exported FMU, a requested name is first protected, as ``build_variables``
    marks it (the model description doesn't tell), then fixed at build time, when the
    model description makes it a ``calculatedParameter`` or leaves it out while
    ``build_variables`` lists it as a non-changeable parameter. Its key then needs a
    variant FMU (ADR 0001), and the other keys are set on the variant and checked
    against its model description instead: an array sized by a build-time parameter
    has other elements there.

    Args:
        parameters: The run settings' parameters (dataclass instance or mapping).
        variables: The FMU's variables by name.
        model_name: The model, for the messages.
        to_fmu: Translates an experiment name to the FMU's name.
        exported: Whether the FMU was exported by this run.
        build_variables: For an exported FMU, the variables of the build that exported
            it (``model_init.xml``) by name; empty for a given FMU.

    Returns:
        The start values by FMU name, the problems by config path, and the modifier text
        by key of the build-time parameters (none for a given FMU). With build-time
        parameters, the start values are empty and the problems are those of the
        protected and build-time keys.
    """
    values: dict[str, Any] = {}
    problems: list[str] = []
    run_problems: list[str] = []
    build_values: dict[str, str] = {}
    for key, value in flatten_parameters(parameters).items():
        path = f"settings.parameters.{key}"
        if exported:
            names = _names(key, value)
            if protected := [name for name in names if name in build_variables and build_variables[name].protected]:
                problems.append(f"{path}: '{model_name}' parameter '{protected[0]}' is protected")
                continue
            if any(_is_build_time(variables.get(to_fmu(name)), build_variables.get(name)) for name in names):
                added = _add_build_value(key, value, variables, to_fmu, build_variables, build_values)
                problems.extend(f"{path}: {problem}" for problem in added)
                continue
        added = _add_start_values(key, value, variables, model_name, to_fmu, exported, values)
        run_problems.extend(f"{path}: {problem}" for problem in added)
    if build_values:
        return {}, problems, build_values
    return values, problems + run_problems, build_values


def _add_start_values(
    key: str,
    value: Any,
    variables: Mapping[str, FmuVariable],
    model_name: str,
    to_fmu: Callable[[str], str],
    exported: bool,
    values: dict[str, Any],
) -> list[str]:
    """Add the start values of ``key`` to ``values`` by FMU name; return why they can't be set."""
    variable = variables.get(to_fmu(key))
    if variable is not None and _is_array_like(value):
        return [f"expected {_expectation(variable)}, got {_show(value)}"]
    try:
        expanded = expand_parameters({key: value})
    except ValueError:
        return [f"'{key}' has an empty array value; nothing to set"]
    unknown = [name for name in expanded if to_fmu(name) not in variables]
    if unknown:
        listed = ", ".join(f"'{name}'" for name in unknown)
        return [f"'{model_name}' has no parameter {listed}"]
    problems: list[str] = []
    for name, element in expanded.items():
        fmu_name = to_fmu(name)
        problem = _check(variables[fmu_name], element, model_name, exported)
        if problem is None:
            values[fmu_name] = _convert(variables[fmu_name], element)
        else:
            problems.append(problem)
    return problems


def _add_build_value(
    key: str,
    value: Any,
    variables: Mapping[str, FmuVariable],
    to_fmu: Callable[[str], str],
    build_variables: Mapping[str, Variable],
    build_values: dict[str, str],
) -> list[str]:
    """Add the modifier text of the build-time parameter ``key`` to ``build_values``;
    return why it can't be built. Each element is checked against its type in the model
    description, or in ``build_variables`` for a name the description leaves out."""
    wrong: list[str] = []
    for name, element in expand_parameters({key: value}).items():
        variable = variables.get(to_fmu(name))
        if variable is not None and not _accepts(variable, element):
            wrong.append(f"expected {_expectation(variable)}, got {_show(element)}")
        elif variable is None and name in build_variables and not _accepts_build(build_variables[name], element):
            kind = _KINDS.get(build_variables[name].type, build_variables[name].type)
            wrong.append(f"expected {_kind_expectation(kind)}, got {_show(element)}")
    if wrong:
        return wrong
    try:
        build_values.update(build_time_values({key: value}, build_variables))
    except ValueError as error:
        return [str(error)]
    return []


def build_time_values(candidates: Mapping[str, Any], init_variables: Mapping[str, Variable]) -> dict[str, str]:
    """Return the modifier text by key of the build-time parameters ``candidates``, as
    for a native build variant; the type comes from the first name in ``init_variables``,
    which must list at least one name of each key.

    Raises:
        ValueError: A value can't be written as a literal of its type.
    """
    return {
        key: literal(value, next(init_variables[name] for name in _names(key, value) if name in init_variables))
        for key, value in candidates.items()
    }


def _names(key: str, value: Any) -> list[str]:
    """Return the names ``key`` expands to with ``value``; none for an empty array."""
    try:
        return list(expand_parameters({key: value}))
    except ValueError:
        return []


def _is_build_time(variable: FmuVariable | None, build_variable: Variable | None) -> bool:
    """Whether OMC fixed a variable while translating the exported model: the model
    description makes it a ``calculatedParameter``, or leaves it out while the build
    lists it as a non-changeable parameter. Either way the build must list it, because
    its modifier is written as a literal of the build's type."""
    if build_variable is None:
        return False
    if variable is not None:
        return variable.causality == "calculatedParameter"
    return fixed_at_build(build_variable)


def _check(variable: FmuVariable, value: Any, model_name: str, exported: bool) -> str | None:
    """Return why ``value`` can't be set on ``variable``, or ``None``."""
    if not is_settable(variable):
        state = variable.variability if variable.causality == "local" else variable.causality
        fixed = f"'{model_name}' parameter '{variable.name}' is fixed in the FMU ({state})"
        return fixed if exported else f"{fixed}; a given FMU can't be rebuilt"
    if _accepts(variable, value):
        return None
    return f"expected {_expectation(variable)}, got {_show(value)}"


def _accepts(variable: FmuVariable, value: Any) -> bool:
    kind = _KINDS.get(variable.type)
    if kind == "Enumeration":
        return _enumeration(variable, value) is not None
    return _accepts_kind(kind, value)


def _accepts_build(variable: Variable, value: Any) -> bool:
    """Whether ``value`` fits the type ``model_init.xml`` gives ``variable``. OMC lists an
    enumeration as Integer there, so an Integer also takes a string, which
    :func:`~mtools.internal.omc.variants.literal` requires to be a qualified literal."""
    kind = _KINDS.get(variable.type)
    if kind in ("Integer", "Enumeration"):
        return isinstance(value, str) or _integer(value) is not None
    return _accepts_kind(kind, value)


def _accepts_kind(kind: str | None, value: Any) -> bool:
    """Whether ``value`` fits the value kind ``Real``, ``Integer``, ``Boolean`` or ``String``."""
    if kind == "Real":
        return isinstance(value, numbers.Real) and not isinstance(value, (bool, np.bool_))
    if kind == "Integer":
        return _integer(value) is not None
    if kind == "Boolean":
        return isinstance(value, (bool, np.bool_))
    if kind == "String":
        return isinstance(value, str)
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
        return _kind_expectation(kind)
    type_name = (variable.declared_type or "Type").rpartition(".")[2]
    item = list(variable.items)[-1] if variable.items else "item"
    return f"an enumeration item or a qualified literal such as '{type_name}.{item}'"


def _kind_expectation(kind: str) -> str:
    return f"{_ARTICLES.get(kind, 'a')} {kind}"


def _show(value: Any) -> str:
    return repr(value)
