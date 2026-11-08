import tempfile
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def backend_temp_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Keep the backend's build and run directories under pytest's temporary directory."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path_factory.mktemp("backend")))
        yield
