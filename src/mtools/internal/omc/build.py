"""Build a model with one OMC process running a generated ``.mos`` script."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import pandas as pd

from mtools.errors import CompileError, TranslationError
from mtools.internal.omc import cache, run, workdir
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
        owned: Whether the directory belongs to this build alone (``MTOOLS_NO_CACHE``)
            and is deleted by ``close()``; a cached build's directory never is.
    """

    config: BuildConfig
    directory: Path
    file_name_prefix: str
    variables: Mapping[str, Variable]
    experiment: Experiment
    loaded_libraries: tuple[LoadedLibrary, ...]
    owned: bool = False

    def close(self) -> None:
        """Delete the build directory if this build owns it (uncached); else do nothing."""
        if self.owned:
            workdir.discard(self.directory)

    def __enter__(self) -> Build:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

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
        """Run the build with ``settings`` and return its result.

        The run directory is deleted when this returns or raises (``MTOOLS_KEEP_RUNS=1``
        keeps it).
        """
        return run.simulate(self, settings)


def build(config: BuildConfig) -> Build:
    """Build ``config``, or take it from the cache when nothing changed.

    With ``MTOOLS_NO_CACHE=1`` the build is made in a directory of its own under
    ``runs/``; call ``Build.close()`` (or use the build as a context manager) to delete it.

    Raises:
        TranslationError: OMC failed to set options, load or translate the model.
        CompileError: Compiling or linking the generated code failed.
    """
    if workdir.no_cache():
        directory = workdir.new_run_directory("build-")
        result = _make(config, directory)
        logger.info("Built '%s' without cache in %s", config.model_name, directory)
        return replace(result, owned=True)

    key = cache.cache_key(config)
    hit = cache.lookup(key, config)
    if hit is None:
        result = _make(config, workdir.new_tmp_directory())
        directory, published = cache.publish(result.directory, key)
        if published:
            logger.info("Built '%s' (cache key %s)", config.model_name, key[:12])
            return replace(result, directory=directory)
        hit = cache.lookup(key, config)
        if hit is None:  # removed again meanwhile; keep this build's data uncached
            return _make(config, workdir.new_run_directory("build-"))
    directory, record = hit
    logger.info("Reused cached build of '%s' (cache key %s)", config.model_name, key[:12])
    return Build(
        config=config,
        directory=directory,
        file_name_prefix=FILE_NAME_PREFIX,
        variables=read_variables(directory / f"{FILE_NAME_PREFIX}_init.xml"),
        experiment=record.experiment,
        loaded_libraries=record.loaded_libraries,
    )


def _make(config: BuildConfig, directory: Path) -> Build:
    """Run OMC in ``directory``; delete the directory if the build fails."""
    try:
        return _run_omc(config, directory)
    except BaseException:
        workdir.discard(directory)
        raise


def _run_omc(config: BuildConfig, directory: Path) -> Build:
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
        diagnostics = diagnostics or (completed.stdout + completed.stderr).strip()
        raise _build_error(config, completed.returncode, workdir.with_run_directory(diagnostics, directory))

    cache.save_record(
        directory,
        cache.BuildRecord(
            output.experiment,
            output.loaded_libraries,
            cache.library_hashes(config, output.loaded_libraries),
        ),
    )
    return Build(
        config=config,
        directory=directory,
        file_name_prefix=FILE_NAME_PREFIX,
        variables=read_variables(directory / f"{FILE_NAME_PREFIX}_init.xml"),
        experiment=output.experiment,
        loaded_libraries=output.loaded_libraries,
    )


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
