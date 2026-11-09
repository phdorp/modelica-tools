"""Run a command in its own process group with an optional time limit.

Target-agnostic: the caller supplies the command line, working directory and limit and
gets the exit status and the combined output back.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProcessResult:
    """How a process ended.

    Attributes:
        returncode: The exit status, negative for the signal that ended the process.
        output: Standard output and standard error, interleaved.
        timed_out: Whether the time limit expired and the process group was killed.
    """

    returncode: int
    output: str
    timed_out: bool

    @property
    def signal(self) -> signal.Signals | None:
        """The signal that ended the process, if any."""
        return signal.Signals(-self.returncode) if self.returncode < 0 else None


def execute(command: Sequence[str], cwd: Path, timeout: float | None = None) -> ProcessResult:
    """Run ``command`` in ``cwd`` in a new process group.

    The group is killed when ``timeout`` seconds pass, and on any exception raised while
    waiting (``KeyboardInterrupt`` included) before it propagates.
    """
    logger.debug("Running %s in %s", list(command), cwd)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    timed_out = False
    try:
        try:
            output, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(process)
            output, _ = process.communicate()
    except BaseException:
        _kill_group(process)
        process.wait()
        raise
    logger.debug("Run exited with %d (timed out: %s).\n%s", process.returncode, timed_out, output)
    return ProcessResult(process.returncode, output, timed_out)


def _kill_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
