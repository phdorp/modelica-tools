"""Fixture-wiring tests for ``mtools.testing`` experiment base classes.

``test_testing.py`` drives ``fetch_experiment``/``fetch_sweep`` directly,
so the actual ``@pytest.fixture(autouse=True, scope="class") @classmethod``
path (argument-name injection of the module-level ``model_name`` and
``registry`` fixtures plus the builtin ``tmp_path_factory``) had zero
coverage. These tests run a real inner pytest session via the ``pytester``
fixture, so a fixture typo surfaces here instead of only in the slow
example suite.
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


def _fake_simulate(config, **kwargs):
    """Stand in for ``mtools.sim_tools.simulate`` in single-run and sweep modes."""
    if kwargs.get("multirun"):
        return [
            _FakeJob(
                {"session": {"parameters": {"phi": phi}}},
                {"my.Model": _frame(f"phi={phi}")},
            )
            for phi in (0.1, 0.2)
        ]
    return {"my.Model": _frame(config["composed_experiment"])}


INNER_MODULE = textwrap.dedent(
    """\
    import pytest

    from mtools import testing


    class FakeRegistry:
        def __init__(self, runs=None):
            self._runs = runs or {}

        def compose_experiment(self, name, overrides=None):
            return {"composed_experiment": name}

        def get_experiment_run_config(self, name):
            return self._runs[name]


    @pytest.fixture(scope="module")
    def model_name():
        return "my.Model"


    @pytest.fixture(scope="module")
    def registry():
        return FakeRegistry(runs={"turn_left": object()})


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
    """
)


def test_classmethod_fixtures_wire_model_name_registry_and_tmp_path(pytester, monkeypatch):
    """The autouse class-scoped fixtures populate ``results`` from module fixtures."""
    monkeypatch.setattr(sim_tools, "simulate", _fake_simulate)
    pytester.makepyfile(test_wired_inner=INNER_MODULE)

    result = pytester.runpytest("-v")

    result.assert_outcomes(passed=2)
