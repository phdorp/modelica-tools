# Examples

The directory contains an example package `kinematicVehicle` that demonstrates a configuration with a modelica model.

## Installation

Install the `kinematicVehicle` package in a virtual environment with

```bash
pip install -e .
```

## Run simulation

The simulation can be executed with session parameter overrides from the commandline:

```bash
python -m kinematicVehicle # default configuration
python -m kinematicVehicle parameters/state_0=front_position # `front_position` initial state override
python -m kinematicVehicle experiment=front_position
python -m kinematicVehicle -m session.parameters.v_norm=10,20 # multirun with `v_norm` override
```
