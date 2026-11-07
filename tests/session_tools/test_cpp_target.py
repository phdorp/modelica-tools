from __future__ import annotations

import os
import pathlib
import shutil

import numpy as np
import pydelica
import pytest
from models.kinematic_vehicle import vehicle_default

from mtools.internal.pydelica_patch import install_pydelica_patch
from mtools.internal.session_tools import SessionBuilder, SessionDirector
from mtools.session_config import Model, Simulation

MODEL = pathlib.Path(__file__).parent.joinpath("models", "kinematic_vehicle.mo").resolve()
CPP_BUILD_OPTIONS = {"omc_build_flags": {"-q": None, "--simCodeTarget": "Cpp"}}


def _cpp_runtime_available() -> bool:
    omc_binary = shutil.which("omc")
    if omc_binary is None:
        return False
    configured_home = os.environ.get("OPENMODELICAHOME")
    omc_home = (
        pathlib.Path(configured_home)
        if configured_home
        else pathlib.Path(omc_binary).resolve().parent.parent
    )
    return omc_home.joinpath("include", "omc", "cpp", "ModelicaConfig_gcc.inc").is_file()


pytestmark = pytest.mark.skipif(
    not _cpp_runtime_available(),
    reason="OpenModelica Cpp runtime headers are not installed",
)


def _configure(builder: SessionBuilder, emit_protected: bool = False) -> None:
    builder.configure_parameters(
        {"state_0.px": 0.0, "state_0.py": 0.0, "state_0.theta": 0.0, "v_norm": 10.0, "phi": 0.0}
    )
    builder.configure_models(
        {
            "KinematicVehicle": {
                "time_range": {
                    "model_name": "KinematicVehicle",
                    "start_time": 0.0,
                    "stop_time": 1.0,
                },
                "tolerance": {"model_name": "KinematicVehicle", "tolerance": 1e-8},
                "variable_filter": {
                    "model_name": "KinematicVehicle",
                    "filter_str": "*",
                },
            }
        }
    )
    builder.configure_simulation(
        {"solver": "dassl", "output_format": "csv", "emit_protected": emit_protected}
    )


def test_cpp_target_compiles_and_simulates_through_session_director():
    director = SessionDirector(
        model=MODEL,
        parameters=vehicle_default,
        model_configurations={
            "KinematicVehicle": Model.from_parameters(
                "KinematicVehicle", start_time=0.0, stop_time=1.0, tolerance=1e-8
            )
        },
        sim_configurations=Simulation(solver="dassl", output_format="csv"),
        build_options=CPP_BUILD_OPTIONS,
    )
    session = director.make_session()

    session.simulate(model_name="KinematicVehicle")
    solution = session.get_solutions()["KinematicVehicle"]

    assert np.isclose(solution["time"].values[-1], 1.0)
    assert np.isclose(solution["state.px"].values[-1], 10.0, rtol=1e-4)
    assert np.allclose(solution["state.py"], 0.0, atol=1e-6)
    assert np.allclose(solution["state.theta"], 0.0, atol=1e-6)
    for column in ("px_dot", "py_dot", "theta_dot"):
        assert column not in solution.columns


def test_cpp_target_emits_protected_variables_when_enabled():
    builder = SessionBuilder(MODEL, build_options=CPP_BUILD_OPTIONS)
    _configure(builder, emit_protected=True)

    builder.session.simulate(model_name="KinematicVehicle")
    solution = builder.session.get_solutions()["KinematicVehicle"]

    for column in ("px_dot", "py_dot", "theta_dot"):
        assert column in solution.columns


def test_cpp_target_works_with_pydelica_session_directly():
    install_pydelica_patch()
    session = pydelica.Session()
    session.build_model(MODEL, omc_build_flags={"-q": None, "--simCodeTarget": "Cpp"})
    session.set_parameter("v_norm", 10.0)
    session.set_parameter("phi", 0.0)
    session.set_time_range(start_time=0, stop_time=1)
    session.set_solver("dassl")
    session.set_output_format("csv")

    session.simulate(model_name="KinematicVehicle")
    solution = session.get_solutions()["KinematicVehicle"]

    assert np.isclose(solution["time"].values[-1], 1.0)
    assert np.isclose(solution["state.px"].values[-1], 10.0, rtol=1e-4)