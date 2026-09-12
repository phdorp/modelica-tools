"""Tests for ``mtools.testing`` experiment base classes.

``mtools.sim_tools.simulate`` is faked, so no OpenModelica installation is
needed. Covered behavior:

- single experiment (``Experiment``): composes the experiment by name via
  the registry, runs a single simulation, and stores the ``model_name``
  solution table in ``results``.
- multiple experiments (``Experiments``): same, but ``name`` is a list and
  ``results`` maps each name to its solution table.
- parameter sweep (``ExperimentSweep``): resolves the experiment's base
  config from the registry, fans out via multirun simulate with one
  comma-separated ``<prefix>.<param>`` override per entry in
  ``sweep_params``, and maps each cartesian-product tuple to its solution
  table.
"""

import dataclasses
from itertools import product as _product

import pandas as pd
from omegaconf import OmegaConf

import mtools.internal.testing as internal_testing
import mtools.sim_tools as sim_tools
import mtools.testing as testing


def _frame(tag: str) -> pd.DataFrame:
    """Build a minimal solution table tagged for later identification."""
    return pd.DataFrame({"time": [0.0, 1.0], "tag": [tag, tag]})


class FakeRegistry:
    """Test double for ``HydraZenRegistry`` recording experiment calls."""

    def __init__(self, runs=None):
        self.calls: list = []
        self._runs = runs or {}

    def compose_experiment(self, name, overrides=None):
        """Record the call and return the name as the composed config."""
        self.calls.append({"compose_experiment": name, "overrides": overrides})
        return {"composed_experiment": name}

    def get_experiment_run_config(self, name):
        """Return the run config registered for experiment ``name``."""
        return self._runs[name]


def test_single_experiment_uses_registry_and_model_name(monkeypatch):
    """Single experiment composes the experiment by name and stores the ``model_name`` table."""
    captured = {}

    def fake_simulate(config, **kwargs):
        captured["config"] = config
        assert kwargs == {}
        return {"my.Model": _frame("single")}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = FakeRegistry()

    class T(testing.Experiment):
        name = "standstill"

    T.fetch_experiment(fake_registry, "my.Model")

    assert fake_registry.calls == [{"compose_experiment": "standstill", "overrides": None}]
    assert captured["config"] == {"composed_experiment": "standstill"}
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

    T.fetch_experiment(fake_registry, "my.Model")

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

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        captured["config"] = config
        captured["overrides"] = overrides
        captured["multirun"] = multirun
        captured["sweep_dir"] = sweep_dir
        assert multirun is True
        return [
            FakeJob(
                {"session": {"parameters": {"phi": phi}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, phi in enumerate((0.1, 0.2))
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = object()
    fake_registry = FakeRegistry(runs={"turn_left": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {"phi": [0.1, 0.2]}
        name = "turn_left"

    T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)

    assert captured["config"] is sentinel_run
    assert captured["overrides"] == ["experiment=turn_left", "session.parameters.phi=0.1,0.2"]
    assert set(T.results.keys()) == {(0.1,), (0.2,)}


def test_sweep_results_keyed_by_job_config_not_launch_order(monkeypatch, tmp_path_factory):
    """Jobs returned out of Cartesian order still attribute each table to its own sweep value."""

    class FakeJob:
        """Test double for ``SweepResult`` exposing per-job ``config`` and ``solutions``."""

        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        assert multirun is True
        jobs = [
            FakeJob(
                {"session": {"parameters": {"phi": phi}}},
                {"my.Model": _frame(f"phi={phi}")},
            )
            for phi in (0.1, 0.2)
        ]
        return jobs[::-1]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = FakeRegistry(runs={"turn_left": object()})

    class T(testing.ExperimentSweep):
        sweep_params = {"phi": [0.1, 0.2]}
        name = "turn_left"

    T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)

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

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        captured["overrides"] = overrides
        assert multirun is True
        combos = list(_product([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)], [5, 10], [True, False]))
        return [
            FakeJob(
                {"session": {"parameters": {"state_0": list(state), "v_norm": v, "flag": flag}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, (state, v, flag) in enumerate(combos)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = object()
    fake_registry = FakeRegistry(runs={"straight_driving": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {
            "state_0": [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
            "v_norm": [5, 10],
            "flag": [True, False],
        }
        name = "straight_driving"

    T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "session.parameters.state_0=[0.0,0.0,0.0],[1.0,0.0,0.0]",
        "session.parameters.v_norm=5,10",
        "session.parameters.flag=true,false",
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

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        captured["overrides"] = overrides
        assert multirun is True
        states = [
            {"px": 0.0, "py": 0.0, "theta": 0.0},
            {"px": 1.0, "py": 0.0, "theta": 0.0},
        ]
        return [
            FakeJob(
                {"session": {"parameters": {"state_0": dict(state)}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, state in enumerate(states)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = object()
    fake_registry = FakeRegistry(runs={"straight_driving": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {
            "state_0": [{"px": 0.0, "py": 0.0, "theta": 0.0}, {"px": 1.0, "py": 0.0, "theta": 0.0}],
        }
        name = "straight_driving"

    T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "session.parameters.state_0={px:0.0,py:0.0,theta:0.0},{px:1.0,py:0.0,theta:0.0}",
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

        def compose_experiment(self, name, overrides=None):
            self.calls.append({"compose_experiment": name, "overrides": overrides})
            return OmegaConf.create(
                {"session": {"parameters": {"state_0": {"px": 0.0, "py": 0.0, "theta": 0.0}}}}
            )

    captured = {}

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        captured["overrides"] = overrides
        assert multirun is True
        states = [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0)]
        fields = ("px", "py", "theta")
        return [
            FakeJob(
                {"session": {"parameters": {"state_0": dict(zip(fields, state))}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, state in enumerate(states)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = object()
    fake_registry = StructuredRegistry(runs={"straight_driving": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {"state_0": [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0)]}
        name = "straight_driving"

    T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "session.parameters.state_0={px:0.0,py:0.0,theta:0.0},{px:1.0,py:2.0,theta:3.0}",
    ]
    assert set(T.results.keys()) == {((0.0, 0.0, 0.0),), ((1.0, 2.0, 3.0),)}


def test_sweep_tuple_arity_mismatch_raises(monkeypatch, tmp_path_factory):
    """A tuple whose arity differs from the structured target's field count raises ValueError."""

    class StructuredRegistry(FakeRegistry):
        """Fake registry composing a structured config exposing ``state_0`` fields."""

        def compose_experiment(self, name, overrides=None):
            return OmegaConf.create(
                {"session": {"parameters": {"state_0": {"px": 0.0, "py": 0.0, "theta": 0.0}}}}
            )

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        raise AssertionError("simulate must not run when tuple arity mismatches")

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = StructuredRegistry(runs={"straight_driving": object()})

    class T(testing.ExperimentSweep):
        sweep_params = {"state_0": [(0.0, 0.0)]}
        name = "straight_driving"

    try:
        T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)
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

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        captured["overrides"] = overrides
        assert multirun is True
        combos = list(_product((0.0, 1.0), (0.0, 1.0)))
        jobs = [
            FakeJob(
                {"session": {"parameters": {"state_0": {"px": px, "py": py}}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, (px, py) in enumerate(combos)
        ]
        return [jobs[i] for i in (2, 0, 3, 1)]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = object()
    fake_registry = FakeRegistry(runs={"straight_driving": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {"state_0.px": [0.0, 1.0], "state_0.py": [0.0, 1.0]}
        name = "straight_driving"

    T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "session.parameters.state_0.px=0.0,1.0",
        "session.parameters.state_0.py=0.0,1.0",
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

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        captured["overrides"] = overrides
        assert multirun is True
        states = [
            {"px": 0.0, "py": 0.0, "theta": 0.0},
            {"px": 1.0, "py": 0.0, "theta": 0.0},
        ]
        return [
            FakeJob(
                {"session": {"parameters": {"state_0": dict(state)}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, state in enumerate(states)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = object()
    fake_registry = FakeRegistry(runs={"straight_driving": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_params = {
            "state_0": [_State(px=0.0), _State(px=1.0)],
        }
        name = "straight_driving"

    T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "session.parameters.state_0={px:0.0,py:0.0,theta:0.0},{px:1.0,py:0.0,theta:0.0}",
    ]
    assert set(T.results.keys()) == {
        ((("px", 0.0), ("py", 0.0), ("theta", 0.0)),),
        ((("px", 1.0), ("py", 0.0), ("theta", 0.0)),),
    }


def test_sweep_duplicate_frozen_keys_raise(monkeypatch, tmp_path_factory):
    """Sweep values collapsing to the same frozen key (True vs 1) fail fast."""

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        raise AssertionError("simulate must not run when frozen keys collide")

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = FakeRegistry(runs={"exp": object()})

    class T(testing.ExperimentSweep):
        sweep_params = {"flag": [True, 1]}
        name = "exp"

    try:
        T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)
    except ValueError as exc:
        assert "duplicate result keys" in str(exc)
    else:
        raise AssertionError("expected ValueError for colliding frozen keys")


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

        def compose_experiment(self, name, overrides=None):
            self.calls.append({"compose_experiment": name, "overrides": overrides})
            return OmegaConf.create(
                {"session": {"parameters": {"state_0": {"px": 0.0, "py": 0.0, "theta": 0.0}}}}
            )

    captured = {}

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        captured["overrides"] = overrides
        assert multirun is True
        states = [
            {"px": 0.0, "py": 0.0, "theta": 0.0},
            {"px": 1.0, "py": 2.0, "theta": 3.0},
        ]
        return [
            FakeJob(
                {"session": {"parameters": {"state_0": dict(state)}}},
                {"my.Model": _frame(f"s{i}")},
            )
            for i, state in enumerate(states)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    fake_registry = StructuredRegistry(runs={"straight_driving": object()})

    class T(testing.ExperimentSweep):
        sweep_params = {"state_0": [_State(), _State(px=1.0, py=2.0, theta=3.0)]}
        name = "straight_driving"

    T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)

    assert captured["overrides"] == [
        "experiment=straight_driving",
        "session.parameters.state_0={px:0.0,py:0.0,theta:0.0},{px:1.0,py:2.0,theta:3.0}",
    ]
    assert set(T.results.keys()) == {
        ((("px", 0.0), ("py", 0.0), ("theta", 0.0)),),
        ((("px", 1.0), ("py", 2.0), ("theta", 3.0)),),
    }


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
