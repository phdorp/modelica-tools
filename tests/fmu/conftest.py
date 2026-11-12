import logging
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from mtools.internal.omc import build, workdir
from mtools.internal.omc.config import BuildConfig, FmuExportConfig
from tests.fmu.fmu_models import MODEL_PATH


@pytest.fixture(scope="module", autouse=True)
def work_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Keep run directories under pytest's temporary directory, one work directory per test file."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(workdir.WORK_DIR_VARIABLE, str(tmp_path_factory.mktemp("work")))
        yield


@pytest.fixture(scope="module")
def exported_fmu(tmp_path_factory: pytest.TempPathFactory, work_dir: None) -> Callable[..., Path]:
    """Return ``export(model, fmu_type="me", **build) -> Path``, which exports ``model`` of
    ``FmuTests.mo`` through the build cache and returns a copy of its ``model.fmu``."""
    directory = tmp_path_factory.mktemp("exported")

    def export(model: str, fmu_type: str = "me", **build_fields: Any) -> Path:
        config = BuildConfig(model_path=MODEL_PATH, model_name=model, fmu=FmuExportConfig(fmu_type), **build_fields)
        with build.build(config) as built:
            copy = Path(shutil.copy(built.fmu_path, directory / f"{model}-{fmu_type}.fmu"))
        return copy

    return export


@pytest.fixture
def fresh_work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """An empty work directory (no cached builds) for this test alone; INFO logs captured."""
    monkeypatch.setenv(workdir.WORK_DIR_VARIABLE, str(tmp_path / "work"))
    caplog.set_level(logging.INFO)
