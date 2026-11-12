"""A Modelica model exported as an FMU runs through ``sim_tools.simulate``, cached like a native build."""

import fmpy
import numpy as np

from tests.fmu.helpers import simulate_exported


def test_exported_fmu_runs_and_matches_the_analytic_solution(exported_fmu):
    result = simulate_exported("FmuTests.Decay")["FmuTests.Decay"]

    kept = {"x", "der(x)", "count", "positive"}  # k and x0 are parameters
    description = fmpy.read_model_description(exported_fmu("FmuTests.Decay"))
    order = [variable.name for variable in description.modelVariables if variable.name in kept]
    assert list(result.columns) == ["time", *order]
    assert result[["x", "count", "positive"]].dtypes.tolist() == ["float64", "int64", "bool"]
    np.testing.assert_allclose(result["x"], np.exp(-result["time"]), rtol=1e-4)
