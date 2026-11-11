# Why CVODE reports "tout too close" on OMC-exported FMUs

Date: 2026-11-11
Sources:
- FMPy source at tag [`v0.3.32`](https://github.com/CATIA-Systems/FMPy/tree/v0.3.32): `simulation.py` and `sundials/__init__.py`. Also [`v0.3.29`](https://github.com/CATIA-Systems/FMPy/tree/v0.3.29) `simulation.py`, the v0.3.30–v0.3.32 release notes, [PR #870](https://github.com/CATIA-Systems/FMPy/pull/870) and [issue #882](https://github.com/CATIA-Systems/FMPy/issues/882).
- SUNDIALS [`v7.5.0`](https://github.com/LLNL/sundials/tree/v7.5.0) `src/cvode/cvode.c` and the CVODE usage guide. FMPy 0.3.32 bundles 7.5.0, as its error path shows.
- SUNDIALS 5.4.0 as vendored by OMC in [OMCompiler-3rdParty `dfc66f9`](https://github.com/OpenModelica/OMCompiler-3rdParty/tree/dfc66f9ee9ab081c79a33bcb208e3b307f48f16f/sundials-5.4.0). The CS FMU ships `libsundials_cvode.so.5.4.0`.
- OpenModelica source at tag [`v1.27.2`](https://github.com/OpenModelica/OpenModelica/tree/v1.27.2) (commit `4f2b2b1`): the FMI 2.0 export runtime `fmu2_model_interface.c`, plus `cvode_solver.c`, `events.c`, `epsilon.h`, `model_help.c` and `initialization.c`. The `fmu2_model_interface.c` inside the exported FMUs matches the tag except for the generated `#include` line.

Observed with OpenModelica 1.27.2 (`omc`), FMPy 0.3.32 and 0.3.29 on Python 3.11.18 (`uv run --no-project --python 3.11 --with fmpy==…`), Debian 13 x86_64.

Prior work: [What OMC's FMU export gives mtools](https://github.com/phdorp/modelica-tools/blob/research/omc-fmu-export/docs/research/2026-11-10-omc-fmu-export.md) ("Other observations") measured the failures and guessed at a cause without confirming it. [FMPy as a simulator for reference-model comparison tests](https://github.com/phdorp/modelica-tools/blob/research/fmpy-reference-comparison/docs/research/2026-11-09-fmpy-reference-comparison.md) mentions #882.

## Question

From [#82](https://github.com/phdorp/modelica-tools/issues/82): OMC-exported Model Exchange FMUs fail under FMPy's CVODE with "tout too close" when a `sample()` event lands on the output grid.

1. What exactly triggers it: FMPy's ME loop, the event time, or the output interval?
2. Does it also hit Co-Simulation FMUs on the communication grid?
3. Does it hit FMPy's `Euler` solver?
4. Which measures avoid it? Candidates: interval choice, FMPy options, OMC export flags, a patched stepping loop, upstream fixes.
5. Is native OMC simulation of the same model affected?

## Method

1. Read FMPy 0.3.32's ME and CS loops and its CVODE wrapper. Read SUNDIALS' `CVode`/`cvHin` code paths that return `CV_TOO_CLOSE`. Read OMC 1.27.2's FMI 2.0 runtime: sample activation, `fmi2NewDiscreteStates`, `fmi2DoStep` and the CS CVODE step. Read the native solver's sample handling.
2. Exported three probe models as FMI 2.0 FMUs in three variants each: ME, CS with Euler (the default), and CS with `--fmiFlags=s:cvode`:
   - `S1`: `when sample(0.1, 0.1)`
   - `S2`: `when sample(0.05, 0.07)`
   - `S3`: `sample(0.1, 0.1)` plus `sample(0.3, 0.3)`

   Each has `der(x) = -x`, stop time 1. The models are in [Reproduction](#reproduction).
3. Wrapped FMPy's `CVodeSolver.step`/`reset`, `FMU2Model.newDiscreteStates` and `FMU2Slave.doStep` to log the exact float times.
4. Wrote a predictor (`predict.py`, no FMU). It replays FMPy's grid arithmetic and OMC's sample arithmetic and applies `cvHin`'s too-close rule. It names the failure time for any `(sample start, sample interval, output interval)`. It was compared with real runs over 30 intervals per model and mode: 0.001–0.25, including binary-exact ones such as 1/64.
5. Tried each candidate avoidance against the same sweep, and ran the same models natively with `simulate()`.

**(verified)** means read in source or measured here. **(inference)** means my reasoning from verified pieces.

## Short answer

1. **Trigger (verified).** Two float roundings of the same decimal time disagree by one ulp, and CVODE refuses a first step that short after a re-init.
   - OMC's FMU accumulates sample times: `nextSampleTimes[i] += interval`, so the 3rd tick of `sample(0.1, 0.1)` is `0.30000000000000004`.
   - OMC fires a sample only if `nextSampleTime <= time`, with no tolerance.
   - FMPy computes output points as `start + k·h`, so `30·0.01 = 0.3`, and treats times as equal when `math.isclose` holds (relative tolerance 1e-9).
   - **ME:** FMPy integrates to the output point 0.3 and calls an event there, but the FMU does not fire because 0.30000000000000004 > 0.3. FMPy then re-initialises CVODE (unconditionally since 0.3.30, [PR #870](https://github.com/CATIA-Systems/FMPy/pull/870)) and asks it to integrate from 0.3 to 0.30000000000000004. `cvHin` returns `CV_TOO_CLOSE` (−27) because the distance is below `2·DBL_EPSILON·max(|t0|,|tout|)`.
   - **When it fires:** an output point lies 1–2 ulps *below* a sample time. An event below or equal to the grid point is harmless in ME.
   - **Why 0.05 and 0.0125 pass for `S1`:** at both, every `S1` tick is equal to or below its grid point (table in section 1).
   - **The guessed cause was partly wrong.** The first ME failure is at 0.3, not 0.6, and it needs the grid point *below* the event. The "6·0.1 = 0.6000000000000001" mechanism is the CS failure (point 2).
   - The predictor matched every one of the 780 runs listed under "Key numbers" (after two corrections, see [Method notes](#method-notes)).
2. **CS (verified).** CS FMUs with embedded CVODE fail too, and more often.
   - In OMC's `fmi2DoStep`, an event slightly *before* the step end is integrated to, handled, and followed by a re-init. The remaining sub-ulp step `tEnd − e` then fails the same check.
   - `S1` CS+CVODE failed at all 30 step sizes. The last tick is `0.9999999999999999` against stop time 1.0, so every step size whose grid ends at 1.0 trips there if not earlier.
   - `S2` failed at 2/30.
   - CS FMUs with the default Euler never failed (60/60).
3. **Euler (verified).** FMPy's ME `Euler` never failed (60/60), and `sample()` counters were correct. In 0.3.32, `step_size` does not change Euler's step: it steps once per output interval. `x(1)` is identical for `step_size` 0.1 and 0.001 at output interval 0.1.
4. **Avoidances (verified unless marked).**
   - **Output-interval choice works only per model.** It depends on where OMC's accumulated tick times fall. Binary-exact intervals do not help: `S2` fails at 0.25 and 1/64. Longer runs get worse: with stop time 10, `S1` failed at 0.0125, 0.05 and 0.1.
   - **FMPy options do not help.** `relative_tolerance`, `step_size`, `record_events=False` and `step_finished` all still fail. Shifting `start_time` by 1e-9 avoided it in the two cases tried, but it changes the experiment.
   - **There is no OMC export flag for it.** FMU sample activation has no tolerance.
   - **What works on all 90 sweep cases each (`S1`–`S3`):**
     - FMPy **0.3.29** (before PR #870).
     - A patch that resets CVODE only when the FMU reports changed continuous states (as in the #882 comment).
     - A patch that skips zero-length solver calls. As a ~10-line runtime wrapper around `fmpy.sundials.CVodeSolver.step`, no copy of FMPy is needed.
   - **Snapping the output point to the FMU's event time fixes `S1`/`S2` but not `S3`.** In `S3` two sample clocks drift 1 ulp apart.
   - **No upstream fix exists.** 0.3.32 is the latest FMPy release and `main` has no commits after it. #882 is open.
5. **Native OMC (verified).** Unaffected: 8 runs passed, including CVODE at intervals 0.01, 0.03 and 0.25, with correct counters. The native solver treats sample times within `SAMPLE_EPS = 1e-14` as reached. The FMU runtime has no such tolerance.

## Findings

### 1. The ME trigger

**FMPy's ME loop (verified).**
- Each iteration's output point is `next_regular_point = start_time + (n_steps + 1) * output_interval` ([`simulation.py` L1093](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1093)).
- The point is clamped to the FMU's `next_event_time` only if it is later *and not* `isclose` to it ([L1102-L1103](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1102-L1103)).
- A time event is declared when the two are `isclose` ([L1110](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1110)). `isclose` is `math.isclose` with its defaults, relative tolerance 1e-9 ([L4](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L4)).
- The solver integrates to that point ([L1112](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1112)). On any event, FMPy calls `enterEventMode`, iterates `newDiscreteStates` and takes the new `next_event_time` ([L1160-L1180](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1160-L1180)).
- FMPy then calls `solver.reset(time)` unconditionally ([L1204](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1204)). That is `CVodeReInit` ([`sundials/__init__.py` L189-L197](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/sundials/__init__.py#L189-L197)).
- In 0.3.29 the reset was conditional on `nominals_of_continuous_states_changed or values_of_continuous_states_changed` ([v0.3.29 L1127](https://github.com/CATIA-Systems/FMPy/blob/v0.3.29/src/fmpy/simulation.py#L1127), [L1168](https://github.com/CATIA-Systems/FMPy/blob/v0.3.29/src/fmpy/simulation.py#L1168), [L1199-L1200](https://github.com/CATIA-Systems/FMPy/blob/v0.3.29/src/fmpy/simulation.py#L1199-L1200)). The change is [PR #870](https://github.com/CATIA-Systems/FMPy/pull/870) "Always reset solver after event", released in [v0.3.30](https://github.com/CATIA-Systems/FMPy/releases/tag/v0.3.30).

**OMC's FMU (verified).**
- At initialisation, a sample's next time is its `start` ([`initialization.c` L757-L766](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/simulation/solver/initialization/initialization.c#L757-L766)).
- In `internalEventUpdate`, which `fmi2NewDiscreteStates` calls, a sample fires only if `nextSampleTimes[i] <= time`, with no tolerance. A fired sample advances by repeated addition, `nextSampleTimes[i] += interval` ([`fmu2_model_interface.c` L296-L316](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu2_model_interface.c#L296-L316)).
- The minimum over all samples is returned as `nextEventTime` ([L349-L355](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu2_model_interface.c#L349-L355)).
- So the tick times are rounded sums: `S1` ticks at 0.1, 0.2, **0.30000000000000004**, 0.4, 0.5, 0.6, 0.7, **0.7999999999999999**, **0.8999999999999999**, **0.9999999999999999**.
- `S2`'s 11th tick is 0.05 + 10 additions of 0.07 = **0.7500000000000002**.
- OMC `master` (at `ed5c2a659e`, 2026-11-11) still uses the exact `<=` in the shared C interface ([`fmu_model_interface.c.inc` L952-L959](https://github.com/OpenModelica/OpenModelica/blob/ed5c2a659e/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu_model_interface.c.inc#L952-L959)). Its new Rust runtime advances samples with an `advance_sample(next, start, interval)` helper, not inspected here.

**SUNDIALS (verified).**
- On the first `CVode` call after `CVodeInit`/`CVodeReInit` (`nst == 0`) with no initial step set, CVODE calls `cvHin` ([`cvode.c` L1119](https://github.com/LLNL/sundials/blob/v7.5.0/src/cvode/cvode.c#L1119), [L1175-L1190](https://github.com/LLNL/sundials/blob/v7.5.0/src/cvode/cvode.c#L1175-L1190)).
- `cvHin` returns `CV_TOO_CLOSE` if `tout == tn` or `|tout − tn| < 2·uround·max(|tn|, |tout|)`, with `uround = DBL_EPSILON` ([L2161-L2176](https://github.com/LLNL/sundials/blob/v7.5.0/src/cvode/cvode.c#L2161-L2176)). The same test is in OMC's 5.4.0 copy ([`cvode.c` L1906-L1921](https://github.com/OpenModelica/OMCompiler-3rdParty/blob/dfc66f9ee9ab081c79a33bcb208e3b307f48f16f/sundials-5.4.0/src/cvode/cvode.c#L1906-L1921)).
- The guide documents −27 as "The initial time t0 and the output time tout are too close to each other and the user did not specify an initial step size" ([CVODE usage guide, `CVode` return values](https://github.com/LLNL/sundials/blob/v7.5.0/doc/cvode/guide/source/Usage/index.rst?plain=1#L754)).
- At t ≈ 0.3 one ulp is 5.6e-17 and the limit is 1.3e-16. At t ≈ 0.6–1 one ulp is 1.1e-16 and the limit is 2.2e-16 to 4.4e-16. One-ulp gaps always fail, two-ulp gaps sometimes.
- FMPy never sets an initial step (`CVodeSetInitStep` is not even bound in [`sundials/cvode.py` L155](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/sundials/cvode.py#L155)).

**The sequence (measured, `S1` ME, interval 0.01; the 0.03 run is identical from 0.3 on):**

```text
cvode.step t=0.29 tout=0.3 diff=1.000e-02
  newDiscreteStates -> nextEventTimeDefined=True nextEventTime=0.30000000000000004   # FMU did not fire at 0.3
cvode.reset t=0.3
cvode.step t=0.3 tout=0.30000000000000004 diff=5.551e-17
RuntimeError: CVode error (code -27) in module cvHandleFailure … tout too close to t0 to start integration.
```

**The rule (verified by the predictor against every run).** FMPy ≥ 0.3.30 ME CVode fails at the first output point `g` with `g < e` and `e − g < 2·ε·max(|g|,|e|)` for some FMU time event `e`.
- If `g ≥ e` and they are `isclose`, FMPy steps to `g` and the FMU fires there, since `e <= g`.
- If `e − g` is larger than about 2 ulps (but still `isclose`), CVODE takes the tiny step.

Event-minus-grid offsets for `S1` (0 = equal; `.` = no grid point near the tick; positive = event just after the grid point, which fails):

| interval | 0.1 | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | 1.0 | ME CVode |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.01 | 0 | 0 | **+5.6e-17** | 0 | 0 | 0 | −1.1e-16 | −1.1e-16 | −1.1e-16 | −1.1e-16 | fails at 0.3 |
| 0.03 | . | . | **+5.6e-17** | . | . | 0 | . | . | 0 | . | fails at 0.3 |
| 0.05 | 0 | 0 | 0 | 0 | 0 | −1.1e-16 | −1.1e-16 | −1.1e-16 | −1.1e-16 | −1.1e-16 | passes |
| 0.0125 | 0 | 0 | 0 | 0 | 0 | −1.1e-16 | −1.1e-16 | −1.1e-16 | −1.1e-16 | −1.1e-16 | passes |
| 0.1 | 0 | 0 | 0 | 0 | 0 | −1.1e-16 | −1.1e-16 | −1.1e-16 | −1.1e-16 | −1.1e-16 | passes |

`S1` passes at 0.05 and 0.0125 because `6·0.05 = 24·0.0125 = 0.30000000000000004` matches OMC's sum. Later ticks fall below their grid points, and ME tolerates that.

**Sweep of ME CVode, FMPy 0.3.32 (measured, 30 intervals each):**

| Model | Fails | Failing intervals | Failure time |
|---|---|---|---|
| `S1` `sample(0.1,0.1)` | 12/30 | 0.001 0.002 0.0025 0.003 0.004 0.005 0.006 0.01 0.015 0.02 0.03 0.06 | 0.3 → 0.30000000000000004 |
| `S2` `sample(0.05,0.07)` | 23/30 | all except 0.007 0.035 0.07 0.08 0.09 0.1 0.2. Binary-exact 0.25, 0.125, 1/64, 1/32 and 1/128 fail too | 0.12, 0.54 or 0.75 |
| `S3` two samples | 26/30 | all except 0.0125 0.025 0.05 0.1 | 0.3 → 0.30000000000000004 |

- **`S3` (verified).** The `sample(0.3, 0.3)` clock fires at 0.3, and the first clock's tick at 0.30000000000000004 is then 1 ulp later. FMPy's `isclose` then makes it the next communication point after a reset. Here two sample clocks inside the FMU disagree, so the grid barely matters. It passes only where a grid point equals 0.30000000000000004 and both fire together.
- **Longer runs (measured).** `S1` with `stop_time=10` failed at intervals 0.05, 0.1 and 0.0125, all at `1.5 → 1.5000000000000002`. The predictor gives 0/30 passing intervals for `S1` at stop time 10 (predicted only).

### 2. Co-Simulation FMUs

**FMPy's CS loop (verified).** It calls `doStep(time, next − time)` with `next = start + (n+1)·h`, clamped to `stop_time` for FMUs that can vary the step ([L1289-L1310](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1289-L1310), [L1327-L1329](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1327-L1329)). OMC's CS FMUs declare `canHandleVariableCommunicationStepSize="true"` (measured).

**OMC's `fmi2DoStep` (verified).**
- It computes `tEnd = currentCommunicationPoint + communicationStepSize` ([L2269](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu2_model_interface.c#L2269)).
- It loops while `time < tEnd`, integrating to `nextEventTime` if that is `<= tEnd` ([L2288](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu2_model_interface.c#L2288), [L2323-L2332](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu2_model_interface.c#L2323-L2332)). After an event it sets `didEventStep = 1` ([L2411-L2449](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu2_model_interface.c#L2411-L2449)).
- `cvode_solver_fmi_step` then re-inits CVODE, sets the stop time and calls `CVode` ([`cvode_solver.c` L1020-L1043](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/simulation/solver/cvode_solver.c#L1020-L1043)).
- The local `time_event` flag is set at [L2327](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu2_model_interface.c#L2327) and never cleared inside the loop. Every sub-step after a time event in the same `doStep` is treated as an event step, so the next `doStep` also starts with a re-init.

**Two failure shapes (measured):**
- **Event just before `tEnd`.** At step 0.1, the step 0.5 → 0.6000000000000001 contains the tick at 0.6. CVODE integrates to 0.6, the event fires, CVODE re-inits, and 0.6 → 0.6000000000000001 fails. The FMU logs `fmi2DoStep: ##CVODE## -27 error occurred at time = 0.6.` This is the earlier note's case.
- **Event just after a communication point, with a re-init pending.** `S2` at 0.125/0.25: the step ending at 0.75 contained the tick at 0.68, so the next `doStep` re-inits. The tick at 0.7500000000000002 is then 1 ulp ahead.

**Sweep, CS FMUs, FMPy 0.3.32 (measured, 30 step sizes each):**

| FMU | `S1` | `S2` |
|---|---|---|
| CS + CVODE (`--fmiFlags=s:cvode`) | **30/30 fail**, at 0.6, 0.7, 0.8, 0.9 or 1.0 | 2/30 fail (0.125, 0.25), at 0.75 |
| CS + Euler (default) | 0/30 fail, `cnt` = 10 | 0/30 fail, `cnt` = 14 |

`S1` CS+CVODE cannot pass with stop time 1: the last tick `0.9999999999999999` sits 1 ulp before the final `tEnd = 1.0`. The predictor gives 5/30 passing with stop 1.05 and 2/30 with stop 10 (predicted only). Euler integrates any step length, so no CS Euler step fails.

### 3. FMPy's ME `Euler`

**Verified.** `ForwardEuler.step` does one explicit step of `tNext − t`, however small ([`simulation.py` L590-L616](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L590-L616)). Its `reset` does nothing.

**Measured.** 0/60 failures across `S1`/`S2`, with correct counters. With `output_interval=0.01, solver="Euler"`, `S1` gives `x(1) = 0.3660323412732296`, where the exact value is 0.36788.

**`step_size` has no effect on the Euler step in 0.3.32.**
- The ME loop advances on the output grid ([L1093](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1093)).
- `step_size` is only checked to divide the output interval ([L1067-L1068](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1067-L1068)).
- Measured: `S1` with output 0.1 gives `x(1) = 0.3486784401000001` = 0.9¹⁰ for both `step_size=0.1` and `step_size=0.001`.
- Euler accuracy is therefore set by the output interval.

### 4. Avoidances

| Measure | Works? | Evidence |
|---|---|---|
| Pick the output interval | Only per model and horizon | Depends on OMC's accumulated tick times (section 1). `S2` fails at binary-exact intervals. `S1` passes at 18/30 intervals with stop time 1 but failed at all three tried (0.0125, 0.05, 0.1) with stop time 10. Tick times are not in `modelDescription.xml`. |
| `relative_tolerance` 1e-3 / 1e-10 | No | Measured, `S1` and `S2` at 0.01. `cvHin`'s check does not depend on tolerances. |
| `step_size` (CVode) | No | Measured. Overwritten with `output_interval` for CVode ([L1061](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1061)). |
| `record_events=False` | No | Measured. Recording only. |
| `step_finished` callback | No | Measured. Called after the step ([L1206](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1206)) and cannot change the next time. |
| `start_time=1e-9` (shift the grid off the ticks) | Passed `S1`, `S2` at 0.01 | Measured. It changes the experiment's start time and offsets all output times. **(inference)** It works because the shift (1e-9) is far larger than the ulp drift and far smaller than the interval. That has to hold for every model and horizon. |
| `solver="Euler"` (ME) or the CS Euler FMU | Yes, 0/120 failures | Measured. Explicit Euler at the output/communication step, so accuracy is limited. |
| OMC export flags | None found | **(verified)** FMU sample activation has no tolerance (section 1). The earlier note found `--fmiFlags` understands only `s` (solver). |
| Pin FMPy **0.3.29** | Yes, 90/90 (`S1`–`S3`, ME CVode) | Measured. **(verified)** OMC's FMU reports `valuesOfContinuousStatesChanged=False` (and `newDiscreteStatesNeeded=False`) even when a sample fires, so 0.3.29 never re-inits CVODE after these events. The cost is losing 0.3.30–0.3.32 changes ([v0.3.30](https://github.com/CATIA-Systems/FMPy/releases/tag/v0.3.30), [v0.3.31](https://github.com/CATIA-Systems/FMPy/releases/tag/v0.3.31), [v0.3.32](https://github.com/CATIA-Systems/FMPy/releases/tag/v0.3.32)). PR #870 has no description of what always-reset fixed. |
| Patch P1: conditional reset (the #882 comment's patch) | Yes, 90/90 | Measured: 0.3.32 copy, 6-line diff. For models whose events change continuous states (`reinit`), it still resets. **(inference, not tested)** Two ticks 1 ulp apart could still fail then. |
| Patch P2: step to the FMU's event time when `isclose` | `S1`, `S2` yes; **`S3` 0/30** | Measured, 3-line diff. Does not cover two sample clocks drifting apart. |
| Patch P3: skip the solver call when `isclose(time, next)` | Yes, 90/90 | Measured, 4-line diff in `simulateME`. Also 90/90 as a runtime wrapper (below). `stop_time=10`, interval 0.05: passes, `cnt=100`. |
| `CVodeSetInitStep` after each reset | Not tested | The guide says −27 only occurs when no initial step is given. FMPy has no binding for it. |
| Upstream FMPy fix | None released | 0.3.32 (2026-09-09) is the latest on PyPI. `main` is not ahead of `v0.3.32` (GitHub compare, 2026-11-11). [#882](https://github.com/CATIA-Systems/FMPy/issues/882) (opened 2026-07-07) is open. It names PR #870 as the cause and has a proposed patch in a comment. A 2026-10-12 comment reports another FMU with the same error. |

**P3 as a runtime wrapper (measured, 90/90).** It needs no copy of FMPy. It relies on the private `fmpy.sundials.CVodeSolver.step(t, tNext) -> (state_event, roots, time)` signature, which `simulateME` imports at call time ([L1054](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1054)):

```python
import math
import numpy as np
import fmpy.sundials as sund

_step = sund.CVodeSolver.step

def _guarded_step(self, t, tNext):
    if math.isclose(t, tNext):  # zero-length step: nothing to integrate
        return False, np.zeros(self.nz, dtype=np.int32), tNext
    return _step(self, t, tNext)

sund.CVodeSolver.step = _guarded_step
```

**Own loop (inference).**
- An importer-side fix as a full own ME loop means copying `simulateME` ([L928-L1213](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L928-L1213), about 285 lines with input, recording and FMI 1/2/3 branches) and changing 3–6 lines (P1/P2/P3).
- The wrapper above changes about 10 lines but couples to a private class.
- None of these fixes CS+CVODE. That failure is inside the FMU's `fmi2DoStep` and FMI 2.0 CS gives the importer no event times. Only step choice, the Euler CS FMU, or an OMC runtime change avoids it.

### 5. Native OMC is unaffected

**Verified.**
- The native solver moves its step end onto `nextSampleEvent` when that is within `SAMPLE_EPS` of the step end ([`events.c` L59-L69](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/simulation/solver/events.c#L59-L69)).
- It activates every sample with `nextSampleTimes[i] <= time + SAMPLE_EPS` ([L157-L163](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/simulation/solver/events.c#L157-L163)), with `SAMPLE_EPS = 1e-14` ([`epsilon.h` L37](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/simulation/solver/epsilon.h#L37)).
- It accumulates sample times the same way ([`model_help.c` L127-L135](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/simulation/solver/model_help.c#L127-L135)), but the tolerance absorbs the drift.

**Measured.** All 8 native runs finished successfully with correct counters:

| Model | Solver | Interval | Final counter |
|---|---|---|---|
| `S1` | `cvode` | 0.01 | 10 |
| `S1` | `cvode` | 0.03 (stop 0.99) | 9 |
| `S1` | `cvode` | 0.1 | 10 |
| `S2` | `cvode` | 0.01 | 14 |
| `S2` | `cvode` | 0.25 | 14 |
| `S2` | `cvode` | 0.0125 | 14 |
| `S1` | `dassl` | 0.01 | 10 |
| `S1` | `euler` | 0.01 | 10 |

## Method notes

The predictor was corrected twice against measurements before the final agreement:
1. It first omitted FMPy's clamp of the last CS step to `stop_time`. That caused 5 CS mismatches.
2. It first assumed OMC reports `valuesOfContinuousStatesChanged=True` when a sample fires. A trace showed `False`, which caused 52 mismatches for 0.3.29/P1 on `S3`.
   - OMC `master` has a comment saying that, after `updateDiscreteSystem` returns, "the checks below see nothing" ([`fmu_model_interface.c.inc` L964-L971](https://github.com/OpenModelica/OpenModelica/blob/ed5c2a659e/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu_model_interface.c.inc#L964-L971)). This matches the observation.

All tables above come from runs after these corrections.

## Open questions

- Whether PR #870 fixed a real problem that reverting to 0.3.29 behaviour (or P1) would bring back. The PR has no description and #882 has no maintainer reply.
- Whether OMC master's Rust FMI runtime (`advance_sample`) or later OMC releases change the tick arithmetic or add a tolerance. Not inspected.
- `CVodeSetInitStep` as an FMPy-side guard is untested (no binding).
- With `stop_time=10`, `S1` ME at interval 0.05 ends at `x = 4.9576e-05` under P3 and `4.5399e-05` under 0.3.29 (exact e⁻¹⁰ = 4.5400e-05). **(inference)** The gap is within FMPy's default absolute tolerance (nominal·rtol = 1e-5) and comes from 0.3.32 re-initialising CVODE at each of the 100 events. Not isolated.

## Reproduction

Scratch under `/tmp/cvode-tout/` (not in the repo): models in `models/Q/`, scripts in `scripts/`, FMUs in `work/<model>_<me|cs_euler|cs_cvode>/`, sweep logs `sweep_*.out`, FMPy copies with P1–P3 in `patched/p{1,2,3}/fmpy/`.

```bash
cd /tmp/cvode-tout
bash scripts/build_all.sh; bash scripts/build_s3.sh   # buildModelFMU(Q.S*, version="2.0", fmuType="me"|"cs") [+ --fmiFlags=s:cvode]
bash scripts/run_me_basic.sh                           # traced ME runs at 0.01 0.03 0.05 0.1 0.0125
bash scripts/run_sweep.sh                              # me-cvode, me-euler, cs-cvode, cs-euler × S1, S2; predictor vs measured
bash scripts/run_avoid.sh                              # ME CVode: FMPy 0.3.32 / 0.3.29 / P1 / P2 / P3 × S1–S3
bash scripts/run_p3m.sh                                # P3 as a runtime wrapper
bash scripts/run_options.sh                            # FMPy options at 0.01
bash scripts/run_stop10.sh                             # stop_time=10
cd work/native && omc ../../scripts/native.mos         # native OMC runs
python3 -I scripts/summarize.py sweep_me_cvode.out sweep_cs.out sweep_avoid.out sweep_p3m.out
# all Python runs: uv run -q --no-project --python 3.11 --with fmpy==<ver> python -I scripts/<script>.py …
```

Models:

```modelica
package Q
  model S1 "sample(0.1, 0.1)"
    Real x(start = 1, fixed = true);  Integer cnt(start = 0, fixed = true);
  equation
    der(x) = -x;
    when sample(0.1, 0.1) then cnt = pre(cnt) + 1; end when;
    annotation(experiment(StartTime = 0, StopTime = 1, Interval = 0.01, Tolerance = 1e-6));
  end S1;
  model S2 "sample(0.05, 0.07)"  // as S1 with: when sample(0.05, 0.07) then …
  end S2;
  model S3 "two samples"         // as S1 plus: Integer cnt3; when sample(0.3, 0.3) then cnt3 = pre(cnt3) + 1; end when;
  end S3;
end Q;
```

Predictor rule (`scripts/predict.py`):
- **ME:** replay FMPy's loop (`g = start + (n+1)·h`, the `isclose` merging, and a reset after every event in 0.3.32 or none for these models in 0.3.29). Fire samples iff `t_i <= time`, advance them with `t_i += interval`, and fail on the first post-reset step with `|tout − t| < 2·DBL_EPSILON·max(|t|,|tout|)`.
- **CS:** replay `fmi2DoStep`'s sub-stepping, with the sticky `time_event` flag.

Key numbers:

| Case | Result |
|---|---|
| Runs compared with the predictor | 780, all agree (`S1`–`S3`, 30 intervals, ME CVode/Euler, CS CVODE/Euler, FMPy 0.3.32/0.3.29, P1/P2/P3/P3-wrapper) |
| ME CVode 0.3.32 fails | `S1` 12/30, `S2` 23/30, `S3` 26/30 |
| CS CVODE fails | `S1` 30/30, `S2` 2/30 |
| ME Euler, CS Euler fails | 0/120 |
| 0.3.29, P1, P3, P3 wrapper | 0/90 each |
| P2 | `S1`/`S2` 0/60, `S3` 30/30 fail |
| Native OMC | 8/8 pass |
