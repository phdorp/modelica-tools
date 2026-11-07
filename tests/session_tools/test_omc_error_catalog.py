"""Error classes from the OpenModelica User's Guide (v1.24), reproduced on the installed OMC.

Each case is a minimal model that triggers one documented error class. The tests pin
how mtools reports it: the pydelica exception type and stable OMC phrases. Findings,
including the error classes that are not pinned here, are in
``docs/research/2026-11-07-omc-error-catalog.md``.
"""

from __future__ import annotations

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
]


@pytest.mark.parametrize(
    ("section", "name", "source", "exc_type", "phrases"),
    RUNTIME_ERRORS,
    ids=[case[1] for case in RUNTIME_ERRORS],
)
def test_runtime_error_reports_cause(tmp_path, section, name, source, exc_type, phrases):
    path = tmp_path / f"{name}.mo"
    path.write_text(source)
    builder = session_tools.SessionBuilder(path)

    with pytest.raises(exc_type) as exc:
        builder.session.simulate(model_name=name)

    for phrase in phrases:
        assert phrase in str(exc.value), phrase

