"""A model exported as an FMU from the Cpp target: Model Exchange only, with a warning."""

import numpy as np
import pytest

from mtools.errors import ConfigError
from tests.fmu.helpers import simulate_exported


def test_cpp_export_warns_once_and_runs(caplog):
    result = simulate_exported("FmuTests.Decay", target="Cpp")["FmuTests.Decay"]
    warnings = [
        record
        for record in caplog.records
        if record.getMessage().startswith("Exporting 'FmuTests.Decay' from the Cpp target")
    ]
    assert len(warnings) == 1
    # The Cpp FMU's broken time events sometimes shrink the steps (13237 rows, error up to 8e-4).
    np.testing.assert_allclose(result["x"], np.exp(-result["time"]), rtol=2e-3, atol=1e-6)


def test_cpp_co_simulation_is_a_config_error(caplog):
    with pytest.raises(ConfigError) as error:
        simulate_exported("FmuTests.Decay", target="Cpp", fmu_type="cs")
    assert "build.fmu.fmu_type: Co-Simulation export isn't supported on the Cpp target" in error.value.diagnostics
    assert "Built" not in caplog.text
