"""A failed FMU run lists what the FMU, FMI and the run said, without Python tracebacks."""

import logging
import re

import pytest

from mtools.errors import SimulationError
from mtools.internal.fmu import child
from mtools.internal.fmu.diagnostics import (failure_diagnostics,
                                             warning_entries)
from tests.fmu.helpers import reference_fmu, simulate_exported, simulate_given


def test_assert_failure_lists_fmu_messages_failed_call_and_exception():
    with pytest.raises(SimulationError, match=r"^Simulation of 'FmuTests.AssertFails' failed:") as error:
        simulate_exported("FmuTests.AssertFails")
    lines = error.value.diagnostics.splitlines()
    assert any("time passed 0.5" in line for line in lines)
    assert any(re.search(r"fmi2\w+ failed with status \d \(\w+\)", line) for line in lines)
    assert "Traceback" not in error.value.diagnostics
    assert lines[-1].startswith("FMICallException:")
    call = next(i for i, line in enumerate(lines) if re.fullmatch(r"fmi2\w+ failed with status \d \(\w+\)", line))
    assert call < len(lines) - 1


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


def test_fmi_logger_message_precedes_failed_call_and_exception():
    with pytest.raises(SimulationError) as error:
        simulate_given(reference_fmu("Stair"), parameters={"counter": 11})
    assert error.value.diagnostics.splitlines() == [
        'FMI | error | logStatusError | Variable "counter" must be at most 10 but was 11.',
        "fmi2SetInteger failed with status 3 (error)",
        "FMICallException: fmi2SetInteger failed with status 3 (error).",
    ]


def test_diagnostics_keep_order_of_occurrence_and_strip_the_exception_prefix():
    output = (
        "FMI | warning | logAll | first\n"
        "LOG_ASSERT        | error   | [model.mo:1:1]\n"
        "|                 | |       | assertion violated\n"
        "FMI | error | logStatusError | second\n"
        "fmi2DoStep failed with status 3 (error)\n"
        "mtools-fmu-exception | FMICallException: boom\n"
    )
    assert failure_diagnostics(output).splitlines() == [
        "FMI | warning | logAll | first",
        "LOG_ASSERT | error | [model.mo:1:1]",
        "    assertion violated",
        "FMI | error | logStatusError | second",
        "fmi2DoStep failed with status 3 (error)",
        "FMICallException: boom",
    ]


def test_diagnostics_keep_only_the_first_failed_call_and_drop_tracebacks():
    output = (
        "Exception ignored in: <function f>\n"
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1, in f\n'
        "fmi2GetDerivatives failed with status 3 (error)\n"
        "mtools-fmu-exception | FMICallException: fmi2Other failed with status 2 (discard).\n"
    )
    lines = failure_diagnostics(output).splitlines()
    assert lines == [
        "fmi2GetDerivatives failed with status 3 (error)",
        "FMICallException: fmi2Other failed with status 2 (discard).",
    ]


def test_warning_entries_list_fmi_warnings_before_log_entries():
    output = (
        "FMI | warning | logAll | careful\n"
        "FMI | error | logStatusError | not a warning\n"
        "LOG_ASSERT        | warning | [model.mo:1:1]\n"
        "|                 | |       | assertion\n"
    )
    assert warning_entries(output) == [
        "FMI | warning | logAll | careful",
        "LOG_ASSERT | warning | [model.mo:1:1]\n    assertion",
    ]


def test_exception_line_is_one_line():
    line = child.exception_line(ValueError("first\nsecond\n  third"))
    assert line == "mtools-fmu-exception | ValueError: first second third"
