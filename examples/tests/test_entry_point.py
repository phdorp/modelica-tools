"""``python -m kinematic_vehicle`` saves the result in Hydra's run directory as `.mat` or `.csv`."""

import subprocess
import sys
from pathlib import Path

import pytest
from kinematic_vehicle.kinematic_vehicle import MODEL_NAME

from mtools.sim_tools import load_solution


def _run(output_dir: Path, *overrides: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "kinematic_vehicle", f"hydra.run.dir={output_dir}", *overrides],
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    ("overrides", "suffix"), [pytest.param((), "mat", id="default"), pytest.param(("output_format=csv",), "csv", id="csv")]
)
def test_the_result_is_saved_in_the_chosen_format(tmp_path: Path, overrides, suffix):
    _run(tmp_path, *overrides)

    saved = sorted(path.name for path in tmp_path.glob(f"{MODEL_NAME}.*"))
    assert saved == [f"{MODEL_NAME}.{suffix}"]
    result = load_solution(tmp_path / saved[0])
    assert result.columns[0] == "time"
    assert result["time"].iloc[-1] == pytest.approx(10.0)
