"""The child switches on FMI logging for the status categories an FMU declares, and no others."""

import inspect

import pytest

from mtools.internal.fmu import status_logging
from mtools.internal.fmu.status_logging import status_categories
from tests.fmu.helpers import reference_fmu, simulate_given

pytestmark = pytest.mark.fmu


def test_only_declared_status_categories_are_selected():
    declared = ["logAll", "logStatusFatal", "logFmi2Call", "logStatusWarning", "logEvents", "logStatusError"]
    assert status_categories(declared) == ["logStatusFatal", "logStatusWarning", "logStatusError"]


def test_no_status_category_leaves_logging_unchanged():
    assert status_categories(["logAll", "logEvents"]) == []
    assert status_categories([]) == []


def test_install_sets_debug_logging_after_instantiate_and_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    from fmpy.fmi2 import _FMU2

    monkeypatch.setattr(_FMU2, "instantiate", lambda self, *a, **k: calls.append("instantiate"))
    monkeypatch.setattr(status_logging, "_selected", [])
    calls: list = []
    monkeypatch.setattr(_FMU2, "setDebugLogging", lambda self, on, cats: calls.append((on, list(cats))), raising=False)
    status_logging.install(["logAll", "logStatusFatal"])
    status_logging.install(["logStatusFatal", "logStatusError"])
    _FMU2.instantiate(_FMU2.__new__(_FMU2))
    assert calls == ["instantiate", (True, ["logStatusFatal", "logStatusError"])]


def test_fmpy_instantiate_still_has_the_wrapped_signature():
    from fmpy.fmi2 import _FMU2

    assert list(inspect.signature(_FMU2.instantiate).parameters) == ["self", "visible", "callbacks", "loggingOn"]


@pytest.mark.parametrize("fmi_version, name", [("2.0", "Dahlquist"), ("3.0", "Dahlquist"), ("2.0", "BouncingBall")])
def test_reference_fmus_still_run(fmi_version: str, name: str):
    result = simulate_given(reference_fmu(name, fmi_version))
    assert len(next(iter(result.values()))) > 1
