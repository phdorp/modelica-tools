"""FMPy's ``FMU2Model.getEventIndicators`` is still what the event-indicator guard wraps."""

import inspect

import fmpy.fmi2


def test_get_event_indicators_signature_is_unchanged():
    method = getattr(fmpy.fmi2.FMU2Model, "getEventIndicators")
    assert list(inspect.signature(method).parameters) == ["self", "z", "nz"]


def test_install_is_idempotent():
    from mtools.internal.fmu import indicator_guard

    indicator_guard.install()
    first = fmpy.fmi2.FMU2Model.getEventIndicators
    indicator_guard.install()
    assert fmpy.fmi2.FMU2Model.getEventIndicators is first
