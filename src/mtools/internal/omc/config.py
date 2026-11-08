"""Backend-internal build config and run settings, mirroring the spec's config schema."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Target = Literal["C", "Cpp"]


@dataclass(frozen=True)
class Library:
    """A Modelica library to load before the model.

    Attributes:
        name: Library name, e.g. ``Modelica``.
        version: Exact version to load; ``None`` loads the installed default.
        directory: Directory prepended to OMC's library path.
    """

    name: str
    version: str | None = None
    directory: Path | None = None


@dataclass(frozen=True)
class BuildConfig:
    """The inputs that determine a build.

    Attributes:
        model_path: Modelica source file holding the model (a package's ``package.mo``
            for a model inside a package).
        model_name: Fully qualified name of the model class.
        target: Simulation target.
        extra_sources: Source files loaded before ``model_path``.
        libraries: Libraries loaded before the sources.
        omc_flags: Extra OMC flags (``{"-d": "nogen", "--flag": None}``); mtools adds
            the target and ``-q`` itself.
    """

    model_path: Path
    model_name: str
    target: Target = "C"
    extra_sources: Sequence[Path] = ()
    libraries: Sequence[Library] = ()
    omc_flags: Mapping[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class RunSettings:
    """Everything that can vary between runs of one build.

    Unset (``None``) time range, interval, tolerance and solver come from the model's
    experiment annotation.

    Attributes:
        parameters: Parameter values, as a (nested) dataclass instance or mapping.
            Nested values become dotted names; arrays become 1-based indexed names.
        start_time: Simulation start time.
        stop_time: Simulation stop time.
        interval: Output interval.
        tolerance: Solver tolerance.
        solver: Integration method.
        variable_filter: OMC regular expression (full match) selecting result columns;
            ``time`` is always kept.
        emit_protected: Whether protected variables become result columns.
        timeout: Time limit in seconds; ``None`` means no limit.
        abort_on_chattering: Whether a chattering model aborts the run (C only).
    """

    parameters: Any = field(default_factory=dict)
    start_time: float | None = None
    stop_time: float | None = None
    interval: float | None = None
    tolerance: float | None = None
    solver: str | None = None
    variable_filter: str = ".*"
    emit_protected: bool = False
    timeout: float | None = None
    abort_on_chattering: bool = True
