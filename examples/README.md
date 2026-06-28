# Examples

This directory contains a `kinematic_vehicle` example package that demonstrates how to configure and run a [Modelica](https://modelica.org/) simulation with `modelica-tools`.

The example uses a bicycle kinematic model (`kinematic_vehicle.mo`) with three state variables (`px`, `py`, `theta`), an initial state config group, and sweepable parameters (`v_norm`).

## Project structure

```
src/kinematic_vehicle/
├── __init__.py
├── __main__.py              # Hydra entry point: composes config and runs simulation
├── kinematic_vehicle.mo     # Modelica model
├── kinematic_vehicle.py     # Config dataclasses, registry setup, group options
└── experiments.py           # Named experiment registration (e.g. front_position)
tests/
├── __init__.py
├── experiments.py           # Test-specific experiment registrations
└── test_kinematic_vehicle.py  # Plausibility tests via parameterized experiments
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

## Results

Simulation results are saved as CSV files in Hydra's run output directory (printed to the console during execution). Visualize results with:

```bash
uv run python -m mtools <output_directory>
```
