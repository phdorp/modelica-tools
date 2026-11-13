"""Filters for the output of an FMU run's child process (the FMU counterpart of ``omc.run_diagnostics``)."""

from __future__ import annotations

import re

from mtools.internal.fmu.child import EXCEPTION_PREFIX, FMI_PREFIX
from mtools.internal.omc.run_diagnostics import log_entries, notable_entries

#: The first failed FMI call, which FMPy reports in an exception or an "Exception ignored" traceback.
_FAILED_CALL = re.compile(r"\w+ failed with status \d \(\w+\)")

#: CVODE's "too close" failure as the child's output shows it: the FMU's ``##CVODE## -27`` log
#: line, ``CV_TOO_CLOSE`` or the message.
_CVODE_TOO_CLOSE = re.compile(r"##CVODE## -27|CV_TOO_CLOSE|tout too close")

#: The hint that ends the diagnostics of a Co-Simulation run that CVODE stopped with "tout too close".
CS_CVODE_HINT = (
    "Hint: CVODE inside the Co-Simulation FMU stopped because a sample() event lies within one "
    "floating-point step of a communication point. "
    'Use fmu_type="me", export without --fmiFlags=s:cvode (Euler), or choose another interval.'
)


def failure_diagnostics(output: str) -> str:
    """Return the readable diagnostics of a failed FMU run.

    Collects, in order of occurrence, the FMI logger messages, the ``LOG_*`` entries of an
    OMC-exported FMU, the first failed FMI call and the exception that ended the run;
    Python tracebacks are dropped. Falls back to the non-empty raw lines when nothing matched.
    """
    entries: list[str] = []
    unclaimed: list[str] = []  # lines that may be LOG_* entries, until the next FMI line or exception
    call_found = False

    def flush() -> None:
        entries.extend(log_entries("\n".join(unclaimed)))
        unclaimed.clear()

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        failed_call = None if call_found else _FAILED_CALL.search(line)
        if line.startswith(FMI_PREFIX) or line.startswith(EXCEPTION_PREFIX) or failed_call:
            flush()
        if failed_call:
            call_found = True
            entries.append(failed_call.group(0))
        if line.startswith(FMI_PREFIX):
            entries.append(line)
        elif line.startswith(EXCEPTION_PREFIX):
            entries.append(line.removeprefix(EXCEPTION_PREFIX))
        elif not failed_call:
            unclaimed.append(line)
    flush()
    return "\n".join(entries or [line.strip() for line in output.splitlines() if line.strip()])


def warning_entries(output: str) -> list[str]:
    """Return the entries of a successful FMU run that the user should see.

    These are the FMI logger's warning messages, then the ``LOG_ASSERT`` and ``warning`` or
    ``error`` entries of an OMC-exported FMU.
    """
    fmi_warnings = [line.rstrip() for line in output.splitlines() if line.startswith(f"{FMI_PREFIX}warning | ")]
    return fmi_warnings + notable_entries(output)


def cvode_hint(output: str, fmu_type: str) -> str | None:
    """Return :data:`CS_CVODE_HINT` if a Co-Simulation run's ``output`` shows CVODE's "tout too close" failure."""
    if fmu_type == "cs" and _CVODE_TOO_CLOSE.search(output):
        return CS_CVODE_HINT
    return None
