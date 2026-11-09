"""Where the backend keeps its files, and when it deletes them.

The work directory holds ``builds/`` (the build cache), ``runs/`` (run directories and
uncached builds) and ``tmp/`` (builds in progress, moved into ``builds/`` when done).
"""

from __future__ import annotations

import getpass
import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

WORK_DIR_VARIABLE = "MTOOLS_WORK_DIR"
NO_CACHE_VARIABLE = "MTOOLS_NO_CACHE"
KEEP_RUNS_VARIABLE = "MTOOLS_KEEP_RUNS"

# Relative ``MTOOLS_WORK_DIR`` values resolve against this directory: the one the
# process started in, not whatever a later ``chdir`` (e.g. Hydra's) moved to.
START_DIR = Path.cwd()


def work_dir() -> Path:
    """Return the work directory; ``MTOOLS_WORK_DIR`` or ``<tempdir>/mtools-<user>``."""
    configured = os.environ.get(WORK_DIR_VARIABLE)
    if configured:
        return (START_DIR / configured).absolute()
    return Path(tempfile.gettempdir()) / f"mtools-{_user()}"


def builds_dir() -> Path:
    return _subdirectory("builds")


def runs_dir() -> Path:
    return _subdirectory("runs")


def tmp_dir() -> Path:
    return _subdirectory("tmp")


def no_cache() -> bool:
    return _enabled(NO_CACHE_VARIABLE)


def keep_runs() -> bool:
    return _enabled(KEEP_RUNS_VARIABLE)


def new_run_directory(prefix: str = "run-") -> Path:
    """Create a new, empty directory under ``runs/``."""
    return Path(tempfile.mkdtemp(prefix=prefix, dir=runs_dir()))


def new_tmp_directory(prefix: str = "build-") -> Path:
    """Create a new, empty directory under ``tmp/`` (same file system as ``builds/``)."""
    return Path(tempfile.mkdtemp(prefix=prefix, dir=tmp_dir()))


def discard(directory: Path) -> None:
    """Delete ``directory``, or keep it and log its path when ``MTOOLS_KEEP_RUNS`` is set."""
    if keep_runs():
        logger.info("Keeping %s (%s is set)", directory, KEEP_RUNS_VARIABLE)
    else:
        shutil.rmtree(directory, ignore_errors=True)


def with_run_directory(diagnostics: str, directory: Path) -> str:
    """Return ``diagnostics`` ending with the run directory when it is kept."""
    if not keep_runs():
        return diagnostics
    return "\n".join(filter(None, [diagnostics, f"Run directory: {directory}"]))


def _subdirectory(name: str) -> Path:
    directory = work_dir() / name
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _enabled(variable: str) -> bool:
    return os.environ.get(variable, "").strip().lower() in {"1", "true", "yes"}


def _user() -> str:
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return str(os.getuid())
