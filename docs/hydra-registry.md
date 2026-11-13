# The Hydra registry

A run config tells `sim_tools.simulate` what to build, how to run it and how to save the result. `mtools.hydra_registry.HydraZenRegistry` creates run configs, registers the config groups that fill them, and registers experiments, which are named variations of a run config. Hydra composes the result, so every value can be overridden from the command line. The [`kinematic_vehicle` example](../examples/src/kinematic_vehicle/kinematic_vehicle.py) uses everything on this page. To learn what happens when a run config is simulated, see [The OMC backend](omc-backend.md).

## The run config

A run config is a `mtools.session_config.SimulationRun` with three parts:

```
SimulationRun
├── build: Build                 what to build
│   ├── model_path, model_name
│   ├── target                   "C" (default) or "Cpp"
│   ├── extra_sources            list of files
│   ├── libraries                list of Library(name, version, directory)
│   └── omc_flags                {"-d": "initialization", "--flag": None}
├── settings: RunSettings        how to run it
│   ├── parameters               a (nested) parameter dataclass
│   ├── start_time, stop_time, interval, tolerance, solver
│   └── variable_filter, emit_protected, timeout, abort_on_chattering
└── output_format                "mat" (default) or "csv", used by save_solutions
```

| Override path | Content |
|---|---|
| `build.model_path`, `build.model_name` | Source file and fully qualified model class. Results are keyed by the name. |
| `build.target` | `C` (default) or `Cpp`; see [Targets](omc-backend.md#targets). |
| `build.extra_sources`, `build.libraries`, `build.omc_flags` | Extra packages, libraries (`name`, `version`, `directory`) and OMC flags. `--simCodeTarget` is rejected; use `build.target`. |
| `settings.parameters.*` | Parameter values. The structure follows the parameter dataclass. |
| `settings.start_time`, `stop_time`, `interval`, `tolerance`, `solver` | Values left unset come from the model's `experiment` annotation, or OMC's defaults (0 to 1 s) if it has none. The default solver comes from the `__OpenModelica_simulationFlags(s=...)` annotation, else `dassl`. |
| `settings.variable_filter`, `emit_protected`, `timeout`, `abort_on_chattering` | Result columns (an OMC regular expression; Python's `re` for FMU runs), protected variables, a time limit in seconds, and aborting a chattering run (C only). |
| `output_format` | `mat` (default) or `csv`; see [Saving results](omc-backend.md#saving-results). |

Parameters:

- Nested dataclasses become dotted names, and arrays become 1-based indexed names: `y=[1, 2]` sets `y[1]` and `y[2]`, and a 2-D array sets `m[1,2]`, with no space after the comma.
- If OMC fixes a parameter at build time (for example an array size or an `Evaluate=true` parameter), mtools builds and caches a variant with that value. An enumeration value for such a parameter must be a qualified literal, `"Mode.high"`.
- An unknown or protected parameter name raises `ConfigError`.

`simulate` validates the whole run config before building anything, and reports every invalid value by its path in one `ConfigError`.

## Creating a run config

```python
import dataclasses
from pathlib import Path

import hydra_zen
from hydra_zen import MISSING

import mtools.hydra_registry as hydra_registry
import mtools.session_config as session_config


@dataclasses.dataclass
class Parameters:
    k: float = 1.0
    n: int = 3


registry = hydra_registry.HydraZenRegistry(store=hydra_zen.ZenStore())

# Options for the `settings/parameters` and `settings` groups. The defaults fill every run config.
registry.register_group_options("settings/parameters", {"default": Parameters()}, default="default")
registry.register_group_options(
    "settings",
    {"default": session_config.RunSettings(parameters=MISSING, stop_time=10.0)},
    default="default",
)

run_default = registry.create_run(
    model_name="my_simulation.MyModel",
    model_path=(Path(__file__).parent / "package.mo").resolve(),
    target="C",
    libraries=[session_config.Library("Modelica", version="4.0.0")],
    omc_flags={"-d": "initialization"},
    include_experiment_group=True,
    name="default",
)
```

`create_run` takes these arguments, all keyword-only:

| Argument | Content |
|---|---|
| `model_name`, `model_path` | The model class and its source file. A model inside a package is loaded from the package's `package.mo`. |
| `target`, `extra_sources`, `libraries`, `omc_flags` | The other `build` fields. |
| `settings` | A `RunSettings`. When it is omitted, the parameters come from the `settings/parameters` group and every other value comes from the model's annotation. A `settings` group default replaces it either way. |
| `selections` | `{group: option}`, choosing a non-default option of a registered group for this run config. |
| `include_experiment_group` | Whether experiments can be applied to this run config (`experiment=<name>`). |
| `name` | The name to register the run config under. It becomes the `config_name` for `@hydra.main` and for `compose`. |

For a different base class, call `build_run_config(base=..., build=session_config.Build(...), settings=...)` instead. `get_run_config(name)` returns a registered run config.

To run an FMU instead of a native build, pass `fmu=FmuExport()` to `create_run`, or use `create_fmu_run(fmu_path=...)` for an FMU you supply; see [FMU runs](fmu-runs.md).

## Config groups

`register_group_options(group, {name: config}, default=name)` registers the interchangeable options of one group, and `register_group_option` registers a single option. The group path is also the config path it fills:

- **`settings/parameters`** holds parameter dataclass instances. Select one with `settings/parameters=<option>`.
- **`settings`** holds `RunSettings` instances. Their `parameters` are merged with the `settings/parameters` group, so leave them `MISSING`.

Group options are shared by every run config in the registry.

## Experiments

An experiment is a named set of overrides on a run config:

```python
registry.register_experiment(
    name="stiff",
    base_run_config=run_default,
    overrides={"settings/parameters": Parameters(k=1e4)},
)
registry.register_experiment(
    name="long",
    base_run_config=run_default,
    overrides={"settings": session_config.RunSettings(parameters=MISSING, stop_time=100.0)},
)
```

- `overrides` maps a group to a config instance that replaces that group's default. `selections` maps a group to the name of a registered option.
- Each experiment is bound to every run config whose defaults include the `experiment` group, both the ones registered now and the ones registered later. A reference model's run config therefore gets the same experiments.
- `ExperimentSpec(name, overrides, selections)` with `register_experiments(specs, base_run_config=...)` replays one set of experiments in several registries.
- `compose_experiment(name, run_config=...)` returns the composed config, and `get_experiment_run_config` returns the run config it uses. The `mtools.testing` base classes run experiments in pytest.

## Running from the command line

The entry point registers the configs in Hydra's store and saves the solutions in the chosen format:

```python
import hydra
from hydra.core.hydra_config import HydraConfig

import my_simulation.config
import mtools.session_config as session_config
import mtools.sim_tools as sim_tools


@hydra.main(config_name="default", version_base=None, config_path=None)
def main(config: session_config.SimulationRun) -> None:
    solutions = sim_tools.simulate(config)
    sim_tools.save_solutions(solutions, HydraConfig.get().runtime.output_dir, config.output_format)


if __name__ == "__main__":
    my_simulation.config.registry.add_to_hydra_store()
    main()
```

```bash
uv run python -m my_simulation settings.parameters.k=5.0           # one value
uv run python -m my_simulation settings.stop_time=20 build.target=Cpp
uv run python -m my_simulation experiment=stiff                    # an experiment
uv run python -m my_simulation output_format=csv                   # save CSV instead of .mat
uv run python -m my_simulation -m settings.parameters.k=1,10,100   # a sweep
uv run python -m my_simulation '+build.omc_flags={-d:initialization,--maxSizeLinearTearing:300}'
```

`build.omc_flags` needs the leading `+`; without it, Hydra rejects the override with `Key ... is not in struct`. The given flags are added to the configured ones, and `null` gives a flag without a value (`{--showErrorMessages:null}`).

From Python, `simulate(run_default, overrides=["settings.parameters.k=1,10"], multirun=True, registry=registry)` runs a sweep and returns one `SweepResult(config, solutions)` per point. No `add_to_hydra_store()` call is needed.

A sweep from Python runs inside your process and leaves it as it found it: Hydra's config store is restored, and Hydra changes no log levels or handlers. So Hydra writes no per-job `.log` files; to get them, pass a logging option yourself, e.g. `hydra/job_logging=default`, and Hydra configures logging for your process as it does for a command-line run.

## Several registries

Each run from Python resolves its configs from the registry it is given, and nothing else: `compose(name, overrides)`, `simulate(..., multirun=True, registry=registry)`, and the sweeps in `mtools.testing`. For the duration of the call, Hydra sees only its own configs and that registry's; afterwards Hydra's global config store is as it was, and the registry is unchanged. So separate registries, for example one per run or per test module, never see each other's configs, even when they reuse names. `registry.activated()` gives you the same scope for your own Hydra calls.

Only the command line reads Hydra's global store: `add_to_hydra_store()` adds a registry's configs to it once, for `hydra.main`. If two registries put the same names there, the later call needs `overwrite_ok=True`.
