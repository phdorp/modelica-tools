# AGENTS.md

## Setup

Installation and environment setup instructions are in the README.md section **"Development container"** (`.devcontainer/`).
The devcontainer installs OpenModelica, Python 3.11, uv, and all dependencies automatically.

Prefer working inside the devcontainer (`devcontainer up` / `devcontainer exec`).
Do not install any dependencie unless the devcontainer is unavailable.

## Repository layout

- `src/mtools/` — main package: `session_config.py`, `sim_tools.py`, `hydra_registry.py`, and internal helpers in `internal/`.
- `tests/session_tools/` — pytest suite (unit and integration tests).
- `examples/` — separate uv workspace member with its own `pyproject.toml`, package, and tests.

## Development

- Run the main test suite with: `uv run pytest tests`
- Tests compile real Modelica models via `pydelica`, so OpenModelica must be installed and on `PATH`.

### Full test suite

The main suite does not cover the `examples` workspace.
Run everything that CI runs:

```bash
uv run pytest tests
uv pip install -e 'examples[test]'
# then, from the examples/ directory:
uv run pytest tests
```

## Code style / quality

```bash
uv run mypy src tests
uv run isort --check-only src tests examples
```

## Conventions

- Uses a `src/` layout; all package config lives in `pyproject.toml` (no `setup.cfg`).
- Follow existing patterns in `src/mtools/` when adding or modifying code.

## Commits and pull requests

- Follow conventional-commit style: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, ...
- Use the `gh` CLI for GitHub tasks (`gh pr create`, `gh pr edit`, `gh pr list`, etc.).
- Pull requests must follow the template in `.github/pull_request_template.md` (Changes, Relevant links, Reasoning, Explanation, Additional notes, and the Checklist).
- Keep the PR description as brief as possible, including only the information the reviewer needs to quickly grasp the changes.
- Squash-merge pull requests into `main`.
- The squash-merge commit message must be a conventional-commit message that describes the change for both developers and users - `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, followed by a concise summary.
