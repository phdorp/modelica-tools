"""The child process of an FMU run: ``python -m mtools.internal.fmu.child <run directory>``.

It reads the run request from the run directory, extracts the FMU there, runs it with
FMPy and saves the result as ``result.npy``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from mtools.internal.fmu.request import RunRequest

RESULT_FILE_NAME = "result.npy"


def main(argv: list[str]) -> int:
    """Run the request in the run directory ``argv[0]``; return the exit status."""
    import fmpy

    directory = Path(argv[0])
    request = RunRequest.read(directory)
    fmpy.extract(request.fmu_path, unzipdir=request.unzip_dir)
    result = fmpy.simulate_fmu(
        request.unzip_dir,
        fmi_type=request.fmi_type,
        start_time=request.start_time,
        stop_time=request.stop_time,
        step_size=request.interval,
        output_interval=request.interval,
        relative_tolerance=request.tolerance,
        solver=request.solver or "CVode",
        start_values=request.start_values,
        output=request.output,
        record_events=True,
        validate=False,
    )
    np.save(directory / RESULT_FILE_NAME, np.asarray(result), allow_pickle=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
