# Examples

The directory contains an example package `kinematic_vehicle` that demonstrates a configuration with a modelica model.

## Installation

Install the `kinematic_vehicle` package in a virtual environment with

```bash
pip install -e .
```

## Run simulation

The simulation can be executed with session parameter overrides from the commandline:

```bash
python -m kinematic_vehicle # default configuration
python -m kinematic_vehicle parameters/state_0=front_position # `front_position` initial state override
python -m kinematic_vehicle experiment=front_position
python -m kinematic_vehicle -m session.parameters.v_norm=10,20 # multirun with `v_norm` override
```
