"""Validate a public run config and turn it into the backend's build config and run settings.

Hydra composes the public dataclasses of :mod:`mtools.session_config`; this module
instantiates them into config objects, checks every value that can be checked without
building, and maps them onto the backend's own frozen config types.
"""

from __future__ import annotations

import dataclasses
import numbers
import os
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import hydra_zen
from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import OmegaConfBaseException

import mtools.internal.omc.config as backend
import mtools.session_config as session_config
from mtools.errors import ConfigError
from mtools.internal import result_files
from mtools.internal.fmu.config import FmuFileConfig
from mtools.internal.fmu.description import file_problems, require_fmpy
from mtools.internal.fmu.resolve import FMU_TYPES
from mtools.internal.omc import run_cpp

TARGETS = ("C", "Cpp")

_HEADER = "Invalid config for '{}':"


def instantiate(config: session_config.SimulationRun | DictConfig) -> session_config.SimulationRun:
    """Return ``config`` as config objects; a composed Hydra config is instantiated.

    Raises:
        ConfigError: A value is missing or does not fit its field's type.
    """
    if isinstance(config, session_config.SimulationRun):
        return config
    try:
        run: session_config.SimulationRun = hydra_zen.instantiate(config, _convert_="object")
    except OmegaConfBaseException as error:
        model_name = OmegaConf.select(config, "build.model_name", default="", throw_on_missing=False)
        raise ConfigError(
            _HEADER.format(model_name),
            model_name=str(model_name),
            diagnostics=f"{error.full_key}: {error.msg}",  # type: ignore[attr-defined]
        ) from None
    return run


def validate(run: session_config.SimulationRun) -> tuple[backend.BuildConfig, backend.RunSettings]:
    """Check ``run`` and map it onto the backend's build config and run settings.

    Checks what needs no build: types, that files and directories exist, the target,
    the output format, no ``--simCodeTarget`` in ``build.omc_flags``, an exported
    FMU's ``fmu_type``, and an explicitly requested Cpp solver. Checks that need the
    build (parameter names, a solver from the annotation) happen when the build runs.
    A build that exports an FMU needs FMPy, checked first.

    Raises:
        ImportError: The build exports an FMU and FMPy isn't installed.
        ConfigError: Listing every invalid value by its config path.
    """
    build, settings = run.build, run.settings
    if not isinstance(build, session_config.Build):
        raise TypeError(f"validate takes a run of a Build, got {type(build).__name__}")
    if build.fmu is not None:
        require_fmpy()
    model_name = build.model_name if isinstance(build.model_name, str) else str(build.model_name)
    problems = [*_build_problems(build), *_settings_problems(settings)]
    if (format_problem := result_files.output_format_problem(run.output_format)) is not None:
        problems.append(format_problem)
    if problems:
        raise ConfigError(_HEADER.format(model_name), model_name=model_name, diagnostics="\n".join(problems))
    build_config = backend.BuildConfig(
        model_path=Path(build.model_path),
        model_name=build.model_name,
        target=build.target,
        extra_sources=tuple(Path(source) for source in build.extra_sources),
        libraries=tuple(
            backend.Library(
                name=library.name,
                version=library.version,
                directory=None if library.directory is None else Path(library.directory),
            )
            for library in build.libraries
        ),
        omc_flags=dict(build.omc_flags),
        fmu=(
            None
            if build.fmu is None
            else backend.FmuExportConfig(fmu_type=build.fmu.fmu_type, emit_protected=settings.emit_protected)
        ),
    )
    run_settings = _run_settings(settings)
    if build.fmu is None:  # an exported FMU runs in FMPy, whose solvers the FMU resolution checks
        run_cpp.validate_settings(build_config, run_settings)
    return build_config, run_settings


def validate_fmu_file(run: session_config.SimulationRun) -> tuple[FmuFileConfig, backend.RunSettings]:
    """Check a run of a given FMU and map it onto its FMU config and the run settings.

    Checks that FMPy is installed, that the FMU file can be run (an archive with a
    readable model description and a Linux binary), the run settings and the output
    format. Checks against the model description happen when the run starts.

    Raises:
        ImportError: FMPy isn't installed.
        ConfigError: Listing every invalid value by its config path.
    """
    require_fmpy()
    build, settings = run.build, run.settings
    if not isinstance(build, session_config.FmuFile):
        raise TypeError(f"validate_fmu_file takes a run of an FmuFile, got {type(build).__name__}")
    if isinstance(build.fmu_path, (str, os.PathLike)):
        model_name = build.model_name or Path(build.fmu_path).stem
        problems = file_problems(Path(build.fmu_path))
    else:
        model_name = build.model_name or ""
        problems = [f"build.fmu_path: expected a path, got {build.fmu_path!r}"]
    problems.extend(_settings_problems(settings))
    if build.fmu_type is not None and build.fmu_type not in FMU_TYPES:
        expected = ", ".join(map(repr, FMU_TYPES))
        problems.append(f"build.fmu_type: expected {expected} or null, got {build.fmu_type!r}")
    if not isinstance(build.name_map, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in build.name_map.items()
    ):
        problems.append(f"build.name_map: expected a mapping of experiment names to FMU names, got {build.name_map!r}")
    if (format_problem := result_files.output_format_problem(run.output_format)) is not None:
        problems.append(format_problem)
    if problems:
        raise ConfigError(_HEADER.format(model_name), model_name=model_name, diagnostics="\n".join(problems))
    fmu_config = FmuFileConfig(
        fmu_path=Path(build.fmu_path),
        model_name=build.model_name,
        fmu_type=build.fmu_type,
        name_map=dict(build.name_map),
    )
    return fmu_config, _run_settings(settings)


def _run_settings(settings: session_config.RunSettings) -> backend.RunSettings:
    return backend.RunSettings(
        parameters=settings.parameters,
        start_time=settings.start_time,
        stop_time=settings.stop_time,
        interval=settings.interval,
        tolerance=settings.tolerance,
        solver=settings.solver,
        variable_filter=settings.variable_filter,
        emit_protected=settings.emit_protected,
        timeout=settings.timeout,
        abort_on_chattering=settings.abort_on_chattering,
    )


def _build_problems(build: session_config.Build) -> Iterator[str]:
    if not isinstance(build.model_name, str) or not build.model_name:
        yield f"build.model_name: expected the model's class name, got {build.model_name!r}"
    yield from _existing("build.model_path", build.model_path, Path.is_file, "file")
    if build.target not in TARGETS:
        yield f"build.target: expected one of {', '.join(map(repr, TARGETS))}, got {build.target!r}"
    if not isinstance(build.extra_sources, (list, tuple)):
        yield f"build.extra_sources: expected a list of files, got {build.extra_sources!r}"
    else:
        for index, source in enumerate(build.extra_sources):
            yield from _existing(f"build.extra_sources[{index}]", source, Path.is_file, "file")
    yield from _library_problems(build.libraries)
    yield from _flag_problems(build.omc_flags, exported=build.fmu is not None)
    if build.fmu is not None and build.fmu.fmu_type not in FMU_TYPES:
        yield f"build.fmu.fmu_type: expected {' or '.join(map(repr, FMU_TYPES))}, got {build.fmu.fmu_type!r}"
    elif build.fmu is not None and build.fmu.fmu_type == "cs" and build.target == "Cpp":
        yield "build.fmu.fmu_type: Co-Simulation export isn't supported on the Cpp target"


def _library_problems(libraries: Any) -> Iterator[str]:
    if not isinstance(libraries, (list, tuple)):
        yield f"build.libraries: expected a list of Library, got {libraries!r}"
        return
    for index, library in enumerate(libraries):
        path = f"build.libraries[{index}]"
        if not isinstance(library, session_config.Library):
            yield f"{path}: expected a Library, got {library!r}"
            continue
        if not isinstance(library.name, str) or not library.name:
            yield f"{path}.name: expected a library name, got {library.name!r}"
        yield from _optional(f"{path}.version", library.version, str, "a version string")
        if library.directory is not None:
            yield from _existing(f"{path}.directory", library.directory, Path.is_dir, "directory")


def _flag_problems(omc_flags: Any, *, exported: bool) -> Iterator[str]:
    if not isinstance(omc_flags, Mapping):
        yield f"build.omc_flags: expected a mapping of flag to value, got {omc_flags!r}"
        return
    for flag, value in omc_flags.items():
        if not isinstance(flag, str) or not (value is None or isinstance(value, str)):
            yield f"build.omc_flags: expected string flags with string or null values, got {flag!r}: {value!r}"
        elif flag.lstrip("-+").split("=")[0] == "simCodeTarget":
            yield f"build.omc_flags: '{flag}' is not allowed; set the simulation target with build.target"
        elif exported and flag.lstrip("-+").split("=")[0] == "fmiFilter":
            yield f"build.omc_flags: '{flag}' is not allowed for an exported FMU; set settings.emit_protected"


def _settings_problems(settings: session_config.RunSettings) -> Iterator[str]:
    parameters = settings.parameters
    if not (dataclasses.is_dataclass(parameters) and not isinstance(parameters, type)) and not isinstance(
        parameters, Mapping
    ):
        yield f"settings.parameters: expected a parameter dataclass instance, got {parameters!r}"
    for name in ("start_time", "stop_time", "interval", "tolerance", "timeout"):
        yield from _optional(f"settings.{name}", getattr(settings, name), _is_number, "a number")
    yield from _optional("settings.solver", settings.solver, str, "a solver name")
    if not isinstance(settings.variable_filter, str):
        yield f"settings.variable_filter: expected a regular expression, got {settings.variable_filter!r}"
    for name in ("emit_protected", "abort_on_chattering"):
        if not isinstance(getattr(settings, name), bool):
            yield f"settings.{name}: expected true or false, got {getattr(settings, name)!r}"


def _is_number(value: Any) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _optional(path: str, value: Any, check: type | Callable[[Any], bool], expected: str) -> Iterator[str]:
    valid = isinstance(value, check) if isinstance(check, type) else check(value)
    if value is not None and not valid:
        yield f"{path}: expected {expected} or null, got {value!r}"


def _existing(path: str, value: Any, check: Callable[[Path], bool], kind: str) -> Iterator[str]:
    if not isinstance(value, (str, os.PathLike)):
        yield f"{path}: expected a path, got {value!r}"
    elif not check(Path(value)):
        yield f"{path}: no such {kind} '{Path(value).absolute()}'"
