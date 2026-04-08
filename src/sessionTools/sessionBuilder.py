from __future__ import annotations

import logging
import functools

import pydantic
import pydelica
from omegaconf import DictConfig


def flatten_nested_dict(data: DictConfig, parent_key: str = "", sep: str = ".") -> DictConfig:
    flattened = DictConfig({})
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else str(key)
        if isinstance(value, DictConfig):
            flattened.update(flatten_nested_dict(value, new_key, sep))
        else:
            flattened[new_key] = value
    return flattened


# @functools.cache
class SessionBuilder:

    @property
    def session(self) -> pydelica.Session:
        return self._session

    def __init__(
        self, source_file: pydantic.FilePath, log_level: int | str = logging.INFO, build_options: dict | None = None
    ):
        build_options = build_options or {}

        self._session = pydelica.Session(log_level)
        self._session.build_model(source_file, **build_options)

    def configure_model(self, parameters: DictConfig):
        for name, value in parameters.items():
            self._session.set_parameter(str(name), value)

    def configure_simulation(self):
        raise NotImplementedError("Simulation configuration is not implemented yet.")


class Director:

    def __init__(self, model: pydantic.FilePath, parameters: DictConfig):
        self._parameters = flatten_nested_dict(parameters)
        self._session_builder = SessionBuilder(model)

    def make_session(self) -> pydelica.Session:
        self._session_builder.configure_model(self._parameters)
        return self._session_builder.session
