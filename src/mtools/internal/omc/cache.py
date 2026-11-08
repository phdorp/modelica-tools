"""The build cache: content-hash keys, validating a hit, and publishing a build.

A key is a hash of everything that determines a build's content, never of timestamps.
A hit must also pass validation: every package on the build's input list
(``getLoadedLibraries()``) must still hash to the value recorded when it was built.
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from mtools.internal.omc import workdir
from mtools.internal.omc.config import BuildConfig, Library
from mtools.internal.omc.script import Experiment, LoadedLibrary, build_script

logger = logging.getLogger(__name__)

# Bump when a change to the backend alters builds without altering the build script.
BACKEND_REVISION = "1"
RECORD_NAME = "mtools-build.json"


@dataclass(frozen=True)
class BuildRecord:
    """What a cached build stores next to its files.

    Attributes:
        experiment: The model's experiment annotation.
        loaded_libraries: The build's input list, ``getLoadedLibraries()``.
        hashes: Input hash per entry of ``loaded_libraries``, in the same order.
    """

    experiment: Experiment
    loaded_libraries: tuple[LoadedLibrary, ...]
    hashes: tuple[str, ...]


def package_root(path: Path) -> Path:
    """Return what a source file brings with it: its top-level package directory.

    A file in a directory with a ``package.mo`` belongs to that package, and the
    package to its parent package if that directory has a ``package.mo`` too. A file
    outside any package is its own root. A directory is treated as a package.
    """
    path = Path(path).absolute()
    if path.is_dir():
        root = path
    elif path.name == "package.mo" or (path.parent / "package.mo").exists():
        root = path.parent
    else:
        return path
    while (root.parent / "package.mo").exists():
        root = root.parent
    return root


def hash_path(path: Path) -> str:
    """Return a content hash of a file, or of a directory's relative names and contents."""
    digest = hashlib.sha256()
    path = Path(path)
    if path.is_dir():
        for file in sorted(path.rglob("*")):
            if file.is_file():
                digest.update(file.relative_to(path).as_posix().encode() + b"\0")
                digest.update(_file_hash(file).encode())
    elif path.is_file():
        digest.update(_file_hash(path).encode())
    else:
        digest.update(b"missing")
    return digest.hexdigest()


def cache_key(config: BuildConfig, build_values: Mapping[str, str] | None = None) -> str:
    """Return the cache key of ``config``.

    Args:
        config: The build config.
        build_values: Parameter values fixed at build time (build variants), by name.
            Different values give different keys.
    """
    sources = [
        {"root": hash_path(root), "file": _relative(Path(source), root)}
        for source in [*config.extra_sources, config.model_path]
        for root in [package_root(Path(source))]
    ]
    libraries = [
        {"name": library.name, "version": library.version, "directory": _directory_hash(library)}
        for library in config.libraries
    ]
    description = {
        "model": config.model_name,
        "sources": sources,
        "libraries": libraries,
        "target": config.target,
        "omc_flags": sorted((name, value) for name, value in config.omc_flags.items()),
        "build_values": sorted((build_values or {}).items()),
        "omc": omc_version(),
        "compiler": compiler_version(),
        "backend": backend_version(),
    }
    return hashlib.sha256(json.dumps(description, sort_keys=True).encode()).hexdigest()


@functools.cache
def omc_version() -> str:
    return _tool_version(["omc", "--version"])


@functools.cache
def compiler_version() -> str:
    return _tool_version([os.environ.get("CC") or "gcc", "--version"])


@functools.cache
def backend_version() -> str:
    """Return a version that changes whenever the build-script template changes."""
    sample = BuildConfig(
        model_path=Path("model.mo"),
        model_name="Model",
        target="Cpp",
        extra_sources=(Path("extra.mo"),),
        libraries=(Library("Lib", "1.0", Path("libs")), Library("Other")),
        omc_flags={"-d": "nogen", "--flag": None},
    )
    template = hashlib.sha256(build_script(sample, "model").encode()).hexdigest()
    return f"{BACKEND_REVISION}-{template[:16]}"


def library_hashes(config: BuildConfig, loaded: Iterable[LoadedLibrary]) -> tuple[str, ...]:
    """Return the input hash of each loaded library.

    A library that comes from the model's, an ``extra_sources`` entry's or a
    ``directory`` library's files is hashed by content. Any other (an installed
    library) is identified by name and path, which carries its version.
    """
    roots = _tracked_roots(config)
    hashes = []
    for library in loaded:
        path = library.path.absolute()
        touched = [root for root in roots if root == path or root in path.parents or path in root.parents]
        if touched:
            hashes.append("content:" + ",".join(hash_path(root) for root in touched))
        else:
            hashes.append(f"installed:{library.name}:{path}")
    return tuple(hashes)


def save_record(directory: Path, record: BuildRecord) -> None:
    (directory / RECORD_NAME).write_text(json.dumps(asdict(record), default=str))


def load_record(directory: Path) -> BuildRecord | None:
    """Read a build's record; ``None`` if missing or unreadable."""
    try:
        data = json.loads((directory / RECORD_NAME).read_text())
        return BuildRecord(
            experiment=Experiment(**data["experiment"]),
            loaded_libraries=tuple(LoadedLibrary(item["name"], Path(item["path"])) for item in data["loaded_libraries"]),
            hashes=tuple(data["hashes"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def lookup(key: str, config: BuildConfig) -> tuple[Path, BuildRecord] | None:
    """Return the valid cached build for ``key``, or ``None``.

    A stale entry (a package changed since it was built) is removed.
    """
    directory = workdir.builds_dir() / key
    if not directory.is_dir():
        return None
    record = load_record(directory)
    if record is not None and library_hashes(config, record.loaded_libraries) == record.hashes:
        return directory, record
    logger.debug("Discarding stale cached build %s", directory)
    _remove(directory)
    return None


def publish(directory: Path, key: str) -> tuple[Path, bool]:
    """Move the finished build ``directory`` into the cache in one step.

    Returns:
        The cached directory and whether this call published it. ``False`` means
        another process published ``key`` first; ``directory`` is deleted and the
        cached copy is the one to use.
    """
    target = workdir.builds_dir() / key
    try:
        os.rename(directory, target)
    except OSError:
        if not target.is_dir():
            raise
        shutil.rmtree(directory, ignore_errors=True)
        return target, False
    return target, True


def _remove(directory: Path) -> None:
    """Delete a cache entry; moved away first so a concurrent reader never sees half of it."""
    trash = workdir.tmp_dir() / f"stale-{os.getpid()}-{directory.name}"
    try:
        os.rename(directory, trash)
    except OSError:
        return  # another process removed or replaced it
    shutil.rmtree(trash, ignore_errors=True)


def _tracked_roots(config: BuildConfig) -> list[Path]:
    roots = [package_root(Path(source)) for source in [*config.extra_sources, config.model_path]]
    roots += [library.directory.absolute() for library in config.libraries if library.directory is not None]
    return roots


def _directory_hash(library: Library) -> str | None:
    return None if library.directory is None else hash_path(library.directory)


def _relative(path: Path, root: Path) -> str:
    path = path.absolute()
    return "" if path == root else path.relative_to(root).as_posix()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tool_version(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, errors="replace", check=False)
    except OSError:
        return "unknown"
    return (completed.stdout + completed.stderr).strip()
