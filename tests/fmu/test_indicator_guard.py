"""The event-indicator guard zeroes the buffer and wraps FMPy's ``FMU2Model.getEventIndicators`` once."""

import ctypes
import inspect

import fmpy.fmi2
import pytest

from mtools.internal.fmu import indicator_guard

SENTINEL = object()


def test_get_event_indicators_signature_is_unchanged():
    method = getattr(fmpy.fmi2.FMU2Model, "getEventIndicators")
    assert list(inspect.signature(method).parameters) == ["self", "z", "nz"]


@pytest.fixture
def seen(monkeypatch):
    """Replace the method with a recording stub; monkeypatch restores the real one at teardown."""
    calls: list[tuple[object, list[float], int]] = []

    def stub(self, z, nz):
        calls.append((z, list(z), nz))
        return SENTINEL

    monkeypatch.setattr(fmpy.fmi2.FMU2Model, "getEventIndicators", stub)
    return calls


def test_the_guard_zeroes_the_buffer_and_forwards_the_call(seen):
    indicator_guard.install()
    z = (ctypes.c_double * 3)(1.5, -2.5, 3.5)

    returned = fmpy.fmi2.FMU2Model.getEventIndicators(object(), z, 3)  # type: ignore[arg-type]

    assert returned is SENTINEL
    assert seen == [(z, [0.0, 0.0, 0.0], 3)]


def test_install_is_idempotent(seen):
    indicator_guard.install()
    first = fmpy.fmi2.FMU2Model.getEventIndicators
    indicator_guard.install()
    assert fmpy.fmi2.FMU2Model.getEventIndicators is first
