"""The name map between an experiment's variable names and a given FMU's."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Collection, Mapping

#: The independent variable; it is the ``time`` column whatever the FMU calls it.
TIME = "time"


def problems(name_map: Mapping[str, str], fmu_names: Collection[str], *, model_name: str) -> list[str]:
    """Return what is wrong with ``name_map``, by config path.

    Args:
        name_map: Experiment name to FMU variable name.
        fmu_names: Every variable name in the FMU's model description.
        model_name: The model, for the messages.
    """
    found: list[str] = []
    named: defaultdict[str, list[str]] = defaultdict(list)
    for key, fmu_name in name_map.items():
        if TIME in (key, fmu_name):
            found.append(f"build.name_map: '{TIME}' can't be mapped")
            continue
        named[fmu_name].append(key)
        if fmu_name not in fmu_names:
            found.append(f"build.name_map.{key}: '{model_name}' has no variable '{fmu_name}'")
    for fmu_name, keys in named.items():
        if len(keys) > 1:
            found.append(f"build.name_map: {_joined(keys)} both map to FMU name '{fmu_name}'")
    for key in name_map:
        if key != TIME and key in fmu_names and key not in named:
            found.append(f"build.name_map.{key}: '{key}' is also the name of an FMU variable that isn't renamed")
    return found


def to_fmu(name_map: Mapping[str, str]) -> Callable[[str], str]:
    """Return the translation of an experiment name to the FMU's name."""
    return lambda name: name_map.get(name, name)


def to_experiment(name_map: Mapping[str, str]) -> Callable[[str], str]:
    """Return the translation of an FMU name to the experiment's name."""
    inverse = {fmu_name: key for key, fmu_name in name_map.items()}
    return lambda name: inverse.get(name, name)


def _joined(keys: list[str]) -> str:
    return " and ".join(f"'{key}'" for key in keys)
