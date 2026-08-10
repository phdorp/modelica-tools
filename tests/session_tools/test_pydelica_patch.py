from __future__ import annotations

import logging
import os

import pytest
import pydelica.compiler

import mtools.internal.pydelica_patch as pydelica_patch
import mtools.internal.session_tools as session_tools
from mtools.internal.pydelica_patch import _compile_without_source_copy, install_pydelica_patch

_ORIGINAL_COMPILE = pydelica.compiler.Compiler.compile


@pytest.fixture(autouse=True)
def _reset_patch_state(monkeypatch):
    monkeypatch.setattr(pydelica_patch, "_PATCH_INSTALLED", False)
    monkeypatch.setattr(pydelica.compiler.Compiler, "compile", _ORIGINAL_COMPILE)


def test_install_pydelica_patch_replaces_compiler_compile():
    install_pydelica_patch()

    assert pydelica.compiler.Compiler.compile is _compile_without_source_copy


def test_install_pydelica_patch_is_idempotent():
    install_pydelica_patch()
    first_install = pydelica.compiler.Compiler.compile

    install_pydelica_patch()

    assert pydelica.compiler.Compiler.compile is first_install


def test_install_pydelica_patch_raises_on_version_mismatch(monkeypatch):
    monkeypatch.setattr(
        "mtools.internal.pydelica_patch._pydelica_version",
        lambda: "0.7.0",
    )

    with pytest.raises(RuntimeError, match="pydelica 0.7.0"):
        install_pydelica_patch()

    assert pydelica.compiler.Compiler.compile is _ORIGINAL_COMPILE


def test_install_pydelica_patch_succeeds_on_supported_version(monkeypatch):
    monkeypatch.setattr(
        "mtools.internal.pydelica_patch._pydelica_version",
        lambda: "0.6.3",
    )

    install_pydelica_patch()

    assert pydelica.compiler.Compiler.compile is _compile_without_source_copy


def test_compile_without_source_copy_compiles_in_place_and_stages_c_sources(
    monkeypatch, tmp_path
):
    model = tmp_path / "model.mo"
    model.write_text("model Example\nend Example;\n")
    include = tmp_path / "Resources" / "Include"
    include.mkdir(parents=True)
    (include / "ext.c").write_text("/* external C */")

    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "model.makefile").write_text("all:\n")

    class _FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    compile_calls: list[list[str]] = []
    run_count = {"n": 0}

    def fake_run(args, **kwargs):
        run_count["n"] += 1
        if run_count["n"] == 1:
            compile_calls.append(list(args))
        return _FakeResult()

    monkeypatch.setattr(pydelica_patch.tempfile, "mkdtemp", lambda: str(build_dir))
    monkeypatch.setattr(pydelica_patch.subprocess, "run", fake_run)
    monkeypatch.setattr(pydelica_patch.shutil, "which", lambda _: "make")

    class _FakeCompiler:
        _logger = logging.getLogger("test.pydelica_patch")
        _omc_binary = "omc"
        _omc_flags: dict[str, str | None] = {}
        _environment = dict(os.environ)
        _binary_dirs: list[str] = []

    compiler = _FakeCompiler()
    result = _compile_without_source_copy(compiler, model)

    assert result == build_dir
    assert compiler._binary_dirs == [str(build_dir)]
    assert compile_calls[0][:3] == ["omc", "-s", str(model)]
    assert (build_dir / "Resources" / "Include" / "ext.c").read_text() == "/* external C */"
    assert (include / "ext.c").read_text() == "/* external C */"


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
