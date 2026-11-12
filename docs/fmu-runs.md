# FMU runs

mtools runs an experiment against an FMU through [FMPy](https://github.com/CATIA-Systems/FMPy), in the same test classes and with the same parameters and run settings as a native run. This page describes the two kinds of FMU, which run settings apply, how a run is isolated, how exported FMUs are cached, how to compare results, and the known limits. For native runs, see [The OMC backend](omc-backend.md); to define run configs, see [The Hydra registry](hydra-registry.md).

Install FMPy with the optional extra:

```bash
pip install "modelica-tools[fmu]"
```

Without FMPy, mtools and native runs work as before. An FMU run raises `ImportError` before anything is built or exported.

## Given and exported FMUs

The kind of model is chosen only in the run config's `build`. Experiments, run settings and test classes don't change when a run config switches from a native build to an FMU.

| Kind | Config | What runs |
|---|---|---|
| Native | `create_run(...)` | The OMC simulation binary. |
| Exported FMU | `create_run(..., fmu=FmuExport())` | A Modelica model that mtools exports with OMC's `buildModelFMU`. |
| Given FMU | `create_fmu_run(fmu_path=...)` | An FMU file you supply, for example one exported from another tool. |

### Exported FMUs

`FmuExport` (in `mtools.session_config`) has one field, `fmu_type`: `"me"` for Model Exchange (the default) or `"cs"` for Co-Simulation. Sources, libraries, `omc_flags` and the build cache apply as for a native build. mtools exports FMI 2.0 only, because OMC 1.27.2 rejects 3.0.

```python
run_fmu = registry.create_run(
    model_name="my_simulation.MyModel",
    model_path=(Path(__file__).parent / "package.mo").resolve(),
    target="C",
    fmu=session_config.FmuExport(),
    include_experiment_group=True,
    name="fmu",
)
```

`settings.emit_protected=true` exports with `--fmiFilter=internal`, so protected variables become result columns. It is the only source of `--fmiFilter`: a `--fmiFilter` in `build.omc_flags` is a `ConfigError`. Other FMU flags, such as `--fmiFlags=s:cvode`, stay allowed.

Parameters follow [ADR 0001](adr/0001-automatic-build-variants.md). A sweep over a build-time parameter (one OMC fixed while translating, which the FMU then lists as a `calculatedParameter`) exports one cached variant FMU per value. A protected parameter is a `ConfigError`, also with `emit_protected=true`. A `final` parameter raises `TranslationError`.

An export from `target="Cpp"` logs one WARNING naming its risks, listed under [Known limits](#known-limits). `fmu_type="cs"` on Cpp is a `ConfigError`.

### Given FMUs

`create_fmu_run` takes the path of the `.fmu` file and an optional `name_map`:

```python
run_ctrl = registry.create_fmu_run(
    fmu_path=Path("controller.fmu"),
    name_map={"ctrl.k": "Kp"},
    include_experiment_group=True,
    name="ctrl",
)
```

Its other arguments are `model_name`, `fmu_type`, `settings` and `selections`, as for `create_run`.

- `fmu_path` must exist and hold a readable `modelDescription.xml` and a `linux64` binary; otherwise `simulate` raises a `ConfigError` naming `build.fmu_path`.
- `fmu_type=None` runs Model Exchange when the FMU offers it, otherwise Co-Simulation. Requesting a type the FMU lacks is a `ConfigError`.
- The result is keyed by `model_name`, or by the FMU's `modelName` when `model_name` is unset. The test classes handle both, so a given FMU without `model_name` works as candidate or reference unchanged.
- FMI 2.0 and 3.0 FMUs run. Given FMUs are not cached: each run extracts the file into its own run directory.

### Name map

A third-party FMU names its variables its own way. `name_map` maps `{experiment name: FMU name}` for parameters and result columns alike, so tests, saved results, plots and comparisons see the experiment's names. The experiment sets `ctrl.k=2.0`, mtools sets `Kp=2.0` in the FMU, and the result column `Kp` comes back as `ctrl.k`.

- Keys and values are exact, fully flattened and expanded names (`"y0[1]": "Y0_1"`). There are no prefixes or patterns.
- The map is one-to-one and lives only on the given FMU's build config: candidate and reference carry their own, and sweeps and settings overrides never touch it.
- Each of these is a `ConfigError`: an FMU name that isn't in `modelDescription.xml`, two keys pointing at the same FMU name, `time` as a key or value, and a key that is also the name of another FMU variable that isn't itself renamed. A swap (`{"a": "b", "b": "a"}`) is legal.
- Set `name_map` in Python or YAML. A dotted key on the command line (`build.name_map.ctrl.k=Kp`) isn't supported.
- Diagnostics from the FMU keep the FMU's names.

## Run settings

Time range, interval, tolerance, solver, variable filter and timeout mean what they mean for native runs, with these differences. Every value is checked before the run, and a `ConfigError` names the config path.

- **Defaults.** Unset `start_time`, `stop_time`, `interval` and `tolerance` come from the FMU's `DefaultExperiment`. A missing field takes OMC's default: start 0, stop 1, interval (stop - start)/500, tolerance 1e-6. `interval` must be greater than 0.
- **Solver, Model Exchange.** `"cvode"` (the default) or `"euler"`. Any other name is a `ConfigError`. For an exported FMU, `settings.solver` is the FMPy solver on both targets, and the model's `__OpenModelica_simulationFlags` isn't consulted. Euler steps once per output interval.
- **Solver, Co-Simulation.** The FMU's built-in solver runs. An explicit `solver` is ignored with a WARNING. `tolerance` is passed to the FMU, which OMC's Co-Simulation FMUs ignore.
- **Interval, Co-Simulation.** If the interval doesn't divide `stop_time - start_time` and the FMU can't vary its communication step (`canHandleVariableCommunicationStepSize`), it's a `ConfigError`.
- **`variable_filter`.** An OMC regular expression that must match the whole name, matched against the experiment's names (after the name map); `time` is always kept. An invalid regex is a `ConfigError`.
- **`emit_protected`.** For an exported FMU, applied at export and part of the cache key. For a given FMU, no effect, with a WARNING when `true`.
- **`abort_on_chattering`.** No effect, as on Cpp.
- **`timeout`.** See [Isolation and timeouts](#isolation-and-timeouts).

### Parameters

`settings.parameters` is flattened as for native runs (dotted names, 1-based indexes), translated through the name map and set in the FMU once, before initialization. Names and values are checked against `modelDescription.xml` for FMI 2.0 and 3.0 before the run; for an exported FMU, right after the export. Problems are reported together in one `ConfigError`, naming `settings.parameters.<key>`, with the FMU name for a mapped name (`settings.parameters.ctrl.k (FMU name 'Kp'): ...`).

- A name is settable if the FMU declares it with `causality="parameter"` and variability `fixed` or `tunable` (or `initial="exact"`). Constants and inputs aren't settable. A given FMU can't be rebuilt, so a calculated parameter is a `ConfigError`; an unknown name is one too.
- Real takes int or float. Integer takes integral values only (`2.7` is rejected, not truncated). Boolean takes `bool` and String takes `str`. Enumeration takes the item's integer or a qualified literal such as `"Mode.high"`.

### Results

A result is a DataFrame as described in [Results](omc-backend.md#results): `time` first, then the columns `variable_filter` keeps, in `modelDescription.xml` order. Parameter, calculated-parameter and constant columns are dropped. Real columns are `float64`, Integer and enumeration columns are `int64`, Boolean columns are `bool`; String and Binary variables are left out. Model Exchange repeats rows at events, Co-Simulation has no event rows. `save_solutions`, `load_solution` and the plotting tool work unchanged.

## Isolation and timeouts

Every FMU run is a fresh child Python process, so a crashing FMU raises `SimulationError` ("crashed with SIG...") instead of killing your test process. This costs about 165 ms per run.

- Each run extracts its FMU into a run directory under `runs/` and deletes it when the run ends. `MTOOLS_KEEP_RUNS=1` keeps it, logs its path and adds `Run directory: <path>` to failure diagnostics.
- `settings.timeout` covers the whole child: interpreter start, `import fmpy`, extraction and the simulation. It does not cover the export of an exported FMU, which is a build. On expiry the process group is killed and `SimulationTimeout` is raised. Ctrl-C kills the child too.
- The child saves the rows recorded so far about once per second, so a timeout or crash gives `SimulationError.partial_result` up to the last save, or `None` before the first.
- mtools has no chattering guard. A chattering Model Exchange FMU, or a Co-Simulation FMU that keeps returning `Discard`, runs until `timeout` or forever without one. Set a `timeout` on FMU tests.

### Diagnostics

A `SimulationError` lists, in order of occurrence:

1. messages the FMU logged through the FMI logger with status warning or worse;
2. `LOG_*` entries an OMC-exported FMU printed;
3. the first failed FMI call, for example `fmi2GetDerivatives failed with status 3 (error)`;
4. the exception that ended the run.

The failed call can appear twice, once on its own line and once inside the final exception. For FMI 2.0 FMUs, mtools switches on the `logStatusWarning`, `logStatusDiscard`, `logStatusError`, `logStatusFatal` and `logStatusPending` debug-logging categories that the FMU declares, so OMC FMUs report their warnings. FMI 3.0 logging is left as FMPy sets it. A successful run logs one WARNING with the FMU's warning-level messages.

## Caching

An exported FMU is a build: `builds/<key>/` holds `model.fmu` and the build record. Hits, misses, `MTOOLS_NO_CACHE=1` and ADR 0001 variants behave as in the [build cache](omc-backend.md#build-cache).

The key of an exported FMU is the native key plus `fmu_type`, `emit_protected` and the `cmake --version` of the `cmake` on `PATH`. OMC calls the first `cmake` on `PATH`, so a different CMake rebuilds. `me` and `cs` exports of one model are separate entries. Native keys don't change, so existing native builds stay cached. The Co-Simulation solver and tolerance need no field of their own: they come from the model's `experiment` annotation or from `--fmiFlags` in `omc_flags`, both already in the key.

## Comparing results

`assert_matches_reference()` works for any pair of runs, FMU or native, under one set of rules. Both sides must have exactly the same columns; narrow them with each side's `variable_filter`. Two class variables, set on the test class, control the comparison (documented on `ExperimentBase` in `mtools.testing`):

| Variable | Default | Meaning |
|---|---|---|
| `eps` | machine epsilon | Absolute tolerance on every compared column. |
| `rtol` | `0.0` | Relative tolerance on every compared column. |
| `interpolate` | `False` | Align the two time grids before comparing. |

By default the tables need the same number of rows, and every column including `time` is compared row by row. With `interpolate = True`, where a time repeats only the last row is kept (the value after an event) on both sides. The candidate is then interpolated onto the reference's time points, linearly for Real and by the last value at or before the time point for Boolean and Integer, and every signal is compared at every reference row. A reference time point outside the candidate's span fails; nothing is extrapolated.

```python
class TestTurnLeftFmuReference(ExperimentReference):
    name = "turn_left"
    rtol = 1e-6
    interpolate = True

    def test_matches_reference(self):
        self.assert_matches_reference()
```

Model Exchange and Co-Simulation results compare under the same rules, but a Co-Simulation result shows an event only at the next communication point and may use another embedded solver. OMC's Co-Simulation FMUs embed fixed-step Euler by default: for `FmuTests.Decay` at interval 0.01 the error was about 2% relative. A Model Exchange vs. Co-Simulation test therefore needs `interpolate`, a tolerance and/or a fine interval.

The kinematic vehicle example compares two exported FMUs; see [`examples/README.md`](../examples/README.md).

## Known limits

- **Co-Simulation CVODE "tout too close"** ([FMPy #882](https://github.com/CATIA-Systems/FMPy/issues/882)). A `sample()` event within one float step of the communication grid can fail inside the FMU's own CVODE. When a failed Co-Simulation run's diagnostics show it, mtools adds a hint line naming the fixes: `fmu_type="me"`, an export without `--fmiFlags=s:cvode` (Euler), or another interval. It applies to given FMUs too.
- **Two workarounds for FMPy and OMC defects.** On Model Exchange runs with `solver="cvode"`, mtools skips the steps CVODE would refuse (FMPy #882, again). On every Model Exchange run, it zeroes the event-indicator buffer before each call: OMC 1.27.2's Cpp export declares more event indicators than it writes, so unwritten values made results nondeterministic. FMUs that set every indicator are unaffected. Both are dropped once fixed upstream.
- **Cpp FMUs.** Model Exchange only. Time events (`when sample(...)`) don't fire under FMPy. Resources and shared libraries aren't copied.
- **Co-Simulation accuracy.** See [Comparing results](#comparing-results).
- **Model Exchange Euler** steps once per output interval.
- **Linux FMUs only.** The FMU needs a `linux64` binary.
- **No FMU inputs.**
- **No native-vs-FMU reference tests.** Both sides of a reference test are native, or both are FMUs.
- **`name_map`** is set in Python or YAML, not on the command line.
- **A `timeout` is recommended**, see [Isolation and timeouts](#isolation-and-timeouts).
