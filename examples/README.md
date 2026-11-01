# Examples

This directory contains a `kinematic_vehicle` example package that demonstrates how to configure and run a [Modelica](https://modelica.org/) simulation with `modelica-tools`.

The example uses a bicycle kinematic model (`kinematic_vehicle.mo`) with three state variables (`px`, `py`, `theta`), an initial state config group, and sweepable parameters (`v_norm`).

## Project structure

```
src/kinematic_vehicle/
├── __init__.py
├── __main__.py              # Hydra entry point: composes config and runs simulation
├── KinematicVehicle.mo      # Candidate Modelica model
├── shared_config.py         # Shared schema and group options
├── kinematic_vehicle.py     # Shared registry, candidate run config, experiment binding
└── experiments.py           # Shared experiment definitions (e.g. front_position)
tests/
├── __init__.py
├── reference_models/        # Separate Modelica package for the reference model
│   ├── __init__.py
│   ├── kinematic_vehicle.py # Reference run config added to the shared registry
│   ├── package.mo
│   ├── State.mo
│   ├── Input.mo
│   └── KinematicVehicle.mo
├── test_kinematic_vehicle.py  # Plausibility tests via parameterized experiments
└── test_reference_comparison.py  # Candidate vs reference model comparison
```

## Prerequisites

- [OpenModelica](https://openmodelica.org/) installed (`omc` and `omlibrary` packages on Debian/Ubuntu)
- **Python >= 3.11** with [uv](https://docs.astral.sh/uv/)

## Installation

The example is part of the `modelica-tools` workspace. Install from the repository root:

```bash
git clone https://github.com/phdorp/modelica-tools.git
cd modelica-tools
uv sync --dev
```

## Run simulation

All commands must be run from the `examples/` directory.

### Default configuration

```bash
uv run python -m kinematic_vehicle
```

Runs the simulation with default parameters: `v_norm=10.0`, `stop_time=10.0`, initial state `(px=0, py=0)`.

### Config group override

```bash
uv run python -m kinematic_vehicle parameters/state_0=front_position
```

Selects the `front_position` config group, which sets `state_0.px=1.0`. The group is registered via `register_group_name("session.parameters.state_0", "parameters/state_0")` with two options (`zero_state`, `front_position`) in `shared_config.py`.

### Experiment override

```bash
uv run python -m kinematic_vehicle experiment=front_position
```

Applies the `front_position` experiment defined in `src/kinematic_vehicle/experiments.py`, which overrides the `parameters/state_0` group to `front_position`.

Experiments are registered via `HydraZenRegistry.register_experiment(registry, ...)` and compose their configs using Hydra's `override /group` defaults syntax.

### Parameter sweep

```bash
uv run python -m kinematic_vehicle -m session.parameters.v_norm=10,20
```

Launches a multirun sweep over `v_norm` values 10 and 20. Hydra runs separate simulations for each value and stores results in separate output directories.

## Tests

Plausibility tests verify kinematic vehicle behavior (standstill, straight driving, turn left) against expected physical properties. Tests require OpenModelica and the optional test dependencies:

```bash
uv sync --group test
uv run pytest
```

`TestProtectedOutput` runs the `protected_output` experiment to show the `emit_protected` runtime option: setting
`sim_configurations.emit_protected=True` logs protected Modelica variables (here `px_dot`, `py_dot`, `theta_dot`) as
extra result columns. The option defaults to `False`, so protected variables are omitted unless enabled.

## Compare against a reference model

`tests/reference_models/` is a separate Modelica package containing a behaviourally
identical reference model. The candidate lives in the `src/kinematic_vehicle` package, so the
comparison demonstrates cross-package testing rather than two models in one source file.

A single `HydraZenRegistry` is owned by `src/kinematic_vehicle/kinematic_vehicle.py`. It applies
the shared group options, creates the candidate run config (`name="default"`), and calls
`register_experiments(EXPERIMENTS, base_run_config=run_default)`. The reference run config is
added to that same registry by `tests/reference_models/kinematic_vehicle.py`, which imports the
candidate registry and creates a second run config (`name="reference"`,
`include_experiment_group=True`) that points at the `tests`-side reference Modelica package.

The registry binds every experiment to every run config whose defaults include the `experiment`
group, now and for any run config registered later. Registering the reference run config is
therefore all that is needed; there is no separate experiment-sharing call. Experiments are
defined once in `src/kinematic_vehicle/experiments.py` as `ExperimentSpec` values.
`compose_experiment(name, run_config=...)` and `get_experiment_run_config(name, run_config=...)`
accept an optional run config; when omitted they use the run config the experiment was
registered with.

The test module provides two fixtures: `registry` supplies the shared registry, and
`reference_run_config` supplies the run config that composes the reference. The candidate is the
experiment's registered (default) run config, and each side's model name is read from its run
config, so no name fixture is needed. Test classes inherit `ExperimentReference` for a single
experiment or `ExperimentSweepReference` for a parameter sweep:

```python
import pytest
from kinematic_vehicle.kinematic_vehicle import registry as model_registry
from tests.reference_models.kinematic_vehicle import run_reference

from mtools.testing import ExperimentReference, ExperimentSweepReference


@pytest.fixture(scope="module")
def registry():
    return model_registry


@pytest.fixture(scope="module")
def reference_run_config():
    return run_reference


class TestStandstillReference(ExperimentReference):
    name = "standstill"

    def test_matches_reference(self):
        self.assert_matches_reference()


class TestTurnLeftReference(ExperimentSweepReference):
    name = "turn_left"
    sweep_params = {"phi": [0.1, 0.5, 1.0]}

    def test_matches_reference(self):
        self.assert_matches_reference()
```

Both bases run the experiment for the candidate from the registry's default run config and the
reference from `registry` with `run_config=reference_run_config`. The candidate table is exposed
as `results` and the reference table as
`reference_results`; sweeps key both mappings by parameter combination.
`assert_matches_reference()` fails if the models expose different output signals, if their
solution lengths differ, or if any signal value differs beyond `eps` (absolute tolerance,
defaulting to `numpy.finfo(float).eps`). Override `eps` on the test class to allow known
numerical differences. The comparison is explicit, so a test can assert physical properties
before comparing against the reference.

See `tests/test_reference_comparison.py` for the complete example.

## Results

Simulation results are saved as CSV files in Hydra's run output directory (printed to the console during execution). Visualize results with:

```bash
uv run python -m mtools <output_directory>
```
