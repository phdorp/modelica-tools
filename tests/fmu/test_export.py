"""A Modelica model exported as an FMU runs through ``sim_tools.simulate``, cached like a native build."""

import logging
import sys
from typing import Any

import fmpy
import numpy as np
import pytest
from omegaconf import OmegaConf

from mtools import sim_tools
from mtools.errors import CompileError, ConfigError, TranslationError
from mtools.hydra_registry import HydraZenRegistry
from mtools.internal.omc import workdir
from mtools.session_config import FmuExport, RunSettings
from tests.fmu.fmu_models import MODEL_PATH
from tests.fmu.helpers import build_messages, simulate_exported


def test_exported_fmu_runs_and_matches_the_analytic_solution(exported_fmu):
    result = simulate_exported("FmuTests.Decay")["FmuTests.Decay"]

    kept = {"x", "der(x)", "count", "positive"}  # k and x0 are parameters
    description = fmpy.read_model_description(exported_fmu("FmuTests.Decay"))
    order = [variable.name for variable in description.modelVariables if variable.name in kept]
    assert list(result.columns) == ["time", *order]
    assert result[["x", "count", "positive"]].dtypes.tolist() == ["float64", "int64", "bool"]
    np.testing.assert_allclose(result["x"], np.exp(-result["time"]), rtol=1e-4)


def test_missing_fmpy_raises_before_export(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setitem(sys.modules, "fmpy", None)

    with pytest.raises(ImportError, match=r"^FMU runs need FMPy: install modelica-tools\[fmu\]$"):
        simulate_exported("FmuTests.Sampled")

    assert build_messages(caplog) == []


def test_unknown_fmu_type_is_a_config_error(caplog):
    caplog.set_level(logging.INFO)

    with pytest.raises(ConfigError, match="^Invalid config for 'FmuTests.Decay':\n") as raised:
        simulate_exported("FmuTests.Decay", fmu_type="both")

    assert raised.value.diagnostics == "build.fmu.fmu_type: expected 'me' or 'cs', got 'both'"
    assert build_messages(caplog) == []


def test_second_run_reuses_the_export_and_other_type_exports_anew(fresh_work_dir, caplog):
    simulate_exported("FmuTests.Decay")
    simulate_exported("FmuTests.Decay")
    simulate_exported("FmuTests.Decay", fmu_type="cs")

    assert [message.split(" ")[0] for message in build_messages(caplog)] == ["Built", "Reused", "Built"]


def test_native_and_fmu_builds_of_one_model_are_separate(fresh_work_dir, caplog):
    native = HydraZenRegistry().create_run(
        model_name="FmuTests.Decay", model_path=MODEL_PATH, settings=RunSettings(parameters={})
    )
    sim_tools.simulate(OmegaConf.structured(native))
    simulate_exported("FmuTests.Decay")

    assert [message.split(" ")[0] for message in build_messages(caplog)] == ["Built", "Built"]


def test_no_cache_exports_into_a_throwaway_directory(fresh_work_dir, monkeypatch, caplog):
    monkeypatch.setenv(workdir.NO_CACHE_VARIABLE, "1")

    simulate_exported("FmuTests.Decay")

    [message] = build_messages(caplog)
    assert message.startswith("Built 'FmuTests.Decay' without cache in ")
    assert list(workdir.builds_dir().iterdir()) == []
    assert list(workdir.runs_dir().iterdir()) == []  # the export and the run directory are deleted


def _simulate_source(tmp_path, model: str, source: str) -> None:
    """Export ``model`` from ``source``, written into ``tmp_path``, and run it."""
    path = tmp_path / f"{model}.mo"
    path.write_text(source)
    no_parameters: Any = {}
    run = HydraZenRegistry().create_run(
        model_name=model, model_path=path, settings=RunSettings(parameters=no_parameters), fmu=FmuExport()
    )
    sim_tools.simulate(OmegaConf.structured(run))


def test_translation_failure_is_a_translation_error(tmp_path):
    source = "model Broken Real x; equation der(x) = undefinedThing; end Broken;\n"

    with pytest.raises(TranslationError, match="^Modelica translation failed for 'Broken'") as raised:
        _simulate_source(tmp_path, "Broken", source)

    assert raised.value.diagnostics.count("Variable undefinedThing not found in scope Broken") == 1


def test_compile_failure_is_a_compile_error(tmp_path):
    source = (
        "model CBuild\n  function f\n    input Real x;\n    output Real y;\n"
        '    external "C" y = missingF(x) annotation(Include="#include \\"no_such_header.h\\"");\n'
        "  end f;\n  Real v = f(time);\nend CBuild;\n"
    )

    with pytest.raises(CompileError, match="^Modelica build failed for 'CBuild'") as raised:
        _simulate_source(tmp_path, "CBuild", source)

    assert "no_such_header.h" in raised.value.diagnostics


def test_export_logs_translation_warnings_once(fresh_work_dir, caplog):
    simulate_exported("FmuTests.Warns")

    warnings = [record.getMessage() for record in caplog.records if "reported warnings" in record.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].count("The initial conditions are not fully specified") == 1
