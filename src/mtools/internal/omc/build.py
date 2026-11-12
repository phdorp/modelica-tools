"""Build a model with one OMC process running a generated ``.mos`` script."""

from __future__ import annotations

import logging
import subprocess
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

import pandas as pd

from mtools.errors import CompileError, TranslationError
from mtools.internal.omc import cache, diagnostics, run, variants, workdir
from mtools.internal.omc.config import BuildConfig, RunSettings, Target
from mtools.internal.omc.init_xml import Variable, read_variables
from mtools.internal.omc.script import (Experiment, LoadedLibrary, Stage,
                                        build_script, parse_output)

logger = logging.getLogger(__name__)

OMC = "omc"
FILE_NAME_PREFIX = "model"
SCRIPT_NAME = "build.mos"

CPP_FMU_WARNING = (
    "Exporting '{model}' from the Cpp target: the FMU is Model Exchange only, time events"
    " (when sample(...)) broke silently under FMPy, and resources and shared libraries"
    " aren't copied into it."
)


@dataclass(frozen=True)
class Build:
    """One model compiled with one build config, ready to run any number of times.

    A build is never changed after it is made; runs write nothing into its directory.

    Attributes:
        config: The build config it was made from.
        directory: Directory holding the executable (or, for an FMU export, the FMU) and
            ``<prefix>_init.xml``.
        file_name_prefix: Name of the executable and its generated files.
        variables: Every variable of ``<prefix>_init.xml`` by name.
        experiment: The model's experiment annotation (OMC defaults where unset).
        loaded_libraries: The classes OMC had loaded (``getLoadedLibraries()``).
        owned: Whether the directory belongs to this build alone (``MTOOLS_NO_CACHE``)
            and is deleted by ``close()``; a cached build's directory never is.
        build_values: For a build variant, the modifier text of the parameters fixed in
            it, by name; empty for a plain build.
    """

    config: BuildConfig
    directory: Path
    file_name_prefix: str
    variables: Mapping[str, Variable]
    experiment: Experiment
    loaded_libraries: tuple[LoadedLibrary, ...]
    owned: bool = False
    build_values: Mapping[str, str] = field(default_factory=dict)

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
    def fmu_path(self) -> Path:
        """The exported FMU of a build whose config sets ``fmu``."""
        return self.directory / f"{self.file_name_prefix}.fmu"

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

        A requested parameter the plain build fixed (an array size, an if-equation
        selector, ``Evaluate=true``) is built into a variant first, which is cached like
        any build; the other parameters are set on the variant per run.
        """
        if not self.build_values:
            split = variants.split_parameters(settings.parameters, self.variables, self.model_name)
            if split.build_values:
                log_variant(self.model_name, split.build_values)
                with build(self.config, split.build_values) as variant:
                    return variant.simulate(replace(settings, parameters=dict(split.run_parameters)))
        return run.simulate(self, settings)


def log_variant(model_name: str, names: Iterable[str]) -> None:
    """Log at INFO that a variant of ``model_name`` is built because of the parameters ``names``."""
    quoted = [f"'{name}'" for name in names]
    logger.info(
        "Building a variant of '%s' because %s fixed at build time",
        model_name,
        ", ".join(quoted) + (" is" if len(quoted) == 1 else " are"),
    )


def build(config: BuildConfig, build_values: Mapping[str, str] | None = None) -> Build:
    """Build ``config``, or take it from the cache when nothing changed.

    With ``MTOOLS_NO_CACHE=1`` the build is made in a directory of its own under
    ``runs/``; call ``Build.close()`` (or use the build as a context manager) to delete it.

    Args:
        config: What to build.
        build_values: Modifier text by name of parameters to fix at build time; makes a
            variant (see ``Build.simulate``), cached under a key that includes them.

    Raises:
        TranslationError: OMC failed to set options, load or translate the model.
        CompileError: Compiling or linking the generated code failed.
    """
    if _is_cpp_export(config):
        logger.warning(CPP_FMU_WARNING.format(model=config.model_name))
    if workdir.no_cache():
        directory = workdir.new_run_directory("build-")
        result = _make(config, directory, build_values)
        logger.info("Built '%s' without cache in %s", config.model_name, directory)
        return replace(result, owned=True)

    key = cache.cache_key(config, build_values)
    hit = cache.lookup(key, config)
    if hit is None:
        result = _make(config, workdir.new_tmp_directory(), build_values)
        directory, published = cache.publish(result.directory, key)
        if published:
            logger.info("Built '%s' (cache key %s)", config.model_name, key[:12])
            return replace(result, directory=directory)
        hit = cache.lookup(key, config)
        if hit is None:  # removed again meanwhile; keep this build's data uncached
            return _make(config, workdir.new_run_directory("build-"), build_values)
    directory, record = hit
    logger.info("Reused cached build of '%s' (cache key %s)", config.model_name, key[:12])
    return Build(
        config=config,
        directory=directory,
        file_name_prefix=FILE_NAME_PREFIX,
        variables=read_variables(directory / f"{FILE_NAME_PREFIX}_init.xml"),
        experiment=record.experiment,
        loaded_libraries=record.loaded_libraries,
        build_values=dict(build_values or {}),
    )


def _make(config: BuildConfig, directory: Path, build_values: Mapping[str, str] | None) -> Build:
    """Run OMC in ``directory``; delete the directory if the build fails."""
    try:
        return _run_omc(config, directory, build_values)
    except BaseException:
        workdir.discard(directory)
        raise


def _run_omc(config: BuildConfig, directory: Path, build_values: Mapping[str, str] | None) -> Build:
    script = directory / SCRIPT_NAME
    script.write_text(build_script(config, FILE_NAME_PREFIX, build_values))
    logger.debug("Building '%s' in %s", config.model_name, directory)

    completed = subprocess.run(
        [OMC, SCRIPT_NAME], cwd=directory, capture_output=True, text=True, errors="replace", check=False
    )
    logger.debug(
        "omc exited with %d.\nstdout:\n%s\nstderr:\n%s", completed.returncode, completed.stdout, completed.stderr
    )
    output = parse_output(completed.stdout)
    stage_text = "\n".join(text for text in output.diagnostics.values() if text)
    if completed.returncode != 0 or output.experiment is None:
        raise _build_error(
            config, completed.returncode, stage_text, (completed.stdout + completed.stderr).strip(), directory
        )
    _log_build_diagnostics(config.model_name, stage_text)

    if _is_cpp_export(config):
        _extract_init_xml(config, directory)
    cache.save_record(directory, cache.new_record(config, output.experiment, output.loaded_libraries))
    return Build(
        config=config,
        directory=directory,
        file_name_prefix=FILE_NAME_PREFIX,
        variables=read_variables(directory / f"{FILE_NAME_PREFIX}_init.xml"),
        experiment=output.experiment,
        loaded_libraries=output.loaded_libraries,
        build_values=dict(build_values or {}),
    )


def _is_cpp_export(config: BuildConfig) -> bool:
    """Whether ``config`` exports an FMU from the Cpp target."""
    return config.fmu is not None and config.target == "Cpp"


def _extract_init_xml(config: BuildConfig, directory: Path) -> None:
    """Copy ``<prefix>_init.xml`` out of the FMU that ``config`` exported into ``directory``:
    ``translateModel`` writes none for Cpp.

    Raises:
        CompileError: The FMU is no zip archive or holds no ``sources/<prefix>_init.xml``.
    """
    name = f"{FILE_NAME_PREFIX}_init.xml"
    fmu_path = directory / f"{FILE_NAME_PREFIX}.fmu"
    try:
        with zipfile.ZipFile(fmu_path) as archive:
            (directory / name).write_bytes(archive.read(f"sources/{name}"))
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise CompileError(
            f"Modelica build failed for '{config.model_name}' ({Path(config.model_path).absolute()}):",
            model_name=config.model_name,
            diagnostics=f"can't read sources/{name} from the exported FMU {fmu_path}: {error}",
        ) from None


def _log_build_diagnostics(model_name: str, stage_text: str) -> None:
    """Log what OMC and the C compiler said about a build that succeeded."""
    if warnings := diagnostics.translation_warnings(stage_text):
        logger.warning("Modelica translation of '%s' reported warnings:\n%s", model_name, warnings)
    if notes := diagnostics.notifications(stage_text):
        logger.debug("OMC notifications for '%s':\n%s", model_name, notes)
    if compiler := diagnostics.compiler_warnings(stage_text):
        logger.debug("C compiler warnings for '%s':\n%s", model_name, compiler)


def _build_error(
    config: BuildConfig, returncode: int, stage_text: str, raw_output: str, directory: Path
) -> TranslationError | CompileError:
    """The exception for a failed build; ``stage_text`` is OMC's error strings, ``raw_output`` its raw output.

    Under ``MTOOLS_KEEP_RUNS=1`` the diagnostics end with the kept build directory.
    """
    source = Path(config.model_path).absolute()
    if returncode == Stage.COMPILE:
        return CompileError(
            f"Modelica build failed for '{config.model_name}' ({source}):",
            model_name=config.model_name,
            diagnostics=workdir.with_run_directory(diagnostics.filter_compile(stage_text or raw_output), directory),
        )
    return TranslationError(
        f"Modelica translation failed for '{config.model_name}' ({source}):",
        model_name=config.model_name,
        diagnostics=workdir.with_run_directory(
            diagnostics.filter_translation(stage_text) or diagnostics.filter_translation(raw_output) or raw_output,
            directory,
        ),
    )
