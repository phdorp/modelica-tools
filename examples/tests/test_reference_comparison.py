import pytest
from kinematic_vehicle.kinematic_vehicle import MODEL_NAME
from tests.experiments import registry as kinematic_registry

from mtools.testing import ExperimentReference, ExperimentSweepReference
from tests import reference_experiments

REFERENCE_NAME = reference_experiments.MODEL_NAME


@pytest.fixture(scope="module")
def model_name():
    return MODEL_NAME


@pytest.fixture(scope="module")
def reference_name():
    return REFERENCE_NAME


@pytest.fixture(scope="module")
def registry():
    return kinematic_registry


@pytest.fixture(scope="module")
def reference_registry():
    return reference_experiments.registry


class TestStandstillReference(ExperimentReference):
    name = "standstill"

    def test_matches_reference(self):
        self.assert_matches_reference()


class TestTurnLeftReference(ExperimentSweepReference):
    name = "turn_left"
    sweep_params = {"phi": [0.1, 0.5, 1.0]}

    def test_matches_reference(self):
        self.assert_matches_reference()
