"""Multi-file packages, extra sources and libraries built in place."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from mtools.internal.omc.build import build
from mtools.internal.omc.config import (BuildConfig, Library, RunSettings,
                                        Target)
from mtools.internal.omc.packages import package_root

MODELS = Path(__file__).parent / "models"


@pytest.fixture(scope="module")
def fixture_package(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of FixturePkg whose static library is built with the installed compiler."""
    root = tmp_path_factory.mktemp("workspace") / "FixturePkg"
    shutil.copytree(MODELS / "FixturePkg", root)
    source = root / "Resources" / "Source" / "fixture_offset.c"
    obj = source.with_suffix(".o")
    subprocess.run(["cc", "-c", "-fPIC", str(source), "-o", str(obj)], check=True)
    subprocess.run(["ar", "rcs", str(root / "Resources" / "Library" / "libfixture.a"), str(obj)], check=True)
    return root


@pytest.fixture
def elsewhere(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run from a working directory outside the package."""
    directory = tmp_path / "elsewhere"
    directory.mkdir()
    monkeypatch.chdir(directory)
    return directory


def _simulate(config: BuildConfig, target: Target):
    return build(replace(config, target=target)).simulate(RunSettings(stop_time=1.0, interval=0.5))


def test_model_in_a_package_file_builds_with_its_package_and_external_c_code(
    fixture_package: Path, elsewhere: Path, target: Target
):
    result = _simulate(BuildConfig(fixture_package / "Top.mo", "FixturePkg.Top"), target)

    np.testing.assert_allclose(result["a"], 2.0 * result["time"])
    np.testing.assert_allclose(result["b"], result["time"] + 100.0)


def test_model_in_a_subpackage_builds(fixture_package: Path, elsewhere: Path, target: Target):
    result = _simulate(BuildConfig(fixture_package / "Sub" / "Nested.mo", "FixturePkg.Sub.Nested"), target)

    np.testing.assert_allclose(result["a"], 2.0 * result["time"])


def test_model_using_the_msl_builds_without_listing_it(fixture_package: Path, elsewhere: Path, target: Target):
    result = _simulate(BuildConfig(fixture_package / "UsesMsl.mo", "FixturePkg.UsesMsl"), target)

    np.testing.assert_allclose(result["y"], 2.0 * result["time"])


def test_extra_sources_are_loaded_before_the_model(tmp_path: Path, target: Target):
    helper = tmp_path / "Helper.mo"
    helper.write_text("package Helper constant Real k = 7; end Helper;\n")
    model = tmp_path / "UsesHelper.mo"
    model.write_text("model UsesHelper Real y = Helper.k; end UsesHelper;\n")

    result = _simulate(BuildConfig(model, "UsesHelper", extra_sources=[helper]), target)

    np.testing.assert_allclose(result["y"], 7.0)


def test_extra_source_inside_a_package_loads_its_package(fixture_package: Path, tmp_path: Path, target: Target):
    model = tmp_path / "UsesGain.mo"
    model.write_text("model UsesGain Real y = FixturePkg.Gain(time); end UsesGain;\n")

    result = _simulate(BuildConfig(model, "UsesGain", extra_sources=[fixture_package / "Gain.mo"]), target)

    np.testing.assert_allclose(result["y"], 2.0 * result["time"])


def _loaded(model_build, name: str) -> Path:
    return next(library.path for library in model_build.loaded_libraries if library.name == name)


def test_pinned_library_version_loads_exactly_that_version(fixture_package: Path):
    config = BuildConfig(
        fixture_package / "UsesMsl.mo", "FixturePkg.UsesMsl", libraries=[Library("Modelica", "4.0.0")]
    )
    assert "4.0.0" in str(_loaded(build(config), "Modelica"))

    config = BuildConfig(
        fixture_package / "UsesMsl.mo", "FixturePkg.UsesMsl", libraries=[Library("Modelica", "4.1.0")]
    )
    assert "4.1.0" in str(_loaded(build(config), "Modelica"))


def test_library_without_a_version_loads_the_installed_default(fixture_package: Path):
    config = BuildConfig(fixture_package / "UsesMsl.mo", "FixturePkg.UsesMsl", libraries=[Library("Modelica")])

    assert _loaded(build(config), "Modelica").exists()


@pytest.fixture
def two_versions(tmp_path: Path) -> Path:
    directory = tmp_path / "libs"
    for version, value in (("1.0.0", 1), ("2.0.0", 2)):
        package = directory / f"Lib {version}"
        package.mkdir(parents=True)
        (package / "package.mo").write_text(
            f'package Lib annotation(version = "{version}");\n  constant Integer value = {value};\nend Lib;\n'
        )
    return directory


@pytest.mark.parametrize("version, value", [("1.0.0", 1), ("2.0.0", 2)])
def test_library_in_a_directory_is_found_at_its_pinned_version(
    tmp_path: Path, two_versions: Path, version: str, value: int, target: Target
):
    model = tmp_path / "UsesLib.mo"
    model.write_text("model UsesLib Real y = Lib.value; end UsesLib;\n")
    config = BuildConfig(model, "UsesLib", libraries=[Library("Lib", version, directory=two_versions)])

    result = _simulate(config, target)

    np.testing.assert_allclose(result["y"], float(value))


def test_package_root_is_the_top_level_package_directory(fixture_package: Path, tmp_path: Path):
    assert package_root(fixture_package / "Sub" / "Nested.mo") == fixture_package
    assert package_root(fixture_package / "Top.mo") == fixture_package
    assert package_root(fixture_package / "package.mo") == fixture_package
    single = tmp_path / "Single.mo"
    single.write_text("model Single end Single;\n")
    assert package_root(single) == single
