"""Keep Hydra's process-wide state out of the caller's process.

Composing or launching through Hydra writes into two process-wide places: the
global ``ConfigStore`` and, for a launch, the logging configuration. mtools
runs Hydra inside the caller's process, so it scopes both to the call.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Protocol

from hydra.core.config_store import ConfigStore
from hydra_zen import ZenStore

# Entries Hydra registers itself. Its ``hydra`` group also grows lazily while
# Hydra runs, so that group is carried over rather than restored.
_HYDRA_ENTRIES = ("hydra", "_dummy_empty_config_.yaml")

# Hydra's ``none`` presets set ``root: null``, so Hydra skips
# ``logging.config.dictConfig``: it neither changes levels and handlers nor
# closes the caller's handlers.
_LOGGING_GROUPS = ("hydra/hydra_logging", "hydra/job_logging")


class ActivatableRegistry(Protocol):
    """A registry a run can resolve its configs from, without changing it."""

    def activated(self) -> AbstractContextManager[None]:
        """Let Hydra see exactly this registry's configs inside the block."""
        ...


def _copy_groups(repo: dict[str, Any]) -> dict[str, Any]:
    """Copy the store's group dicts and share its config nodes.

    ``ConfigStore.store`` writes into the group dicts in place but always
    stores a new node, and ``ConfigStore.load`` hands out copies, so stored
    nodes are never changed.
    """
    return {key: _copy_groups(value) if isinstance(value, dict) else value for key, value in repo.items()}


@contextmanager
def config_store_scope(*, isolate: bool = False) -> Iterator[None]:
    """Restore Hydra's global config store when the block ends.

    Args:
        isolate: If True, the block starts from a store holding only Hydra's
            own entries, so it sees no configs that other code added.
    """
    store = ConfigStore.instance()
    saved = store.repo
    visible = {key: saved[key] for key in _HYDRA_ENTRIES if key in saved} if isolate else saved
    store.repo = _copy_groups(visible)
    try:
        yield
    finally:
        hydra_group = store.repo.get("hydra")
        store.repo = saved
        if hydra_group is not None:
            saved["hydra"] = hydra_group


@contextmanager
def store_scope(zen_store: ZenStore) -> Iterator[None]:
    """Let Hydra see exactly Hydra's own entries and ``zen_store``'s for the block.

    The entries are read from ``zen_store``, not added through it, so the
    ZenStore's own record of what it has added stays unchanged.
    """
    with config_store_scope(isolate=True):
        config_store = ConfigStore.instance()
        for entry in zen_store:
            config_store.store(**entry)
        yield


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
