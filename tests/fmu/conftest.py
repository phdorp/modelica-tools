from collections.abc import Iterator

import pytest

from mtools.internal.omc.workdir import WORK_DIR_VARIABLE


@pytest.fixture(scope="module", autouse=True)
def work_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Keep run directories under pytest's temporary directory, one work directory per test file."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(WORK_DIR_VARIABLE, str(tmp_path_factory.mktemp("work")))
        yield
