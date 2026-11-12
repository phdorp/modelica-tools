"""A model exported as an FMU from the Cpp target: Model Exchange only, with a warning."""

import logging

import numpy as np
import pytest

from mtools.errors import ConfigError
from mtools.internal.omc import workdir
from tests.fmu.helpers import build_messages, simulate_exported


@pytest.fixture
def fresh_work_dir(tmp_path, monkeypatch, caplog):
    """An empty work directory (no cached builds) for this test alone; INFO logs captured."""
    monkeypatch.setenv(workdir.WORK_DIR_VARIABLE, str(tmp_path / "work"))
    caplog.set_level(logging.INFO)


def test_cpp_export_warns_once_and_runs(caplog):
    result = simulate_exported("FmuTests.Decay", target="Cpp")["FmuTests.Decay"]
    warnings = [
        record
        for record in caplog.records
        if record.getMessage().startswith("Exporting 'FmuTests.Decay' from the Cpp target")
    ]
    assert len(warnings) == 1
    # The Cpp FMU's output grid is nondeterministic across runs of the same FMU and settings:
    # 109 rows (max relative error 4.2e-6) or about 13238 rows (max relative error 7.75e-4).
    # The tolerance covers the worse mode.
    np.testing.assert_allclose(result["x"], np.exp(-result["time"]), rtol=2e-3, atol=1e-6)


def test_cpp_co_simulation_is_a_config_error(caplog):
    with pytest.raises(ConfigError) as error:
        simulate_exported("FmuTests.Decay", target="Cpp", fmu_type="cs")
    assert "build.fmu.fmu_type: Co-Simulation export isn't supported on the Cpp target" in error.value.diagnostics
    assert "Built" not in caplog.text


def test_cpp_export_warns_on_every_call_built_or_reused(fresh_work_dir, caplog):
    simulate_exported("FmuTests.Decay", target="Cpp")
    simulate_exported("FmuTests.Decay", target="Cpp")

    assert [message.split()[0] for message in build_messages(caplog)] == ["Built", "Reused"]
    warnings = [r for r in caplog.records if r.getMessage().startswith("Exporting 'FmuTests.Decay' from the Cpp target")]
    assert len(warnings) == 2


def test_cpp_export_accepts_euler():
    # settings.solver is the FMPy solver for an exported FMU, whatever the target; the Cpp
    # output grid is nondeterministic, so only the run's success is asserted.
    result = simulate_exported("FmuTests.Decay", target="Cpp", solver="euler")["FmuTests.Decay"]
    assert len(result) > 0
