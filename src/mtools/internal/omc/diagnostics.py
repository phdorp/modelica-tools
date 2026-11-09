"""Filters that turn raw OMC and compiler output into readable build diagnostics.

All functions are pure. The translation filter works on OMC's ``getErrorString()`` text,
the compile filter on the C compiler and ``make`` log that OMC embeds in its
``Error building simulator`` message.
"""

from __future__ import annotations

import re

#: The first line of an OMC message: optional ``[file:l:c-l:c:writable] `` location, then its kind.
_MESSAGE_START = re.compile(r"^(?P<location>\[[^\]]*\]\s*)?(?P<kind>Error|Warning|Notification):")

#: OMC lines that explain nothing.
_BOILERPLATE_PREFIXES = ("Failed to parse file",)
_BOILERPLATE_LINES = ("Execution failed!",)

#: OMC's follow-on error when a package fails to load because of an earlier error.
_FAILED_TO_LOAD_PACKAGE = "Error: Failed to load package"

_Message = tuple[str, list[str]]


def _messages(text: str) -> list[_Message]:
    """Split OMC output into ``(kind, lines)`` messages, dropping blank and boilerplate lines.

    A message is its first line plus the continuation lines that follow. ``kind`` is
    ``"Notification"`` only for an unlocated notification (a located one such as
    ``From here:`` explains the error before it), ``"Error"``, ``"Warning"`` or ``""``.
    """
    messages: list[_Message] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.startswith(_BOILERPLATE_PREFIXES) or line in _BOILERPLATE_LINES:
            continue
        start = _MESSAGE_START.match(line)
        if start:
            kind = start["kind"]
            if kind == "Notification" and start["location"]:
                kind = ""
            messages.append((kind, [line]))
        elif messages:
            messages[-1][1].append(line)
        else:
            messages.append(("", [line]))
    return messages


def filter_translation(text: str) -> str:
    """Keep OMC's errors and warnings with their continuations, in order.

    Unlocated ``Notification:`` messages and OMC boilerplate are dropped, and so are
    ``Failed to load package`` follow-ons when another error explains them.

    Args:
        text: OMC's error string (or raw output) of the failed stages.

    Returns:
        The kept lines joined by newlines, empty when nothing is left.
    """
    kept = [message for message in _messages(text) if message[0] != "Notification"]
    follow_on = [message for message in kept if _FAILED_TO_LOAD_PACKAGE in message[1][0]]
    errors = [message for message in kept if message[0] == "Error"]
    if follow_on and len(follow_on) < len(errors):
        kept = [message for message in kept if message not in follow_on]
    return "\n".join(line for _, lines in kept for line in lines)


def translation_warnings(text: str) -> str:
    """Return the ``Warning:`` messages of ``text`` (with continuations), joined by newlines."""
    return "\n".join(line for kind, lines in _messages(text) if kind == "Warning" for line in lines)


def notifications(text: str) -> str:
    """Return the unlocated ``Notification:`` messages of ``text``, joined by newlines."""
    return "\n".join(line for kind, lines in _messages(text) if kind == "Notification" for line in lines)


#: A compiler diagnostic: ``file:line:col: [fatal ]error|warning|note:``.
_COMPILER_DIAGNOSTIC = re.compile(r"^\S+?:\d+:\d+: (?P<kind>(?:fatal )?error|warning|note):")
_LINKER_LINE = re.compile(r"undefined reference|^(\S*/)?(ld|collect2)\b|\b(ld|collect2): ")
#: A source line as printed by the compiler (``  7 | code``) or its caret line (``      |   ^~~``).
_SOURCE_OR_CARET = re.compile(r"^\s*\d*\s*\|")


def _compile_messages(log: str) -> list[_Message]:
    """Split a compile log into ``(kind, lines)`` compiler diagnostics and linker lines."""
    messages: list[_Message] = []
    current: list[str] | None = None
    for raw in log.splitlines():
        line = raw.rstrip()
        diagnostic = _COMPILER_DIAGNOSTIC.match(line)
        if diagnostic:
            current = [line]
            messages.append((diagnostic["kind"], current))
        elif _LINKER_LINE.search(line):
            current = None
            messages.append(("link", [line]))
        elif current is not None and _SOURCE_OR_CARET.match(line):
            current.append(line)
        else:
            current = None
    return messages


def filter_compile(log: str) -> str:
    """Trim a C compile and link log to its diagnostics.

    Keeps ``file:line:col: [fatal ]error|warning|note:`` lines with their source and caret
    lines, ``undefined reference`` lines and ``ld``/``collect2`` lines. Compile command
    lines and ``make`` chatter are dropped. If nothing matches, the whole log is returned.
    """
    kept = [line for _, lines in _compile_messages(log) for line in lines]
    return "\n".join(kept) if kept else log.strip()


def compiler_warnings(log: str) -> str:
    """Return the compiler ``warning:`` diagnostics (with source lines) of ``log``."""
    return "\n".join(line for kind, lines in _compile_messages(log) if kind == "warning" for line in lines)
