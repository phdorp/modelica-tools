from __future__ import annotations

import glob
import logging
import os
import pathlib
import platform
import shutil
import subprocess
import tempfile

import pydantic

import pydelica.exception as pde
from pydelica.options import LibrarySetup


_PATCH_INSTALLED = False


def _prepare_c_incls(logger: logging.Logger, c_source_dir: str, temp_dir: str) -> None:
    logger.debug("Checking for C sources in '%s'", c_source_dir)
    c_sources = glob.glob(os.path.join(c_source_dir, "*.c"))
    c_sources += glob.glob(os.path.join(c_source_dir, "*.C"))
    include_dir = os.path.join(temp_dir, "Resources", "Include")
    os.makedirs(include_dir)
    for source in c_sources:
        file_name = os.path.basename(source)
        logger.debug("Found '%s'", file_name)
        shutil.copy(source, os.path.join(include_dir, file_name))


@pydantic.validate_call
def _compile_without_source_copy(
    self,
    modelica_source_file: pydantic.FilePath,
    model_addr: str | None = None,
    c_source_dir: pydantic.DirectoryPath | None = None,
    extra_models: list[str] | None = None,
    custom_library_spec: list[dict[str, str]] | None = None,
) -> pathlib.Path:
    _temp_build_dir = tempfile.mkdtemp()

    _candidate_c_inc = modelica_source_file.parent.joinpath("Resources", "Include")
    if os.path.exists(_candidate_c_inc) and not c_source_dir:
        c_source_dir = _candidate_c_inc

    modelica_source_file = modelica_source_file.absolute()

    if c_source_dir:
        _prepare_c_incls(self._logger, f"{c_source_dir}", f"{_temp_build_dir}")

    if not modelica_source_file.exists():
        raise FileNotFoundError(
            f"Could not compile Modelica file '{modelica_source_file}',"
            " file does not exist"
        )

    _args = [self._omc_binary, "-s", str(modelica_source_file)]

    if extra_models:
        for model in extra_models:
            _orig_model = modelica_source_file.parent.joinpath(model)
            if not os.path.exists(_orig_model):
                raise FileNotFoundError(
                    f"Could not compile supplementary Modelica file '{model}',"
                    " file does not exist"
                )
            _args.append(str(_orig_model))

    _args.append("Modelica")

    if model_addr:
        _args.append(f"+i={model_addr}")

    for flag, value in self._omc_flags.items():
        if not value:
            _args.append(flag)
        else:
            _args.append(f"{flag}={value}")

    _cmd_str = " ".join(_args)
    self._logger.debug(f"Executing Command: {_cmd_str}")

    _gen = None

    with LibrarySetup() as library:
        for lib in custom_library_spec or []:
            library.use_library(**lib)

        _environ = os.environ.copy()
        if library.session_library:
            _environ["OPENMODELICALIBRARY"] = library.session_library

        try:
            _gen = subprocess.run(
                _args,
                shell=False,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                env=_environ,
                cwd=_temp_build_dir,
            )

            pde.parse_error_string_compiler(_gen.stdout, _gen.stderr)
        except FileNotFoundError as e:
            self._logger.error("Failed to run command '%s'", _cmd_str)
            self._logger.debug("PATH: %s", self._environment["PATH"])
            if _gen:
                self._logger.error("Traceback: %s", _gen.stdout)
            raise e from e
        except pde.OMExecutionError as e:
            self._logger.error("Failed to run command '%s'", _cmd_str)
            if _gen:
                self._logger.error("Traceback: %s", _gen.stdout)
            raise e from e
        except pde.OMBuildError as e:
            if "lexer failed" in e.args[0]:
                self._logger.warning(e.args[0])
            else:
                if _gen:
                    self._logger.error("Traceback: %s", _gen.stdout)
                raise e from e

        if not _gen:
            raise RuntimeError("Failed to execute model generation")

        if _gen.returncode != 0:
            raise pde.OMBuildError(
                f"Model build configuration failed with exit code {_gen.returncode}:\n\t{_gen.stderr}"
            )

        self._logger.debug(_gen.stdout)

        if _gen.stderr:
            self._logger.error(_gen.stderr)

    _make_file = glob.glob(os.path.join(_temp_build_dir, "*.makefile"))

    if not _make_file:
        self._logger.error(
            "Output directory contents [%s]: %s",
            _temp_build_dir,
            os.listdir(_temp_build_dir),
        )
        raise pde.ModelicaFileGenerationError(
            f"Failed to find a Makefile in the directory: {_temp_build_dir}, "
            "Modelica failed to generated required files."
        )

    if platform.system() == "Windows":
        _make_binaries = glob.glob(
            os.path.join(
                os.environ["OPENMODELICAHOME"],
                "tools",
                "msys",
                "mingw*",
                "bin",
                "mingw*-make.exe",
            )
        )

        if not _make_binaries:
            raise pde.BinaryNotFoundError(
                "Failed to find Make binary in Modelica directories"
            )

        _make_cmd = _make_binaries[0]
    elif not shutil.which("make"):
        raise pde.BinaryNotFoundError("Could not find GNU-Make on this system")
    else:
        _make_cmd = shutil.which("make")

    _make_file = _make_file[0]
    _build_cmd = [_make_cmd, "-f", _make_file]

    if platform.system() == "Windows":
        _build_cmd.extend(("-w", "OMC_LDFLAGS_LINK_TYPE=static"))
    self._logger.debug(f"Build Command: {' '.join(_build_cmd)}")

    _build = subprocess.run(
        _build_cmd,
        shell=False,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=self._environment,
        cwd=_temp_build_dir,
    )

    try:
        pde.parse_error_string_compiler(_build.stdout, _build.stderr)
    except pde.OMBuildError as e:
        self._logger.error(_build.stderr)
        raise e from e

    if _build.stdout:
        self._logger.debug(_build.stdout)

    if _build.stderr:
        self._logger.error(_build.stderr)

    if _build.returncode != 0:
        raise pde.OMBuildError(
            f"Model build failed with exit code {_build.returncode}:\n\t{_build.stderr}"
        )

    self._binary_dirs.append(_temp_build_dir)
    return pathlib.Path(_temp_build_dir)


def install_pydelica_patch() -> None:
    global _PATCH_INSTALLED
    if _PATCH_INSTALLED:
        return

    import pydelica.compiler as pydelica_compiler

    pydelica_compiler.Compiler.compile = _compile_without_source_copy
    _PATCH_INSTALLED = True