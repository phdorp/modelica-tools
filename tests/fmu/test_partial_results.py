"""A failed FMU run returns the rows recorded before it failed, shaped like a full result."""

from pathlib import Path

import numpy as np
import pytest

from mtools.errors import SimulationError, SimulationTimeout
from mtools.internal.fmu import child, runner
from mtools.internal.fmu.resolve import ResolvedRun
from mtools.internal.omc.config import RunSettings
from mtools.internal.omc.process import ProcessResult
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


RUN = ResolvedRun(
    model_name="M",
    fmu_type="me",
    start_time=0.0,
    stop_time=1.0,
    interval=0.1,
    tolerance=1e-6,
    solver="CVode",
    start_values={},
    columns={"x": "x"},
    column_types={"x": "Real"},
    cvode_guard=True,
    build_values={},
)


@pytest.mark.parametrize(
    "content", [None, b"", b"\x93NUMPY cut off"], ids=["missing", "empty", "cut-off"]
)
def test_unreadable_partial_result_is_none(tmp_path, content):
    if content is not None:
        (tmp_path / child.PARTIAL_FILE_NAME).write_bytes(content)
    assert runner._read_partial(tmp_path, RUN) is None


def test_non_structured_partial_result_keeps_the_run_error(monkeypatch):
    def failed_run(command: object, directory: Path, timeout: float | None) -> ProcessResult:
        np.save(directory / child.PARTIAL_FILE_NAME, np.zeros(3), allow_pickle=False)
        return ProcessResult(returncode=1, output="", timed_out=False)

    monkeypatch.setattr(runner, "execute", failed_run)
    with pytest.raises(SimulationError, match="^Simulation of 'M' failed:") as error:
        runner._run(Path("model.fmu"), RUN, RunSettings())
    assert error.value.partial_result is None


def test_partial_result_conversion_bug_is_not_hidden(tmp_path, monkeypatch):
    rows = np.zeros(2, dtype=[("time", "f8"), ("x", "f8")])
    np.save(tmp_path / child.PARTIAL_FILE_NAME, rows, allow_pickle=False)

    def broken(array: np.ndarray, run: ResolvedRun) -> None:
        raise TypeError("a bug in to_frame")

    monkeypatch.setattr(runner, "to_frame", broken)
    with pytest.raises(TypeError, match="a bug in to_frame"):
        runner._read_partial(tmp_path, RUN)
