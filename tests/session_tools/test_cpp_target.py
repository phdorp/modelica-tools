"""The same run config on both simulation targets, through ``sim_tools.simulate``."""

from __future__ import annotations

import hydra_zen
import numpy as np
import pytest
from models.kinematic_vehicle import run_default

from mtools.sim_tools import simulate

TARGETS = ["C", "Cpp"]


def _simulate(tmp_path, overrides):
    job = hydra_zen.launch(
        run_default,
        simulate,
        [*overrides, f"hydra.run.dir={tmp_path}", "hydra.job.chdir=False"],
        with_log_configuration=False,
        version_base=None,
    )
    return job.return_value["KinematicVehicle"]


@pytest.mark.parametrize("target", TARGETS)
def test_target_override_builds_and_solves(tmp_path, target):
    solution = _simulate(tmp_path, [f"build.target={target}", "settings.stop_time=1.0"])

    assert solution["time"].values[0] == 0.0
    assert solution["time"].values[-1] == pytest.approx(1.0)
    np.testing.assert_allclose(solution["state.px"], 10.0 * solution["time"], rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(solution["state.py"], 0.0, atol=1e-12)
    for column in ("px_dot", "py_dot", "theta_dot"):
        assert column not in solution.columns


@pytest.mark.parametrize("target", TARGETS)
def test_protected_variables_emitted_when_enabled(tmp_path, target):
    solution = _simulate(tmp_path, [f"build.target={target}", "settings.emit_protected=true"])

    for column in ("px_dot", "py_dot", "theta_dot"):
        assert column in solution.columns


@pytest.mark.parametrize("solver", ["cvode", "ida"])
def test_c_and_cpp_agree(tmp_path, solver):
    overrides = [
        "settings.parameters.phi=0.1",
        "settings.stop_time=2.0",
        "settings.interval=0.01",
        "settings.tolerance=1e-10",
        f"settings.solver={solver}",
    ]
    c = _simulate(tmp_path / "C", ["build.target=C", *overrides])
    cpp = _simulate(tmp_path / "Cpp", ["build.target=Cpp", *overrides])

    assert list(cpp.columns) == list(c.columns)
    assert len(cpp) == len(c)
    # The runtimes step through the grid differently, so grid times can differ in the last bit.
    np.testing.assert_allclose(cpp["time"], c["time"], rtol=1e-14, atol=0)
    for column in c.columns:
        np.testing.assert_allclose(cpp[column], c[column], rtol=1e-7, atol=1e-9, err_msg=column)
