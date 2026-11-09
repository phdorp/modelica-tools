from collections.abc import Iterator

import pytest

from mtools.internal.omc.workdir import WORK_DIR_VARIABLE


@pytest.fixture(scope="session", autouse=True)
def work_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Keep builds and run directories under pytest's temporary directory, shared by the session."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(WORK_DIR_VARIABLE, str(tmp_path_factory.mktemp("work")))
        yield
