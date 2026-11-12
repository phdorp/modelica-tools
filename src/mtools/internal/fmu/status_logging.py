"""Turn on an FMI 2.0 FMU's logging for its status categories only.

OpenModelica-exported FMUs log nothing, not even a fatal error such as CVODE's ``-27``, until
debug logging is on, and then they log every call. FMPy's ``debug_logging`` switches on all
categories, so this wraps ``fmpy.fmi2._FMU2.instantiate`` to call ``setDebugLogging`` with just
the ``logStatus*`` categories the FMU declares. An FMU declaring none is left as it is.

Only FMI 2.0 is wrapped; the FMI 3.0 instantiate calls are left unchanged.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable
from typing import Any

STATUS_CATEGORIES = ("logStatusWarning", "logStatusDiscard", "logStatusError", "logStatusFatal", "logStatusPending")

_INSTALLED_MARK = "_mtools_status_logging"

#: The categories to switch on, read by the wrapper at instantiation; set by :func:`install`.
_selected: list[str] = []


def status_categories(declared: Iterable[str]) -> list[str]:
    """Return the status categories among the ``declared`` log category names, in declared order."""
    return [name for name in declared if name in STATUS_CATEGORIES]


def install(declared: Iterable[str]) -> None:
    """Switch on the status categories among ``declared`` after FMPy instantiates an FMI 2.0 FMU.

    Idempotent: the wrapper is installed once and a later call only changes the categories.
    """
    from fmpy.fmi2 import _FMU2

    _selected[:] = status_categories(declared)
    original = _FMU2.instantiate
    if getattr(original, _INSTALLED_MARK, False):
        return

    @functools.wraps(original)
    def instantiate(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        if _selected:
            self.setDebugLogging(True, _selected)
        return result

    setattr(instantiate, _INSTALLED_MARK, True)
    _FMU2.instantiate = instantiate
