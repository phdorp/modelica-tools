from abc import ABC
from typing import ClassVar, Generic, TypeVar, cast

import numpy as np
import pandas as pd
import pytest
from kinematic_vehicle.kinematic_vehicle import MODEL_NAME, run_default
from tests.experiments import registry

from mtools import sim_tools

NameType = TypeVar("NameType", bound="str | list[str]")
ResultType = TypeVar("ResultType")
SweepResultType = TypeVar("SweepResultType")


class ExperimentBase(ABC):
    result = MODEL_NAME
    eps = np.finfo(float).eps


class ExperimentT(ExperimentBase, Generic[NameType, ResultType]):

    name: NameType
    results: ResultType

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_experiment(cls):
        names = [cls.name] if isinstance(cls.name, str) else cls.name
        results = {
            name: sim_tools.simulate(
                registry.compose(config_name="default", overrides=[f"experiment={name}"])
            )[cls.result]
            for name in names
        }
        cls.results = cast(ResultType, results[cls.name] if isinstance(cls.name, str) else results)


Experiment = ExperimentT[str, pd.DataFrame]
Experiments = ExperimentT[list[str], dict[str,pd.DataFrame]]


class ExperimentSweepT(ExperimentBase, Generic[NameType, SweepResultType]):

    name: NameType
    sweep_param: ClassVar[str]
    sweep_values: ClassVar[list[float]]
    results: SweepResultType
    base_run = run_default

    @classmethod
    def run_single_sweep(cls, name, tmp_path_factory):
        sweep = ",".join(str(value) for value in cls.sweep_values)
        sweep_results = sim_tools.simulate(
            cls.base_run,
            overrides=[f"experiment={name}", f"session.parameters.{cls.sweep_param}={sweep}"],
            multirun=True,
            sweep_dir=str(tmp_path_factory.mktemp(f"{name}_sweep")),
        )
        assert len(sweep_results) == len(cls.sweep_values), (
            f"expected {len(cls.sweep_values)} sweep results, got {len(sweep_results)}"
        )
        return dict(
            zip(cls.sweep_values, (result.solutions[cls.result] for result in sweep_results), strict=True)
        )

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_sweep(cls, tmp_path_factory):
        names = [cls.name] if isinstance(cls.name, str) else cls.name
        results = {name: cls.run_single_sweep(name, tmp_path_factory) for name in names}
        cls.results = cast(SweepResultType, results[cls.name] if isinstance(cls.name, str) else results)

ExperimentSweep = ExperimentSweepT[str, dict[float, pd.DataFrame]]
ExperimentSweeps = ExperimentSweepT[list[str], dict[str, dict[float, pd.DataFrame]]]


class TestStandstill(Experiment):

    name = "standstill"

    def test_position_unchanged(self):
        np.testing.assert_array_less(self.results["state.px"].abs(), self.eps, "px should remain ~0.0")
        np.testing.assert_array_less(self.results["state.py"].abs(), self.eps, "py should remain ~0.0")
        np.testing.assert_array_less(self.results["state.theta"].abs(), self.eps, "theta should remain ~0.0")


class TestStraightDriving(ExperimentSweep):

    name = "straight_driving"
    sweep_param = "state_0.px"
    sweep_values: ClassVar[list[float]] = [0.0, 1.0, 2.0]

    def test_monotonic_forward_motion(self):
        for solutions in self.results.values():
            px_vals = solutions["state.px"].to_numpy()
            assert np.all(np.diff(px_vals) >= -self.eps), "px should increase monotonically"

    def test_final_position_matches_velocity(self):
        for px0, solutions in self.results.items():
            expected_px = px0 + solutions["time"].iloc[-1] * solutions["der(state.px)"].iloc[-1]
            np.testing.assert_allclose(solutions["state.px"].iloc[-1], expected_px)

    def test_no_lateral_drift(self):
        for solutions in self.results.values():
            np.testing.assert_array_less(
                solutions["state.py"].abs(), self.eps, "py should remain near 0.0 with zero steering"
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
    sweep_param = "phi"
    sweep_values: ClassVar[list[float]] = [np.deg2rad(0.1), np.deg2rad(0.5), np.deg2rad(1.0)]

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
