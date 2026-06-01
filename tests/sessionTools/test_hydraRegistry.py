import dataclasses
from pathlib import Path
from typing import Sequence

import hydra_zen
import pytest
from hydra import compose, initialize
from hydra.core.global_hydra import GlobalHydra

import mtools.sessionConfig as sessionConfig
from mtools.hydraRegistry import HydraZenRegistry


@dataclasses.dataclass
class State:
    px: float = 0.0
    py: float = 0.0
    theta: float = 0.0


@dataclasses.dataclass
class KinematicVehicle:
    state_0: State
    v_norm: float = 10.0
    phi: float = 0.1
    l: float = 2.0


@dataclasses.dataclass(frozen=True)
class ComposeCase:
    name: str
    overrides: Sequence[str]
    expected_state_px: float


@dataclasses.dataclass(frozen=True)
class RegistryExampleConfig:
    run_default: type


class TestHydraRegistryWithHydraComposition:
    COMPOSE_CASES = (
        ComposeCase(name="default", overrides=(), expected_state_px=0.0),
        ComposeCase(
            name="group_alias_override",
            overrides=("parameters/state_0=front_position",),
            expected_state_px=1.0,
        ),
        ComposeCase(
            name="experiment_override",
            overrides=("experiment=front_position",),
            expected_state_px=1.0,
        ),
    )

    @pytest.fixture(autouse=True)
    def _reset_global_hydra(self):
        GlobalHydra.instance().clear()
        yield
        GlobalHydra.instance().clear()

    @pytest.fixture(scope="class")
    def registry_example(self) -> RegistryExampleConfig:
        registry = HydraZenRegistry(store=hydra_zen.ZenStore())

        # Register a package path with a shorter group alias as used in examples.
        registry.register_group_name("session.parameters.state_0", group_name="parameters/state_0")
        registry.register_group_option(group_id="parameters/state_0", name="zero_state", config=State())
        registry.register_group_option(
            group_id="session.parameters.state_0",
            name="front_position",
            config=State(px=1.0),
        )

        model_name = "KinematicVehicle"
        session_default = hydra_zen.make_config(
            bases=(sessionConfig.Session,),
            parameters=KinematicVehicle(state_0=State()),
            model_configurations={
                model_name: sessionConfig.Model(
                    time_range=sessionConfig.TimeRange(model_name=model_name, start_time=0.0, stop_time=10.0),
                    tolerance=sessionConfig.Tolerance(model_name=model_name, tolerance=1e-9),
                    variable_filter=sessionConfig.VariableFilter(model_name=model_name),
                )
            },
            sim_configurations=sessionConfig.Simulation(solver="rungekutta", output_format="csv"),
            model=Path("tests/sessionTools/models/kinematicVehicle.mo").resolve(),
        )

        run_default = registry.build_run_config(
            base=sessionConfig.SimulationRun,
            model_name=model_name,
            session=session_default,
            selections={"parameters/state_0": "zero_state"},
            include_experiment_group=True,
            name="default",
        )
        registry.register_experiment(
            name="front_position",
            base_run_config=run_default,
            selections={"parameters/state_0": "front_position"},
        )
        registry.add_to_hydra_store()

        return RegistryExampleConfig(run_default=run_default)

    @pytest.mark.parametrize("case", COMPOSE_CASES, ids=lambda case: case.name)
    def test_compose_examples(self, registry_example: RegistryExampleConfig, case: ComposeCase):
        with initialize(version_base=None, config_path=None):
            cfg = compose(config_name="default", overrides=list(case.overrides))

        assert cfg.model_name == "KinematicVehicle"
        assert cfg.session.parameters.state_0.px == case.expected_state_px
        assert cfg.session.model == Path("tests/sessionTools/models/kinematicVehicle.mo").resolve()

    def test_multirun_parameter_sweep(self, registry_example: RegistryExampleConfig, tmp_path):
        job_runs = hydra_zen.launch(
            registry_example.run_default,
            lambda cfg: cfg.session.parameters.v_norm,
            overrides=[
                "session.parameters.v_norm=10,20",
                f"hydra.sweep.dir={tmp_path}",
                "hydra.job.chdir=False",
            ],
            multirun=True,
            version_base=None,
        )

        run_results = [job.return_value for job in job_runs[0]]
        expected_results = [job.cfg["session"]["parameters"]["v_norm"] for job in job_runs[0]]
        assert run_results == expected_results
