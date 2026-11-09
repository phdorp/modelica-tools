"""Save results as `.mat` or `.csv` files and read them back, chosen by file suffix."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from mtools.internal.omc import matfile
from mtools.session_config import OutputFormat

#: Formats ``save_solutions`` writes; each is also the file suffix.
OUTPUT_FORMATS: tuple[OutputFormat, ...] = ("mat", "csv")

#: File suffixes of saved results, ``.mat`` and ``.csv``.
RESULT_SUFFIXES = tuple(f".{output_format}" for output_format in OUTPUT_FORMATS)


def output_format_problem(output_format: object) -> str | None:
    """Return why ``output_format`` is invalid, or ``None`` when it is a known format."""
    if output_format in OUTPUT_FORMATS:
        return None
    formats = ", ".join(map(repr, OUTPUT_FORMATS))
    return f"output_format: expected one of {formats}, got {output_format!r}"


def write_solutions(
    solutions: Mapping[str, pd.DataFrame], output_path: str | Path, output_format: OutputFormat
) -> None:
    """Write each result to ``<output_path>/<name>.<output_format>``.

    Args:
        solutions: Results keyed by model name.
        output_path: Existing directory the files are written to.
        output_format: One of :data:`OUTPUT_FORMATS`.

    Raises:
        ValueError: ``output_format`` is not one of :data:`OUTPUT_FORMATS`, or a
            result cannot be saved as `.mat`.
    """
    if (problem := output_format_problem(output_format)) is not None:
        raise ValueError(problem)
    for name, solution in solutions.items():
        path = Path(output_path) / f"{name}.{output_format}"
        if output_format == "mat":
            matfile.write_result(path, solution)
        else:
            solution.to_csv(path, index=False)


def is_result_file(path: Path) -> bool:
    """Whether ``path`` is a `.csv` file or a `.mat` file in OMC's result layout.

    Args:
        path: The file to check; only the header of a `.mat` file is read.
    """
    if path.suffix == ".mat":
        return matfile.is_result_file(path)
    return path.suffix == ".csv"


def read_result_file(path: str | Path) -> pd.DataFrame:
    """Read a saved `.mat` or `.csv` result, or an OMC `.mat` result file.

    Args:
        path: The file to read; its suffix selects the format.

    Raises:
        ValueError: The suffix is neither ``.mat`` nor ``.csv``, or the `.mat` file is
            not in OMC's binTrans layout.
    """
    path = Path(path)
    if path.suffix == ".mat":
        return matfile.read_result(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"{path}: expected a result file ending in {' or '.join(RESULT_SUFFIXES)}")
