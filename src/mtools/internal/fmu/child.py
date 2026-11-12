"""The child process of an FMU run: ``python -m mtools.internal.fmu.child <run directory>``.

It reads the run request from the run directory, extracts the FMU there, runs it with
FMPy and saves the result as ``result.npy``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

from mtools.internal.fmu import indicator_guard
from mtools.internal.fmu.request import RunRequest

RESULT_FILE_NAME = "result.npy"
#: The prefix of the line the child prints for the exception that ended the run.
EXCEPTION_PREFIX = "mtools-fmu-exception | "
#: FMPy's own default solver, what a Co-Simulation run (``solver=None``) passes.
FMPY_DEFAULT_SOLVER = "CVode"


#: FMI status names by value (FMI 2.0 ``fmi2Status``).
_STATUS_NAMES = ("ok", "warning", "discard", "error", "fatal", "pending")


def _log_fmi_message(_environment: Any, _instance: Any, status: int, category: bytes, message: bytes) -> None:
    """The FMI logger: print each message of status warning or worse as ``FMI | <status> | <category> | <message>``."""
    if status >= 1:
        name = _STATUS_NAMES[status] if status < len(_STATUS_NAMES) else str(status)
        text = message.decode("utf-8", "replace").strip().replace("\n", " ")
        print(f"FMI | {name} | {category.decode('utf-8', 'replace')} | {text}", flush=True)


def main(argv: list[str]) -> int:
    """Run the request in the run directory ``argv[0]``; return the exit status.

    A Python failure prints ``mtools-fmu-exception | <type>: <message>`` as the last line
    and returns 1, without a traceback.
    """
    try:
        return _run(Path(argv[0]))
    except Exception as error:
        print(f"{EXCEPTION_PREFIX}{type(error).__name__}: {error}", flush=True)
        return 1


def _run(directory: Path) -> int:
    import fmpy

    request = RunRequest.read(directory)
    fmpy.extract(request.fmu_path, unzipdir=request.unzip_dir)
    if request.fmi_type == "ModelExchange":
        indicator_guard.install()
    result = fmpy.simulate_fmu(
        request.unzip_dir,
        fmi_type=request.fmi_type,
        start_time=request.start_time,
        stop_time=request.stop_time,
        step_size=request.interval,
        output_interval=request.interval,
        relative_tolerance=request.tolerance,
        solver=request.solver or FMPY_DEFAULT_SOLVER,  # Co-Simulation ignores it
        start_values=request.start_values,
        output=request.output,
        record_events=True,
        validate=False,
        logger=_log_fmi_message,
    )
    np.save(directory / RESULT_FILE_NAME, np.asarray(result), allow_pickle=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
