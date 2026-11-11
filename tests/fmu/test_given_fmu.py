"""A given FMU runs through ``sim_tools.simulate`` like a native build."""

import sys

import numpy as np
import pytest

from mtools.errors import ConfigError
from tests.fmu.helpers import (capture_request, reference_fmu, simulate_given,
                               write, zip_without)


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


@pytest.mark.parametrize(
    "make, phrase",
    [
        pytest.param(lambda d: d / "missing.fmu", "no such file", id="missing"),
        pytest.param(lambda d: write(d / "x.fmu", b"not a zip"), "not an FMU archive", id="not-a-zip"),
        pytest.param(
            lambda d: zip_without(reference_fmu("Dahlquist"), d, "modelDescription.xml"),
            "modelDescription.xml",
            id="no-model-description",
        ),
        pytest.param(
            lambda d: zip_without(reference_fmu("Dahlquist"), d, "binaries/linux64/"), "linux64", id="no-binary"
        ),
    ],
)
def test_unusable_fmu_file_is_a_config_error(tmp_path, make, phrase):
    with pytest.raises(ConfigError, match="build.fmu_path") as error:
        simulate_given(make(tmp_path))

    assert phrase in error.value.diagnostics


def test_missing_fmpy_raises_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "fmpy", None)

    with pytest.raises(ImportError, match=r"install modelica-tools\[fmu\]"):
        simulate_given(reference_fmu("Dahlquist"))
