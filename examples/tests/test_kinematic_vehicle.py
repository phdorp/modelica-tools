from abc import ABC
from typing import ClassVar

import numpy as np
import pandas as pd
import pytest
from kinematic_vehicle.kinematic_vehicle import MODEL_NAME, run_default
from tests.experiments import registry

import mtools.sim_tools as sim_tools


class ExperimentBase(ABC):
    result = MODEL_NAME
    eps = np.finfo(float).eps
    tol_position = 1e-2
    tol_angle = 1e-2
    tol_speed = 0.05
    stop_time = 10.0


class Experiment(ExperimentBase):

    name: ClassVar[str]
    solutions: ClassVar[pd.DataFrame]

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_experiment(cls):
        cls.solutions = sim_tools.simulate(
            registry.compose(config_name="default", overrides=[f"experiment={cls.name}"])
        )[cls.result]


class Experiments(ExperimentBase):

    name: ClassVar[str | list[str]]
    solutions: ClassVar[dict[str, pd.DataFrame]]

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_experiment(cls):
        cls.solutions = {}
        for name in cls.name:
            cls.solutions[name] = sim_tools.simulate(
                registry.compose(config_name="default", overrides=[f"experiment={name}"])
            )[cls.result]


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
        assert isinstance(px_vals, np.ndarray)
        assert np.all(np.diff(px_vals) >= -self.eps), "px should increase monotonically"

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


class TestTurnLeft(ExperimentBase):

    name = "turn_left"
    phis = [np.deg2rad(0.1), np.deg2rad(0.5), np.deg2rad(1.0)]
    results: ClassVar[list] = []

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_sweep(cls, tmp_path_factory):
        sweep = ",".join(str(phi) for phi in cls.phis)
        cls.results = sim_tools.simulate(
            run_default,
            overrides=[f"experiment={cls.name}", f"session.parameters.phi={sweep}"],
            multirun=True,
            sweep_dir=str(tmp_path_factory.mktemp("turn_sweep")),
        )
        cls.results = sorted(cls.results, key=lambda r: r.config["session"]["parameters"]["phi"])

    def test_sweep_covers_all_angles(self):
        assert [r.config["session"]["parameters"]["phi"] for r in self.results] == pytest.approx(self.phis)

    def test_monotonic_heading_rotation(self):
        for r in self.results:
            theta_vals = r.solutions[self.result]["state.theta"].values
            assert isinstance(theta_vals, np.ndarray)
            assert np.all(np.diff(theta_vals) >= -self.eps), "theta should increase for left turn"

    def test_final_position_first_quadrant(self):
        for r in self.results:
            final_px = r.solutions[self.result]["state.px"].iloc[-1]
            final_py = r.solutions[self.result]["state.py"].iloc[-1]
            assert final_px > 0, f"final px should be positive, got {final_px}"
            assert final_py > 0, f"final py should be positive, got {final_py}"

    def test_no_singular_heading(self):
        for r in self.results:
            final_theta = abs(r.solutions[self.result]["state.theta"].iloc[-1])
            assert final_theta < np.pi / 2, f"final heading |theta| should be < pi/2, got {final_theta}"

    def test_monotonic_turn_with_phi(self):
        thetas = [r.solutions[self.result]["state.theta"].iloc[-1] for r in self.results]
        assert thetas == sorted(thetas), f"final theta should increase with phi, got {thetas}"
        assert len(set(thetas)) == len(thetas), "each phi should give a distinct final theta"


class TestVelocityIncrease(Experiments):

    name: ClassVar[list[str]] = ["standstill", "straight_driving"]

    def test_monotonic_speed_increase(self):
        standstill = self.solutions["standstill"]
        straight_driving = self.solutions["straight_driving"]
        assert np.all(
            straight_driving["der(state.px)"].to_numpy() - standstill["der(state.px)"].to_numpy() >= 0.0
        ), "speed should increase monotonically"
