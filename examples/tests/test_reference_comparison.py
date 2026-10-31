import pytest
from kinematic_vehicle.experiments import EXPERIMENTS
from kinematic_vehicle.kinematic_vehicle import MODEL_NAME
from kinematic_vehicle.kinematic_vehicle import registry as model_registry
from tests.reference_models.kinematic_vehicle import MODEL_NAME as REFERENCE_NAME
from tests.reference_models.kinematic_vehicle import registry as _reference_registry

from mtools.testing import ExperimentReference, ExperimentSweepReference


def test_registries_share_experiment_definitions():
    """Both registries expose the shared experiments with identical session inputs."""
    for experiment in EXPERIMENTS:
        candidate = model_registry.compose_experiment(experiment.name)
        reference = _reference_registry.compose_experiment(experiment.name)

        assert candidate.model_name != reference.model_name
        assert candidate.session.parameters == reference.session.parameters
        assert candidate.session.sim_configurations == reference.session.sim_configurations


@pytest.fixture(scope="module")
def model_name():
    return MODEL_NAME


@pytest.fixture(scope="module")
def reference_name():
    return REFERENCE_NAME


@pytest.fixture(scope="module")
def registry():
    return model_registry


@pytest.fixture(scope="module")
def reference_registry():
    return _reference_registry


class TestStandstillReference(ExperimentReference):
    name = "standstill"

    def test_matches_reference(self):
        self.assert_matches_reference()


class TestTurnLeftReference(ExperimentSweepReference):
    name = "turn_left"
    sweep_params = {"phi": [0.1, 0.5, 1.0]}

    def test_matches_reference(self):
        self.assert_matches_reference()
