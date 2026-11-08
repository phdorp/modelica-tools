"""Build variants for build-time parameters: unit tests of the split and integration tests against OMC."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from mtools.errors import ConfigError, TranslationError
from mtools.internal.omc.build import Build, build
from mtools.internal.omc.config import BuildConfig, RunSettings, Target
from mtools.internal.omc.init_xml import Variable
from mtools.internal.omc.variants import split_parameters

MODEL = Path(__file__).parent / "models" / "Variants.mo"


def _variable(name: str, type: str, *, changeable: bool = False, protected: bool = False) -> Variable:
    return Variable(name, type, "parameter", "parameter", changeable, protected)


VARIABLES = {
    variable.name: variable
    for variable in [
        _variable("r", "Real"),
        _variable("i", "Integer"),
        _variable("b", "Boolean"),
        _variable("s", "String"),
        _variable("e", "Integer"),
        _variable("sub.r", "Real"),
        _variable("v[1]", "Real"),
        _variable("v[2]", "Real"),
        _variable("m[1,1]", "Integer"),
        _variable("m[1,2]", "Integer"),
        _variable("hidden", "Real", protected=True),
        _variable("hiddenFree", "Real", changeable=True, protected=True),
        _variable("free", "Real", changeable=True),
    ]
}


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [
        ({"r": 0.1 + 0.2}, {"r": "0.30000000000000004"}),
        ({"i": 3}, {"i": "3"}),
        ({"b": True}, {"b": "true"}),
        ({"b": False}, {"b": "false"}),
        ({"s": 'a"b'}, {"s": '"a\\"b"'}),
        ({"e": "M.Mode.high"}, {"e": "M.Mode.high"}),
        ({"sub": {"r": 5}}, {"sub.r": "5.0"}),
        ({"v": [7, 8]}, {"v": "{7.0, 8.0}"}),
        ({"m": [[1, 2], [3, 4]]}, {"m": "{{1, 2}, {3, 4}}"}),
    ],
)
def test_build_time_values_are_written_as_literals_of_their_type(parameters: Any, expected: dict[str, str]) -> None:
    split = split_parameters(parameters, VARIABLES, "M")

    assert dict(split.build_values) == expected
    assert not split.run_parameters


def test_changeable_and_unlisted_parameters_stay_per_run() -> None:
    split = split_parameters({"free": 1.0, "r": 2.0, "other": 3}, VARIABLES, "M")

    assert dict(split.build_values) == {"r": "2.0"}
    assert dict(split.run_parameters) == {"free": 1.0, "other": 3}


def test_an_unqualified_enumeration_literal_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="settings.parameters.e: 'high' is not a qualified enumeration literal"):
        split_parameters({"e": "high"}, VARIABLES, "M")


def test_a_changeable_protected_parameter_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="settings.parameters.hiddenFree: 'M' parameter 'hiddenFree' is protected"):
        split_parameters({"hiddenFree": 1.0}, VARIABLES, "M")


def test_a_protected_build_time_parameter_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="settings.parameters.hidden: 'M' parameter 'hidden' is protected"):
        split_parameters({"r": 1.0, "hidden": 1.0}, VARIABLES, "M")


# ---- against OMC -------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "work"
    monkeypatch.setenv("MTOOLS_WORK_DIR", str(directory))
    monkeypatch.delenv("MTOOLS_NO_CACHE", raising=False)
    monkeypatch.delenv("MTOOLS_KEEP_RUNS", raising=False)
    return directory


@pytest.fixture
def plain(work_dir: Path, target: Target) -> Build:
    return build(BuildConfig(model_path=MODEL, model_name="Variants", target=target))


def _last(build_: Build, **parameters: Any) -> dict[str, float]:
    result = build_.simulate(RunSettings(parameters=parameters))
    return {str(name): float(value) for name, value in result.iloc[-1].items()}


def _messages(caplog: pytest.LogCaptureFixture, start: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.INFO and r.getMessage().startswith(start)]


def test_plain_parameters_need_no_variant(plain: Build, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        row = _last(plain, k=7.0)

    assert row["kOut"] == 14.0
    assert not _messages(caplog, "Building a variant")


def test_an_array_size_changes_the_variants_parameters(plain: Build) -> None:
    row = _last(plain, n=3, y=[1, 2, 4], k=9.0)

    assert row["sumY"] == 7.0
    assert row["kOut"] == 18.0  # a changeable parameter still varies per run on the variant
    assert row["time"] == 2.0  # the experiment annotation carries over
    assert not plain.variables["n"].changeable
    assert "y[3]" not in plain.variables


def test_an_if_equation_selector(plain: Build) -> None:
    assert _last(plain)["selected"] == 2.0
    assert _last(plain, sel=True)["selected"] == 1.0


def test_an_enumeration_selector(plain: Build) -> None:
    assert _last(plain)["modeValue"] == 2.0
    assert _last(plain, mode="Mode.high")["modeValue"] == 1.0


def test_a_local_and_an_inherited_evaluate_parameter(plain: Build) -> None:
    row = _last(plain, loc=11.0, inh=3.0)

    assert row["localOut"] == 11.0
    assert row["xb"] == pytest.approx(6.0)  # der(xb) = inh over two seconds


def test_whole_array_parameters(plain: Build) -> None:
    row = _last(plain, a=[7, 8], mm=[[1, 2], [3, 4]])
    assert (row["aOut"], row["mmOut"]) == (78.0, 23.0)

    row = _last(plain, mm=[[1, 5], [6, 4]])
    assert row["mmOut"] == 56.0


def test_a_nested_parameter(plain: Build) -> None:
    row = _last(plain, sub={"m": 5, "free": 2})

    assert row["subOut"] == 205.0


def test_a_string_parameter_is_accepted_at_build_time(plain: Build) -> None:
    assert _last(plain, label="b")["time"] == 2.0


def test_columns_and_model_name_are_those_of_the_plain_build(plain: Build) -> None:
    result = plain.simulate(RunSettings(parameters={"loc": 4.0}))

    assert list(result.columns) == list(plain.simulate(RunSettings()).columns)


def test_one_info_record_names_the_parameters_that_forced_the_variant(
    plain: Build, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        _last(plain, loc=5.0, k=2.0, a=[1, 1])

    records = _messages(caplog, "Building a variant")
    assert len(records) == 1
    assert "'loc'" in records[0] and "'a'" in records[0] and "'k'" not in records[0]


def test_a_repeated_sweep_reuses_the_cached_variants(plain: Build, caplog: pytest.LogCaptureFixture) -> None:
    values = [1.0, 2.0, 3.0]
    first = [_last(plain, loc=v)["localOut"] for v in values]
    with caplog.at_level(logging.INFO):
        again = [_last(plain, loc=v)["localOut"] for v in values]

    assert first == again == values
    assert not _messages(caplog, "Built ")
    assert len(_messages(caplog, "Reused cached build")) == 3
    assert len(list((plain.directory.parent).iterdir())) == 4  # the plain build and one variant per value


def test_the_variant_does_not_collide_with_the_plain_build(plain: Build) -> None:
    assert _last(plain, loc=4.0)["localOut"] == 4.0
    assert _last(plain)["localOut"] == 3.0


def test_a_protected_parameter_fails_before_any_variant_is_built(plain: Build, caplog: pytest.LogCaptureFixture) -> None:
    builds = set(plain.directory.parent.iterdir())

    with caplog.at_level(logging.INFO), pytest.raises(ConfigError, match="hidden"):
        _last(plain, loc=5.0, hidden=3.0)

    assert set(plain.directory.parent.iterdir()) == builds
    assert not _messages(caplog, "Building a variant")


def test_a_final_parameter_fails_as_a_translation_error(plain: Build) -> None:
    with pytest.raises(TranslationError, match="Trying to override final element"):
        _last(plain, fixedValue=1.0)


def test_an_unknown_parameter_is_still_rejected_with_a_variant(plain: Build) -> None:
    with pytest.raises(ConfigError, match="settings.parameters.nope"):
        _last(plain, loc=5.0, nope=1.0)


def test_uncached_variants_are_deleted(plain: Build, monkeypatch: pytest.MonkeyPatch, work_dir: Path) -> None:
    monkeypatch.setenv("MTOOLS_NO_CACHE", "1")
    with build(BuildConfig(model_path=MODEL, model_name="Variants", target=plain.target)) as uncached:
        assert _last(uncached, loc=2.0)["localOut"] == 2.0

    assert not any((work_dir / "runs").iterdir())
