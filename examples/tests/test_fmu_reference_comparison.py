import pytest

from mtools.testing import ExperimentReference
from tests.fmu_registry import fmu_registry, run_fmu_reference


@pytest.fixture(scope="module")
def registry():
    return fmu_registry


@pytest.fixture(scope="module")
def reference_run_config():
    return run_fmu_reference


class TestTurnLeftFmuReference(ExperimentReference):
    name = "turn_left"
    rtol = 1e-6  # both sides run CVODE on different model structures

    def test_matches_reference(self):
        self.assert_matches_reference()
