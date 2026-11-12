"""A Modelica model exported as an FMU runs through ``sim_tools.simulate``, cached like a native build."""

import logging
import sys

import fmpy
import numpy as np
import pytest
from omegaconf import OmegaConf

from mtools import sim_tools
from mtools.errors import ConfigError
from mtools.hydra_registry import HydraZenRegistry
from mtools.internal.omc import workdir
from mtools.session_config import RunSettings
from tests.fmu.fmu_models import MODEL_PATH
from tests.fmu.helpers import build_messages, simulate_exported


@pytest.fixture
def fresh_work_dir(tmp_path, monkeypatch, caplog):
    """An empty work directory (no cached builds) for this test alone; INFO logs captured."""
    monkeypatch.setenv(workdir.WORK_DIR_VARIABLE, str(tmp_path / "work"))
    caplog.set_level(logging.INFO)


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
