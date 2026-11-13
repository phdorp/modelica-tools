# FMU-Based Tests Spec

Status: ready-for-agent
Source: charted and resolved on the map "Map: FMU-based tests through FMPy" (#69). Every decision below links to the ticket that holds its reasoning.

Terms follow `GLOSSARY.md`: **build**, **build config**, **build-time parameter**, **simulation target**, **run**, **run settings**, **result**, **partial result**, **diagnostics**, and the terms this spec adds: **given FMU**, **exported FMU**, **name map**.

## Problem Statement

mtools tests a Modelica model by running an experiment against it, alone or against a reference model, and every run goes through OMC's native simulation binaries. Users who work with FMUs can't use that:

- **A model that only exists as an FMU can't be tested.** A controller exported from Simulink or another tool can't be the candidate or the reference of a test, even though the experiment, its parameters and the expected behaviour are already written for the Modelica model.
- **A Modelica model can't be checked as an FMU.** A team shipping its model as an FMU has no way to run the same experiments against the FMU it ships, so export problems surface downstream.
- **Names don't line up.** A third-party FMU names its parameters and signals its own way, while the experiment uses the parameter dataclass's names, so the results of the two sides of a test can't be compared column by column.
- **Two FMUs rarely share a time grid.** Today's comparison needs identical rows. Two FMUs with different event handling, or a Model Exchange and a Co-Simulation FMU, never pass it, and there's no relative tolerance.

## Solution

An experiment written once runs against an FMU through FMPy, in the single-model test bases (`Experiment`, `ExperimentSweep`, …) and on either or both sides of the reference bases (`ExperimentReference`, …):

- **Two kinds of FMU, chosen only in the run config's `build`.** A **given FMU** is a file the user supplies, configured with `create_fmu_run(fmu_path=…)`. An **exported FMU** is a Modelica model that mtools exports with OMC's `buildModelFMU`, configured with `create_run(…, fmu=FmuExport())`. Experiments and test classes don't change.
- **Same run settings and parameters.** Time range, interval, tolerance, solver, variable filter and timeout mean what they mean for native runs, with the documented differences of FMI. Parameters are set from the same parameter dataclass.
- **A name map for given FMUs.** It translates the experiment's parameter names into the FMU's names and renames the FMU's result columns into the experiment's names, so tests, saved results, plots and comparisons see one vocabulary.
- **Comparisons that work across FMUs.** `assert_matches_reference()` gains a relative tolerance `rtol` and an opt-in `interpolate` mode that aligns two time grids.
- **Robust runs.** Each FMU run is isolated in its own child process, so a crashing FMU raises `SimulationError` instead of killing the test process, and `settings.timeout` stops a hung FMU. Exported FMUs are cached like native builds.
- **Optional dependency.** FMPy comes with the `modelica-tools[fmu]` extra. Without it, mtools and native runs work as before.

## User Stories

### Configuring an FMU run

1. As a test author, I want to point a run config at an FMU file with `create_fmu_run(fmu_path=…)`, so that I can test a model I only have as an FMU.
2. As a model developer, I want to run my Modelica model as an FMU with `create_run(…, fmu=FmuExport())`, so that my experiments check the FMU I ship.
3. As a test author, I want experiments, parameter groups and test classes to stay unchanged when a run config switches to an FMU, so that one experiment covers native and FMU runs.
4. As a test author, I want one registry to hold an exported-FMU candidate and a given-FMU reference, so that I can compare them in one test.
5. As a test author, I want an exported FMU to default to Model Exchange, and a given FMU to default to Model Exchange when it offers it and Co-Simulation otherwise, so that the solver and tolerance I configure apply wherever possible.
6. As a test author, I want to choose `fmu_type="me"` or `"cs"` explicitly, and get a `ConfigError` when a given FMU lacks the type, so that I always know which interface ran.
7. As a test author, I want a given FMU's `model_name` to default to its `modelName`, so that results are keyed without extra configuration.
8. As a Cpp user, I want to export an FMU from the Cpp target with a WARNING naming its known risks, so that I can still use it when C isn't an option.
9. As a Cpp user, I want `fmu_type="cs"` on Cpp to be a `ConfigError`, so that I never silently get Model Exchange when I asked for Co-Simulation.
10. As a user without FMPy installed, I want `import mtools` and native runs to keep working, and an FMU run to raise `ImportError` telling me to install `modelica-tools[fmu]` before anything is built, so that the fix is obvious and costs no export.

### Names and parameters

11. As a test author, I want to give a given FMU a name map `{experiment name: FMU name}`, so that its parameters and signals line up with the experiment's names.
12. As a test author, I want unmapped names to pass through unchanged, so that the map lists only the names that differ.
13. As a test author, I want a map entry that names a variable missing from the FMU, a collision with an unrenamed FMU variable, two entries pointing at one FMU name, or `time` in the map to be a `ConfigError` before the run, so that a typo can't silently drop a signal.
14. As a test author, I want parameters set from my parameter dataclass, flattened and expanded as for native runs, so that sweeps over FMU parameters work as they do today.
15. As a test author, I want every unknown name, non-settable name and wrongly typed value reported together in one `ConfigError` before the run, each naming its `settings.parameters.<key>` (and the FMU name when it was mapped), so that I fix all problems at once.
16. As a test author, I want a parameter that a given FMU fixed to be a `ConfigError` saying the FMU can't be rebuilt, so that I don't wait for a sweep to fail point by point.
17. As a model developer, I want a sweep over a build-time parameter of an exported FMU to export a cached variant FMU automatically, as for native builds, so that ADR 0001 keeps working.

### Running and results

18. As a test author, I want unset start, stop, interval and tolerance to come from the FMU's `DefaultExperiment`, then OMC's defaults, so that an FMU runs like the model it came from.
19. As a test author, I want Model Exchange runs to accept only `cvode` and `euler` and reject any other solver with a `ConfigError`, so that no solver is silently substituted.
20. As a test author, I want a Co-Simulation run with an explicit `solver` to WARN that the FMU's built-in solver runs instead, so that a forced Co-Simulation doesn't fail the test.
21. As a test author, I want a Co-Simulation interval that can't reach `stop_time` on an FMU with a fixed communication step to be a `ConfigError`, so that a run never silently stops early.
22. As a test author, I want `variable_filter` to keep its meaning, matched against the experiment's names, so that one regex works on both sides of a reference test.
23. As a test author, I want FMU results as DataFrames with native column types (`float64`, `int64`, `bool`) and without parameter columns, so that `save_solutions`, `load_solution` and the plotting tool work unchanged.
24. As a test author, I want an OMC-exported Model Exchange FMU with `sample()` events to run with CVODE at any output interval, so that FMPy's "tout too close" defect doesn't fail my tests.

### Failures

25. As a test author, I want an FMU that segfaults or aborts to raise `SimulationError` "crashed with SIG…", so that one bad FMU doesn't kill my test session.
26. As a test author, I want `settings.timeout` to stop a hung or chattering FMU and raise `SimulationTimeout`, so that CI never hangs.
27. As a test author, I want a failed FMU run's `SimulationError` to carry the FMU's logged messages, the first failed FMI call and the final exception, so that I can see why it failed.
28. As a test author, I want the rows recorded before a failure or timeout as a partial result, so that I can see where the run went wrong.
29. As a test author, I want an unusable FMU file (missing, not a zip, no `modelDescription.xml`, no `linux64` binary) to be a `ConfigError` naming `build.fmu_path`, so that `SimulationError` always means the FMU ran and failed.
30. As a test author, I want a Co-Simulation CVODE failure caused by an event on the communication grid to end with a hint naming the cause and the fixes, so that I know to switch to Model Exchange, Euler or another interval.
31. As a debugger, I want `MTOOLS_KEEP_RUNS=1` to keep the run directory with the extracted FMU and add its path to the diagnostics, so that I can inspect a failed run.

### Comparing

32. As a test author, I want `assert_matches_reference()` to apply the same rules to FMU and native reference tests, so that I learn one set of rules.
33. As a test author, I want an `rtol` class variable next to `eps`, so that I can compare signals of very different magnitudes.
34. As a test author, I want an opt-in `interpolate` mode that aligns the candidate onto the reference's time points, so that two FMUs with different event rows or grids can be compared.
35. As a test author, I want a length mismatch in the default mode to point me at `interpolate`, so that I find the option when I need it.

### Caching and speed

36. As a model developer, I want exported FMUs cached by content like native builds, so that a sweep exports once and a repeated sweep exports nothing.
37. As a model developer, I want an export to be redone when OMC, the C compiler, the CMake on `PATH`, the FMU type or `emit_protected` changes, so that a cached FMU is never stale.

### Docs and examples

38. As a new user, I want one doc page on FMU runs with the known limits listed, so that I can tell what works before I start.
39. As a new user, I want a worked FMU reference test in the `examples` workspace, so that I can copy a setup that CI keeps working.

## Implementation Decisions

### Config schema ([How a run config points at a given or exported FMU](https://github.com/phdorp/modelica-tools/issues/72), [Name map between experiment terms and a given FMU](https://github.com/phdorp/modelica-tools/issues/75))

- **The model kind lives only in the run config's `build`.** A native build, a `Build` with `fmu` set (exported FMU), or a `FmuFile` (given FMU). `RunSettings`, experiments and the test classes don't change.
- **`FmuExport`**, a new public dataclass in `session_config` with one field `fmu_type: str = "me"`. `Build` gets an optional field `fmu: FmuExport | None = None`; `None` keeps today's native run. Sources, libraries, flags, the build cache and ADR 0001 variants apply unchanged.
- **`FmuFile`**, a new public dataclass in `session_config`: `fmu_path` (must exist when the run is validated), `model_name: str | None = None`, `fmu_type: str | None = None`, `name_map: dict[str, str] = {}`. An unset `model_name` comes from the FMU's `modelName` and keys the results.
- **`SimulationRun.build`** is annotated `Build | FmuFile` through `session_config`'s existing `TYPE_CHECKING` alias pattern (`Any` at run time). Verified: a `FmuFile` instance passed through `build_run_config` composes, accepts overrides such as `build.fmu_type=cs`, rejects `Build`-only keys, and instantiates as `FmuFile`. No OmegaConf `Union` is involved.
- **Registry entry points.** `create_run(…, fmu=None)` gains the `fmu` argument. A new `create_fmu_run(fmu_path, model_name=None, fmu_type=None, name_map=None, settings=None, selections=None, include_experiment_group=False, name=None)` mirrors `create_run`'s other arguments.
- **`fmu_type`** is `"me"` or `"cs"`; anything else is a `ConfigError`. Exported FMUs default to `"me"`. A given FMU with `fmu_type=None` runs Model Exchange when it offers it, otherwise Co-Simulation; requesting a type the FMU lacks is a `ConfigError`.
- **Cpp target.** An export from `target="Cpp"` logs one WARNING naming the known risks: Model Exchange only; time events (`when sample(...)`) broke silently under FMPy; resources and shared libraries aren't copied. `fmu_type="cs"` on Cpp is a `ConfigError`.
- **Name map** (given FMU only). One one-to-one mapping `{experiment name: FMU name}` of exact, fully flattened and expanded names, for parameters and signals alike (`"ctrl.k": "Kp"`, `"y0[1]": "Y0_1"`). No prefixes or patterns. It lives only on `FmuFile`: candidate and reference carry their own, and sweeps and settings overrides never touch it. The docs say to set it in Python or YAML; single dotted keys on the command line are not supported.

### Validation order

1. Instantiate and check the run config as today. A `FmuFile` build, or a `Build` with `fmu` set, without FMPy importable raises `ImportError("FMU runs need FMPy: install modelica-tools[fmu]")` here, before anything is built or exported ([How fmpy is installed and which FMUs the tests run](https://github.com/phdorp/modelica-tools/issues/84)). It isn't a `ConfigError`: the config is valid, the environment lacks a package.
2. Given FMU: check the file. A missing file, a non-zip, a missing or unreadable `modelDescription.xml`, or no `linux64` binary is a `ConfigError` naming `build.fmu_path` ([How an FMU run is isolated, stopped and reports failures](https://github.com/phdorp/modelica-tools/issues/78)).
3. Exported FMU: export, or take the export from the cache. Export failures stay `TranslationError` / `CompileError`.
4. Check everything that needs the model description, and report every problem in one `ConfigError`: parameters, the name map, `fmu_type`, the solver and the Co-Simulation interval.
5. Start the run.

### Exporting ([What OMC's FMU export gives mtools](https://github.com/phdorp/modelica-tools/issues/70))

- The build script runs unchanged up to its last stage, which becomes `buildModelFMU(<model>, version="2.0", fmuType=<fmu_type>, fileNamePrefix="model")`. An empty return value is a failure. `model_FMU.makefile` tells a compile failure from a translation failure, as `model.makefile` does today.
- FMI 2.0 only (OMC 1.27.2 rejects 3.0). Export from C; Cpp as above.
- `emit_protected=True` exports with `--fmiFilter=internal`; otherwise OMC's default `--fmiFilter=protected` applies ([Which run settings an FMU run honours](https://github.com/phdorp/modelica-tools/issues/73)). With `internal`, OMC writes `$` in names as `_D_`.
- `emit_protected` is the only source of `--fmiFilter`: for an exported FMU, a `--fmiFilter` in `build.omc_flags` is a `ConfigError` naming `build.omc_flags`, as `--simCodeTarget` is. Other FMU flags such as `--fmiFlags=s:cvode` stay allowed and are part of the key through `omc_flags`.
- OMC calls the first `cmake` on `PATH`. Inside a venv with `modelica-tools[fmu]`, that is the CMake 4.x that FMPy depends on; an export with CMake 4.4.4 succeeded. OMC's package depends on `cmake` and `zip`.

### Run settings ([Which run settings an FMU run honours](https://github.com/phdorp/modelica-tools/issues/73))

The same rules apply to given and exported FMUs unless stated. Every value is checked before the run; a `ConfigError` names the config path.

- **Defaults.** Unset `start_time`, `stop_time`, `interval` and `tolerance` come from the FMU's `DefaultExperiment`. A field missing there takes OMC's default: start 0, stop 1, interval (stop − start)/500, tolerance 1e-6. mtools passes every value to FMPy explicitly and never relies on FMPy's defaults.
- **Solver, Model Exchange.** `"cvode"` (the default when unset) or `"euler"`, mapped to FMPy's `CVode` / `Euler`. Any other name is a `ConfigError`. The model's `__OpenModelica_simulationFlags` solver isn't consulted. Euler steps once per output interval.
- **Solver and tolerance, Co-Simulation.** An explicit `solver` logs a WARNING that the FMU's built-in solver runs instead. `tolerance` goes to the FMU through `setupExperiment`, without a warning; OMC's Co-Simulation FMUs ignore it.
- **Interval, Co-Simulation.** If the interval doesn't divide `stop_time − start_time` and the FMU lacks `canHandleVariableCommunicationStepSize`, it's a `ConfigError`.
- **`variable_filter`.** An OMC regex, full match, `time` always kept, matched against the experiment's names (after the name map).
- **`emit_protected`.** Exported FMU: applied at export and part of the cache key. Given FMU: no effect, with a WARNING when `True`.
- **`abort_on_chattering`.** No effect and no warning, as on Cpp.
- **`timeout`.** See Running.

### Parameters ([How experiment parameters reach an FMU](https://github.com/phdorp/modelica-tools/issues/74))

- `settings.parameters` is flattened and expanded as for the OMC backend (dotted names, 1-based row-major indexes), translated through the name map, and passed to FMPy as start values once, before initialisation.
- A name is settable if the model description gives it `causality="parameter"` with `variability` fixed or tunable, or `initial="exact"`. FMI 2.0 inputs aren't settable.
- Every name and value is checked against `modelDescription.xml` before the run. For an exported FMU this happens right after the export.
- **Given FMU:** an unknown name is a `ConfigError`. An existing but non-settable name (`calculatedParameter`, `constant`, anything else) is a `ConfigError` with its own message: the parameter is fixed in the FMU, and a given FMU can't be rebuilt.
- **Exported FMU:** ADR 0001 unchanged. If a requested name is a `calculatedParameter`, mtools exports a variant FMU of the `extends` wrapper, cached under a key with the build-time values, with today's INFO log. A `final` parameter fails as a `TranslationError`. A protected parameter is a `ConfigError`, also with `emit_protected=True`.
- **Value types**, a mismatch being a `ConfigError`: Real takes int or float; Integer takes integral values only (`2.7` is rejected, not truncated); Boolean takes `bool`; String takes `str`; Enumeration takes the item's integer or a qualified literal such as `'Mode.high'`. Unit tuples are rejected.
- Problem messages name `settings.parameters.<key>` and add the FMU name for a mapped name, e.g. `settings.parameters.ctrl.k (FMU name 'Kp'): …`.

### Name map checks ([Name map between experiment terms and a given FMU](https://github.com/phdorp/modelica-tools/issues/75))

Each is a `ConfigError` before the run, reported together with the parameter problems:

- an entry whose FMU name isn't in `modelDescription.xml` (naming `build.name_map.<key>`);
- two experiment names pointing at the same FMU name;
- `time` as a key or a value;
- a collision: an experiment name in the map that is also the name of another FMU variable which isn't itself renamed (map `{"x": "pos"}` while the FMU has its own `x`), checked against every FMU variable regardless of `variable_filter`. A swap (`{"a": "b", "b": "a"}`) is legal.

An experiment name nothing uses can't be detected and stays silent. FMI aliases get no special handling. Diagnostics from the FMU keep the FMU's names.

### Running ([How an FMU run is isolated, stopped and reports failures](https://github.com/phdorp/modelica-tools/issues/78), [What an FMU run does when an event lands on the output grid](https://github.com/phdorp/modelica-tools/issues/83))

- **One child process per run.** Every FMU run is a fresh Python interpreter started through the backend's existing process runner (new process group, combined output captured), whether or not `timeout` is set. Settings go in and the result comes out as files in the run directory. This costs about 165 ms per run; a reusable pre-warmed worker may replace it later without changing behaviour ([What is cached for FMU runs](https://github.com/phdorp/modelica-tools/issues/85)).
- **Run directory.** Each run extracts its FMU into a fresh run directory under `runs/` and deletes it when the run ends, however it ended. `MTOOLS_KEEP_RUNS=1` keeps it and adds `Run directory: <path>` to the diagnostics. FMPy's own temp directories are never used.
- **Timeout.** `settings.timeout` covers the whole child: interpreter start, `import fmpy`, extraction and the run. On expiry the parent kills the process group with SIGKILL and raises `SimulationTimeout`. Exporting is a build and stays outside the limit. FMPy's own `timeout` is never used.
- **No chattering guard.** A chattering Model Exchange FMU, or a Co-Simulation FMU that keeps returning `Discard`, runs until `timeout`, or forever without one. The docs recommend a `timeout` for FMU tests.
- **CVODE guard, Model Exchange.** On every Model Exchange run with `solver="cvode"`, the child wraps FMPy's private `fmpy.sundials.CVodeSolver.step` so that a step is skipped, returning no state event and `tNext`, only when CVODE would refuse it: `|tNext − t| < 2·DBL_EPSILON·max(|t|, |tNext|)`. Measured with FMPy 0.3.32 on three `sample()` models over 30 intervals each: 90/90 pass with correct counters, against 12–26 failures out of 30 per model without the guard. It's never installed for `euler`. Drop it once FMPy fixes [#882](https://github.com/CATIA-Systems/FMPy/issues/882).
- **Event-indicator guard, Model Exchange.** On every Model Exchange run, whatever the solver, the child wraps `fmpy.fmi2.FMU2Model.getEventIndicators` so that the indicator buffer is zeroed before each call. OMC 1.27.2's Cpp export declares more event indicators than `fmi2GetEventIndicators` writes, and FMPy passes CVODE's uninitialised root buffers, so CVODE sometimes sees a fake root on almost every step. Without the guard, one cached Cpp FMU of a decaying state gave 109 rows (error 4.2e-6) in some runs and about 13238 rows (error 7.75e-4) in others; with it, 5 out of 5 runs gave 107 rows and 4.2e-6. FMI 2.0 requires every indicator to be set, so the guard changes nothing for FMUs that set them all. Drop it once OMC fixes the Cpp export.
- **Co-Simulation CVODE hint.** When a Co-Simulation run's diagnostics contain CVODE −27 / "tout too close", the `SimulationError` diagnostics end with one hint line. It names the cause (a `sample()` event within one float step of the communication grid, inside the FMU's own CVODE) and the fixes: `fmu_type="me"`, an export without `--fmiFlags=s:cvode` (Euler), or another interval. This applies to given FMUs too.

### Errors and diagnostics ([How an FMU run is isolated, stopped and reports failures](https://github.com/phdorp/modelica-tools/issues/78))

- `SimulationError` always means the FMU was loaded and the run failed. Its header is "Simulation of '…' failed:", or "Simulation of '…' crashed with SIG…:" when a signal killed the child.
- Failure diagnostics, in order of occurrence:
  1. messages the FMU logged through the FMI logger with status warning or worse;
  2. `LOG_*` entries an OMC-exported FMU printed, filtered as for C runs;
  3. the first failed FMI call (e.g. `fmi2GetDerivatives failed with status 3 (error)`), taken from the "Exception ignored" tracebacks when CVODE swallowed it;
  4. the exception that ended the run.

  Python tracebacks are dropped. The raw output is the fallback when nothing matches, and the child's full output goes to the DEBUG log.
- A successful run logs one WARNING with the FMU's warning-level logger messages and `LOG_ASSERT` / warning entries, as a C run does, and is otherwise silent.
- **Partial result.** When the run fails inside Python, the child writes the rows recorded so far (a `Recorder` kept through `step_finished`). It also saves them to the run directory about once per second of wall time, so a timeout or crash gives a partial result up to the last save, or `None` before the first. A partial result has the same columns and types as a full one.
- No check for NaN or infinite values, as on the OMC backend.

### Results ([How FMPy maps onto run settings and results](https://github.com/phdorp/modelica-tools/issues/71), [Which docs, example and plotting changes the spec includes](https://github.com/phdorp/modelica-tools/issues/86))

- A DataFrame with `time` first, then one column per variable kept by `variable_filter`, in `modelDescription.xml` order (not FMPy's grouping by type), named in the experiment's names. Parameter, calculated-parameter and constant columns are dropped, as in native results.
- Column types are cast to the native ones: every Real width to `float64`, every Integer width and enumeration to `int64`, Boolean to `bool`. String and Binary are left out, as FMPy does. A `UInt64` value outside the `int64` range raises a `SimulationError` naming the column.
- Rows are what FMPy produces: Model Exchange repeats rows at events and repeats the stop-time row only when an event falls on it; Co-Simulation has no event rows. Results are deterministic for the same FMU and settings.
- So `save_solutions`, `load_solution` and the plotting tool work unchanged.

### Comparing ([What assert_matches_reference compares for two FMUs](https://github.com/phdorp/modelica-tools/issues/76))

One set of rules for every reference test, FMU or native.

- **Signals.** Both sides must have exactly the same columns; a missing or extra signal is a failure. Each side's `variable_filter` is the only way to narrow them.
- **Tolerances.** New class variable `rtol: ClassVar[float] = 0.0` next to `eps` (absolute, default machine epsilon). Both apply to every compared column. No per-signal tolerances.
- **Default mode (`interpolate = False`).** Today's rule: same row count, then every column including `time` compared row by row, event rows included. A length mismatch's message points at `interpolate`.
- **Interpolation mode (`interpolate: ClassVar[bool] = True`).**
  1. On both sides, where a time repeats, only the last row is kept (the value after the event).
  2. It fails if any reference time point lies outside the candidate's time span; no extrapolation.
  3. The candidate is interpolated onto the reference's time points: linearly for Real; Boolean and Integer take the last value at or before the time point.
  4. Every signal is compared at every reference row with `rtol` and `eps`. Row counts need not match and `time` isn't compared.
- **Model Exchange vs. Co-Simulation.** Any combination, under the same rules, without a warning. The docs say a Co-Simulation result shows an event only at the next communication point and may use another embedded solver, so a mixed pair usually needs `interpolate` and a tolerance.

### Cache ([What is cached for FMU runs](https://github.com/phdorp/modelica-tools/issues/85))

- **Exported FMUs are builds.** `builds/<key>/` holds `model.fmu` and the build record. Validation by inputs (exports are never byte-identical because of the random GUID), atomic publish, `MTOOLS_NO_CACHE=1` (an uncached export goes into `runs/build-*`) and ADR 0001 variants work as for native builds. Hits and misses use today's log messages.
- **Key.** A C-target export's key is today's key plus `kind="fmu"`, FMI version `"2.0"`, `fmu_type`, `emit_protected`, and the `cmake --version` output of the `cmake` on `PATH`. Native keys don't change. Co-Simulation solver and tolerance need no field of their own: they come from the model's `experiment` annotation (in the source hash) or `--fmiFlags` in `omc_flags` (in the key).
- `me` and `cs` exports of one model are separate entries.
- **Given FMUs aren't cached.** Each run extracts the user's file into its run directory (about 40 ms for a 1 MB OMC FMU). `modelDescription.xml` is read in the parent on every run, without caching (about 12 ms).

### Installing ([How fmpy is installed and which FMUs the tests run](https://github.com/phdorp/modelica-tools/issues/84))

- `fmpy~=0.3.32` as the optional extra `modelica-tools[fmu]`; the `dev` extra pulls in the same pin, so the full suite and CI always have FMPy. The cap is deliberate: FMPy is pre-1.0 and this spec relies on 0.3.32 behaviour (the Model Exchange event loop, when start values apply, `step_finished`, the private `CVodeSolver.step`). Raising it is a checked step.
- FMPy is imported only for FMU runs, in the child process and in the parent's model-description checks.

### Docs and examples ([Which docs, example and plotting changes the spec includes](https://github.com/phdorp/modelica-tools/issues/86))

- **New `docs/fmu-runs.md`:**
  - given and exported FMUs, `create_fmu_run`, `FmuExport`, `name_map`;
  - which run settings apply;
  - isolation and timeouts;
  - caching;
  - `rtol` and `interpolate`, which apply to native reference tests too;
  - known limits:
    - Co-Simulation CVODE "tout too close" (FMPy #882);
    - Cpp FMU risks;
    - a `timeout` is recommended against chattering;
    - Model Exchange Euler steps once per output interval;
    - Linux FMUs only;
    - no FMU inputs;
    - native-vs-FMU reference tests are not supported;
    - set `name_map` in Python or YAML.
- **`README.md`:** a Features bullet, the `modelica-tools[fmu]` install line, and a short "FMU runs" section linking to the new doc.
- **`docs/omc-backend.md`** (build cache) and **`docs/hydra-registry.md`** (creating a run config) each get one line linking to it.
- **`examples`:**
  - It depends on `modelica-tools[fmu]`.
  - One new reference test where both sides are exported FMUs: the kinematic vehicle and its reference model, `target="C"`, `fmu=FmuExport()`.
  - A registered `fmu` run config that CI runs once from the command line.
  - Given FMUs appear only as a doc snippet with `name_map`.
- **Plotting tool:** no change.

### Glossary

`GLOSSARY.md` changes with this spec: new **Given FMU**, **Exported FMU** and **Name map**; widened **Build**, **Build config** and **Diagnostics**.

## Testing Decisions

- **What a good test looks like:** it checks behaviour through the seams below: exception types, config paths and stable phrases in messages, result values, columns and dtypes, and the backend's log records. It doesn't check run-directory layouts, child-process plumbing or private helpers. FMU tests live in `tests/fmu/`, carry a new `fmu` marker (like `cpp`), point `MTOOLS_WORK_DIR` at `tmp_path`, and fail rather than skip when FMPy is missing.
- **Test FMUs.**
  - FMUs exported by OMC during the tests from the existing test models cover exported FMUs. Loaded through `FmuFile`, they also cover given FMUs and the name map.
  - Vendored [Reference-FMUs v0.0.42](https://github.com/modelica/Reference-FMUs/tree/v0.0.42) (2-Clause BSD) cover another exporter and FMI 3.0: BouncingBall, Dahlquist, Stair and VanDerPol, each as FMI 2.0 and 3.0, about 2 MB. They go in `tests/fmu/reference_fmus/` with their LICENSE, version and sha256 in a README; nothing is downloaded.
- **Seam 1: public `sim_tools.simulate(config)`**, with run configs from `create_run(…, fmu=FmuExport(...))` and `create_fmu_run(...)`. This is the main seam. It covers:
  - config validation: `fmu_type`, Cpp `cs`, `--fmiFilter` in `omc_flags`, unusable FMU files, the missing-FMPy `ImportError` (by hiding the module);
  - run-setting defaults from `DefaultExperiment`, solver rules, the Co-Simulation solver WARNING and interval `ConfigError`, `variable_filter`, `emit_protected`;
  - parameters: flattening, all problems in one `ConfigError`, a parameter fixed in a given FMU, value types, an exported variant FMU for a build-time parameter;
  - the name map: renaming in and out, every map `ConfigError`, a swap;
  - result columns, their order and dtypes for FMI 2.0 and 3.0, and a save round trip through `save_solutions` / `load_solution`;
  - failures: a segfaulting FMU, an FMU error with its diagnostics, `SimulationTimeout` on a hung FMU, partial results after a failure and after a timeout, `MTOOLS_KEEP_RUNS`;
  - the CVODE guard: an exported `sample(0.1, 0.1)` model at interval 0.01, Model Exchange with CVODE, passes with the correct counter;
  - the Co-Simulation hint on an exported CVODE Co-Simulation FMU with `sample(0.1, 0.1)`;
  - cache behaviour through the backend's "built" / "reused" log records: a hit, a new export for another `fmu_type` or `emit_protected`, native and FMU builds of one model kept apart, `MTOOLS_NO_CACHE`.

  Prior art: `tests/session_tools/test_sim_tools.py`, `tests/session_tools/test_config_validation.py`, `tests/omc_backend/test_cache.py`, `tests/omc_backend/test_run_failures.py`.
- **Seam 2: the `mtools.testing` reference bases.**
  - Test classes compare an exported FMU with a given FMU, and Model Exchange with Co-Simulation using `interpolate`.
  - The comparison rules are tested on hand-made DataFrames, with no simulation: `rtol`, `interpolate`'s repeated-time handling, the extrapolation failure, linear vs. last-value interpolation, and the length-mismatch hint.
  - The `examples` FMU reference test sits on this seam.

  Prior art: `tests/session_tools/test_testing.py`, `examples/tests/test_reference_comparison.py`.
- **Two internal checks, without a simulation:**
  - Cache-key unit tests: the FMU fields change the key; native keys are unchanged. Prior art: `tests/omc_backend/test_cache_key.py`.
  - A check that fails if `fmpy.sundials.CVodeSolver.step` is missing or its signature changes, so an FMPy upgrade can't silently drop the CVODE guard.
  - A check that fails if `fmpy.fmi2.FMU2Model.getEventIndicators` is missing or its parameters are no longer `self, z, nz`, so an FMPy upgrade can't silently drop the event-indicator guard.

## Out of Scope

- Comparing a native OMC run against an FMU (cross-tool time grids and solver differences): not supported and not guarded; the docs say so.
- Input tables for FMUs with input variables.
- Windows FMUs on Linux through FMPy's Wine remoting; macOS and Windows hosts.
- FMI 3.0 export (OMC 1.27.2 can't); FMI 3.0 given FMUs are in scope.
- A pre-warmed, reusable child process.
- A chattering guard or default timeout for FMU runs.
- Changing tunable parameters during a run.
- Per-signal tolerances, a shared-columns mode or an explicit signal list in comparisons.
- Filing upstream fixes for FMPy #882 or OMC's sample-time arithmetic.
- Plotting-tool changes.

## Further Notes

- **Protected parameters of an exported FMU:** the model description doesn't mark protected variables (with the default `--fmiFilter=protected` they're absent, with `internal` they appear as `calculatedParameter`), and neither does OMC's `model_info.json`. Per [How experiment parameters reach an FMU](https://github.com/phdorp/modelica-tools/issues/74), the plan decides how mtools detects them so that they're a `ConfigError` rather than a variant export that fails.
- **Research** (throwaway branches, never merged):
  - [FMPy as a simulator for reference-model comparison tests](https://github.com/phdorp/modelica-tools/blob/research/fmpy-reference-comparison/docs/research/2026-11-09-fmpy-reference-comparison.md)
  - [What OMC's FMU export gives mtools](https://github.com/phdorp/modelica-tools/blob/research/omc-fmu-export/docs/research/2026-11-10-omc-fmu-export.md)
  - [How FMPy maps onto run settings and results](https://github.com/phdorp/modelica-tools/blob/research/fmpy-run-settings/docs/research/2026-11-10-fmpy-run-settings.md)
  - [Why CVODE reports "tout too close" on OMC-exported FMUs](https://github.com/phdorp/modelica-tools/blob/research/cvode-tout-too-close/docs/research/2026-11-11-cvode-tout-too-close.md)

  All were verified against OpenModelica 1.27.2 and FMPy 0.3.32.
- **No new ADR.** ADR 0001 (build variants) applies to exported FMUs unchanged; ADR 0002 (saved result format) needs no change.
- **Behaviour changes for existing users:** none. `create_run` gains an optional argument and `RunSettings` is unchanged. The reference bases gain `rtol` (default 0) and `interpolate` (default `False`), which keep today's results.
