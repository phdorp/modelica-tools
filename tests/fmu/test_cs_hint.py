"""A Co-Simulation CVODE "tout too close" failure ends with a hint at the cause and the fixes."""

from collections.abc import Callable
from pathlib import Path

import pytest

from mtools.errors import SimulationError
from mtools.internal.fmu.diagnostics import CS_CVODE_HINT, cvode_hint
from tests.fmu.helpers import simulate_exported, simulate_given

pytestmark = pytest.mark.fmu

# The research note (S1: der(x) = -x with sample(0.1, 0.1), CS with --fmiFlags=s:cvode) saw this fail at 30/30 step sizes.
# A model without a continuous state never starts CVODE, so SampledDecay carries one; 0.01 is pinned.
CVODE_FLAGS: dict[str, str | None] = {"--fmiFlags": "s:cvode"}


def test_cs_cvode_failure_ends_with_the_hint():
    with pytest.raises(SimulationError) as error:
        simulate_exported("FmuTests.SampledDecay", fmu_type="cs", interval=0.01, omc_flags=CVODE_FLAGS)
    assert error.value.diagnostics.splitlines()[-1] == CS_CVODE_HINT


def test_hint_applies_to_given_fmus(exported_fmu: Callable[..., Path]):
    path = exported_fmu("FmuTests.SampledDecay", "cs", omc_flags=CVODE_FLAGS)
    with pytest.raises(SimulationError) as error:
        simulate_given(path, fmu_type="cs", interval=0.01)
    assert error.value.diagnostics.splitlines()[-1] == CS_CVODE_HINT


def test_hint_stays_above_the_run_directory(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MTOOLS_KEEP_RUNS", "1")
    with pytest.raises(SimulationError) as error:
        simulate_exported("FmuTests.SampledDecay", fmu_type="cs", interval=0.01, omc_flags=CVODE_FLAGS)
    lines = error.value.diagnostics.splitlines()
    assert lines[-2] == CS_CVODE_HINT
    assert lines[-1].startswith("Run directory:")


def test_no_hint_on_model_exchange():
    assert cvode_hint("CV_TOO_CLOSE -27 tout too close", "me") is None


def test_no_hint_without_a_cvode_failure():
    assert cvode_hint("FMICallException: fmi2DoStep failed with status 3 (error)", "cs") is None


def test_no_hint_for_an_unrelated_minus_27():
    assert cvode_hint("FMI | warning | logStatusWarning | x = -27.5", "cs") is None


def test_hint_matches_the_fmu_log_line():
    line = "FMI | fatal | logStatusFatal | fmi2DoStep: ##CVODE## -27 error occurred at time = 0.7."
    assert cvode_hint(line, "cs") == CS_CVODE_HINT


@pytest.mark.parametrize("output", ["CV_TOO_CLOSE", "tout too close to t0 to start integration."])
def test_hint_matches_either_marker(output: str):
    assert cvode_hint(output, "cs") == CS_CVODE_HINT
