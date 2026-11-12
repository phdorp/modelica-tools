"""Zero the event-indicator buffer before FMPy asks an FMU for its event indicators.

OpenModelica 1.27.2's Cpp-target FMU export declares more event indicators than it writes:
``fmi2GetEventIndicators`` never sets the slot reserved for ``sample()`` and may negate it.
FMPy passes CVODE's root buffers, which start as uninitialised heap memory, so in some
processes CVODE sees a fake root on almost every step and the same FMU gives a different
output grid and accuracy from run to run.

FMI 2.0 requires ``fmi2GetEventIndicators`` to set all values, so zeroing the buffer first
changes nothing for a conforming FMU. Drop this guard once OpenModelica fixes the export.

Only FMI 2.0 is wrapped: OpenModelica can't export FMI 3.0 FMUs.
"""

from __future__ import annotations

import ctypes
import functools
from typing import Any

_INSTALLED_MARK = "_mtools_indicator_guard"


def install() -> None:
    """Wrap ``fmpy.fmi2.FMU2Model.getEventIndicators`` to zero its buffer first; idempotent."""
    from fmpy.fmi2 import FMU2Model

    original = FMU2Model.getEventIndicators
    if getattr(original, _INSTALLED_MARK, False):
        return

    @functools.wraps(original)
    def get_event_indicators(self: Any, z: Any, nz: int) -> Any:
        ctypes.memset(z, 0, nz * ctypes.sizeof(ctypes.c_double))
        return original(self, z, nz)

    setattr(get_event_indicators, _INSTALLED_MARK, True)
    FMU2Model.getEventIndicators = get_event_indicators
