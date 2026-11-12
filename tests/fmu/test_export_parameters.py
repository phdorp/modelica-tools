"""Build-time and protected parameters of an exported FMU: variant FMUs, as for native builds (ADR 0001)."""

import pytest

from mtools.errors import ConfigError
from tests.fmu.helpers import build_messages, simulate_exported

MODEL = "FmuTests.BuildTime"


def test_array_size_sweep_exports_a_cached_variant(fresh_work_dir, caplog):
    for _ in range(2):
        result = simulate_exported(MODEL, parameters={"n": 3})[MODEL]
    assert [c for c in result.columns if c.startswith("y[")] == ["y[1]", "y[2]", "y[3]"]
    assert "Building a variant of 'FmuTests.BuildTime' because 'n' is fixed at build time" in caplog.text
    assert [m.split(" ")[0] for m in build_messages(caplog)] == ["Built", "Built", "Reused", "Reused"]


@pytest.mark.parametrize("emit_protected", [False, True])
def test_protected_parameter_is_a_config_error_before_any_variant(caplog, emit_protected):
    with pytest.raises(ConfigError) as error:
        simulate_exported(MODEL, parameters={"hp": 1.0}, emit_protected=emit_protected)
    assert "settings.parameters.hp: 'FmuTests.BuildTime' parameter 'hp' is protected" in error.value.diagnostics
    assert "Building a variant" not in caplog.text
