"""A model exported as an FMU from the Cpp target: Model Exchange only, with a warning."""

import numpy as np
import pytest

from mtools.errors import ConfigError
from tests.fmu.helpers import build_messages, simulate_exported


def test_cpp_export_warns_once_and_runs(caplog):
    result = simulate_exported("FmuTests.Decay", target="Cpp")["FmuTests.Decay"]
    warnings = [
        record
        for record in caplog.records
        if record.getMessage().startswith("Exporting 'FmuTests.Decay' from the Cpp target")
    ]
    assert len(warnings) == 1
    # Without the event-indicator guard (see indicator_guard.py) the output varies per run.
    np.testing.assert_allclose(result["x"], np.exp(-result["time"]), rtol=1e-4, atol=1e-6)


def test_cpp_export_runs_are_reproducible(fresh_work_dir):
    # The export is cached after the first run, so each further run is one child start.
    results = [simulate_exported("FmuTests.Decay", target="Cpp")["FmuTests.Decay"] for _ in range(8)]
    assert {len(result) for result in results} == {len(results[0])}
    for result in results:
        np.testing.assert_allclose(result["x"], np.exp(-result["time"]), rtol=1e-4, atol=1e-6)


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
