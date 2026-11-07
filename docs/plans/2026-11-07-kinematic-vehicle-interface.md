# Kinematic Vehicle Interface Refactor Plan

**Feature:** Split the kinematic vehicle example into interface, implementation,
and standalone wrapper, with matching Python configuration, tests, reference
package, and documentation.

**Goal:** Simulating `kinematic_vehicle.WrapperKinematicVehicle` must produce the
same bicycle-kinematic behaviour as the old example while exposing `v_norm`,
`phi`, and `wheelbase` as Python-overridable parameters.

**Architecture:** `IKinematicVehicle` declares inputs and outputs.
`KinematicVehicle` inherits it, owns `wheelbase`, implements the differential
equations, and fixes the initial state to zero. `WrapperKinematicVehicle` is a
block that parameterizes one `vehicle` component so the example can simulate it
standalone. The Python registry selects the wrapper and maps a flat
`WrapperKinematicVehicle` dataclass onto its parameters.

**Tech stack:** Modelica, OpenModelica 1.27 with the Cpp simulation target,
pydelica, hydra-zen, pytest, pandas/numpy.

**Spec:** `docs/specs/2026-11-07-kinematic-vehicle-interface-spec.md`

## Global Constraints

- Keep `--simCodeTarget=Cpp` and the `dassl` solver; the Cpp runtime does not
  support the deprecated `rungekutta` solver.
- Do not add dependencies; use the existing `examples[test]` environment.
- Preserve the physical equations and protected derivative names from the old
  model.
- Do not change `mtools` or `tests/session_tools/models/kinematic_vehicle.mo`.
- Result signals for the simulated wrapper are `vehicle.px`, `vehicle.py`,
  `vehicle.theta`, `der(vehicle.px)`, and, when protected output is enabled,
  `vehicle.px_dot`, `vehicle.py_dot`, `vehicle.theta_dot`.
- Python parameter paths are flat: `session.parameters.v_norm`,
  `session.parameters.phi`, `session.parameters.wheelbase`.
- Use conventional commit messages (`refactor:`, `test:`, `docs:`).

## Review Focus

- **Unbound inputs:** `KinematicVehicle` must not be simulated directly after
  the refactor; its inputs are only bound by the wrapper.
- **Initialization:** zero initial equations in `KinematicVehicle` must survive
  component instantiation in the wrapper; do not also add fixed starts to the
  interface.
- **Parameter wiring:** `wheelbase` must reach `KinematicVehicle` through the
  wrapper modification; a Python override that only reaches the wrapper is not
  enough.
- **Signal names:** tests must use the actual wrapper-prefixed columns; old
  `state.*`, `control.*`, and unprefixed derivative names must not remain.
- **Reference parity:** the reference package must expose the same signal set
  and use the same parameter names, or the comparison fails before values are
  checked.

## File Structure

**Create**

- `examples/src/kinematic_vehicle/IKinematicVehicle.mo` — shared input/output
  contract for the example.
- `examples/src/kinematic_vehicle/WrapperKinematicVehicle.mo` — simulated block
  that parameterizes one `KinematicVehicle` component.
- `examples/tests/reference_models/IKinematicVehicle.mo` — reference-side
  contract.
- `examples/tests/reference_models/WrapperKinematicVehicle.mo` — reference-side
  standalone block.

**Modify**

- `examples/src/kinematic_vehicle/KinematicVehicle.mo` — inherit the interface,
  own `wheelbase`, equations, protected derivatives, and initial equations.
- `examples/src/kinematic_vehicle/kinematic_vehicle.py` — new model name,
  parameter dataclass, experiments, and removed state group.
- `examples/tests/test_kinematic_vehicle.py` — wrapper signal names, wheelbase
  sweep, and config assertions.
- `examples/tests/reference_models/KinematicVehicle.mo` — mirror the candidate
  implementation.
- `examples/tests/reference_models/kinematic_vehicle.py` — reference model name.
- `examples/README.md` — structure, commands, signal names, and reference
  description.

**Delete**

- `examples/src/kinematic_vehicle/State.mo`
- `examples/src/kinematic_vehicle/Input.mo`
- `examples/tests/reference_models/State.mo`
- `examples/tests/reference_models/Input.mo`

## Tasks

### Task 1: Candidate interface, implementation, wrapper, and Python config

**Files**

- Create: `examples/src/kinematic_vehicle/IKinematicVehicle.mo`
- Create: `examples/src/kinematic_vehicle/WrapperKinematicVehicle.mo`
- Modify: `examples/src/kinematic_vehicle/KinematicVehicle.mo`
- Modify: `examples/src/kinematic_vehicle/kinematic_vehicle.py`
- Modify/Test: `examples/tests/test_kinematic_vehicle.py`
- Delete: `examples/src/kinematic_vehicle/State.mo`,
  `examples/src/kinematic_vehicle/Input.mo`

**Interfaces**

- Consumes: nothing from earlier tasks.
- Produces:
  - `partial model IKinematicVehicle` with `input Real v_norm`,
    `input Real phi`, `output Real px`, `output Real py`,
    `output Real theta`.
  - `model KinematicVehicle extends IKinematicVehicle` with
    `parameter Real wheelbase = 2`, protected `Real px_dot`, `Real py_dot`,
    `Real theta_dot`, and zero initial equations.
  - `block WrapperKinematicVehicle` with `parameter Real v_norm = 10`,
    `parameter Real phi = 0.1`, `parameter Real wheelbase = 2`, and component
    `KinematicVehicle vehicle(wheelbase=wheelbase)`.
  - Python `WrapperKinematicVehicle` dataclass with `v_norm: float = 10.0`,
    `phi: float = 0.0`, `wheelbase: float = 2.0`; `vehicle_default`,
    experiment overrides, and `run_default` all use it.
  - `MODEL_NAME = "kinematic_vehicle.WrapperKinematicVehicle"`.

**Steps**

1. In `examples/tests/test_kinematic_vehicle.py`, rewrite the signal accesses:

   - `TestStandstill.test_position_unchanged`: use `vehicle.px`, `vehicle.py`,
     `vehicle.theta`.
   - `TestStandstill.test_protected_columns_hidden_by_default`: assert
     `vehicle.px_dot`, `vehicle.py_dot`, `vehicle.theta_dot` are absent.
   - `TestStraightDriving`: set
     `sweep_params: ClassVar[dict[str, list[SweepValue]]] = {"v_norm": [5, 10]}`;
     use `vehicle.px`, `der(vehicle.px)`, `vehicle.py`, `vehicle.theta`.
   - `TestTurnLeft`: use `vehicle.theta`, `vehicle.px`, `vehicle.py`.
   - `TestVelocityIncrease`: use `der(vehicle.px)`.
   - `TestProtectedOutput`: assert `vehicle.px_dot`, `vehicle.py_dot`, and
     `vehicle.theta_dot` are present, then compare each protected derivative
     with its `der(...)` counterpart:

     ```python
     for name, state in (("px", "vehicle.px"), ("py", "vehicle.py"), ("theta", "vehicle.theta")):
         np.testing.assert_allclose(self.results[f"vehicle.{name}_dot"], self.results[f"der({state})"])
     ```

2. Add a wheelbase simulation test after `TestTurnLeft`:

   ```python
   class TestWheelbase(ExperimentSweep):

       name = "turn_left"
       sweep_params: ClassVar[dict[str, list[SweepValue]]] = {"wheelbase": [2.0, 4.0]}

       def test_longer_wheelbase_turns_slower(self):
           short = self.results[(2.0,)]
           long = self.results[(4.0,)]
           assert abs(long["vehicle.theta"].iloc[-1]) < abs(short["vehicle.theta"].iloc[-1])
   ```

3. Extend `test_example_builds_and_solves_with_cpp_target` with:

   ```python
   assert config.model_name == "kinematic_vehicle.WrapperKinematicVehicle"
   assert config.session.parameters.v_norm == 10.0
   assert config.session.parameters.phi == 0.0
   assert config.session.parameters.wheelbase == 2.0
   ```

4. Run `cd examples && uv run pytest tests/test_kinematic_vehicle.py`. Expect
   failures at simulation/config composition because the model and registry do
   not provide the new names yet.

5. Create `examples/src/kinematic_vehicle/IKinematicVehicle.mo`:

   ```modelica
   within kinematic_vehicle;

   partial model IKinematicVehicle
     input Real v_norm "velocity";
     input Real phi "steering angle";
     output Real px "x position";
     output Real py "y position";
     output Real theta "heading angle";
   end IKinematicVehicle;
   ```

6. Replace `examples/src/kinematic_vehicle/KinematicVehicle.mo` with:

   ```modelica
   within kinematic_vehicle;

   model KinematicVehicle
     extends IKinematicVehicle;
     parameter Real wheelbase = 2 "wheelbase";

   protected
     Real px_dot = der(px);
     Real py_dot = der(py);
     Real theta_dot = der(theta);

   equation
     px_dot = v_norm * cos(theta);
     py_dot = v_norm * sin(theta);
     theta_dot = v_norm / wheelbase * tan(phi);

   initial equation
     px = 0;
     py = 0;
     theta = 0;
   end KinematicVehicle;
   ```

7. Create `examples/src/kinematic_vehicle/WrapperKinematicVehicle.mo`:

   ```modelica
   within kinematic_vehicle;

   block WrapperKinematicVehicle
     parameter Real v_norm = 10 "velocity";
     parameter Real phi = 0.1 "steering angle";
     parameter Real wheelbase = 2 "wheelbase";

     KinematicVehicle vehicle(wheelbase=wheelbase);

   equation
     vehicle.v_norm = v_norm;
     vehicle.phi = phi;
   end WrapperKinematicVehicle;
   ```

8. Delete `examples/src/kinematic_vehicle/State.mo` and
   `examples/src/kinematic_vehicle/Input.mo`.

9. In `examples/src/kinematic_vehicle/kinematic_vehicle.py`, make the wrapper
   the only model entry point:

   - Set `MODEL_NAME = "kinematic_vehicle.WrapperKinematicVehicle"`.
   - Ensure `run_default = registry.create_run(model_name=MODEL_NAME, ...)`,
     so every run config composes the wrapper. No Python value may remain
     `kinematic_vehicle.KinematicVehicle`; the bare implementation name is
     only used as the wrapper's internal component type.
   - Replace the `State` dataclass and old `KinematicVehicle` dataclass with:

     ```python
     @dataclasses.dataclass
     class WrapperKinematicVehicle:
         v_norm: float = 10.0
         phi: float = 0.0
         wheelbase: float = 2.0
     ```

   - Set `vehicle_default = WrapperKinematicVehicle()`.
   - Remove `registry.register_group_name("session.parameters.state_0", ...)`
     and `registry.register_group_options("parameters/state_0", ...)`.
   - Remove the `front_position` experiment.
   - Keep `standstill`, `straight_driving`, `turn_left`, and
     `protected_output`; build their overrides with
     `WrapperKinematicVehicle(v_norm=..., phi=..., wheelbase=2.0)`.
   - Keep `simulation_default`, `run_default`, `registry.add_to_hydra_store()`,
     and `__all__` unchanged except for the dataclass name if re-exported.

10. Run `cd examples && uv run pytest tests/test_kinematic_vehicle.py`. Expect
    all tests, including `TestWheelbase`, to pass.

11. Commit:

    ```
    refactor: split the kinematic vehicle into interface, implementation, and wrapper
    ```

### Task 2: Port the reference package and keep comparison green

**Files**

- Create: `examples/tests/reference_models/IKinematicVehicle.mo`
- Create: `examples/tests/reference_models/WrapperKinematicVehicle.mo`
- Modify: `examples/tests/reference_models/KinematicVehicle.mo`
- Modify: `examples/tests/reference_models/kinematic_vehicle.py`
- Delete: `examples/tests/reference_models/State.mo`,
  `examples/tests/reference_models/Input.mo`

**Interfaces**

- Consumes: the parameter dataclass and registry from Task 1.
- Produces: `reference_models.WrapperKinematicVehicle` with the same
  `v_norm`, `phi`, `wheelbase`, `vehicle.*` signal names, equations, and zero
  initial state as the candidate.

**Steps**

1. Create `examples/tests/reference_models/IKinematicVehicle.mo` with the same
   contract as Task 1, under `within reference_models;`.

2. Replace `examples/tests/reference_models/KinematicVehicle.mo` with the same
   implementation as Task 1, under `within reference_models;`, including
   `extends IKinematicVehicle`, `parameter Real wheelbase = 2`, protected
   derivatives, equations, and zero initial equations.

3. Create `examples/tests/reference_models/WrapperKinematicVehicle.mo` with the
   same block interface and `vehicle` component as Task 1, under
   `within reference_models;`.

4. Delete `examples/tests/reference_models/State.mo` and
   `examples/tests/reference_models/Input.mo`.

5. In `examples/tests/reference_models/kinematic_vehicle.py`, set
   `REFERENCE_MODEL_NAME = "reference_models.WrapperKinematicVehicle"`.

6. Run `cd examples && uv run pytest tests/test_reference_comparison.py`.
   Expect `TestStandstillReference` and `TestTurnLeftReference` to pass with
   matching signal sets and values.

7. Commit:

   ```
   test: port the reference kinematic vehicle to the interface structure
   ```

### Task 3: Update the example documentation, CI commands, and import order

**Files**

- Modify: `examples/README.md`
- Modify: `.github/workflows/tests.yml`
- Modify: `examples/src/kinematic_vehicle/__main__.py`

**Interfaces**

- Consumes: model names, parameter names, and signal names from Tasks 1-2.
- Produces: documentation and CI commands that match the refactored example,
  and an import order that passes the repository-level isort check.

**Steps**

1. Update the project-structure tree to show `IKinematicVehicle.mo`,
   `KinematicVehicle.mo`, and `WrapperKinematicVehicle.mo` in both packages and
   to omit `State.mo` and `Input.mo`.

2. Update the introduction and default-run description to name
   `WrapperKinematicVehicle`, the `vehicle.*` signal path, parameters
   `v_norm`, `phi`, and `wheelbase`, and the zero initial state.

3. Replace the `parameters/state_0=front_position` config-group section and the
   `experiment=front_position` section with direct parameter overrides, for
   example:

   ```bash
   uv run python -m kinematic_vehicle session.parameters.phi=0.1
   uv run python -m kinematic_vehicle session.parameters.wheelbase=3.0
   ```

4. Keep the experiment override example (`experiment=turn_left`) and the
   parameter-sweep example (`-m session.parameters.v_norm=10,20`). Mention that
   `wheelbase` is sweepable too.

5. Update the protected-output test description to
   `vehicle.px_dot`, `vehicle.py_dot`, and `vehicle.theta_dot`.

6. Update the reference-comparison description to the refactored
   `reference_models.WrapperKinematicVehicle` structure.

7. In `.github/workflows/tests.yml`, replace the two removed commands in the
   `Run examples` step with valid refactored commands. Keep the default run and
   the parameter sweep; use `experiment=turn_left` for the experiment example:

   ```bash
   uv run python -m kinematic_vehicle
   uv run python -m kinematic_vehicle session.parameters.phi=0.1
   uv run python -m kinematic_vehicle experiment=turn_left
   uv run python -m kinematic_vehicle -m session.parameters.v_norm=10,20
   ```

8. In `examples/src/kinematic_vehicle/__main__.py`, reorder the imports so the
   repository-level isort check passes. Do not change behavior.

9. Run verification from `examples/`:

   ```bash
   uv run pytest tests
   ```

   Expect all example tests to pass, including the reference comparison.

10. Run repository-level checks from the repository root:

    ```bash
    uv run pytest tests
    uv run mypy src tests
    uv run isort --check-only src tests examples
    ```

    Expect the main suite and both static checks to pass; the main suite is
    unchanged but guards against accidental cross-package edits.

11. Commit:

    ```
    docs: describe the interface-based kinematic vehicle example
    ```

## Self-review

- **Spec coverage:** every spec section maps to a task: interface and
  implementation (Task 1, steps 5-6), wrapper (Task 1, step 7), removed records
  (Task 1, step 8), Python config (Task 1, step 9), tests (Task 1, steps 1-4 and
  10), reference package (Task 2), README, CI commands, and import order
  (Task 3).
- **Step scan:** each step names one file or one command and one expected
  result; the long Modelica snippets are exact interface decisions, not
  line-by-line algorithm narration.
- **Type consistency:** `WrapperKinematicVehicle`, `wheelbase`, `MODEL_NAME`,
  `REFERENCE_MODEL_NAME`, and the `vehicle.*` signal names are used identically
  across tasks and tests.
- **Review Focus:** each failure mode has a test: unbound inputs fail the
  wrapper simulation/config test, initialization is covered by standstill,
  parameter wiring by `TestWheelbase`, signal names by every experiment, and
  reference parity by Task 2's comparison run.
- **Proportion:** the plan is shorter than the code it describes and defers
  algorithm bodies to the model equations already fixed by the spec.

## Execution handoff

This is one coherent slice: Modelica files, Python registry, tests, reference
package, and docs must change together for the suite to stay green. It is small
enough for a single sequential implementer and does not need a ticket graph.
Recommended execution mode: single-session sequential implementation with the
test cycle per task above. Wait for approval of this plan before editing the
model.