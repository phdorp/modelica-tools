"""FMU runs compared through the reference test classes, with the test classes unchanged."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import hydra_zen
import pytest
from hydra_zen import MISSING

from mtools.hydra_registry import HydraZenRegistry, RunConfig
from mtools.session_config import FmuExport, RunSettings
from mtools.testing import ExperimentReference, ExperimentSweepReference
from tests.fmu.fmu_models import MODEL_PATH, DecayParameters

pytestmark = pytest.mark.fmu

MODEL = "FmuTests.Decay"

#: Communication interval of the ME vs CS pair. The Co-Simulation FMU embeds fixed-step Euler, whose error at the
#: model's own 0.01 interval is 2 % (above the pinned rtol 1e-3); 2e-4 brings it under.
CS_INTERVAL = 2e-4


def _decay_registry(
    candidate: Callable[[HydraZenRegistry], RunConfig],
    reference: Callable[[HydraZenRegistry], RunConfig],
    interval: float | None = None,
) -> HydraZenRegistry:
    """A registry with the experiment ``decay`` on the candidate run config and a ``reference`` run config."""
    registry = HydraZenRegistry(store=hydra_zen.ZenStore())
    registry.register_group_options("settings/parameters", {"default": DecayParameters()}, default="default")
    registry.register_group_options(
        "settings", {"default": RunSettings(parameters=MISSING, interval=interval)}, default="default"
    )
    base = candidate(registry)
    reference(registry)
    registry.register_experiment(
        name="decay", base_run_config=base, overrides={"settings/parameters": DecayParameters(k=2.0)}
    )
    return registry


def _exported(registry: HydraZenRegistry, **fmu: Any) -> RunConfig:
    return registry.create_run(
        model_name=MODEL, model_path=MODEL_PATH, fmu=FmuExport(**fmu), include_experiment_group=True, name="default"
    )


def _given(given: Path, name: str, **fields: Any) -> Callable[[HydraZenRegistry], RunConfig]:
    """A run config factory for the given FMU ``given``, registered as ``name``."""
    return lambda registry: registry.create_fmu_run(
        fmu_path=given, include_experiment_group=True, name=name, **fields
    )


class _ReferenceTest:
    """Shared by the classes below: the reference run config is the registry's ``reference`` run config."""

    @pytest.fixture(scope="class")
    def reference_run_config(self, registry: HydraZenRegistry) -> RunConfig:
        return registry.get_run_config("reference")

    def test_matches(self) -> None:
        self.assert_matches_reference()  # type: ignore[attr-defined]


class TestExportedMatchesGiven(_ReferenceTest, ExperimentReference):
    name = "decay"

    @pytest.fixture(scope="class")
    def registry(self, exported_fmu: Callable[..., Path]) -> HydraZenRegistry:
        return _decay_registry(_exported, _given(exported_fmu(MODEL), "reference", model_name=MODEL))


class TestModelExchangeMatchesCoSimulation(_ReferenceTest, ExperimentReference):
    name = "decay"
    interpolate = True
    rtol = 1e-3
    eps = 1e-6

    @pytest.fixture(scope="class")
    def registry(self) -> HydraZenRegistry:
        return _decay_registry(
            _exported,
            lambda r: r.create_run(
                model_name=MODEL,
                model_path=MODEL_PATH,
                fmu=FmuExport(fmu_type="cs"),
                include_experiment_group=True,
                name="reference",
            ),
            interval=CS_INTERVAL,
        )


class TestGivenFmusWithoutModelName(_ReferenceTest, ExperimentReference):
    """Both sides are given FMUs without ``model_name``; results are keyed by the FMU's ``modelName``."""

    name = "decay"

    @pytest.fixture(scope="class")
    def registry(self, exported_fmu: Callable[..., Path]) -> HydraZenRegistry:
        given = exported_fmu(MODEL)
        return _decay_registry(_given(given, "default"), _given(given, "reference"))


class TestGivenFmuSweepWithoutModelName(_ReferenceTest, ExperimentSweepReference):
    """A sweep over given FMUs without ``model_name`` keys each job's table by the FMU's ``modelName``."""

    name = "decay"
    sweep_params = {"k": [1.0, 3.0]}

    @pytest.fixture(scope="class")
    def registry(self, exported_fmu: Callable[..., Path]) -> HydraZenRegistry:
        given = exported_fmu(MODEL)
        return _decay_registry(_given(given, "default"), _given(given, "reference"))
