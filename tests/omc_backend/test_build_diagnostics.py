"""Build failures and warnings at the backend interface: exception type and stable OMC phrases."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from mtools.errors import BuildError, CompileError, TranslationError
from mtools.internal.omc.build import build
from mtools.internal.omc.config import BuildConfig

# (model name, source, expected exception type, expected phrases)
BUILD_FAILURES = [
    (
        "Syntax",
        "model Syntax\n  Real x(start=1)\nequation\n  der(x) = -x;\nend Syntax;\n",
        TranslationError,
        ["Missing token: SEMICOLON", ":3:1-3:1:"],
    ),
    (
        "Imbalanced",
        "model Imbalanced\n  Real x(start=1);\n  Real y;\nequation\n  der(x) = -x;\nend Imbalanced;\n",
        TranslationError,
        [
            "Too few equations, under-determined system. The model has 1 equation(s) and 2 variable(s).",
            "Variable y does not have any remaining equation",
        ],
    ),
    (
        "Over",
        "model Over\n  Real x(start=1);\nequation\n  der(x) = -x;\n  x = 1;\nend Over;\n",
        TranslationError,
        ["Too many equations, over-determined system"],
    ),
    (
        "Undeclared",
        "model Undeclared\n  Real x(start=1);\nequation\n  der(x) = -k*x;\nend Undeclared;\n",
        TranslationError,
        ["Variable k not found in scope Undeclared"],
    ),
    (
        "MissingLib",
        "model MissingLib\n  Modelica.Blocks.Sources.NoSuchBlock b;\nend MissingLib;\n",
        TranslationError,
        ["NoSuchBlock"],
    ),
    (
        "BrokenC",
        "model BrokenC\n  function f\n    input Real x;\n    output Real y;\n"
        '  external "C" y = brokenF(x) annotation(Include="double brokenF(double x) { return x +; }");\n'
        "  end f;\n  Real x(start=1);\nequation\n  der(x) = f(x);\nend BrokenC;\n",
        CompileError,
        ["error: expected expression", "brokenF(double x)"],
    ),
]


def _failure(tmp_path: Path, name: str, source: str) -> BuildError:
    path = tmp_path / f"{name}.mo"
    path.write_text(source)
    with pytest.raises(BuildError) as raised:
        build(BuildConfig(model_path=path, model_name=name))
    return raised.value


@pytest.mark.parametrize(("name", "source", "error_type", "phrases"), BUILD_FAILURES, ids=[f[0] for f in BUILD_FAILURES])
def test_build_failure_has_type_and_stable_phrases(tmp_path, name, source, error_type, phrases):
    error = _failure(tmp_path, name, source)

    assert type(error) is error_type
    for phrase in phrases:
        assert phrase in str(error)
    assert "Notification: Automatically loaded" not in str(error)
    assert "Execution failed!" not in str(error)


def test_translation_error_header_names_model_and_absolute_source(tmp_path):
    error = _failure(tmp_path, *BUILD_FAILURES[0][:2])

    assert str(error).startswith(f"Modelica translation failed for 'Syntax' ({tmp_path / 'Syntax.mo'}):\n[")
    assert repr(error) == str(error)


def test_compile_error_shows_only_compiler_diagnostics(tmp_path):
    error = _failure(tmp_path, *BUILD_FAILURES[-1][:2])

    assert "clang " not in str(error)
    assert "make:" not in str(error)
    assert "Error building simulator" not in str(error)
    assert str(error).count("error: expected expression") == 1


def test_diagnostics_are_shown_once_and_raw_output_logged_at_debug_only(tmp_path, caplog):
    with caplog.at_level(logging.DEBUG, logger="mtools"):
        error = _failure(tmp_path, *BUILD_FAILURES[0][:2])

    assert str(error).count("Missing token: SEMICOLON") == 1
    assert [r for r in caplog.records if "Missing token" in r.getMessage()]
    assert all(r.levelno == logging.DEBUG for r in caplog.records if "Missing token" in r.getMessage())
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_broken_package_reports_the_parse_error_without_follow_on(tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "package.mo").write_text("package pkg\nend pkg;\n")
    (package / "M.mo").write_text("within pkg;\nmodel M\n  Real x(start=1)\nequation\n  der(x) = -x;\nend M;\n")

    with pytest.raises(TranslationError) as raised:
        build(BuildConfig(model_path=package / "package.mo", model_name="pkg.M"))

    assert str(raised.value).count("Missing token: SEMICOLON") == 1
    assert "Failed to load package" not in str(raised.value)
    assert f"({package / 'package.mo'}):" in str(raised.value)


WARNING_MODEL = "model Warn\n  parameter Real p(start=1);\n  Real x(start=1);\nequation\n  der(x) = -p*x;\nend Warn;\n"


def test_model_with_warnings_builds_and_logs_them_at_warning(tmp_path, caplog):
    path = tmp_path / "Warn.mo"
    path.write_text(WARNING_MODEL)

    with caplog.at_level(logging.DEBUG, logger="mtools"):
        build(BuildConfig(model_path=path, model_name="Warn"))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Warning:" in r.getMessage() for r in warnings)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_successful_build_logs_notifications_at_debug(tmp_path, caplog):
    path = tmp_path / "Note.mo"
    path.write_text("model Note\n  Modelica.Blocks.Sources.Constant c(k=1);\nend Note;\n")

    with caplog.at_level(logging.DEBUG, logger="mtools"):
        build(BuildConfig(model_path=path, model_name="Note"))

    notes = [r for r in caplog.records if r.getMessage().startswith("OMC notifications for 'Note'")]
    assert notes
    assert "Notification: Automatically loaded package" in notes[0].getMessage()
    assert all(r.levelno == logging.DEBUG for r in notes)
