"""Typed run configs: what to build (``build``), how to run it (``settings``) and how to
save the result (``output_format``).

The classes are plain dataclasses that Hydra composes as structured configs, so every
field can be overridden from the command line (``build.target=Cpp``,
``settings.stop_time=20``, ``settings.parameters.phi=0.1``). ``sim_tools.simulate``
validates a run config once, before anything is built.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Literal, Protocol

if TYPE_CHECKING:
    from typing import TypeAlias

    #: Simulation target. OmegaConf has no ``Literal`` support, so Hydra sees ``str``;
    #: ``sim_tools.simulate`` rejects any other value with a ``ConfigError``.
    Target: TypeAlias = Literal["C", "Cpp"]
    #: Saved result file format. Hydra sees ``str``; ``sim_tools.simulate`` and
    #: ``sim_tools.save_solutions`` reject any other value.
    OutputFormat: TypeAlias = Literal["mat", "csv"]
    #: Parameter values: a (nested) parameter dataclass instance. OmegaConf cannot
    #: type a ``Protocol``, so Hydra sees ``Any``.
    Parameters: TypeAlias = "DataclassType"
    #: What a run simulates: a Modelica build or a given FMU. OmegaConf has no
    #: ``Union`` support, so Hydra sees ``Any`` and composes the instance it is given.
    BuildSpec: TypeAlias = "Build | FmuFile"
else:
    Target = str
    OutputFormat = str
    Parameters = Any
    BuildSpec = Any

#: A Modelica source file; must exist when the run is validated.
FilePath = Path
#: A directory; must exist when the run is validated.
DirectoryPath = Path


class DataclassType(Protocol):
    """Protocol describing objects that expose dataclass field metadata."""

    #: Dataclass field definitions exposed by dataclass instances.
    __dataclass_fields__: ClassVar[Dict[str, dataclasses.Field[Any]]]


@dataclasses.dataclass
class Library:
    """A Modelica library loaded before the model's sources."""

    #: Library name, e.g. ``Modelica``.
    name: str
    #: Exact version to load; ``None`` loads the installed default.
    version: str | None = None
    #: Directory holding the library, prepended to OMC's library path.
    directory: DirectoryPath | None = None


@dataclasses.dataclass
class FmuExport:
    """Export the built model as an FMI 2.0 FMU and run it through FMPy."""

    #: FMU type to export and run, ``"me"`` (Model Exchange) or ``"cs"`` (Co-Simulation).
    fmu_type: str = "me"


@dataclasses.dataclass
class Build:
    """What to build: one model, its sources, libraries and simulation target."""

    #: Modelica source file holding the model; for a model inside a package, any file
    #: of the package (the package is loaded from its ``package.mo``).
    model_path: FilePath
    #: Fully qualified name of the model class; results are keyed by it.
    model_name: str
    #: Simulation target, ``"C"`` or ``"Cpp"``.
    target: Target = "C"
    #: Source files or packages loaded before ``model_path``.
    extra_sources: list[FilePath] = dataclasses.field(default_factory=list)
    #: Libraries loaded before the sources.
    libraries: list[Library] = dataclasses.field(default_factory=list)
    #: Extra OMC flags (``{"-d": "nogen", "--flag": None}``); mtools adds ``-q`` and the
    #: target itself, so ``--simCodeTarget`` is rejected.
    omc_flags: dict[str, str | None] = dataclasses.field(default_factory=dict)
    #: Export the model as an FMU and run that; ``None`` runs the native executable.
    fmu: FmuExport | None = None


@dataclasses.dataclass
class FmuFile:
    """A given FMU, run through FMPy instead of a Modelica build."""

    #: The ``.fmu`` file to run.
    fmu_path: FilePath
    #: Name the results are keyed by; ``None`` takes the FMU's ``modelName``.
    model_name: str | None = None
    #: FMU type to run, ``"me"`` (Model Exchange) or ``"cs"`` (Co-Simulation); ``None``
    #: runs Model Exchange when the FMU offers it, otherwise Co-Simulation.
    fmu_type: str | None = None
    #: Experiment name to FMU variable name, for parameters and result columns alike
    #: (``{"ctrl.k": "Kp"}``); unmapped names are used as they are.
    name_map: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class RunSettings:
    """How to run a build. Unset (``None``) time range, interval, tolerance and solver
    come from the model's ``experiment`` annotation."""

    #: Parameter values, as a (nested) parameter dataclass instance; nested values become
    #: dotted names and arrays become 1-based indexed names (``y[1]``, ``m[1,2]``).
    parameters: Parameters
    #: Simulation start time.
    start_time: float | None = None
    #: Simulation stop time.
    stop_time: float | None = None
    #: Output interval.
    interval: float | None = None
    #: Solver tolerance.
    tolerance: float | None = None
    #: Integration method; on Cpp only ``dassl``, ``cvode`` and ``ida``.
    solver: str | None = None
    #: OMC regular expression (full match) selecting result columns; ``time`` is always kept.
    variable_filter: str = ".*"
    #: Whether protected variables become result columns.
    emit_protected: bool = False
    #: Time limit in seconds; ``None`` means no limit.
    timeout: float | None = None
    #: Whether a chattering model aborts the run (C only; no effect on Cpp).
    abort_on_chattering: bool = True


@dataclasses.dataclass
class SimulationRun:
    """Top-level run config: one build, the settings to run it with, and how to save it."""

    #: What to build: a :class:`Build`, or a given FMU as :class:`FmuFile`.
    build: BuildSpec
    #: How to run it.
    settings: RunSettings
    #: File format ``sim_tools.save_solutions`` writes: ``"mat"`` (OMC's MATLAB v4
    #: result layout, the default) or ``"csv"``. Override with ``output_format=csv``.
    output_format: OutputFormat = "mat"
