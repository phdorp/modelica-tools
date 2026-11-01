# 01: Single-experiment reference comparison base

**What to build:** A user can write a test class with `model_name`,
`reference_name`, `registry`, and `reference_registry` fixtures plus an
experiment name. Before the test methods run, the class simulates the experiment
for both models, exposes the candidate table as `results` and the reference
table as `reference_results`, and offers `assert_matches_reference()` to prove
the two models expose the same output signals and matching values within `eps`.
The multi-experiment variant maps each name to both tables. Each registry owns
its own parameters, model source, model configurations, libraries, and
simulation settings.

**Blocked by:** None (can start immediately)

**Status:** completed

- [x] `ExperimentReference` and `ExperimentsReference` exist and mirror the
      result shapes of `Experiment` and `Experiments`.
- [x] The candidate run composes the experiment from `registry`; the reference
      run composes the same experiment name from `reference_registry`.
- [x] The comparison helper passes for matching tables and fails for a value
      mismatch, a missing or extra signal, and a different row count.
- [x] Failure messages name the class, experiment, and offending signal.
- [x] `eps` can be overridden per test class.
- [x] A real inner pytest session proves `reference_name` and
      `reference_registry` fixture injection and autouse population of both
      result attributes.
