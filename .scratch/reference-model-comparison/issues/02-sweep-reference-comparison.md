# 02: Sweep reference comparison base

**What to build:** A user can write a sweep test class with `model_name`,
`reference_name`, `registry`, and `reference_registry` fixtures plus an
experiment name and `sweep_params`. The class runs the reference model over the
same parameter combinations as the candidate, exposes both mappings keyed by
combination, and `assert_matches_reference()` fails when combinations differ or
any matching table differs. The multi-sweep variant maps each experiment name to
both per-combination mappings. Each registry owns its own parameters, model
source, model configurations, libraries, and simulation settings.

**Blocked by:** 01 (uses the comparison helper and public naming)

**Status:** completed

- [x] `ExperimentSweepReference` and `ExperimentSweepsReference` exist and
      mirror the result shapes of `ExperimentSweep` and `ExperimentSweeps`.
- [x] The reference sweep uses the same combinations and attribution as the
      candidate sweep, resolving its base run config from `reference_registry`.
- [x] The reference sweep writes to its own temporary sweep directory.
- [x] The comparison helper fails when a combination is missing or extra and
      when matching combinations have different signals or values.
- [x] A real inner pytest session proves `reference_name` and
      `reference_registry` injection and autouse population for the sweep
      comparison base.
