import pytest
from kinematic_vehicle.experiments import EXPERIMENTS
from kinematic_vehicle.kinematic_vehicle import registry as model_registry
from tests.reference_models.kinematic_vehicle import run_reference

from mtools.testing import ExperimentReference, ExperimentSweepReference


def test_registry_shares_one_experiment_set():
    """One registry composes the shared experiments for both run configs."""
    for experiment in EXPERIMENTS:
        candidate = model_registry.compose_experiment(experiment.name)
        reference = model_registry.compose_experiment(experiment.name, run_config=run_reference)

        assert candidate.model_name != reference.model_name
        assert candidate.session.parameters == reference.session.parameters
        assert candidate.session.sim_configurations == reference.session.sim_configurations


@pytest.fixture(scope="module")
def registry():
    return model_registry


@pytest.fixture(scope="module")
def reference_run_config():
    return run_reference


class TestStandstillReference(ExperimentReference):
    name = "standstill"

    def test_matches_reference(self):
        self.assert_matches_reference()


class TestTurnLeftReference(ExperimentSweepReference):
    name = "turn_left"
    sweep_params = {"phi": [0.1, 0.5, 1.0]}

    def test_matches_reference(self):
        self.assert_matches_reference()
