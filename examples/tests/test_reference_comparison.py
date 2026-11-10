import pytest
from kinematic_vehicle.kinematic_vehicle import registry as model_registry

from mtools.testing import ExperimentReference, ExperimentSweepReference
from tests.reference_models.kinematic_vehicle import run_reference


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
