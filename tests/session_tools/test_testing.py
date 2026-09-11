"""Tests for ``mtools.testing`` experiment base classes.

``mtools.sim_tools.simulate`` is faked, so no OpenModelica installation is
needed. Covered behavior:

- single experiment (``Experiment``): composes the experiment by name via
  the registry, runs a single simulation, and stores the ``model_name``
  solution table in ``results``.
- multiple experiments (``Experiments``): same, but ``name`` is a list and
  ``results`` maps each name to its solution table.
- parameter sweep (``ExperimentSweep``): resolves the experiment's base
  config from the registry, fans out via multirun simulate with a
  comma-separated ``<prefix>.<sweep_param>`` override, and maps each value
  in ``sweep_values`` to its solution table.
"""

import pandas as pd

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
    """Sweep resolves the multirun base config from the registry and keys results by value."""
    captured = {}

    class FakeJob:
        """Test double for ``SweepResult`` exposing per-job ``solutions``."""

        def __init__(self, solutions):
            self.solutions = solutions

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        captured["config"] = config
        captured["overrides"] = overrides
        captured["multirun"] = multirun
        captured["sweep_dir"] = sweep_dir
        assert multirun is True
        return [FakeJob({"my.Model": _frame("s0")}), FakeJob({"my.Model": _frame("s1")})]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    sentinel_run = object()
    fake_registry = FakeRegistry(runs={"turn_left": sentinel_run})

    class T(testing.ExperimentSweep):
        sweep_param = "phi"
        sweep_values = [0.1, 0.2]
        name = "turn_left"

    T.fetch_sweep("my.Model", fake_registry, tmp_path_factory)

    assert captured["config"] is sentinel_run
    assert captured["overrides"] == ["experiment=turn_left", "session.parameters.phi=0.1,0.2"]
    assert set(T.results.keys()) == {0.1, 0.2}
