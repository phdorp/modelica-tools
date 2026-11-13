import pandas as pd
import pytest

from mtools.errors import ConfigError
from tests.fmu.helpers import (capture_request, edited_fmu, reference_fmu,
                               remove_element, simulate_given)


def test_unset_type_runs_model_exchange_when_offered(monkeypatch):
    assert capture_request(monkeypatch, reference_fmu("Dahlquist")).fmi_type == "ModelExchange"


def test_cs_only_fmu_runs_co_simulation(tmp_path):
    fmu = edited_fmu(reference_fmu("Stair"), tmp_path, remove_element("ModelExchange"))
    result = simulate_given(fmu)["Stair"]
    model_exchange = simulate_given(reference_fmu("Stair"))["Stair"]
    # Stair requests termination at its event at t=9: FMPy's ME loop stops before recording the
    # post-event row (counter 9), CS records it (10); so compare the settled value (the last row
    # of each time) before t=9
    settled = model_exchange.groupby("time")["counter"].last().iloc[:-1]
    pd.testing.assert_series_equal(result.set_index("time")["counter"].iloc[:-1], settled)
    assert not result["time"].duplicated().any()  # no event rows on Co-Simulation


def test_requesting_a_missing_type_is_a_config_error(tmp_path):
    fmu = edited_fmu(reference_fmu("Stair"), tmp_path, remove_element("CoSimulation"))
    with pytest.raises(ConfigError, match="Invalid run settings") as error:
        simulate_given(fmu, fmu_type="cs")
    assert "build.fmu_type: 'Stair' has no Co-Simulation interface" in error.value.diagnostics


def test_unknown_type_is_a_config_error():
    with pytest.raises(ConfigError) as error:
        simulate_given(reference_fmu("Dahlquist"), fmu_type="xx")
    assert "build.fmu_type: expected 'me', 'cs' or null, got 'xx'" in error.value.diagnostics
