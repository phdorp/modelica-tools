# How FMPy maps onto run settings and results

Date: 2026-11-10
Sources: FMPy source at tag [`v0.3.32`](https://github.com/CATIA-Systems/FMPy/tree/v0.3.32) (commit `e42e288`, latest release, 2026-09-09);
FMI specification sources [`v2.0.4`](https://github.com/modelica/fmi-standard/tree/v2.0.4/docs) and [`v3.0.2`](https://github.com/modelica/fmi-standard/tree/v3.0.2/docs);
[Reference-FMUs `v0.0.42`](https://github.com/modelica/Reference-FMUs/tree/v0.0.42) (commit `75d16f8`, binaries and source);
OpenModelica [`Flags.mo` at v1.27.2](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/Flags.mo);
CPython [`Modules/_ctypes/callbacks.c` (3.11)](https://github.com/python/cpython/blob/3.11/Modules/_ctypes/callbacks.c) and the [`multiprocessing` docs](https://github.com/python/cpython/blob/main/Doc/library/multiprocessing.rst);
this repo at `bae149a` (`origin/main`, OMC backend from #68).
Observed with FMPy 0.3.32 (bundled SUNDIALS 7.5.0), Python 3.11.18, numpy 2.4.6 (`uv run --no-project --python 3.11 --with fmpy==0.3.32`), OpenModelica 1.27.2, gcc 14.2.0, Debian 13.7 x86_64, 4 cores.
Builds on `docs/research/2026-11-09-fmpy-reference-comparison.md` (branch `research/fmpy-reference-comparison`). Its findings on FMI versions, solvers, event handling, inputs, licence and the `step_size`/`output_interval` pitfalls are taken as given and not repeated.

FMPy line references are to `src/fmpy/<file>` at `v0.3.32`, e.g. `simulation.py:1087` is
<https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1087>.
Repo references are `file:line` at `bae149a`.

## Question

Issue #71: how does FMPy (current release) map onto mtools' `RunSettings` and result format, for Model Exchange (ME) and Co-Simulation (CS) FMUs?

1. For each `RunSettings` field, what is the FMPy equivalent in ME and in CS, or is there none? Where do defaults come from (`DefaultExperiment`)?
2. Results: the structured array's fields and dtypes versus mtools' typed DataFrame, repeated event rows, the stop-time row, alias and `der` variables, and how `output=` selects signals.
3. Errors: what FMPy raises or logs for a bad start value, an unknown variable, a solver failure, and an `fmi2Error`/`fmi2Fatal` status. Does a crash in the FMU binary take down the Python process?
4. Timeouts: can a run be stopped in-process, or does a timeout need a subprocess? What does that cost per run and in sweeps?
5. Determinism: do the same FMU and the same settings give bit-identical results across runs and processes?

## Method

1. Read the mtools seam on `origin/main`:
   - `RunSettings` (`src/mtools/session_config.py:79-103`);
   - `simulate_run` (`src/mtools/internal/sim_tools.py:25-46`);
   - the C command line (`src/mtools/internal/omc/run.py:118-134`);
   - the process-group timeout (`src/mtools/internal/omc/process.py:40-65`);
   - the result reader (`src/mtools/internal/omc/matfile.py`);
   - `mtools.errors`;
   - the backend spec (`docs/specs/2026-11-08-omc-backend-spec.md:175-200`).
2. Read FMPy's `simulate_fmu`, `simulateME`, `simulateCS`, `Recorder`, `apply_start_values`, `FMICallException`/`_call` and `CVodeSolver` at `v0.3.32`. Read the FMI 2.0.4 and 3.0.2 text on status codes, `DefaultExperiment`, `fmi2SetupExperiment` and aliases.
3. Built test FMUs (scratch only, nothing in the repo):
   - **OMC exports**: `Types`, `Assert`, `BlowUp` and `Chatter`, exported with `buildModelFMU(..., version="2.0", fmuType="me_cs")` (models in [Reproduction](#reproduction)).
   - **`Faulty2`**: the Reference-FMUs `Dahlquist` source, compiled with gcc, with a fault injected into `getDerivatives` for `time > 0.5`. The parameter `k` selects the fault: 2 returns `Error`, 3 `Fatal`, 4 dereferences NULL (SIGSEGV), 5 calls `sleep(30)` once, 6 calls `abort()`, 7 returns `Discard`, 8 returns a NaN derivative.
   - **Reference FMUs v0.0.42**: the 2.0 and 3.0 `linux64` binaries.
4. Ran four probes: settings and results, error surfaces (one child process per case, so crashes are visible as exit codes), timeouts and per-run cost, and determinism (hashes of `result.tobytes()`).

**(verified)** means read in source or spec, or measured here. **(inference)** means my reasoning from verified pieces.

## Short answer

- **Every time and solver setting has an FMPy argument, but the defaults differ from OMC's and must never be left to FMPy.**
  - ME ignores `DefaultExperiment.stepSize`. With no interval, FMPy picks its own grid (measured: 0.001 instead of the FMU's 0.1).
  - CS ignores `solver` entirely; ME ignores `tolerance` unless CVode is the solver.
  - `variable_filter` maps onto `output=` only after mtools expands the regex against the model description, because FMPy silently drops unknown names.
  - `emit_protected` and `abort_on_chattering` have no FMPy equivalent.
- **Results need a small adapter:**
  - Cast FMI 2.0 `int32` (Integer and enumeration) to `int64`. FMI 3.0 brings per-width dtypes (`float32`, `int8` … `uint64`).
  - Reorder the columns: FMPy groups them by type, not in the requested order.
  - Drop parameter columns.
  - ME repeats rows at events like OMC. The stop time is repeated only when an event falls on it, while OMC always repeats it.
  - CS has no event rows at all.
- **Errors are mostly bare `Exception`s, raised late, and leak resources.**
  - Unknown and non-settable start values are reported only after initialisation.
  - FMI status ≥ `Discard` raises `FMICallException` with a `.status`. **Under ME + CVode, however, the FMU's error is swallowed inside a ctypes callback and a misleading follow-up error is raised.** After `fmi2Fatal`, FMPy even keeps calling the FMU.
  - CS `fmi2Discard` without termination loops forever.
  - A failing run leaks the FMU instance and its extraction directory.
  - **A segfault or `abort()` in the FMU kills the Python process** (exit 139 / 134), in ME and in CS.
- **Timeouts need a subprocess.**
  - FMPy's `timeout` is cooperative: it is checked once per loop pass and silently returns a truncated result. It cannot interrupt a blocking FMI call (it returned after 30.0 s with `timeout=1`).
  - SIGALRM can be swallowed inside the CVODE callback, after which the run never ended.
  - A killed child process stops within 1 s.
  - Cost per run on top of the 11.8 ms run itself: `fork` +9-12 ms, `forkserver` +124 ms, `spawn` +175 ms, a fresh interpreter +164 ms (mostly the 125 ms `import fmpy`).
- **Determinism: bit-identical.** 12 FMU/mode combinations gave a single hash each over 5 runs × 3 processes. The exception is a run cut short by FMPy's wall-clock `timeout`.

## 1. `RunSettings` → FMPy

`simulate_fmu` keyword arguments are listed at `simulation.py:622-652`. "DE" is `<DefaultExperiment>`.

| `RunSettings` field (`session_config.py:79-103`) | OMC C today (`run.py:118-134`) | FMPy, Model Exchange | FMPy, Co-Simulation | Default when unset (FMPy) |
|---|---|---|---|---|
| `start_time` | `-startTime` | `start_time` → `fmi2SetupExperiment(startTime)` (`simulation.py:958`) / FMI 3 `enterInitializationMode(startTime)` (`:1010`) | same; FMI 2 `setupExperiment` at `:1243` | DE `startTime`, else `0.0` (`:728-736`) |
| `stop_time` | `-stopTime` | `stop_time`; also passed to the FMU as `stopTime` (`set_stop_time=True`) | same | DE `stopTime`, else `start_time + 1` (`:738-744`) |
| `interval` | `-stepSize` | `output_interval`: the regular grid `start + (n+1)*interval` (`:1093`), plus event rows | `output_interval` **is** the communication step size. The last partial step to `stop_time` happens only if `canHandleVariableCommunicationStepSize`; otherwise the run silently stops before `stop_time` (`:1298-1306`) | **ME ignores DE `stepSize`**: `auto_interval` gives 500-1000 points (`:933-935`, `util.py:712-733`); measured 0.001 on `Types` (DE `stepSize=0.1`). **CS**: `fixedInternalStepSize`, else DE `stepSize`, doubled until ≤1000 steps (`:754-765`); measured 0.1 |
| `tolerance` | `-tolerance` | `relative_tolerance` → CVode `rtol`, with `abstol = nominal × rtol` (`sundials/__init__.py:105,116`). Not passed to the FMU: `fmi2SetupExperiment` is called without a tolerance (`:958`). Ignored by `Euler` | FMI 2: `setupExperiment(tolerance=…)` (`:1243`); FMI 3: `enterInitializationMode(tolerance=…)`. The FMU may ignore it (FMI 2.0.4 §2.1.6, [`2_1_common_api.adoc` L574-L578](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/2_1_common_api.adoc#L574-L578)). **Measured:** OMC CS FMU, rtol 1e-3 vs 1e-9 → max \|Δx\| = 0 (it runs forward Euler) | DE `tolerance` (`:746-747`), else ME `1e-5` (`:930-931`); CS: none |
| `solver` | `-s` (`dassl`, `cvode`, …) | `solver='CVode'` (default) or `'Euler'`, case-sensitive. Anything else raises `Exception("Unknown solver: dassl. Must be one of 'Euler' or 'CVode'.")` (`:1052-1064`, measured with `dassl` and `cvode`) | **None.** The FMU's internal solver is fixed at export (OMC CS: forward Euler unless exported with `--fmiFlags=s:cvode`, per the earlier note). `solver=` is silently ignored (measured: `solver='dassl'` runs) | `'CVode'` |
| `variable_filter` | `-variableFilter` (OMC regex, full match) | `output=[names]`. Only exact names; unknown names are **silently dropped** (`Recorder`, `simulation.py:90-104`; measured `output=['x','nope','hidden']` → `time, x`). `None` → outputs, else ≤5 states, else ≤5 locals (`:33-62`) | same | outputs only (measured `Types`: `time, out`) |
| `emit_protected` | `-emit_protected` | **None at run time.** An FMU exposes only what its exporter put in `modelDescription.xml`. For OMC exports this is the **build-time** flag `--fmiFilter`, default `protected`, which hides protected variables ([`Flags.mo` L1260-L1261](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/Flags.mo#L1260-L1261); measured: protected `hidden` is absent) | same | — |
| `timeout` | process-group kill (`process.py:40-65`) | `timeout=` seconds of wall clock, checked once per loop pass. **Expiry silently `break`s and returns the rows so far, with no exception** (`:1087-1088`) | same (`:1283-1284`) | none |
| `abort_on_chattering` | `-abortSlowSimulation` | **None.** Measured on `Chatter` (`der(x) = if x > 0 then -1 else 1`): ME CVode gets stuck at t ≈ 1.0 recording ~14,000 event rows/s until the timeout (rows=14029 after 1 s, 142101 after 10 s) and has no end otherwise; ME `Euler` and CS run to `stop_time` without complaint | same | — |
| `parameters` | override file (`-overrideFile`) | `start_values={name: value}`, applied in Instantiated and again in Initialization Mode according to causality, variability and `initial` (`:913-926`, `:980-984`). With `validate=True`, leftover names raise **after** initialisation (`:1034-1036`). Values are coerced with the variable's Python type (`:553-561`) | same (`:1243-1270`) | the FMU's start values |

Notes on the mapping:

- **Names.** `mtools.internal.omc.parameters.expand_parameters` gives dotted names and 1-based `m[1,2]` indices. OMC's FMU variables use the same scalarised names (`Types` shows `der(x)`, and arrays follow the same convention in OMC CSVs). So `start_values` can take the flattened dict unchanged **(inference; array parameters were not exercised)**. FMI 3.0 array variables are real arrays with a `shape` and take a list (`simulation.py:553-559`).
- **Defaults from the FMU.** OMC wrote the `experiment` annotation into `<DefaultExperiment startTime="0.0" stopTime="1.0" tolerance="1e-6" stepSize="0.1"/>` (measured). The FMI standard makes DE advisory ("A tool may ignore this information"; FMI 2.0.4 §2.2.5 [`2_2_common_schema.adoc` L700-L705](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/2_2_common_schema.adoc#L700-L705)). FMI 3.0 says `stepSize` "has no defined meaning" for ME ([`2_4_common_schema.adoc` L810-L817](https://github.com/modelica/fmi-standard/blob/v3.0.2/docs/2_4_common_schema.adoc#L810-L817)). DE has no solver field. **(inference)** To match the backend's "every setting explicit" rule (spec `:178`), mtools should read DE itself (`read_model_description(...).defaultExperiment`) and always pass `start_time`, `stop_time`, `output_interval` and `relative_tolerance`. Without that, ME runs on FMPy's grid rather than the FMU's.
- **Settable start values** (measured on `Types`, ME and CS alike):

  | `start_values` | Result |
  |---|---|
  | `k`, `n`, `flag` (`causality="parameter"`), `x` (state, `initial="exact"`) | applied |
  | `k2` (bound parameter → `calculatedParameter`), `kf` (`final`), `y` (alias of `x`), `der(x)`, `mode` | `Exception: The start values for the following variables could not be set: k2` |
  | `count` (discrete, `initial="exact"`) | accepted, but no visible effect (count still ends at 4) |
  | `n=2.7` (Integer) | **silently truncated to 2** (`int(2.7)`) |
  | `n="2"`, `flag="false"`, `flag=0` | accepted |
  | `flag="maybe"` | `Exception: … could not be converted to Boolean` |
  | `k="abc"` | `ValueError: could not convert string to float: 'abc'` |
  | `k=(2.0, "s")` | `Exception: Variable k has no unit but the unit "s" was specified …` |

  The OMC backend instead rejects unknown and protected names with `ConfigError` **before** the run (`parameters.py:73`, spec `:182`). The FMU equivalent of "known parameter" is `causality in {parameter}` with `variability in {fixed, tunable}`. **(inference)** mtools should check names and value types against the model description up front, rather than rely on FMPy's late, untyped error.

## 2. Results

| Aspect | FMPy | mtools contract (spec `:194-200`, `matfile.py:26`) | Adapter needed |
|---|---|---|---|
| Container | `SimulationResult`, a numpy structured array; `time` first (`simulation.py:20-30`, `:80`, `:165-174`) | `pandas.DataFrame`, `time` first | `pd.DataFrame({n: r[n] for n in r.dtype.names})` |
| FMI 2.0 dtypes | Real `float64`, Integer **and Enumeration** `int32`, Boolean `bool` (`:108-111`; measured on `Types`: `count`, `mode`, `n` int32; `on`, `flag` bool) | float64 / int64 / bool | `int32 → int64` |
| FMI 3.0 dtypes | one dtype per FMI type: `float32`, `float64`, `int8`, `uint8`, … `int64`, `uint64`, `bool`; Enumeration → `int64` (`:111-126`; measured on Reference `Feedthrough` 3.0) | float64 / int64 / bool only | decide: widen to float64/int64 (`uint64` cannot always fit `int64`) or extend the contract |
| String, Binary, Clock | requested names are **silently dropped** (only the types above become columns; measured `String_*` and `Binary_*` on Feedthrough 3.0) | not representable | report or reject |
| Column order | grouped by type (all Real, then Integer, then Boolean), each in model-description order, **not** the `output=` order (measured `output=['on','out','count','x']` → `time, x, out, count, on`) | file order | reorder if the order matters |
| Parameter columns | recorded like any variable if listed (`k`, `k2`, `n`, `flag` became constant columns) | "no parameter columns" | exclude `causality ∈ {parameter, calculatedParameter}` and `variability = constant` when expanding `variable_filter` |
| Event rows (ME) | `record_events=True` (default) records the left limit before the event update and the right limit after it, so two rows share a time (`:1084`, `:1136-1139`). Measured `Types`, interval 0.1: time events at 0.25, 0.5, 0.75 and 1.0 and a state event at 0.6931474523 each give a duplicated time; 19 rows. `record_events=False` → 11 grid rows only | repeated event rows kept | none |
| Event rows (CS) | **none**: one row per communication point (`:1274`, `:1320`). Events inside a step show up only at the next communication point (measured: `on` turns true at 0.7, the state event is at 0.693) | — | inherent to CS; document |
| Stop-time row | ME: repeated **only if an event falls on `stop_time`** (measured: `Types` has a `sample` at 1.0 → `1.0, 1.0`; Reference BouncingBall → single 1.2 row). CS: never repeated | OMC always repeats the stop-time row (spec `:198`; earlier note: 2002 vs 2001 rows) | none for FMU-vs-FMU tests; matters only against native OMC |
| Grid | `start + (n+1)*interval` with `math.isclose` (rel 1e-9) closeness (`:1093`); times like `0.30000000000000004` appear. A non-dividing interval ends with a short step to `stop_time` (measured 0.3 → `…, 0.8999999999999999, 1.0`) in ME and in CS when variable steps are allowed | — | — |
| Aliases | FMI 2: aliases share a `valueReference` (FMI 2.0.4 §2.2.7, [`2_2_common_schema.adoc` L1203-L1224](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/2_2_common_schema.adoc#L1203-L1224)). Each listed name becomes its own column (measured `y == x` exactly). FMI 2 has no negated alias; OMC exports `ny = -x` as a separate variable (measured `ny == -x`). FMI 3 `<Alias>` children are expanded into extra model variables, so they can be listed too (`model_description.py:827-833`, `:974-987`) | the reader resolves negated aliases (`matfile.py`) | none |
| `der(...)` | recorded when it is a model variable and listed (OMC `der(x)`, Reference `der(h)`); never in the default selection | `der(x)` columns present | include via the expanded filter |
| Partial result | none: on an exception the `Recorder` is lost with the frame (`simulation.py:800-810`) | `SimulationError.partial_result` | **(inference, untested)** `step_finished(time, recorder)` (`:1206`, CS `:1391`) receives the `Recorder`, so mtools could keep a reference and call `recorder.result()` after a failure. With a subprocess, the child would have to stream rows back |

## 3. Errors

All raised exceptions are `builtins.Exception`, `ValueError`, `RuntimeError` or `fmpy.fmi1.FMICallException(Exception)`. `FMICallException` carries `.function` and `.status` (`fmi1.py:123-138`); FMPy raises it for any status `> Warning`, i.e. `Discard`, `Error` and `Fatal` (`fmi1.py:366-369`).

**FMI status semantics.** FMI 2.0.4 §2.1.3, [`2_1_common_api.adoc` L293-L313](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/2_1_common_api.adoc#L293-L313):

- After `fmi2Error`, "the simulation cannot be continued with this FMU instance", and `fmi2FreeInstance` or `fmi2Reset` must be called.
- After `fmi2Fatal`, "it is not possible to call any other function for any of the FMU instances".

FMI 3.0.2 §2.2.3 ([`2_2_common_mechanisms.adoc` L219-L234](https://github.com/modelica/fmi-standard/blob/v3.0.2/docs/2_2_common_mechanisms.adoc#L219-L234)) says the same for `fmi3Error`/`fmi3Fatal`.

Measured outcomes; each case ran in its own child process:

| Case | ME, `CVode` | ME, `Euler` | CS |
|---|---|---|---|
| Unknown or non-settable start value | `Exception: The start values … could not be set: muu`, raised after initialisation | same | same |
| Bad value type | `ValueError` or `Exception` (see §1) | same | same |
| Unknown `output` name | silently dropped | same | same |
| Unknown solver | `Exception: Unknown solver: …` | — | ignored |
| `Faulty2` k=2: FMU returns `Error` from `getDerivatives` | **The FMU's error is swallowed.** `CVodeSolver.f` runs as a ctypes callback; the `FMICallException` is printed as `Exception ignored on calling ctypes callback function` (10×) and CVode gets an undefined return value. The run then raises `FMICallException: fmi2SetContinuousStates failed with status 3 (error)`, after the FMU logged `fmi2SetTime: Illegal call sequence.` 10 times | `FMICallException: fmi2GetDerivatives failed with status 3 (error)`; the FMU logger message is `injected error at t=0.6` | `FMICallException: fmi2DoStep failed with status 3 (error)` |
| k=3: FMU returns `Fatal` | swallowed as above. CVode reports "the right-hand side routine failed in an unrecoverable manner"; the run raises `FMICallException: fmi2SetContinuousStates … status 3`. **FMPy called the FMU again after `Fatal`** (`fmi2SetContinuousStates: Illegal call sequence.`), contrary to §2.1.3 | `FMICallException: fmi2GetDerivatives failed with status 4 (fatal)` | `FMICallException: fmi2DoStep failed with status 4 (fatal)` |
| k=7: FMU returns `Discard` | swallowed; raises `RuntimeError: CVode error (code -8) … right-hand side routine failed in an unrecoverable manner` | `FMICallException: … status 2 (discard)` | **endless loop.** `fmi2Discard` without `fmi2Terminated` neither advances time nor stops (`simulation.py:1331-1344`). With `timeout=3` it returned silently: 241,860 rows, all at t ≤ 0.6. Without a timeout it was killed by `timeout 120` (exit 124) |
| k=8: NaN derivative (solver failure) | `RuntimeError: CVode error (code -1) … At t = 0.5, mxstep steps taken before reaching tout.` plus SUNDIALS `[ERROR]`/`[WARNING]` lines on stderr | **returns** a result full of NaN, with no error | returns NaN, with no error |
| OMC `BlowUp` (`der(x) = x^2`, finite-time blow-up at t=1) | `RuntimeError: CVode error (code -1) … At t = 0.999965111496019, mxstep steps taken …` (CVode `maxNumSteps=500`, `sundials/__init__.py:50`) | returns x(2) = 5.6e103 | returns 5.6e103 |
| OMC `Assert` (`assert(x > 0.5, …)`, violated at t ≈ 0.69) | `FMICallException: fmi2CompletedIntegratorStep failed with status 3 (error)`. The assert text goes to **stdout from inside the FMU** (`LOG_ASSERT … The following assertion has been violated at time 0.700000`), not through the FMI logger callback (0 callback messages) | same | `FMICallException: fmi2DoStep failed with status 3 (error)` |
| k=4: NULL dereference | **process dies, SIGSEGV (exit 139)** | exit 139 | exit 139 |
| k=6: `abort()` | **process dies, SIGABRT (exit 134)** | exit 134 | exit 134 |

More detail on these outcomes:

- **Why the CVode path masks errors (verified).**
  - `CVodeSolver.f` (`sundials/__init__.py:138-149`) and `g` are ctypes callbacks.
  - When a Python callback raises, CPython writes the exception as "unraisable" and does not set the C return value ([`callbacks.c` L232-L235](https://github.com/python/cpython/blob/3.11/Modules/_ctypes/callbacks.c#L232-L235)). That is why one run saw "repeated recoverable" and another "unrecoverable" RHS errors.
  - `CVodeSolver.step` then calls `set_x` on an FMU that is already in the Terminated state before checking the flag (`:173-185`). That call is the exception the caller sees.
  - Euler and CS call the FMU directly, so the original status surfaces.
- **Logging.**
  - With no `logger=`, FMU messages go to stdout through `print` (`fmi1.py:96-106`), e.g. `[ERROR] injected error at t=0.6`.
  - `logger=callback` receives `(status, category, message)` (measured with the Reference-based FMU).
  - OMC FMUs print their runtime logs (`LOG_ASSERT`) to the process's stdout directly, so capturing them in-process needs fd-level redirection. A subprocess captures them for free **(inference)**.
  - SUNDIALS writes `[ERROR]`/`[WARNING]` lines to stderr.
- **Resource leaks on failure (verified).** `simulate_fmu` frees the instance and removes the extraction directory only on the success path (`simulation.py:800-808`, no `try/finally`). Measured: a failed run left its `tmp…/binaries` extraction directory behind. Repeated failures in a long sweep therefore accumulate loaded libraries and temp dirs in-process.
- **Same process after `Error`/`Fatal`.** A fresh run of `Faulty2` in the same process succeeded after each of k=2, 3 and 7. This holds only for this FMU's per-instance state; FMI 2.0.4 §2.1.3 says `fmi2Fatal` corrupts *all* instances, so it cannot be relied on.

**Mapping to `mtools.errors` (inference).** Bad names or values → `ConfigError`, if mtools pre-validates against the model description (FMPy's own messages arrive only after initialisation). Every FMI status, CVode error and NaN/terminate condition → `SimulationError`. A dead child (SIGSEGV/SIGABRT) → `SimulationError` "crashed with SIGSEGV", which needs a subprocess, as on Cpp today (`run.py:79-95`). Euler and CS return NaN or overflowing values silently, so a finite-value check would be needed to report them.

## 4. Timeouts

| Mechanism | What happened (measured) | Verdict |
|---|---|---|
| FMPy `timeout=1` on `Chatter`, ME CVode | returned after 1.03 s with 14,029 rows, last t = 1.0000000001 of 2.0; no exception | works only between loop passes; truncation is **silent** (detect via `time[-1] < stop_time`) |
| FMPy `timeout=1` on `Faulty2` k=5 (one FMI call blocks 30 s) | returned after **30.01 s** | cannot interrupt a blocking FMI call |
| `signal.setitimer` / SIGALRM handler raising, blocking FMI call | `Alarm` raised after 1.00 s | interrupts `sleep` (EINTR), but in general the handler runs only when control returns to Python **(inference)**, and the FMU is left mid-call |
| SIGALRM handler raising, `Chatter` ME CVode | the `Alarm` was raised inside `CVodeSolver.f` and **swallowed** as `Exception ignored on calling ctypes callback function`. **The run never ended**; it was stopped externally (first `timeout_probe.py` run; not repeated) | unusable with CVode |
| Child process (`multiprocessing` `fork`/`forkserver`/`spawn`), `kill()` after 1 s, blocking FMI call | killed after 1.00-1.04 s, exit code −9 | reliable; also isolates SIGSEGV/SIGABRT and leaks |

So `settings.timeout` with `SimulationTimeout` semantics needs the run in a separate process that is killed on expiry. That is the same model as `process.execute` (new session, `killpg`, `process.py:40-65`). FMPy's own `timeout` is at most a soft limit inside the child.

**Per-run cost** (`Types` ME, interval 0.01, 3 columns; median of 20 in-process or 10 subprocess runs; 4 cores):

| Way to run | Median per run | Overhead vs. in-process |
|---|---|---|
| in-process, FMU zip (extracts on every call, `simulation.py:774`) | 17.8-19.7 ms | +6-8 ms |
| in-process, pre-extracted directory | **11.8 ms** | — |
| one `fork` child per run, result via `Queue` | 20.2-23.4 ms | +9-12 ms |
| one `forkserver` child per run | 136 ms | +124 ms |
| one `spawn` child per run | 187 ms | +175 ms |
| fresh `python -I` per run (`subprocess.run`, result via `.npy`) | 176 ms | +164 ms |
| ↳ of which: bare interpreter start / `import fmpy.simulation` | 13.0 ms / 138.5 ms | — |

Sweep implications **(inference from these numbers)**:

- **Overhead for 100 points:** about +1 s with `fork`, or +12-18 s with `forkserver`, `spawn` or a fresh interpreter.
- **Reusable workers** (a pool that pre-imports FMPy and is replaced only when a run times out or crashes) would bring the cost close to `fork`'s, with any start method.
- **`fork` caveats:**
  - Python 3.12+ warns when forking a multi-threaded process.
  - Python 3.14 made `forkserver` the POSIX default ([`multiprocessing.rst` L140-L149, L190-L194](https://github.com/python/cpython/blob/main/Doc/library/multiprocessing.rst)).
  - So mtools would have to request `fork` explicitly, or use a pre-warmed worker.
- **Extraction:** extract once per FMU (pass the directory to `simulate_fmu`) to save about 6 ms per run, and to avoid one temp dir per failed run.

## 5. Determinism

| FMU | ME CVode | ME Euler | CS | Rows (ME CVode / Euler / CS) |
|---|---|---|---|---|
| Reference `VanDerPol` 2.0 | 1 hash | 1 hash | 1 hash | 2001 / 2001 / 2001 |
| Reference `BouncingBall` 2.0 | 1 | 1 | 1 | 323 / 319 / 301 |
| Reference `Stair` 2.0 | 1 | 1 (same as CVode: no states) | 1 | 909 / 909 / 901 |
| OMC `Types` | 1 | 1 | 1 | 107 / 106 / 101 |

Each cell is 5 runs in one process × 3 separate processes (random `PYTHONHASHSEED`), interval 0.01, all numeric variables recorded. The SHA-256 of `result.tobytes()` was identical across all 15 runs in every cell.

Caveats:

- **Wall clock.** The only wall-clock input in FMPy's loop is `timeout`, so a run truncated by `timeout` is load-dependent.
- **The FMU itself.** Determinism also depends on the FMU (threads, clocks, random seeds); FMPy adds no randomness of its own (verified in the loop code, `simulation.py:1082-1213`, `:1281-1394`).
- **Other machines.** Not checked across machines or FMPy/SUNDIALS versions.

## Open questions

- **Partial results:** should mtools capture the `Recorder` through `step_finished` (untested here), or accept `partial_result=None` for FMU runs?
- **FMI 3.0 dtypes:** widen to float64/int64 to keep the three-dtype contract, or extend it? `uint64` values above 2⁶³ cannot fit `int64`.
- **Chattering:** with no `abort_on_chattering` equivalent, is a mandatory default `timeout` for FMU runs acceptable, or should mtools detect event storms itself (e.g. via `step_finished`, counting events per unit of simulated time)?
- **CS solver:** should the `solver` setting be rejected (`ConfigError`) for CS runs instead of being ignored, as Cpp rejects unsupported solvers today?
- **Upstream FMPy issues:** I did not check whether the swallowed CVode callback errors, the calls after `fmi2Fatal`, the CS `fmi2Discard` loop and the leaks on failure are already reported upstream.
- **Array parameters:** array parameters through `start_values` with OMC's `m[1,2]` names were not exercised.

## Reproduction

Everything is under `/tmp/fmpy-run-settings/`:

- `scripts/`: the probes;
- `omc/`: Modelica models and exported FMUs;
- `faulty-src/` and `fmus/`: the fault-injecting FMU;
- `dl-reffmus/`: Reference-FMUs v0.0.42, unzipped from the release zip with sha256 `b6b4a195…1e97`;
- `spec/`: downloaded spec and source files;
- `*.out`: raw outputs.

Downloaded files were kept in their own directories, passed as arguments, and read with `python -I`. Nothing was added to the repo or to `pyproject.toml`.

```bash
# FMI 2.0 FMUs from OMC 1.27.2 (Types, Assert, BlowUp, Chatter), ~25 s
cd /tmp/fmpy-run-settings/omc && omc export.mos      # buildModelFMU(M, version="2.0", fmuType="me_cs")

# Fault-injecting FMU: Reference-FMUs Dahlquist + switch on k in getDerivatives for time > 0.5
cd /tmp/fmpy-run-settings/faulty-src && gcc -shared -fPIC -O2 -DFMI_VERSION=2 -DDISABLE_PREFIX -Iinclude -IDahlquist \
  src/fmi2Functions.c src/common.c src/cosimulation.c Dahlquist/model.c \
  -o ../fmus/Faulty2/binaries/linux64/Dahlquist.so -lm   # + Dahlquist/FMI2.xml as modelDescription.xml, zipped

PY="uv run --no-project --python 3.11 --with fmpy==0.3.32 python -I"
cd /tmp/fmpy-run-settings/scripts
$PY settings_probe.py ../omc/Types.fmu ../dl-reffmus/zip/2.0 ../dl-reffmus/zip/3.0   # §1, §2 -> settings_probe.out
bash run_errors.sh ../fmus/Faulty2.fmu ../omc                                       # §3 -> errors.out (one child per case)
TMPDIR=$(mktemp -d) $PY leak_probe.py ../fmus/Faulty2.fmu                           # leaked extraction dir
timeout 540 $PY -u timeout_probe.py ../fmus/Faulty2.fmu ../omc/Types.fmu ../omc/Chatter.fmu  # §4 kill timings
timeout 500 $PY -u cost_probe.py   ../fmus/Faulty2.fmu ../omc/Types.fmu ../omc/Chatter.fmu   # §4 cost table
for p in 1 2 3; do $PY determinism_probe.py 5 ../dl-reffmus/zip/2.0/{VanDerPol,BouncingBall,Stair}.fmu ../omc/Types.fmu; done  # §5
```

Test models (`omc/*.mo`). Each has `experiment(StopTime=…, Interval=0.1, Tolerance=1e-6)`; `StopTime` is 1 for `Types` and `Assert`, 2 for the others:

- `Types`:
  - variables:
    - parameters `k=1`, `k2=2*k`, `final kf=5`, `Integer n=3`, `Boolean flag=true`;
    - state `x`, alias `y=x`, negated alias `ny=-x`;
    - `Integer count`, incremented by `when sample(0.25, 0.25)`;
    - `Boolean on = x < 0.5`, an enumeration `mode`, `output Real out`, protected `hidden`;
  - equation: `der(x) = -k*x`.
- `Assert`: `der(x) = -x`; `assert(x > 0.5, "x dropped below 0.5")`.
- `BlowUp`: `der(x) = x^2`, `x(0) = 1`.
- `Chatter`: `der(x) = if x > 0 then -1 else 1`, `x(0) = 1`.

Key numbers:

- **`Types` defaults:**
  - ME: 1007 rows on a 0.001 grid, columns `time, out`.
  - CS: 11 rows on a 0.1 grid.
  - ME, interval 0.1, all variables: 19 rows with 5 duplicated times (0.25, 0.5, 0.6931474523385249, 0.75, 1.0).
- **Tolerance 1e-3 vs 1e-9** (`Types`): ME CVode max \|Δx\| = 3.7e-3; OMC CS 0.
- **First timeout probe run:** printed only the swallowed `Alarm` traceback before it was stopped. Stdout was block-buffered, so the timings in §4 come from the bounded rerun (`timeout_probe.out`, `cost_probe.out`).
