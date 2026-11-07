"""Error classes from the OpenModelica User's Guide (v1.24), reproduced on the installed OMC.

Each case is a minimal model that triggers one documented error class. The tests pin
how mtools reports it: the pydelica exception type and stable OMC phrases. Findings,
including the error classes that are not pinned here, are in
``docs/research/2026-11-07-omc-error-catalog.md``.
"""

from __future__ import annotations

import logging
import threading

import pydelica.exception
import pytest

import mtools.internal.session_tools as session_tools

# (guide section, model name, source, expected exception type, expected phrases)
TRANSLATION_ERRORS = [
    (
        "1.2.2",
        "TypeMismatch",
        "model TypeMismatch\n  Integer t = 1.5;\nend TypeMismatch;\n",
        pydelica.exception.OMExecutionError,
        [
            "TypeMismatch.mo:2:3-2:18:writable] Error: Type mismatch in binding t = 1.5,"
            " expected subtype of Integer, got type Real."
        ],
    ),
    (
        "1.2.2",
        "DerInteger",
        "model DerInteger\n  Integer a;\n  Real b;\nequation\n  der(a) = b;\n  der(b) = 12.0;\nend DerInteger;\n",
        pydelica.exception.OMExecutionError,
        ["DerInteger.mo:5:3-5:13:writable] Error: Argument 'a' of der is not differentiable."],
    ),
    (
        "9.2",
        "ArrayModifierWithoutEach",
        "model ArrayModifierWithoutEach\n  model C\n    parameter Real p;\n    Real y = p;\n  end C;\n"
        "  parameter Real r = 4;\n  C ma[3](p = r);\nend ArrayModifierWithoutEach;\n",
        pydelica.exception.OMExecutionError,
        [
            # OMC's location-prefixed "From here:" line points at the offending modifier.
            "ArrayModifierWithoutEach.mo:7:11-7:16:writable] Notification: From here:",
            "Error: Non-array modification 'r' for array component 'p', possibly due to missing 'each'.",
        ],
    ),
    (
        "9.4",
        "PartialPackageLookup",
        "model PartialPackageLookup\n  partial package PartialPackage\n    function f\n"
        "      input Real x;\n      output Real y;\n    algorithm\n      y := 2*x;\n    end f;\n"
        "  end PartialPackage;\n  package P = PartialPackage;\n  Real x = P.f(time);\nend PartialPackageLookup;\n",
        pydelica.exception.OMExecutionError,
        [
            "PartialPackageLookup.mo:11:3-11:21:writable] Error: P is partial,"
            " name lookup is not allowed in partial classes."
        ],
    ),
    (
        "9.5",
        "AlgorithmEquality",
        "model AlgorithmEquality\n  function f\n    input Real x;\n    input Real y = 0;\n"
        "    output Real z;\n  algorithm\n    z = x + y;\n  end f;\n  Real v = f(time);\nend AlgorithmEquality;\n",
        pydelica.exception.OMParsingError,
        [
            "AlgorithmEquality.mo:7:7-7:8:writable] Error: Parse error: Algorithms can not contain"
            " equations ('='), use assignments (':=') instead"
        ],
    ),
    (
        "9.6",
        "PublicFunctionVariable",
        "model PublicFunctionVariable\n  function f\n    input Real x;\n    output Real y;\n    Real z;\n"
        "  algorithm\n    z := 2;\n    y := x + z;\n  end f;\n  Real v = f(time);\nend PublicFunctionVariable;\n",
        pydelica.exception.OMExecutionError,
        [
            "PublicFunctionVariable.mo:5:5-5:11:writable] Error: Invalid public variable z,"
            " function variables that are not input/output must be protected."
        ],
    ),
    (
        "3.2.5 (Symbolic)",
        "StructurallySingular",
        "model StructurallySingular\n  Real x;\n  Real y;\nequation\n  x = 1;\n  x = 2*time;\nend StructurallySingular;\n",
        pydelica.exception.OMExecutionError,
        ["Error: Internal error IndexReduction.pantelidesIndexReduction failed!"],
    ),
]


@pytest.mark.parametrize(
    ("section", "name", "source", "exc_type", "phrases"),
    TRANSLATION_ERRORS,
    ids=[case[1] for case in TRANSLATION_ERRORS],
)
def test_translation_error_is_reported_once_and_readably(
    tmp_path, section, name, source, exc_type, phrases
):
    path = tmp_path / f"{name}.mo"
    path.write_text(source)

    with pytest.raises(exc_type) as exc:
        session_tools.SessionBuilder(path)

    message = str(exc.value)
    assert message.startswith(f"Modelica translation failed for '{path}':\n")
    for phrase in phrases:
        assert message.count(phrase) == 1, phrase
    assert "Notification: Automatically loaded package" not in message
    assert "Execution failed!" not in message
    assert "\\n" not in message
    assert repr(exc.value) == message


# (guide section, model name, source, expected exception type, expected phrases)
RUNTIME_ERRORS = [
    (
        "3.x LOG_DIVISION",
        "DivisionByZero",
        "model DivisionByZero\n  parameter Real p = 0;\n  Real y;\nequation\n  y = 1/p;\nend DivisionByZero;\n",
        ZeroDivisionError,
        ["division by zero at time 0, (a=1) / (b=0), where divisor b expression is: p"],
    ),
    (
        "3.x LOG_DIVISION",
        "DivisionByZeroDuringSimulation",
        "model DivisionByZeroDuringSimulation\n  Real d(start = 1, fixed = true);\n  Real y;\nequation\n"
        "  der(d) = -2;\n  y = 1/(if d > 0 then d else 0);\nend DivisionByZeroDuringSimulation;\n",
        ZeroDivisionError,
        ["division by zero at time 0.5", "where divisor b expression is: if d > 0.0 then d else 0.0"],
    ),
    (
        "6.3 / 6.4",
        "InitializationNonlinearFailure",
        "model InitializationNonlinearFailure\n  Real x(start = 1);\nequation\n"
        "  x*exp(x) + 1 = 0;\nend InitializationNonlinearFailure;\n",
        pydelica.exception.OMAssertionError,
        ["Solving non-linear system", "failed at time=0.", "simulation terminated by an assertion at initialization"],
    ),
    (
        "6.4",
        "LinearSystemSingular",
        "model LinearSystemSingular\n  Real a = if time > 0.5 then 1 else 0.5;\n  Real x, y;\nequation\n"
        "  x + a*y = 1;\n  a*x + y = 0;\nend LinearSystemSingular;\n",
        pydelica.exception.OMExecutionError,
        ["Error solving linear system of equations", "failed at time=0.5"],
    ),
    (
        "6.1",
        "IntegratorFailure",
        "model IntegratorFailure\n  Real x(start = 1, fixed = true);\nequation\n  der(x) = x^3*1e3;\n"
        "end IntegratorFailure;\n",
        pydelica.exception.OMExecutionError,
        ["Integrator failed.", "Simulation terminated at time 0.000499"],
    ),
]


@pytest.mark.parametrize(
    ("section", "name", "source", "exc_type", "phrases"),
    RUNTIME_ERRORS,
    ids=[case[1] for case in RUNTIME_ERRORS],
)
def test_runtime_error_is_reported_once_and_readably(
    tmp_path, capsys, section, name, source, exc_type, phrases
):
    path = tmp_path / f"{name}.mo"
    path.write_text(source)
    builder = session_tools.SessionBuilder(path)
    capsys.readouterr()

    with pytest.raises(exc_type) as exc:
        builder.session.simulate(model_name=name)

    message = str(exc.value)
    assert message.startswith(f"Simulation of '{name}' failed:\n")
    for phrase in phrases:
        assert message.count(phrase) == 1, phrase
    assert "LOG_SUCCESS" not in message
    assert "DASKR" not in message
    assert "In above" not in message
    assert "\\n" not in message
    assert repr(exc.value) == message
    assert type(exc.value.__cause__) is exc_type
    assert capsys.readouterr().out == ""


# (guide section, model name, source, expected phrases in the WARNING record)
NON_FATAL_RUNTIME_ASSERTS = [
    (
        "6.4",
        "NonlinearSystemFailure",
        "model NonlinearSystemFailure\n  Real x(start = -0.5);\nequation\n  x*exp(x) = -0.2 - time;\n"
        "end NonlinearSystemFailure;\n",
        ["Solving non-linear system", "failed at time=0.16", "For more information please use -lv LOG_NLS."],
    ),
    (
        "29.2 warnMinMax",
        "MinMaxViolation",
        "model MinMaxViolation\n  Real x(start = 0, fixed = true, max = 1);\nequation\n  der(x) = 2;\n"
        "end MinMaxViolation;\n",
        [
            "MinMaxViolation.mo:2:3-2:43:writable]",
            "The following assertion has been violated at time 0.5",
            "Variable violating max constraint: x <= 1.0",
        ],
    ),
]


@pytest.mark.parametrize(
    ("section", "name", "source", "phrases"),
    NON_FATAL_RUNTIME_ASSERTS,
    ids=[case[1] for case in NON_FATAL_RUNTIME_ASSERTS],
)
def test_non_fatal_runtime_assert_is_logged_as_warning(
    tmp_path, caplog, capsys, section, name, source, phrases
):
    """OMC finishes these runs successfully; the assert is only reported in its log."""
    path = tmp_path / f"{name}.mo"
    path.write_text(source)
    builder = session_tools.SessionBuilder(path)
    capsys.readouterr()

    with caplog.at_level(logging.WARNING):
        builder.session.simulate(model_name=name)

    warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1, warnings
    assert warnings[0].startswith(f"Simulation of '{name}' reported failed assertions:\n")
    for phrase in phrases:
        assert warnings[0].count(phrase) == 1, phrase
    assert "LOG_SUCCESS" not in warnings[0]
    assert capsys.readouterr().out == ""


def test_clean_simulation_logs_no_warnings(tmp_path, caplog, capsys):
    path = tmp_path / "Clean.mo"
    path.write_text("model Clean\n  Real x(start = 1, fixed = true);\nequation\n  der(x) = -x;\nend Clean;\n")
    builder = session_tools.SessionBuilder(path)
    capsys.readouterr()

    with caplog.at_level(logging.WARNING):
        builder.session.simulate(model_name="Clean")

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert capsys.readouterr().out == ""


CHATTERING = (
    "model Chattering\n  Real x(start = 1, fixed = true);\nequation\n"
    "  der(x) = if x > 0 then -1 else 1;\n  annotation(experiment(StopTime = 2));\nend Chattering;\n"
)


def test_chattering_simulation_is_aborted(tmp_path, capsys):
    """Guide sections 7.1.3 and 30.1: without -abortSlowSimulation this run never returns."""
    path = tmp_path / "Chattering.mo"
    path.write_text(CHATTERING)
    builder = session_tools.SessionBuilder(path)
    capsys.readouterr()

    raised: list[BaseException] = []

    def simulate() -> None:
        try:
            builder.session.simulate(model_name="Chattering")
        except BaseException as error:
            raised.append(error)

    worker = threading.Thread(target=simulate, daemon=True)
    worker.start()
    worker.join(timeout=60)
    assert not worker.is_alive(), "simulation of a chattering model did not terminate"

    assert len(raised) == 1
    error = raised[0]
    assert isinstance(error, pydelica.exception.OMExecutionError)
    message = str(error)
    assert message.startswith("Simulation of 'Chattering' failed:\n")
    assert message.count("Chattering detected around time 1.0") == 1
    assert message.count("Aborting simulation due to chattering being detected") == 1
    assert "LOG_SUCCESS" not in message
    assert repr(error) == message
    assert capsys.readouterr().out == ""


def test_abort_slow_simulation_is_a_default_that_can_be_turned_off(tmp_path):
    path = tmp_path / "Chattering.mo"
    path.write_text(CHATTERING)
    session = session_tools.SessionBuilder(path).session

    options = session.get_runtime_options("Chattering")
    assert options.abortSlowSimulation is True
    assert "-abortSlowSimulation" in options.assemble_args()

    options.abortSlowSimulation = False
    assert "-abortSlowSimulation" not in options.assemble_args()


def test_build_warning_is_logged_without_notifications(tmp_path, caplog):
    """Guide section 9.8: users should act on this warning until it no longer appears."""
    path = tmp_path / "InitialConditionsNotSpecified.mo"
    path.write_text(
        "model InitialConditionsNotSpecified\n  Real x;\n  Real y(start = 1);\n  Real z(start = 2);\n"
        "equation\n  der(x) = y + z;\n  y = 2*x;\n  z = 10*x + 1;\nend InitialConditionsNotSpecified;\n"
    )

    with caplog.at_level(logging.WARNING):
        session_tools.SessionBuilder(path)

    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("Warning: The initial conditions are not fully specified." in m for m in messages)
    assert not any("Notification:" in m for m in messages)
