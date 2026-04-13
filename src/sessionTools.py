from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Callable, Dict

import pydantic
import pydelica

import sessionConfig


def flatten_nested_dict(data: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    flattened = dict()
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else str(key)
        if isinstance(value, dict):
            flattened.update(flatten_nested_dict(value, new_key, sep))
        else:
            flattened[new_key] = value
    return flattened


class SessionBuilder:

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
        return self._session

    def __init__(
        self, source_file: pydantic.FilePath, log_level: int | str = logging.INFO, build_options: dict | None = None
    ):
        build_options = build_options or {}

        self._session = pydelica.Session(log_level)
        self._session.build_model(source_file, **build_options)

    def configure_parameters(self, parameters: Dict[str, Any]):
        for name, value in parameters.items():
            self._session.set_parameter(str(name), value)

    def configure_models(self, configurations: Dict[str, Dict[str, Any]]):
        for model, configuration in configurations.items():
            for name, value in configuration.items():
                if name in self._model_configurations:
                    self._model_configurations[name](self._session, value)
                else:
                    raise ValueError(f"Unknown simulation configuration: {name}")

    def configure_simulation(self, configuration: Dict[str, Any]):
        for name, value in configuration.items():
            if name in self._sim_configurations:
                self._sim_configurations[name](self._session, value)
            else:
                raise ValueError(f"Unknown simulation configuration: {name}")


class SessionDirector:

    def __init__(
        self,
        model: pydantic.FilePath,
        parameters: sessionConfig.DataclassType,
        model_configurations: Dict[str, sessionConfig.Model],
        sim_configurations: sessionConfig.Simulation,
        **kwargs,
    ):
        self._parameters = flatten_nested_dict(asdict(parameters))
        self._model_configurations = {name: asdict(config) for name, config in model_configurations.items()}
        self._sim_configurations = asdict(sim_configurations)
        self._configuration = kwargs
        self._session_builder = SessionBuilder(model)

    def make_session(self) -> pydelica.Session:
        self._session_builder.configure_parameters(self._parameters)
        self._session_builder.configure_models(self._model_configurations)
        self._session_builder.configure_simulation(self._sim_configurations)
        return self._session_builder.session
