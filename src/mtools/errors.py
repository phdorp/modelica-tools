"""Exceptions mtools raises for invalid configs, failed builds and failed runs.

Every exception's message is a header line naming the model and the stage, followed by
the filtered diagnostics. ``repr`` equals ``str`` so that tracebacks and logs show the
readable message once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class MtoolsError(Exception):
    """Base class of all mtools errors.

    Attributes:
        model_name: Name of the Modelica model the error belongs to.
        diagnostics: The filtered diagnostics shown below the header.
    """

    def __init__(self, header: str, *, model_name: str, diagnostics: str) -> None:
        message = f"{header}\n{diagnostics}" if diagnostics else header
        super().__init__(message)
        self.model_name = model_name
        self.diagnostics = diagnostics

    def __repr__(self) -> str:
        return str(self)


class ConfigError(MtoolsError, ValueError):
    """A config value is invalid; the diagnostics name its config path."""


class BuildError(MtoolsError):
    """Building the model failed."""


class TranslationError(BuildError):
    """OMC failed to load or translate the model."""


class CompileError(BuildError):
    """Compiling or linking the generated code failed."""


class SimulationError(MtoolsError):
    """A run failed.

    Attributes:
        partial_result: The result written before the failure, or ``None`` if nothing
            could be read.
    """

    def __init__(
        self,
        header: str,
        *,
        model_name: str,
        diagnostics: str,
        partial_result: pd.DataFrame | None = None,
    ) -> None:
        super().__init__(header, model_name=model_name, diagnostics=diagnostics)
        self.partial_result = partial_result


class SimulationTimeout(SimulationError):
    """A run exceeded its time limit and was killed."""
