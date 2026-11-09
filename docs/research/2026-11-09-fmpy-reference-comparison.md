# FMPy as a simulator for reference-model comparison tests

Date: 2026-11-09
Sources: FMPy source at tag [`v0.3.32`](https://github.com/CATIA-Systems/FMPy/tree/v0.3.32) (commit `e42e288`), its `README.md`, `pyproject.toml`, `LICENSE.txt` and [PyPI metadata](https://pypi.org/project/FMPy/0.3.32/);
FMI specification sources [`v2.0.4`](https://github.com/modelica/fmi-standard/tree/v2.0.4/docs);
[FMI Cross-Check rules 4.1](https://github.com/modelica/fmi-cross-check/blob/master/FMI-CROSS-CHECK-RULES.md) (repository archived 2022);
[Reference-FMUs `v0.0.42`](https://github.com/modelica/Reference-FMUs/tree/v0.0.42) (commit `75d16f8`);
OpenModelica source at tag [`v1.27.2`](https://github.com/OpenModelica/OpenModelica/tree/v1.27.2) (`ModelicaBuiltin.mo`, `SimulationResultsCmpTubes.c`, User's Guide `fmitlm.rst`);
[csv-compare](https://github.com/modelica-tools/csv-compare) README; OMSimulator PyPI sdist `3.0.0.post198`; [PyFMI `2.23.0`](https://github.com/modelon-community/PyFMI/tree/PyFMI-2.23.0); [fmi4c](https://github.com/robbr48/fmi4c) README;
MathWorks FMU Builder documentation (pages labelled R2026b); this repo at `a80e92b`.
Observed with OpenModelica 1.27.2 (`omc`), FMPy 0.3.32 on Python 3.11.18 (`uv run --no-project --python 3.11 --with fmpy==0.3.32`), Reference FMUs v0.0.42 (`linux64`), Debian 13 x86_64.
Background: the earlier note on Simulink FMUs in OpenModelica (`docs/research/2026-11-08-simulink-fmu-import-openmodelica.md`, untracked in the main checkout) is taken as given and not re-researched.

## Question

OpenModelica's FMU import is too limited to be useful. Can mtools drive FMUs through FMPy and use that in the two-model test bases of `mtools.testing` for regression testing?
A typical case: a Simulink-exported FMU is the reference and a Modelica model simulated by OMC through mtools is the candidate, or the other way round.

The note answers six points:

1. Where FMPy fits in mtools.
2. What FMPy can do.
3. How to compare results across tools.
4. The alternatives.
5. Risks.
6. A ranked recommendation.

## Method

1. Read the comparison spec, the OMC backend spec, the glossary, and the code paths that the test bases use to simulate and compare. Every repo claim cites `file:line` at `a80e92b`.
2. Read FMPy's `simulate_fmu`, `simulateME`, `simulateCS`, `Input`, `Recorder`, `apply_start_values`, remoting and the validation/compare utilities at `v0.3.32`. Checked PyPI metadata, the licence file and the installed wheel's native libraries.
3. Read the comparison rules or code of the FMI Cross-Check, the Reference-FMUs test harness, OpenModelica's `diffSimulationResults` (tube algorithm), and csv-compare.
4. Checked the alternatives' install paths and licences from their packages or repos.
5. **Prototype under `/tmp`** (nothing in the repo):
   - Ran Reference FMUs `VanDerPol`, `Stair`, `BouncingBall` and `Feedthrough` (FMI 2.0, `linux64`) through FMPy.
   - Wrote equivalent Modelica models and simulated them with `omc`. Exported them with `buildModelFMU` and ran the exported FMUs through FMPy too.
   - Compared the tables with the same rules as `assert_solutions_match` (see [Reproduction](#reproduction)).

**(verified)** means read in source or spec, or measured here. **(inference)** means my reasoning from verified pieces.

## Short answer

- **FMPy is a good fit as a second simulator behind mtools' run seam, but neither the code on `main` nor the current comparison helper is ready for it.**
  - The test bases already reach the simulator through one call, `sim_tools.simulate(config)`, and key the result by `config.model_name`. They don't care how the table was produced.
  - What is missing:
    - a run config for an FMU;
    - dispatch on it in `simulate_run`;
    - a cross-tool comparison mode.
  - The OMC backend spec's `build` / `Build.simulate(run_settings) -> DataFrame` interface fits an FMU run naturally. So do its `settings.parameters` path and its result contract.
- **The current `assert_matches_reference()` cannot pass any OMC-vs-FMPy pair, even for identical equations (verified, VanDerPol).** It fails for three independent reasons:
  - the signal sets differ (OMC also writes `der(x0)`, `der(x1)`);
  - the row counts differ (OMC repeats the stop-time row: 2002 vs 2001);
  - `time` differs by 3.6e-15, which is above `atol = eps` = 2.2e-16.

  Even after aligning signals and rows, the values differ by 7.5e-5. That is expected for two different solver runs at tolerance 1e-6.
- **Apples-to-apples works.** Export the Modelica model with `buildModelFMU(..., version="2.0")` and run both FMUs through FMPy with the same settings. The OMC-exported VanDerPol then matched the Reference FMU **bit for bit** (max diff 0, mtools rule passes at `eps`).
- **FMPy 0.3.32 is solid for this job:**
  - FMI 1.0, 2.0 and 3.0, ME and CS, BSD-2, Python ≥3.10. It ran on 3.11 here.
  - Model Exchange follows the FMI event sequence. Discrete and Boolean inputs are set only in Event Mode, and input changes trigger events.
  - `start_values` with `validate=True` rejects misspelt names.
  - Pitfalls (verified):
    - The ME `Euler` solver ignores `step_size` and steps at `output_interval`.
    - If `output_interval` is not given, FMPy may silently double the interval to keep at most 1000 steps.
    - CS output at a communication point does not yet reflect an input changed at that point.
- **Simulink FMUs are the main risk, not FMPy:**
  - MathWorks builds a Linux binary from Windows only for **fixed-step co-simulation** FMUs, through WSL2.
  - Variable-step FMUs need "an installation of MATLAB or MATLAB runtime".
  - FMPy's `win64`-on-Linux remoting needs Wine and is marked experimental.
  - CI (Linux only, per the backend spec) therefore needs `linux64` FMUs.

## 1. Where FMPy fits in mtools

### The seam that exists today (`main`, pydelica)

| Step | Where | What it means for an FMU run |
|---|---|---|
| Test bases simulate through one public call and index the result by the composed config's `model_name` | `src/mtools/testing.py:236-240` (candidate), `:292-296` (reference); sweeps `src/mtools/internal/testing.py:381-386`, `:416-421` | The bases need no change if `sim_tools.simulate` accepts an FMU run config and returns `{model_name: DataFrame}` |
| The test bases only need a `Registry` protocol: `add_to_hydra_store`, `compose_experiment`, `get_experiment_run_config` | `src/mtools/testing.py:125-149` | No new protocol method is needed |
| `sim_tools.simulate` delegates to `simulate_run` for single runs and to `hydra_zen.launch` for sweeps | `src/mtools/sim_tools.py:64-76`; `src/mtools/internal/sim_tools.py:132-150` | Sweeps reuse the single-run path, so one dispatch point covers both |
| `simulate_run` **always** instantiates a pydelica `SessionDirector` and builds a session | `src/mtools/internal/sim_tools.py:97-111` | **Missing:** dispatch on the run kind |
| A run config is typed as `type[SimulationRun]` = `model_name` + `session: Session` (pydelica-shaped) | `src/mtools/hydra_registry.py:25`; `src/mtools/session_config.py:90-115` | **Missing:** an FMU run config type. Today it would have to fake a `Session` |
| Experiments are re-registered as subclasses of **every** experiment-capable run config, with `model_name=MISSING, session=MISSING`. Their overrides target `session/parameters` and `session/sim_configurations` | `src/mtools/hydra_registry.py:536-552`; `examples/src/kinematic_vehicle/kinematic_vehicle.py:73-104` | An FMU run config must accept the **same** parameter group path, or experiments fail to compose against it |
| Sweeps override `<sweep_param_prefix>.<param>`, default `session.parameters` | `src/mtools/testing.py:339`, `:393` | The same constraint applies to sweeps |
| Comparison: same column set, same length, then column-wise `assert_allclose(rtol=0, atol=eps)`, including `time` | `src/mtools/internal/testing.py:214-264`; spec `docs/specs/2026-10-30-reference-model-comparison-spec.md:158-177` | **Missing for cross-tool runs:** signal mapping or subset, per-signal tolerances, time-grid tolerance, event handling. Signal subsets are explicitly out of scope (spec `:233-242`). `assert_solutions_match` already has an `rtol` parameter (`:220`), but `assert_matches_reference` passes only `atol=self.eps` (`src/mtools/testing.py:194-201`) |

### The seam the OMC backend spec will create

`docs/specs/2026-11-08-omc-backend-spec.md` is `ready-for-agent`, so it is not implemented on `a80e92b`. It defines the seam an FMU run should plug into:

- **Two-call backend:** `build(build_config) -> Build` and `Build.simulate(run_settings) -> DataFrame`. Configs are plain data. `simulate_run` validates, builds and runs outside `instantiate` (spec `:105-113`).
- **Config shape:** `SimulationRun(build: Build, settings: RunSettings)`. `RunSettings` holds parameters, start/stop time, interval, tolerance, solver, variable filter and timeout. The override paths become `build.*` / `settings.*`, and the sweep prefix becomes `settings.parameters` (spec `:117-155`).
- **Result contract:** `time` first, one column per time-varying variable, Integer/enum as `int64`, Boolean as `bool`, repeated event and stop-time rows kept (spec `:193-201`).
- **Errors:** `mtools.errors` with `ConfigError`, `SimulationError(.partial_result)` and `SimulationTimeout` (spec `:203-214`).
- **Platform:** Windows and macOS are out of scope; CI is Linux only (spec `:308`).

**How an FMU run maps onto it (inference):**

- **Build.** An FMU is already a compiled artefact, so the "build" step reduces to opening and validating it: `read_model_description(validate=True)`, plus a platform check.
- **Run settings.** `RunSettings` maps almost one-to-one onto `simulate_fmu` keyword arguments (FMPy `simulation.py:622-652`):

  | `RunSettings` | `simulate_fmu` |
  |---|---|
  | `parameters` (flattened) | `start_values` |
  | `start_time` / `stop_time` | `start_time` / `stop_time` |
  | `interval` | `output_interval` |
  | `tolerance` | `relative_tolerance` |
  | `solver` | `solver` (`"CVode"` / `"Euler"`) |
  | `timeout` | `timeout` |
  | `variable_filter` | `output` (names matched against `modelDescription`) |

- **Unset settings.** As with OMC's `experiment` annotation, unset values come from the FMU's `DefaultExperiment` (FMPy `simulation.py:730-765`).
- **Parameter paths.** `settings.parameters` stays the parameter path, so registered experiments and sweeps compose against an FMU run config unchanged, as long as the parameter dataclass field names are valid FMU variable names.
- **Vocabulary.** `GLOSSARY.md` defines **Build** as "One Modelica model compiled with one build configuration" and **Simulation target** as "the OMC code generator and runtime" ("_Avoid_: backend"). An FMU is neither, so a new term is needed (for example **FMU run**) rather than a third simulation target.

### Three placement options

| Option | What it is | Fits the comparison bases? | Verdict |
|---|---|---|---|
| **A. Standalone helper** | `mtools.fmu.simulate(fmu, settings) -> DataFrame` used by hand-written tests | No. Tests must compose, sweep and key results themselves, which is what the spec set out to remove (spec `:6-18`) | Cheap interim only |
| **B. Reference-only source** | `reference_run_config` may be an FMU run config | Yes, but it needs exactly the same dispatch as C, because the bases call the same `sim_tools.simulate` for both sides | No cheaper than C |
| **C. Second simulator behind the run seam** | An FMU run config accepted wherever a Modelica run config is: candidate or reference, single or sweep | Yes, unchanged bases | **Recommended**, after backend migration step 2 |

## 2. FMPy 0.3.32 capabilities (primary sources)

All `simulation.py` lines refer to [`src/fmpy/simulation.py` at v0.3.32](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py).

| Topic | Finding | Source |
|---|---|---|
| FMI versions, interfaces | FMI 1.0, 2.0, 3.0; Model Exchange and Co-Simulation. `fmi_type=None` picks CS if present, else ME | [README L7-L8](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/README.md#L7-L8); `simulation.py:711-717`; separate `fmi1.py`/`fmi2.py`/`fmi3.py` |
| ME solvers | `'CVode'` (default; SUNDIALS CVODE BDF, `maxStep = (stop-start)/50`, default rtol 1e-5) or `'Euler'` (forward Euler with sign-change root detection) | `simulation.py:930-931`, `:1049-1064`, `:568-620` |
| **ME `Euler` ignores `step_size`** | The ME loop steps from one communication point to the next: `next_regular_point = start + (n+1)*output_interval`, shortened to input or time events. `ForwardEuler.step(t, tNext)` takes one step of `tNext - t`. `step_size` is only checked to divide `output_interval`. The docstring says "step size for the 'Euler' solver". **Measured:** `step_size=1e-4` and `1e-2` with `output_interval=0.01` give identical results | `simulation.py:659`, `:1067-1068`, `:1093-1111`, `:590-604`; [Reproduction](#reproduction) |
| ME event handling | Follows the FMI 2.0 importer sequence: initial event iteration `while newDiscreteStatesNeeded` before continuous time; steps are clipped to `nextEventTime` (only when defined), to input events and to the stop time; then `enterEventMode`, inputs applied after the event, loop on `newDiscreteStates`, `enterContinuousTimeMode`, solver reset. FMI 3.0 uses `updateDiscreteStates` | `simulation.py:978-1004`, `:1093-1112`, `:1156-1203` |
| Rows at events (ME) | `record_events=True` (default) records the left limit before the event update (`force=True`) and the right limit on the next pass. Events therefore give two rows at the same time, as in OMC results (backend spec `:198`) | `simulation.py:1083-1085`, `:1136-1139` |
| CS stepping | `output_interval` **is** the communication step; there is no separate `step_size`. Steps are shortened to input event times only if `canHandleVariableCommunicationStepSize`. A last partial step to `stop_time` happens only then; otherwise the run stops early | `simulation.py:1216-1222`, `:1287-1306` |
| CS inputs | FMI 2.0: all inputs are set at the start of each step with the post-event value (`after_event=True`), then `doStep`. The row at `t` is the output **after** the step ending at `t`, so a direct-feedthrough output shows an input change made at `t` only at the next row. **Measured:** Feedthrough FMU, Boolean step at 0.5, interval 0.1: ME shows `true` at t=0.5, CS first at t=0.6. FMI 3.0 with `use_event_mode=True` enters Event Mode at input or FMU events and records an extra row | `simulation.py:1322-1344`, `:1346-1383`; FMI 2.0.4 CS "frozen data `u(tc_i)`" ([CS math L40-L49](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/4_1_co-simulation_math.adoc#L40-L49)) |
| Default intervals | ME: no `output_interval` → `auto_interval` (500-1000 points). If only `step_size` is given, the interval starts at `step_size` and **doubles until ≤1000 steps** (measured: `step_size=0.01` over 20 s gives grid 0.02). CS: falls back to `fixedInternalStepSize`, then `DefaultExperiment.stepSize`, again doubled until ≤1000 steps. ME ignores `DefaultExperiment.stepSize` ([FMPy#665](https://github.com/CATIA-Systems/FMPy/issues/665), open) | `simulation.py:749-765`, `:933-945`; [`util.py` `auto_interval` L712-L733](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/util.py#L712-L733) |
| Time grid arithmetic | Grid points are `start + (n+1)*interval` (multiplied, not accumulated). Closeness uses `math.isclose` (rel 1e-9) | `simulation.py:1093`, `:1289`, `:3` |
| `Input` class | Structured array; first field is time. Continuous Real inputs are interpolated linearly. Repeated time stamps mark discontinuities. Variables with `variability` `discrete`/`tunable` (all Boolean, Integer and enum inputs) are piecewise constant (left value; the right value after the event). Their changes become **time events** (`findEvents`). In ME, discrete inputs are set only in Event Mode (`apply(time, discrete=False)` during continuous time), which matches the FMI rule that a discrete input change is an external event. A missing input only prints `Warning: missing input` | `simulation.py:185-307`, `:355-391`, `:393-466`, `:1116`, `:274`; FMI 2.0.4 [ME math L110-L115](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/3_1_model_exchange_math.adoc#L110-L115) |
| `start_values` | Applied in the instantiated state and again in Initialization Mode, according to `causality`/`variability`/`initial`. They accept units and display units, arrays and Boolean strings. With `validate=True` (default), any name not applied raises `Exception("The start values for the following variables could not be set: …")`. Measured with `muu` | `simulation.py:467-566`, `:913-926`, `:1034-1036` |
| Result format | `SimulationResult`, a numpy structured array subclass. FMI 2.0 dtypes are `float64` / `int32` / `bool`; FMI 3.0 has per-width types; array variables are sub-arrays. Default columns: outputs. If there are none, the first 5 state derivatives or locals. **No `der(...)` or local columns unless listed in `output=`** | `simulation.py:20-30`, `:33-63`, `:65-175` |
| Conversion to the mtools table | `pandas.DataFrame({n: r[n] for n in r.dtype.names})` gives `time` first. Integer columns need `int32 → int64` to match the backend spec (`:197`). FMPy does not repeat the stop-time row; OMC does | prototype; backend spec `:193-199` |
| Validation | `validate_fmu()` / `fmpy validate` check the model description; `fmpy info`; CLI `simulate` with `--input-file`, `--output-interval`, `--interface-type` | [`cli.py` L45-L70](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/cli.py#L45-L70); [`validation.py` L8](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/validation.py#L8) |
| Platforms and remoting | One `py3-none-any` wheel. It ships CVODE for `x86_64-linux`, `x86_64-windows` and `aarch64-darwin` only (listed from the installed wheel), so there is **no CVODE for aarch64 Linux**. `simulate_fmu` refuses an FMU without a binary for the host unless remoting applies. `remote_platform='auto'` handles `win32` on `win64` (shared memory), `linux64` on Windows (WSL), and `win64` on Linux **only if `wine64` is installed** (TCP server run by Wine). Marked "experimental" | `simulation.py:678-679`, `:694-704`; [`util.py` L645-L710, L1004-L1049](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/util.py#L645-L710) |
| Licence | 2-Clause BSD (icons CC BY 4.0). Remoting binaries are BSD-2 | [`LICENSE.txt`](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/LICENSE.txt); `remoting/license.txt` |
| Dependencies | `requires-python >=3.10`. Hard dependencies: `attrs, cmake>=4.0.3, jinja2, lark, lxml, msgpack, nbformat, numpy>=2.1.3`. The `cmake` wheel alone is 87 MB installed. `scipy` and `plotly` are only in extras. No conflict with mtools' `numpy~=2.4.6` / `pandas~=3.0.2` | [`pyproject.toml` L1-L16](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/pyproject.toml#L1-L16); PyPI JSON |
| Maintenance | Releases 0.3.27 (2025-12-16) to 0.3.32 (2026-09-09), about every 1-3 months. Last push 2026-11-02. 170 open issues. Open regressions: [#882](https://github.com/CATIA-Systems/FMPy/issues/882) (CVode `CV_TOO_CLOSE` after time events since 0.3.30; **not reproduced here** with two OMC FMUs that have a state and time events) and [#863](https://github.com/CATIA-Systems/FMPy/issues/863) (Buildings FMU fails on 0.3.29, works on 0.3.21) | PyPI release list; GitHub API |

## 3. Comparing results across tools

### What breaks the current helper (measured, see [Reproduction](#reproduction))

| Effect | Example | Size |
|---|---|---|
| Different signal sets | OMC writes every time-varying variable (`der(x0)`, `g`, …); FMPy records only outputs by default | Fails `assert_solutions_match` at the signal-set check (`internal/testing.py:249-252`) |
| OMC repeats the stop-time row | VanDerPol: 2002 OMC rows vs 2001 FMPy rows | Fails the length check (`:253-256`) |
| Grid arithmetic | VanDerPol, both on a 0.01 grid: max \|Δtime\| = 3.6e-15 | Above `eps`, so `time` fails even after alignment |
| OMC rounds the interval count | `Stair`, `StopTime=8.5`, `Interval=0.2`: `simulate()` used `numberOfIntervals = 42`, grid 0.20238…; FMPy used 0.2 plus a last point 8.5 | Different grids |
| Solver differences | VanDerPol, CVODE rtol 1e-6 in both tools: max \|Δx1\| = 1.2e-4 | Far above `eps`, below 1e-3 |
| Event instants | Stair time events: both switch at exactly 1.0, 2.0, …, 8.0. BouncingBall state events: the first two agree to 1e-6 (0.451524, 1.083656). After that my "equivalent" Modelica model fired the bounce one output step late (h = +1e-10 at the located event, so `h <= 0 and v < 0` stayed false until t = 1.09), and the trajectories diverged | Positional comparison is meaningless near events (Δv = 5.27 at the event row) |
| CS vs ME semantics | VanDerPol CS (the Reference FMU's internal forward Euler, `FIXED_SOLVER_STEP 1e-2`) vs OMC CVODE: max \|Δ\| = 0.64 | A different numerical method, not a model difference |

### How established tools compare

| Tool | Time-grid handling | Events | Tolerance | Source |
|---|---|---|---|---|
| **FMI Cross-Check (rules 4.1)** | The exporter supplies `_ref.csv` and `_ref.opt` (`StartTime`, `StopTime`, `StepSize` (0 = variable step), `RelTol`, optional `AbsTol`, `SolverType`, `OutputIntervalLength`). Inputs from `_in.csv` are interpolated linearly; Booleans are written as `0`/`1`; repeated time stamps mark discontinuities | No explicit rule | "automatic result comparison with specified epsilon bands", but no band width is specified. Since 4.1 importers submit only a self-assessed `passed`/`failed`, and the Steering Committee "may reject results that differ significantly" | [Rules §3, §9.1.4, §9.2.5, §10](https://github.com/modelica/fmi-cross-check/blob/master/FMI-CROSS-CHECK-RULES.md) |
| **FMPy cross-check** (`fmpy.util.validate_result`) | Resamples the reference onto 1000 uniform points. Duplicate times are nudged by 1e-13. Linear interpolation for floats, zero-order hold otherwise | Absorbed by the horizontal band | Band = min/max filter over 20 samples ± 10 % of the signal range. Green if no sample is outside, yellow if ≤ 10 % are. Needs `scipy`. Too loose for regression tests | [`util.py` L116-L213](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/util.py#L116-L213); [`cross_check.py` L219-L270](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/cross_check/cross_check.py#L219-L270) |
| **Reference-FMUs harness** | Tests run `validate_fmu` and **smoke-simulate** (`simulate_fmu(fmu, fmi_type=…)`) with no numeric comparison. One test compares an exact CSV text. Reference CSVs are produced at release time with `fmusim --interface-type me --solver cvode` and shipped as `fmi-ls-ref` | n/a | n/a | [`tests/test_targets.py` L31-L108](https://github.com/modelica/Reference-FMUs/blob/v0.0.42/tests/test_targets.py#L31-L108); [`build/merge_binaries.py` L116-L128](https://github.com/modelica/Reference-FMUs/blob/v0.0.42/build/merge_binaries.py#L116-L128) |
| **OMC `diffSimulationResults`** | Interpolates the actual result onto the **reference** time grid (`calibrateValues`). Event detection tolerance in x is `(t_end - t_0) * 1e-3 / max(n, n_ref)` | Points at duplicate times are not judged (error = NaN). They get a band 10× wider, tight around both values | Tube around the reference (csv-compare algorithm) with x-width `rangeDelta` (default 0.002), plus `relTol` (1e-3) × \|y\|, plus abs tol = signal range × `relTolDiffMinMax` (1e-4). `compareSimulationResults` is marked `version="Deprecated"` | [`ModelicaBuiltin.mo` L3337-L3380](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/FrontEnd/ModelicaBuiltin.mo#L3337-L3380); [`SimulationResultsCmpTubes.c` L547-L645](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/runtime/SimulationResultsCmpTubes.c#L547-L645) |
| **csv-compare** (BSD-3, ITI) | Tube around the base curve; values of the compared curve are checked against it | `--tolerance` sets the tube width in x at discontinuities | Recommends a base file with finer resolution than the compared file. Needs .NET 4 or Mono. Last release v2.1.1 (2024-09-27) | [README](https://github.com/modelica-tools/csv-compare#readme) |

### What a cross-tool mode in mtools needs (inference from the above)

1. **Signal mapping and subset.** A class-level map `{candidate_name: reference_name}`. Only mapped signals are compared, and a missing mapped signal still fails (keeps user story 4's intent). This changes the spec's "Out of Scope: Comparing a subset of signals" (`:235`).
2. **Grid normalisation.**
   - Drop the duplicated stop-time row.
   - Compare `time` with a tolerance relative to the interval, not `eps`.
   - For different grids, interpolate the candidate onto the reference grid, as `diffSimulationResults` does.
   - Pass the **same explicit `interval`** to both sides. Never let FMPy pick it: the doubling rule applies when it is unset.
3. **Events.** Keep the right limit at duplicate time stamps, and either skip a small window around reference event instants or use a tube. This is what OMC and csv-compare do. For Boolean and Integer signals, compare switching instants within a time tolerance instead of values.
4. **Tolerances.** Expose `rtol` (already in `assert_solutions_match`) and per-signal `atol` next to `eps`. Cross-tool values cannot be compared at `eps` (measured gap 1.2e-4 at rtol 1e-6).
5. **Inputs.** If the FMU has inputs, the reference run needs an input table. The equivalent Modelica model must see the same signal: a `CombiTimeTable` from the same CSV, or the same `BooleanStep`. Cross-Check uses linear interpolation and 0/1 Booleans.

## 4. Alternatives

| Tool | FMI support | Python install on Linux | Licence | Fit for mtools | Source |
|---|---|---|---|---|---|
| **FMPy 0.3.32** | 1.0/2.0/3.0, ME+CS, FMI 3.0 CS event mode | `pip`/`uv` wheel; pure Python plus bundled native libraries | BSD-2 | Best: one function call → structured array; FMI-conformant ME event loop; validation | above |
| **OMSimulator** (PyPI `3.0.0.post198`, 2026-10-07) | The OM 1.27.2 bundle is FMI 2.0 only. FMI 3.0 is on `master` (per the background note) | **sdist only.** Installing downloads a *nightly* binary from `build.openmodelica.org` with `requests.get(url, verify=False)`, so TLS verification is off. Only `linux-x86_64` (Ubuntu 24.04 build, else focal), Windows and macOS | OSMC-PL / AGPL-3 | SSP and multi-FMU co-simulation are strengths, but a heavy and unsafe install path for a single-FMU reference | sdist `build_helpers.py` L73-L101, `pyproject.toml` L14, `OSMC-License.txt` |
| **PyFMI 2.23.0** (2026-09-09) | 1.0/2.0, plus FMI 3.0 ME and CS classes (`FMUModelME3`, `FMUModelCS3`) | PyPI is stuck at 2.5 (2018). Current releases via `conda install -c conda-forge pyfmi`, or from source with FMI Library and Assimulo | LGPL-3.0 | Capable (Assimulo solvers, master algorithm), but conda-only does not fit a uv workspace | [README](https://github.com/modelon-community/PyFMI/blob/PyFMI-2.23.0/README.md); [`fmi3.pyx` L3783, L4219](https://github.com/modelon-community/PyFMI/blob/PyFMI-2.23.0/src/pyfmi/fmi3.pyx#L3783); PyPI JSON |
| **fmi4c v1.2** (2026-06-03) | 1.0/2.0/3.0, all interface types | **C library**; no Python simulation driver | MIT | Would need a hand-written master loop, solver and event handling, which is what FMPy already provides | [README](https://github.com/robbr48/fmi4c#readme) |
| **`buildModelFMU` + FMPy** (apples-to-apples) | OMC 1.27.2 exports FMI 1.0/2.0 (ME, CS, `me_cs`). `version="3.0"` → `Error: Unknown FMU version 3.0. Only version 1.0 & 2.0 are supported.` (measured). The CS FMU's default solver is forward Euler with one step per `communicationStepSize`; CVODE needs `--fmiFlags=s:cvode` | Needs only `omc` (already in CI) and FMPy | n/a | Removes solver, grid and runtime differences, so a mismatch is a model difference. Measured: bit-identical VanDerPol | [`ModelicaBuiltin.mo` L2728-L2749](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/FrontEnd/ModelicaBuiltin.mo#L2728-L2749); [`fmitlm.rst` L59-L83](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/doc/UsersGuide/source/fmitlm.rst#L59-L83) |

**Weighing `buildModelFMU` apples-to-apples (inference, except where measured):**

- **Pros:**
  - The same solver, grid, event loop and result format on both sides.
  - The comparison can stay strict: eps-level for identical equations (measured), small `rtol` otherwise.
  - Boolean inputs reach both FMUs through the same FMI-conformant `Input` path.
  - The OMC `importFMU` wrapper is avoided entirely.
- **Cons:**
  - It tests the **exported FMU**, not the C/Cpp runtime mtools normally runs. Runtime flags, the result reader and `.mat` dtypes are bypassed.
  - FMI 2.0 only in 1.27.2.
  - The CS default is Euler at the communication step.
  - Each export is another OMC build. The backend cache does not cover `buildModelFMU`.
  - Column names follow the FMU's model description; OMC uses the same names (`x0`, `der(x0)`) only when they are exported.

## 5. Risks and limits

- **Simulink FMU portability (verified in MathWorks docs).**
  - FMU Builder writes one binary "for the current platform".
  - A Linux binary from Windows needs MATLAB R2024a Update 1+, WSL ≥ 2.0.9.0 and FMU Builder ≥ 24.1.1. It is limited to co-simulation: "Model exchange FMU generation is not supported", "Models with a variable-step solver are not supported" ([Export Model as FMU with Linux Binary on Windows](https://www.mathworks.com/help/fmuexport/ug/fmu-cross-platform-compilation.html)).
  - So a Linux CI reference from Simulink is realistically a **fixed-step FMI 2.0/3.0 CS FMU**. Its communication step must be "an integral multiple of the fundamental sample time" ([Export Simulink Models to FMUs](https://www.mathworks.com/help/fmuexport/ug/export-simulink-models-to-functional-mock-up-units.html)).
  - Public Simulink FMUs found earlier are `win64` only (background note).
- **MATLAB runtime and licence.**
  - "For simulating a variable-step FMU in your system, you need to have an installation of MATLAB or MATLAB runtime" of the same version (same MathWorks page).
  - A variable-step Simulink FMU in CI therefore needs MATLAB Runtime on the runner. I found no statement on whether running a fixed-step standalone FMU needs a licence.
  - The FMI Cross-Check requires submitted FMUs to "run without license checks" (rules §9.1.3), but that applies only to cross-check submissions.
- **Windows FMUs on Linux.** FMPy remoting runs a `win64` FMU under Wine through a TCP server. It is "experimental" and needs `wine64` (FMPy `util.py:1004-1049`). Untested here because Wine is not installed. Not a basis for CI.
- **Boolean and event semantics.**
  - The tools are correct; the model pair may still differ:
    - CS outputs lag input changes by one communication step (measured).
    - Simulink CS FMUs have a documented single-step delay (background note).
    - ME needs `nextEventTime`, which FMPy honours.
  - A Simulink-CS reference vs an OMC candidate will differ at every Boolean edge unless the candidate models the same sample-and-hold. Compare switching instants with a tolerance of one communication step, or use FMI 3.0 CS event mode (`use_event_mode=True`) when the FMU supports it.
- **FMPy pitfalls.**
  - Always pass `output_interval` (the doubling rule otherwise).
  - Do not rely on `step_size` with ME `Euler`.
  - Pass `output=` explicitly (the default is outputs only, or at most 5 variables).
  - Map FMPy's bare `Exception`s to `mtools.errors`: an unknown start value → `ConfigError`, a failure → `SimulationError`.
  - Pin FMPy (`~=0.3.32`) because of open CVode regressions (#882, #863).
- **CI.**
  - Linux x86_64 only (backend spec `:308`). FMPy's wheel has no CVODE for aarch64 Linux.
  - Test FMUs should be produced in CI by `buildModelFMU` (OMC is already installed). The alternative is vendoring small BSD-2 Reference FMUs instead of committing third-party binaries.
  - Make `fmpy` an optional extra (`modelica-tools[fmu]`, like the existing `testing` extra in `pyproject.toml:12-14`), import it lazily, and `pytest.importorskip("fmpy")` in tests.
  - `cmake` (87 MB) comes with FMPy as a hard dependency.

## Ranked recommendations

1. **Use apples-to-apples first when the reference is an FMU.**
   - Export the Modelica candidate with `buildModelFMU(model, version="2.0", fmuType="me")` and run both FMUs through FMPy with identical `output_interval`, solver and tolerance.
   - This gives strict, eps-level comparisons today with no change to the comparison semantics (measured bit-identical on VanDerPol).
   - Pair it with one OMC-native-vs-FMU check at a loose tolerance, to catch export differences.
2. **Add an FMU run config behind the run seam, after backend migration step 2.**
   - Add an `FmuBuild` (FMU path, `fmi_type`, optional output names) as an alternative to `Build` in `SimulationRun.build`.
   - `simulate_run` dispatches on it to a small internal `_fmu.run(build, settings) -> DataFrame` built on `fmpy.simulate_fmu`.
   - This gives option C: candidate or reference, single or sweep, with no change to `mtools.testing`'s fetch code.
   - Doing it before the switch would mean faking pydelica's `Session` shape and redoing it (backend spec `:260-269`).
3. **Add a cross-tool comparison mode to `assert_matches_reference`.**
   - Signal map or subset, `rtol` / per-signal `atol`, time tolerance, stop-row and event-row handling, interpolation onto the reference grid.
   - Keep the exact mode as the default.
   - This needs a spec amendment, because subsets are out of scope today. It is required for any OMC-native vs FMPy pair.
4. **Interim, if the backend switch is far away: a standalone helper (option A).** `mtools.fmu.simulate(fmu_path, settings) -> DataFrame` with the same mapping as item 2, used in hand-written tests.
5. **Not recommended now:**
   - OMSimulator Python: unsafe nightly binary download, AGPL/OSMC-PL, FMI 2.0 only in the 1.27.2 bundle.
   - PyFMI: conda-only, LGPL.
   - fmi4c: no Python simulation loop.
   - FMPy Wine remoting for `win64` Simulink FMUs in CI.

### Sketch of the smallest viable integration (not implemented)

```python
# session_config.py (after the backend switch)
@dataclass
class FmuBuild:
    fmu_path: FilePath
    model_name: str                                   # key in sim_tools.simulate's result
    fmi_type: Literal["ModelExchange", "CoSimulation"] | None = None
    outputs: list[str] | None = None                  # None: all outputs; matched before variable_filter

@dataclass
class SimulationRun:
    build: Build | FmuBuild
    settings: RunSettings

# internal/fmu.py
def run(build: FmuBuild, settings: RunSettings) -> pandas.DataFrame:
    fmpy = _import_fmpy()                             # ConfigError("install modelica-tools[fmu]") if missing
    md = fmpy.read_model_description(build.fmu_path, validate=True)
    try:
        result = fmpy.simulate_fmu(
            build.fmu_path, fmi_type=build.fmi_type, model_description=md,
            start_time=settings.start_time, stop_time=settings.stop_time,
            output_interval=settings.interval,        # required explicitly: avoid FMPy's doubling rule
            relative_tolerance=settings.tolerance, solver=_SOLVERS[settings.solver or "cvode"],
            start_values=_flatten(settings.parameters), output=_select(md, build, settings),
            timeout=settings.timeout, remote_platform=None,  # no Wine/WSL remoting in mtools
        )
    except Exception as exc:                          # FMPy raises bare Exception
        raise _map_error(build, exc) from exc         # unknown start value -> ConfigError, else SimulationError
    return _to_frame(result)                          # time first; int32 -> int64; bool kept

# internal/sim_tools.py: simulate_run
#   if isinstance(config.build, FmuBuild): return {config.build.model_name: fmu.run(config.build, config.settings)}
# hydra_registry.py: create_fmu_run(model_name, fmu_path, fmi_type=None, outputs=None, settings=..., name=..., include_experiment_group=True)
# testing.py: class vars `signal_map`, `rtol`, `time_tol`; `assert_matches_reference(mode="exact" | "cross_tool")`
# pyproject.toml: [project.optional-dependencies] fmu = ["fmpy~=0.3.32"]
```

Tests:

- Build the FMU in a fixture with `omc` and `buildModelFMU`, so no binaries are committed.
- Run the registry experiments and a sweep against it as `reference_run_config`.
- Pin the error mapping and the dtype casts.
- Guard everything with `pytest.importorskip("fmpy")`.

## Open questions

- Which Simulink FMUs will the user actually have: FMI version, ME or CS, fixed or variable step, `linux64` binary? This decides between a plain FMPy run on Linux, MATLAB Runtime on the runner, or a Windows runner (§5).
- Should the FMU run be a new glossary term, and does an FMU count as a **build** for caching? There is nothing to cache except validation, so probably not.
- What tolerance policy is acceptable for regression: a tube (OMC/csv-compare style) or interpolation plus `rtol`/`atol` with event windows? Who owns per-signal tolerances, the test class or the run config?
- Will the backend's explicit `-stepSize` (backend spec `:179`) give exactly `start + n*interval` grids when `(stop-start)/interval` is not an integer? Today's `simulate()` rounded to 42 intervals (`Stair`). Not checked against the new backend, which does not exist yet.
- Does FMPy issue #882 (CVode after time events) affect real Simulink FMUs? Not reproduced with OMC-exported FMUs here.
- Does running a fixed-step standalone Simulink FMU need any MathWorks licence or runtime? The MathWorks pages read here do not say.

## Reproduction

All work is under `/tmp/fmpy-research/` (scripts in `proto/scripts/`, Modelica models in `proto/models/`, OMC output in `proto/omc-work/`). Nothing was added to the repo or `pyproject.toml`.
The Reference FMUs zip (`/tmp/fmu-repro/download-reference-fmus/Reference-FMUs.zip`) has sha256 `b6b4a195…1e97`, equal to the GitHub release digest of v0.0.42. It was treated as untrusted: paths were passed as arguments and Python ran with `-I`.

```bash
# OMC side: native runs (cvode, CSV) and FMU export
cd /tmp/fmpy-research/proto/omc-work && omc run.mos      # simulate(VanDerPol|BouncingBall|Stair, method="cvode", outputFormat="csv")
                                                          # buildModelFMU(..., version="2.0", fmuType="me_cs"); version="3.0" -> error
# FMPy side and comparison (rules copied from mtools.internal.testing.assert_solutions_match)
cd /tmp/fmpy-research/proto/scripts
uv run --no-project --python 3.11 --with fmpy==0.3.32 --with pandas \
  python -I compare.py /tmp/fmu-repro/download-reference-fmus/extracted/2.0 /tmp/fmpy-research/proto/omc-work
```

The Modelica models re-implement the Reference FMUs' `model.c`:

- `VanDerPol`: `mu=1`, `x0(start=2)`, `x1(start=0)`, `StopTime=20`, `Interval=0.01`, `Tolerance=1e-6`.
- `Stair`: `when sample(1, 1)` increments an `Integer`, `StopTime=8.5`, `Interval=0.2`.
- `BouncingBall`: `when h <= 0 and v < 0 then reinit(v, -e*pre(v))`. This is an approximation; it lacks the FMU's hysteresis and `h = DBL_MIN`.

| Comparison | Rows (cand / ref) | mtools rule, all columns, `eps` | mtools rule, common columns | After dropping duplicate rows and interpolating onto the reference grid |
|---|---|---|---|---|
| VanDerPol: OMC native vs Reference FMU, FMPy ME CVode (rtol 1e-6, interval 0.01) | 2002 / 2001 | FAIL: unexpected `der(x0)`, `der(x1)` | FAIL: length | max \|Δtime\| 3.55e-15; max \|Δx0\| 7.5e-5 (t=9.04), \|Δx1\| 1.2e-4 (t=9.67) |
| VanDerPol: OMC native vs Reference FMU, FMPy CS (FMU-internal Euler h=0.01) | 2002 / 2001 | FAIL | FAIL: length | \|Δx0\| 0.35, \|Δx1\| 0.64 |
| VanDerPol: **OMC-exported FMU vs Reference FMU, both FMPy ME CVode** | 2001 / 2001 | **PASS** | PASS | **0 (bit-identical)** |
| VanDerPol: OMC-exported FMU via FMPy ME vs OMC native | 2001 / 2002 | FAIL | FAIL: length | same as row 1 (7.5e-5 / 1.2e-4) |
| VanDerPol: OMC-exported FMU via FMPy CS (OMC default Euler) vs OMC native | 2001 / 2002 | FAIL | FAIL | \|Δx0\| 0.35, \|Δx1\| 0.64 (equal to row 2: both are forward Euler at h=0.01) |
| Stair: OMC native vs Reference FMU, FMPy ME | 60 / 52 | FAIL: length | FAIL: length | OMC grid 0.20238 (42 intervals) vs FMPy 0.2; both switch at exactly 1.0 … 8.0 |
| BouncingBall: OMC native vs Reference FMU, FMPy ME | 330 / 323 | FAIL | FAIL: length | events agree at 0.451524 and 1.083656, then the Modelica re-implementation fires one step late (t=1.09) and diverges; \|Δv\| 5.27 at an event row |

Other measurements from the same run:

- **ME Euler ignores `step_size`:**
  - `step_size=1e-4` and `step_size=1e-2`, both with `output_interval=0.01`, give identical DataFrames; max \|Δx0\| vs CVode is 0.351.
  - `step_size=1e-4` with `output_interval=1e-4`, subsampled, gives \|Δx0\| 0.0034.
- **Doubling rule:** ME with `step_size=0.01` and no `output_interval` over 20 s gives grid spacing 0.02 (1001 rows).
- **`start_values` sweep:** `mu` = 0.5 / 1 / 2 gives `x0(20)` = 1.490817 / 2.008150 / −1.728283. `start_values={"muu": 2}` raises `Exception: The start values for the following variables could not be set: muu`.
- **dtypes:** FMPy `counter` is `int32`; OMC CSV read by pandas is `int64`.
- **Feedthrough** (Boolean input step, interval 0.1, `output=["Boolean_output"]`):

  | Step at | ME | CS (`canHandleVariableCommunicationStepSize=true`) |
  |---|---|---|
  | 0.5 (on the grid) | rows at 0.5 twice; `true` from t=0.5 | `true` first at t=0.6 |
  | 0.55 (off the grid) | event rows at 0.55; `true` from 0.55 | extra communication point at 0.55, but `true` first at t=0.6 |

  FMPy also printed `Warning: missing input` for the four unspecified inputs.
- **FMPy #882 check:** OMC-exported FMUs with a state and time events (`sample(0.5, 0.5)` and `sample(0.3000000001, 0.37)`) ran under ME CVode and ME Euler without error.
- **`buildModelFMU(VanDerPol, version="3.0")`:** `Error: Unknown FMU version 3.0. Only version 1.0 & 2.0 are supported.`
