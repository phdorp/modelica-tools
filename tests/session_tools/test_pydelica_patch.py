from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ElementTree

import pydelica
import pydelica.compiler
import pydelica.options.simulation
import pytest

import mtools.internal.pydelica_patch as pydelica_patch
import mtools.internal.session_tools as session_tools
from mtools.internal.pydelica_patch import (
    _compile_without_source_copy, _cpp_default_simulation_options,
    _cpp_variable_filter, _CppRuntimeOptions, _inject_cpp_default_experiment,
    _is_cpp_target, _patched_simulate,
    _simulation_options_init_with_cpp_fallback, install_pydelica_patch)

_ORIGINAL_COMPILE = pydelica.compiler.Compiler.compile
_ORIGINAL_SIMULATE = pydelica.Session.simulate
_ORIGINAL_SIMULATION_OPTIONS_INIT = pydelica.options.simulation.SimulationOptions.__init__


@pytest.fixture(autouse=True)
def _reset_patch_state(monkeypatch):
    monkeypatch.setattr(pydelica_patch, "_PATCH_INSTALLED", False)
    monkeypatch.setattr(pydelica_patch, "_ORIGINAL_SIMULATE", None)
    monkeypatch.setattr(pydelica_patch, "_ORIGINAL_SIMULATION_OPTIONS_INIT", None)
    monkeypatch.setattr(pydelica.compiler.Compiler, "compile", _ORIGINAL_COMPILE)
    monkeypatch.setattr(pydelica.Session, "simulate", _ORIGINAL_SIMULATE)
    monkeypatch.setattr(
        pydelica.options.simulation.SimulationOptions,
        "__init__",
        _ORIGINAL_SIMULATION_OPTIONS_INIT,
    )


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
        _runtime_opts: dict = {}

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
    assert calls[1] == f"session:{logging.INFO}"
    assert calls[2] == f"build_model:{model_path}"


def test_install_pydelica_patch_replaces_simulate_and_simulation_options_init():
    install_pydelica_patch()

    assert pydelica.Session.simulate is _patched_simulate
    assert (
        pydelica.options.simulation.SimulationOptions.__init__
        is _simulation_options_init_with_cpp_fallback
    )


def test_is_cpp_target_recognises_simcode_target_flags():
    assert _is_cpp_target({"--simCodeTarget": "Cpp"})
    assert _is_cpp_target({"-simCodeTarget": "cpp"})
    assert not _is_cpp_target({"--simCodeTarget": "C"})
    assert not _is_cpp_target({})


def test_cpp_default_simulation_options_read_shell_wrapper(tmp_path):
    script = tmp_path / "Model.sh"
    script.write_text(
        "#!/bin/sh\nexec ./Model -S 0.5 -E 12 -H 0.01 -G 1200 -P csv "
        "-T 1e-8 -I dassl -R /runtime/ -M /build/ -r result.mat  $*"
    )

    options = _cpp_default_simulation_options(script)

    assert options["startTime"] == "0.5"
    assert options["stopTime"] == "12"
    assert options["stepSize"] == "0.01"
    assert options["numberOfIntervals"] == "1200"
    assert options["outputFormat"] == "csv"
    assert options["tolerance"] == "1e-8"
    assert options["solver"] == "dassl"


def test_inject_cpp_default_experiment_adds_missing_element(tmp_path):
    xml_file = tmp_path / "Model_init.xml"
    xml_file.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ModelDescription modelName="Model"><ModelVariables/></ModelDescription>'
    )
    (tmp_path / "Model.sh").write_text("exec ./Model -S 0 -E 4 -P csv -T 1e-7 -I dassl\n")

    _inject_cpp_default_experiment(xml_file)
    _inject_cpp_default_experiment(xml_file)

    tree = ElementTree.parse(xml_file)
    experiments = tree.getroot().findall("DefaultExperiment")
    assert len(experiments) == 1
    assert experiments[0].attrib["stopTime"] == "4"
    assert experiments[0].attrib["outputFormat"] == "csv"


def test_simulation_options_init_adds_defaults_for_cpp_xml(tmp_path):
    install_pydelica_patch()
    xml_file = tmp_path / "Model_init.xml"
    xml_file.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ModelDescription modelName="Model"><ModelVariables/></ModelDescription>'
    )
    (tmp_path / "Model.sh").write_text("exec ./Model -S 0 -E 4 -P csv -T 1e-7 -I dassl\n")

    options = pydelica.options.simulation.SimulationOptions(xml_file)

    assert options["startTime"] == "0"
    assert options["stopTime"] == "4"
    options.set_option("stopTime", 9)
    assert options["stopTime"] == 9


def test_cpp_runtime_options_translate_simulation_options():
    simulation_options = {
        "startTime": 1,
        "stopTime": 5,
        "stepSize": 0.01,
        "numberOfIntervals": 400,
        "tolerance": 1e-8,
        "solver": "dassl",
        "variableFilter": "state*",
        "outputFormat": "csv",
    }

    class _RuntimeOptions:
        emit_protected = True

    runtime_options = _CppRuntimeOptions(
        "pkg.Model", simulation_options, _RuntimeOptions()
    )

    assert runtime_options.assemble_args() == [
        "-S", "1",
        "-E", "5",
        "-H", "0.01",
        "-G", "400",
        "-T", "1e-08",
        "-I", "dassl",
        "-B", "state*",
        "-P", "csv",
        "-F", "pkg_Model_res.csv",
        "-U", "protected",
    ]
    assert runtime_options.emit_protected is True


def test_cpp_variable_filter_translates_default_wildcard():
    assert _cpp_variable_filter("*") == ".*"
    assert _cpp_variable_filter("") == ".*"
    assert _cpp_variable_filter("state.*") == "state.*"
