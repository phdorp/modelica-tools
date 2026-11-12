"""The child process of an FMU run: ``python -m mtools.internal.fmu.child <run directory>``.

It reads the run request from the run directory, extracts the FMU there, runs it with
FMPy and saves the result as ``result.npy``. While it runs, it also saves the rows recorded so far
as ``partial.npy`` about every ``save_every`` seconds, and once more when the run fails in
Python, so the parent can return a partial result.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from mtools.internal.fmu import indicator_guard
from mtools.internal.fmu.request import RunRequest

RESULT_FILE_NAME = "result.npy"
PARTIAL_FILE_NAME = "partial.npy"
#: The prefix of the line the child prints for the exception that ended the run.
EXCEPTION_PREFIX = "mtools-fmu-exception | "
#: FMPy's own default solver, what a Co-Simulation run (``solver=None``) passes.
FMPY_DEFAULT_SOLVER = "CVode"


#: FMI status names by value (FMI 2.0 ``fmi2Status``).
_STATUS_NAMES = ("ok", "warning", "discard", "error", "fatal", "pending")


def _one_line(text: str) -> str:
    """Flatten ``text`` onto one line, so the parent reads one entry per line."""
    return " ".join(text.split())


def exception_line(error: Exception) -> str:
    """Return the line that reports ``error`` as the exception that ended the run."""
    return f"{EXCEPTION_PREFIX}{type(error).__name__}: {_one_line(str(error))}"


def _log_fmi_message(_environment: Any, _instance: Any, status: int, category: bytes, message: bytes) -> None:
    """The FMI logger: print each message of status warning or worse as ``FMI | <status> | <category> | <message>``."""
    if status >= 1:
        name = _STATUS_NAMES[status] if status < len(_STATUS_NAMES) else str(status)
        text = _one_line(message.decode("utf-8", "replace"))
        print(f"FMI | {name} | {category.decode('utf-8', 'replace')} | {text}", flush=True)


class _PartialSaver:
    """FMPy's ``step_finished`` callback: keeps the ``Recorder`` and saves its rows now and then."""

    def __init__(self, directory: Path, save_every: float) -> None:
        self._directory = directory
        self._save_every = save_every
        self._recorder: Any = None
        self._last_save: float | None = None

    def __call__(self, _time: float, recorder: Any) -> bool:
        self._recorder = recorder
        now = time.monotonic()
        if self._last_save is None:
            self._last_save = now  # counting starts at the first call
        elif now - self._last_save >= self._save_every:
            self.save()
        return True

    def save(self) -> None:
        """Save the rows recorded so far, atomically; do nothing before the first step."""
        if self._recorder is None:
            return
        self._last_save = time.monotonic()
        temporary = self._directory / f"{PARTIAL_FILE_NAME}.tmp"
        with open(temporary, "wb") as file:
            np.save(file, np.asarray(self._recorder.result()), allow_pickle=False)
        os.replace(temporary, self._directory / PARTIAL_FILE_NAME)


def main(argv: list[str]) -> int:
    """Run the request in the run directory ``argv[0]``; return the exit status.

    A Python failure prints ``mtools-fmu-exception | <type>: <message>`` as the last line
    and returns 1, without a traceback.
    """
    try:
        return _run(Path(argv[0]))
    except Exception as error:
        print(exception_line(error), flush=True)
        return 1


def _run(directory: Path) -> int:
    import fmpy

    request = RunRequest.read(directory)
    fmpy.extract(request.fmu_path, unzipdir=request.unzip_dir)
    if request.fmi_type == "ModelExchange":
        indicator_guard.install()
    saver = _PartialSaver(directory, request.save_every)
    try:
        result = _simulate(request, saver)
    except Exception:
        saver.save()
        raise
    np.save(directory / RESULT_FILE_NAME, np.asarray(result), allow_pickle=False)
    return 0


def _simulate(request: RunRequest, saver: _PartialSaver) -> Any:
    import fmpy

    return fmpy.simulate_fmu(
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
        step_finished=saver,
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
