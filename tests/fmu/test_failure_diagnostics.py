"""A failed FMU run lists what the FMU, FMI and the run said, without Python tracebacks."""

import logging
import re

import pytest

from mtools.errors import SimulationError
from mtools.internal.fmu.diagnostics import failure_diagnostics
from tests.fmu.helpers import simulate_exported


def test_assert_failure_lists_fmu_messages_failed_call_and_exception():
    with pytest.raises(SimulationError, match=r"^Simulation of 'FmuTests.AssertFails' failed:") as error:
        simulate_exported("FmuTests.AssertFails")
    lines = error.value.diagnostics.splitlines()
    assert any("time passed 0.5" in line for line in lines)
    assert any(re.search(r"fmi2\w+ failed with status \d \(\w+\)", line) for line in lines)
    assert "Traceback" not in error.value.diagnostics
    assert lines.index(next(line for line in lines if "time passed 0.5" in line)) < len(lines) - 1  # exception last


def test_raw_output_is_the_fallback():
    assert failure_diagnostics("something odd\n") == "something odd"


def test_successful_run_logs_warnings_once(caplog):
    simulate_exported("FmuTests.AssertWarns")
    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING and "reported warnings" in record.getMessage()
    ]
    assert len(warnings) == 1
    assert "time passed 0.5" in warnings[0].getMessage()


def test_child_output_goes_to_debug_log(caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(SimulationError):
        simulate_exported("FmuTests.AssertFails")
    debug = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("mtools-fmu-exception |" in message for message in debug)
