# Task #67 report: docs and plotting tool

Branch feat/omc-backend-67 (from 69dd21c). Status: DONE.

## Commits
- feat: plot Boolean result columns as 0/1 (src/mtools/internal/plot_tools.py `_load_results`; tests in tests/plot_tools/test_result_explorer.py)
- test: satisfy mypy in the Boolean plot test
- docs: describe the OMC backend, config paths and breaking changes (README.md, examples/README.md, AGENTS.md, both specs)

## TDD
RED `uv run pytest tests/plot_tools`: `assert 'b' in 'iuf'` (bool dtype after load). GREEN: 15 passed.

## Docs covered
README: new intro, build/settings paths table, parameters (R4 `m[1,2]`, R20 `"Mode.high"`, R5 solver default), Targets (three spec differences plus events 1e-6 late, no failure on division by zero or singular systems, 1-row partial result on init failure, `--simCodeTarget` Python-only), env vars, cache limits, errors tree and logger, breaking changes. examples/README: `settings.*` paths, Cpp target text, `extra_sources`. AGENTS.md pydelica line. Spec 2026-11-08: R4 note inline. Error-messages spec: status note.

## Verification
plot_tools + test_hydra_registry 43 passed; mypy src tests: 0 errors; isort clean. Full suite not re-run (only plot_tools.py changed in code).

## Rulings / concerns
- Boolean conversion is in the CSV loader (`_load_results`), so every figure sees 0/1. Cost if wrong: none.
- README does not mention the open finding that Cpp has extra parameter-bound columns and different repeated rows (violates story 38); document or fix after the backend fix wave.
- The "typed columns" breaking-change line assumes the old columns were float; not verified against pydelica.
