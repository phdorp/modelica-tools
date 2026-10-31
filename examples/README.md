# Examples

This directory contains a `kinematic_vehicle` example package that demonstrates how to configure and run a [Modelica](https://modelica.org/) simulation with `modelica-tools`.

The example uses a bicycle kinematic model (`kinematic_vehicle.mo`) with three state variables (`px`, `py`, `theta`), an initial state config group, and sweepable parameters (`v_norm`).

## Project structure

```
src/kinematic_vehicle/
├── __init__.py
├── __main__.py              # Hydra entry point: composes config and runs simulation
├── KinematicVehicle.mo      # Candidate Modelica model
├── kinematic_vehicle.py     # Config dataclasses, registry setup, group options
└── experiments.py           # Named experiment registration (e.g. front_position)
tests/
├── __init__.py
├── experiments.py           # Candidate experiment registrations
├── reference_experiments.py # Dedicated registry and experiments for the reference model
├── reference_models/        # Separate Modelica package for the reference model
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

Selects the `front_position` config group, which sets `state_0.px=1.0`. The group is registered via `register_group_name("session.parameters.state_0", "parameters/state_0")` with two options (`zero_state`, `front_position`) in `kinematic_vehicle.py`.

### Experiment override

```bash
uv run python -m kinematic_vehicle experiment=front_position
```

Applies the `front_position` experiment defined in `src/kinematic_vehicle/experiments.py`, which overrides the `parameters/state_0` group to `front_position`.

Experiments are registered via `registry.register_experiment()` and compose their configs using Hydra's `override /group` defaults syntax.

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

The reference model has its own Hydra registry in `tests/reference_experiments.py`. That
registry owns the reference parameters, model source, model configurations, libraries, and
simulation settings, and registers experiments under the same names as the candidate
registry. The test module provides four fixtures: `model_name` selects the candidate,
`reference_name` selects the reference model, `registry` supplies the candidate experiment
configurations, and `reference_registry` supplies the reference configurations. Test
classes inherit `ExperimentReference` for a single experiment or
`ExperimentSweepReference` for a parameter sweep:

```python
import pytest
from mtools.testing import ExperimentReference, ExperimentSweepReference
from tests import reference_experiments
from tests.experiments import registry as kinematic_registry


@pytest.fixture(scope="module")
def registry():
    return kinematic_registry


@pytest.fixture(scope="module")
def reference_registry():
    return reference_experiments.registry


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

Both bases run the experiment for the candidate from `registry` and the reference from
`reference_registry`. The candidate table is exposed as `results` and the reference table as
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
