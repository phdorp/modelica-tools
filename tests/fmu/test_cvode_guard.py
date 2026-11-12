"""The CVODE guard skips only the steps CVODE would refuse, and only for Model Exchange runs with CVODE."""

import inspect
import sys

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


def test_install_skips_a_refused_step_forwards_others_and_is_idempotent(monkeypatch):
    import fmpy.sundials

    calls = []
    sentinel = object()

    def stub(self, t, tNext):
        calls.append((t, tNext))
        return sentinel

    monkeypatch.setattr(fmpy.sundials.CVodeSolver, "step", stub)
    cvode_guard.install()
    first = fmpy.sundials.CVodeSolver.step
    cvode_guard.install()
    assert fmpy.sundials.CVodeSolver.step is first

    solver = type("Solver", (), {"nz": 2})()
    event, roots, time = first(solver, 1.0, 1.0 + sys.float_info.epsilon)
    assert (event, list(roots), time) == (False, [0, 0], 1.0 + sys.float_info.epsilon) and calls == []
    assert first(solver, 1.0, 2.0) is sentinel and calls == [(1.0, 2.0)]
