from __future__ import annotations

import pydelica.compiler

import mtools.internal.session_tools as session_tools
from mtools.internal.pydelica_patch import _compile_without_source_copy, install_pydelica_patch


def test_install_pydelica_patch_replaces_compiler_compile(monkeypatch):
    original_compile = pydelica.compiler.Compiler.compile

    monkeypatch.setattr(pydelica.compiler.Compiler, "compile", original_compile, raising=False)

    install_pydelica_patch()

    assert pydelica.compiler.Compiler.compile is _compile_without_source_copy


def test_install_pydelica_patch_is_idempotent():
    install_pydelica_patch()
    first_install = pydelica.compiler.Compiler.compile

    install_pydelica_patch()

    assert pydelica.compiler.Compiler.compile is first_install


def test_session_builder_installs_patch_before_session_creation(monkeypatch, tmp_path):
    calls: list[str] = []

    def fake_install() -> None:
        calls.append("installed")

    class DummySession:
        def __init__(self, log_level):
            calls.append(f"session:{log_level}")

        def use_libraries(self, libraries):
            calls.append("use_libraries")

        def build_model(self, source_file, **build_options):
            calls.append(f"build_model:{source_file}")

    monkeypatch.setattr(session_tools, "install_pydelica_patch", fake_install)
    monkeypatch.setattr(session_tools.pydelica, "Session", DummySession)

    model_path = tmp_path / "model.mo"
    model_path.write_text("model Example\nend Example;\n")

    session_tools.SessionBuilder(model_path)

    assert calls[0] == "installed"
    assert calls[1] == "session:20"
    assert calls[2] == f"build_model:{model_path}"