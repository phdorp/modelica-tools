import math
import subprocess

import numpy as np
from hydra import compose, initialize
import mtools.sim_tools as sim_tools
import pytest
import tests.experiments


def _openmodelica_available() -> bool:
    try:
        result = subprocess.run(
            ["omc", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_solution_df(solutions, name="KinematicVehicle"):
    if name in solutions:
        return solutions[name]
    for key in solutions:
        if "state" in key.lower() or "Kinematic" in key:
            return solutions[key]
    raise ValueError(f"Could not find solution dataframe in {list(solutions.keys())}")


POSITION_TOL = 1e-2
ANGLE_TOL = 1e-2
SPEED_TOL = 0.05
DEFAULT_STOP_TIME = 10.0


def _ensure_omc_available():
    if not _openmodelica_available():
        pytest.skip("OpenModelica (omc) not available")


@pytest.fixture
def run_experiment():

    def _run_experiment(experiment):
        with initialize(version_base=None, config_path=None):
            solutions = sim_tools.simulate(compose(config_name="default", overrides=list({f"experiment={experiment}"})))
            return solutions

    return _run_experiment


@pytest.fixture
def standstill_df(run_experiment):
    _ensure_omc_available()
    solutions = run_experiment("standstill")
    return get_solution_df(solutions)


class TestStandstill:
    def test_position_unchanged(self, standstill_df):
        df = standstill_df
        assert df["state.px"].abs().max() < POSITION_TOL, "px should remain ~0.0"
        assert df["state.py"].abs().max() < POSITION_TOL, "py should remain ~0.0"
        assert df["state.theta"].abs().max() < ANGLE_TOL, "theta should remain ~0.0"


@pytest.fixture
def straight_driving_df(run_experiment):
    _ensure_omc_available()
    solutions = run_experiment("straight_driving")
    return get_solution_df(solutions)


class TestStraightDriving:
    def test_monotonic_forward_motion(self, straight_driving_df):
        df = straight_driving_df
        px_vals = df["state.px"].values
        assert all(
            px_vals[i] <= px_vals[i + 1] + 1e-6 for i in range(len(px_vals) - 1)
        ), "px should increase monotonically"

    def test_final_position_matches_velocity(self, straight_driving_df):
        df = straight_driving_df
        expected_px = 10.0 * DEFAULT_STOP_TIME
        final_px = df["state.px"].iloc[-1]
        assert final_px == pytest.approx(expected_px, rel=SPEED_TOL), f"px should be ~{expected_px}, got {final_px}"

    def test_no_lateral_drift(self, straight_driving_df):
        df = straight_driving_df
        assert df["state.py"].abs().max() < POSITION_TOL, "py should remain near 0.0 with zero steering"

    def test_heading_unchanged(self, straight_driving_df):
        df = straight_driving_df
        assert df["state.theta"].abs().max() < ANGLE_TOL, "theta should remain near 0.0 with zero steering"

    def test_speed_matches_v_norm(self, straight_driving_df):
        df = straight_driving_df
        px_dot = df["der(state.px)"]
        py_dot = df["der(state.py)"]
        vel = np.sqrt(px_dot**2 + py_dot**2)
        expected_speed = 10.0
        assert all(
            (vel - expected_speed) / expected_speed < SPEED_TOL
        ), f"speed should be ~{expected_speed} within {SPEED_TOL*100}%"


@pytest.fixture
def turn_left_df(run_experiment):
    _ensure_omc_available()
    solutions = run_experiment("turn_left")
    return get_solution_df(solutions)


class TestTurnLeft:
    def test_monotonic_heading_rotation(self, turn_left_df):
        df = turn_left_df
        theta_vals = df["state.theta"].values
        assert all(
            theta_vals[i] < theta_vals[i + 1] + 1e-6 for i in range(len(theta_vals) - 1)
        ), "theta should increase for left turn"

    def test_final_position_first_quadrant(self, turn_left_df):
        df = turn_left_df
        final_px = df["state.px"].iloc[-1]
        final_py = df["state.py"].iloc[-1]
        assert final_px > 0, f"final px should be positive, got {final_px}"
        assert final_py > 0, f"final py should be positive, got {final_py}"

    def test_no_singular_heading(self, turn_left_df):
        df = turn_left_df
        final_theta = abs(df["state.theta"].iloc[-1])
        assert final_theta < math.pi / 2, f"final heading |theta| should be < pi/2, got {final_theta}"
