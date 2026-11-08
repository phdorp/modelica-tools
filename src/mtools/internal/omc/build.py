"""Build a model with one OMC process running a generated ``.mos`` script."""

from __future__ import annotations

import logging
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from mtools.errors import CompileError, TranslationError
from mtools.internal.omc import run
from mtools.internal.omc.config import BuildConfig, RunSettings, Target
from mtools.internal.omc.init_xml import Variable, read_variables
from mtools.internal.omc.script import (Experiment, LoadedLibrary, Stage,
                                        build_script, parse_output)

logger = logging.getLogger(__name__)

OMC = "omc"
FILE_NAME_PREFIX = "model"
SCRIPT_NAME = "build.mos"


@dataclass(frozen=True)
class Build:
    """One model compiled with one build config, ready to run any number of times.

    A build is never changed after it is made; runs write nothing into its directory.

    Attributes:
        config: The build config it was made from.
        directory: Directory holding the executable and ``<prefix>_init.xml``.
        file_name_prefix: Name of the executable and its generated files.
        variables: Every variable of ``<prefix>_init.xml`` by name.
        experiment: The model's experiment annotation (OMC defaults where unset).
        loaded_libraries: The classes OMC had loaded (``getLoadedLibraries()``).
    """

    config: BuildConfig
    directory: Path
    file_name_prefix: str
    variables: Mapping[str, Variable]
    experiment: Experiment
    loaded_libraries: tuple[LoadedLibrary, ...]

    @property
    def model_name(self) -> str:
        return self.config.model_name

    @property
    def target(self) -> Target:
        return self.config.target

    @property
    def parameters(self) -> dict[str, Variable]:
        """The variables a run may name: parameters, and other variables whose start
        value a run can change (e.g. states)."""
        return {
            name: variable
            for name, variable in self.variables.items()
            if variable.variability == "parameter" or variable.changeable
        }

    def simulate(self, settings: RunSettings) -> pd.DataFrame:
        """Run the build with ``settings`` and return its result."""
        return run.simulate(self, settings)


def build(config: BuildConfig) -> Build:
    """Build ``config`` in a fresh build directory.

    Raises:
        TranslationError: OMC failed to set options, load or translate the model.
        CompileError: Compiling or linking the generated code failed.
    """
    directory = _new_build_directory()
    script = directory / SCRIPT_NAME
    script.write_text(build_script(config, FILE_NAME_PREFIX))
    logger.debug("Building '%s' in %s", config.model_name, directory)

    completed = subprocess.run(
        [OMC, SCRIPT_NAME], cwd=directory, capture_output=True, text=True, errors="replace", check=False
    )
    logger.debug(
        "omc exited with %d.\nstdout:\n%s\nstderr:\n%s", completed.returncode, completed.stdout, completed.stderr
    )
    output = parse_output(completed.stdout)
    if completed.returncode != 0 or output.experiment is None:
        diagnostics = "\n".join(text for text in output.diagnostics.values() if text)
        raise _build_error(config, completed.returncode, diagnostics or (completed.stdout + completed.stderr).strip())

    return Build(
        config=config,
        directory=directory,
        file_name_prefix=FILE_NAME_PREFIX,
        variables=read_variables(directory / f"{FILE_NAME_PREFIX}_init.xml"),
        experiment=output.experiment,
        loaded_libraries=output.loaded_libraries,
    )


def _new_build_directory() -> Path:
    """Return a new, empty build directory."""
    return Path(tempfile.mkdtemp(prefix="mtools-build-"))


def _build_error(config: BuildConfig, returncode: int, diagnostics: str) -> TranslationError | CompileError:
    source = Path(config.model_path).absolute()
    if returncode == Stage.COMPILE:
        return CompileError(
            f"Modelica build failed for '{config.model_name}' ({source}):",
            model_name=config.model_name,
            diagnostics=diagnostics,
        )
    return TranslationError(
        f"Modelica translation failed for '{config.model_name}' ({source}):",
        model_name=config.model_name,
        diagnostics=diagnostics,
    )
