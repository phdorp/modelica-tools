# mtools

mtools configures and runs OpenModelica simulations from Python, driven by Hydra configs, and returns the simulated signals as tables.

## Simulation

**Build**:
One Modelica model compiled with one build configuration, ready to be run any number of times. A build is never changed after it is made.
_Avoid_: Session, compiled model, binary

**Build config**:
The inputs that determine a build: model source, model name, simulation target, extra sources, libraries and compiler flags. Two builds with equal build configs are interchangeable.
_Avoid_: Build options

**Build-time parameter**:
A parameter whose value OMC fixes while translating the model, so changing it needs a new build rather than a new run.
_Avoid_: Structural parameter (only one of several reasons a parameter is fixed), non-tunable parameter

**Simulation target**:
The OMC code generator and runtime a build uses: C, the default, or Cpp, an alternative chosen deliberately when C is not an option. Results can differ between targets.
_Avoid_: Fallback, backend

**Run**:
One execution of a build with fixed run settings.
_Avoid_: Simulation (as a noun for a single execution), job

**Run settings**:
Everything that can vary between runs of the same build: parameter values, time range, output interval, tolerance, solver, variable filter, whether protected variables are emitted, the time limit, and whether chattering aborts the run.
_Avoid_: Simulation options, runtime options, sim configurations

**Result**:
The time series a run returns for its model: one row per output time point, one column per variable.
_Avoid_: Solution

**Partial result**:
The part of a result written before a run failed, kept for debugging and never mistaken for a full result.
_Avoid_: Truncated solution

**Diagnostics**:
The errors, warnings and failed assertions that OMC, the C compiler or the simulation runtime report about a build or run, filtered down to what explains the outcome.
_Avoid_: Log, OMC output
