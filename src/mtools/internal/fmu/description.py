"""What mtools reads from an FMU's ``modelDescription.xml``.

FMPy is imported only inside these functions, so importing this module never needs it.
"""

from __future__ import annotations

import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

#: The binaries directory of a 64-bit Linux FMU, by FMI major version.
LINUX_PLATFORMS = {"2": "linux64", "3": "x86_64-linux"}


@dataclass(frozen=True)
class FmuVariable:
    """One model variable.

    Attributes:
        name: The FMU's variable name.
        type: FMPy's type name: ``Real``, ``Float64``, ``Int32``, ``UInt64``, ``Boolean``,
            ``Enumeration``, ``String``, ``Binary``, ...
        causality: ``parameter``, ``calculatedParameter``, ``input``, ``output``, ``local``,
            ``independent``, ...
        variability: ``constant``, ``fixed``, ``tunable``, ``discrete`` or ``continuous``.
        initial: ``exact``, ``approx``, ``calculated`` or ``None``.
        declared_type: Name of the variable's type definition, if any.
        items: An enumeration's item names and values; empty for other types.
    """

    name: str
    type: str
    causality: str
    variability: str
    initial: str | None
    declared_type: str | None
    items: Mapping[str, int]


@dataclass(frozen=True)
class FmuDescription:
    """The parts of a model description a run needs.

    Attributes:
        model_name: The FMU's ``modelName``.
        fmi_version: ``"2.0"``, ``"3.0"``, ...
        fmu_types: The FMU types it offers, from ``"me"`` and ``"cs"``.
        can_handle_variable_step: Whether its Co-Simulation interface can change the
            communication step size.
        start_time: ``DefaultExperiment`` start time, if given.
        stop_time: ``DefaultExperiment`` stop time, if given.
        interval: ``DefaultExperiment`` step size, if given.
        tolerance: ``DefaultExperiment`` tolerance, if given.
        variables: The model variables, in model-description order.
    """

    model_name: str
    fmi_version: str
    fmu_types: frozenset[str]
    can_handle_variable_step: bool
    start_time: float | None
    stop_time: float | None
    interval: float | None
    tolerance: float | None
    variables: tuple[FmuVariable, ...]


def file_problems(path: Path, config_path: str = "build.fmu_path") -> list[str]:
    """Return why the file at ``path`` can't be run as an FMU, naming ``config_path``.

    It must be a zip archive with a readable ``modelDescription.xml`` and a shared
    library for 64-bit Linux: ``binaries/linux64/*.so`` for FMI 2.0,
    ``binaries/x86_64-linux/*.so`` for FMI 3.0.
    """
    from fmpy import read_model_description

    location = path.absolute()
    if not path.is_file():
        return [f"{config_path}: no such file '{location}'"]
    if not zipfile.is_zipfile(path):
        return [f"{config_path}: not an FMU archive '{location}'"]
    try:
        description = read_model_description(str(path), validate=False)
    except Exception as error:  # FMPy raises whatever zipfile, lxml or its own parser raise
        return [f"{config_path}: no readable modelDescription.xml in '{location}': {error}"]
    platform = LINUX_PLATFORMS.get(description.fmiVersion.split(".")[0], LINUX_PLATFORMS["2"])
    with zipfile.ZipFile(path) as archive:
        entries = [PurePosixPath(name) for name in archive.namelist()]
    if not any(entry.parent == PurePosixPath("binaries", platform) and entry.suffix == ".so" for entry in entries):
        return [f"{config_path}: no linux64 binary in '{location}'"]
    return []


def read_description(path: Path) -> FmuDescription:
    """Read the model description of the FMU at ``path``."""
    from fmpy import read_model_description

    description = read_model_description(str(path), validate=False)
    experiment = description.defaultExperiment
    co_simulation = description.coSimulation
    fmu_types = {"me": description.modelExchange, "cs": co_simulation}
    return FmuDescription(
        model_name=description.modelName,
        fmi_version=description.fmiVersion,
        fmu_types=frozenset(name for name, interface in fmu_types.items() if interface is not None),
        can_handle_variable_step=bool(co_simulation and co_simulation.canHandleVariableCommunicationStepSize),
        start_time=_float(experiment and experiment.startTime),
        stop_time=_float(experiment and experiment.stopTime),
        interval=_float(experiment and experiment.stepSize),
        tolerance=_float(experiment and experiment.tolerance),
        variables=tuple(_variable(variable) for variable in description.modelVariables),
    )


def _variable(variable: Any) -> FmuVariable:
    declared_type = variable.declaredType
    return FmuVariable(
        name=variable.name,
        type=variable.type,
        causality=variable.causality,
        variability=variable.variability,
        initial=variable.initial,
        declared_type=None if declared_type is None else declared_type.name,
        items={} if declared_type is None else {item.name: int(item.value) for item in declared_type.items},
    )


def _float(value: Any) -> float | None:
    return None if value is None else float(value)
