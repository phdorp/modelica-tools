"""Find the requested parameters OMC fixed at build time and write them as modifiers.

A parameter OMC fixed while translating (an array size, an if-equation selector,
``Evaluate=true``) is a non-changeable parameter in ``<prefix>_init.xml``. A run that
requests one needs a build variant with that value fixed in a modifier.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from mtools.errors import ConfigError
from mtools.internal.omc.init_xml import Variable
from mtools.internal.omc.parameters import (expand_parameters,
                                            flatten_parameters, is_array_like)
from mtools.internal.omc.script import string_literal


@dataclass(frozen=True)
class Split:
    """Requested parameters divided into build-time and per-run ones.

    Attributes:
        build_values: Modifier text by parameter name for the build-time parameters.
        run_parameters: The other requested parameters, by their (unexpanded) names.
    """

    build_values: Mapping[str, str]
    run_parameters: Mapping[str, Any]


def split_parameters(parameters: Any, variables: Mapping[str, Variable], model_name: str) -> Split:
    """Divide the requested ``parameters`` by whether the plain build fixed them.

    The original (unexpanded) config value is available here, so a build-time array is
    written whole from it (``y0={7,8}``).

    Raises:
        ConfigError: A requested parameter is protected (changeable or not).
    """
    build_values: dict[str, str] = {}
    run_parameters: dict[str, Any] = {}
    problems: list[str] = []
    for key, value in flatten_parameters(parameters).items():
        names = list(expand_parameters({key: value}))
        if protected := [name for name in names if name in variables and variables[name].protected]:
            problems.append(f"settings.parameters.{key}: '{model_name}' parameter '{protected[0]}' is protected")
            continue
        fixed = [variables[name] for name in names if name in variables and fixed_at_build(variables[name])]
        if not fixed:
            run_parameters[key] = value
        else:
            try:
                build_values[key] = literal(value, fixed[0])
            except ValueError as error:
                problems.append(f"settings.parameters.{key}: {error}")
    if problems:
        raise ConfigError(
            f"Invalid run settings for '{model_name}':", model_name=model_name, diagnostics="\n".join(problems)
        )
    return Split(build_values, run_parameters)


def fixed_at_build(variable: Variable) -> bool:
    """Whether the build fixed ``variable``: a parameter whose value a run can't change."""
    return variable.variability == "parameter" and not variable.changeable


def literal(value: Any, variable: Variable) -> str:
    """Write ``value`` as a Modelica literal of ``variable``'s type; arrays as ``{...}``."""
    if is_array_like(value):
        return "{" + ", ".join(literal(element, variable) for element in value) + "}"
    if variable.type == "Real":
        return repr(float(value))
    if variable.type in ("Integer", "Enumeration"):
        if isinstance(value, str):
            # OMC 1.27 lists an enumeration parameter as Integer, without its type name,
            # so the config must give the qualified literal itself.
            if "." not in value:
                raise ValueError(f"'{value}' is not a qualified enumeration literal (e.g. 'Mode.high')")
            return value
        return str(int(value))
    if variable.type == "Boolean":
        return "true" if value else "false"
    return string_literal(str(value))
