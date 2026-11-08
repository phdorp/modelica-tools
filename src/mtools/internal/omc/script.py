"""Generate the ``.mos`` build script and parse what it prints.

The script runs every build stage in order. After each stage it prints a marked
section with ``getErrorString()`` and, when the stage failed, calls ``exit`` with the
stage's code, because an OMC script otherwise exits 0. Values the build records (the
loaded libraries and the experiment annotation) are echoed into marked data sections.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from mtools.internal.omc.config import BuildConfig, Library


class Stage(IntEnum):
    """Build-script stages; each value is the script's exit code when the stage fails."""

    OPTIONS = 11
    LIBRARY_PATH = 12
    LOAD_LIBRARIES = 13
    LOAD_SOURCES = 14
    LOADED_LIBRARIES = 15
    SIMULATION_OPTIONS = 16
    TRANSLATE = 17
    COMPILE = 18


DEFAULT_SOLVER = "dassl"


@dataclass(frozen=True)
class Experiment:
    """The model's experiment settings, as OMC reads them from its annotations."""

    start_time: float
    stop_time: float
    interval: float
    tolerance: float
    solver: str


@dataclass(frozen=True)
class LoadedLibrary:
    """A top-level class loaded during the build and the directory it came from."""

    name: str
    path: Path


@dataclass(frozen=True)
class ScriptOutput:
    """What a build script printed.

    Attributes:
        diagnostics: ``getErrorString()`` output per stage that ran.
        loaded_libraries: Result of ``getLoadedLibraries()``; empty if not reached.
        experiment: The experiment annotation; ``None`` if not reached.
    """

    diagnostics: Mapping[Stage, str]
    loaded_libraries: tuple[LoadedLibrary, ...]
    experiment: Experiment | None


_BEGIN = "@@mtools:begin"
_END = "@@mtools:end"


def build_script(config: BuildConfig, file_name_prefix: str) -> str:
    """Return the ``.mos`` script that builds ``config`` in the current directory.

    Args:
        config: The build config.
        file_name_prefix: Name of the generated executable and its files.
    """
    model = config.model_name
    flags = " ".join([f"--simCodeTarget={config.target}", "-q", *map(_flag, config.omc_flags.items())])
    lines = _checked(f"ok := setCommandLineOptions({_string(flags)});", Stage.OPTIONS)

    directories = [str(library.directory) for library in config.libraries if library.directory is not None]
    if directories:
        prefix = _string(":".join(directories) + ":")
        lines += _checked(f"ok := setModelicaPath({prefix} + getModelicaPath());", Stage.LIBRARY_PATH)

    for library in config.libraries:
        lines += _checked(f"ok := {_load_model(library)};", Stage.LOAD_LIBRARIES)

    for source in [*config.extra_sources, config.model_path]:
        lines += _checked(f"ok := loadFile({_string(str(Path(source).absolute()))});", Stage.LOAD_SOURCES)

    lines += _data("loaded_libraries", "getLoadedLibraries();")
    lines += [_errors(Stage.LOADED_LIBRARIES)]

    lines += _data("simulation_options", f"getSimulationOptions({model});")
    lines += _data("solver", f'getAnnotationModifierValue({model}, "__OpenModelica_simulationFlags", "s");')
    lines += [_errors(Stage.SIMULATION_OPTIONS)]

    lines += [
        f"result := buildModel({model}, fileNamePrefix={_string(file_name_prefix)});",
        _errors(Stage.TRANSLATE),
        # buildModel reports translation and make failures alike; a makefile means
        # translation succeeded and make failed.
        f'if result[1] == "" then'
        f" if regularFileExists({_string(file_name_prefix + '.makefile')}) then exit({int(Stage.COMPILE)});"
        f" else exit({int(Stage.TRANSLATE)}); end if; end if;",
    ]
    return "\n".join(lines) + "\n"


def parse_output(stdout: str) -> ScriptOutput:
    """Parse the marked sections a build script printed to stdout."""
    errors: dict[Stage, str] = {}
    data: dict[str, str] = {}
    section: tuple[str, str] | None = None
    content: list[str] = []
    for line in stdout.splitlines():
        if section is None and line.startswith(_BEGIN):
            kind, name = line[len(_BEGIN) :].split()
            section, content = (kind, name), []
        elif section is not None and line == _END:
            kind, name = section
            text = "\n".join(content).strip()
            if kind == "errors":
                errors[Stage(int(name))] = text
            else:
                data[name] = text
            section = None
        elif section is not None:
            content.append(line)

    return ScriptOutput(
        diagnostics=errors,
        loaded_libraries=_loaded_libraries(data.get("loaded_libraries", "")),
        experiment=_experiment(data) if "simulation_options" in data else None,
    )


def _checked(statement: str, stage: Stage) -> list[str]:
    return [statement, _errors(stage), f"if not ok then exit({int(stage)}); end if;"]


def _errors(stage: Stage) -> str:
    return f'print("{_BEGIN} errors {int(stage)}\\n" + getErrorString() + "\\n{_END}\\n");'


def _data(name: str, call: str) -> list[str]:
    """Echo the result of ``call`` into a data section."""
    return [f'print("{_BEGIN} data {name}\\n");', call, f'print("{_END}\\n");']


def _flag(item: tuple[str, str | None]) -> str:
    name, value = item
    return name if value is None else f"{name}={value}"


def _load_model(library: Library) -> str:
    if library.version is None:
        return f"loadModel({library.name})"
    return f"loadModel({library.name}, {{{_string(library.version)}}}, requireExactVersion=true)"


def _string(value: str) -> str:
    """Quote ``value`` as a Modelica string literal."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


_QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _unquote(literal: str) -> str:
    return re.sub(r"\\(.)", r"\1", literal)


def _loaded_libraries(text: str) -> tuple[LoadedLibrary, ...]:
    strings = [_unquote(match) for match in _QUOTED.findall(text)]
    return tuple(LoadedLibrary(name, Path(path)) for name, path in zip(strings[::2], strings[1::2]))


def _experiment(data: Mapping[str, str]) -> Experiment:
    start, stop, tolerance, _intervals, interval = data["simulation_options"].strip("()").split(",")
    solvers = _QUOTED.findall(data.get("solver", ""))
    solver = _unquote(solvers[0]) if solvers and solvers[0] else DEFAULT_SOLVER
    return Experiment(
        start_time=float(start),
        stop_time=float(stop),
        interval=float(interval),
        tolerance=float(tolerance),
        solver=solver,
    )
