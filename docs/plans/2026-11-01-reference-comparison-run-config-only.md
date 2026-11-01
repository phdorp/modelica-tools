# Run-Config-Sourced Reference Comparison Implementation Plan

**Goal:** Make the experiment test bases read each simulated model's name from its run config, so a
single-model test needs only the `registry` fixture and a comparison test needs only `registry` and
`reference_run_config` — no `model_name` or `reference_name` fixtures.

**Architecture:** A run config carries exactly one `model_name`, and `sim_tools.simulate` already
keys its result mapping by the composed config's `model_name`. The bases therefore compose the
experiment, read `config.model_name` for the result key, and drop the name fixtures. Sweep results
read the name from each job's composed config (`SweepResult.config`), exactly as sweep values are
already read from it. Comparison bases compose the candidate from the registry default and the
reference with `run_config=reference_run_config`.

**Tech Stack:** Python 3.11, pytest, hydra-zen / OmegaConf, OpenModelica 1.27.2 (examples suite).
`uv` is unavailable: use `.venv/bin/python`.

**Spec:** `docs/specs/2026-10-30-reference-model-comparison-spec.md`

## Global Constraints

- One model per run config: a run config's `model_name` is the single source of truth for both the
  model that is built and the key its results return under.
- Single-model bases (`Experiment`, `Experiments`, `ExperimentSweep`, `ExperimentSweeps`) require
  only the `registry` fixture.
- Comparison bases (`ExperimentReference`, `ExperimentsReference`, `ExperimentSweepReference`,
  `ExperimentSweepsReference`) require only `registry` and `reference_run_config`, plus the builtin
  `tmp_path_factory` for the sweep variants.
- No `model_name` or `reference_name` fixture remains anywhere in `src`, `tests`, or `examples`.
- The public alias names and result shapes do not change.
- `compose_experiment(name)` uses the experiment's registered default run config; the comparison
  reference uses `compose_experiment(name, run_config=reference_run_config)`.
- Test commands: `.venv/bin/python -m pytest tests` from the repo root; from `examples/`,
  `PYTHONPATH=src ../.venv/bin/python -m pytest tests`.
- Commit messages follow the conventional-commit style.

## Review Focus

Failure modes the spec implies but no current test exercises; each gets a test in Task 1.

1. A sweep job whose composed config has no `model_name`: `_SweepPlan.attribute` raises
   `ValueError` naming the missing path instead of returning a mis-keyed table.
2. The candidate and the reference composed from the same run config: both tables match and
   `assert_matches_reference()` passes instead of picking unrelated models.
3. A multi-experiment comparison: each name's table is keyed by that name's composed
   `model_name`, so a name resolving to a different run config is attributed correctly.

## File Structure

- `src/mtools/testing.py` — experiment/reference base classes and aliases; change the `fetch_*`
  signatures and their autouse fixtures to drop `model_name`/`reference_name` and read
  `config.model_name`.
- `src/mtools/internal/testing.py` — `_SweepPlan.attribute` reads each job's `model_name` from its
  composed config.
- `tests/session_tools/test_testing.py` — direct-driver tests for the bases, the sweep planner, and
  the three Review Focus failure modes.
- `tests/session_tools/test_testing_fixtures.py` — `pytester` wiring proof for the module-level
  fixtures the bases now require.
- `examples/tests/test_kinematic_vehicle.py` — single-model example; drop the `model_name` fixture.
- `examples/tests/test_reference_comparison.py` — comparison example; drop `model_name` and
  `reference_name`.
- `examples/README.md` — the fixture list and the comparison test snippet.
- `docs/specs/2026-10-30-reference-model-comparison-spec.md` — the binding spec's fixture and
  reference-selection decisions.
- `docs/plans/2026-10-30-reference-model-comparison.md` — a superseding note pointing at this plan.

## Tasks

### Task 1: Derive model names in the bases and the sweep planner

**Files:**
- Modify: `src/mtools/internal/testing.py` (`_SweepPlan.attribute`, around line 382)
- Modify: `src/mtools/testing.py` (module docstring, `ExperimentBase`, `ExperimentT`,
  `ExperimentReferenceT`, `ExperimentSweepT`, `ExperimentSweepReferenceT`)
- Test: `tests/session_tools/test_testing.py`
- Test: `tests/session_tools/test_testing_fixtures.py`

**Interfaces:**
- Consumes: `registry.compose_experiment(name, run_config=None, overrides=None) -> DictConfig`
  (the returned config exposes `model_name`); `registry.get_experiment_run_config(name,
  run_config=None) -> run config`; `sim_tools.simulate(config) -> dict[str, DataFrame]`;
  `SweepResult.config` / `SweepResult.solutions`.
- Produces (later tasks and the example rely on these exact signatures):
  - `ExperimentT.fetch_experiment(registry: HydraZenRegistry) -> None`
  - `ExperimentReferenceT.fetch_reference_experiment(registry: HydraZenRegistry, reference_run_config: Any) -> None`
  - `ExperimentSweepT.run_single_sweep(name: str, registry: HydraZenRegistry, tmp_path_factory: Any, run_config: Any = None) -> dict[tuple[Hashable, ...], pd.DataFrame]`
  - `ExperimentSweepT.fetch_sweep(registry: HydraZenRegistry, tmp_path_factory: Any) -> None`
  - `ExperimentSweepReferenceT.run_single_reference_sweep(name: str, registry: HydraZenRegistry, reference_run_config: Any, tmp_path_factory: Any) -> dict[tuple[Hashable, ...], pd.DataFrame]`
  - `ExperimentSweepReferenceT.fetch_reference_sweep(registry: HydraZenRegistry, reference_run_config: Any, tmp_path_factory: Any) -> None`
  - `_SweepPlan.attribute(sweep_results: list) -> dict[tuple[Hashable, ...], pd.DataFrame]`

- [ ] **Step 1: Update the test doubles and the direct-driver calls to the new signatures**

In `tests/session_tools/test_testing.py`:

- `FakeRegistry.compose_experiment` returns an attribute-accessible config. Replace its return with
  `OmegaConf.create({"composed_experiment": name, "model_name": getattr(run_config, "model_name", self.model_name)})`.
- Give every `FakeJob` config a `"model_name"` entry (the model its table is keyed by), e.g.
  `{"model_name": "my.Model", "session": {"parameters": {"phi": phi}}}`; the reference-sweep test's
  jobs use the `model_name` read from the launched base config.
- Drop the name argument from the direct calls: `T.fetch_experiment(fake_registry)`,
  `T.fetch_sweep(fake_registry, tmp_path_factory)`,
  `T.fetch_reference_experiment(registry, reference_run_config)`,
  `T.fetch_reference_sweep(registry, reference_run_config, tmp_path_factory)`.

In `tests/session_tools/test_testing_fixtures.py`:

- Delete the `model_name` and `reference_name` fixtures from `INNER_MODULE`; keep `registry` and
  `reference_run_config`.
- Make the inner `FakeRegistry.compose_experiment` return
  `OmegaConf.create({"composed_experiment": name, "model_name": getattr(run_config, "model_name", self.model_name)})`
  (`INNER_MODULE` imports `from omegaconf import OmegaConf`).
- Add `"model_name"` to the `_FakeJob` config dict returned by `_fake_simulate`.
- Update the module docstring and the test name to describe `registry` / `reference_run_config`
  wiring.

Add the three Review Focus tests to `tests/session_tools/test_testing.py`:

```python
def test_sweep_job_config_missing_model_name_raises(monkeypatch, tmp_path_factory):
    # a FakeJob config without "model_name"
    ...
    # expect ValueError mentioning "model_name"

def test_reference_comparison_accepts_same_run_config_for_both_models(monkeypatch):
    # registry.compose_experiment(name) and compose_experiment(name, run_config=same) return the
    # same model_name; T().assert_matches_reference() passes.

def test_multi_experiment_reference_keys_each_name_by_its_own_model_name(monkeypatch):
    # compose_experiment returns a different model_name per name; reference_results is keyed by it.
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/session_tools/test_testing.py tests/session_tools/test_testing_fixtures.py -q`
Expected: FAIL — `fetch_experiment() takes 2 positional arguments but 3 were given`,
`fetch_sweep() takes 3 positional arguments but 4 were given`, and the missing-`model_name` test
fails because `attribute` still takes the name argument.

- [ ] **Step 3: Implement the signature and derivation changes**

`src/mtools/internal/testing.py` — `_SweepPlan.attribute(self, sweep_results: list) -> dict`: drop
the `model_name` parameter and use `_select_job_value(job.config, "model_name")` for the table key
on each job. Update its docstring.

`src/mtools/testing.py` — for each class, drop the name parameter(s) and read the name from the
composed config:

- `ExperimentT.fetch_experiment(cls, registry)`: for each name in `cls.name`, compose
  `registry.compose_experiment(name)` and store `sim_tools.simulate(config)[config.model_name]`.
- `ExperimentReferenceT.fetch_reference_experiment(cls, registry, reference_run_config)`: call
  `super().fetch_experiment(registry)`, then for each name store
  `sim_tools.simulate(registry.compose_experiment(name, run_config=reference_run_config))[config.model_name]`.
- `ExperimentSweepT.run_single_sweep(cls, name, registry, tmp_path_factory, run_config=None)` and
  `fetch_sweep(cls, registry, tmp_path_factory)`: drop the model name; pass it through to
  `plan.attribute(sweep_results)`.
- `ExperimentSweepReferenceT.run_single_reference_sweep(cls, name, registry, reference_run_config,
  tmp_path_factory)` and `fetch_reference_sweep(cls, registry, reference_run_config,
  tmp_path_factory)`: drop the name parameters.
- Update every autouse class-scoped fixture to request only the fixtures the base now needs, and
  rewrite the module docstring's "Required fixtures" list and the class docstrings so no
  `model_name`/`reference_name` requirement remains.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/session_tools/test_testing.py tests/session_tools/test_testing_fixtures.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole library suite**

Run: `.venv/bin/python -m pytest tests -q`
Expected: PASS (no regressions elsewhere).

- [ ] **Step 6: Commit**

```bash
git add src/mtools/testing.py src/mtools/internal/testing.py tests/session_tools/test_testing.py tests/session_tools/test_testing_fixtures.py
git commit -m "refactor: derive comparison model names from run configs"
```

### Task 2: Drop the redundant fixtures from the example suite

**Files:**
- Modify: `examples/tests/test_kinematic_vehicle.py`
- Modify: `examples/tests/test_reference_comparison.py`
- Modify: `examples/README.md`
- Test: the example suite itself (`examples/tests`)

**Interfaces:**
- Consumes: Task 1's `Experiment`/`ExperimentSweep` (need `registry` only) and
  `ExperimentReference`/`ExperimentSweepReference` (need `registry` + `reference_run_config`).
- Produces: nothing later tasks depend on.

This task removes now-redundant wiring; there is no new behaviour to drive red. The evidence is the
example suite staying green and the fixtures being gone.

- [ ] **Step 1: Remove the fixtures**

`examples/tests/test_kinematic_vehicle.py`: delete the `model_name` fixture and the now-unused
`MODEL_NAME` import; keep the `registry` fixture.
`examples/tests/test_reference_comparison.py`: delete the `model_name` and `reference_name`
fixtures and the now-unused `MODEL_NAME`/`REFERENCE_MODEL_NAME` imports; keep `registry` and
`reference_run_config`.

- [ ] **Step 2: Update `examples/README.md`**

Rewrite the "four fixtures" sentence and the comparison snippet so the module provides only
`registry` and `reference_run_config`, and drop the two name fixtures from the snippet. Keep the
`run_reference` import and the `ExperimentReference`/`ExperimentSweepReference` classes.

- [ ] **Step 3: Run the example suite**

Run: `cd examples && PYTHONPATH=src ../.venv/bin/python -m pytest tests -q`
Expected: PASS (16 passed).

- [ ] **Step 4: Prove no name fixtures remain**

Run: `grep -rn "def model_name\|def reference_name" tests examples tests/session_tools 2>/dev/null; grep -rn "reference_name" src tests examples`
Expected: no matches in `src`, `tests`, or `examples`.

- [ ] **Step 5: Commit**

```bash
git add examples/tests/test_kinematic_vehicle.py examples/tests/test_reference_comparison.py examples/README.md
git commit -m "docs: drop redundant model-name fixtures from the example suite"
```

### Task 3: Revise the spec and supersede the old plan

**Files:**
- Modify: `docs/specs/2026-10-30-reference-model-comparison-spec.md`
- Modify: `docs/plans/2026-10-30-reference-model-comparison.md` (append a superseding note at the
  top)

**Interfaces:**
- Consumes: the final implemented behaviour from Tasks 1-2.
- Produces: the binding spec matching the code.

- [ ] **Step 1: Update the spec**

In `docs/specs/2026-10-30-reference-model-comparison-spec.md`:

- Problem Statement and Solution: replace the two name fixtures with the run config as the source
  of the model name.
- User Stories 1 and 13: refer to run configs, not `model_name`/`reference_name` fixtures.
- Reference selection: state that `reference_name` is gone and the reference model name comes from
  `reference_run_config`; the candidate name comes from the experiment's registered run config.
- Fixtures: the comparison bases require `registry` and `reference_run_config` only; single-model
  bases require `registry` only.
- Testing Decisions: drop the `reference_name` injection claim; keep the `reference_run_config`
  injection claim.

- [ ] **Step 2: Add the superseding note**

At the top of `docs/plans/2026-10-30-reference-model-comparison.md`, add one line noting that the
`model_name`/`reference_name` fixture design in that plan was superseded by
`docs/plans/2026-11-01-reference-comparison-run-config-only.md`.

- [ ] **Step 3: Verify the spec no longer requires the name fixtures**

Run: `grep -n "model_name fixture\|reference_name fixture\|reference_name and\|the new .reference_name." docs/specs/2026-10-30-reference-model-comparison-spec.md`
Expected: no matches (the spec still legitimately mentions `reference_run_config`).

- [ ] **Step 4: Re-run both suites**

Run: `.venv/bin/python -m pytest tests -q` and then
`cd examples && PYTHONPATH=src ../.venv/bin/python -m pytest tests -q`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/specs/2026-10-30-reference-model-comparison-spec.md docs/plans/2026-10-30-reference-model-comparison.md
git commit -m "docs: revise the reference comparison spec to run-config-sourced names"
```

## Self-review

1. **Spec coverage:** the spec's Solution, Reference selection, Fixtures, and Testing Decisions
   sections are covered by Task 1 (Implementation Decisions) and Task 3 (the written spec); the
   example requirement in the spec's Documentation decision is covered by Task 2.
2. **Step scan:** each step names one edit or one command with an expected result.
3. **Type consistency:** the Produces signatures in Task 1 match the calls Task 2's base classes
   make internally; `attribute` takes one argument everywhere.
4. **Review Focus:** the three failure modes each have a named test in Task 1.
5. **Proportion:** three short tasks over nine files; no task restates code the signature plus its
   test already fixes.

## Execution handoff

Execute inline (mode 1): all three tasks touch one shared interface (`mtools.testing`), so a
preflight scan marks every task pair as sharing that interface and parallel work would conflict.
One fresh whole-branch review at the end.