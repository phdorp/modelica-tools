import pandas as pd
import pytest

from mtools import errors


@pytest.mark.parametrize(
    ("error_type", "parents"),
    [
        (errors.ConfigError, (errors.MtoolsError, ValueError)),
        (errors.BuildError, (errors.MtoolsError,)),
        (errors.TranslationError, (errors.BuildError,)),
        (errors.CompileError, (errors.BuildError,)),
        (errors.SimulationError, (errors.MtoolsError,)),
        (errors.SimulationTimeout, (errors.SimulationError,)),
    ],
)
def test_exceptions_follow_the_spec_hierarchy(error_type, parents):
    for parent in parents:
        assert issubclass(error_type, parent)


def test_message_is_the_header_followed_by_the_diagnostics():
    error = errors.TranslationError(
        "Modelica translation failed for 'M' (/abs/M.mo):",
        model_name="M",
        diagnostics="[/abs/M.mo:2:3] Error: Type mismatch",
    )

    assert str(error) == "Modelica translation failed for 'M' (/abs/M.mo):\n[/abs/M.mo:2:3] Error: Type mismatch"
    assert error.model_name == "M"
    assert error.diagnostics == "[/abs/M.mo:2:3] Error: Type mismatch"


def test_repr_equals_str():
    error = errors.CompileError("Modelica build failed for 'M' (/abs/M.mo):", model_name="M", diagnostics="ld: oops")

    assert repr(error) == str(error)


def test_simulation_error_carries_a_partial_result():
    partial = pd.DataFrame({"time": [0.0, 0.1]})

    error = errors.SimulationTimeout(
        "Simulation of 'M' timed out after 5 s:", model_name="M", diagnostics="", partial_result=partial
    )

    assert error.partial_result is partial
    assert errors.SimulationError("Simulation of 'M' failed:", model_name="M", diagnostics="").partial_result is None
