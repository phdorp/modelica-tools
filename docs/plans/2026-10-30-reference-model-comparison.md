# Reference Model Comparison Implementation Plan

**Goal:** Add pytest test bases that simulate a candidate model and a reference model from their own Hydra registries, expose both result sets, and assert that their output signals and values match. The reference model may use different parameters and live in a separate Modelica package.

**Architecture:** New public comparison bases in `mtools.testing` reuse the existing `Experiment` and `ExperimentSweep` machinery for the candidate run from `registry`, then run the same experiment name from a dedicated `reference_registry`. Each registry owns its own parameters, model source, model configurations, libraries, and simulation settings. A shared comparison helper recursively checks result keys, signal columns, and values. Sweeps reuse the existing sweep planner and attribution against each registry's base run config and write to independent temporary sweep directories. Core session construction stays unchanged; no model-selection overrides or configuration retargeting are needed.

**Tech Stack:** Python 3.11, pytest, pandas, numpy, Hydra / hydra-zen, Modelica via pydelica.

**Spec:** `docs/specs/2026-10-30-reference-model-comparison-spec.md`

> **Revision 2 (superseded):** Added `reference_model_path` and model/source
> overrides to reuse the candidate registry.
>
> **Revision 3 (implemented):** The reference model has its own Hydra registry.
> Comparison bases require `reference_registry` instead of
> `reference_model_path` and run the same experiment name from each registry.
> Core session construction is unchanged; the previous model-selection and
> configuration-retargeting changes were reverted. The example reference model
> remains in `examples/tests/reference_models` and now has its own registry in
> `examples/tests/reference_experiments.py`.

## Global Constraints

- Python >= 3.11.
- Public API lives in `mtools.testing`; private helpers live in `mtools.internal.testing`.
- `reference_name` is a Modelica model name; the dedicated `reference_registry` owns its source file or package. The reference source may be a separate package from the candidate.
- Candidate and reference registries register the same experiment name. The reference config adds no model or source overrides.
- Comparison uses `rtol=0` and `atol=eps`.
- `eps` defaults to `numpy.finfo(float).eps` and is overridable per test class.
- The comparison is explicit; it never runs automatically at fixture time.
- Both models must expose the same output signal columns; comparison never ignores a column.
- Result keys and columns are matched by name, never by row or launch order.
- Unit tests fake `sim_tools.simulate`; only the example integration test needs OpenModelica.
- Run `uv run pytest tests`, `uv run mypy src tests`, and `uv run isort --check-only src tests examples` before claiming completion.

## Review Focus

- A reference model missing from the source file must fail with the existing simulation error, not compare the candidate against itself.
- Extra or missing output signals must fail with a message that lists both sets.
- Two solution tables with different row counts must fail with a length message, not an opaque numpy broadcast error.
- A sweep with a missing or extra parameter combination must fail and name the combination.
- A NaN versus a finite value must fail rather than pass silently.
- Candidate and reference registries may reuse the same config and experiment names; activating one registry must replace the other's entries in Hydra's global store.

## File Structure

- `src/mtools/internal/testing.py` - add `assert_solutions_match` and table comparison helper; make `_SweepPlan.launch` activate its registry's Hydra store before launching.
- `src/mtools/hydra_registry.py` - make `add_to_hydra_store(overwrite_ok=True)` re-enqueue registered entries so registries sharing names can be activated in turn.
- `src/mtools/testing.py` - add `_ReferenceComparisonMixin`, `ExperimentReferenceT`, `ExperimentSweepReferenceT`, four public aliases, exports, and module/fixture documentation.
- `tests/session_tools/test_testing.py` - unit tests driving the comparison bases with a fake `sim_tools.simulate` and separate candidate/reference registries.
- `tests/session_tools/test_testing_fixtures.py` - `pytester` wiring test proving `reference_name` and `reference_registry` injection and autouse population.
- `examples/tests/reference_models/` - separate Modelica package for the reference model.
- `examples/tests/reference_experiments.py` - dedicated registry and experiments for the reference model.
- `examples/tests/test_reference_comparison.py` - real single-experiment and sweep comparison tests across registries and packages.
- `examples/README.md` - document the reference comparison workflow.
- `README.md` - add reference comparison to the feature list.

## Tasks

### Task 1: Comparison helper and single-experiment reference base

**Files:**
- Modify: `src/mtools/internal/testing.py`
- Modify: `src/mtools/testing.py`
- Test: `tests/session_tools/test_testing.py`
- Test: `tests/session_tools/test_testing_fixtures.py`

**Interfaces:**
- Consumes: existing `ExperimentT.fetch_experiment(registry, model_name)`, `sim_tools.simulate`, `registry.compose_experiment(name, overrides)`.
- Produces:
  - `mtools.internal.testing.assert_solutions_match(actual: Any, reference: Any, *, atol: float, context: str, rtol: float = 0.0) -> None`
  - `mtools.testing.ExperimentReferenceT.fetch_reference_experiment(registry: HydraZenRegistry, model_name: str, reference_name: str) -> None`
  - `mtools.testing.ExperimentReference` and `mtools.testing.ExperimentsReference`
  - `assert_matches_reference(self) -> None` on both aliases.

- [ ] **Step 1: Write the failing unit tests**

Add `import numpy as np` and `import pytest` to `tests/session_tools/test_testing.py`, plus a numeric frame helper:

```python
def _signal_frame(values, signal="signal"):
    return pd.DataFrame({"time": [float(i) for i in range(len(values))], signal: values})
```

Add these tests:

```python
def test_reference_experiment_uses_model_name_override_for_reference(monkeypatch):
    class ReferenceRegistry(FakeRegistry):
        def compose_experiment(self, name, overrides=None):
            self.calls.append({"compose_experiment": name, "overrides": overrides})
            model_name = "my.Model"
            for override in overrides or []:
                if override.startswith("model_name="):
                    model_name = override.split("=", 1)[1]
            return {"composed_experiment": name, "model_name": model_name}

    def fake_simulate(config, **kwargs):
        model_name = config["model_name"]
        return {model_name: _frame(model_name)}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    registry = ReferenceRegistry()

    class T(testing.ExperimentReference):
        name = "standstill"

    T.fetch_reference_experiment(registry, "my.Model", "ref.Model")

    assert registry.calls == [
        {"compose_experiment": "standstill", "overrides": None},
        {"compose_experiment": "standstill", "overrides": ["model_name=ref.Model"]},
    ]
    assert T.results["tag"].iloc[0] == "my.Model"
    assert T.reference_results["tag"].iloc[0] == "ref.Model"


def test_reference_experiment_multi_name_returns_mappings(monkeypatch):
    class ReferenceRegistry(FakeRegistry):
        def compose_experiment(self, name, overrides=None):
            model_name = "my.Model"
            for override in overrides or []:
                if override.startswith("model_name="):
                    model_name = override.split("=", 1)[1]
            return {"composed_experiment": name, "model_name": model_name}

    def fake_simulate(config, **kwargs):
        model_name = config["model_name"]
        tag = f"{model_name}:{config['composed_experiment']}"
        return {model_name: _frame(tag)}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)

    class T(testing.ExperimentsReference):
        name = ["a", "b"]

    T.fetch_reference_experiment(ReferenceRegistry(), "my.Model", "ref.Model")

    assert T.results["a"]["tag"].iloc[0] == "my.Model:a"
    assert T.reference_results["b"]["tag"].iloc[0] == "ref.Model:b"


def test_reference_experiment_propagates_missing_reference_solution(monkeypatch):
    def fake_simulate(config, **kwargs):
        if config["model_name"] == "ref.Model":
            raise ValueError("No solution matches the requested model 'ref.Model'.")
        return {"my.Model": _frame("candidate")}

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)

    class ReferenceRegistry(FakeRegistry):
        def compose_experiment(self, name, overrides=None):
            model_name = "my.Model"
            for override in overrides or []:
                if override.startswith("model_name="):
                    model_name = override.split("=", 1)[1]
            return {"composed_experiment": name, "model_name": model_name}

    class T(testing.ExperimentReference):
        name = "standstill"

    with pytest.raises(ValueError, match="No solution matches"):
        T.fetch_reference_experiment(ReferenceRegistry(), "my.Model", "ref.Model")


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
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/session_tools/test_testing.py -k reference -v`

Expected: FAIL because `testing.ExperimentReference` and `assert_solutions_match` do not exist.

- [ ] **Step 3: Implement the comparison helper**

In `src/mtools/internal/testing.py`, add `numpy` and `pandas` imports and:

```python
def assert_solutions_match(
    actual: Any,
    reference: Any,
    *,
    atol: float,
    context: str,
    rtol: float = 0.0,
) -> None:
    """Recursively assert that candidate solutions match reference solutions."""
```

Implementation rules:

- A `pandas.DataFrame` reference compares against an `actual` DataFrame.
- A `dict` reference requires the same key set in `actual`; recurse with `context=f"{context}[{key!r}]"`.
- A table with missing or extra columns raises `AssertionError(f"{context}: output signals differ; missing {missing!r}, unexpected {extra!r}")`.
- A table with a different row count raises `AssertionError(f"{context}: solution length differs ({len(actual)} != {len(reference)})")`.
- Each reference column is compared positionally with `numpy.testing.assert_allclose(actual[column], reference[column], rtol=rtol, atol=atol, err_msg=f"{context}: signal {column!r} differs")`.
- Any other reference type raises `TypeError`.

- [ ] **Step 4: Implement the single-experiment comparison base**

In `src/mtools/testing.py`, add a mixin and generic class. Use `ClassVar`, `Any`, `cast`, and `np` already imported.

```python
class _ReferenceComparisonMixin:
    eps: ClassVar[float] = np.finfo(float).eps
    results: Any
    reference_results: Any

    def assert_matches_reference(self) -> None:
        _internal.assert_solutions_match(
            self.results,
            self.reference_results,
            atol=self.eps,
            context=f"{type(self).__name__}(name={getattr(self, 'name', None)!r})",
        )


class ExperimentReferenceT(_ReferenceComparisonMixin, ExperimentT[NameType, ResultType]):
    reference_results: ResultType

    @classmethod
    def fetch_reference_experiment(
        cls, registry: HydraZenRegistry, model_name: str, reference_name: str
    ) -> None:
        """Run the experiment for both the candidate and reference models."""
        super().fetch_experiment(registry, model_name)
        names = [cls.name] if isinstance(cls.name, str) else cls.name
        reference_results = {
            name: sim_tools.simulate(
                registry.compose_experiment(name, overrides=[f"model_name={reference_name}"])
            )[reference_name]
            for name in names
        }
        cls.reference_results = cast(
            ResultType,
            reference_results[cls.name] if isinstance(cls.name, str) else reference_results,
        )

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_experiment(cls, registry: HydraZenRegistry, model_name: str, reference_name: str):
        """Class-scoped fixture populating candidate and reference results."""
        cls.fetch_reference_experiment(registry, model_name, reference_name)
```

Add the aliases and exports:

```python
ExperimentReference = ExperimentReferenceT[str, pd.DataFrame]
ExperimentsReference = ExperimentReferenceT[list[str], dict[str, pd.DataFrame]]
```

Add all new public names to `__all__`, and extend the module docstring's fixture table with `reference_name`.

- [ ] **Step 5: Run the unit tests and verify they pass**

Run: `uv run pytest tests/session_tools/test_testing.py -k reference -v`

Expected: PASS.

- [ ] **Step 6: Add the pytester fixture-wiring test**

In `tests/session_tools/test_testing_fixtures.py`:

- Add a module-level `reference_name` fixture returning `"ref.Model"` inside `INNER_MODULE`.
- Update the inner `FakeRegistry.compose_experiment` to copy `model_name=<value>` overrides into the returned config.
- Update `_fake_simulate` so single runs use `config.get("model_name", "my.Model")` as the solution key, and return tag `"reference"` for `"ref.Model"` and the experiment name otherwise.
- Add:

```python
class TestReference(testing.ExperimentReference):
    name = "standstill"

    def test_results_populated_by_class_fixture(self):
        assert self.results["tag"].iloc[0] == "standstill"
        assert self.reference_results["tag"].iloc[0] == "reference"
```

- Change the final assertion to `result.assert_outcomes(passed=3)`.

Run: `uv run pytest tests/session_tools/test_testing_fixtures.py -v`

Expected: PASS with 3 passed tests.

- [ ] **Step 7: Commit**

```bash
git add src/mtools/internal/testing.py src/mtools/testing.py tests/session_tools/test_testing.py tests/session_tools/test_testing_fixtures.py
git commit -m "feat: add single-experiment reference model comparison base"
```

### Task 2: Sweep reference base

**Files:**
- Modify: `src/mtools/internal/testing.py` (`_SweepPlan.launch`)
- Modify: `src/mtools/testing.py`
- Test: `tests/session_tools/test_testing.py`
- Test: `tests/session_tools/test_testing_fixtures.py`

**Interfaces:**
- Consumes: Task 1's `_ReferenceComparisonMixin` and `assert_solutions_match`.
- Produces:
  - `_SweepPlan.launch(registry, tmp_path_factory, *, model_name: str | None = None) -> list`
  - `mtools.testing.ExperimentSweepReferenceT.run_single_reference_sweep(name: str, reference_name: str, registry: HydraZenRegistry, tmp_path_factory: Any) -> dict[tuple[Hashable, ...], pd.DataFrame]`
  - `mtools.testing.ExperimentSweepReferenceT.fetch_reference_sweep(model_name: str, reference_name: str, registry: HydraZenRegistry, tmp_path_factory: Any) -> None`
  - `mtools.testing.ExperimentSweepReference` and `mtools.testing.ExperimentSweepsReference`.

- [ ] **Step 1: Write the failing sweep tests**

Add to `tests/session_tools/test_testing.py`:

```python
def test_reference_sweep_uses_model_override_and_matches_combinations(monkeypatch, tmp_path_factory):
    calls = []

    class FakeJob:
        def __init__(self, config, solutions):
            self.config = config
            self.solutions = solutions

    def fake_simulate(config, *, overrides, multirun, sweep_dir):
        calls.append({"overrides": list(overrides), "sweep_dir": sweep_dir})
        assert multirun is True
        model_name = next(
            (override.split("=", 1)[1] for override in overrides if override.startswith("model_name=")),
            "my.Model",
        )
        return [
            FakeJob(
                {"session": {"parameters": {"phi": phi}}},
                {model_name: pd.DataFrame({"time": [0.0, 1.0], "signal": [phi, phi]})},
            )
            for phi in (0.1, 0.2)
        ]

    monkeypatch.setattr(sim_tools, "simulate", fake_simulate)
    registry = FakeRegistry(runs={"turn_left": object()})

    class T(testing.ExperimentSweepReference):
        name = "turn_left"
        sweep_params = {"phi": [0.1, 0.2]}

    T.fetch_reference_sweep("my.Model", "ref.Model", registry, tmp_path_factory)

    assert calls[0]["overrides"] == ["experiment=turn_left", "session.parameters.phi=0.1,0.2"]
    assert calls[1]["overrides"] == [
        "experiment=turn_left",
        "session.parameters.phi=0.1,0.2",
        "model_name=ref.Model",
    ]
    assert calls[0]["sweep_dir"] != calls[1]["sweep_dir"]
    assert set(T.results) == set(T.reference_results) == {(0.1,), (0.2,)}
    assert T.reference_results[(0.2,)]["signal"].iloc[0] == 0.2
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
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `uv run pytest tests/session_tools/test_testing.py -k "reference_sweep" -v`

Expected: FAIL because `testing.ExperimentSweepReference` does not exist.

- [ ] **Step 3: Extend `_SweepPlan.launch`**

Change the signature in `src/mtools/internal/testing.py` to:

```python
def launch(
    self,
    registry: HydraZenRegistry,
    tmp_path_factory: Any,
    *,
    model_name: str | None = None,
) -> list:
```

Build the override list with `self.build_overrides()`, append `f"model_name={model_name}"` when `model_name is not None`, pass the result to `sim_tools.simulate`, and keep the existing per-experiment `mktemp` sweep directory. Existing callers must see unchanged overrides.

- [ ] **Step 4: Implement the sweep comparison base**

In `src/mtools/testing.py`, add:

```python
class ExperimentSweepReferenceT(
    _ReferenceComparisonMixin, ExperimentSweepT[NameType, SweepResultType]
):
    reference_results: SweepResultType

    @classmethod
    def run_single_reference_sweep(
        cls, name: str, reference_name: str, registry: HydraZenRegistry, tmp_path_factory: Any
    ) -> dict[tuple[Hashable, ...], pd.DataFrame]:
        """Run one reference sweep and map each parameter combination to its table."""
        plan = _internal._SweepPlan(cls.sweep_params, cls.sweep_param_prefix, name, registry)
        sweep_results = plan.launch(registry, tmp_path_factory, model_name=reference_name)
        return plan.attribute(sweep_results, reference_name)

    @classmethod
    def fetch_reference_sweep(
        cls, model_name: str, reference_name: str, registry: HydraZenRegistry, tmp_path_factory: Any
    ) -> None:
        """Sweep the experiment for both the candidate and reference models."""
        super().fetch_sweep(model_name, registry, tmp_path_factory)
        names = [cls.name] if isinstance(cls.name, str) else cls.name
        reference_results = {
            name: cls.run_single_reference_sweep(name, reference_name, registry, tmp_path_factory)
            for name in names
        }
        cls.reference_results = cast(
            SweepResultType,
            reference_results[cls.name] if isinstance(cls.name, str) else reference_results,
        )

    @pytest.fixture(autouse=True, scope="class")
    @classmethod
    def run_sweep(cls, model_name: str, reference_name: str, registry: HydraZenRegistry, tmp_path_factory):
        """Class-scoped fixture populating candidate and reference sweep results."""
        cls.fetch_reference_sweep(model_name, reference_name, registry, tmp_path_factory)
```

Add the aliases and exports:

```python
ExperimentSweepReference = ExperimentSweepReferenceT[str, dict[tuple[Hashable, ...], pd.DataFrame]]
ExperimentSweepsReference = ExperimentSweepReferenceT[
    list[str], dict[str, dict[tuple[Hashable, ...], pd.DataFrame]]
]
```

- [ ] **Step 5: Run the sweep tests and verify they pass**

Run: `uv run pytest tests/session_tools/test_testing.py -k "reference" -v`

Expected: PASS.

- [ ] **Step 6: Extend the pytester wiring test for sweeps**

In `tests/session_tools/test_testing_fixtures.py`:

- Update the multirun branch of `_fake_simulate` to read the `model_name` override from `kwargs["overrides"]`, defaulting to `"my.Model"`, and return solutions keyed by that model.
- Tag reference frames with `f"ref={phi}"` and candidate frames with `f"phi={phi}"`.
- Add:

```python
class TestReferenceSweep(testing.ExperimentSweepReference):
    name = "turn_left"
    sweep_params = {"phi": [0.1, 0.2]}

    def test_results_populated_by_class_fixture(self):
        assert self.reference_results[(0.2,)]["tag"].iloc[0] == "ref=0.2"
```

- Change the final assertion to `result.assert_outcomes(passed=4)`.

Run: `uv run pytest tests/session_tools/test_testing_fixtures.py -v`

Expected: PASS with 4 passed tests.

- [ ] **Step 7: Commit**

```bash
git add src/mtools/internal/testing.py src/mtools/testing.py tests/session_tools/test_testing.py tests/session_tools/test_testing_fixtures.py
git commit -m "feat: add sweep reference model comparison base"
```

### Task 3: Example model, example tests, and documentation

**Files:**
- Create: `examples/src/kinematic_vehicle/KinematicVehicleReference.mo`
- Create: `examples/tests/test_reference_comparison.py`
- Modify: `examples/README.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: `mtools.testing.ExperimentReference`, `mtools.testing.ExperimentSweepReference`, and their `assert_matches_reference()` method from Tasks 1 and 2.
- Produces: no library API; a working example and user-facing documentation.

- [ ] **Step 1: Add the reference Modelica model**

Create `examples/src/kinematic_vehicle/KinematicVehicleReference.mo` with:

```modelica
within kinematic_vehicle;

model KinematicVehicleReference
  parameter Real v_norm = 10 "velocity";
  parameter Real phi = 0.1 "steering angle";
  parameter Real l = 2 "wheelbase";
  parameter State state_0 = State(px=0, py=0, theta=0) "initial state";

  State state(px(start=state_0.px, fixed=true), py(start=state_0.py, fixed=true), theta(start=state_0.theta, fixed=true));
  Input control(v_norm=v_norm, phi=phi);

protected
  Real px_dot = der(state.px);
  Real py_dot = der(state.py);
  Real theta_dot = der(state.theta);

equation
  px_dot = v_norm * cos(state.theta);
  py_dot = v_norm * sin(state.theta);
  theta_dot = v_norm / l * tan(control.phi);
end KinematicVehicleReference;
```

- [ ] **Step 2: Add the example comparison tests**

Create `examples/tests/test_reference_comparison.py` with:

```python
import pytest
from mtools.testing import ExperimentReference, ExperimentSweepReference

from kinematic_vehicle.kinematic_vehicle import MODEL_NAME
from tests.experiments import registry as kinematic_registry

REFERENCE_NAME = "kinematic_vehicle.KinematicVehicleReference"


@pytest.fixture(scope="module")
def model_name():
    return MODEL_NAME


@pytest.fixture(scope="module")
def reference_name():
    return REFERENCE_NAME


@pytest.fixture(scope="module")
def registry():
    return kinematic_registry


class TestStandstillReference(ExperimentReference):
    name = "standstill"

    def test_matches_reference(self):
        self.assert_matches_reference()


class TestTurnLeftReference(ExperimentSweepReference):
    name = "turn_left"
    sweep_params = {"phi": [0.1, 0.5, 1.0]}

    def test_matches_reference(self):
        self.assert_matches_reference()
```

- [ ] **Step 3: Run the example tests and verify they pass**

Run: `uv pip install -e 'examples[test]' && cd examples && uv run pytest tests/test_reference_comparison.py -v`

Expected: PASS for both comparison classes. A failure here means the reference model is not visible from the package source or the `model_name` override is not reaching the simulation.

- [ ] **Step 4: Document the example**

In `examples/README.md`, add a "Compare against a reference model" section that explains:

- the candidate lives in `src` and the reference model is a separate Modelica package in `tests`;
- the reference model has its own registry and experiment registrations;
- the test module provides `model_name`, `reference_name`, `registry`, and `reference_registry` fixtures;
- the test class inherits `ExperimentReference` or `ExperimentSweepReference`;
- `assert_matches_reference()` compares signal sets and values within `eps`.

In `README.md`, add a feature bullet:

```markdown
- **Reference-model comparison** — Test a model against a reference implementation registered in a dedicated Hydra registry, comparing output signals and values.
```

- [ ] **Step 5: Run the full verification**

Run:

```bash
uv run pytest tests
uv pip install -e 'examples[test]'
cd examples && uv run pytest tests
cd .. && uv run mypy src tests
uv run isort --check-only src tests examples
```

Expected: all tests pass, mypy reports no errors, isort reports no changes.

- [ ] **Step 6: Commit**

```bash
git add examples/src/kinematic_vehicle/KinematicVehicleReference.mo examples/tests/test_reference_comparison.py examples/README.md README.md
git commit -m "docs: demonstrate reference model comparison"
```

## Self-review

- Spec coverage: single and multi-experiment comparison, sweeps, `reference_name` semantics, dedicated reference registry, per-registry parameters, signal checking, tolerance, errors, docs, and example are covered by Tasks 1-3.
- Step scan: every task has a failing test, an implementation step with exact signatures, a passing test run, and a commit.
- Type consistency: `reference_results`, `assert_matches_reference`, `fetch_reference_experiment`, `fetch_reference_sweep`, `reference_registry`, and `_SweepPlan.launch(registry, tmp_path_factory)` are used consistently across tasks.
- Review Focus: missing reference solution, signal mismatch, length mismatch, sweep key mismatch, and NaN versus finite each have a named test in the owning task.
- Proportion: the plan names interfaces and test assertions; bodies are limited to the comparison helper and the two base implementations where the decisions are not obvious from signatures.

## Execution handoff

Review the spec, tickets, and plan. If they capture the intended behaviour, implementation can proceed with the `executing-plans` skill. Recommended execution mode: inline, sequentially through the three tasks. The tasks share `src/mtools/testing.py` and build on each other's interfaces, so parallel agents would create avoidable merge and ordering risk; the total change is small enough for one implementer.
