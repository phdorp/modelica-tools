"""Fixture-wiring tests for ``mtools.testing`` experiment base classes.

``test_testing.py`` drives ``fetch_experiment``/``fetch_sweep`` directly,
so the actual ``@pytest.fixture(autouse=True, scope="class") @classmethod``
path (argument-name injection of the module-level ``model_name``,
``registry``, ``reference_name``, and ``reference_registry`` fixtures plus the
builtin ``tmp_path_factory``) had zero coverage. These tests run a real inner
pytest session via the ``pytester`` fixture, so a fixture typo surfaces here
instead of only in the slow example suite.
"""

import textwrap

import mtools.sim_tools as sim_tools

# ``pytester`` is a builtin but opt-in plugin in this pytest version, so it
# must be requested explicitly for the ``pytester`` fixture below.
pytest_plugins = ["pytester"]


def _frame(tag):
    """Build a minimal solution table tagged for later identification."""
    import pandas as pd

    return pd.DataFrame({"time": [0.0, 1.0], "tag": [tag, tag]})


class _FakeJob:
    """Test double for ``SweepResult`` exposing per-job ``config`` and ``solutions``."""

    def __init__(self, config, solutions):
        self.config = config
        self.solutions = solutions


def _config_model_name(config):
    """Read ``model_name`` from a composed DictConfig or a base run config object."""
    if isinstance(config, dict):
        return config.get("model_name", "my.Model")
    return getattr(config, "model_name", "my.Model")


def _fake_simulate(config, **kwargs):
    """Stand in for ``mtools.sim_tools.simulate`` in single-run and sweep modes."""
    if kwargs.get("multirun"):
        model_name = _config_model_name(config)
        is_reference = model_name == "ref.Model"
        return [
            _FakeJob(
                {"session": {"parameters": {"phi": phi}}},
                {model_name: _frame(f"ref={phi}" if is_reference else f"phi={phi}")},
            )
            for phi in (0.1, 0.2)
        ]
    model_name = _config_model_name(config)
    tag = "reference" if model_name == "ref.Model" else config["composed_experiment"]
    return {model_name: _frame(tag)}


INNER_MODULE = textwrap.dedent(
    """\
    from types import SimpleNamespace

    import pytest

    from mtools import testing


    class FakeRegistry:
        def __init__(self, model_name, runs=None):
            self.model_name = model_name
            self._runs = runs or {}

        def add_to_hydra_store(self, overwrite_ok=None):
            pass

        def compose_experiment(self, name, overrides=None):
            return {"composed_experiment": name, "model_name": self.model_name}

        def get_experiment_run_config(self, name):
            return self._runs[name]


    @pytest.fixture(scope="module")
    def model_name():
        return "my.Model"


    @pytest.fixture(scope="module")
    def reference_name():
        return "ref.Model"


    @pytest.fixture(scope="module")
    def registry():
        return FakeRegistry(
            model_name="my.Model",
            runs={"turn_left": SimpleNamespace(model_name="my.Model")},
        )


    @pytest.fixture(scope="module")
    def reference_registry():
        return FakeRegistry(
            model_name="ref.Model",
            runs={"turn_left": SimpleNamespace(model_name="ref.Model")},
        )


    class TestSingle(testing.Experiment):
        name = "standstill"

        def test_results_populated_by_class_fixture(self):
            assert self.results["tag"].iloc[0] == "standstill"


    class TestSweep(testing.ExperimentSweep):
        name = "turn_left"
        sweep_params = {"phi": [0.1, 0.2]}

        def test_results_populated_by_class_fixture(self):
            assert set(self.results) == {(0.1,), (0.2,)}
            assert self.results[(0.2,)]["tag"].iloc[0] == "phi=0.2"


    class TestReference(testing.ExperimentReference):
        name = "standstill"

        def test_results_populated_by_class_fixture(self):
            assert self.results["tag"].iloc[0] == "standstill"
            assert self.reference_results["tag"].iloc[0] == "reference"


    class TestReferenceSweep(testing.ExperimentSweepReference):
        name = "turn_left"
        sweep_params = {"phi": [0.1, 0.2]}

        def test_results_populated_by_class_fixture(self):
            assert self.reference_results[(0.2,)]["tag"].iloc[0] == "ref=0.2"
    """
)


def test_classmethod_fixtures_wire_model_name_registry_and_tmp_path(pytester, monkeypatch):
    """The autouse class-scoped fixtures populate ``results`` from module fixtures."""
    monkeypatch.setattr(sim_tools, "simulate", _fake_simulate)
    pytester.makepyfile(test_wired_inner=INNER_MODULE)

    result = pytester.runpytest("-v")

    result.assert_outcomes(passed=4)
