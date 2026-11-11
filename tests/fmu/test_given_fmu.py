"""A given FMU runs through ``sim_tools.simulate`` like a native build."""

import numpy as np
import pytest

from tests.fmu.helpers import capture_request, reference_fmu, simulate_given


def test_dahlquist_runs_with_its_default_experiment():
    results = simulate_given(reference_fmu("Dahlquist"))

    result = results["Dahlquist"]  # model_name from modelName
    assert result["time"].iloc[0] == 0.0 and result["time"].iloc[-1] == pytest.approx(10.0)
    assert len(result) == 101  # stepSize 0.1, no events
    # CVODE's absolute tolerance is nominal (1) x tolerance (1e-6), so near zero the
    # relative error exceeds 1e-4: atol keeps the comparison to what the solver promises.
    np.testing.assert_allclose(result["x"], np.exp(-result["time"]), rtol=1e-4, atol=1e-6)


def test_result_columns_follow_the_model_description():
    result = simulate_given(reference_fmu("BouncingBall"))["BouncingBall"]

    assert list(result.columns) == ["time", "h", "der(h)", "v", "der(v)"]  # g, e, v_min dropped
    assert all(result.dtypes == "float64")


def test_unset_tolerance_takes_omc_default(monkeypatch):  # Dahlquist has no tolerance attribute
    captured = capture_request(monkeypatch, reference_fmu("Dahlquist"))

    assert captured.tolerance == 1e-6 and captured.solver == "CVode" and captured.interval == 0.1


def test_model_name_overrides_the_result_key():
    assert list(simulate_given(reference_fmu("Dahlquist"), model_name="ref")) == ["ref"]
