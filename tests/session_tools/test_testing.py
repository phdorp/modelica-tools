import contextlib

"""Tests for ``mtools.testing`` experiment base classes.

``mtools.sim_tools.simulate`` is faked, so no OpenModelica installation is
needed. Covered behavior:

- single experiment (``Experiment``): composes the experiment by name via
  the registry, runs a single simulation, and stores the solution table keyed
  by the composed config's ``build.model_name`` in ``results``.
- multiple experiments (``Experiments``): same, but ``name`` is a list and
  ``results`` maps each name to its solution table.
- parameter sweep (``ExperimentSweep``): resolves the experiment's base
  config from the registry, fans out via multirun simulate with one
  comma-separated ``<prefix>.<param>`` override per entry in
  ``sweep_params``, and maps each cartesian-product tuple to its solution
  table.
- reference comparison (``ExperimentReference`` / ``ExperimentSweepReference``):
  composes the candidate from the registry's default run config and the
  reference with ``run_config=reference_run_config``, reads each side's model
  name from its composed config, then compares the two result structures.
"""

import dataclasses
import typing
from itertools import product as _product

import numpy as np
import pandas as pd
import pytest
from omegaconf import OmegaConf

import mtools.internal.testing as internal_testing
import mtools.sim_tools as sim_tools
import mtools.testing as testing


def _frame(tag: str) -> pd.DataFrame:
    """Build a minimal solution table tagged for later identification."""
    return pd.DataFrame({"time": [0.0, 1.0], "tag": [tag, tag]})



def _run_config(model_name: str) -> type:
    """Build a minimal run config type carrying ``model_name``.

    Real run configs are Hydra config types created by ``registry.create_run``;
    the test doubles only need the ``model_name`` the composed config carries.
    """
    return type("RunConfig", (), {"model_name": model_name})


def _signal_frame(values, signal="signal"):
    return pd.DataFrame({"time": [float(i) for i in range(len(values))], signal: values})


def test_reference_experiment_uses_reference_run_config(monkeypatch):
    def fake_simulate(config, **kwargs):
        model_name = config["build"]["model_name"]
        return {model_name: _frame(model_name)}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    registry = FakeRegistry(model_name="my.Model")
    reference_run_config = _run_config("ref.Model")

    class T(testing.ExperimentReference):
        name = "standstill"

    T.fetch_reference_experiment(registry, reference_run_config)

    assert registry.calls == [
        {"compose_experiment": "standstill", "overrides": None, "run_config": None},
        {"compose_experiment": "standstill", "overrides": None, "run_config": reference_run_config},
    ]
    assert T.results["tag"].iloc[0] == "my.Model"
    assert T.reference_results["tag"].iloc[0] == "ref.Model"


def test_reference_experiment_multi_name_returns_mappings(monkeypatch):
    def fake_simulate(config, **kwargs):
        model_name = config["build"]["model_name"]
        tag = f"{model_name}:{config['composed_experiment']}"
        return {model_name: _frame(tag)}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)

    class T(testing.ExperimentsReference):
        name = ["a", "b"]

    registry = FakeRegistry(model_name="my.Model")
    reference_run_config = _run_config("ref.Model")

    T.fetch_reference_experiment(registry, reference_run_config)

    assert T.results["a"]["tag"].iloc[0] == "my.Model:a"
    assert T.reference_results["b"]["tag"].iloc[0] == "ref.Model:b"


def test_reference_experiment_propagates_missing_reference_solution(monkeypatch):
    def fake_simulate(config, **kwargs):
        if config["build"]["model_name"] == "ref.Model":
            raise ValueError("No solution matches the requested model 'ref.Model'.")
        return {"my.Model": _frame("candidate")}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)

    class T(testing.ExperimentReference):
        name = "standstill"

    registry = FakeRegistry(model_name="my.Model")
    reference_run_config = _run_config("ref.Model")

    with pytest.raises(ValueError, match="No solution matches"):
        T.fetch_reference_experiment(registry, reference_run_config)


def test_reference_comparison_passes_for_matching_tables():
    class T(testing.ExperimentReference):
        name = "standstill"
        results = _signal_frame([1.0, 2.0])
        reference_results = _signal_frame([1.0, 2.0])

    T().assert_matches_reference()


def test_reference_comparison_rejects_value_mismatch():
    class T(testing.ExperimentReference):
        name = "standstill"
        results = _signal_frame([1.0, 2.0])
        reference_results = _signal_frame([1.0, 2.5])

    with pytest.raises(AssertionError, match="signal"):
        T().assert_matches_reference()


def test_reference_comparison_rejects_signal_set_mismatch():
    class T(testing.ExperimentReference):
        name = "standstill"
        results = pd.DataFrame({"time": [0.0, 1.0], "px": [1.0, 2.0]})
        reference_results = pd.DataFrame({"time": [0.0, 1.0], "py": [1.0, 2.0]})

    with pytest.raises(AssertionError, match="output signals differ"):
        T().assert_matches_reference()


def test_reference_comparison_rejects_length_mismatch():
    class T(testing.ExperimentReference):
        name = "standstill"
        results = _signal_frame([1.0, 2.0])
        reference_results = _signal_frame([1.0, 2.0, 3.0])

    with pytest.raises(AssertionError, match="length differs"):
        T().assert_matches_reference()


def test_reference_comparison_rejects_nan_against_finite():
    class T(testing.ExperimentReference):
        name = "standstill"
        results = _signal_frame([np.nan])
        reference_results = _signal_frame([1.0])

    with pytest.raises(AssertionError, match="signal"):
        T().assert_matches_reference()


def test_reference_comparison_eps_is_overridable():
    class T(testing.ExperimentReference):
        name = "standstill"
        eps = 0.5
        results = _signal_frame([1.0])
        reference_results = _signal_frame([1.2])

    T().assert_matches_reference()


def test_reference_comparison_rejects_time_grid_mismatch():
    """Matching signals on a different time grid fail: the setups differ."""

    class T(testing.ExperimentReference):
        name = "standstill"
        results = pd.DataFrame({"time": [0.0, 0.5], "signal": [1.0, 2.0]})
        reference_results = pd.DataFrame({"time": [0.0, 1.0], "signal": [1.0, 2.0]})

    with pytest.raises(AssertionError, match="time"):
        T().assert_matches_reference()


def test_reference_comparison_rejects_extra_column():
    """An extra output signal is still reported, alongside the compared ``time`` column."""

    class T(testing.ExperimentReference):
        name = "standstill"
        results = pd.DataFrame({"time": [0.0, 1.0], "signal": [1.0, 2.0], "extra": [1.0, 2.0]})
        reference_results = pd.DataFrame({"time": [0.0, 1.0], "signal": [1.0, 2.0]})

    with pytest.raises(AssertionError, match="unexpected"):
        T().assert_matches_reference()


def test_reference_comparison_failure_names_model_pair(monkeypatch):
    """Value-mismatch failures name both the candidate and reference models."""

    def fake_simulate(config, **kwargs):
        signal = [1.0, 2.0] if config["build"]["model_name"] == "my.Model" else [1.0, 2.5]
        return {config["build"]["model_name"]: _signal_frame(signal)}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    registry = FakeRegistry(model_name="my.Model")
    reference_run_config = _run_config("ref.Model")

    class T(testing.ExperimentReference):
        name = "standstill"

    T.fetch_reference_experiment(registry, reference_run_config)

    with pytest.raises(AssertionError) as excinfo:
        T().assert_matches_reference()

    message = str(excinfo.value)
    assert "my.Model" in message
    assert "ref.Model" in message


class FakeRegistry:
    """Test double for ``HydraZenRegistry`` recording experiment calls."""

    def __init__(self, runs=None, model_name="my.Model"):
        self.calls: list = []
        self._runs = runs or {}
        self.model_name = model_name

    def activated(self):
        """Activate nothing: sweeps under test never reach Hydra."""
        return contextlib.nullcontext()

    def compose_experiment(self, name, run_config=None, overrides=None):
        """Record the call and return a composed config for the selected run config."""
        self.calls.append({"compose_experiment": name, "overrides": overrides, "run_config": run_config})
        model_name = getattr(run_config, "model_name", self.model_name)
        return OmegaConf.create({"composed_experiment": name, "build": {"model_name": model_name}})

    def get_experiment_run_config(self, name, run_config=None):
        """Return the base run config for experiment ``name``."""
        if run_config is not None:
            return run_config
        return self._runs[name]


def test_single_experiment_uses_registry_default_run_config(monkeypatch):
    """Single experiment composes the experiment by name and stores its run config's solution table."""
    captured = {}

    def fake_simulate(config, **kwargs):
        captured["config"] = config
        assert kwargs == {}
        return {"my.Model": _frame("single")}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = FakeRegistry()

    class T(testing.Experiment):
        name = "standstill"

    T.fetch_experiment(fake_registry)

    assert fake_registry.calls == [
        {"compose_experiment": "standstill", "overrides": None, "run_config": None}
    ]
    assert captured["config"] == {"composed_experiment": "standstill", "build": {"model_name": "my.Model"}}
    assert T.results["tag"].iloc[0] == "single"


def test_multi_experiment_returns_mapping(monkeypatch):
    """Multiple experiments map each name in ``name`` to its own solution table."""
    def fake_simulate(config, **kwargs):
        name = config["composed_experiment"]
        return {"my.Model": _frame(name)}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = FakeRegistry()

    class T(testing.Experiments):
        name = ["a", "b"]

    T.fetch_experiment(fake_registry)

    assert set(T.results.keys()) == {"a", "b"}
    assert T.results["a"]["tag"].iloc[0] == "a"
    assert T.results["b"]["tag"].iloc[0] == "b"


def test_sweep_resolves_base_run_from_registry(monkeypatch, tmp_path_factory):
    """Sweep resolves the multirun base config from the registry and keys results by value tuple."""
    captured = {}

    class FakeJob:
        """Test double for ``SweepResult`` exposing per-job ``config`` and ``solutions``."""

        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        captured["config"] = config
        captured["overrides"] = overrides
        captured["multirun"] = multirun
        captured["sweep_dir"] = sweep_dir
        captured["registry"] = registry
        assert multirun is True
        return [
            FakeJob(
                {"build": {"model_name": "my.Model"}, "settings": {"parameters": {"phi": phi}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, phi in enumerate((0.1, 0.2))
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = _run_config("my.Model")
    fake_registry = FakeRegistry(runs={"turn_left": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {"phi": [0.1, 0.2]}
        name = "turn_left"

    T.fetch_sweep(fake_registry, tmp_path_factory)

    assert captured["config"] is sentinel_run
    assert captured["registry"] is fake_registry
    assert captured["overrides"] == ["experiment=turn_left", "settings.parameters.phi=0.1,0.2"]
    assert set(T.results.keys()) == {(0.1,), (0.2,)}


def test_sweep_results_keyed_by_job_config_not_launch_order(monkeypatch, tmp_path_factory):
    """Jobs returned out of Cartesian order still attribute each table to its own sweep value."""

    class FakeJob:
        """Test double for ``SweepResult`` exposing per-job ``config`` and ``solutions``."""

        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        assert multirun is True
        jobs = [
            FakeJob(
                {"build": {"model_name": "my.Model"}, "settings": {"parameters": {"phi": phi}}},
                {"my.Model": _frame(f"phi={phi}")},
            )
            for phi in (0.1, 0.2)
        ]
        return jobs[::-1]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = FakeRegistry(runs={"turn_left": _run_config("my.Model")})

    class T(testing.ExperimentSweep):
        sweep_params = {"phi": [0.1, 0.2]}
        name = "turn_left"

    T.fetch_sweep(fake_registry, tmp_path_factory)

    assert T.results[(0.1,)]["tag"].iloc[0] == "phi=0.1"
    assert T.results[(0.2,)]["tag"].iloc[0] == "phi=0.2"


def test_sweep_serializes_hydra_native_types(monkeypatch, tmp_path_factory):
    """Tuple (list target), int, and bool sweep values serialize to Hydra-native override syntax."""

    class FakeJob:
        """Test double for ``SweepResult`` exposing per-job ``config`` and ``solutions``."""

        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    captured = {}

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        captured["overrides"] = overrides
        assert multirun is True
        combos = list(_product([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [5, 10], [True, False]))
        return [
            FakeJob(
                {
                    "build": {"model_name": "my.Model"},
                    "settings": {"parameters": {"state_0": list(state), "v_norm": v, "flag": flag}},
                },
                {"my.Model": _frame(f"s{i}")},
            )
            for i, (state, v, flag) in enumerate(combos)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = _run_config("my.Model")
    fake_registry = FakeRegistry(runs={"straight_driving": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {
            "state_0": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
            "v_norm": [5, 10],
            "flag": [True, False],
        }
        name = "straight_driving"

    T.fetch_sweep(fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "settings.parameters.state_0=[0.0,0.0,0.0],[1.0,0.0,0.0]",
        "settings.parameters.v_norm=5,10",
        "settings.parameters.flag=true,false",
    ]
    assert set(T.results.keys()) == {
        ((0.0, 0.0, 0.0), 5, True),
        ((0.0, 0.0, 0.0), 5, False),
        ((0.0, 0.0, 0.0), 10, True),
        ((0.0, 0.0, 0.0), 10, False),
        ((1.0, 0.0, 0.0), 5, True),
        ((1.0, 0.0, 0.0), 5, False),
        ((1.0, 0.0, 0.0), 10, True),
        ((1.0, 0.0, 0.0), 10, False),
    }


def test_sweep_serializes_dict_values_and_freezes_keys(monkeypatch, tmp_path_factory):
    """Dict sweep values serialize to Hydra dict syntax with hashable frozen keys."""

    class FakeJob:
        """Test double for ``SweepResult`` exposing per-job ``config`` and ``solutions``."""

        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    captured = {}

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        captured["overrides"] = overrides
        assert multirun is True
        states = [
            {"px": 0.0, "py": 0.0, "theta": 0.0},
            {"px": 1.0, "py": 0.0, "theta": 0.0},
        ]
        return [
            FakeJob(
                {"build": {"model_name": "my.Model"}, "settings": {"parameters": {"state_0": dict(state)}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, state in enumerate(states)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = _run_config("my.Model")
    fake_registry = FakeRegistry(runs={"straight_driving": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {
            "state_0": [{"px": 0.0, "py": 0.0, "theta": 0.0}, {"px": 1.0, "py": 0.0, "theta": 0.0}],
        }
        name = "straight_driving"

    T.fetch_sweep(fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "settings.parameters.state_0={px:0.0,py:0.0,theta:0.0},{px:1.0,py:0.0,theta:0.0}",
    ]
    assert set(T.results.keys()) == {
        ((("px", 0.0), ("py", 0.0), ("theta", 0.0)),),
        ((("px", 1.0), ("py", 0.0), ("theta", 0.0)),),
    }


def test_sweep_maps_tuples_onto_structured_fields(monkeypatch, tmp_path_factory):
    """Tuple sweep values over a mapping target serialize as Hydra dicts with raw tuple keys."""

    class FakeJob:
        """Test double for ``SweepResult`` exposing per-job ``config`` and ``solutions``."""

        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    class StructuredRegistry(FakeRegistry):
        """Fake registry composing a structured config exposing ``state_0`` fields."""

        def compose_experiment(self, name, run_config=None, overrides=None):
            self.calls.append({"compose_experiment": name, "overrides": overrides, "run_config": run_config})
            return OmegaConf.create(
                {"settings": {"parameters": {"state_0": {"px": 0.0, "py": 0.0, "theta": 0.0}}}}
            )

    captured = {}

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        captured["overrides"] = overrides
        assert multirun is True
        states = [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0)]
        fields = ("px", "py", "theta")
        return [
            FakeJob(
                {"build": {"model_name": "my.Model"}, "settings": {"parameters": {"state_0": dict(zip(fields, state))}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, state in enumerate(states)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = _run_config("my.Model")
    fake_registry = StructuredRegistry(runs={"straight_driving": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {"state_0": [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0)]}
        name = "straight_driving"

    T.fetch_sweep(fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "settings.parameters.state_0={px:0.0,py:0.0,theta:0.0},{px:1.0,py:2.0,theta:3.0}",
    ]
    assert set(T.results.keys()) == {((0.0, 0.0, 0.0),), ((1.0, 2.0, 3.0),)}


def test_sweep_tuple_arity_mismatch_raises(monkeypatch, tmp_path_factory):
    """A tuple whose arity differs from the structured target's field count raises ValueError."""

    class StructuredRegistry(FakeRegistry):
        """Fake registry composing a structured config exposing ``state_0`` fields."""

        def compose_experiment(self, name, run_config=None, overrides=None):
            return OmegaConf.create(
                {"settings": {"parameters": {"state_0": {"px": 0.0, "py": 0.0, "theta": 0.0}}}}
            )

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        raise AssertionError("simulate must not run when tuple arity mismatches")

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = StructuredRegistry(runs={"straight_driving": _run_config("my.Model")})

    class T(testing.ExperimentSweep):
        sweep_params = {"state_0": [(0.0, 0.0)]}
        name = "straight_driving"

    try:
        T.fetch_sweep(fake_registry, tmp_path_factory)
    except ValueError as exc:
        assert "state_0" in str(exc)
    else:
        raise AssertionError("expected ValueError for tuple arity mismatch")


def test_sweep_over_multiple_parameters_uses_cartesian_product(monkeypatch, tmp_path_factory):
    """Multi-parameter sweep emits one override per param and keys results by product tuples."""

    class FakeJob:
        """Test double for ``SweepResult`` exposing per-job ``config`` and ``solutions``."""

        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    captured = {}

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        captured["overrides"] = overrides
        assert multirun is True
        combos = list(_product((0.0, 1.0), (0.0, 1.0)))
        jobs = [
            FakeJob(
                {"build": {"model_name": "my.Model"}, "settings": {"parameters": {"state_0": {"px": px, "py": py}}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, (px, py) in enumerate(combos)
        ]
        return [jobs[i] for i in (2, 0, 3, 1)]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = _run_config("my.Model")
    fake_registry = FakeRegistry(runs={"straight_driving": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {"state_0.px": [0.0, 1.0], "state_0.py": [0.0, 1.0]}
        name = "straight_driving"

    T.fetch_sweep(fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "settings.parameters.state_0.px=0.0,1.0",
        "settings.parameters.state_0.py=0.0,1.0",
    ]
    assert set(T.results.keys()) == {(0.0, 0.0), (0.0, 1.0), (1.0, 0.0), (1.0, 1.0)}
    assert T.results[(1.0, 0.0)]["tag"].iloc[0] == "s2"


@dataclasses.dataclass
class _State:
    px: float = 0.0
    py: float = 0.0
    theta: float = 0.0


def test_sweep_serializes_dataclass_values_like_dicts(monkeypatch, tmp_path_factory):
    """Dataclass sweep values serialize and freeze identically to their dict form."""

    class FakeJob:
        """Test double for ``SweepResult`` exposing per-job ``config`` and ``solutions``."""

        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    captured = {}

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        captured["overrides"] = overrides
        assert multirun is True
        states = [
            {"px": 0.0, "py": 0.0, "theta": 0.0},
            {"px": 1.0, "py": 0.0, "theta": 0.0},
        ]
        return [
            FakeJob(
                {"build": {"model_name": "my.Model"}, "settings": {"parameters": {"state_0": dict(state)}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, state in enumerate(states)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = _run_config("my.Model")
    fake_registry = FakeRegistry(runs={"straight_driving": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {
            "state_0": [_State(px=0.0), _State(px=1.0)],
        }
        name = "straight_driving"

    T.fetch_sweep(fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "settings.parameters.state_0={px:0.0,py:0.0,theta:0.0},{px:1.0,py:0.0,theta:0.0}",
    ]
    assert set(T.results.keys()) == {
        ((("px", 0.0), ("py", 0.0), ("theta", 0.0)),),
        ((("px", 1.0), ("py", 0.0), ("theta", 0.0)),),
    }


def test_sweep_duplicate_frozen_keys_raise(monkeypatch, tmp_path_factory):
    """Sweep values collapsing to the same frozen key (True vs 1) fail fast."""

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        raise AssertionError("simulate must not run when frozen keys collide")

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = FakeRegistry(runs={"exp": _run_config("exp.Model")})

    class T(testing.ExperimentSweep):
        sweep_params = {"flag": [True, 1]}
        name = "exp"

    try:
        T.fetch_sweep(fake_registry, tmp_path_factory)
    except ValueError as exc:
        assert "duplicate result keys" in str(exc)
    else:
        raise AssertionError("expected ValueError for colliding frozen keys")


def test_sweep_empty_value_list_raises(monkeypatch, tmp_path_factory):
    """A param with no sweep values fails fast instead of emitting an invalid override."""

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        raise AssertionError("simulate must not run with empty value lists")

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = FakeRegistry(runs={"exp": _run_config("exp.Model")})

    class T(testing.ExperimentSweep):
        sweep_params = {"phi": []}
        name = "exp"

    try:
        T.fetch_sweep(fake_registry, tmp_path_factory)
    except ValueError as exc:
        assert "'phi'" in str(exc)
    else:
        raise AssertionError("expected ValueError for empty sweep value list")


def test_to_hydra_value_rejects_non_identifier_dict_keys():
    """Dict keys with Hydra syntax characters fail fast instead of emitting invalid overrides."""
    for bad in ["a b", "a,b", "a:b", "a{b", 'a"b', "a'b", "a.b", "a-b"]:
        try:
            internal_testing._to_hydra_value({bad: 1.0})
        except ValueError as exc:
            assert "not expressible in Hydra overrides" in str(exc)
        else:
            raise AssertionError(f"expected ValueError for dict key {bad!r}")
    assert internal_testing._to_hydra_value({"px": 1.0}) == "{px:1.0}"


def test_sweep_dataclass_over_structured_target_needs_no_arity_mapping(monkeypatch, tmp_path_factory):
    """Whole-object dataclass values over a mapping target sweep without positional conversion."""

    class FakeJob:
        """Test double for ``SweepResult`` exposing per-job ``config`` and ``solutions``."""

        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    class StructuredRegistry(FakeRegistry):
        """Fake registry composing a structured config exposing ``state_0`` fields."""

        def compose_experiment(self, name, run_config=None, overrides=None):
            self.calls.append({"compose_experiment": name, "overrides": overrides, "run_config": run_config})
            return OmegaConf.create(
                {"settings": {"parameters": {"state_0": {"px": 0.0, "py": 0.0, "theta": 0.0}}}}
            )

    captured = {}

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        captured["overrides"] = overrides
        assert multirun is True
        states = [
            {"px": 0.0, "py": 0.0, "theta": 0.0},
            {"px": 1.0, "py": 2.0, "theta": 3.0},
        ]
        return [
            FakeJob(
                {"build": {"model_name": "my.Model"}, "settings": {"parameters": {"state_0": dict(state)}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, state in enumerate(states)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = StructuredRegistry(runs={"straight_driving": _run_config("my.Model")})

    class T(testing.ExperimentSweep):
        sweep_params = {"state_0": [_State(), _State(px=1.0, py=2.0, theta=3.0)]}
        name = "straight_driving"

    T.fetch_sweep(fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "settings.parameters.state_0={px:0.0,py:0.0,theta:0.0},{px:1.0,py:2.0,theta:3.0}",
    ]
    assert set(T.results.keys()) == {
        ((("px", 0.0), ("py", 0.0), ("theta", 0.0)),),
        ((("px", 1.0), ("py", 2.0), ("theta", 3.0)),),
    }


def test_sweep_value_alias_covers_dataclass_instances():
    """The public SweepValue alias admits dataclass instances such as State."""
    assert testing.DataclassInstance in typing.get_args(testing.SweepValue)
    assert isinstance(_State(), testing.DataclassInstance)
    assert not isinstance(5, testing.DataclassInstance)


def test_dataclass_helpers_recurse_into_nested_and_tuple_fields():
    """Nested dataclasses and tuple fields serialize and freeze recursively."""

    @dataclasses.dataclass
    class Inner:
        x: float = 0.0

    @dataclasses.dataclass
    class Outer:
        inner: Inner = dataclasses.field(default_factory=Inner)
        tags: tuple = (1.0, 2.0)

    assert internal_testing._to_hydra_value(Outer(inner=Inner(x=1.0))) == "{inner:{x:1.0},tags:[1.0,2.0]}"
    assert internal_testing._to_hashable(Outer(inner=Inner(x=1.0))) == (
        ("inner", (("x", 1.0),)),
        ("tags", (1.0, 2.0)),
    )


def test_reference_sweep_uses_reference_run_config_and_matches_combinations(monkeypatch, tmp_path_factory):
    calls = []

    class FakeJob:
        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        calls.append({"overrides": list(overrides), "sweep_dir": sweep_dir})
        assert multirun is True
        model_name = config.model_name
        return [
            FakeJob(
                {"build": {"model_name": model_name}, "settings": {"parameters": {"phi": phi}}},
                {model_name: pd.DataFrame({"time": [0.0, 1.0], "signal": [phi, phi]})},
            )
            for phi in (0.1, 0.2)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    registry = FakeRegistry(
        runs={"turn_left": _run_config("my.Model")}, model_name="my.Model"
    )
    reference_run_config = _run_config("ref.Model")

    class T(testing.ExperimentSweepReference):
        name = "turn_left"
        sweep_params = {"phi": [0.1, 0.2]}

    T.fetch_reference_sweep(registry, reference_run_config, tmp_path_factory)

    assert calls[0]["overrides"] == ["experiment=turn_left", "settings.parameters.phi=0.1,0.2"]
    assert calls[1]["overrides"] == ["experiment=turn_left", "settings.parameters.phi=0.1,0.2"]
    assert calls[0]["sweep_dir"] != calls[1]["sweep_dir"]
    assert set(T.results) == set(T.reference_results) == {(0.1,), (0.2,)}
    assert T.reference_results[(0.2,)]["signal"].iloc[0] == 0.2
    T().assert_matches_reference()


def test_multi_experiment_reference_sweep_maps_each_name_to_both_sides(monkeypatch, tmp_path_factory):
    """``ExperimentSweepsReference`` maps every experiment name to both per-combination mappings."""

    class FakeJob:
        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        assert multirun is True
        model_name = config.model_name
        return [
            FakeJob(
                {"build": {"model_name": model_name}, "settings": {"parameters": {"phi": phi}}},
                {model_name: _signal_frame([phi])},
            )
            for phi in (0.1, 0.2)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    registry = FakeRegistry(
        runs={
            "turn_left": _run_config("my.Model"),
            "straight_driving": _run_config("my.Model"),
        },
        model_name="my.Model",
    )
    reference_run_config = _run_config("ref.Model")

    class T(testing.ExperimentSweepsReference):
        name = ["turn_left", "straight_driving"]
        sweep_params = {"phi": [0.1, 0.2]}

    T.fetch_reference_sweep(registry, reference_run_config, tmp_path_factory)

    assert set(T.results) == set(T.reference_results) == {"turn_left", "straight_driving"}
    for name in ("turn_left", "straight_driving"):
        assert set(T.results[name]) == set(T.reference_results[name]) == {(0.1,), (0.2,)}
        assert T.results[name][(0.2,)]["signal"].iloc[0] == 0.2
        assert T.reference_results[name][(0.2,)]["signal"].iloc[0] == 0.2
    T().assert_matches_reference()


def test_reference_sweep_launches_reference_pass_with_reference_run_config(monkeypatch, tmp_path_factory):
    """The reference pass launches against ``reference_run_config``; the candidate uses the default.

    Pins the delegation's central guarantee: dropping ``run_config`` from the reference
    pass would launch both sides against the registry default and still compare matching
    tables, so only the resolved run configs distinguish the two.
    """

    class RecordingRegistry(FakeRegistry):
        """Fake registry recording the run config each sweep launch resolved."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.run_config_calls: list = []

        def get_experiment_run_config(self, name, run_config=None):
            self.run_config_calls.append(run_config)
            return super().get_experiment_run_config(name, run_config=run_config)

    class FakeJob:
        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        model_name = config.model_name
        return [
            FakeJob(
                {"build": {"model_name": model_name}, "settings": {"parameters": {"phi": phi}}},
                {model_name: _signal_frame([phi])},
            )
            for phi in (0.1, 0.2)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    default_run = _run_config("my.Model")
    registry = RecordingRegistry(runs={"turn_left": default_run}, model_name="my.Model")
    reference_run_config = _run_config("ref.Model")

    class T(testing.ExperimentSweepReference):
        name = "turn_left"
        sweep_params = {"phi": [0.1, 0.2]}

    T.fetch_reference_sweep(registry, reference_run_config, tmp_path_factory)

    assert registry.run_config_calls == [None, reference_run_config]
    assert set(T.results) == set(T.reference_results) == {(0.1,), (0.2,)}
    T().assert_matches_reference()


def test_reference_sweep_comparison_rejects_missing_combination():
    class T(testing.ExperimentSweepReference):
        name = "turn_left"
        sweep_params = {"phi": [0.1, 0.2]}
        results = {(0.1,): _signal_frame([0.1])}
        reference_results = {(0.1,): _signal_frame([0.1]), (0.2,): _signal_frame([0.2])}

    with pytest.raises(AssertionError, match="0.2"):
        T().assert_matches_reference()


def test_reference_sweep_comparison_rejects_value_mismatch():
    class T(testing.ExperimentSweepReference):
        name = "turn_left"
        sweep_params = {"phi": [0.1, 0.2]}
        results = {(0.1,): _signal_frame([0.1])}
        reference_results = {(0.1,): _signal_frame([0.2])}

    with pytest.raises(AssertionError, match="signal"):
        T().assert_matches_reference()


def test_sweep_job_config_missing_model_name_raises(monkeypatch, tmp_path_factory):
    """A job whose composed config lacks ``model_name`` fails instead of mis-keying its table."""

    class FakeJob:
        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    def fake_simulate(config, *, overrides, multirun, sweep_dir, registry):
        assert multirun is True
        return [
            FakeJob({"settings": {"parameters": {"phi": phi}}}, {"my.Model": _frame(f"phi={phi}")})
            for phi in (0.1, 0.2)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = FakeRegistry(runs={"turn_left": _run_config("my.Model")})

    class T(testing.ExperimentSweep):
        name = "turn_left"
        sweep_params = {"phi": [0.1, 0.2]}

    with pytest.raises(ValueError, match="model_name"):
        T.fetch_sweep(fake_registry, tmp_path_factory)


def test_reference_comparison_accepts_same_run_config_for_both_models(monkeypatch):
    """Passing one run config for both sides compares a model against itself."""

    def fake_simulate(config, **kwargs):
        return {config["build"]["model_name"]: _signal_frame([1.0, 2.0])}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    shared = _run_config("my.Model")
    registry = FakeRegistry(model_name="my.Model")

    class T(testing.ExperimentReference):
        name = "standstill"

    T.fetch_reference_experiment(registry, shared)

    assert T.results["signal"].iloc[0] == 1.0
    assert T.reference_results["signal"].iloc[0] == 1.0
    T().assert_matches_reference()


def test_multi_experiment_reference_keys_each_name_by_its_own_model_name(monkeypatch):
    """Each experiment name is attributed to the model name its own composed config carries."""

    class PerNameRegistry(FakeRegistry):
        def compose_experiment(self, name, run_config=None, overrides=None):
            self.calls.append({"compose_experiment": name, "overrides": overrides, "run_config": run_config})
            model_name = "ref.Model" if run_config is not None else f"my.{name}"
            return OmegaConf.create({"composed_experiment": name, "build": {"model_name": model_name}})

    def fake_simulate(config, **kwargs):
        model_name = config["build"]["model_name"]
        return {model_name: _frame(f"{config['composed_experiment']}:{model_name}")}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    registry = PerNameRegistry()
    reference_run_config = _run_config("ref.Model")

    class T(testing.ExperimentsReference):
        name = ["a", "b"]

    T.fetch_reference_experiment(registry, reference_run_config)

    assert T.results["a"]["tag"].iloc[0] == "a:my.a"
    assert T.results["b"]["tag"].iloc[0] == "b:my.b"
    assert T.reference_results["a"]["tag"].iloc[0] == "a:ref.Model"
    assert T.reference_results["b"]["tag"].iloc[0] == "b:ref.Model"
