"""Unit tests (no OMC) for cache keys and the work directory."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mtools.internal.omc import cache, workdir
from mtools.internal.omc.config import BuildConfig, Library
from mtools.internal.omc.packages import package_root
from mtools.internal.omc.script import Experiment, LoadedLibrary


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


@pytest.mark.parametrize("in_package", [False, True])
def test_key_is_stable_and_ignores_timestamps(tmp_path: Path, in_package: bool):
    if in_package:
        model = _package(tmp_path)
    else:
        model = tmp_path / "A.mo"
        model.write_text("model A end A;")
    config = BuildConfig(model_path=model, model_name="Pkg.M")
    first = cache.cache_key(config)
    stat = model.stat()
    model.write_text(model.read_text())  # same content
    os.utime(model, ns=(stat.st_atime_ns + 10**9, stat.st_mtime_ns + 10**9))  # new mtime

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

    assert package_root(nested) == tmp_path / "Pkg"


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


def test_backend_version_changes_the_key_and_follows_the_script_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    model = tmp_path / "A.mo"
    model.write_text("model A end A;")
    config = BuildConfig(model_path=model, model_name="A")
    before = cache.cache_key(config)
    version = cache.backend_version()

    monkeypatch.setattr(cache, "backend_version", lambda: "other")
    assert cache.cache_key(config) != before

    monkeypatch.undo()
    original = cache.build_script
    cache.backend_version.cache_clear()
    try:
        monkeypatch.setattr(cache, "build_script", lambda *args: original(*args) + "// changed\n")
        assert cache.backend_version() != version
    finally:
        monkeypatch.undo()
        cache.backend_version.cache_clear()


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


def _stored_build(tmp_path: Path, config: BuildConfig, loaded: tuple[LoadedLibrary, ...]) -> str:
    key = cache.cache_key(config)
    directory = workdir.builds_dir() / key
    directory.mkdir(parents=True)
    experiment = Experiment(0.0, 1.0, 0.1, 1e-6, "dassl")
    cache.save_record(directory, cache.new_record(config, experiment, loaded))
    return key


@pytest.fixture
def _work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MTOOLS_WORK_DIR", str(tmp_path / "work"))


def test_a_hit_is_rejected_when_a_listed_source_package_changed_since_the_build(tmp_path: Path, _work: None):
    model = _package(tmp_path)
    config = BuildConfig(model_path=model, model_name="Pkg.M")
    key = _stored_build(tmp_path, config, (LoadedLibrary("Pkg", tmp_path / "Pkg"),))
    assert cache.lookup(key, config) is not None

    (tmp_path / "Pkg" / "Resources" / "data.txt").write_text("changed")

    assert cache.lookup(key, config) is None
    assert not (workdir.builds_dir() / key).exists()


def test_a_hit_is_rejected_when_an_installed_library_changed_version(tmp_path: Path, _work: None):
    model = tmp_path / "A.mo"
    model.write_text("model A end A;")
    config = BuildConfig(model_path=model, model_name="A")
    key = _stored_build(tmp_path, config, (LoadedLibrary("Lib", tmp_path / "installed" / "Lib 1.0"),))
    assert cache.lookup(key, config) is not None

    record = cache.load_record(workdir.builds_dir() / key)
    assert record is not None
    upgraded = (LoadedLibrary("Lib", tmp_path / "installed" / "Lib 2.0"),)
    cache.save_record(workdir.builds_dir() / key, cache.BuildRecord(record.experiment, upgraded, record.hashes))

    assert cache.lookup(key, config) is None


def _checkout(root: Path, in_package: bool) -> tuple[BuildConfig, LoadedLibrary]:
    """A model as OMC loads it: a package by its directory, a single file by the file's directory."""
    if in_package:
        return BuildConfig(model_path=_package(root), model_name="Pkg.M"), LoadedLibrary("Pkg", root / "Pkg")
    root.mkdir(parents=True)
    (root / "A.mo").write_text("model A end A;")
    return BuildConfig(model_path=root / "A.mo", model_name="A"), LoadedLibrary("A", root)


@pytest.mark.parametrize("in_package", [False, True], ids=["single-file", "package"])
def test_a_hit_is_valid_for_the_same_sources_at_another_path(tmp_path: Path, _work: None, in_package: bool):
    built, loaded = _checkout(tmp_path / "a", in_package)
    other, _ = _checkout(tmp_path / "b", in_package)
    key = _stored_build(tmp_path, built, (loaded,))

    assert cache.cache_key(other) == key
    assert cache.lookup(key, other) is not None
    assert cache.lookup(key, built) is not None


def test_a_hit_from_another_path_is_rejected_when_the_package_there_changed(tmp_path: Path, _work: None):
    built, loaded = _checkout(tmp_path / "a", in_package=True)
    other, _ = _checkout(tmp_path / "b", in_package=True)
    key = _stored_build(tmp_path, built, (loaded,))

    (tmp_path / "b" / "Pkg" / "Resources" / "data.txt").write_text("changed")

    assert cache.lookup(key, other) is None
