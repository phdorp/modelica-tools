"""``settings.emit_protected`` decides whether an exported FMU exposes protected variables."""

import logging

import pytest

from mtools.errors import ConfigError
from mtools.internal.omc import workdir
from tests.fmu.helpers import (build_messages, reference_fmu,
                               simulate_exported, simulate_given)


@pytest.fixture
def fresh_work_dir(tmp_path, monkeypatch, caplog):
    """An empty work directory (no cached builds) for this test alone; INFO logs captured."""
    monkeypatch.setenv(workdir.WORK_DIR_VARIABLE, str(tmp_path / "work"))
    caplog.set_level(logging.INFO)


def test_protected_variables_appear_only_with_emit_protected(fresh_work_dir, caplog):
    assert "hidden" not in simulate_exported("FmuTests.Protected")["FmuTests.Protected"]
    assert "hidden" in simulate_exported("FmuTests.Protected", emit_protected=True)["FmuTests.Protected"]
    assert [message.split(" ")[0] for message in build_messages(caplog)] == ["Built", "Built"]


def test_fmi_filter_flag_is_rejected_for_exports(caplog):
    caplog.set_level(logging.INFO)

    with pytest.raises(ConfigError) as error:
        simulate_exported("FmuTests.Decay", omc_flags={"--fmiFilter": "none"})

    assert (
        "build.omc_flags: '--fmiFilter' is not allowed for an exported FMU; set settings.emit_protected"
        in error.value.diagnostics
    )
    assert build_messages(caplog) == []


def test_other_fmi_flags_are_allowed_and_keyed(fresh_work_dir, caplog):
    simulate_exported("FmuTests.Decay")
    simulate_exported("FmuTests.Decay", omc_flags={"--fmiFlags": "s:cvode"})

    assert [message.split(" ")[0] for message in build_messages(caplog)] == ["Built", "Built"]


def test_emit_protected_warns_on_a_given_fmu(caplog):
    simulate_given(reference_fmu("Dahlquist"), emit_protected=True)

    assert "settings.emit_protected has no effect on the given FMU 'Dahlquist'" in caplog.text
