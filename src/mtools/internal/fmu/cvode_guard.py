"""Skip the CVODE steps that CVODE itself would refuse, in FMPy's Model Exchange loop.

FMPy 0.3.32 steps CVODE to the next output point or the next time event, whichever comes first.
For an OpenModelica-exported FMU with ``sample()`` events, the two can differ by less than a float
step, and CVODE then fails with "tout too close" (error -27) (FMPy #882,
https://github.com/CATIA-Systems/FMPy/issues/882).

The guard wraps ``fmpy.sundials.CVodeSolver.step`` so that such a step returns no state event and
``tNext`` without calling CVODE; the loop then handles the time event as usual. Every other step is
passed through unchanged. Drop this guard once FMPy fixes #882.
"""

from __future__ import annotations

import functools
import sys
from typing import Any

import numpy as np

_INSTALLED_MARK = "_mtools_cvode_guard"


def should_skip(t: float, t_next: float) -> bool:
    """Whether stepping from ``t`` to ``t_next`` is closer than CVODE accepts."""
    return abs(t_next - t) < 2 * sys.float_info.epsilon * max(abs(t), abs(t_next))


def install() -> None:
    """Wrap ``fmpy.sundials.CVodeSolver.step`` to skip refused steps; idempotent."""
    from fmpy.sundials import CVodeSolver

    original = CVodeSolver.step
    if getattr(original, _INSTALLED_MARK, False):
        return

    @functools.wraps(original)
    def step(self: Any, t: float, tNext: float) -> Any:
        if should_skip(t, tNext):
            return False, np.zeros(shape=(self.nz,), dtype=np.int32), tNext
        return original(self, t, tNext)

    setattr(step, _INSTALLED_MARK, True)
    CVodeSolver.step = step
