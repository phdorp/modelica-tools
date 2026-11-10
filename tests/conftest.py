import copy
import logging
from collections.abc import Iterator

import pytest
from hydra.core.config_store import ConfigStore

# Loggers whose level a test (e.g. a Hydra run) may change and leave behind.
_LOGGERS = ["", "mtools"]


@pytest.fixture(autouse=True)
def isolate_global_state() -> Iterator[None]:
    """Restore Hydra's config store and the logger levels after every test.

    Both are process-wide, so a test that registers configs or raises a log
    level otherwise changes the outcome of whichever test runs next. Hydra
    registers its own ``hydra`` group lazily, so that group is kept as is.
    """
    store = ConfigStore.instance()
    repo = {key: copy.deepcopy(value) for key, value in store.repo.items() if key != "hydra"}
    levels = {name: logging.getLogger(name).level for name in _LOGGERS}
    yield
    if "hydra" in store.repo:
        repo["hydra"] = store.repo["hydra"]
    store.repo = repo
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test that builds or runs the Cpp target with ``cpp``.

    That covers tests parametrised with a ``"Cpp"`` value and every test in a
    ``test_cpp_*.py`` file.
    """
    for item in items:
        callspec = getattr(item, "callspec", None)
        params = callspec.params.values() if callspec is not None else ()
        cpp_param = any(isinstance(value, str) and value == "Cpp" for value in params)
        if cpp_param or item.path.name.startswith("test_cpp_"):
            item.add_marker(pytest.mark.cpp)
