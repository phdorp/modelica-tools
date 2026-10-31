# 03: Document and demonstrate reference comparison

**What to build:** The example package contains a separate reference Modelica
package under `tests` with the same output signals as the candidate model in
`src`, a dedicated registry for the reference model, and a comparison test that
checks both a single experiment and a sweep against it. The README explains how
to wire `reference_name` and `reference_registry` and use the comparison bases.

**Blocked by:** 01 and 02 (needs the public bases being demonstrated)

**Status:** completed

- [x] The example candidate package stays in `src`; the reference model is a
      separate Modelica package under `tests`.
- [x] The reference model has its own registry and experiment registrations in
      `examples/tests/reference_experiments.py`.
- [x] The example test suite compares a single experiment and a sweep against
      the reference model.
- [x] The example README documents the new fixtures, bases, and helper.
- [x] The main README feature list mentions reference-model comparison.
- [x] `uv run pytest tests` and the example suite pass.
