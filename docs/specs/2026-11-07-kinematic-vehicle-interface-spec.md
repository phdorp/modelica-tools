# Kinematic Vehicle Interface Refactor Spec

Status: ready for implementation
Source: Conversation on 2026-11-07 (refactor request for `examples/src/kinematic_vehicle`)

## Problem Statement

The example kinematic vehicle currently mixes three concerns in one Modelica
model: simulation parameters, input signals, and state. It represents inputs and
state with the `Input` and `State` records, so the model's interface is coupled
to one particular data layout. A user cannot substitute a different
implementation behind the same signals, and standalone simulation requires the
records and an initial-state parameter to travel together.

The Python side mirrors that coupling: the parameter dataclass carries a nested
`state_0` object and a wheelbase field that is not reachable through the model
that is actually simulated. Removing or renaming a Modelica signal therefore
requires edits in the model, the registry, the tests, the reference package, and
the README.

## Solution

Split the example into a reusable interface, one concrete implementation, and a
standalone wrapper:

- `IKinematicVehicle` declares the external contract: inputs `v_norm` and
  `phi`, outputs `px`, `py`, and `theta`.
- `KinematicVehicle` extends the interface, owns the wheelbase parameter, and
  implements the bicycle kinematic differential equations plus a zero initial
  state.
- `WrapperKinematicVehicle` is the simulated block. It parameterizes the
  vehicle's inputs and wheelbase so the model can run standalone.

The Python registry points at the wrapper and exposes only the wrapper's
parameters: `v_norm`, `phi`, and `wheelbase`. The `State` and `Input` records,
the `state_0` parameter group, and the `front_position` experiment disappear.
The test-side reference package is ported to the same structure so the
cross-package comparison keeps proving behavioural equivalence.

## User Stories

1. As a model developer, I want an `IKinematicVehicle` interface that declares
   inputs `v_norm` and `phi` and outputs `px`, `py`, and `theta`, so that every
   implementation exposes the same external signals.
2. As a model developer, I want `KinematicVehicle` to inherit the interface, so
   that I do not repeat input and output declarations in the implementation.
3. As a model developer, I want the differential equations to live in
   `KinematicVehicle`, so that the implementation owns its dynamics.
4. As a model developer, I want a `wheelbase` parameter in `KinematicVehicle`,
   so that the turning response is configurable without changing equations.
5. As a model developer, I want the initial state `(px, py, theta) = (0, 0, 0)`
   expressed as initial equations in `KinematicVehicle`, so that the interface
   stays free of initialization policy.
6. As a model developer, I want a `WrapperKinematicVehicle` block with
   parameters `v_norm`, `phi`, and `wheelbase`, so that I can simulate the
   vehicle standalone without an external signal source.
7. As a model developer, I want the wrapper to drive the implementation's
   inputs by equations, so that the wrapper parameters behave like control
   inputs during a run.
8. As a model developer, I want the `State` and `Input` records removed, so that
   the example no longer depends on record types to carry signals.
9. As a model developer, I want the Python run config to select
   `kinematic_vehicle.WrapperKinematicVehicle`, so that every run simulates the
   standalone block.
10. As a model developer, I want a Python parameter dataclass whose fields are
    exactly `v_norm`, `phi`, and `wheelbase`, so that parameter overrides map
    one-to-one onto Modelica parameters.
11. As a model developer, I want the `state_0` parameter group and the
    `front_position` experiment removed, so that no configuration path points
    at the deleted state record.
12. As a model developer, I want the `standstill`, `straight_driving`,
    `turn_left`, and `protected_output` experiments preserved against the
    wrapper, so that the example keeps demonstrating the same runtime features.
13. As a test author, I want the example tests to address signals by their
    wrapper path (`vehicle.px`, `der(vehicle.px)`, `vehicle.px_dot`), so that
    the tests prove the actual simulated variable names.
14. As a test author, I want a wheelbase sweep that shows a longer wheelbase
    turns more slowly, so that the new parameter is verified through simulation
    and not only through config composition.
15. As a test author, I want the reference package ported to the same
    interface/implementation/wrapper structure, so that the comparison test
    still matches signal names and values.
16. As a user, I want the README to describe the new files, model name, and
    parameter overrides, so that the documented commands work.
17. As a user, I want an invalid or missing wrapper parameter to fail at build
    or composition time, so that a stale `state_0` override is not silently
    ignored.
18. As a maintainer, I want no changes to `mtools` or the main test-suite
    fixture model, so that the refactor stays inside the example and its
    reference package.

## Implementation Decisions

### Interface contract

`IKinematicVehicle` is a `partial model` in the example package. It declares
`input Real v_norm`, `input Real phi`, `output Real px`, `output Real py`, and
`output Real theta`. It declares no parameters, equations, or initial
attributes; initialization belongs to the concrete implementation.

### Implementation

`KinematicVehicle` extends `IKinematicVehicle` and declares
`parameter Real wheelbase = 2`. It keeps the existing protected derivative
names and definitions, `Real px_dot = der(px)`, `Real py_dot = der(py)`, and
`Real theta_dot = der(theta)`, and uses them in the existing equations:

- `px_dot = v_norm * cos(theta)`
- `py_dot = v_norm * sin(theta)`
- `theta_dot = v_norm / wheelbase * tan(phi)`

An `initial equation` section fixes `px`, `py`, and `theta` to zero. This
replaces the old `state_0` parameter and fixed-start attributes.

### Standalone wrapper

`WrapperKinematicVehicle` is a `block` in the example package. It declares
parameters `v_norm = 10`, `phi = 0.1`, and `wheelbase = 2`, instantiates one
`KinematicVehicle` component named `vehicle`, binds the wheelbase through the
component modification, and drives the inputs by equations. The wrapper adds no
output aliases, so simulation results expose `vehicle.px`, `vehicle.py`,
`vehicle.theta`, and protected derivatives under `vehicle.*`.

The `wheelbase` wrapper parameter is an explicit extension of the original
request, chosen so Python runs and sweeps can override it.

### Removed model elements

The `State` and `Input` record files are deleted from both the candidate and the
reference package. No model declares `state` or `control` components, and no
configuration path refers to `state_0`.

### Python configuration

The parameter dataclass is named `WrapperKinematicVehicle` and has fields
`v_norm: float = 10.0`, `phi: float = 0.0`, and `wheelbase: float = 2.0`.
`MODEL_NAME` becomes `kinematic_vehicle.WrapperKinematicVehicle`, and
`vehicle_default`, every experiment override, and `run_default` all use the
`WrapperKinematicVehicle` dataclass. No Python configuration may name the bare
`kinematic_vehicle.KinematicVehicle` model; that name is reserved for the
Modelica implementation that the wrapper instantiates. The
`parameters/state_0` group registration and its group options are removed.
The `standstill`, `straight_driving`, `turn_left`, and `protected_output`
experiments remain; `front_position` is removed. Experiment overrides set all
three wrapper parameters explicitly.

The Modelica wrapper keeps `phi = 0.1` while the Python default stays `0.0`;
this preserves the previous example convention where Python runs supply their
own steering value.

### Reference package

The test-side reference package mirrors the candidate structure with package
name `reference_models`: its own `IKinematicVehicle`, `KinematicVehicle`, and
`WrapperKinematicVehicle`, the same component name `vehicle`, the same equations
and initial state, and model name `reference_models.WrapperKinematicVehicle`.
The reference run config keeps using the shared parameter group, so both sides
receive the same parameter values during comparisons.

### Documentation

The README's project structure, default-run description, experiment examples,
parameter override examples, and protected-output note are updated. The
removed config-group and `front_position` sections are replaced with direct
parameter overrides.

## Testing Decisions

Good tests exercise the simulated wrapper through the existing experiment bases
and assert external signals, not Modelica internals.

Seams:

- `examples/tests/test_kinematic_vehicle.py` runs the wrapper through
  OpenModelica and addresses exported signals. It covers standstill, straight
  driving, a phi sweep, a wheelbase sweep, velocity change, and protected
  output. The `protected_output` experiment enables `emit_protected`, and
  `TestProtectedOutput` checks `vehicle.px_dot`, `vehicle.py_dot`, and
  `vehicle.theta_dot` against the matching `der(vehicle.*)` columns.
- The same module composes run and experiment configs to prove the model name,
  default parameter values, Cpp target, and solver.
- `examples/tests/test_reference_comparison.py` compares the refactored
  candidate wrapper with the separately packaged reference wrapper under the
  shared registry.

Covered failure modes:

- a stale `state.px` or `control.phi` signal name (missing column),
- a wrapper parameter that never reaches the implementation (wheelbase sweep),
- protected variables absent by default and present with `emit_protected`,
  with all three derivatives matching their `der(...)` columns,
- a reference package whose signal set or values diverge from the candidate,
- a run config that still selects `KinematicVehicle` instead of the wrapper.

Prior art: the existing example tests already use the `Experiment`,
`ExperimentSweep`, and `ExperimentReference` bases and run real OpenModelica
simulations.

## Out of Scope

- Changes to `mtools`, including the registry, simulation, or testing modules.
- Changes to the main suite's `tests/session_tools/models/kinematic_vehicle.mo`
  fixture.
- Alias outputs on the wrapper or preservation of the old `state.*` and
  `control.*` result-column names.
- Configurable initial states, including keeping the `front_position`
  experiment.
- Unit annotations, wheelbase validation, or non-zero initial conditions.
- Changing the Cpp target, solver choice, or result output format.

## Further Notes

This is a breaking change for anyone using the example's old configuration
paths: `session.parameters.state_0` and `parameters/state_0` are gone, result
columns move from `state.*` to `vehicle.*`, and the simulated model changes from
`kinematic_vehicle.KinematicVehicle` to
`kinematic_vehicle.WrapperKinematicVehicle`.