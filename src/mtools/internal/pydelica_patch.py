"""Workarounds for pydelica multi-file compilation and Cpp target simulation.

``_compile_without_source_copy`` is a copy of ``pydelica.compiler.Compiler.compile``
(pydelica 0.6.3) with only the temp-source-staging step removed: upstream copies the
single ``.mo`` file (and ``extra_models``) flat into its own temporary directory, which
destroys the sibling ``.mo`` files / ``Resources/`` layout that OMC needs to resolve
``within`` members across multiple files. This variant points OMC at the original source
path so the relative layout is preserved.

When OMC's ``Cpp`` simulation target is selected (``--simCodeTarget=Cpp``) the generated
XML contains no ``DefaultExperiment`` element and the resulting binary reads simulation
options from the command line rather than from that XML. pydelica 0.6.x assumes the C
target layout, so this module also:

* injects a ``DefaultExperiment`` derived from OMC's generated ``<model>.sh`` wrapper so
  pydelica can construct its ``SimulationOptions``, and
* translates those options to the Cpp runtime's command-line flags at simulation time.

Note on resource resolution: because the source is compiled in place, relative references
in external C code and ``modelica://`` / ``loadResource``-style paths resolve against the
*workspace* location of the model, not the temporary build directory. The C sources are
still mirrored into ``<temp_build_dir>/Resources/Include`` because OMC's generated makefile
is run with ``cwd=<temp_build_dir>`` and may reference them relative to that directory. The
two copies are identical, so both roots resolve consistently as long as the model's
``Resources/Include`` directory remains next to the ``.mo`` file in the workspace.

The patch is validated against pydelica 0.6.x (see ``_SUPPORTED_PYDELICA_MAJOR_MINOR``);
``install_pydelica_patch`` refuses to install against other versions so the copy cannot
drift silently on upgrades.
"""

from __future__ import annotations

import glob
import logging
import os
import pathlib
import platform
import shlex
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ElementTree
from importlib import metadata
from typing import Any, Callable, MutableMapping

import pydantic
import pydelica.exception as pde
from pydelica.options import LibrarySetup

_SUPPORTED_PYDELICA_MAJOR_MINOR = "0.6"

_PATCH_INSTALLED = False

_ORIGINAL_SIMULATE: Callable[..., None] | None = None

_ORIGINAL_SIMULATION_OPTIONS_INIT: Callable[..., None] | None = None


#: OMC option used to select the simulation code-generation target.
_CPP_SIMCODE_TARGET_FLAG = "simcodetarget"

#: Simulation option names parsed from the generated Cpp shell wrapper.
_CPP_SHELL_FLAG_OPTIONS = {
    "-S": "startTime",
    "-E": "stopTime",
    "-H": "stepSize",
    "-G": "numberOfIntervals",
    "-P": "outputFormat",
    "-T": "tolerance",
    "-I": "solver",
    "-B": "variableFilter",
}

#: Fallbacks used when OMC does not emit a shell wrapper alongside the model XML.
_CPP_DEFAULT_SIMULATION_OPTIONS = {
    "startTime": "0.0",
    "stopTime": "1.0",
    "stepSize": "0.002",
    "numberOfIntervals": "500",
    "outputFormat": "mat",
    "tolerance": "1e-6",
    "solver": "dassl",
    "variableFilter": ".*",
}

#: Cpp runtime flags corresponding to pydelica simulation option names.
_CPP_SIMULATION_OPTION_FLAGS = {
    "startTime": "-S",
    "stopTime": "-E",
    "stepSize": "-H",
    "numberOfIntervals": "-G",
    "tolerance": "-T",
    "solver": "-I",
    "variableFilter": "-B",
}


def _is_cpp_target(omc_flags: dict[str, str | None]) -> bool:
    """Return whether OMC flags select the Cpp simulation target."""
    for flag, value in omc_flags.items():
        if flag.lstrip("-").lower() == _CPP_SIMCODE_TARGET_FLAG:
            return value is not None and value.lower() == "cpp"
    return False


def _cpp_shell_script(xml_file: pathlib.Path, model_name: str | None) -> pathlib.Path | None:
    """Find the shell wrapper OMC generated for a model's Cpp binary."""
    candidates = []
    if model_name:
        candidates.append(xml_file.parent.joinpath(f"{model_name}.sh"))
    candidates.append(xml_file.parent.joinpath(f"{xml_file.stem.removesuffix('_init')}.sh"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    scripts = list(xml_file.parent.glob("*.sh"))
    return scripts[0] if len(scripts) == 1 else None


def _cpp_default_simulation_options(script: pathlib.Path | None) -> dict[str, str]:
    """Read default simulation options from an OMC-generated Cpp shell wrapper."""
    options = dict(_CPP_DEFAULT_SIMULATION_OPTIONS)
    if script is None or not script.exists():
        return options
    try:
        tokens = shlex.split(script.read_text())
    except OSError:
        return options
    for index, token in enumerate(tokens[:-1]):
        option_name = _CPP_SHELL_FLAG_OPTIONS.get(token)
        if option_name:
            options[option_name] = tokens[index + 1]
    return options


def _inject_cpp_default_experiment(xml_file: pathlib.Path) -> None:
    """Add a ``DefaultExperiment`` element to Cpp-generated model XML in place.

    pydelica constructs ``SimulationOptions`` from this element, but OMC's Cpp target
    does not emit it. The values are taken from the shell wrapper generated next to the
    XML, which contains the experiment annotation defaults OMC compiled into the binary.
    """
    tree = ElementTree.parse(xml_file)
    root = tree.getroot()
    if root.find("DefaultExperiment") is not None:
        return
    script = _cpp_shell_script(xml_file, root.get("modelName"))
    options = _cpp_default_simulation_options(script)
    root.insert(0, ElementTree.Element("DefaultExperiment", options))
    tree.write(xml_file, encoding="UTF-8", xml_declaration=True)


def _inject_cpp_default_experiments(build_dir: str, logger: logging.Logger) -> None:
    """Inject ``DefaultExperiment`` into every Cpp-generated model XML in ``build_dir``."""
    for xml_file in glob.glob(os.path.join(build_dir, "*_init.xml")):
        try:
            _inject_cpp_default_experiment(pathlib.Path(xml_file))
        except (ElementTree.ParseError, OSError):
            logger.warning("Failed to add default experiment to '%s'", xml_file, exc_info=True)


def _cpp_variable_filter(filter_str: str) -> str:
    """Translate mtools' default wildcard filter to the Cpp runtime's regex syntax."""
    return ".*" if filter_str in ("", "*") else filter_str


def _simulation_options_init_with_cpp_fallback(self: Any, xml_model_file: Any) -> None:
    """Create pydelica simulation options, supplying Cpp XML defaults when missing.

    Some OMC Cpp builds write model XML without a ``DefaultExperiment`` element, which
    makes pydelica 0.6.x raise ``IndexError``. Adding the element before delegating keeps
    both option reads and later writes working for all supported OMC XML layouts.
    """
    assert _ORIGINAL_SIMULATION_OPTIONS_INIT is not None
    try:
        _inject_cpp_default_experiment(pathlib.Path(xml_model_file))
    except (ElementTree.ParseError, OSError):
        # Let pydelica report its own error for unreadable or unexpected XML.
        pass
    _ORIGINAL_SIMULATION_OPTIONS_INIT(self, xml_model_file)


def _pydelica_version() -> str:
    """Return the installed pydelica version from package metadata."""
    return metadata.version("pydelica")


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
        # Stage the C sources into the build dir for the makefile step (run with
        # cwd=<temp_build_dir>). Unlike upstream, the .mo is compiled in place, so
        # modelica:// / loadResource-style paths and relative references in the C
        # code resolve against the workspace Resources/ tree, not this copy. The
        # two copies are identical, so both roots agree as long as Resources/Include
        # stays next to the source file.
        _prepare_c_incls(self._logger, f"{c_source_dir}", f"{_temp_build_dir}")

    if not modelica_source_file.exists():
        raise FileNotFoundError(
            f"Could not compile Modelica file '{modelica_source_file}',"
            " file does not exist"
        )

    # Deviation from upstream: pydelica 0.6.3 stages the source (and extra_models) by
    # copying them flat into a temp dir and compiling from there, which drops sibling
    # .mo files / Resources/ and breaks 'within' resolution. We instead compile the
    # original file in place so the relative layout is preserved.
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

    _make_files = glob.glob(os.path.join(_temp_build_dir, "*.makefile"))

    if not _make_files:
        self._logger.error(
            "Output directory contents [%s]: %s",
            _temp_build_dir,
            os.listdir(_temp_build_dir),
        )
        raise pde.ModelicaFileGenerationError(
            f"Failed to find a Makefile in the directory: {_temp_build_dir}, "
            "Modelica failed to generated required files."
        )

    _make_cmd: str
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
    else:
        _make_path = shutil.which("make")
        if _make_path is None:
            raise pde.BinaryNotFoundError("Could not find GNU-Make on this system")
        _make_cmd = _make_path

    _build_cmd: list[str] = [_make_cmd, "-f", _make_files[0]]

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

    if _is_cpp_target(self._omc_flags):
        _inject_cpp_default_experiments(_temp_build_dir, self._logger)

    self._binary_dirs.append(_temp_build_dir)
    return pathlib.Path(_temp_build_dir)


class _CppRuntimeOptions:
    """Expose Cpp runtime flags through pydelica's ``assemble_args`` interface.

    ``pydelica.Session.simulate`` appends the arguments returned by the model's runtime
    options object. For the Cpp target the simulation options are command-line flags, so
    this adapter reads pydelica's (XML-backed) simulation options and emits them in the
    form accepted by the Cpp binary.
    """

    _OUTPUT_EXTENSIONS = {"csv": "csv", "mat": "mat", "plt": "plt"}

    def __init__(
        self,
        model_name: str,
        simulation_options: MutableMapping[str, Any],
        runtime_options: Any,
    ) -> None:
        object.__setattr__(self, "_model_name", model_name.replace(".", "_"))
        object.__setattr__(self, "_simulation_options", simulation_options)
        object.__setattr__(self, "_runtime_options", runtime_options)

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_runtime_options"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_runtime_options"), name, value)

    def assemble_args(self) -> list[str]:
        """Return Cpp simulation flags for the configured model run."""
        options = object.__getattribute__(self, "_simulation_options")
        args: list[str] = []
        for option_name, flag in _CPP_SIMULATION_OPTION_FLAGS.items():
            value = options.get(option_name)
            if value is not None and value != "":
                if option_name == "variableFilter":
                    value = _cpp_variable_filter(str(value))
                args.extend([flag, str(value)])

        output_format = str(options.get("outputFormat") or "csv").lower()
        extension = self._OUTPUT_EXTENSIONS.get(output_format, output_format)
        args.extend(["-P", output_format])
        args.extend(["-F", f"{self._model_name}_res.{extension}"])

        emit_protected = bool(getattr(self._runtime_options, "emit_protected", False))
        args.extend(["-U", "protected" if emit_protected else "public"])
        return args


def _simulate_with_cpp_options(self: Any, model_name: str | None = None, verbosity: Any = None) -> None:
    """Run pydelica's simulation, adding Cpp-specific runtime arguments when needed."""
    if _ORIGINAL_SIMULATE is None or not _is_cpp_target(
        getattr(self._compiler, "_omc_flags", {})
    ):
        assert _ORIGINAL_SIMULATE is not None
        return _ORIGINAL_SIMULATE(self, model_name=model_name, verbosity=verbosity)

    resolved_model = model_name or self.default_model
    try:
        model_key = self._get_cache_key(resolved_model, self._simulation_opts)
    except KeyError:
        return _ORIGINAL_SIMULATE(self, model_name=model_name, verbosity=verbosity)

    runtime_options = self._runtime_opts[model_key]
    self._runtime_opts[model_key] = _CppRuntimeOptions(
        model_key, self._simulation_opts[model_key], runtime_options
    )
    try:
        return _ORIGINAL_SIMULATE(self, model_name=model_name, verbosity=verbosity)
    finally:
        self._runtime_opts[model_key] = runtime_options


def install_pydelica_patch() -> None:
    global _PATCH_INSTALLED, _ORIGINAL_SIMULATE, _ORIGINAL_SIMULATION_OPTIONS_INIT
    if _PATCH_INSTALLED:
        return

    _version = _pydelica_version()
    if not _version.startswith(_SUPPORTED_PYDELICA_MAJOR_MINOR):
        raise RuntimeError(
            f"install_pydelica_patch was validated against pydelica "
            f"{_SUPPORTED_PYDELICA_MAJOR_MINOR}.x but pydelica {_version} is installed. "
            "Update pydelica_patch._compile_without_source_copy to match the upstream "
            "pydelica.compiler.Compiler.compile of the installed version."
        )

    import pydelica
    import pydelica.compiler as pydelica_compiler
    import pydelica.options.simulation as pydelica_simulation

    pydelica_compiler.Compiler.compile = _compile_without_source_copy
    if _ORIGINAL_SIMULATE is None:
        _ORIGINAL_SIMULATE = pydelica.Session.simulate
    pydelica.Session.simulate = _simulate_with_cpp_options
    if _ORIGINAL_SIMULATION_OPTIONS_INIT is None:
        _ORIGINAL_SIMULATION_OPTIONS_INIT = pydelica_simulation.SimulationOptions.__init__
    pydelica_simulation.SimulationOptions.__init__ = (
        _simulation_options_init_with_cpp_fallback
    )
    _PATCH_INSTALLED = True