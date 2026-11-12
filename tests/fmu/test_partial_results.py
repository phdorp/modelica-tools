"""A failed FMU run returns the rows recorded before it failed, shaped like a full result."""

import pytest

from mtools.errors import SimulationError, SimulationTimeout
from tests.fmu.helpers import simulate_exported, simulate_given


def test_partial_result_after_an_fmu_error():
    with pytest.raises(SimulationError) as error:
        simulate_exported("FmuTests.AssertFails")
    partial = error.value.partial_result
    full = simulate_exported("FmuTests.Decay")["FmuTests.Decay"]  # AssertFails extends Decay
    assert partial is not None and 0.4 <= partial["time"].iloc[-1] <= 0.5
    assert list(partial.columns) == list(full.columns) and (partial.dtypes == full.dtypes).all()


def test_partial_result_after_a_timeout():
    simulate_exported("FmuTests.SlowThenHang", stop_time=0.105)  # export first, outside the timed run
    with pytest.raises(SimulationTimeout) as error:
        simulate_exported("FmuTests.SlowThenHang", timeout=6)
    partial = error.value.partial_result
    assert partial is not None and partial["time"].iloc[-1] <= 0.51


def test_partial_result_is_none_before_the_first_save():
    simulate_exported("FmuTests.Hang", stop_time=0.1)  # export first
    with pytest.raises(SimulationTimeout) as error:
        simulate_exported("FmuTests.Hang", timeout=1)
    assert error.value.partial_result is None


def test_partial_result_uses_the_name_map(exported_fmu):
    with pytest.raises(SimulationError) as error:
        simulate_given(exported_fmu("FmuTests.AssertFails"), name_map={"state": "x"})
    partial = error.value.partial_result
    assert partial is not None and "state" in partial.columns and "x" not in partial.columns
