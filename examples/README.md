# Examples

This directory contains a `kinematic_vehicle` example package that demonstrates how to configure and run a [Modelica](https://modelica.org/) simulation with `modelica-tools`.

The example splits a bicycle kinematic model into an interface (`IKinematicVehicle`), an implementation
(`KinematicVehicle`), and a standalone block (`WrapperKinematicVehicle`). The wrapper is the simulated
model: its sweepable `v_norm`, `phi`, and `wheelbase` parameters drive the implementation, which starts
from the zero initial state `(px, py, theta) = (0, 0, 0)`. Simulation results expose the implementation's
signals under the `vehicle.*` path.

## Project structure

```
src/kinematic_vehicle/
├── __init__.py
├── __main__.py              # Hydra entry point: composes config and runs simulation
├── IKinematicVehicle.mo     # Interface: inputs v_norm and phi, outputs px, py, and theta
├── KinematicVehicle.mo      # Implementation: bicycle equations and zero initial state
├── WrapperKinematicVehicle.mo  # Simulated block: parameters drive the implementation
└── kinematic_vehicle.py     # Registry, group options, run config, and experiments
tests/
├── __init__.py
├── reference_models/        # Separate Modelica package for the reference model
│   ├── __init__.py
│   ├── kinematic_vehicle.py # Reference run config added to the shared registry
│   ├── package.mo
│   ├── IKinematicVehicle.mo
│   ├── KinematicVehicle.mo
│   └── WrapperKinematicVehicle.mo
├── test_entry_point.py     # `python -m kinematic_vehicle` saves .mat or .csv
├── test_kinematic_vehicle.py  # Plausibility tests via parameterized experiments
└── test_reference_comparison.py  # Candidate vs reference model comparison
```

## How the run config is built

`src/kinematic_vehicle/kinematic_vehicle.py` creates one `HydraZenRegistry` and fills a `SimulationRun` in four steps. [The Hydra registry](../docs/hydra-registry.md) describes each call.

1. `register_group_options("settings/parameters", {"default": vehicle_default}, default="default")` makes the `WrapperKinematicVehicle` dataclass the parameter defaults, overridable as `settings.parameters.*`.
2. `register_group_options("settings", {"default": settings_default}, default="default")` sets the run settings: `stop_time=10.0`, `tolerance=1e-9` and `solver="dassl"`. Its `parameters` are left `MISSING`, so the group above fills them.
3. `create_run(model_name=MODEL_NAME, model_path=..., target="Cpp", include_experiment_group=True, name="default")` creates the `build` part and registers the run config as `default`, the `config_name` that `__main__.py` passes to `@hydra.main`.
4. `register_experiment(name=..., base_run_config=run_default, overrides={...})` registers `standstill`, `straight_driving`, `turn_left` (each replacing `settings/parameters`) and `protected_output` (replacing `settings`).

The composed config has three top-level keys: `build`, `settings` and `output_format`.

## Prerequisites

- [OpenModelica](https://openmodelica.org/) installed (`omc`, `omlibrary`, `libomccpp`, `clang`, and `libomp-dev` packages on Debian/Ubuntu)
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

Runs `kinematic_vehicle.WrapperKinematicVehicle` with default parameters `v_norm=10.0`, `phi=0.0`,
`wheelbase=2.0`, `stop_time=10.0`, and zero initial state for `vehicle.px`, `vehicle.py`, and
`vehicle.theta`.

The run configs set `build.target="Cpp"`, so results come from OpenModelica's C++ simulation
runtime (see [Targets](../docs/omc-backend.md#targets)). The run settings set `solver="dassl"`
because the Cpp runtime only supports `dassl`, `cvode` and `ida`. The model has no `experiment`
annotation, so `settings_default` in `src/kinematic_vehicle/kinematic_vehicle.py` sets `stop_time=10.0` and
`tolerance=1e-9`.

### Parameter overrides

```bash
uv run python -m kinematic_vehicle settings.parameters.phi=0.1
uv run python -m kinematic_vehicle settings.parameters.wheelbase=3.0
```

Overrides a wrapper parameter directly. `phi` is the steering angle in radians and `wheelbase` is the
distance between the axles. `v_norm` is overridden the same way.

### Experiment override

```bash
uv run python -m kinematic_vehicle experiment=turn_left
```

Applies the `turn_left` experiment defined in `src/kinematic_vehicle/kinematic_vehicle.py`, which sets
all three wrapper parameters (`v_norm`, `phi`, and `wheelbase`).

Experiments are registered via `registry.register_experiment(...)` and compose their configs using Hydra's `override /group` defaults syntax.

### Build and run settings overrides

```bash
uv run python -m kinematic_vehicle build.target=C
uv run python -m kinematic_vehicle settings.stop_time=20 "settings.variable_filter='vehicle\.p[xy]'"
uv run python -m kinematic_vehicle '+build.omc_flags={-d:initialization}'
```

`build.*` overrides change what is built, so the first run with a new value builds the model and later runs reuse that build. The first command runs the model on OpenModelica's C runtime instead of Cpp. `settings.*` overrides only change the run. `variable_filter` keeps `time`, `vehicle.px` and `vehicle.py`; quote a regular expression with `[` or `,` so Hydra reads it as one string. `build.omc_flags` needs the leading `+`.

### Output format

```bash
uv run python -m kinematic_vehicle                    # kinematic_vehicle.WrapperKinematicVehicle.mat
uv run python -m kinematic_vehicle output_format=csv  # kinematic_vehicle.WrapperKinematicVehicle.csv
```

`src/kinematic_vehicle/__main__.py` passes the run config's `output_format` to `save_solutions`, so the result is saved as `.mat` by default and as `.csv` on request. Read either file back with `mtools.sim_tools.load_solution(path)`. A `.mat` file keeps the column types; `vehicle.*` columns are all `float64` in this model.

### Parameter sweep

```bash
uv run python -m kinematic_vehicle -m settings.parameters.v_norm=10,20
```

Launches a multirun sweep over `v_norm` values 10 and 20. Hydra runs separate simulations for each value and stores results in separate output directories. `phi` and `wheelbase` are sweepable the same way, for example `uv run python -m kinematic_vehicle -m settings.parameters.wheelbase=2,4`.

## Tests

Plausibility tests verify kinematic vehicle behavior (standstill, straight driving, turn left) against expected physical properties. Tests require OpenModelica and the optional test dependencies:

```bash
uv sync --group test
uv run pytest
```

`TestProtectedOutput` runs the `protected_output` experiment to show the `emit_protected` runtime option: setting
`settings.emit_protected=True` logs protected Modelica variables (here `vehicle.px_dot`,
`vehicle.py_dot`, and `vehicle.theta_dot`) as extra result columns. The option defaults to `False`, so protected variables are omitted unless enabled.

## Compare against a reference model

`tests/reference_models/` is a separate Modelica package nested in the `tests`
package, mirroring the candidate structure: `tests.reference_models.KinematicVehicle` and the
simulated `tests.reference_models.WrapperKinematicVehicle`, with the same `vehicle` component
and equations. `tests.reference_models.KinematicVehicle` extends the candidate interface
`kinematic_vehicle.IKinematicVehicle`, and the reference build loads the candidate package as an
`extra_sources` entry, so there is no duplicate interface to maintain. The
candidate lives in the `src/kinematic_vehicle` package, so the comparison demonstrates cross-package
testing rather than two models in one source file.

A single `HydraZenRegistry` is owned by `src/kinematic_vehicle/kinematic_vehicle.py`. It registers
the shared group options, creates the candidate run config (`name="default"`), and registers
each experiment directly with `register_experiment(..., base_run_config=run_default)`. The
reference run config is added to that same registry by
`tests/reference_models/kinematic_vehicle.py`, which imports the candidate registry and creates
a second run config (`name="reference"`, `include_experiment_group=True`) that points at the
`tests`-side reference Modelica package.

The registry binds every experiment to every run config whose defaults include the `experiment`
group, now and for any run config registered later. Registering the reference run config is
therefore all that is needed; there is no separate experiment-sharing call. The parameter
schema, group options, and experiments are all defined once in
`src/kinematic_vehicle/kinematic_vehicle.py`.
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

Simulation results are saved in Hydra's run output directory (printed to the console during execution), as `.mat` unless `output_format=csv` is given. Visualize `.mat` and `.csv` results with:

```bash
uv run python -m mtools <output_directory>
```
