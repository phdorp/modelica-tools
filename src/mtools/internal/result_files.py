"""Save results as `.mat` or `.csv` files and read them back, chosen by file suffix."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from mtools.internal.omc import matfile

#: Formats ``save_solutions`` writes; each is also the file suffix.
OUTPUT_FORMATS = ("mat", "csv")


def write_solutions(solutions: Mapping[str, pd.DataFrame], output_path: str | Path, output_format: str) -> None:
    """Write each result to ``<output_path>/<name>.<output_format>``.

    Raises:
        ValueError: ``output_format`` is not one of :data:`OUTPUT_FORMATS`, or a
            result cannot be saved as `.mat`.
    """
    if output_format not in OUTPUT_FORMATS:
        raise ValueError(f"output_format: expected one of {_formats()}, got {output_format!r}")
    for name, solution in solutions.items():
        path = Path(output_path) / f"{name}.{output_format}"
        if output_format == "mat":
            matfile.write_result(path, solution)
        else:
            solution.to_csv(path, index=False)


def read_result_file(path: str | Path) -> pd.DataFrame:
    """Read a saved `.mat` or `.csv` result, or an OMC `.mat` result file.

    Raises:
        ValueError: The suffix is neither ``.mat`` nor ``.csv``, or the `.mat` file is
            not in OMC's binTrans layout.
    """
    path = Path(path)
    if path.suffix == ".mat":
        return matfile.read_result(path)
    if path.suffix == ".csv":
        return pd.read_csv(path)
    raise ValueError(f"{path}: expected a result file ending in {_formats('.')}")


def _formats(prefix: str = "") -> str:
    return ", ".join(repr(prefix + output_format) for output_format in OUTPUT_FORMATS)
