import tempfile
from collections.abc import Iterator

import pytest

from mtools.internal.omc.config import Target


@pytest.fixture(scope="session", autouse=True)
def backend_temp_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Keep the backend's build and run directories under pytest's temporary directory."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path_factory.mktemp("backend")))
        yield


@pytest.fixture(params=["C", "Cpp"])
def target(request: pytest.FixtureRequest) -> Target:
    """Run the requesting test on each simulation target."""
    return request.param  # type: ignore[no-any-return]
