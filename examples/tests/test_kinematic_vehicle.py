from typing import ClassVar

import numpy as np
import pytest
from kinematic_vehicle.kinematic_vehicle import MODEL_NAME
from tests.experiments import registry as kinematic_registry

from mtools.testing import Experiment, Experiments, ExperimentSweep


@pytest.fixture(scope="module")
def model_name():
    return MODEL_NAME


@pytest.fixture(scope="module")
def registry():
    return kinematic_registry


class TestStandstill(Experiment):

    name = "standstill"

    def test_position_unchanged(self):
        np.testing.assert_array_less(self.results["state.px"].abs(), self.eps, "px should remain ~0.0")
        np.testing.assert_array_less(self.results["state.py"].abs(), self.eps, "py should remain ~0.0")
        np.testing.assert_array_less(self.results["state.theta"].abs(), self.eps, "theta should remain ~0.0")


class TestStraightDriving(ExperimentSweep):

    name = "straight_driving"
    sweep_params: ClassVar[dict[str, list[float]]] = {
        "state_0.px": [0.0, 1.0, 2.0],
        "state_0.py": [0.0, 1.0, 2.0],
    }

    def test_monotonic_forward_motion(self):
        for solutions in self.results.values():
            px_vals = solutions["state.px"].to_numpy()
            assert np.all(np.diff(px_vals) >= -self.eps), "px should increase monotonically"

    def test_final_position_matches_velocity(self):
        for (px0, _py0), solutions in self.results.items():
            expected_px = px0 + solutions["time"].iloc[-1] * solutions["der(state.px)"].iloc[-1]
            np.testing.assert_allclose(solutions["state.px"].iloc[-1], expected_px)

    def test_no_lateral_drift(self):
        for (_px0, py0), solutions in self.results.items():
            np.testing.assert_array_less(
                (solutions["state.py"] - py0).abs(),
                self.eps,
                f"py should remain near {py0} with zero steering",
            )

    def test_heading_unchanged(self):
        for solutions in self.results.values():
            np.testing.assert_array_less(
                solutions["state.theta"].abs(), self.eps, "theta should remain near 0.0 with zero steering"
            )

    def test_speed_matches_v_norm(self):
        for solutions in self.results.values():
            vel = np.sqrt(solutions["der(state.px)"] ** 2 + solutions["der(state.py)"] ** 2)
            np.testing.assert_allclose(vel, 10.0)

class TestTurnLeft(ExperimentSweep):

    name = "turn_left"
    sweep_params: ClassVar[dict[str, list[float]]] = {
        "phi": [np.deg2rad(0.1), np.deg2rad(0.5), np.deg2rad(1.0)]
    }

    def test_monotonic_heading_rotation(self):
        for solutions in self.results.values():
            theta_vals = solutions["state.theta"].to_numpy()
            assert np.all(np.diff(theta_vals) >= -self.eps), "theta should increase for left turn"

    def test_final_position_first_quadrant(self):
        for solutions in self.results.values():
            final_px = solutions["state.px"].iloc[-1]
            final_py = solutions["state.py"].iloc[-1]
            assert final_px > 0, f"final px should be positive, got {final_px}"
            assert final_py > 0, f"final py should be positive, got {final_py}"

    def test_no_singular_heading(self):
        for solutions in self.results.values():
            final_theta = abs(solutions["state.theta"].iloc[-1])
            assert final_theta < np.pi / 2, f"final heading |theta| should be < pi/2, got {final_theta}"

class TestVelocityIncrease(Experiments):

    name: list[str] = ["standstill", "straight_driving"]  # noqa: RUF012 - shared immutable test config

    def test_monotonic_speed_increase(self):
        standstill = self.results["standstill"]
        straight_driving = self.results["straight_driving"]
        assert np.all(
            straight_driving["der(state.px)"].to_numpy() - standstill["der(state.px)"].to_numpy() >= -self.eps
        ), "speed should increase monotonically"
