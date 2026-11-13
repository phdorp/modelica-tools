"""The run request: what the parent hands the child process, as JSON in the run directory."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FILE_NAME = "request.json"


@dataclass(frozen=True)
class RunRequest:
    """One FMPy run, with every value explicit.

    Attributes:
        fmu_path: The ``.fmu`` file to extract.
        unzip_dir: Where the child extracts it, inside the run directory.
        fmi_type: ``"ModelExchange"`` or ``"CoSimulation"``.
        start_time: Simulation start time.
        stop_time: Simulation stop time.
        interval: Output interval, also the step size.
        tolerance: Relative tolerance.
        solver: FMPy's solver name; ``None`` for Co-Simulation.
        start_values: Start values by FMU name.
        output: FMU names recorded in the result.
        cvode_guard: Whether the child guards CVODE's steps.
        save_every: Wall-time seconds between saves of the rows recorded so far.
    """

    fmu_path: str
    unzip_dir: str
    fmi_type: str
    start_time: float
    stop_time: float
    interval: float
    tolerance: float
    solver: str | None
    start_values: dict[str, Any]
    output: list[str]
    cvode_guard: bool
    save_every: float = 1.0

    def write(self, directory: Path) -> None:
        """Write the request to ``directory``."""
        (directory / FILE_NAME).write_text(json.dumps(dataclasses.asdict(self)), encoding="utf-8")

    @classmethod
    def read(cls, directory: Path) -> RunRequest:
        """Read the request written to ``directory``."""
        return cls(**json.loads((directory / FILE_NAME).read_text(encoding="utf-8")))
