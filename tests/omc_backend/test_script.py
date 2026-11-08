"""Build-script generation and parsing of the script's output, without OMC."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtools.internal.omc.config import BuildConfig, Library
from mtools.internal.omc.script import (Experiment, LoadedLibrary, Stage,
                                        build_script, parse_output)


def _config(**overrides) -> BuildConfig:
    defaults: dict = dict(model_path=Path("/src/Pkg/package.mo"), model_name="Pkg.M")
    return BuildConfig(**(defaults | overrides))


def _position(script: str, text: str) -> int:
    assert text in script, f"{text!r} not in script"
    return script.index(text)


def test_stages_run_in_spec_order():
    script = build_script(
        _config(
            extra_sources=[Path("/src/Base/package.mo")],
            libraries=[Library("Modelica", "4.0.0"), Library("MyLib", directory=Path("/libs"))],
        ),
        "model",
    )

    positions = [
        _position(script, "setCommandLineOptions("),
        _position(script, "setModelicaPath("),
        _position(script, "loadModel(Modelica"),
        _position(script, "loadModel(MyLib"),
        _position(script, 'loadFile("/src/Base/package.mo")'),
        _position(script, 'loadFile("/src/Pkg/package.mo")'),
        _position(script, "getLoadedLibraries()"),
        _position(script, "getSimulationOptions(Pkg.M)"),
        _position(script, "buildModel(Pkg.M"),
    ]
    assert positions == sorted(positions)


def test_options_set_target_quiet_mode_and_user_flags():
    script = build_script(_config(omc_flags={"-d": "nogen", "--showErrorMessages": None}), "model")

    assert 'setCommandLineOptions("--simCodeTarget=C -q -d=nogen --showErrorMessages")' in script


def test_versioned_library_is_pinned_exactly_and_unversioned_uses_the_default():
    script = build_script(_config(libraries=[Library("Modelica", "4.0.0"), Library("Other")]), "model")

    assert 'loadModel(Modelica, {"4.0.0"}, requireExactVersion=true)' in script
    assert "loadModel(Other)" in script


def test_library_directories_are_prepended_to_the_library_path():
    script = build_script(
        _config(libraries=[Library("A", directory=Path("/libs/a")), Library("B", directory=Path("/libs/b"))]),
        "model",
    )

    assert 'setModelicaPath("/libs/a:/libs/b:" + getModelicaPath())' in script


def test_without_library_directories_the_library_path_is_untouched():
    assert "setModelicaPath(" not in build_script(_config(), "model")


def test_build_uses_the_internal_file_name_prefix():
    assert 'buildModel(Pkg.M, fileNamePrefix="model")' in build_script(_config(), "model")


def test_paths_are_escaped_as_modelica_strings():
    script = build_script(_config(model_path=Path('/src/we"ird\\dir/M.mo')), "model")

    assert 'loadFile("/src/we\\"ird\\\\dir/M.mo")' in script


def test_every_failing_stage_exits_with_its_own_code():
    script = build_script(
        _config(extra_sources=[Path("/src/Base.mo")], libraries=[Library("L", "1.0", Path("/libs"))]), "model"
    )

    for stage in (
        Stage.OPTIONS,
        Stage.LIBRARY_PATH,
        Stage.LOAD_LIBRARIES,
        Stage.LOAD_SOURCES,
        Stage.TRANSLATE,
        Stage.COMPILE,
    ):
        assert f"exit({int(stage)})" in script


CAPTURED_SUCCESS = """\
true
@@mtools:begin errors 11

@@mtools:end

true
@@mtools:begin errors 14

@@mtools:end

@@mtools:begin data loaded_libraries
{{"Modelica", "/root/.openmodelica/libraries/Modelica 4.1.0"}, {"M", "/tmp/src"}}
@@mtools:end
@@mtools:begin errors 15

@@mtools:end

@@mtools:begin data simulation_options
(0.1, 0.3333333333333333, 1.234567890123e-7, 18, 0.01296296296296296)
@@mtools:end
@@mtools:begin data solver
"euler"
@@mtools:end
@@mtools:begin errors 16

@@mtools:end

{"/tmp/build/model", "model_init.xml"}
@@mtools:begin errors 17
Warning: The initial conditions are not fully specified.
@@mtools:end
"""


def test_parse_reads_the_experiment_annotation():
    output = parse_output(CAPTURED_SUCCESS)

    assert output.experiment == Experiment(
        start_time=0.1,
        stop_time=0.3333333333333333,
        interval=0.01296296296296296,
        tolerance=1.234567890123e-7,
        solver="euler",
    )


def test_parse_defaults_the_solver_to_dassl_without_a_solver_annotation():
    output = parse_output(CAPTURED_SUCCESS.replace('"euler"\n', "\n"))

    assert output.experiment is not None
    assert output.experiment.solver == "dassl"


def test_parse_reads_the_loaded_libraries():
    output = parse_output(CAPTURED_SUCCESS)

    assert output.loaded_libraries == (
        LoadedLibrary("Modelica", Path("/root/.openmodelica/libraries/Modelica 4.1.0")),
        LoadedLibrary("M", Path("/tmp/src")),
    )


def test_parse_collects_each_stage_error_string():
    output = parse_output(CAPTURED_SUCCESS)

    assert output.diagnostics[Stage.TRANSLATE] == "Warning: The initial conditions are not fully specified."
    assert output.diagnostics[Stage.OPTIONS] == ""


def test_parse_tolerates_output_of_a_script_that_stopped_early():
    output = parse_output(
        "false\n@@mtools:begin errors 14\nError: Failed to load file /x.mo: file does not exist.\n@@mtools:end\n"
    )

    assert output.diagnostics == {Stage.LOAD_SOURCES: "Error: Failed to load file /x.mo: file does not exist."}
    assert output.experiment is None
    assert output.loaded_libraries == ()


@pytest.mark.parametrize("target", ["C", "Cpp"])
def test_target_is_passed_to_the_code_generator(target):
    assert f"--simCodeTarget={target}" in build_script(_config(target=target), "model")
