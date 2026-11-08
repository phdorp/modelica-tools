"""Unit tests (no OMC) for cache keys and the work directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from mtools.internal.omc import cache, workdir
from mtools.internal.omc.config import BuildConfig, Library


@pytest.fixture(autouse=True)
def fixed_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, "omc_version", lambda: "omc 1")
    monkeypatch.setattr(cache, "compiler_version", lambda: "gcc 1")


def _package(root: Path) -> Path:
    (root / "Pkg" / "Resources").mkdir(parents=True)
    (root / "Pkg" / "package.mo").write_text("within; package Pkg end Pkg;")
    (root / "Pkg" / "M.mo").write_text("within Pkg; model M end M;")
    (root / "Pkg" / "Resources" / "data.txt").write_text("1")
    return root / "Pkg" / "M.mo"


def test_key_is_stable_and_ignores_timestamps(tmp_path: Path):
    model = _package(tmp_path)
    config = BuildConfig(model_path=model, model_name="Pkg.M")
    first = cache.cache_key(config)
    model.write_text(model.read_text())  # new mtime, same content

    assert cache.cache_key(config) == first


@pytest.mark.parametrize("edited", ["package.mo", "Resources/data.txt"])
def test_editing_any_file_of_the_top_level_package_changes_the_key(tmp_path: Path, edited: str):
    config = BuildConfig(model_path=_package(tmp_path), model_name="Pkg.M")
    before = cache.cache_key(config)

    (tmp_path / "Pkg" / edited).write_text("changed")

    assert cache.cache_key(config) != before


def test_nested_package_resolves_to_the_top_level_package(tmp_path: Path):
    _package(tmp_path)
    (tmp_path / "Pkg" / "Sub").mkdir()
    (tmp_path / "Pkg" / "Sub" / "package.mo").write_text("within Pkg; package Sub end Sub;")
    nested = tmp_path / "Pkg" / "Sub" / "N.mo"
    nested.write_text("within Pkg.Sub; model N end N;")

    assert cache.package_root(nested) == tmp_path / "Pkg"


def test_single_file_outside_a_package_does_not_hash_its_neighbours(tmp_path: Path):
    model = tmp_path / "A.mo"
    model.write_text("model A end A;")
    config = BuildConfig(model_path=model, model_name="A")
    before = cache.cache_key(config)

    (tmp_path / "Other.mo").write_text("model Other end Other;")

    assert cache.cache_key(config) == before


def test_extra_sources_flags_target_and_libraries_change_the_key(tmp_path: Path):
    model = tmp_path / "A.mo"
    model.write_text("model A end A;")
    extra = tmp_path / "pkg_extra"
    extra.mkdir()
    (extra / "package.mo").write_text("package E end E;")
    libs = tmp_path / "libs"
    libs.mkdir()
    (libs / "L.mo").write_text("package L end L;")
    base = BuildConfig(model_path=model, model_name="A")
    keys = {cache.cache_key(base)}

    keys.add(cache.cache_key(BuildConfig(model_path=model, model_name="A", extra_sources=(extra / "package.mo",))))
    (extra / "package.mo").write_text("package E2 end E2;")
    keys.add(cache.cache_key(BuildConfig(model_path=model, model_name="A", extra_sources=(extra / "package.mo",))))
    keys.add(cache.cache_key(BuildConfig(model_path=model, model_name="A", target="Cpp")))
    keys.add(cache.cache_key(BuildConfig(model_path=model, model_name="A", omc_flags={"-d": "nogen"})))
    keys.add(cache.cache_key(BuildConfig(model_path=model, model_name="A", libraries=(Library("L", "1"),))))
    directory = BuildConfig(model_path=model, model_name="A", libraries=(Library("L", directory=libs),))
    keys.add(cache.cache_key(directory))
    (libs / "L.mo").write_text("package L2 end L2;")
    keys.add(cache.cache_key(directory))

    assert len(keys) == 8


def test_tool_versions_change_the_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    model = tmp_path / "A.mo"
    model.write_text("model A end A;")
    config = BuildConfig(model_path=model, model_name="A")
    before = cache.cache_key(config)

    monkeypatch.setattr(cache, "omc_version", lambda: "omc 2")
    after_omc = cache.cache_key(config)
    monkeypatch.setattr(cache, "compiler_version", lambda: "gcc 2")

    assert len({before, after_omc, cache.cache_key(config)}) == 3


def test_build_time_values_extend_the_key(tmp_path: Path):
    model = tmp_path / "A.mo"
    model.write_text("model A end A;")
    config = BuildConfig(model_path=model, model_name="A")

    assert cache.cache_key(config, {"n": "3"}) != cache.cache_key(config)
    assert cache.cache_key(config, {"n": "3"}) != cache.cache_key(config, {"n": "4"})
    assert cache.cache_key(config, {"a": "1", "b": "2"}) == cache.cache_key(config, {"b": "2", "a": "1"})


def test_work_directory_defaults_to_the_temp_directory_and_can_be_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("MTOOLS_WORK_DIR", raising=False)
    assert workdir.work_dir().parent == Path(workdir.tempfile.gettempdir())
    assert workdir.work_dir().name.startswith("mtools-")

    monkeypatch.setenv("MTOOLS_WORK_DIR", str(tmp_path / "w"))
    assert workdir.work_dir() == tmp_path / "w"
    assert workdir.builds_dir() == tmp_path / "w" / "builds"
    assert workdir.runs_dir() == tmp_path / "w" / "runs"


def test_relative_work_directory_resolves_against_the_start_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(workdir, "START_DIR", tmp_path)
    monkeypatch.setenv("MTOOLS_WORK_DIR", "rel/w")

    assert workdir.work_dir() == tmp_path / "rel" / "w"
