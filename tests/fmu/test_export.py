"""A Modelica model exported as an FMU runs through ``sim_tools.simulate``, cached like a native build."""

import logging
import sys

import fmpy
import numpy as np
import pytest

from tests.fmu.helpers import build_messages, simulate_exported


def test_exported_fmu_runs_and_matches_the_analytic_solution(exported_fmu):
    result = simulate_exported("FmuTests.Decay")["FmuTests.Decay"]

    kept = {"x", "der(x)", "count", "positive"}  # k and x0 are parameters
    description = fmpy.read_model_description(exported_fmu("FmuTests.Decay"))
    order = [variable.name for variable in description.modelVariables if variable.name in kept]
    assert list(result.columns) == ["time", *order]
    assert result[["x", "count", "positive"]].dtypes.tolist() == ["float64", "int64", "bool"]
    np.testing.assert_allclose(result["x"], np.exp(-result["time"]), rtol=1e-4)


def test_missing_fmpy_raises_before_export(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setitem(sys.modules, "fmpy", None)

    with pytest.raises(ImportError, match=r"^FMU runs need FMPy: install modelica-tools\[fmu\]$"):
        simulate_exported("FmuTests.Sampled")

    assert build_messages(caplog) == []
