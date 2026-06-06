import importlib
import subprocess

import pytest


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


def _get_simulation_duration(solutions: dict) -> float:
    for df in solutions.values():
        if "time" in df.columns:
            return float(df["time"].iloc[-1])
    return 10.0


@pytest.fixture(scope="module")
def kinematic_registry():
    mod = importlib.import_module("kinematic_vehicle.kinematic_vehicle")
    return mod.registry


@pytest.fixture(scope="module")
def simulate():
    import mtools.sim_tools as sim_tools
    return sim_tools.simulate


@pytest.fixture(params=["standstill", "straight_driving", "turn_left"])
def run_experiment(kinematic_registry, simulate, request):
    def _run_experiment(
        experiment_name: str | None = None,
        selections: dict | None = None,
        parameters: dict | None = None,
        include_experiment_group: bool = True,
        **extra_selections,
    ):
        import hydra_zen
        import mtools.session_config as session_config
        from kinematic_vehicle.kinematic_vehicle import (
            KinematicVehicle,
            State,
            registry,
            run_default,
            simulation_default,
            vehicle_default,
        )

        name = experiment_name or request.param

        if selections is None:
            selections = {"parameters/state_0": "zero_state"}
        selections = dict(selections, **extra_selections)

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

        solutions = simulate(run_config)
        return solutions

    return _run_experiment


@pytest.fixture(
    params=["standstill", "straight_driving", "turn_left"],
    scope="function",
)
def run_experiment_no_omc(kinematic_registry, simulate, request):
    if not _openmodelica_available():
        pytest.skip("OpenModelica (omc) not available")

    def _run_experiment(experiment_name=None, selections=None, parameters=None, **extra_selections):
        return run_experiment(
            experiment_name=experiment_name,
            selections=selections,
            parameters=parameters,
            include_experiment_group=True,
            **extra_selections,
        )

    return _run_experiment


@pytest.fixture
def skip_if_no_omc():
    if not _openmodelica_available():
        pytest.skip("OpenModelica (omc) not available")


def get_solution_df(solutions, name="KinematicVehicle"):
    if name in solutions:
        return solutions[name]
    for key in solutions:
        if "state" in key.lower() or "Kinematic" in key:
            return solutions[key]
    raise ValueError(f"Could not find solution dataframe in {list(solutions.keys())}")
