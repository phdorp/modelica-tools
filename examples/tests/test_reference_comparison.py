import pytest
from kinematic_vehicle.kinematic_vehicle import MODEL_NAME
from tests.experiments import reference_registry as _reference_registry
from tests.experiments import registry as kinematic_registry
from tests.reference_models.kinematic_vehicle import \
    MODEL_NAME as REFERENCE_NAME

from mtools.testing import ExperimentReference, ExperimentSweepReference


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
