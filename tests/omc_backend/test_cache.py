"""Integration tests of the build cache, the work directory and cleanup, against real OMC."""

from __future__ import annotations

import logging
import multiprocessing
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from mtools.errors import SimulationError
from mtools.internal.omc.build import build
from mtools.internal.omc.config import BuildConfig, Library, RunSettings, Target

MODEL = "model {name} parameter Real k = {k}; Real x(start=0, fixed=true); equation der(x) = k; end {name};\n"
FAILING = (
    "model Failing Real x(start=0, fixed=true); equation der(x) = 1; "
    'assert(time < 0.5, "boom", AssertionLevel.error); end Failing;\n'
)


@pytest.fixture(autouse=True)
def work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "work"
    monkeypatch.setenv("MTOOLS_WORK_DIR", str(directory))
    monkeypatch.delenv("MTOOLS_NO_CACHE", raising=False)
    monkeypatch.delenv("MTOOLS_KEEP_RUNS", raising=False)
    return directory


def _single(tmp_path: Path, k: int = 1, target: Target = "C") -> BuildConfig:
    source = tmp_path / "A.mo"
    source.write_text(MODEL.format(name="A", k=k))
    return BuildConfig(model_path=source, model_name="A", target=target)


def _package(root: Path, name: str, k: int = 1) -> Path:
    """Write package ``name`` with model ``M``; return the model file."""
    (root / name / "Resources").mkdir(parents=True, exist_ok=True)
    (root / name / "package.mo").write_text(f"within; package {name} end {name};\n")
    model = root / name / "M.mo"
    model.write_text(f"within {name};\n" + MODEL.format(name="M", k=k))
    return model


def _messages(caplog: pytest.LogCaptureFixture, word: str) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(word)]


def test_unchanged_build_is_reused_without_compiling(tmp_path: Path, caplog: pytest.LogCaptureFixture, target: Target):
    caplog.set_level(logging.INFO)
    config = _single(tmp_path, target=target)

    first = build(config)
    second = build(config)

    assert len(_messages(caplog, "Built")) == 1
    assert len(_messages(caplog, "Reused")) == 1
    assert second.directory == first.directory
    assert second.experiment == first.experiment
    assert second.loaded_libraries == first.loaded_libraries
    assert second.simulate(RunSettings()).iloc[-1]["x"] == pytest.approx(1.0)


def test_editing_the_model_file_rebuilds(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    build(_single(tmp_path, k=1))

    changed = build(_single(tmp_path, k=2))

    assert len(_messages(caplog, "Built")) == 2
    assert changed.simulate(RunSettings()).iloc[-1]["x"] == pytest.approx(2.0)


def test_editing_a_file_in_the_model_package_rebuilds(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    model = _package(tmp_path, "Pkg")
    config = BuildConfig(model_path=model.parent / "package.mo", model_name="Pkg.M")
    build(config)
    build(config)
    assert len(_messages(caplog, "Reused")) == 1

    (model.parent / "Resources" / "data.txt").write_text("changed")
    build(config)

    assert len(_messages(caplog, "Built")) == 2


def test_editing_an_extra_sources_package_rebuilds(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    extra = _package(tmp_path, "Extra")
    main = _single(tmp_path)
    config = BuildConfig(model_path=main.model_path, model_name="A", extra_sources=(extra.parent / "package.mo",))
    build(config)
    build(config)
    assert len(_messages(caplog, "Reused")) == 1

    (extra.parent / "Resources" / "data.txt").write_text("changed")
    build(config)

    assert len(_messages(caplog, "Built")) == 2


def test_editing_a_directory_library_rebuilds(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    libs = tmp_path / "libs"
    library = _package(libs, "Lib")
    main = tmp_path / "B.mo"
    main.write_text("model B Lib.M m; end B;\n")
    config = BuildConfig(model_path=main, model_name="B", libraries=(Library("Lib", directory=libs),))
    build(config)
    build(config)
    assert len(_messages(caplog, "Reused")) == 1

    library.write_text("within Lib;\n" + MODEL.format(name="M", k=5))
    build(config)

    assert len(_messages(caplog, "Built")) == 2


def _build_in_process(model: str, work: str, results: "multiprocessing.Queue[tuple[str, str]]") -> None:
    os.environ["MTOOLS_WORK_DIR"] = work
    results.put((str(build(BuildConfig(model_path=Path(model), model_name="A")).directory), "ok"))


def test_two_processes_building_the_same_key_both_succeed_and_share_one_build(tmp_path: Path, work_dir: Path):
    config = _single(tmp_path)
    context = multiprocessing.get_context("spawn")
    results: multiprocessing.Queue[tuple[str, str]] = context.Queue()
    processes = [
        context.Process(target=_build_in_process, args=(str(config.model_path), str(work_dir), results))
        for _ in range(2)
    ]

    for process in processes:
        process.start()
    outcomes = [results.get(timeout=300) for _ in processes]
    for process in processes:
        process.join()

    assert [process.exitcode for process in processes] == [0, 0]
    assert len({directory for directory, _ in outcomes}) == 1
    assert len(list((work_dir / "builds").iterdir())) == 1
    assert list((work_dir / "tmp").iterdir()) == []


def test_c_and_cpp_builds_of_one_model_are_cached_separately(tmp_path: Path, work_dir: Path):
    c_build = build(_single(tmp_path, target="C"))
    cpp_build = build(_single(tmp_path, target="Cpp"))

    assert c_build.directory != cpp_build.directory
    assert len(list((work_dir / "builds").iterdir())) == 2
    assert build(_single(tmp_path, target="Cpp")).directory == cpp_build.directory
    assert cpp_build.simulate(RunSettings()).iloc[-1]["x"] == pytest.approx(1.0)


def test_run_directories_are_deleted_after_success_and_failure(tmp_path: Path, work_dir: Path, target: Target):
    failing = tmp_path / "Failing.mo"
    failing.write_text(FAILING)
    good = build(_single(tmp_path, target=target))
    bad = build(BuildConfig(model_path=failing, model_name="Failing", target=target))

    good.simulate(RunSettings())
    with pytest.raises(SimulationError) as error:
        bad.simulate(RunSettings())

    assert list((work_dir / "runs").iterdir()) == []
    assert "Run directory:" not in str(error.value)


def test_keep_runs_keeps_run_directories_logs_them_and_names_them_in_failures(
    tmp_path: Path, work_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, target: Target
):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("MTOOLS_KEEP_RUNS", "1")
    failing = tmp_path / "Failing.mo"
    failing.write_text(FAILING)
    bad = build(BuildConfig(model_path=failing, model_name="Failing", target=target))
    _single(tmp_path)

    with pytest.raises(SimulationError) as error:
        bad.simulate(RunSettings())

    kept = list((work_dir / "runs").iterdir())
    assert len(kept) == 1
    assert str(error.value).rstrip().endswith(f"Run directory: {kept[0]}")
    assert any(str(kept[0]) in message for message in _messages(caplog, "Keeping"))


def test_no_cache_builds_into_runs_and_close_deletes_the_build(tmp_path: Path, work_dir: Path, monkeypatch):
    monkeypatch.setenv("MTOOLS_NO_CACHE", "1")
    config = _single(tmp_path)

    with build(config) as uncached:
        assert uncached.directory.parent == work_dir / "runs"
        assert uncached.simulate(RunSettings()).iloc[-1]["x"] == pytest.approx(1.0)
    assert not uncached.directory.exists()

    assert not (work_dir / "builds").exists()
    assert list((work_dir / "runs").iterdir()) == []


def test_closing_a_cached_build_keeps_it(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    config = _single(tmp_path)

    with build(config) as first:
        pass
    build(config)

    assert first.directory.exists()
    assert len(_messages(caplog, "Reused")) == 1


def test_failed_builds_leave_nothing_behind(tmp_path: Path, work_dir: Path):
    from mtools.errors import TranslationError

    source = tmp_path / "Bad.mo"
    source.write_text("model Bad Real x; equation x = y; end Bad;\n")

    with pytest.raises(TranslationError):
        build(BuildConfig(model_path=source, model_name="Bad"))

    assert list((work_dir / "builds").iterdir()) == []
    assert list((work_dir / "tmp").iterdir()) == []
