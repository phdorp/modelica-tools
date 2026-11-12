"""Build-time and protected parameters of an exported FMU: variant FMUs, as for native builds (ADR 0001)."""

import pytest

from mtools.errors import ConfigError
from tests.fmu.helpers import simulate_exported

MODEL = "FmuTests.BuildTime"


@pytest.mark.parametrize("emit_protected", [False, True])
def test_protected_parameter_is_a_config_error_before_any_variant(caplog, emit_protected):
    with pytest.raises(ConfigError) as error:
        simulate_exported(MODEL, parameters={"hp": 1.0}, emit_protected=emit_protected)
    assert "settings.parameters.hp: 'FmuTests.BuildTime' parameter 'hp' is protected" in error.value.diagnostics
    assert "Building a variant" not in caplog.text
