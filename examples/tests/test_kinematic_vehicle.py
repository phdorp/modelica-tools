from typing import ClassVar

import numpy as np
import pytest
from kinematic_vehicle.kinematic_vehicle import registry as kinematic_registry

from mtools.testing import Experiment, Experiments, ExperimentSweep, SweepValue


@pytest.fixture(scope="module")
def registry():
    return kinematic_registry


class TestStandstill(Experiment):

    name = "standstill"

    def test_position_unchanged(self):
        np.testing.assert_array_less(self.results["vehicle.px"].abs(), self.eps, "px should remain ~0.0")
        np.testing.assert_array_less(self.results["vehicle.py"].abs(), self.eps, "py should remain ~0.0")
        np.testing.assert_array_less(
            self.results["vehicle.theta"].abs(), self.eps, "theta should remain ~0.0"
        )

    def test_protected_columns_hidden_by_default(self):
        for column in ("vehicle.px_dot", "vehicle.py_dot", "vehicle.theta_dot"):
            assert column not in self.results.columns


class TestStraightDriving(ExperimentSweep):

    name = "straight_driving"
    # `v_norm` demonstrates int sweep values.
    sweep_params: ClassVar[dict[str, list[SweepValue]]] = {"v_norm": [5, 10]}

    def test_monotonic_forward_motion(self):
        for result in self.results.values():
            px_vals = result["vehicle.px"].to_numpy()
            assert np.all(np.diff(px_vals) >= -self.eps), "px should increase monotonically"

    def test_final_position_matches_velocity(self):
        for result in self.results.values():
            px0 = result["vehicle.px"].iloc[0]
            expected_px = px0 + result["time"].iloc[-1] * result["der(vehicle.px)"].iloc[-1]
            np.testing.assert_allclose(result["vehicle.px"].iloc[-1], expected_px)

    def test_no_lateral_drift(self):
        for result in self.results.values():
            py0 = result["vehicle.py"].iloc[0]
            np.testing.assert_array_less(
                (result["vehicle.py"] - py0).abs(),
                self.eps,
                f"py should remain near {py0} with zero steering",
            )

    def test_heading_unchanged(self):
        for result in self.results.values():
            np.testing.assert_array_less(
                result["vehicle.theta"].abs(), self.eps, "theta should remain near 0.0 with zero steering"
            )

    def test_constant_speed(self):
        for result in self.results.values():
            vel = np.sqrt(result["der(vehicle.px)"] ** 2 + result["der(vehicle.py)"] ** 2)
            np.testing.assert_allclose(vel, vel[0])


class TestTurnLeft(ExperimentSweep):

    name = "turn_left"
    sweep_params: ClassVar[dict[str, list[SweepValue]]] = {
        "phi": [np.deg2rad(0.1), np.deg2rad(0.5), np.deg2rad(1.0)]
    }

    def test_monotonic_heading_rotation(self):
        for result in self.results.values():
            theta_vals = result["vehicle.theta"].to_numpy()
            assert np.all(np.diff(theta_vals) >= -self.eps), "theta should increase for left turn"

    def test_final_position_first_quadrant(self):
        for result in self.results.values():
            final_px = result["vehicle.px"].iloc[-1]
            final_py = result["vehicle.py"].iloc[-1]
            assert final_px > 0, f"final px should be positive, got {final_px}"
            assert final_py > 0, f"final py should be positive, got {final_py}"

    def test_no_singular_heading(self):
        for result in self.results.values():
            final_theta = abs(result["vehicle.theta"].iloc[-1])
            assert final_theta < np.pi / 2, f"final heading |theta| should be < pi/2, got {final_theta}"


class TestWheelbase(ExperimentSweep):

    name = "turn_left"
    sweep_params: ClassVar[dict[str, list[SweepValue]]] = {"wheelbase": [2.0, 4.0]}

    def test_longer_wheelbase_turns_slower(self):
        short = self.results[(2.0,)]
        long = self.results[(4.0,)]
        assert abs(long["vehicle.theta"].iloc[-1]) < abs(short["vehicle.theta"].iloc[-1])


class TestVelocityIncrease(Experiments):

    name: list[str] = ["standstill", "straight_driving"]  # noqa: RUF012 - shared immutable test config

    def test_monotonic_speed_increase(self):
        standstill = self.results["standstill"]
        straight_driving = self.results["straight_driving"]
        assert np.all(
            straight_driving["der(vehicle.px)"].to_numpy()
            - standstill["der(vehicle.px)"].to_numpy()
            >= -self.eps
        ), "speed should increase monotonically"


class TestProtectedOutput(Experiment):

    name = "protected_output"

    def test_protected_columns_present(self):
        for column in ("vehicle.px_dot", "vehicle.py_dot", "vehicle.theta_dot"):
            assert column in self.results.columns

    def test_protected_derivatives_match_state_derivatives(self):
        for name, state in (("px", "vehicle.px"), ("py", "vehicle.py"), ("theta", "vehicle.theta")):
            np.testing.assert_allclose(self.results[f"vehicle.{name}_dot"], self.results[f"der({state})"])


def test_example_builds_and_solves_with_cpp_target():
    config = kinematic_registry.compose("default")

    assert config.model_name == "kinematic_vehicle.WrapperKinematicVehicle"
    assert config.session.parameters.v_norm == 10.0
    assert config.session.parameters.phi == 0.0
    assert config.session.parameters.wheelbase == 2.0
    assert config.session.build_options.omc_build_flags["--simCodeTarget"] == "Cpp"
    assert config.session.sim_configurations.solver == "dassl"


def test_protected_output_experiment_keeps_cpp_solver():
    config = kinematic_registry.compose_experiment("protected_output")

    assert config.session.sim_configurations.solver == "dassl"
    assert config.session.sim_configurations.emit_protected is True
