import mtools.sim_tools as sim_tools

import pandas as pd


def test_normalize_solution_match():
    solutions = {"kinematic_vehicle_KinematicVehicle": pd.DataFrame({"time": [0.0, 1.0]})}

    normalized = sim_tools._normalize_solution_keys(solutions, model_name="kinematic_vehicle.KinematicVehicle")

    assert list(normalized.keys()) == ["kinematic_vehicle.KinematicVehicle"]
    assert normalized["kinematic_vehicle.KinematicVehicle"].equals(solutions["kinematic_vehicle_KinematicVehicle"])


def test_normalize_solution_no_match():
    solutions = {"backend_generated_result": pd.DataFrame({"time": [0.0, 1.0]})}

    normalized = sim_tools._normalize_solution_keys(solutions, model_name="some.package.ModelName")

    assert list(normalized.keys()) == ["some.package.ModelName"]
    assert normalized["some.package.ModelName"].equals(solutions["backend_generated_result"])
