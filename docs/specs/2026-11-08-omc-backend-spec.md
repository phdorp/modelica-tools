# In-repo OMC Backend Spec

Status: ready-for-agent
Source: Feature request "feat: replace pydelica with an in-repo OMC backend" (#42), charted and resolved on the map "Map: replace pydelica with an in-repo OMC backend" (#43). Every decision below links back to the ticket that holds its reasoning.

Terms follow `GLOSSARY.md`: **build**, **build config**, **build-time parameter**, **simulation target**, **run**, **run settings**, **result**, **partial result**, **diagnostics**.

## Problem Statement

mtools runs OpenModelica through `pydelica` 0.6.x, which lacks behaviour mtools needs. An ~800-line monkey-patch fills the gaps: it copies pydelica's compile step to keep multi-file packages in place, re-raises OMC errors readably, injects a `DefaultExperiment` and translates options for the Cpp target, and adds default runtime flags. Users and maintainers pay for that:

- **Fragile:** the patch only works with pydelica 0.6.x and refuses to install against anything else, so any upgrade breaks mtools.
- **Hard to fix:** every OMC bug becomes more patching of copied upstream code that is hard to test, review and debug, because behaviour is split between pydelica and the overrides.
- **pydelica leaks into user configs:** `build_options` and `libraries` are pydelica's keyword arguments, and the model name has to be repeated up to five times (`SimulationRun.model_name`, `model_addr`, the `model_configurations` key, and `model_name` inside `TimeRange` / `Tolerance` / `VariableFilter`).
- **Wrong or silent results:**
  - Cpp results go through a CSV that keeps only 6 significant digits.
  - `output_format="mat"` cannot be read back.
  - A misspelt parameter name is silently ignored.
  - Asking for library version 4.0.0 can silently load 4.1.0.
  - The Cpp target falls back to euler with stop time 1 when its defaults aren't injected.
- **Slow sweeps and hangs:** every sweep point recompiles the model, and a stalled Cpp simulation hangs forever, because Cpp has no working timeout or chatter guard.

## Solution

mtools drives OpenModelica itself through a small internal backend and drops `pydelica`:

- **Build once, run many times:** a **build** compiles one model once and is never changed afterwards. Each **run** executes the build with frozen **run settings** in its own directory and returns a `pandas` DataFrame.
- **Builds are cached** on disk by content, so a sweep over ordinary parameters compiles once, and re-running a sweep compiles nothing.
- **Typed configs:** users configure a run through two typed config groups, `build` and `settings`, and name the model once. Unset time range, interval, tolerance and solver come from the model's `experiment` annotation.
- **Public exceptions:** failures raise public `mtools.errors` exceptions with OMC's filtered diagnostics, shown once. A failed or timed-out run still hands back its partial result.
- **Two targets:** C is the default simulation target. Cpp is a deliberate alternative that behaves the same wherever its runtime allows, with its differences documented.
- **One breaking change:** the switch replaces the config schema and override paths. The package has no published releases, so there is no compatibility layer.

## User Stories

### Configuring a run

1. As a model developer, I want to name the model once, in `build.model_name`, so that I cannot configure contradicting names.
2. As a model developer, I want to choose the simulation target with a typed `build.target` field (`"C"` or `"Cpp"`, default `"C"`), so that the target is always my explicit choice.
3. As a model developer, I want a `--simCodeTarget` in `build.omc_flags` to be rejected with a config error naming `build.omc_flags`, so that the target has exactly one source.
4. As a model developer, I want to load extra source files or packages (`build.extra_sources`) before my model, so that a model extending another package's interface builds.
5. As a model developer, I want a library given with a version to load exactly that version, so that my results do not change when a newer version is installed.
6. As a model developer, I want to omit a library's version to get the installed default, so that I do not have to pin versions I don't care about.
7. As a model developer, I want to point a library at my own directory, so that I can use libraries outside OMC's install location.
8. As a model developer, I want unset start time, stop time, output interval, tolerance and solver to come from my model's `experiment` annotation on both targets, so that the model author's settings apply by default.
9. As a model developer, I want to override any run setting from the command line (`settings.stop_time=20`, `settings.parameters.phi=0.1`, `build.target=Cpp`), so that experiments don't need code changes.
10. As a model developer, I want array parameters in my parameter dataclass expanded to Modelica's indexed names, so that I can set `y = [1, 2]` naturally.
11. As a model developer, I want invalid config to fail before any compile time is spent, with an error naming the config path, so that I can fix it straight away.
12. As a model developer, I want a misspelt or protected parameter name to raise `ConfigError` naming `settings.parameters.<name>`, so that my results are not silently computed with the default value.
13. As a registry user, I want `create_run` to take `model_name`, `model_path`, `target`, `extra_sources`, `libraries`, `omc_flags` and the settings directly, so that I don't assemble pydelica-style dicts.

### Building

14. As a model developer, I want multi-file packages (`within`, `package.mo`, `Resources/Include`, `Resources/Library`) to compile in place, so that external C code and sibling files resolve as in my workspace.
15. As a model developer, I want a model that uses the Modelica Standard Library to build without listing the library, so that the `uses` annotation is enough.
16. As a model developer, I want a syntax, load or translation failure to raise `TranslationError` with OMC's diagnostics (file, line, column, message) shown once, so that I can jump to the broken line.
17. As a model developer, I want a C/C++ compile or link failure to raise `CompileError` showing only the compiler and linker diagnostics, so that the cause is not buried in the make log.
18. As a model developer, I want OMC warnings from a successful build logged at WARNING and notifications at DEBUG, so that real warnings stand out.

### Running and results

19. As a model developer, I want a run to return one DataFrame with `time` first and one column per time-varying variable, named as in today's CSV results, so that my existing references, saved CSVs and plots keep working.
20. As a model developer, I want Integer and enumeration columns as `int64` and Boolean columns as `bool`, so that results keep their Modelica types.
21. As a model developer, I want results at full double precision on both targets, so that Cpp results are not truncated to 6 digits.
22. As a model developer, I want the repeated time points at events kept, so that I can see values just before and after each event.
23. As a model developer, I want `settings.variable_filter` (an OMC regex, default `.*`) and `settings.emit_protected` to choose which columns appear, with `time` always kept, so that I control result size.
24. As a model developer, I want `sim_tools.simulate` to key results by `build.model_name`, so that I always find my result under the name I configured.
25. As a model developer, I want a failed run to raise `SimulationError` with the filtered runtime diagnostics and a `.partial_result` up to the failure, so that I can see where the model broke.
26. As a model developer, I want failed asserts and solver warnings in a successful run logged at WARNING, so that I notice a doubtful result.
27. As a model developer, I want to set a time limit (`settings.timeout`, seconds, default no limit), so that a stalled run in a sweep or CI is killed with `SimulationTimeout` carrying the output so far and a partial result.
28. As a model developer, I want chattering models aborted by default on C (`settings.abort_on_chattering`), with a typed way to turn that off, so that chattering doesn't hang my run and I can still opt out.
29. As a model developer pressing Ctrl-C, I want the running simulation killed, so that no orphaned process keeps running.

### Sweeps and caching

30. As a model developer sweeping a changeable parameter, I want every point to reuse one build, so that the sweep compiles once.
31. As a model developer re-running a sweep, script or test session, I want unchanged models taken from the cache, so that nothing recompiles.
32. As a model developer editing any file of my package, an extra source, or a library in my own directory, I want the next run to rebuild, so that I never get results from stale code.
33. As a model developer sweeping a build-time parameter (array size, if-equation selector, `Evaluate=true`), I want mtools to build one variant per distinct value automatically and cache each one, with an INFO log saying which parameters forced it, so that the sweep works without me knowing what OMC fixed.
34. As a user of a process-parallel Hydra launcher, I want concurrent jobs to share builds safely, so that parallel sweeps neither collide nor recompile.
35. As a user, I want to choose where builds and run directories live (`MTOOLS_WORK_DIR`, e.g. `build` in the project root; default in the system temp directory), so that I control disk use and cache lifetime.
36. As a user debugging a stale-cache suspicion, I want `MTOOLS_NO_CACHE=1` to build fresh into a throwaway directory, so that I can rule the cache out.
37. As a user debugging a run, I want `MTOOLS_KEEP_RUNS=1` to keep every run directory and log its path, with failure diagnostics ending in `Run directory: <path>`, so that I can rerun the binary by hand.

### Cpp target

38. As a user without the C runtime libraries, I want to pick `build.target = "Cpp"` and get the same config, result shape, column types, errors, partial results and caching as on C, so that Cpp is a usable alternative.
39. As a Cpp user, I want a solver other than `dassl`, `cvode` or `ida` rejected with `ConfigError`, even when it comes from the model's annotation, so that I never hit a segfault or a silently different solver.
40. As a Cpp user running `dassl` with an interval set, I want a WARNING that Cpp `dassl` ignores the output grid, so that unexpected row counts don't surprise me.
41. As a Cpp user, I want parameters and every run setting to take effect exactly as on C, so that the binary's compiled-in defaults never apply.

### Errors in apps and tests

42. As a Hydra app user, I want build and run errors to appear once, readably, in Hydra's standard error output, so that terminal output is short.
43. As a user handling sweep failures, I want to catch `SimulationError` to record a failed point and let `BuildError` / `ConfigError` stop the sweep, so that one bad parameter combination doesn't abort everything.
44. As a test author using `mtools.testing`, I want failing builds and runs to show the same diagnostics in pytest output, so that a red test tells me why.
45. As a user configuring logging, I want everything mtools logs under the `mtools` logger, with no handlers attached by mtools, so that Hydra's `job_logging` or my own setup controls output.

### Plotting

46. As a plotting-tool user, I want Boolean columns in saved results plotted as 0/1 step lines, so that typed results still plot.

## Implementation Decisions

### Backend shape ([What the mtools simulation session is](https://github.com/phdorp/modelica-tools/issues/46))

- **A new internal backend package** replaces `pydelica`, `pydelica_patch.py`, `SessionBuilder`, `SessionDirector` and `make_session()`. Its interface is two calls:
  - `build(build_config) -> Build`: cached, see below. It raises `ConfigError`, `TranslationError` or `CompileError`.
  - `Build.simulate(run_settings) -> DataFrame`: raises `ConfigError`, `SimulationError` or `SimulationTimeout`.
- **A build** covers exactly one model and is never changed after it is made. It knows its model name, target, parameter list (names, types, which are changeable), the experiment defaults from the annotation, and its recorded input list.
- **A run** gets its own directory and writes nothing into the build. Runs of one build may execute concurrently.
- **No session is public.** Users touch `sim_tools.simulate`, the Hydra configs, `mtools.testing` and `mtools.errors`. Public `sim_tools.simulate` keeps returning `dict[model_name, DataFrame]`.
- **Configs are plain data.** `hydra_zen.instantiate` builds config objects only. `simulate_run` validates the config, gets a build (from the cache or by building), and runs it, all outside `instantiate`.

### Config schema ([Typed config for model build and libraries](https://github.com/phdorp/modelica-tools/issues/47), amended by the caching, Cpp and timeout tickets)

The type shape (decision-rich parts only):

```python
@dataclass
class Library:
    name: str
    version: str | None = None              # None: installed default; given: pinned exactly
    directory: DirectoryPath | None = None  # prepended to OMC's library path

@dataclass
class Build:
    model_path: FilePath
    model_name: str
    target: Literal["C", "Cpp"] = "C"
    extra_sources: list[FilePath] = []      # loaded before model_path
    libraries: list[Library] = []
    omc_flags: dict[str, str | None] = {}   # extra OMC flags; mtools adds -q itself

@dataclass
class RunSettings:
    parameters: DataclassType
    start_time: float | None = None         # None: from the model's experiment annotation
    stop_time: float | None = None
    interval: float | None = None
    tolerance: float | None = None
    solver: str | None = None
    variable_filter: str = ".*"             # OMC regex, full match
    emit_protected: bool = False
    timeout: float | None = None            # seconds; None: no limit
    abort_on_chattering: bool = True        # C only; no effect on Cpp

@dataclass
class SimulationRun:
    build: Build
    settings: RunSettings
```

- **Removed:** `Session`, `Model`, `TimeRange`, `Tolerance`, `VariableFilter`, `Simulation`, `SimulationRun.model_name`, `build_options`, `model_configurations`, `output_format`.
- **Override paths:** the `session` group is replaced by `build` and `settings`. `settings/parameters` stays a group of selectable options. `mtools.testing`'s sweep parameter prefix becomes `settings.parameters`.
- **Parameters:** the parameter dataclass is flattened to dotted names, and array values are expanded to Modelica's 1-based, row-major indexed names (`m[1,2]`; OMC's names have no space after the comma, and the C runtime ignores `m[1, 2]`). Empty arrays raise `ValueError`. This keeps today's behaviour.
- **Validation** happens once in `simulate_run`, before building, and errors name the config path. Checks include `--simCodeTarget` in `omc_flags`, an explicitly requested Cpp solver outside `dassl`/`cvode`/`ida`, and type errors. Checks that need the build (unknown or protected parameter names, a Cpp-unsupported solver from the annotation) run after building and before the run starts.
- **Registry:** `create_run(model_name, model_path, target, extra_sources, libraries, omc_flags, settings, ...)` replaces the `build_options` dict. The examples' `cpp_build_options` helper is deleted in favour of `target="Cpp"`.

### Building ([How mtools should drive the OMC compiler](https://github.com/phdorp/modelica-tools/issues/44))

- **One short-lived OMC process per build.** For each build, mtools generates a `.mos` script from one template and runs it as one `omc [flags] build.mos` subprocess in a fresh temporary build directory. No ZMQ session, no separate `make` call, no CMake (rejected: [Caching builds across sweep points](https://github.com/phdorp/modelica-tools/issues/50)).
- **Script stages, in order:**
  1. Set command-line options: the target, `-q`, and the user's `omc_flags`.
  2. Prepend user library directories to the library path (`setModelicaPath`).
  3. Load each library: `loadModel(name, {version}, requireExactVersion=true)` when a version is given.
  4. Load each `extra_sources` entry and then the model source in place with `loadFile` (a model inside a package loads its `package.mo`).
  5. Record `getLoadedLibraries()` as the build's input list.
  6. Record the model's experiment annotation with `getSimulationOptions`.
  7. Build with `buildModel(model, fileNamePrefix=<internal name>)`. OMC runs the generated makefile with `make -j` itself.
- **Errors after every stage:** after each step the script prints a stage marker and `getErrorString()`, and calls `exit(<stage code>)` on failure, because an OMC script otherwise exits 0. The backend maps stage codes to `TranslationError` (stages 1–4 and translation) or `CompileError` (make).
- **What the backend reads from the build:** the generated `_init.xml` gives the parameter list, each variable's type (`Real`/`Integer`/`Boolean`/enumeration), and `isValueChangeable`.
- **Patch behaviour dropped:** the backend does not copy `Resources/Include` C sources and does not force-load `Modelica`. The fixture package in Testing Decisions proves this before the switch; if it fails, the failing case says which behaviour stays ([How mtools switches from pydelica to the new backend](https://github.com/phdorp/modelica-tools/issues/55)).

### Running ([How C and Cpp simulation binaries take settings and write results](https://github.com/phdorp/modelica-tools/issues/45), [What the backend promises for the Cpp target](https://github.com/phdorp/modelica-tools/issues/52))

- **Run directories:** every run creates a run directory and runs the binary with that directory as its working directory. Every input and output path is absolute, so nothing is written into the build.
- **Explicit settings:** every run setting is passed explicitly as a flag on every run. Unset values take the build's recorded annotation values. Nothing relies on `DefaultExperiment` or on Cpp's compiled-in defaults.
  - **C:** parameters go into a per-run override file (`-overrideFile`, newline-terminated lines, no `#` comments). Settings use the dedicated flags (`-startTime`, `-stopTime`, `-stepSize`, `-tolerance`, `-s`, `-variableFilter`, `-outputFormat=mat`, `-emit_protected`, and `-abortSlowSimulation` when `abort_on_chattering`), with `-inputPath` set to the build and `-outputPath` to the run directory.
  - **Cpp:** parameters go into a per-run copy of `_init.xml` with changed `start` attributes, passed with `--input-path`. Settings use `-S`, `-E`, `-H`, `-T`, `-I`, `-B`, `-P mat`, `-U protected`, and an absolute `-F` into the run directory.
- **No free-form runtime flags:** run settings are a fixed, typed set on both targets; mtools generates every runtime flag itself.
- **Unknown parameter names** (not in the build's parameter list) and **protected** parameters raise `ConfigError` before the run.
- **Cpp target:**
  - Cpp runs only when the user sets it; mtools never picks a target automatically.
  - Only `dassl`, `cvode` and `ida` are allowed on Cpp; any other solver is a `ConfigError`, never substituted.
  - Cpp `dassl` with an interval set logs a WARNING that the grid is ignored, without resampling.
  - `abort_on_chattering` has no effect on Cpp and is not an error there.
- **Timeouts** ([Timeouts and stalled simulations](https://github.com/phdorp/modelica-tools/issues/53)):
  - The binary starts in its own process group. When `settings.timeout` expires, mtools kills the group and raises `SimulationTimeout`. C's `-alarm` and Cpp's `-A` are not used.
  - On `KeyboardInterrupt` the group is killed before the interrupt propagates.
  - Builds have no timeout.

### Results ([Reading results into DataFrames](https://github.com/phdorp/modelica-tools/issues/49))

- **Always `.mat`:** every run writes `.mat`, read by a small in-repo numpy reader of OMC's MATLAB v4 "binTrans" layout. It handles negated aliases and needs no scipy.
- **Columns:** `time` first, then one column per time-varying variable from the trajectory matrix, with no parameter columns. Names are as in OMC's CSV (`x`, `der(x)`, `body.v`, `y[1]`).
- **Types:** OMC stores everything as double. The reader casts each column using the build's `_init.xml` types: `Real` → float64, `Integer` and enumerations → int64, `Boolean` → bool.
- **Rows:** as OMC writes them, keeping the repeated time points at events and at the stop time.
- **Unfinished files:** the reader tolerates a `.mat` whose header was never finished (column count 0 after a kill) by recovering every complete time point from the file length.
- **Failures:** a failed or timed-out run never returns its data as a result. The data goes to `SimulationError.partial_result` (`None` if nothing can be read). A clean exit without a result file raises `SimulationError`.
- **No key normalisation:** `_normalize_solution_keys` is deleted.

### Errors and diagnostics ([Exceptions and diagnostics the backend raises](https://github.com/phdorp/modelica-tools/issues/48))

- **Public module `mtools.errors`:**
  ```
  MtoolsError
  ├── ConfigError (also ValueError)
  ├── BuildError
  │   ├── TranslationError
  │   └── CompileError
  └── SimulationError                  .partial_result: DataFrame | None
      └── SimulationTimeout
  ```
- **Contents of every exception:** a header line naming the model and stage, e.g. `Modelica translation failed for 'Pkg.M' (/abs/Pkg/package.mo):`, `Simulation of 'Pkg.M' failed:` or `Simulation of 'Pkg.M' timed out after 600 s:`, then the filtered diagnostics. Attributes `.model_name` and `.diagnostics`. `repr == str`. The raw output goes to DEBUG only.
- **Translation filter:** keeps `Error:`/`Warning:` lines and their continuations in order. It drops `Notification:` lines and OMC boilerplate, and drops follow-on `Failed to load package` lines when another error is present. These are the existing rules, applied to the `getErrorString()` output of each stage.
- **Compile filter:** keeps `file:line:col: error|warning|note:` lines with their source and caret lines, `undefined reference` lines, and `ld`/`collect2` lines. It drops compile command lines and `make` chatter, and falls back to the whole log when nothing matches.
- **Run filters, one per target:**
  - C: each `LOG_*` line except `LOG_SUCCESS` as `<stream> | <level> | <message>`, with continuations indented, and solver banners dropped.
  - Cpp: each distinct stderr `ERROR :` line once, even though the kinsol retry repeats it. A crash names its signal in the header (`crashed with SIGSEGV`).
- **Logging on success:**
  - OMC translation warnings: WARNING.
  - Notifications: DEBUG.
  - C compiler warnings: DEBUG.
  - Failed asserts and solver warnings during a run: WARNING, headed `Simulation of '<model>' reported warnings:`.
- **No extra handling for Hydra:** mtools only raises; it doesn't log failures at ERROR or reformat them for Hydra.

### Cache, work directory and cleanup ([Caching builds across sweep points](https://github.com/phdorp/modelica-tools/issues/50), [Where run directories live and when they are deleted](https://github.com/phdorp/modelica-tools/issues/54), [ADR 0001](../adr/0001-automatic-build-variants.md))

- **Work directory:** `<work dir>/builds/` holds the build cache and `<work dir>/runs/` holds run directories. The work directory defaults to `<tempfile.gettempdir()>/mtools-<user>/` and is set with `MTOOLS_WORK_DIR`; a relative path resolves against the directory the process starts in.
- **Cache key:** a content hash, never timestamps, of:
  - the source files: the whole top-level package directory including `Resources/` for a model in a package, and the same rule for each `extra_sources` entry;
  - the library specs, plus a content hash of each `directory` library;
  - target, `omc_flags`, build-time parameter values;
  - the OMC version, the C compiler version, and an mtools backend version that changes whenever the build-script template changes.
- **Validating a hit:** a key match counts only if every package on the cached build's input list (`getLoadedLibraries()`) still hashes to its recorded value. Installed library versions are identified by name and version. Otherwise mtools builds again.
- **Not covered, to be documented:** C headers included by absolute path from outside any package.
- **Build variants:** when a run requests a parameter the build marks as non-changeable, the backend builds a variant with that value fixed at build time and caches it under a key that includes the value. One INFO log names the parameters that forced it. The plain build is always made first; its `_init.xml` tells which requested parameters are fixed at build time and gives their types.
  - **Mechanism: a wrapper class.** The variant's build script loads the same sources, then `loadString("model <variant class> extends <build.model_name>(<modifiers>); end <variant class>;")`, and builds that class. The variant class has an internal fixed name; results stay keyed by `build.model_name` and column names are unchanged.
  - **Modifiers** contain only the build-time parameters, so runs that share build-time values share the variant while changeable parameters still vary per run. Dotted names use the dotted form (`sub.m=5`). Array parameters are written as whole-array literals from the config value (`y0={7,8}`, `m={{1,2},{3,4}}`), because a modifier cannot set one element. Values are formatted from the `_init.xml` type: Real as a full-precision literal, Integer, `true`/`false`, quoted String, and enumeration literals as qualified names.
  - **Rejected: OMC's `setComponentModifierValue`.** It silently fails on inherited parameters (it returns `false` and the value stays unchanged), and it edits the user's class inside OMC.
  - **Protected parameters** requested in `settings.parameters` raise `ConfigError` before any variant is built. OMC 1.27 accepts a modifier on a protected parameter, but the Modelica spec forbids it and a later OMC may reject it.
  - **`final` parameters** fail as `TranslationError` with OMC's `Trying to override final element` message.
  - All of the above was verified on OMC 1.27.2: array size, if-equation selector, `Evaluate=true` (local and inherited), whole array, nested parameters, and `final`.
- **Publishing builds:** each build is written to a temporary directory under the work directory and moved into `builds/` in one step. If two processes build the same key, the one that finishes second discards its copy and uses the cached one. No lock files and no automatic eviction.
- **`MTOOLS_NO_CACHE=1`:** builds into a throwaway directory under `runs/` and skips the cache.
- **Cleanup:** run directories and uncached builds are deleted when the `simulate_run` call that created them ends, whether it succeeded, failed or timed out. `MTOOLS_KEEP_RUNS=1` keeps them, logs each path at INFO, and adds `Run directory: <path>` to failure diagnostics.
- **Not mtools' directory:** Hydra's output directory stays the user's. mtools writes there only through `save_solutions`.

### Logging ([Logger names for the backend](https://github.com/phdorp/modelica-tools/issues/56))

- **Loggers:** module-named (`logging.getLogger(__name__)`). Only the top-level `mtools` logger is documented as public.
- **Filter removed:** the `PyDelica.Compiler` notification filter is deleted.
- **No handlers:** mtools attaches no handlers and sets no levels.

### Plotting tool ([Reading results into DataFrames](https://github.com/phdorp/modelica-tools/issues/49))

- **Only change:** the plotting tool converts Boolean columns to 0/1 before plotting. It keeps reading the CSVs that `save_solutions` writes.

### Migration ([How mtools switches from pydelica to the new backend](https://github.com/phdorp/modelica-tools/issues/55))

- **Step 1:** the backend lands as an internal package that nothing uses yet, with its own tests.
- **Step 2:** one breaking change (`feat!:`) switches the configs, `sim_tools`, `hydra_registry`, `mtools.testing` and the examples. It deletes `pydelica`, `pydelica_patch.py`, the `pydelica.*` mypy override and the session classes.
- **No transition flag:** there is no user-facing flag and no period with both backends.
- **Docs in step 2:**
  - README: a new intro, the config and override paths, the environment variables, a targets section, `mtools.errors`, and a breaking-changes list.
  - AGENTS.md: the pydelica test line.
  - The examples.
  - A status note on `docs/specs/2026-11-07-omc-error-messages-spec.md` marking its superseded parts: preserved pydelica exception types, building inside `instantiate`, `get_runtime_options`.

## Testing Decisions

- **What a good test looks like:** it checks behaviour through the agreed seams: exception types and classes, stable OMC phrases, result values and dtypes, observable logs. It doesn't check generated file layouts or private helpers. Assertions use stable phrases, not whole messages, so minor OMC wording changes don't break them.
- **Seam 1: the backend's interface (`build(...)` / `Build.simulate(...)`)**, against real OMC, with `MTOOLS_WORK_DIR` pointed at `tmp_path`. Every integration test runs on both targets unless it tests a target-specific difference. Covers:
  - the translation, compile and run error catalogue, re-pinned on `mtools.errors`;
  - result columns, dtypes, repeated event rows, `variable_filter`, `emit_protected`;
  - partial results after a failed assert and after a timeout;
  - unknown and protected parameter names; Cpp solver rejection, both explicit and from the annotation; the Cpp `dassl` grid WARNING;
  - `abort_on_chattering` and `timeout` on a chattering or slow model;
  - annotation defaults (including Cpp no longer falling back to euler with stop time 1); exact library pinning;
  - a C-vs-Cpp comparison of the same model with `ida`/`cvode` within a tolerance;
  - cache behaviour, observed through the backend's "built" / "reused" log records: a hit; a rebuild after editing a file in the package, in an `extra_sources` package and in a `directory` library; one variant per distinct build-time parameter value, covering an array size, an if-equation selector, an inherited `Evaluate=true` parameter, a whole-array parameter and a nested parameter, with result columns unchanged; a `final` parameter as `TranslationError`; concurrent builds of one key; `MTOOLS_NO_CACHE`; `MTOOLS_KEEP_RUNS`.
- **The fixture package**, at seam 1, built on both targets from a working directory outside it:
  - members across files with `within`, and a model in a subpackage;
  - a `.c` file included from `Resources/Include` and a static library in `Resources/Library`;
  - a model that uses MSL without listing a library.

  It decides whether the dropped patch behaviour is really redundant.
- **Seam 2: public `sim_tools.simulate(config)`** through Hydra configs. Covers:
  - schema validation and config-path messages;
  - `build.*` / `settings.*` override paths in single runs and sweeps;
  - results keyed by `build.model_name`;
  - a broken package through `hydra_zen.instantiate` and `simulate_run`, showing diagnostics once, readably, with no ERROR records and nothing on stdout;
  - `create_run`, `mtools.testing` and the examples with updated paths.
- **Inside the backend, without OMC:** the translation, compile and run filters, the `.mat` reader (including a hand-truncated unfinished file), build-script generation, and cache-key computation each get fast unit tests on captured or hand-made input.
- **Temporary parity test**, before step 2 deletes pydelica: the example models run through the old and new paths on C and Cpp and are compared within a tolerance. It is deleted together with pydelica.
- **No fake `omc`.** CI already installs real OMC with both runtimes.
- **What happens to the existing tests (prior art):**
  - `tests/session_tools/test_omc_diagnostics.py`: filter unit tests and `tmp_path` broken models, ported.
  - `tests/session_tools/test_omc_error_catalog.py`: re-pinned on `mtools.errors`.
  - `tests/session_tools/test_cpp_target.py`: becomes the two-target tests, with the tolerance tightened from `rtol=1e-4`.
  - `tests/session_tools/test_session_builder.py` and `test_session_tools.py`: rewritten for the new configs; the array-expansion tests are kept.
  - `tests/session_tools/test_pydelica_patch.py`: deleted. Its in-place case becomes the fixture package.
  - `tests/session_tools/test_hydra_registry.py`, `test_testing.py` and `examples/tests`: override paths updated.

## Out of Scope

- Windows and macOS support. CI and the devcontainer are Linux only.
- A compatibility layer for pydelica-shaped configs or the `session.*` override paths.
- pydelica features the repo doesn't use: profiling, `update_input_paths_to`, an explicit `c_source_dir`, `fail_on_assert_level`, parameter and option getters.
- Free-form runtime flags, CSV or `plt` output from the backend, parameter columns in results.
- Choosing the target automatically.
- Automatic cache eviction, a cache-clearing command, timeouts on builds.
- Stable public logger names below `mtools`.
- The plotting tool reading `.mat` files or run directories.
- Inferring the model name from the package ("Infer Model Name from Modelica Package", #25).
- Contributing fixes to pydelica upstream.

## Further Notes

- **Behaviour changes users will notice:**
  - Models without an `experiment` annotation now run from 0 to 1 s (OMC's defaults) instead of mtools' fixed 0 to 10 s with tolerance 1e-9.
  - Integer and Boolean columns change dtype.
  - The cache's default location under the system temp directory lasts until the system clears it.
- **Research:**
  - [OMC compile interface](https://github.com/phdorp/modelica-tools/blob/research/omc-compile-interface/docs/research/2026-11-08-omc-compile-interface.md)
  - [C and Cpp runtime interfaces](https://github.com/phdorp/modelica-tools/blob/research/omc-runtime-interfaces/docs/research/2026-11-08-omc-runtime-interfaces.md)

  Both were verified against OMC 1.27.2. One correction to the runtime research: a killed run's `.mat` is recoverable with a tolerant reader. The research describes it as unreadable.
- **Glossary and ADR:** `GLOSSARY.md` (new) and `docs/adr/0001-automatic-build-variants.md` (new) ship with this spec.
