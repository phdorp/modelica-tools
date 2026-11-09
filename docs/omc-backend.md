# The OMC backend

mtools builds and runs Modelica models with OpenModelica's compiler, `omc`, through an in-repo backend. It replaces Pydelica. This page describes what happens when you call `sim_tools.simulate`, what a result contains, how results are saved, and what configures the backend. To define run configs, see [The Hydra registry](hydra-registry.md).

The backend itself is internal (`mtools.internal.omc`). These are the public parts:

| Module | Content |
|---|---|
| `mtools.sim_tools` | `simulate`, `save_solutions`, `load_solution`, `SweepResult` |
| `mtools.session_config` | `SimulationRun`, `Build`, `Library`, `RunSettings` |
| `mtools.hydra_registry` | `HydraZenRegistry`, `ExperimentSpec` |
| `mtools.errors` | The exceptions under [Errors and logging](#errors-and-logging) |
| `mtools.testing` | pytest base classes for experiment and reference tests |

## How a run works

`simulate(config)` takes one composed run config and goes through these steps:

1. **Validate.** It checks every value that can be checked without building: types, that the files and directories exist, `build.target`, `output_format`, `build.omc_flags` and a solver requested on Cpp. All problems are reported together in one `ConfigError`, naming each config path, before anything is built.
2. **Build, or reuse a cached build.** One `omc` process runs a generated `.mos` script. The script loads the libraries, the `extra_sources` and the model's package, then translates the model and compiles it for `build.target`. A failure raises `TranslationError` or `CompileError`. The finished build is published in the [build cache](#build-cache).
3. **Build variants.** If `settings.parameters` sets a parameter that OMC fixed while translating (an array size, a Boolean that selects an if-equation, an `Evaluate=true` parameter), mtools builds and caches a variant with that value fixed. Every other parameter changes per run. See [ADR 0001](adr/0001-automatic-build-variants.md).
4. **Run.** The simulation binary runs in its own run directory. Every setting is passed as an explicit flag, so nothing compiled into the binary applies by accident; unset time range, interval, tolerance and solver come from the model's `experiment` annotation. Parameters go to the C runtime in an `-overrideFile`, and to the Cpp runtime in a per-run copy of the build's `_init.xml`. A failure or timeout raises `SimulationError` or `SimulationTimeout`.
5. **Read the result.** The backend reads OMC's `.mat` result file and casts the column types from the build's `_init.xml`. It returns `{build.model_name: DataFrame}`.

A sweep (`simulate(run_config, overrides=[...], multirun=True)`) repeats these steps for each point, so all points share one build per distinct set of build-time values.

## Results

A result is a pandas DataFrame:

- `time` comes first, then one column per time-varying variable, named as OMC names them (`x`, `der(x)`, `body.v`, `y[1]`, `m[1,2]`). There are no parameter columns.
- `settings.variable_filter` (an OMC regular expression that must match the whole name) selects the columns; `time` is always kept. `settings.emit_protected=true` adds protected variables.
- Real columns are `float64`, Integer and enumeration columns are `int64`, and Boolean columns are `bool`.
- Rows are the output points, including the repeated time points OMC writes at the start, at events and at the stop time.

## Saving results

`save_solutions(solutions, output_path, output_format="mat")` writes each result to `<output_path>/<model name>.<output_format>`. A run config carries the format as `output_format`, so an entry point passes `config.output_format`, and the user picks the format on the command line:

```bash
uv run python -m my_simulation                    # <model name>.mat
uv run python -m my_simulation output_format=csv  # <model name>.csv
```

| Format | Content |
|---|---|
| `mat` (default) | OMC's MATLAB v4 result layout (`binTrans`), written from the returned DataFrame, so it has exactly the returned columns and rows at full double precision. The column types are stored alongside it. OpenModelica's `readSimulationResult` can open it. |
| `csv` | One header row, then one row per output point. Booleans are written as `True`/`False`. |

`load_solution(path)` reads either file back. A `.mat` file reads back unchanged, with `bool` and `int64` columns. A `.csv` file goes through pandas' type inference. `save_solutions` refuses to write a result with no rows as `.mat`. [ADR 0002](adr/0002-saved-result-format.md) records why `.mat` is the default.

The plotting tool (`uv run python -m mtools <directory>`) lists the `.csv` files under the directory and the `.mat` files in OMC's result layout, which includes OMC's own `_res.mat` files and skips other `.mat` files, such as MATLAB v5 files. It shows Boolean columns as 0/1 lines.

## Targets

`build.target` selects the OpenModelica simulation runtime. `C` is the default. `Cpp` is a deliberate alternative for installations without the C runtime libraries; mtools never picks it automatically. Config, result columns and rows, column types, errors, partial results and caching are the same on both targets: mtools drops the parameter aliases Cpp writes as columns and writes the repeated rows at the start, at events and at the stop time as C does. These differences remain on Cpp:

- Only the solvers `dassl`, `cvode` and `ida` run; any other solver, also from the model's annotation, raises `ConfigError`.
- `dassl` ignores `settings.interval` and logs a WARNING instead of resampling.
- When `settings.interval` does not divide the simulated time span, Cpp writes the grid at multiples of the interval plus the stop time, while C spreads a rounded number of intervals evenly (0 to 1 s with interval 0.3: Cpp writes 0, 0.3, 0.6, 0.9, 1; C writes 0, 0.333, 0.667, 1).
- An event at the start time that changes no discrete variable in the result gives one row at the start time instead of C's three.
- `abort_on_chattering` has no effect.
- Events are reported about 1e-6 late.
- Division by zero and singular linear systems do not fail the run.
- A failed initialization gives a one-row partial result instead of `None`.

`--simCodeTarget` is rejected in `build.omc_flags`; use `build.target`.

## Environment variables

| Variable | Effect |
|---|---|
| `MTOOLS_WORK_DIR` | Work directory holding `builds/` (the cache) and `runs/`. Defaults to `<system temp dir>/mtools-<user>/`; a relative path resolves against the directory the process starts in. |
| `MTOOLS_NO_CACHE=1` | Build into a throwaway directory and skip the cache. |
| `MTOOLS_KEEP_RUNS=1` | Keep run directories and uncached builds, log their paths at INFO, and add `Run directory: <path>` to failure diagnostics. |

Run directories and uncached builds are otherwise deleted when `simulate` ends. Hydra's output directory is never touched except by `save_solutions`.

## Build cache

The cache key is a content hash of the source packages (including `Resources/`), library specs, target, `omc_flags`, build-time parameter values, and the OMC and C compiler versions. Editing a file in the package, in an `extra_sources` package or in a `directory` library rebuilds. The key does not depend on where the sources are, so two checkouts of the same project that share a work directory share their builds. There is no automatic eviction; delete `<work dir>/builds/` to clear it. C headers included by absolute path from outside any package are not part of the key, so changing one does not trigger a rebuild; use `MTOOLS_NO_CACHE=1` for those models.

## Errors and logging

All failures raise public exceptions from `mtools.errors`, with a header naming the model and stage, followed by OMC's filtered diagnostics:

```
MtoolsError
├── ConfigError (also ValueError)
├── BuildError
│   ├── TranslationError
│   └── CompileError
└── SimulationError                  .partial_result: DataFrame | None
    └── SimulationTimeout
```

A failed or timed-out run never returns data as a result; what was written before the failure is in `SimulationError.partial_result`. Every exception has `.model_name` and `.diagnostics`.

mtools logs to the `mtools` logger (builds, cache hits, warnings from OMC and from the run). It attaches no handlers and sets no levels.
