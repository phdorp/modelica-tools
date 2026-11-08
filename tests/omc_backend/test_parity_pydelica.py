"""TEMPORARY parity test: the pydelica path against the new OMC backend.

TEMPORARY: delete this file together with pydelica in #66.

It runs the kinematic vehicle example's candidate and reference models through
today's public ``mtools.sim_tools.simulate`` (pydelica) and through the backend
directly (``build()`` and ``Build.simulate()``), on the C and Cpp targets, with the
same parameters, time range, tolerance and solver. The results must agree in column
set and in value.

Tolerance. The pydelica Cpp path reads the runtime's CSV, which carries 6
significant digits, so a value can be off by up to 5e-6 relative. ``RTOL`` = 1e-5
absorbs that and nothing more. ``ATOL`` only covers values that underflow to zero.

Expected differences, all normalised away here and nowhere else:

* dtypes: the backend casts columns by ``_init.xml`` type (Integer -> int64,
  Boolean -> bool); pydelica parses CSV, so an Integer column may arrive as int64 or
  float64. Values are compared as float64.
* defaults: pydelica always applies 0 to 10 s and tolerance 1e-9 from
  ``Model.from_parameters``, the backend otherwise uses the model's experiment
  annotation. Both paths get the same explicit values below. The output interval is
  not configurable on the pydelica path (it uses its own 0.002 s step), so the backend
  gets ``interval=0.002``.
* pydelica's Cpp CSV ends every line with a comma, so pandas yields an extra
  ``Unnamed: N`` column; it is dropped.
* 2-D array parameter names are ``m[1,2]`` on the backend (ledger R4) and
  ``m[1, 2]`` in pydelica; the vehicle models have no array parameters, so this
  does not arise here.
* Row sets: both paths use the same solver (dassl). On Cpp dassl ignores the grid and
  writes every internal step on both paths, so rows still match one to one.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import omegaconf
import pandas as pd
import pytest
from kinematic_vehicle.kinematic_vehicle import \
    registry  # type: ignore[import-untyped]

import mtools.session_config as session_config
import mtools.sim_tools as sim_tools
from mtools.internal.omc.build import build
from mtools.internal.omc.config import BuildConfig, RunSettings, Target

# TEMPORARY: delete with pydelica in #66.

RTOL = 1e-5
ATOL = 1e-12

START_TIME = 0.0
STOP_TIME = 10.0
TOLERANCE = 1e-9
SOLVER = "dassl"
INTERVAL = 0.002

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
CANDIDATE_PACKAGE = EXAMPLES / "src" / "kinematic_vehicle" / "package.mo"
REFERENCE_PACKAGE = EXAMPLES / "tests" / "package.mo"
CANDIDATE = "kinematic_vehicle.WrapperKinematicVehicle"
REFERENCE = "tests.reference_models.WrapperKinematicVehicle"

#: (experiment, hydra overrides). The overrides change a parameter away from the
#: experiment's value so a parameter that is ignored on either path shows up.
SCENARIOS = {
    "standstill": ("standstill", []),
    "straight_driving": ("straight_driving", []),
    "turn_left": ("turn_left", []),
    "turn_left_long_wheelbase": ("turn_left", ["session.parameters.wheelbase=4.0"]),
    "protected_output": ("protected_output", []),
}


def pydelica_config(scenario: str, model: str, target: Target) -> Any:
    """Compose the example's run config for ``model`` on ``target`` with explicit settings."""
    experiment, overrides = SCENARIOS[scenario]
    cfg = registry.compose_experiment(experiment, overrides=overrides)
    omegaconf.OmegaConf.set_struct(cfg, False)
    omc_build_flags: dict[str, str | None] = {"-q": None}
    if target == "Cpp":
        omc_build_flags["--simCodeTarget"] = "Cpp"
    build_options: dict[str, Any] = {"model_addr": model, "omc_build_flags": omc_build_flags}
    if model == REFERENCE:
        # The reference extends the candidate interface, so it loads the candidate too.
        build_options["extra_models"] = [str(CANDIDATE_PACKAGE)]
    model_path = REFERENCE_PACKAGE if model == REFERENCE else CANDIDATE_PACKAGE
    cfg.model_name = model
    cfg.session.model = str(model_path)
    cfg.session.build_options = build_options
    cfg.session.model_configurations = {
        model: omegaconf.OmegaConf.structured(
            session_config.Model.from_parameters(model, START_TIME, STOP_TIME, TOLERANCE)
        )
    }
    cfg.session.sim_configurations.solver = SOLVER
    return cfg


def run_pydelica(scenario: str, model: str, target: Target) -> pd.DataFrame:
    solutions = sim_tools.simulate(pydelica_config(scenario, model, target))
    frame = solutions[model]
    return frame.loc[:, ~frame.columns.str.startswith("Unnamed")]


def run_backend(scenario: str, model: str, target: Target) -> pd.DataFrame:
    # Same parameters as the pydelica run, read from the composed config.
    cfg = pydelica_config(scenario, model, target)
    parameters = omegaconf.OmegaConf.to_container(cfg.session.parameters, resolve=True)
    assert isinstance(parameters, dict)
    parameters.pop("_target_", None)
    emit_protected = bool(cfg.session.sim_configurations.emit_protected)
    if model == REFERENCE:
        config = BuildConfig(REFERENCE_PACKAGE, model, target, extra_sources=[CANDIDATE_PACKAGE])
    else:
        config = BuildConfig(CANDIDATE_PACKAGE, model, target)
    settings = RunSettings(
        parameters=parameters,
        start_time=START_TIME,
        stop_time=STOP_TIME,
        interval=INTERVAL,
        tolerance=TOLERANCE,
        solver=SOLVER,
        emit_protected=emit_protected,
    )
    with build(config) as built:
        return built.simulate(settings)


@pytest.fixture(params=["C", "Cpp"])
def target_(request: pytest.FixtureRequest) -> Iterator[Target]:
    yield request.param


@pytest.mark.parametrize("model", [CANDIDATE, REFERENCE], ids=["candidate", "reference"])
@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_backend_matches_pydelica(scenario: str, model: str, target_: Target) -> None:
    expected = run_pydelica(scenario, model, target_)
    actual = run_backend(scenario, model, target_)

    extra = set(actual.columns) - set(expected.columns)
    missing = set(expected.columns) - set(actual.columns)
    assert not extra and not missing, f"backend extra: {sorted(extra)}, backend missing: {sorted(missing)}"
    assert len(actual) == len(expected)
    for column in expected.columns:
        np.testing.assert_allclose(
            actual[column].to_numpy(dtype=float),
            expected[column].to_numpy(dtype=float),
            rtol=RTOL,
            atol=ATOL,
            err_msg=f"column {column}",
        )
