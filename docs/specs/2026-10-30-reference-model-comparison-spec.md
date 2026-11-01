# Reference Model Comparison Spec

Status: implemented
Source: Conversation on 2026-10-30 (feature request for comparing two simulated models)

## Problem Statement

Today the experiment test bases simulate exactly one model, selected by the
model name carried in its run config. Verifying that a new or refactored Modelica model behaves
identically to an established reference model therefore means writing a second
test class, wiring a second simulation by hand, loading both solution tables,
and writing ad-hoc comparisons. The same work has to be repeated for every
experiment and every parameter sweep.

This is error-prone in three ways: the second simulation can be wired to the
wrong registry configuration, the comparison can forget output signals, and
sweep results can be paired by launch order instead of by parameter
combination. A model change can look tested when it is not.

## Solution

Add first-class comparison test bases that simulate each model from its own
experiment configuration and expose both result sets plus a built-in assertion
helper.

The model under test comes from the shared `registry` fixture; each simulated
model's name is read from the run config that composes it. Both models are
composed from that one registry: the candidate from the registry's default run
config and the reference from a `reference_run_config` fixture holding a run
config added to the same registry. The reference run config lives under
`tests/` and may point at a separate Modelica package with its own model name,
parameters, model source, model configurations, libraries, and simulation
settings. The registry registers the same experiment name for every
experiment-capable run config. Tests opt in to the comparison with
`assert_matches_reference()`.

Both single experiments and parameter sweeps are supported, including the
existing multi-experiment variants.

## User Stories

1. As a model developer, I want to define a test class that compares the model
   composed from the registry's default run config against the model composed
   from `reference_run_config`, so that I can verify a refactor against an
   established implementation without duplicating comparison code.
2. As a model developer, I want the reference model to be simulated from its own
   run config in the shared registry, so that it can define different
   parameters, model source, model configurations, libraries, and solver
   settings.
3. As a model developer, I want the candidate solution table exposed as
   `results` and the reference solution table exposed as `reference_results`,
   so that I can write custom domain assertions when the built-in comparison is
   not enough.
4. As a model developer, I want `assert_matches_reference()` to require both
   models to provide the same output signals, so that a missing or renamed
   signal is a test failure rather than a silently skipped column.
5. As a model developer, I want `assert_matches_reference()` to compare every
   signal value within a configurable tolerance, so that numerical differences
   between implementations are caught.
6. As a model developer, I want to override the comparison tolerance with the
   existing `eps` class variable, so that I can allow for known numerical
   differences without changing the helper.
7. As a model developer, I want a sweep comparison base that runs both models
   for every parameter combination, so that equivalence is proven across the
   whole sweep rather than a single point.
8. As a model developer, I want swept results keyed by parameter combination
   for both models, so that mismatched combinations fail instead of comparing
   unrelated runs.
9. As a model developer, I want comparison failures to name the experiment,
   model pair, signal, and sweep combination, so that I can find the offending
   case without inspecting every table.
10. As a model developer, I want the multi-experiment variants to map each
    experiment name to both candidate and reference results, so that the new
    bases mirror `Experiments` and `ExperimentSweeps`.
11. As a model developer, I want a reference model in a separate Modelica
    package from the candidate, so that I can keep production models in `src`
    and test-only reference models in `tests`.
12. As a model developer, I want a reference model that is absent from the
    reference run config's configured source to fail with the existing simulation
    error, so that I know the reference name and source do not match.
13. As a model developer, I want a missing `reference_run_config` fixture to
    fail at test setup with a normal pytest fixture error, so that the wiring
    mistake is obvious.
14. As a model developer, I want the comparison to run only when I call the
    helper, so that I can first assert physical properties and then compare
    against the reference.
15. As a maintainer, I want an example candidate package in `src` and a separate
    reference package in `tests`, so that users have a working cross-package
    template.

## Implementation Decisions

### Public test bases

Add comparison variants that mirror the existing naming and result shapes:

- `ExperimentReference`: one experiment name, `results` and
  `reference_results` are solution tables.
- `ExperimentsReference`: a list of experiment names, both result attributes
  map each name to its solution table.
- `ExperimentSweepReference`: one experiment name, both result attributes map
  each cartesian-product parameter tuple to its solution table.
- `ExperimentSweepsReference`: a list of experiment names, both result
  attributes map each name to such a per-combination mapping.

The new bases reuse the existing experiment/sweep machinery for candidate
simulation and the existing name handling, indentation conventions, and typed
aliases. Each comparison base overrides the inherited autouse class-scoped
fixture so both candidate and reference results are populated before tests run.

### Reference selection

The reference model is named by the `model_name` of a `reference_run_config`
added to the shared `registry`; that run config also carries the reference
model's parameters, source file or package, model configurations, libraries,
and simulation settings, and it lives under `tests/`. A run config holds
exactly one model name, so the reference name is not a separately supplied
fixture.

The registry binds every experiment to every run config whose defaults include
the `experiment` group. `register_experiment` (and its `register_experiments`
batch wrapper) records the base run config it was registered with as the
experiment's default and automatically rebinds the experiment to any
experiment-capable run config registered now or later, so adding the reference
run config is enough to make every experiment available for the reference side.

The comparison bases compose the candidate experiment from the registry's default
run config via `compose_experiment(name)`, and the reference experiment with the
same name via `compose_experiment(name, run_config=reference_run_config)`. No
extra Hydra overrides are added. The two run configs are independent, so the
reference may use different parameters, group selections, or a separate Modelica
package.

`compose_experiment(name, run_config=None, overrides=None)` and
`get_experiment_run_config(name, run_config=None)` accept the optional run config;
when omitted they use the run config the experiment was registered with.

The existing simulation API maps results under each run's configured model name.
The comparison bases therefore select the candidate table by the default run
config's `model_name` and the reference table by `reference_run_config`'s
`model_name`.

### Sweep reference runs

A reference sweep uses the same sweep planner, the same parameter combinations,
and the same result attribution as the candidate sweep. It resolves its base run
config from the same `registry` with `run_config=reference_run_config` instead of
the registry default, and writes to its own temporary sweep directory. Results
are attributed from each job's composed
config, not from launch order, exactly as candidate sweeps already are.

### Comparison helper

All four bases expose `assert_matches_reference()`. It recursively compares the
candidate and reference result structures:

- For single-experiment results, it compares two solution tables.
- For multi-experiment and sweep results, it first requires the same key sets,
  then compares each matching table.
- Two solution tables must have equal length and the same set of output signal
  columns.
- Every signal column is compared positionally with
  `numpy.testing.assert_allclose` using `rtol=0` and `atol=self.eps`.
- `eps` defaults to `numpy.finfo(float).eps`, matching the existing experiment
  bases, and may be overridden per test class.
- Failures are assertions with context naming the test class, experiment name,
  and sweep combination where applicable. Signal-set failures list the missing
  and unexpected signals.

The helper does not run automatically. A test class may assert custom
behaviour first and call the comparison afterwards.

### Fixtures

A run config holds exactly one `model_name`, so the bases read the simulated
model's name from the composed run config instead of a fixture. The single-model
bases require only the existing `registry` fixture; the comparison bases require
`registry` and `reference_run_config`. Sweep bases additionally use the built-in
`tmp_path_factory`, as existing sweep bases do.

### Documentation

The `mtools.testing` module documentation must list the new fixtures and
aliases alongside the existing ones. The example package gains a separate
reference Modelica package under `tests` and a comparison test so the feature is
demonstrated end to end.

## Testing Decisions

Good tests exercise the public test bases and the public comparison helper, not
the private sweep planner or individual simulation steps. They fake
`sim_tools.simulate` so the library suite does not need OpenModelica for the
comparison logic.

Seams:

- `tests/session_tools/test_testing.py` directly drives
  `fetch_reference_experiment` and `fetch_reference_sweep`, then calls
  `assert_matches_reference()`. This is the same seam as the existing
  `fetch_experiment` / `fetch_sweep` tests.
- `tests/session_tools/test_testing_fixtures.py` runs a real inner pytest
  session with the `pytester` fixture to prove that `reference_run_config` is
  injected and the comparison bases' autouse fixtures actually populate both
  result attributes.
- `examples/tests/test_reference_comparison.py` runs the real candidate package
  from `src` and a separate reference package from `tests` through OpenModelica,
  both from the shared registry - the candidate from its default run config and
  the reference from `reference_run_config` - proving the single-registry
  workflow end to end.

Covered failure modes:

- value mismatch between models
- missing or extra output signal
- different solution lengths
- missing or extra sweep combination
- reference model with no solution
- NaN versus finite signal

Prior art: `tests/session_tools/test_testing.py` and
`tests/session_tools/test_testing_fixtures.py` already test experiment and
sweep bases through direct class methods and `pytester`.

## Out of Scope

- Comparing a subset of signals. Both models must expose the same signals.
- Verifying that the candidate and reference run configs define physically
  equivalent parameter sets. Each run config owns its own parameters; the
  comparison checks output signals and values.
- Stored or golden reference results. The reference is simulated live.
- Sweeping candidate and reference parameters independently. The same
  `sweep_params` mapping is applied to both run configs.
- Generating diff plots or comparison reports.

## Further Notes

The candidate and reference run configs share one registry, so the same config
and experiment names are composed from it in turn. The comparison bases activate
that registry's Hydra store immediately before composing or launching each run.
`HydraZenRegistry.add_to_hydra_store(overwrite_ok=True)` re-enqueues all
registered entries, so repeated activation does not collide in Hydra's global
store.

The reference model is built from the source file or package configured in
`reference_run_config`. If the reference model name is missing from that source,
the existing simulation error path reports that no solution matches the
requested model.
