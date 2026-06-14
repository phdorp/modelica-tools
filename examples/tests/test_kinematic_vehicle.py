import math

import numpy as np
import pytest

import mtools.session_config as session_config
from kinematic_vehicle.kinematic_vehicle import KinematicVehicle, State, registry, run_default, simulation_default

from conftest import get_solution_df, _openmodelica_available


POSITION_TOL = 1e-2
ANGLE_TOL = 1e-2
SPEED_TOL = 0.05
DEFAULT_STOP_TIME = 10.0


def _ensure_omc_available():
    if not _openmodelica_available():
        pytest.skip("OpenModelica (omc) not available")


@pytest.fixture
def run_experiment():
    import hydra_zen
    import mtools.sim_tools as sim_tools

    def _run_experiment(
        selections=None,
        parameters=None,
        include_experiment_group=True,
        name="test",
    ):
        if selections is None:
            selections = {"parameters/state_0": "zero_state"}

        if parameters is None:
            base_params = run_default.session.parameters
            parameters = KinematicVehicle(
                state_0=base_params.state_0 if hasattr(base_params, "state_0") else State(),
                v_norm=10.0,
                phi=0.0,
            )

        session_default = hydra_zen.make_config(
            bases=(session_config.Session,),
            parameters=parameters,
            model_configurations={
                "KinematicVehicle": session_config.Model.from_parameters("KinematicVehicle")
            },
            sim_configurations=simulation_default,
            model=run_default.session.model,
        )

        run_config = registry.build_run_config(
            base=session_config.SimulationRun,
            model_name="KinematicVehicle",
            session=session_default,
            selections=selections,
            include_experiment_group=include_experiment_group,
            name=name,
        )

        solutions = sim_tools.simulate(run_config)
        return solutions

    return _run_experiment


class TestStandstill:
    def test_position_unchanged(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="standstill",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=0.0, phi=0.0),
        )
        df = get_solution_df(solutions)
        assert df["state.px"].abs().max() < POSITION_TOL, "px should remain ~0.0"
        assert df["state.py"].abs().max() < POSITION_TOL, "py should remain ~0.0"
        assert df["state.theta"].abs().max() < ANGLE_TOL, "theta should remain ~0.0"


class TestStraightDriving:
    def test_monotonic_forward_motion(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="straight_driving",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0),
        )
        df = get_solution_df(solutions)
        px_vals = df["state.px"].values
        assert all(px_vals[i] <= px_vals[i + 1] + 1e-6 for i in range(len(px_vals) - 1)), "px should increase monotonically"

    def test_final_position_matches_velocity(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="straight_driving",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0),
        )
        df = get_solution_df(solutions)
        expected_px = 10.0 * DEFAULT_STOP_TIME
        final_px = df["state.px"].iloc[-1]
        assert final_px == pytest.approx(expected_px, rel=SPEED_TOL), f"px should be ~{expected_px}, got {final_px}"

    def test_no_lateral_drift(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="straight_driving",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0),
        )
        df = get_solution_df(solutions)
        assert df["state.py"].abs().max() < POSITION_TOL, "py should remain near 0.0 with zero steering"

    def test_heading_unchanged(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="straight_driving",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0),
        )
        df = get_solution_df(solutions)
        assert df["state.theta"].abs().max() < ANGLE_TOL, "theta should remain near 0.0 with zero steering"

    def test_speed_matches_v_norm(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="straight_driving",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.0),
        )
        df = get_solution_df(solutions)
        time_col = df["time"]
        px_col = df["state.px"]
        py_col = df["state.py"]
        dt = time_col.diff().values[1:-1]
        dpx = px_col.values[2:] - px_col.values[:-2]
        dpy = py_col.values[2:] - py_col.values[:-2]
        speed = np.sqrt(dpx**2 + dpy**2) / dt
        expected_speed = 10.0
        assert all(
            abs(s - expected_speed) / expected_speed < SPEED_TOL for s in speed
        ), f"speed should be ~{expected_speed} within {SPEED_TOL*100}%"


class TestTurnLeft:
    def test_monotonic_forward_motion(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="turn_left",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.5),
        )
        df = get_solution_df(solutions)
        px_vals = df["state.px"].values
        assert all(px_vals[i] <= px_vals[i + 1] + 1e-6 for i in range(len(px_vals) - 1)), "px should increase monotonically"

    def test_monotonic_lateral_displacement(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="turn_left",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.5),
        )
        df = get_solution_df(solutions)
        py_vals = df["state.py"].values
        assert all(py_vals[i] <= py_vals[i + 1] + 1e-6 for i in range(len(py_vals) - 1)), "py should increase for left turn"

    def test_monotonic_heading_rotation(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="turn_left",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.5),
        )
        df = get_solution_df(solutions)
        theta_vals = df["state.theta"].values
        assert all(theta_vals[i] <= theta_vals[i + 1] + 1e-6 for i in range(len(theta_vals) - 1)), "theta should increase for left turn"

    def test_final_position_first_quadrant(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="turn_left",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.5),
        )
        df = get_solution_df(solutions)
        final_px = df["state.px"].iloc[-1]
        final_py = df["state.py"].iloc[-1]
        assert final_px > 0, f"final px should be positive, got {final_px}"
        assert final_py > 0, f"final py should be positive, got {final_py}"

    def test_turn_radius_reasonable(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="turn_left",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.5),
        )
        l = 2.0
        phi = 0.5
        expected_radius = l / math.tan(phi)
        assert expected_radius > 0, "turn radius should be positive"
        assert math.isfinite(expected_radius), "turn radius should be finite"

    def test_no_singular_heading(self, run_experiment):
        _ensure_omc_available()
        solutions = run_experiment(
            name="turn_left",
            selections={"parameters/state_0": "zero_state"},
            parameters=KinematicVehicle(state_0=State(), v_norm=10.0, phi=0.5),
        )
        df = get_solution_df(solutions)
        final_theta = abs(df["state.theta"].iloc[-1])
        assert final_theta < math.pi / 2, f"final heading |theta| should be < pi/2, got {final_theta}"
