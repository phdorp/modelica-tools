from __future__ import annotations

import pytest

from mtools.internal.omc.diagnostics import (compiler_warnings, filter_compile,
                                             filter_translation, notifications,
                                             translation_warnings)

IMBALANCED = (
    "Notification: Automatically loaded package Complex 4.1.0 due to uses annotation from Modelica.\n"
    "Error: Too few equations, under-determined system. The model has 1 equation(s) and 2 variable(s).\n"
    "[/m/Imbalanced.mo:3:3-3:9:writable] Warning: Variable y does not have any remaining equation to be solved in.\n"
    "  The original equations were:\n"
    "\n"
    "Execution failed!\n"
)


def test_translation_keeps_errors_warnings_and_continuations_in_order():
    assert filter_translation(IMBALANCED).splitlines() == [
        "Error: Too few equations, under-determined system. The model has 1 equation(s) and 2 variable(s).",
        "[/m/Imbalanced.mo:3:3-3:9:writable] Warning: Variable y does not have any remaining equation to be solved in.",
        "  The original equations were:",
    ]


def test_translation_drops_parse_boilerplate():
    text = "Failed to parse file: /m/S.mo!\n\n[/m/S.mo:3:1-3:1:writable] Error: Missing token: SEMICOLON\n\nExecution failed!\n"
    assert filter_translation(text) == "[/m/S.mo:3:1-3:1:writable] Error: Missing token: SEMICOLON"


def test_translation_drops_failed_to_load_package_follow_on():
    text = (
        "[/m/pkg/M.mo:3:1-3:1:writable] Error: Missing token: SEMICOLON\n"
        "Error: Failed to load package pkg () using MODELICAPATH /m.\n"
    )
    assert filter_translation(text) == "[/m/pkg/M.mo:3:1-3:1:writable] Error: Missing token: SEMICOLON"


def test_translation_keeps_failed_to_load_package_when_it_is_the_only_error():
    text = "Error: Failed to load package pkg () using MODELICAPATH /m.\n"
    assert filter_translation(text) == "Error: Failed to load package pkg () using MODELICAPATH /m."


def test_translation_keeps_located_notification_that_explains_an_error():
    text = "[/m/A.mo:7:11-7:16:writable] Notification: From here:\nError: Non-array modification.\n"
    assert filter_translation(text) == text.strip()


def test_translation_drops_continuations_of_a_dropped_notification():
    text = "Notification: Automatically loaded\n  package X.\nError: boom\n"
    assert filter_translation(text) == "Error: boom"


def test_translation_empty():
    assert filter_translation("") == ""


def test_warnings_and_notifications_are_separated():
    assert translation_warnings(IMBALANCED).splitlines()[0].endswith("to be solved in.")
    assert "Error:" not in translation_warnings(IMBALANCED)
    assert notifications(IMBALANCED).startswith("Notification: Automatically loaded package")
    assert "Warning" not in notifications(IMBALANCED)


COMPILE_LOG = (
    'clang  -Os -DOM_HAVE_PTHREADS -fPIC -c -o model.o model.c\n'
    "In file included from model_functions.c:7:\n"
    "./model_includes.h:7:38: error: expected expression\n"
    "    7 | double brokenF(double x) { return x +; }\n"
    "      |                                      ^\n"
    "1 error generated.\n"
    "make: *** [<builtin>: model_functions.o] Error 1\n"
    "make: *** Waiting for unfinished jobs....\n"
)


def test_compile_keeps_diagnostic_with_source_and_caret_lines():
    assert filter_compile(COMPILE_LOG).splitlines() == [
        "./model_includes.h:7:38: error: expected expression",
        "    7 | double brokenF(double x) { return x +; }",
        "      |                                      ^",
    ]


def test_compile_keeps_notes_and_warnings():
    log = "a.c:1:1: warning: unused\na.c:2:2: note: declared here\nmake: *** Error 1\n"
    assert filter_compile(log).splitlines() == ["a.c:1:1: warning: unused", "a.c:2:2: note: declared here"]


def test_compile_keeps_linker_lines():
    log = (
        "clang -o model model.o\n"
        "/usr/bin/ld: model.o: in function `main': model.c:(.text+0x1): undefined reference to `foo'\n"
        "collect2: error: ld returned 1 exit status\n"
        "make: *** [model] Error 1\n"
    )
    kept = filter_compile(log).splitlines()
    assert len(kept) == 2
    assert "undefined reference to `foo'" in kept[0]
    assert kept[1].startswith("collect2:")


def test_compile_keeps_undefined_reference_line_without_linker_prefix():
    log = "model.c:(.text+0x1): undefined reference to `bar'\nmake: *** [model] Error 1\n"
    assert filter_compile(log) == "model.c:(.text+0x1): undefined reference to `bar'"


def test_compile_keeps_ld_line_without_undefined_reference():
    log = "/usr/bin/ld: cannot find -lfoo\nmake: *** [model] Error 1\n"
    assert filter_compile(log) == "/usr/bin/ld: cannot find -lfoo"


def test_compile_drops_command_lines_and_make_chatter_around_diagnostics():
    kept = filter_compile(COMPILE_LOG)
    assert "clang" not in kept
    assert "make:" not in kept
    assert "generated." not in kept
    assert "In file included" not in kept


def test_compile_falls_back_to_the_whole_log_when_nothing_matches():
    assert filter_compile("make: *** No rule to make target.\n") == "make: *** No rule to make target."


@pytest.mark.parametrize("log", ["", "\n"])
def test_compile_empty(log):
    assert filter_compile(log) == ""


def test_compiler_warnings_are_extracted():
    log = "a.c:1:1: warning: unused\n    1 | int x;\n      | ^\na.c:2:2: error: bad\n"
    assert compiler_warnings(log).splitlines() == ["a.c:1:1: warning: unused", "    1 | int x;", "      | ^"]
