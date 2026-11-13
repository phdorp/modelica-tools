"""A failed FMU run lists what the FMU, FMI and the run said, without Python tracebacks."""

import logging
import re
from pathlib import Path

import pytest

from mtools.errors import SimulationError
from mtools.internal.fmu import child
from mtools.internal.fmu.diagnostics import (failure_diagnostics,
                                             warning_entries)
from mtools.internal.fmu.request import RunRequest
from tests.fmu.helpers import reference_fmu, simulate_exported, simulate_given


def test_assert_failure_lists_fmu_messages_failed_call_and_exception(caplog):
    caplog.set_level(logging.DEBUG)
    with pytest.raises(SimulationError, match=r"^Simulation of 'FmuTests.AssertFails' failed:") as error:
        simulate_exported("FmuTests.AssertFails")
    lines = error.value.diagnostics.splitlines()
    assert any("time passed 0.5" in line for line in lines)
    assert any(re.search(r"fmi2\w+ failed with status \d \(\w+\)", line) for line in lines)
    assert "Traceback" not in error.value.diagnostics
    assert lines[-1].startswith("FMICallException:")
    call = next(i for i, line in enumerate(lines) if re.fullmatch(r"fmi2\w+ failed with status \d \(\w+\)", line))
    assert call < len(lines) - 1
    # the child's raw output goes to the debug log
    debug = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
    assert any("mtools-fmu-exception |" in message for message in debug)


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


def test_exception_line_without_a_message_names_the_type_alone():
    assert child.exception_line(ValueError()) == "mtools-fmu-exception | ValueError"


def _dahlquist_request(directory: Path) -> Path:
    """Write a Model Exchange request for the Dahlquist Reference-FMU into ``directory``."""
    RunRequest(
        fmu_path=str(reference_fmu("Dahlquist")),
        unzip_dir=str(directory / "fmu"),
        fmi_type="ModelExchange",
        start_time=0.0,
        stop_time=1.0,
        interval=0.1,
        tolerance=1e-6,
        solver="CVode",
        start_values={},
        output=["x"],
        cvode_guard=False,
    ).write(directory)
    return directory


def test_child_reports_the_exception_that_ended_the_run_as_its_last_line(tmp_path, monkeypatch, capsys):
    def failing(request: RunRequest, saver: object) -> None:
        raise RuntimeError("boom\nagain")

    monkeypatch.setattr(child, "_simulate", failing)

    assert child.main([str(_dahlquist_request(tmp_path))]) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "mtools-fmu-exception | RuntimeError: boom again"


def test_failing_partial_save_keeps_the_run_exception(tmp_path, monkeypatch, capsys):
    def failing(request: RunRequest, saver: child._PartialSaver) -> None:
        saver(0.1, object())  # a step was recorded, so the failure path saves
        raise RuntimeError("the run failed")

    def failing_save(self: child._PartialSaver) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(child, "_simulate", failing)
    monkeypatch.setattr(child._PartialSaver, "save", failing_save)

    assert child.main([str(_dahlquist_request(tmp_path))]) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "mtools-fmu-exception | RuntimeError: the run failed"
