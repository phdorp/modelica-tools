# modelica-tools

A Python toolkit for configuring [Pydelica](https://pypi.org/project/pydelica/) sessions, enabling fully configurable [Modelica](https://modelica.org/) simulation runs from Python.

[Pydelica](https://pypi.org/project/pydelica/) provides Python bindings for [OpenModelica](https://openmodelica.org/), giving access to a `pydelica.Session` API with methods to build models, set parameters, configure solvers, and run simulations. `modelica-tools` wraps this API with typed configuration dataclasses and a registry system powered by [Hydra](https://hydra.cc) / [hydra-zen](https://github.com/mit-ll/hydra-zen), allowing simulation setups to be defined once in Python and then overridden, composed, and swept from the command line.

## Features

- **Python-native Modelica configuration** — Define simulation parameters, solver settings, and model configurations as typed Python dataclasses.
- **Hierarchical configuration** with [Hydra](https://hydra.cc) / [hydra-zen](https://github.com/mit-ll/hydra-zen) — Compose, override, and reuse configs across runs.
- **Parameter sweeps** — Launch multirun sweeps over any simulation parameter from the command line.
- **Configuration groups and experiments** — Register reusable config groups (e.g., initial states) and named experiment overrides.
- **Result visualization** — Interactive [Dash](https://dash.plotly.com/) web app for browsing simulation results (CSV) with a grid of time-series plots.
- **Unit-testable** — Simulations are driven by config objects that can be instantiated and verified in isolation.

## Installation

### Prerequisites

Install [OpenModelica](https://openmodelica.org/) (required by `pydelica`):

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

The workspace is mounted into the container, so edits on your host are reflected immediately, and any Python version manager or OpenModelica installation on the host is not needed.

## Testing

```bash
uv run pytest tests
```

Tests require OpenModelica installed (see prerequisites) and compile actual Modelica models via `pydelica`.

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

The `simulate` function instantiates the `Session` via `hydra_zen.instantiate`, which builds the model, applies parameters, configures the solver, and saves simulation results as CSV.

### Run a simulation

Run the simulation with the default configuration:

```bash
uv run python -m my_simulation
```

Override individual parameters or select registered config groups from the command line:

```bash
uv run python -m my_simulation session.parameters.some_value=5.0
uv run python -m my_simulation session.model_configurations.MyModel.time_range.stop_time=20.0
```

Parameter paths follow the structure of the config dataclasses defined in `config.py`.
Refer to the [`kinematic_vehicle` examples](examples/) for a complete working setup.

### Visualize results

```bash
uv run python -m mtools path/to/results
```

This launches an interactive Dash dashboard for exploring simulation output CSV files.
