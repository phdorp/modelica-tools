from __future__ import annotations

import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Callable, Dict

import pydantic
import pydelica  # type: ignore[import-untyped]

from mtools.internal.pydelica_patch import install_pydelica_patch

if TYPE_CHECKING:
    import mtools.session_config as session_config

_OMC_PASSTHROUGH_FILTER_INSTALLED: bool = False


class _OmcPassthroughFilter(logging.Filter):
    """Suppress known non-error OMC compiler output logged at ERROR level."""

    _patterns = ("Notification: Automatically loaded package",)

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR:
            msg = record.getMessage()
            if any(pattern in msg for pattern in self._patterns):
                return False
        return True


def _install_omc_logging_filter() -> None:
    global _OMC_PASSTHROUGH_FILTER_INSTALLED
    if _OMC_PASSTHROUGH_FILTER_INSTALLED:
        return
    _OMC_PASSTHROUGH_FILTER_INSTALLED = True
    compiler_logger = logging.getLogger("PyDelica.Compiler")
    compiler_logger.addFilter(_OmcPassthroughFilter())


def _install_pydelica_runtime_patch() -> None:
    install_pydelica_patch()


def flatten_nested_dict(data: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """Flatten a nested dictionary into dotted-key paths.

    Args:
        data: Nested dictionary to flatten.
        parent_key: Prefix used for recursive calls.
        sep: Separator used between nested key segments.

    Returns:
        A flat dictionary where nested keys are joined by ``sep``.
    """
    flattened = dict()
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else str(key)
        if isinstance(value, dict):
            flattened.update(flatten_nested_dict(value, new_key, sep))
        else:
            flattened[new_key] = value
    return flattened


class SessionBuilder:
    """Build and configure a ``pydelica.Session`` from structured settings."""

    _model_configurations: dict[str, Callable] = {
        "time_range": lambda session, config: session.set_time_range(**config),
        "tolerance": lambda session, config: session.set_tolerance(**config),
        "variable_filter": lambda session, config: session.set_variable_filter(**config),
    }

    _sim_configurations: dict[str, Callable] = {
        "solver": lambda session, solver: session.set_solver(solver),
        "output_format": lambda session, format: session.set_output_format(format),
    }

    @property
    def session(self) -> pydelica.Session:
        """Return the configured simulation session."""
        return self._session

    def __init__(
        self,
        source_file: pydantic.FilePath,
        log_level: int | str = logging.INFO,
        build_options: dict | None = None,
        libraries: list[dict[str, str]] | None = None,
    ):
        """Create a session and build the model from the given source file.

        Args:
            source_file: Path to the Modelica model source file.
            log_level: Logging level forwarded to ``pydelica.Session``.
            build_options: Optional keyword arguments for model building.
            libraries: List of library configurations for model building.
        """
        build_options = dict(build_options or {})
        build_options.setdefault("omc_build_flags", {"-q": None})

        _install_omc_logging_filter()
        _install_pydelica_runtime_patch()

        self._session = pydelica.Session(log_level)
        if libraries:
            self._session.use_libraries(libraries)
        self._session.build_model(source_file, **build_options)

    @staticmethod
    def _convert_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Convert parameter values to a format suitable for the session.

        Conversion rules:
        - Scalar values are passed through unchanged.
        - List or tuple values are converted to indexed parameter names (1-based).

        Args:
            parameters: Mapping of parameter names to values.

        Returns:
            A dictionary of converted parameter values.
        """
        parameters_converted: Dict[str, Any] = {}
        for name, value in parameters.items():
            if isinstance(value, (list, tuple)):
                for idx, element in enumerate(value):
                    parameters_converted[f"{name}[{idx + 1}]"] = element
            else:
                parameters_converted[name] = value
        return parameters_converted

    def configure_parameters(self, parameters: Dict[str, Any]):
        """Apply parameter values to the underlying session.

        Args:
            parameters: Mapping of parameter names to values.
        """
        for name, value in self._convert_parameters(parameters).items():
            self._session.set_parameter(str(name), value)

    def configure_models(self, configurations: Dict[str, Dict[str, Any]]):
        """Apply per-model configuration options to the session.

        Args:
            configurations: Mapping of model names to configuration dictionaries.

        Raises:
            ValueError: If an unknown model configuration option is provided.
        """
        for model, configuration in configurations.items():
            for name, value in configuration.items():
                if name in self._model_configurations:
                    self._model_configurations[name](self._session, value)
                else:
                    raise ValueError(f"Unknown simulation configuration: {name}")

    def configure_simulation(self, configuration: Dict[str, Any]):
        """Apply global simulation configuration options.

        Args:
            configuration: Mapping of simulation option names to values.

        Raises:
            ValueError: If an unknown simulation option is provided.
        """
        for name, value in configuration.items():
            if name in self._sim_configurations:
                self._sim_configurations[name](self._session, value)
            else:
                raise ValueError(f"Unknown simulation configuration: {name}")


class SessionDirector:
    """Coordinate session construction from dataclass-based configuration."""

    def __init__(
        self,
        model: pydantic.FilePath,
        parameters: session_config.DataclassType,
        model_configurations: Dict[str, session_config.Model],
        sim_configurations: session_config.Simulation,
        build_options: dict | None = None,
        libraries: list[dict[str, str]] | None = None,
        **kwargs,
    ):
        """Prepare normalized configuration for session creation.

        Args:
            model: Path to the Modelica model source file.
            parameters: Dataclass containing simulation parameter values.
            model_configurations: Per-model configuration dataclasses.
            sim_configurations: Simulation-wide configuration dataclass.
            **kwargs: Extra configuration values retained for future use.
        """
        self._parameters = flatten_nested_dict(asdict(parameters))
        self._model_configurations = {name: asdict(config) for name, config in model_configurations.items()}
        self._sim_configurations = asdict(sim_configurations)
        self._configuration = kwargs
        self._session_builder = SessionBuilder(model, build_options=build_options, libraries=libraries)

    def make_session(self) -> pydelica.Session:
        """Build, configure, and return a ready-to-simulate session."""
        self._session_builder.configure_parameters(self._parameters)
        self._session_builder.configure_models(self._model_configurations)
        self._session_builder.configure_simulation(self._sim_configurations)
        return self._session_builder.session
