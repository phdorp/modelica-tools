import mtools.sim_tools as sim_tools
import numpy as np
import pytest
from hydra import compose, initialize

import tests.experiments


class Experiment:
    result = "KinematicVehicle"
    tol_position = 1e-2
    tol_angle = 1e-2
    tol_speed = 0.05
    stop_time = 10.0

    @pytest.fixture(autouse=True)
    def run_experiment(self):
        try:
            with initialize(version_base=None, config_path=None):
                self.solutions = sim_tools.simulate(
                    compose(config_name="default", overrides=list({f"experiment={self.name}"}))
                )[self.result]
        except RuntimeError as error:
            raise error


class TestStandstill(Experiment):
    name = "standstill"

    def test_position_unchanged(self):
        assert self.solutions["state.px"].abs().max() < self.tol_position, "px should remain ~0.0"
        assert self.solutions["state.py"].abs().max() < self.tol_position, "py should remain ~0.0"
        assert self.solutions["state.theta"].abs().max() < self.tol_angle, "theta should remain ~0.0"


class TestStraightDriving(Experiment):
    name = "straight_driving"

    def test_monotonic_forward_motion(self):
        px_vals = self.solutions["state.px"].values
        assert all(
            px_vals[i] <= px_vals[i + 1] + 1e-6 for i in range(len(px_vals) - 1)
        ), "px should increase monotonically"

    def test_final_position_matches_velocity(self):
        expected_px = self.solutions["time"].iloc[-1] * self.solutions["der(state.px)"].iloc[-1]
        final_px = self.solutions["state.px"].iloc[-1]
        assert final_px == pytest.approx(
            expected_px, rel=self.tol_speed
        ), f"px should be ~{expected_px}, got {final_px}"

    def test_no_lateral_drift(self):
        assert (
            self.solutions["state.py"].abs().max() < self.tol_position
        ), "py should remain near 0.0 with zero steering"

    def test_heading_unchanged(self):
        assert (
            self.solutions["state.theta"].abs().max() < self.tol_angle
        ), "theta should remain near 0.0 with zero steering"

    def test_speed_matches_v_norm(self):
        px_dot = self.solutions["der(state.px)"]
        py_dot = self.solutions["der(state.py)"]
        vel = np.sqrt(px_dot**2 + py_dot**2)
        expected_speed = 10.0
        assert all(
            (vel - expected_speed) / expected_speed < self.tol_speed
        ), f"speed should be ~{expected_speed} within {self.tol_speed*100}%"


class TestTurnLeft(Experiment):
    name = "turn_left"

    def test_monotonic_heading_rotation(self):
        theta_vals = self.solutions["state.theta"].values
        assert all(
            theta_vals[i] < theta_vals[i + 1] + 1e-6 for i in range(len(theta_vals) - 1)
        ), "theta should increase for left turn"

    def test_final_position_first_quadrant(self):
        final_px = self.solutions["state.px"].iloc[-1]
        final_py = self.solutions["state.py"].iloc[-1]
        assert final_px > 0, f"final px should be positive, got {final_px}"
        assert final_py > 0, f"final py should be positive, got {final_py}"

    def test_no_singular_heading(self):
        final_theta = abs(self.solutions["state.theta"].iloc[-1])
        assert final_theta < np.pi / 2, f"final heading |theta| should be < pi/2, got {final_theta}"
