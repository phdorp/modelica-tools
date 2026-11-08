"""Run failures, partial results, warnings and timeouts at `Build.simulate()`, against real OMC."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from mtools.errors import SimulationError, SimulationTimeout
from mtools.internal.omc.build import Build, build
from mtools.internal.omc.config import BuildConfig, RunSettings
from mtools.internal.omc.run_diagnostics import log_entries, notable_entries

SLOW = "model Slow\n  Real x(start = 0, fixed = true);\nequation\n  der(x) = 1;\n  annotation(experiment(StopTime = 1e9, Interval = 1e6));\nend Slow;\n"
CHATTERING = (
    "model Chattering\n  Real x(start = 1, fixed = true);\nequation\n"
    "  der(x) = if x > 0 then -1 else 1;\n  annotation(experiment(StopTime = 2));\nend Chattering;\n"
)


def _build(tmp_path: Path, name: str, source: str) -> Build:
    path = tmp_path / f"{name}.mo"
    path.write_text(source)
    return build(BuildConfig(model_path=path, model_name=name))


# (model name, source, phrases that appear once in the failure diagnostics)
RUN_ERRORS = [
    (
        "DivisionByZero",
        "model DivisionByZero\n  parameter Real p = 0;\n  Real y;\nequation\n  y = 1/p;\nend DivisionByZero;\n",
        ["division by zero at time 0, (a=1) / (b=0), where divisor b expression is: p"],
    ),
    (
        "DivisionByZeroDuringSimulation",
        "model DivisionByZeroDuringSimulation\n  Real d(start = 1, fixed = true);\n  Real y;\nequation\n"
        "  der(d) = -2;\n  y = 1/(if d > 0 then d else 0);\nend DivisionByZeroDuringSimulation;\n",
        ["division by zero at time 0.5", "where divisor b expression is: if d > 0.0 then d else 0.0"],
    ),
    (
        "InitializationNonlinearFailure",
        "model InitializationNonlinearFailure\n  Real x(start = 1);\nequation\n  x*exp(x) + 1 = 0;\nend InitializationNonlinearFailure;\n",
        ["Solving non-linear system", "failed at time=0.", "simulation terminated by an assertion at initialization"],
    ),
    (
        "LinearSystemSingular",
        "model LinearSystemSingular\n  Real a = if time > 0.5 then 1 else 0.5;\n  Real x, y;\nequation\n"
        "  x + a*y = 1;\n  a*x + y = 0;\nend LinearSystemSingular;\n",
        ["Error solving linear system of equations", "failed at time=0.5"],
    ),
    (
        "IntegratorFailure",
        "model IntegratorFailure\n  Real x(start = 1, fixed = true);\nequation\n  der(x) = x^3*1e3;\nend IntegratorFailure;\n",
        ["Integrator failed.", "Simulation terminated at time 0.000499"],
    ),
]


@pytest.mark.parametrize(("name", "source", "phrases"), RUN_ERRORS, ids=[case[0] for case in RUN_ERRORS])
def test_run_error_is_readable_and_reported_once(tmp_path: Path, caplog, capsys, name, source, phrases):
    built = _build(tmp_path, name, source)

    with caplog.at_level(logging.INFO), pytest.raises(SimulationError) as raised:
        built.simulate(RunSettings())

    message = str(raised.value)
    assert message.startswith(f"Simulation of '{name}' failed:\n")
    for phrase in phrases:
        assert message.count(phrase) == 1, phrase
    assert "LOG_SUCCESS" not in message
    assert "DASKR" not in message
    assert "In above" not in message
    assert "\\n" not in message
    assert repr(raised.value) == message
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert capsys.readouterr().out == ""


def test_failed_assert_keeps_the_partial_result_up_to_the_failure(tmp_path: Path):
    built = _build(
        tmp_path,
        "Fails",
        "model Fails\n  Real x(start = 0, fixed = true);\nequation\n  der(x) = 1;\n"
        '  assert(x < 0.5, "x exceeded its limit");\n  annotation(experiment(StopTime = 1, Interval = 0.1));\nend Fails;\n',
    )

    with pytest.raises(SimulationError) as raised:
        built.simulate(RunSettings())

    partial = raised.value.partial_result
    assert partial is not None
    assert list(partial.columns)[:2] == ["time", "x"]
    assert 0 < len(partial) < 11
    assert partial["time"].iloc[-1] < 0.6


def test_failure_without_a_readable_result_has_no_partial_result(tmp_path: Path):
    built = _build(
        tmp_path,
        "InitFails",
        "model InitFails\n  parameter Real p = 0;\n  Real y;\nequation\n  y = 1/p;\nend InitFails;\n",
    )

    with pytest.raises(SimulationError) as raised:
        built.simulate(RunSettings())

    assert raised.value.partial_result is None


def test_clean_exit_without_result_file_raises_simulation_error(tmp_path: Path):
    built = _build(tmp_path, "Quiet", "model Quiet\n  Real x(start = 1, fixed = true);\nequation\n  der(x) = -x;\nend Quiet;\n")
    # An empty variable filter matches nothing, so the run exits cleanly but writes no trajectories file.
    result_name = f"{built.file_name_prefix}_res.mat"

    import mtools.internal.omc.run as run

    original = run._c_command

    def command(*args):  # make the binary write its result elsewhere
        return [part for part in original(*args) if not part.startswith("-outputFormat")] + ["-outputFormat=csv"]

    run._c_command = command  # type: ignore[assignment]
    try:
        with pytest.raises(SimulationError, match=result_name) as raised:
            built.simulate(RunSettings())
    finally:
        run._c_command = original  # type: ignore[assignment]
    assert raised.value.partial_result is None


NONLINEAR = (
    "model NonlinearSystemFailure\n  Real x(start = -0.5);\nequation\n  x*exp(x) = -0.2 - time;\nend NonlinearSystemFailure;\n"
)
MINMAX = "model MinMaxViolation\n  Real x(start = 0, fixed = true, max = 1);\nequation\n  der(x) = 2;\nend MinMaxViolation;\n"


@pytest.mark.parametrize(
    ("name", "source", "phrases"),
    [
        (
            "NonlinearSystemFailure",
            NONLINEAR,
            [
                "Solving non-linear system",
                "failed at time=0.16",
                "For more information please use -lv LOG_NLS.",
                "LOG_STDOUT | warning | Integrator attempt to handle a problem with a called assert.",
            ],
        ),
        (
            "MinMaxViolation",
            MINMAX,
            [
                "MinMaxViolation.mo:2:3-2:43:writable]",
                "The following assertion has been violated at time 0.5",
                "Variable violating max constraint: x <= 1.0",
            ],
        ),
    ],
)
def test_warnings_of_a_successful_run_are_logged_once(tmp_path: Path, caplog, capsys, name, source, phrases):
    built = _build(tmp_path, name, source)

    with caplog.at_level(logging.INFO):
        result = built.simulate(RunSettings())

    assert not result.empty
    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1, warnings
    assert warnings[0].startswith(f"Simulation of '{name}' reported warnings:\n")
    for phrase in phrases:
        assert warnings[0].count(phrase) == 1, phrase
    assert "LOG_SUCCESS" not in warnings[0]
    assert capsys.readouterr().out == ""


def test_clean_run_logs_no_warnings(tmp_path: Path, caplog):
    built = _build(tmp_path, "Clean", "model Clean\n  Real x(start = 1, fixed = true);\nequation\n  der(x) = -x;\nend Clean;\n")

    with caplog.at_level(logging.INFO):
        built.simulate(RunSettings())

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_chattering_model_fails_readably_by_default(tmp_path: Path):
    built = _build(tmp_path, "Chattering", CHATTERING)

    started = time.monotonic()
    with pytest.raises(SimulationError) as raised:
        built.simulate(RunSettings(timeout=60))

    assert not isinstance(raised.value, SimulationTimeout)
    assert time.monotonic() - started < 60
    message = str(raised.value)
    assert message.startswith("Simulation of 'Chattering' failed:\n")
    assert message.count("Chattering detected around time 1.0") == 1
    assert message.count("Aborting simulation due to chattering being detected") == 1


def test_chattering_guard_can_be_turned_off(tmp_path: Path):
    built = _build(tmp_path, "Chattering", CHATTERING)

    with pytest.raises(SimulationTimeout):
        built.simulate(RunSettings(abort_on_chattering=False, timeout=3))


def test_timeout_kills_the_run_and_raises_with_a_partial_result(tmp_path: Path):
    built = _build(tmp_path, "Slow", SLOW)

    started = time.monotonic()
    with pytest.raises(SimulationTimeout) as raised:
        built.simulate(RunSettings(timeout=2, tolerance=1e-12, solver="euler", interval=1e-3, stop_time=1e6))

    assert time.monotonic() - started < 30
    assert str(raised.value).startswith("Simulation of 'Slow' timed out after 2 s:")
    assert isinstance(raised.value, SimulationError)
    partial = raised.value.partial_result
    assert partial is not None
    assert partial["time"].iloc[0] == 0.0
    assert len(partial) > 1


def test_no_simulation_process_is_left_after_a_timeout(tmp_path: Path):
    built = _build(tmp_path, "Slow", SLOW)

    with pytest.raises(SimulationTimeout):
        built.simulate(RunSettings(timeout=1, stop_time=1e6, interval=1e-3, solver="euler"))

    assert not _running(str(built.directory / built.file_name_prefix))


def test_keyboard_interrupt_kills_the_process_group_before_propagating(tmp_path: Path):
    built = _build(tmp_path, "Slow", SLOW)
    script = (
        "import os, signal, sys, threading\n"
        "from pathlib import Path\n"
        "from mtools.internal.omc.build import build\n"
        "from mtools.internal.omc.config import BuildConfig, RunSettings\n"
        f"b = build(BuildConfig(model_path=Path({str(tmp_path / 'Slow.mo')!r}), model_name='Slow'))\n"
        "threading.Timer(2, lambda: os.kill(os.getpid(), signal.SIGINT)).start()\n"
        "try:\n"
        "    b.simulate(RunSettings(stop_time=1e6, interval=1e-3, solver='euler'))\n"
        "except KeyboardInterrupt:\n"
        "    print('interrupted', flush=True)\n"
    )
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)

    assert "interrupted" in completed.stdout, completed.stderr
    # The child was built again by the script, so match on any run of a binary named after the prefix.
    assert not _running(f"/{built.file_name_prefix} -inputPath=")


def _running(needle: str) -> bool:
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        except OSError:
            continue
        if needle in command and int(pid) != os.getpid():
            return True
    return False


LOG = (
    "LOG_SUCCESS       | info    | The initialization finished successfully without homotopy method.\n"
    "DASKR--  AT T (=R1) AND STEPSIZE H (=R2) THE                                    \n"
    "      In above,  R1 =   4.9999032681052E-04   R2 =   1.0914468208052E-18\n"
    "LOG_STDOUT        | warning | DDASSL had repeated error test failures on the last attempted step.\n"
    "LOG_ASSERT        | debug   | Solving non-linear system 8 failed at time=0.168.\n"
    "|                 | |       | For more information please use -lv LOG_NLS.\n"
    "LOG_STDOUT        | info    | model terminate | Integrator failed. | Simulation terminated at time 0.00049999\n"
)


def test_log_entries_drop_success_and_banners_and_indent_continuations():
    assert log_entries(LOG) == [
        "LOG_STDOUT | warning | DDASSL had repeated error test failures on the last attempted step.",
        "LOG_ASSERT | debug | Solving non-linear system 8 failed at time=0.168.\n"
        "    For more information please use -lv LOG_NLS.",
        "LOG_STDOUT | info | model terminate | Integrator failed. | Simulation terminated at time 0.00049999",
    ]


def test_notable_entries_are_asserts_and_warnings_or_errors():
    assert notable_entries(LOG) == [
        "LOG_STDOUT | warning | DDASSL had repeated error test failures on the last attempted step.",
        "LOG_ASSERT | debug | Solving non-linear system 8 failed at time=0.168.\n"
        "    For more information please use -lv LOG_NLS.",
    ]


def test_log_entries_of_unstructured_output_is_empty():
    assert log_entries("Segmentation fault\n") == []
