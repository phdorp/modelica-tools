"""Build-time and protected parameters of an exported FMU: variant FMUs, as for native builds (ADR 0001)."""

import logging

import pytest

from mtools.errors import ConfigError, TranslationError
from mtools.internal.fmu.description import FmuVariable
from mtools.internal.fmu.parameters import start_values
from mtools.internal.omc.init_xml import Variable
from tests.fmu.helpers import build_messages, simulate_exported

MODEL = "FmuTests.BuildTime"


def test_array_size_sweep_exports_a_cached_variant(fresh_work_dir, caplog):
    for _ in range(2):
        result = simulate_exported(MODEL, parameters={"n": 3})[MODEL]
    assert [c for c in result.columns if c.startswith("y[")] == ["y[1]", "y[2]", "y[3]"]
    assert "Building a variant of 'FmuTests.BuildTime' because 'n' is fixed at build time" in caplog.text
    assert [m.split(" ")[0] for m in build_messages(caplog)] == ["Built", "Built", "Reused", "Reused"]


def test_other_parameters_are_checked_against_the_variant():
    result = simulate_exported(MODEL, parameters={"n": 3, "y0": [1.0, 2.0, 3.0]})[MODEL]
    assert list(result.loc[0, ["y[1]", "y[2]", "y[3]"]]) == pytest.approx([1.0, 2.0, 3.0])


def test_evaluate_true_parameter_exports_a_variant(caplog):
    caplog.set_level(logging.INFO)
    assert (simulate_exported(MODEL)[MODEL]["z"] == 1.0).all()
    assert (simulate_exported(MODEL, parameters={"useA": False})[MODEL]["z"] == 2.0).all()
    assert "Building a variant of 'FmuTests.BuildTime' because 'useA' is fixed at build time" in caplog.text


def test_build_time_value_of_the_wrong_type_is_a_config_error_before_any_variant(caplog):
    caplog.set_level(logging.INFO)
    with pytest.raises(ConfigError) as error:
        simulate_exported(MODEL, parameters={"n": 2.7})
    assert "settings.parameters.n: expected an Integer, got 2.7" in error.value.diagnostics
    assert "Building a variant" not in caplog.text


def test_final_parameter_is_a_translation_error():
    with pytest.raises(TranslationError, match="final"):
        simulate_exported(MODEL, parameters={"f": 2.0})


@pytest.mark.parametrize("emit_protected", [False, True])
def test_protected_parameter_is_a_config_error_before_any_variant(caplog, emit_protected):
    caplog.set_level(logging.INFO)
    with pytest.raises(ConfigError) as error:
        simulate_exported(MODEL, parameters={"hp": 1.0}, emit_protected=emit_protected)
    assert "settings.parameters.hp: 'FmuTests.BuildTime' parameter 'hp' is protected" in error.value.diagnostics
    assert "Building a variant" not in caplog.text


def test_derivative_of_an_exported_fmu_is_fixed_without_the_given_fmu_hint():
    with pytest.raises(ConfigError) as error:
        simulate_exported(MODEL, parameters={"der(y[1])": 1.0})
    assert error.value.diagnostics == (
        "settings.parameters.der(y[1]): 'FmuTests.BuildTime' parameter 'der(y[1])' is fixed in the FMU (continuous)"
    )

def test_parameter_evaluated_out_of_the_model_description_is_build_time():
    # OMC can leave an evaluated parameter out of the model description; the export's
    # model_init.xml still lists it as a public non-changeable parameter.
    k = FmuVariable("k", "Real", "parameter", "fixed", "exact", None, {})
    build_variables = {
        "n": Variable("n", "Integer", "parameter", "calculatedParameter", changeable=False, protected=False),
        "k": Variable("k", "Real", "parameter", "parameter", changeable=True, protected=False),
    }
    _, problems, build_values = start_values(
        {"n": 3, "k": 2.0},
        {"k": k},
        model_name=MODEL,
        to_fmu=lambda name: name,
        exported=True,
        build_variables=build_variables,
    )
    assert (problems, build_values) == ([], {"n": "3"})


def test_build_time_value_that_is_no_literal_of_its_type_is_a_problem():
    # OMC lists an enumeration as Integer in model_init.xml, so only a qualified literal can be written.
    build_variables = {
        "mode": Variable("mode", "Integer", "parameter", "calculatedParameter", changeable=False, protected=False)
    }
    _, problems, build_values = start_values(
        {"mode": "high"},
        {},
        model_name=MODEL,
        to_fmu=lambda name: name,
        exported=True,
        build_variables=build_variables,
    )
    assert (problems, build_values) == (
        ["settings.parameters.mode: 'high' is not a qualified enumeration literal (e.g. 'Mode.high')"], {}
    )


def test_calculated_parameter_missing_from_model_init_xml_is_fixed_not_build_time():
    # Without its model_init.xml entry, no modifier can be written for it.
    n = FmuVariable("n", "Integer", "calculatedParameter", "fixed", "calculated", None, {})
    _, problems, build_values = start_values(
        {"n": 3},
        {"n": n},
        model_name=MODEL,
        to_fmu=lambda name: name,
        exported=True,
        build_variables={},
    )
    assert (problems, build_values) == (
        ["settings.parameters.n: 'FmuTests.BuildTime' parameter 'n' is fixed in the FMU (calculatedParameter)"], {}
    )
