from __future__ import annotations

import dataclasses
import logging

import pydelica.exception
import pytest
from hydra.errors import InstantiationException

import mtools.internal.session_tools as session_tools
import mtools.internal.sim_tools as sim_tools
import mtools.session_config as session_config
from mtools.internal.pydelica_patch import (_omc_diagnostics,
                                            _translation_error_message)

IMBALANCED_STDERR = (
    "Notification: Automatically loaded package Complex 4.1.0 due to uses annotation from Modelica.\n"
    "Error: Too few equations, under-determined system. The model has 1 equation(s) and 2 variable(s).\n"
    "[/m/Imbalanced.mo:3:3-3:9:writable] Warning: Variable y does not have any remaining equation to be solved in.\n"
    "  The original equations were:\n"
    "\n"
    "Execution failed!\n"
)


def test_omc_diagnostics_keeps_errors_warnings_and_continuations_in_order():
    assert _omc_diagnostics("", IMBALANCED_STDERR).splitlines() == [
        "Error: Too few equations, under-determined system. The model has 1 equation(s) and 2 variable(s).",
        "[/m/Imbalanced.mo:3:3-3:9:writable] Warning: Variable y does not have any remaining equation to be solved in.",
        "  The original equations were:",
    ]


def test_omc_diagnostics_drops_parse_boilerplate():
    stderr = "Failed to parse file: /m/S.mo!\n\n[/m/S.mo:3:1-3:1:writable] Error: Missing token: SEMICOLON\n\nExecution failed!\n"
    assert _omc_diagnostics("", stderr) == "[/m/S.mo:3:1-3:1:writable] Error: Missing token: SEMICOLON"


def test_omc_diagnostics_drops_failed_to_load_package_follow_on():
    stderr = (
        "[/m/pkg/M.mo:3:1-3:1:writable] Error: Missing token: SEMICOLON\n"
        "Error: Failed to load package pkg () using MODELICAPATH /m.\n"
    )
    assert _omc_diagnostics("", stderr) == "[/m/pkg/M.mo:3:1-3:1:writable] Error: Missing token: SEMICOLON"


def test_omc_diagnostics_keeps_failed_to_load_package_when_it_is_the_only_error():
    stderr = "Error: Failed to load package pkg () using MODELICAPATH /m.\n"
    assert _omc_diagnostics("", stderr) == "Error: Failed to load package pkg () using MODELICAPATH /m."


def test_omc_diagnostics_falls_back_to_stdout():
    assert _omc_diagnostics("Error: boom\n", "Notification: x\n") == "Error: boom"


def test_omc_diagnostics_empty():
    assert _omc_diagnostics("", "") == ""


def test_translation_error_message_header(tmp_path):
    message = _translation_error_message(tmp_path / "M.mo", "", "Error: boom\n")
    assert message == f"Modelica translation failed for '{tmp_path / 'M.mo'}':\nError: boom"


def _build(tmp_path, name, source):
    path = tmp_path / f"{name}.mo"
    path.write_text(source)
    with pytest.raises(Exception) as exc:
        session_tools.SessionBuilder(path)
    return exc


def test_syntax_error_reports_missing_token(tmp_path):
    exc = _build(tmp_path, "Syntax", "model Syntax\n  Real x(start=1)\nequation\n  der(x) = -x;\nend Syntax;\n")
    assert issubclass(exc.type, pydelica.exception.OMParsingError)
    assert f"Modelica translation failed for '{tmp_path / 'Syntax.mo'}':" in str(exc.value)
    assert "Missing token: SEMICOLON" in str(exc.value)
    assert ":3:1-3:1:" in str(exc.value)


def test_translation_error_repr_is_the_readable_message(tmp_path):
    exc = _build(tmp_path, "Syntax", "model Syntax\n  Real x(start=1)\nequation\n  der(x) = -x;\nend Syntax;\n")
    assert repr(exc.value) == str(exc.value)


@dataclasses.dataclass
class _NoParameters:
    pass


def test_broken_package_through_hydra_reports_diagnostics_once_and_readably(tmp_path, caplog, capsys):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "package.mo").write_text("package pkg\nend pkg;\n")
    (package / "M.mo").write_text("within pkg;\nmodel M\n  Real x(start=1)\nequation\n  der(x) = -x;\nend M;\n")
    config = session_config.SimulationRun(
        model_name="pkg.M",
        session=session_config.Session(
            parameters=_NoParameters(),
            sim_configurations=session_config.Simulation(),
            model=package / "package.mo",
        ),
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(InstantiationException) as exc:
        sim_tools.simulate_run(config)

    message = str(exc.value)
    assert message.count("Missing token: SEMICOLON") == 1
    assert "\\n" not in message
    assert f"Modelica translation failed for '{package / 'package.mo'}':\n[" in message
    assert "Failed to load package" not in message
    assert "exit code" not in message
    assert isinstance(exc.value.__cause__, pydelica.exception.OMParsingError)
    assert isinstance(exc.value.__cause__.__cause__, pydelica.exception.OMParsingError)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert "Error processing file" not in capsys.readouterr().out


def test_under_determined_model_reports_counts_and_free_variable(tmp_path):
    exc = _build(tmp_path, "Imbalanced", "model Imbalanced\n  Real x(start=1);\n  Real y;\nequation\n  der(x) = -x;\nend Imbalanced;\n")
    assert issubclass(exc.type, pydelica.exception.OMExecutionError)
    msg = str(exc.value)
    assert "Too few equations, under-determined system. The model has 1 equation(s) and 2 variable(s)." in msg
    assert "Variable y does not have any remaining equation" in msg
    assert "Notification:" not in msg
    assert "Failed to execute compiled code" not in msg
    assert isinstance(exc.value.__cause__, pydelica.exception.OMExecutionError)


def test_over_determined_model_reports_too_many_equations(tmp_path):
    exc = _build(tmp_path, "Over", "model Over\n  Real x(start=1);\nequation\n  der(x) = -x;\n  x = 1;\nend Over;\n")
    assert "Too many equations, over-determined system" in str(exc.value)


def test_undeclared_variable_reports_name_and_scope(tmp_path):
    exc = _build(tmp_path, "Undeclared", "model Undeclared\n  Real x(start=1);\nequation\n  der(x) = -k*x;\nend Undeclared;\n")
    assert "Variable k not found in scope Undeclared" in str(exc.value)


def test_missing_library_class_is_named(tmp_path):
    exc = _build(tmp_path, "MissingLib", "model MissingLib\n  Modelica.Blocks.Sources.NoSuchBlock b;\nend MissingLib;\n")
    assert "NoSuchBlock" in str(exc.value)


def test_model_with_warnings_still_builds(tmp_path):
    path = tmp_path / "Warn.mo"
    path.write_text("model Warn\n  parameter Real p(start=1);\n  Real x(start=1);\nequation\n  der(x) = -p*x;\nend Warn;\n")
    session_tools.SessionBuilder(path)  # no exception


def test_c_compiler_error_in_external_function_is_reported(tmp_path):
    source = (
        "model BrokenC\n  function f\n    input Real x;\n    output Real y;\n"
        '  external "C" y = brokenF(x) annotation(Include="double brokenF(double x) { return x +; }");\n'
        "  end f;\n  Real x(start=1);\nequation\n  der(x) = f(x);\nend BrokenC;\n"
    )
    exc = _build(tmp_path, "BrokenC", source)
    assert exc.type is pydelica.exception.OMBuildError
    assert "error: expected expression" in str(exc.value)


def test_violated_assert_reports_message_and_time(tmp_path):
    path = tmp_path / "Assertion.mo"
    path.write_text(
        "model Assertion\n  Real x(start=1);\nequation\n  der(x) = 1;\n"
        '  assert(x < 1.5, "x exceeded limit");\nend Assertion;\n'
    )
    builder = session_tools.SessionBuilder(path)
    with pytest.raises(pydelica.exception.OMAssertionError) as exc:
        builder.session.simulate(model_name="Assertion")
    assert "x exceeded limit" in str(exc.value)
    assert "violated at time 0.5" in str(exc.value)
