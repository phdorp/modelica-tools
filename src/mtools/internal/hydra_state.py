"""Keep Hydra's process-wide state out of the caller's process.

Composing or launching through Hydra writes into two process-wide places: the
global ``ConfigStore`` and, for a launch, the logging configuration. mtools
runs Hydra inside the caller's process, so it scopes both to the call.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from contextlib import contextmanager

from hydra.core.config_store import ConfigStore

# Entries Hydra registers itself. Its ``hydra`` group also grows lazily while
# Hydra runs, so that group is carried over rather than restored.
_HYDRA_ENTRIES = ("hydra", "_dummy_empty_config_.yaml")

# Hydra's ``none`` presets set ``root: null``, so Hydra skips
# ``logging.config.dictConfig``: it neither changes levels and handlers nor
# closes the caller's handlers.
_LOGGING_GROUPS = ("hydra/hydra_logging", "hydra/job_logging")


@contextmanager
def config_store_scope(*, isolate: bool = False) -> Iterator[None]:
    """Restore Hydra's global config store when the block ends.

    Args:
        isolate: If True, the block starts from a store holding only Hydra's
            own entries, so it sees no configs that other code added.
    """
    store = ConfigStore.instance()
    saved = store.repo
    if isolate:
        store.repo = {key: copy.deepcopy(saved[key]) for key in _HYDRA_ENTRIES if key in saved}
    else:
        store.repo = copy.deepcopy(saved)
    try:
        yield
    finally:
        hydra_group = store.repo.get("hydra")
        store.repo = saved
        if hydra_group is not None:
            saved["hydra"] = hydra_group


def without_logging_setup(overrides: list[str]) -> list[str]:
    """Add overrides that stop Hydra from configuring logging.

    A logging group the caller already overrides is left to the caller.

    Args:
        overrides: The caller's Hydra overrides.

    Returns:
        A new override list.
    """
    chosen = {override.split("=", 1)[0].lstrip("+~") for override in overrides}
    return [*overrides, *(f"{group}=none" for group in _LOGGING_GROUPS if group not in chosen)]
