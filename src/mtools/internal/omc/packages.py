"""Find the package a Modelica source file belongs to."""

from __future__ import annotations

from pathlib import Path


def package_root(source: Path) -> Path:
    """Return the top-level package directory of ``source``, or ``source`` itself.

    A file belongs to a package when its directory holds a ``package.mo``. The root is
    the outermost directory of an unbroken chain of such directories. A file outside any
    package (or a ``package.mo`` alone in its directory) is its own root.
    """
    source = Path(source).absolute()
    directory = source.parent
    if not (directory / "package.mo").is_file():
        return source
    while (directory.parent / "package.mo").is_file():
        directory = directory.parent
    return directory
