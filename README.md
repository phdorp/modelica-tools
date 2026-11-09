# modelica-tools

A Python toolkit for configuring and running [Modelica](https://modelica.org/) simulations with [OpenModelica](https://openmodelica.org/) from Python.

`modelica-tools` drives the `omc` compiler directly: it builds a model once, caches the build by content, runs it with per-run parameters and settings, and returns typed [pandas](https://pandas.pydata.org/) DataFrames. Typed configuration dataclasses and a registry system powered by [Hydra](https://hydra.cc) / [hydra-zen](https://github.com/mit-ll/hydra-zen) let you define a simulation setup once in Python, then override, compose and sweep it from the command line.

## Features

- **Python-native Modelica configuration** — Define what to build (`build`) and how to run it (`settings`) as typed Python dataclasses.
- **Build cache** — Builds are cached by content, so a parameter sweep compiles once and a repeated sweep compiles nothing.
- **Hierarchical configuration** with [Hydra](https://hydra.cc) / [hydra-zen](https://github.com/mit-ll/hydra-zen) — Compose, override, and reuse configs across runs.
- **Parameter sweeps** — Launch multirun sweeps over any simulation parameter from the command line.
- **Reference-model comparison** — Test a model against a reference implementation from a run config in a shared Hydra registry, comparing output signals and values.
- **Configuration groups and experiments** — Register reusable config groups (e.g., initial states) and named experiment overrides.
- **Result visualization** — Interactive [Dash](https://dash.plotly.com/) web app for browsing simulation results (CSV) with a grid of time-series plots.
- **Unit-testable** — Simulations are driven by config objects that can be instantiated and verified in isolation.

## Installation

### Prerequisites

Install [OpenModelica](https://openmodelica.org/) (`omc` and a C compiler with `make`):

- **Debian / Ubuntu**:
  ```bash
  sudo apt-get install -y omc omlibrary
  ```
- **macOS** (Homebrew):
  ```bash
  brew install openmodelica
  ```
- **Windows**: Download and run the installer from the [OpenModelica download page](https://openmodelica.org/download/download-windows).

See the [OpenModelica installation guide](https://openmodelica.org/download) for other platforms.

### Python version

Requires **Python >= 3.11**.

### Install the package

The `modelica-tools` package is not yet published on PyPI. Install directly from GitHub — first initialize a project with `uv init` (if you haven't already):

```bash
uv init my_simulation
cd my_simulation
uv add git+https://github.com/phdorp/modelica-tools.git
```

For development, clone the repository and install with dev dependencies:

```bash
git clone https://github.com/phdorp/modelica-tools.git
cd modelica-tools
uv sync --all-extras --dev
```

### Development container

A [devcontainer](.devcontainer/) is provided for contributors — it installs OpenModelica, Python 3.11, and all dependencies automatically, so no manual setup is required.

**Prerequisites**

- [Docker](https://docs.docker.com/get-docker/)
- A devcontainer-compatible editor or CLI, e.g. [VS Code](https://code.visualstudio.com/docs/devcontainers/containers) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers), or the `devcontainer` CLI from the [devcontainer-cli](https://github.com/devcontainers/cli) project.

**Setup**

1. Clone the repository:
   ```bash
   git clone https://github.com/phdorp/modelica-tools.git
   cd modelica-tools
   ```
2. Open the folder in a devcontainer environment:
   - **VS Code**: run the **Dev Containers: Reopen in Container** command (or **Rebuild and Reopen in Container** after changing the devcontainer config).
   - **CLI**: `devcontainer build --workspace-folder . && devcontainer up --workspace-folder .`
3. Launch a bash shell inside the running container:
   ```bash
   devcontainer exec --workspace-folder . bash
   ```

The container builds from [`.devcontainer/Dockerfile`](.devcontainer/Dockerfile), which installs `omc` and `omlibrary` from the OpenModelica APT repository via [`.devcontainer/install_dependencies.sh`](.devcontainer/install_dependencies.sh). On first start, the [postCreateCommand](.devcontainer/devcontainer.json) installs `uv` via `pipx`, creates a virtual environment, and runs `uv pip install -e '.[dev]'` to install the package with all development dependencies.

The virtual environment is created at `/home/vscode/.venv` inside the container, and `.vscode/settings.json` sets it as the default Python interpreter.

The workspace is mounted into the container, so edits on your host are reflected immediately, and any Python version manager or OpenModelica installation on the host is not needed.

## Testing

```bash
uv run pytest tests
```

Tests require OpenModelica installed (see prerequisites) and compile and simulate real Modelica models with `omc`.

## Usage

### Create a Python project

Start by creating a Python project with [uv](https://docs.astral.sh/uv/):

```bash
uv init my_simulation
cd my_simulation
```

### Add the package dependency

```bash
uv add git+https://github.com/phdorp/modelica-tools.git
```

### Define a simulation configuration

Create your Python package with the following structure:

```
my_simulation/
├── src/
│   └── my_simulation/
│       ├── __init__.py
│       ├── __main__.py
│       ├── config.py
│       └── my_model.mo
├── pyproject.toml
└── .python-version
```

Place your Modelica model in `src/my_simulation/my_model.mo`.

Define your parameters and register them with a `HydraZenRegistry` in `config.py`.
See [`examples/src/kinematic_vehicle/kinematic_vehicle.py`](examples/src/kinematic_vehicle/kinematic_vehicle.py) for a complete example.

In `__main__.py`, import the config module and call `registry.add_to_hydra_store()` before running the simulation:

```python
import hydra
from hydra.core.hydra_config import HydraConfig
import my_simulation.config  # noqa: F401 - registers Hydra configs
import mtools.session_config as session_config
import mtools.sim_tools as sim_tools


@hydra.main(config_name="default", version_base=None, config_path=None)
def main(config: session_config.SimulationRun):
    sim_tools.save_solutions(sim_tools.simulate(config), HydraConfig.get().runtime.output_dir)


if __name__ == "__main__":
    my_simulation.config.registry.add_to_hydra_store()
    main()
```

See [`examples/src/kinematic_vehicle/__main__.py`](examples/src/kinematic_vehicle/__main__.py) for the corresponding example.

The `simulate` function validates the run config, builds the model (or reuses a cached build), runs it with the given parameters and settings, and returns one DataFrame per model, keyed by `build.model_name`. `save_solutions` writes them as CSV.

### Run a simulation

Run the simulation with the default configuration:

```bash
uv run python -m my_simulation
```

Override individual parameters or select registered config groups from the command line:

```bash
uv run python -m my_simulation settings.parameters.some_value=5.0
uv run python -m my_simulation settings.stop_time=20.0
uv run python -m my_simulation build.target=Cpp
```

`build.omc_flags` maps OMC flags to their values, and `null` gives a flag without a value. Set it from the command line with a leading `+`; without it, Hydra rejects the override with `Key ... is not in struct`. The given flags are added to the configured ones:

```bash
uv run python -m my_simulation '+build.omc_flags={-d:initialization,--maxSizeLinearTearing:300}'
uv run python -m my_simulation '+build.omc_flags={--showErrorMessages:null}'
```

A run config has two parts: `build` says what to build and `settings` says how to run it.

| Path | Content |
|---|---|
| `build.model_path`, `build.model_name` | Source file and fully qualified model class; results are keyed by the name. |
| `build.target` | `C` (default) or `Cpp`, see [Targets](#targets). |
| `build.extra_sources`, `build.libraries`, `build.omc_flags` | Extra packages, libraries (`name`, `version`, `directory`) and OMC flags. |
| `settings.parameters.*` | Parameter values; the structure follows the parameter dataclass in `config.py`. |
| `settings.start_time`, `stop_time`, `interval`, `tolerance`, `solver` | Unset values come from the model's `experiment` annotation (OMC's defaults, 0 to 1 s, if there is none). The default solver comes from the `__OpenModelica_simulationFlags(s=...)` annotation, else `dassl`. |
| `settings.variable_filter`, `emit_protected`, `timeout`, `abort_on_chattering` | Result columns (OMC regular expression), protected variables, time limit in seconds, and chattering abort (C only). |

Parameters:

- Nested dataclasses become dotted names and arrays become 1-based indexed names, so `y=[1, 2]` sets `y[1]` and `y[2]`, and a 2-D array sets `m[1,2]` (no space after the comma).
- A parameter OMC fixes at build time (for example an array size or an `Evaluate=true` parameter) makes mtools build and cache a variant with that value. An enumeration value must then be a qualified literal, `"Mode.high"`.
- Unknown and protected parameter names raise `ConfigError`.

Refer to the [`kinematic_vehicle` examples](examples/) for a complete working setup.

### Targets

`build.target` selects the OpenModelica simulation runtime. `C` is the default. `Cpp` is a deliberate alternative for installations without the C runtime libraries; mtools never picks it automatically. Config, result columns and rows, column types, errors, partial results and caching are the same on both targets: mtools drops the parameter aliases Cpp writes as columns and writes the repeated rows at the start, at events and at the stop time as C does. These differences remain on Cpp:

- Only the solvers `dassl`, `cvode` and `ida` run; any other solver, also from the model's annotation, raises `ConfigError`.
- `dassl` ignores `settings.interval` and logs a WARNING instead of resampling.
- When `settings.interval` does not divide the simulated time span, Cpp writes the grid at multiples of the interval plus the stop time, while C spreads a rounded number of intervals evenly (0 to 1 s with interval 0.3: Cpp writes 0, 0.3, 0.6, 0.9, 1; C writes 0, 0.333, 0.667, 1).
- An event at the start time that changes no discrete variable in the result gives one row at the start time instead of C's three.
- `abort_on_chattering` has no effect.
- Events are reported about 1e-6 late.
- Division by zero and singular linear systems do not fail the run.
- A failed initialization gives a one-row partial result instead of `None`.

`--simCodeTarget` is rejected in `build.omc_flags`; use `build.target`.

### Environment variables

| Variable | Effect |
|---|---|
| `MTOOLS_WORK_DIR` | Work directory holding `builds/` (the cache) and `runs/`. Defaults to `<system temp dir>/mtools-<user>/`; a relative path resolves against the directory the process starts in. |
| `MTOOLS_NO_CACHE=1` | Build into a throwaway directory and skip the cache. |
| `MTOOLS_KEEP_RUNS=1` | Keep run directories and uncached builds, log their paths at INFO, and add `Run directory: <path>` to failure diagnostics. |

Run directories and uncached builds are otherwise deleted when `simulate` ends. Hydra's output directory is never touched except by `save_solutions`.

### Build cache

The cache key is a content hash of the source packages (including `Resources/`), library specs, target, `omc_flags`, build-time parameter values, and the OMC and C compiler versions. Editing a file in the package, in an `extra_sources` package or in a `directory` library rebuilds. There is no automatic eviction; delete `<work dir>/builds/` to clear it. C headers included by absolute path from outside any package are not part of the key, so changing one does not trigger a rebuild; use `MTOOLS_NO_CACHE=1` for those models.

### Errors and logging

All failures raise public exceptions from `mtools.errors`, with a header naming the model and stage, followed by OMC's filtered diagnostics:

```
MtoolsError
├── ConfigError (also ValueError)
├── BuildError
│   ├── TranslationError
│   └── CompileError
└── SimulationError                  .partial_result: DataFrame | None
    └── SimulationTimeout
```

A failed or timed-out run never returns data as a result; what was written before the failure is in `SimulationError.partial_result`. Every exception has `.model_name` and `.diagnostics`.

mtools logs to the `mtools` logger (builds, cache hits, warnings from OMC and from the run). It attaches no handlers and sets no levels.

### Breaking changes

Replacing Pydelica with the in-repo OMC backend changed the following:

- Override paths are `build.*` and `settings.*`, not `session.*`. Parameters are `settings.parameters.*`, and the config groups are `settings` and `settings/parameters`.
- `Session`, `Model`, `Simulation`, `TimeRange`, `Tolerance`, `VariableFilter`, `SessionBuilder`, `SessionDirector` and the Pydelica exception types are removed. Use the dataclasses `Build`, `Library`, `RunSettings` and `SimulationRun` in `mtools.session_config` and the exceptions in `mtools.errors`.
- `create_run` takes `model_name`, `model_path`, `target`, `extra_sources`, `libraries`, `omc_flags` and `settings`.
- Models without an `experiment` annotation run from 0 to 1 s (OMC's defaults) instead of 0 to 10 s with tolerance 1e-9.
- Boolean columns are `bool` instead of 0/1 integers, so `save_solutions` writes them as `True`/`False` instead of `0`/`1`. The plotting tool still shows them as 0/1.
- Integer and enumeration columns stay `int64`.
- Real columns are always `float64`, also when every value is a whole number; Pydelica read those as `int64`.
- Results have no parameter columns and keep OMC's repeated rows at events.
- The cache lives under the system temp directory until the system clears it.

### Visualize results

```bash
uv run python -m mtools path/to/results
```

This launches an interactive Dash dashboard for exploring simulation output CSV files, with per-graph x-axis (`time` or any signal) and y-axis signal selection.
