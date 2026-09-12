from typing import ClassVar

import numpy as np
import pytest
from mtools.testing import Experiment, Experiments, ExperimentSweep, SweepValue

from kinematic_vehicle.kinematic_vehicle import MODEL_NAME
from tests.experiments import registry as kinematic_registry


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
    # `state_0` is swept as a whole object parameterized by tuples
    # (dicts like {"px": ..., "py": ..., "theta": ...} work too);
    # `v_norm` demonstrates int sweep values.
    sweep_params: ClassVar[dict[str, list[SweepValue]]] = {
        "state_0": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        "v_norm": [5, 10],
    }

    def test_monotonic_forward_motion(self):
        for result in self.results.values():
            px_vals = result["state.px"].to_numpy()
            assert np.all(np.diff(px_vals) >= -self.eps), "px should increase monotonically"

    def test_final_position_matches_velocity(self):
        for result in self.results.values():
            px0 = result["state.px"].iloc[0]
            expected_px = px0 + result["time"].iloc[-1] * result["der(state.px)"].iloc[-1]
            np.testing.assert_allclose(result["state.px"].iloc[-1], expected_px)

    def test_no_lateral_drift(self):
        for result in self.results.values():
            py0 = result["state.py"].iloc[0]
            np.testing.assert_array_less(
                (result["state.py"] - py0).abs(),
                self.eps,
                f"py should remain near {py0} with zero steering",
            )

    def test_heading_unchanged(self):
        for result in self.results.values():
            np.testing.assert_array_less(
                result["state.theta"].abs(), self.eps, "theta should remain near 0.0 with zero steering"
            )

    def test_constant_speed(self):
        for result in self.results.values():
            vel = np.sqrt(result["der(state.px)"] ** 2 + result["der(state.py)"] ** 2)
            np.testing.assert_allclose(vel, vel[0])

class TestTurnLeft(ExperimentSweep):

    name = "turn_left"
    sweep_params: ClassVar[dict[str, list[SweepValue]]] = {
        "phi": [np.deg2rad(0.1), np.deg2rad(0.5), np.deg2rad(1.0)]
    }

    def test_monotonic_heading_rotation(self):
        for result in self.results.values():
            theta_vals = result["state.theta"].to_numpy()
            assert np.all(np.diff(theta_vals) >= -self.eps), "theta should increase for left turn"

    def test_final_position_first_quadrant(self):
        for result in self.results.values():
            final_px = result["state.px"].iloc[-1]
            final_py = result["state.py"].iloc[-1]
            assert final_px > 0, f"final px should be positive, got {final_px}"
            assert final_py > 0, f"final py should be positive, got {final_py}"

    def test_no_singular_heading(self):
        for result in self.results.values():
            final_theta = abs(result["state.theta"].iloc[-1])
            assert final_theta < np.pi / 2, f"final heading |theta| should be < pi/2, got {final_theta}"

class TestVelocityIncrease(Experiments):

    name: list[str] = ["standstill", "straight_driving"]  # noqa: RUF012 - shared immutable test config

    def test_monotonic_speed_increase(self):
        standstill = self.results["standstill"]
        straight_driving = self.results["straight_driving"]
        assert np.all(
            straight_driving["der(state.px)"].to_numpy() - standstill["der(state.px)"].to_numpy() >= -self.eps
        ), "speed should increase monotonically"
