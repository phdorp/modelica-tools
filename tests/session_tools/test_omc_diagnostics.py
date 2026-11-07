from __future__ import annotations

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


def test_omc_diagnostics_falls_back_to_stdout():
    assert _omc_diagnostics("Error: boom\n", "Notification: x\n") == "Error: boom"


def test_omc_diagnostics_empty():
    assert _omc_diagnostics("", "") == ""


def test_translation_error_message_header(tmp_path):
    message = _translation_error_message(tmp_path / "M.mo", 1, "", "Error: boom\n")
    assert message == f"OMC failed to translate '{tmp_path / 'M.mo'}' (exit code 1):\nError: boom"
