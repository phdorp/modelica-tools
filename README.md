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
- **Result visualization** — Interactive [Dash](https://dash.plotly.com/) web app for browsing simulation results (`.mat` and `.csv`) with a grid of time-series plots.
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
    solutions = sim_tools.simulate(config)
    sim_tools.save_solutions(solutions, HydraConfig.get().runtime.output_dir, config.output_format)


if __name__ == "__main__":
    my_simulation.config.registry.add_to_hydra_store()
    main()
```

See [`examples/src/kinematic_vehicle/__main__.py`](examples/src/kinematic_vehicle/__main__.py) for the corresponding example.

The `simulate` function validates the run config, builds the model (or reuses a cached build), runs it with the given parameters and settings, and returns one DataFrame per model, keyed by `build.model_name`. `save_solutions` writes them as `.mat` files, or as `.csv` with `output_format=csv`; `load_solution` reads either back. See [The Hydra registry](docs/hydra-registry.md) for run configs, config groups and experiments, and [The OMC backend](docs/omc-backend.md) for what a run does.

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

Save CSV instead of `.mat`, or run a sweep:

```bash
uv run python -m my_simulation output_format=csv
uv run python -m my_simulation -m settings.parameters.some_value=1,2,3
```

Every override path, the parameter naming rules and experiments are described in [The Hydra registry](docs/hydra-registry.md#the-run-config).

Refer to the [`kinematic_vehicle` examples](examples/) for a complete working setup.

### OMC backend

mtools builds and runs models with OpenModelica's `omc` and caches builds across runs and sweeps. [The OMC backend](docs/omc-backend.md) describes:

- [how a run works](docs/omc-backend.md#how-a-run-works);
- [what a result contains](docs/omc-backend.md#results) and [how it is saved](docs/omc-backend.md#saving-results);
- [the C and Cpp targets](docs/omc-backend.md#targets);
- [the environment variables](docs/omc-backend.md#environment-variables) (`MTOOLS_WORK_DIR`, `MTOOLS_NO_CACHE`, `MTOOLS_KEEP_RUNS`);
- [the build cache](docs/omc-backend.md#build-cache);
- [errors and logging](docs/omc-backend.md#errors-and-logging).

### Breaking changes

Replacing Pydelica with the in-repo OMC backend changed the following:

- Override paths are `build.*` and `settings.*`, not `session.*`. Parameters are `settings.parameters.*`, and the config groups are `settings` and `settings/parameters`.
- `Session`, `Model`, `Simulation`, `TimeRange`, `Tolerance`, `VariableFilter`, `SessionBuilder`, `SessionDirector` and the Pydelica exception types are removed. Use the dataclasses `Build`, `Library`, `RunSettings` and `SimulationRun` in `mtools.session_config` and the exceptions in `mtools.errors`.
- `create_run` takes `model_name`, `model_path`, `target`, `extra_sources`, `libraries`, `omc_flags` and `settings`.
- Models without an `experiment` annotation run from 0 to 1 s (OMC's defaults) instead of 0 to 10 s with tolerance 1e-9.
- `save_solutions` writes `.mat` by default; pass `output_format="csv"` (or set `output_format=csv` on the command line) for CSV.
- Boolean columns are `bool` instead of 0/1 integers, so a CSV has `True`/`False` instead of `0`/`1`. The plotting tool still shows them as 0/1.
- Integer and enumeration columns stay `int64`.
- Real columns are always `float64`, also when every value is a whole number; Pydelica read those as `int64`.
- Results have no parameter columns and keep OMC's repeated rows at events.
- The cache lives under the system temp directory until the system clears it.

### Visualize results

```bash
uv run python -m mtools path/to/results
```

This launches an interactive Dash dashboard for exploring the `.mat` and `.csv` result files under the directory, with per-graph x-axis (`time` or any signal) and y-axis signal selection.
