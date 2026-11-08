"""Filters for the output of a C simulation binary (the run counterpart of the build filters)."""

from __future__ import annotations

import re

#: A log line of the C runtime: ``<stream> | <level> | <message>`` with padded columns.
_LOG_LINE = re.compile(r"^(LOG_\w+)\s*\|\s*(\w+)\s*\|\s?(.*)$")

#: A continuation of the previous log line: ``|  | |  | <message>``.
_CONTINUATION = re.compile(r"^\|\s*\|\s*\|\s*\|\s?(.*)$")

#: Log streams that report progress, not problems.
_QUIET_STREAMS = ("LOG_SUCCESS",)


def log_entries(output: str) -> list[str]:
    """Extract the relevant entries from a C runtime log.

    Returns:
        One string per ``LOG_*`` line except ``LOG_SUCCESS``, as
        ``<stream> | <level> | <message>`` with the line's continuations appended as
        indented lines. Other lines, such as the DASKR solver banner, are dropped.
    """
    entries: list[list[str]] = []
    keep = False
    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        log_line = _LOG_LINE.match(line)
        if log_line:
            stream, level, message = log_line.groups()
            keep = stream not in _QUIET_STREAMS
            if keep:
                entries.append([f"{stream} | {level} | {message.strip()}"])
            continue
        continuation = _CONTINUATION.match(line)
        if continuation:
            if keep and continuation.group(1).strip():
                entries[-1].append(f"    {continuation.group(1).strip()}")
            continue
        keep = False
    return ["\n".join(entry) for entry in entries]


def notable_entries(output: str) -> list[str]:
    """Return the entries of a successful run that the user should see.

    These are ``LOG_ASSERT`` entries and ``warning`` or ``error`` entries of any stream.
    """
    notable = []
    for entry in log_entries(output):
        stream, level, _ = entry.split(" | ", 2)
        if stream == "LOG_ASSERT" or level in ("warning", "error"):
            notable.append(entry)
    return notable


def failure_diagnostics(output: str, signal_name: str | None = None) -> str:
    """Return the readable diagnostics of a failed run.

    Falls back to the non-empty raw lines when the output has no log entries, and names
    the signal when the binary was killed by one.
    """
    lines = log_entries(output) or [line.strip() for line in output.splitlines() if line.strip()]
    if signal_name:
        lines.append(f"Terminated by signal {signal_name}")
    return "\n".join(lines)
