"""The CVODE guard skips only the steps CVODE would refuse, and only for Model Exchange runs with CVODE."""

import inspect
import sys
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

from mtools.internal.fmu import cvode_guard
from mtools.internal.fmu.cvode_guard import should_skip
from tests.fmu.helpers import capture_request, reference_fmu, simulate_exported


def test_sampled_model_at_a_fine_interval_passes_with_cvode():
    result = simulate_exported("FmuTests.Sampled", interval=0.01)["FmuTests.Sampled"]
    assert result["count"].iloc[-1] == 10


def test_guard_only_for_me_cvode(monkeypatch):
    assert capture_request(monkeypatch, reference_fmu("Dahlquist")).cvode_guard is True
    assert capture_request(monkeypatch, reference_fmu("Dahlquist"), solver="euler").cvode_guard is False
    assert capture_request(monkeypatch, reference_fmu("Dahlquist"), fmu_type="cs").cvode_guard is False


def test_should_skip_threshold():
    eps = sys.float_info.epsilon
    assert should_skip(1.0, 1.0 + eps) and not should_skip(1.0, 1.0 + 4 * eps)


def test_fmpy_cvode_step_still_has_the_wrapped_signature():
    from fmpy.sundials import CVodeSolver

    assert list(inspect.signature(CVodeSolver.step).parameters) == ["self", "t", "tNext"]


@pytest.fixture
def guarded_step(monkeypatch: pytest.MonkeyPatch) -> tuple[Callable[..., Any], list[tuple[float, float]], object]:
    """Install the guard over a stub ``CVodeSolver.step``; return the guarded step, the
    stub's calls and what the stub returns."""
    import fmpy.sundials

    calls: list[tuple[float, float]] = []
    sentinel = object()

    def stub(self: Any, t: float, tNext: float) -> object:
        calls.append((t, tNext))
        return sentinel

    monkeypatch.setattr(fmpy.sundials.CVodeSolver, "step", stub)
    cvode_guard.install()
    return fmpy.sundials.CVodeSolver.step, calls, sentinel


SOLVER = type("Solver", (), {"nz": 2})()


def test_install_skips_a_refused_step(guarded_step):
    step, calls, _ = guarded_step
    event, roots, time = step(SOLVER, 1.0, 1.0 + sys.float_info.epsilon)

    assert (event, time, calls) == (False, 1.0 + sys.float_info.epsilon, [])
    np.testing.assert_array_equal(roots, np.zeros(2, dtype=np.int32))
    assert roots.dtype == np.int32  # what FMPy's own step returns


def test_install_forwards_other_steps(guarded_step):
    step, calls, sentinel = guarded_step
    assert step(SOLVER, 1.0, 2.0) is sentinel
    assert calls == [(1.0, 2.0)]


def test_install_is_idempotent(guarded_step):
    import fmpy.sundials

    step, _, _ = guarded_step
    cvode_guard.install()
    assert fmpy.sundials.CVodeSolver.step is step
