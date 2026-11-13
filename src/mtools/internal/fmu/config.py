"""Backend-internal config of a given FMU, mirroring ``session_config.FmuFile``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FmuFileConfig:
    """A validated given FMU.

    Attributes:
        fmu_path: The ``.fmu`` file.
        model_name: Name the results are keyed by; ``None`` takes the FMU's ``modelName``.
        fmu_type: ``"me"``, ``"cs"`` or ``None``.
        name_map: Experiment name to FMU variable name.
    """

    fmu_path: Path
    model_name: str | None
    fmu_type: str | None
    name_map: Mapping[str, str]
