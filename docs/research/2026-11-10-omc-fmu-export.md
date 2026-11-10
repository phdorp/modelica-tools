# What OMC's FMU export gives mtools

Date: 2026-11-10
Sources: OpenModelica source at tag [`v1.27.2`](https://github.com/OpenModelica/OpenModelica/tree/v1.27.2) (commit `4f2b2b1`): `ModelicaBuiltin.mo`, `CevalScriptBackend.mo`, `FMI.mo`, `Error.mo`, `Flags.mo`, `SimCodeUtil.mo`, `SimCodeMain.mo`, `SerializeInitXML.mo`, `BackendVariable.mo`, `CodegenFMU.tpl`, `CodegenFMUCommon.tpl`, the FMI export runtime (`SimulationRuntime/fmi/export/openmodelica/`), `cvode_solver.c`, `simulation_options.c`, and the User's Guide chapter [`fmitlm.rst`](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/doc/UsersGuide/source/fmitlm.rst);
FMI specification sources [`v2.0.4`](https://github.com/modelica/fmi-standard/tree/v2.0.4/docs);
FMPy source at tag [`v0.3.32`](https://github.com/CATIA-Systems/FMPy/tree/v0.3.32);
this repo at `bae149a` (`origin/main`, after #68).
Observed with OpenModelica 1.27.2 (`omc`, compiler `clang` 19.1.7 as configured by OMC, CMake 3.31.6), MSL 4.1.0, FMPy 0.3.32 on Python 3.11.18 (`uv run --no-project --python 3.11 --with fmpy==0.3.32`), Debian 13.7 x86_64, 4 cores.
Prior work: [FMPy as a simulator for reference-model comparison tests](https://github.com/phdorp/modelica-tools/blob/research/fmpy-reference-comparison/docs/research/2026-11-09-fmpy-reference-comparison.md) (FMPy capabilities, bit-identical OMC-exported vs Reference FMU). Its findings are taken as given.

## Question

What does OpenModelica 1.27.2's FMU export (`buildModelFMU`) give mtools, as facts a config and parameter design can rest on? From [#70](https://github.com/phdorp/modelica-tools/issues/70):

1. FMI versions and FMU types (`me`, `cs`, `me_cs`); for CS, which solvers can be embedded and how tolerance and step are fixed.
2. Which parameters stay tunable (`causality`/`variability` vs `isValueChangeable`), and whether the ADR 0001 build-variant wrapper exports unchanged.
3. Whether the Cpp target exports FMUs, and with what differences.
4. How libraries, extra sources and `Resources/` end up in the FMU; whether it is self-contained and relocatable.
5. What a cache key for an exported FMU needs beyond today's build key, and whether the `.mos` driver can call `buildModelFMU` the same way.
6. Signal names and types in `modelDescription.xml` vs the `.mat` columns of a native run.

## Method

1. Read the `buildModelFMU` signature and docs, its implementation (`callBuildModelFMU`), the FMI checks, the code that sets `causality`/`variability`/`isValueChangeable`, the FMU resource copying, and the FMI 2.0 CS runtime (solver selection, `fmi2SetupExperiment`, CVODE set-up) at `v1.27.2`. Every source claim cites `file:line` with a link.
2. Read the FMI 2.0.4 rules for `causality`, `variability` and when `fmi2SetXXX` is allowed, and FMPy's `apply_start_values` rules.
3. Wrote scratch models under `/tmp/omc-fmu-export/models/Pkg/` (a multi-file package with `Resources/`) and a user library under `/tmp/omc-fmu-export/libs/MyLib/` (see [Reproduction](#reproduction)). Exported them with `omc` scripts that mirror mtools' build script (`setCommandLineOptions`, `setModelicaPath`, `loadFile`, then `buildModelFMU`), built the same models natively with `buildModel`, and ran native binaries (`-outputFormat=mat`) and FMUs (FMPy `simulate_fmu`).
4. Compared `modelDescription.xml` with the native build's `_init.xml` and `.mat` name lists with small scripts.

**(verified)** means read in source or spec, or measured here. **(inference)** means my reasoning from verified pieces.

## Short answer

1. **FMI 2.0 only for anything useful.** `version="3.0"` is rejected (`Unknown FMU version 3.0`); 1.0 is ME only. 2.0 gives `me`, `cs` and `me_cs`. The default `fmuType` is `me`, not `me_cs` as the User's Guide says. CS embeds forward Euler (default, one step per communication step) or CVODE (`--fmiFlags=s:cvode`). CS CVODE's tolerance is the model's `experiment(Tolerance=...)`, compiled in. The importer's tolerance is ignored, so changing it needs a new export.
2. **Same rule as the native build.** `causality="parameter"` in `modelDescription.xml` exactly when `isValueChangeable="true"` in `_init.xml`. Both come from one `BackendVariable.isChangeable` call in the same code path. Every other parameter is `calculatedParameter`, and FMPy refuses to set it. All parameters are `variability="fixed"` (never `tunable`): settable before initialization only, which is all a run needs. The ADR 0001 wrapper (`model V extends M(n=3, …)`) exports unchanged with unchanged variable names. So build variants carry over one to one.
3. **Cpp exports ME only, and it is not usable for models with time events.** `fmuType="cs"` is downgraded to `me` with a warning. The Cpp FMU has the same variable names and causalities and a statically linked runtime. Under FMPy CVode a `when sample(...)` model produced ~5600 rows, its counter never ticked, and the run ended at t=0.99999999917. An event-free model ran correctly.
4. **Self-contained and relocatable, with two exceptions.**
   - Modelica code from the package, extra sources and libraries is compiled into the binary. The OMC runtime is linked statically. External static libraries are linked in. External shared libraries (with a SONAME) and CVODE's SUNDIALS libraries are copied next to the binary with `RUNPATH $ORIGIN`. Data files named by a **literal** `modelica://` URI are copied into `resources/`.
   - All of this ran after copying the FMU elsewhere and moving the package and the library away.
   - Exception 1: a URI only known at run time (a `String` parameter) is not copied, and the FMU then fails after the package moves.
   - Exception 2: a shared library without a SONAME fails to link in the export, though the native build accepts it.
5. **The driver reuses all stages unchanged. The key needs FMU-specific parts.**
   - Only the last stage changes: `buildModelFMU(...)` returns a path string (`""` on failure). A `<prefix>_FMU.makefile` tells a compile failure from a translation failure, as `<prefix>.makefile` does today.
   - The key additionally needs the artefact kind, the FMI version, the FMU type, the platforms argument, and the CMake version. For CS with CVODE it also needs the tolerance.
   - Outputs are never byte-identical: the GUID is random per export and is compiled into the binary. A hit must therefore be validated by inputs, as today.
6. **Same names as the `.mat` columns.** With the default `--fmiFilter=protected`, the FMU's non-parameter variables are exactly the `.mat` trajectory columns of a run without `-emit_protected`, including aliases, negated aliases and `der(...)`. `--fmiFilter=internal` matches `-emit_protected`, except that `$` is written as `_D_` (`_D_whenCondition1`). Types differ only in the reader: FMPy returns Integer as `int32`, while mtools uses `int64`.

## Findings

### 1. FMI versions, FMU types and CS solvers

**What is accepted (verified):**

| `version` / `fmuType` | Result (measured, model `Pkg.M`) | Source |
|---|---|---|
| `"2.0"` / `"me"` | `M.fmu` with `<ModelExchange>` | [`FMI.mo` L275-L287](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/FMI.mo#L275-L287) |
| `"2.0"` / `"cs"` | `<CoSimulation canHandleVariableCommunicationStepSize="true" …>` | same |
| `"2.0"` / `"me_cs"` | both elements in one `modelDescription.xml`, one binary | same |
| `"2.0"` / argument omitted | **ME only** | [`ModelicaBuiltin.mo` L2732](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/FrontEnd/ModelicaBuiltin.mo#L2732) (`fmuType = "me"`). The User's Guide says "By default an FMU that can be used for both Model Exchange and Co-Simulation is generated" ([`fmitlm.rst` L59](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/doc/UsersGuide/source/fmitlm.rst#L59)); the guide is wrong for `buildModelFMU` |
| `"3.0"` / any | `Error: Unknown FMU version 3.0. Only version 1.0 & 2.0 are supported.`, returns `""`, script exit code 0 | [`FMI.mo` L228-L237](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/FMI.mo#L228-L237); [`Error.mo` L1288-L1289](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/Error.mo#L1288-L1289); the v1.27.2 tree has only `CodegenFMU1.tpl` and `CodegenFMU2.tpl` |
| `"1.0"` / `"cs"` | `Error: Export of FMU type cs for version 1.0 is not supported. …` | [`Error.mo` L1292-L1293](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/Error.mo#L1292-L1293) |
| `"1.0"` / `"me"` | `fmiVersion="1.0"` FMU | |

- The checks run before translation ([`CevalScriptBackend.mo` L4394-L4406](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L4394-L4406)), so a bad version fails in ~1 s.
- The User's Guide states the supported set as "FMI 1.0 & FMI 2.0.4 for Model Exchange FMUs and FMI 2.0.4 for Co-Simulation FMUs" ([`fmitlm.rst` L60-L61](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/doc/UsersGuide/source/fmitlm.rst#L60-L61)).
- An `me_cs` FMU is risky with FMPy: `simulate_fmu(fmi_type=None)` picks CoSimulation whenever it is present ([FMPy `simulation.py` L711-L717](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L711-L717)), so an `me_cs` FMU silently runs the embedded Euler.

**CS solvers (verified):**

- `--fmiFlags` writes `resources/<prefix>_flags.json` ([`Flags.mo` L1272-L1274](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/Flags.mo#L1272-L1274); [`CodegenFMU.tpl` L129](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Template/CodegenFMU.tpl#L129)). Measured with `s:cvode`: `{"s" : "cvode"}`.
- Only `s` is understood. At export, `s` values other than `euler` and `cvode` and any other flag name only produce warnings ([`SimCodeUtil.mo` L13694-L13705](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/SimCode/SimCodeUtil.mo#L13694-L13705)).
- At run time the FMU parses only the solver (and the NLS name) from the JSON ([`fmu_read_flags.c` L106-L140](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu_read_flags.c#L106-L140); [`simulation_options.c` L1499-L1503](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/util/simulation_options.c#L1499-L1503)).
  - With no JSON, the solver is Euler. A model without states also uses Euler.
  - Any solver other than Euler or CVODE is a fatal `Unknown solver method` at `fmi2Instantiate` ([`fmu_read_flags.c` L183-L243](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu_read_flags.c#L183-L243)).
  - The guide lists the same two integrators ([`fmitlm.rst` L63-L88](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/doc/UsersGuide/source/fmitlm.rst#L63-L88)).
- **Step:**
  - Euler takes one explicit step from the current time to the next communication point, or to an earlier time event ([`fmu2_model_interface.c` L2335-L2342](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu2_model_interface.c#L2335-L2342)). So its accuracy is set by the importer's communication step.
    - Measured on `der(x) = -x`: step 0.1 gives `x(1) = 0.3486784401` (= 0.9^10); step 0.01 gives `0.3660323412732296`. The exact value is 0.36787944117144233.
  - CVODE steps adaptively with no maximum step size ([`cvode_solver.c` L464](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/simulation/solver/cvode_solver.c#L464)) and stops at each communication point ([`cvode_solver.c` L1025](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/simulation/solver/cvode_solver.c#L1025)).
- **Tolerance is fixed at export:**
  - CVODE is set up inside `fmi2Instantiate` ([`fmu2_model_interface.c` L742-L747](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu2_model_interface.c#L742-L747)). It takes `rtol = simulationInfo->tolerance` and `atol = nominal·rtol` ([`cvode_solver.c` L567-L579](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/simulation/solver/cvode_solver.c#L567-L579)).
  - That value is compiled into `<prefix>_init_fmu.c` from the experiment settings ([`CodegenFMU.tpl` L3298](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Template/CodegenFMU.tpl#L3298); measured: `simulationInfo->tolerance = 1e-6;`).
  - `fmi2SetupExperiment`'s tolerance is only stored and used as the zero-crossing tolerance ([`fmu2_model_interface.c` L843-L874](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/fmi/export/openmodelica/fmu2_model_interface.c#L843-L874)), although FMPy passes `relative_tolerance` there for CS ([FMPy `simulation.py` L1243](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1243)).
  - Measured with `Pkg.Decay`, CS with CVODE, communication step 0.1:

    | Export | FMPy `relative_tolerance` | `x(1)` |
    |---|---|---|
    | `Tolerance=1e-6` | default, 1e-3, 1e-12 | `0.36788040238055253` (all three identical) |
    | wrapper with `experiment(Tolerance=1e-10)` | default, 1e-3, 1e-12 | `0.3678794419755792` (all three identical) |

- **Runtime dependencies:** a CVODE CS FMU ships `libsundials_cvode.so.5` and `libsundials_nvecserial.so.5` in `binaries/linux64/`. The `.so` has `RUNPATH $ORIGIN` (measured). The guide asks for `--fmuRuntimeDepends=modelica` for this ([`fmitlm.rst` L72-L74](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/doc/UsersGuide/source/fmitlm.rst#L72-L74)), and that is already the default with CMake ≥ 3.21 ([`Flags.mo` L1339-L1351](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/Flags.mo#L1339-L1351)).

### 2. Which parameters stay tunable

**One rule, two outputs (verified):**

- For every parameter, `SimCodeUtil` computes `isValueChangeable := BackendVariable.isChangeable(dlowVar)` ([`SimCodeUtil.mo` L10028](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/SimCode/SimCodeUtil.mo#L10028)). It derives the FMI causality from that same Boolean: `PARAM` and changeable gives `parameter`; `PARAM` and not changeable gives `calculatedParameter` ([`SimCodeUtil.mo` L10139-L10159](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/SimCode/SimCodeUtil.mo#L10139-L10159)).
- `_init.xml` writes the same field ([`SerializeInitXML.mo` L366-L367](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/SimCode/SerializeInitXML.mo#L366-L367)).
- `isChangeable` is true for a parameter that is fixed, has no `Evaluate=true`, is neither `final` nor protected, and has a constant binding (or none and a constant start) ([`BackendVariable.mo` L2077-L2084](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/BackEnd/BackendVariable.mo#L2077-L2084)).
- Parameter variability is always `fixed`. `tunable` is never emitted ([`SimCodeUtil.mo` L10030](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/SimCode/SimCodeUtil.mo#L10030), `// TODO SimCodeVar.TUNABLE()` at [L10266](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/SimCode/SimCodeUtil.mo#L10266)).

**What FMI 2.0 and FMPy make of it (verified):**

- `parameter` must have `initial="exact"`. `calculatedParameter` is `calculated` (or `approx`) and "is computed during initialization" ([FMI 2.0.4 `2_2_common_schema.adoc` L762-L768](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/2_2_common_schema.adoc#L762-L768)).
- `fixed` means the value doesn't change after `fmi2ExitInitializationMode` ([L810-L811](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/2_2_common_schema.adoc#L810-L811)).
- `fmi2SetXXX` before initialization is allowed only for `initial = exact | approx` ([L876-L878](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/2_2_common_schema.adoc#L876-L878)).
- FMPy applies exactly that rule ([`simulation.py` L917-L924](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L917-L924), defaults [`model_description.py` L784-L790](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/model_description.py#L784-L790)). It raises `The start values for the following variables could not be set: …` for the rest ([`simulation.py` L1034-L1036](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1034-L1036)).

**Measured on `Pkg.M`** (C target; native build vs FMU `version="2.0"`, `fmuType="me"`; FMPy `start_values`):

| Parameter | Kind | `_init.xml` causality / `isValueChangeable` | FMU `causality` / `variability` | FMPy `start_values={name: …}` |
|---|---|---|---|---|
| `k = 1` | ordinary | `parameter` / true | `parameter` / `fixed` | set; `k=2` gives `x(1)=0.13531841236927444` |
| `x0 = 1` (start of `x`) | ordinary | `parameter` / true | `parameter` / `fixed` | set; `x(0)=3` |
| `y0[2] = {7, 8}` | array | `parameter` / true per element | `parameter` / `fixed` per element | `y0[1]` set |
| `k2 = 2*k` | dependent binding | `calculatedParameter` / false | `calculatedParameter` / `fixed` | refused |
| `n = 2` | array size | `calculatedParameter` / false | `calculatedParameter` / `fixed` | refused |
| `useB = true` | if-equation selector | `calculatedParameter` / false | `calculatedParameter` / `fixed` | refused |
| `g` (`Evaluate=true`) | evaluated | `calculatedParameter` / false | `calculatedParameter` / `fixed` | refused |
| `fk` (`final`) | final | `calculatedParameter` / false | `calculatedParameter` / `fixed` | refused |
| `pfree(fixed=false)` | initial equation | `calculatedParameter` / false | `calculatedParameter` / `fixed` | not tried |
| `pp` (protected) | protected | `calculatedParameter` / false, `isProtected` | **absent** (default `--fmiFilter=protected`) | refused (unknown name) |
| `xs[i](each start=1, fixed=true)` | state with literal start | `local` / true | `initial="exact"` | set; `xs[1]=2` |
| `x(start=x0, fixed=true)` | state with parameter start | `local` / false | no `initial` | not settable (set `x0`) |

The changeable set is identical in both files: 4 parameters plus 3 start values. That matches the shared code path above.

- For mtools (inference): the build-time parameters of an exported FMU are its `calculatedParameter`s.
- `variants.py:67` (`variability == "parameter" and not changeable`) would therefore read the same answer from `modelDescription.xml` as from `_init.xml`, except for protected parameters. Those are missing from the FMU, so they would surface as "unknown name" instead of "protected". Both are `ConfigError` today (`variants.py:41`).

**The ADR 0001 wrapper exports unchanged (verified):**

- `loadString("model Pkg_M_mtools_variant extends Pkg.M(g=1.5, n=3, useB=false); end Pkg_M_mtools_variant;")` followed by `buildModelFMU(Pkg_M_mtools_variant, version="2.0", fmuType="me", fileNamePrefix="model")` produced `model.fmu`. It has `modelName="Pkg_M_mtools_variant"` and `modelIdentifier="model"`.
- The variable names are unchanged apart from `xs[3]` and `der(xs[3])`, which the new size adds.
- Run with FMPy and `start_values={"k": 2}`: `n=3`, `g=1.5`, `useB=false`, `w(0) = -1.5`, `x(1) = 0.1353…`.
- So build variants carry over one to one: one export per distinct combination of build-time values, with ordinary parameters set per run.
- `fileNamePrefix` sets the `.fmu` name and the `modelIdentifier` ([`CevalScriptBackend.mo` L4420-L4421](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L4420-L4421)). FMPy reads the identifier from the XML, so a fixed internal prefix works as it does for native builds.

### 3. The Cpp target

- **ME only (verified).** With `--simCodeTarget=Cpp`, `fmuType="cs"` (and `me_cs`) gives `Warning: Export of FMU type cs is not supported with Cpp target. FMU will be for Model Exchange (me).` and an ME FMU ([`CevalScriptBackend.mo` L4408-L4411](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L4408-L4411); [`Error.mo` L1303-L1304](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/Error.mo#L1303-L1304)). Measured.
- **Different build path (verified).** Cpp runs the generated `<prefix>_FMU.makefile` and returns. It uses no CMake, no `--fmiFlags`, no runtime-dependency copying and no resource copying ([`CevalScriptBackend.mo` L4452-L4466](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L4452-L4466)).
- **What the Cpp FMU contains (measured on `Pkg.M`):**
  - 30 entries, 0.88 MB, no `resources/` directory.
  - `sources/` holds only the model's C++ files and `M_init.xml`; the C target ships the whole C runtime source.
  - The binary is 2.9 MB with the Cpp runtime linked statically (`NEEDED` only `libm`, `libc`, `ld-linux`; no `RUNPATH`).
  - Same variable names, causalities and `DefaultExperiment` as the C FMU. `numberOfEventIndicators="2"` (C: `1`).
- **Behaviour under FMPy (measured):**
  - `Pkg.Decay` (no events): correct. ME CVode `x(1)=0.36787977`; Euler `0.3584859224` = 0.95^20. `k=2` was applied.
  - `Pkg.M` (a `when sample(0.1, 0.1)` counter) with ME CVode and output interval 0.05:
    - 5595 rows, with events every ~0.00085 s;
    - `cnt` stayed 0, the last time was `0.9999999991706195`, and `x(1)=0.36808` (the C FMU gives 0.36788).
  - With ME Euler, `cnt` reached 9; the C FMU reaches 10.
  - The time-event path in the Cpp FMU wrapper ([`FMU2Wrapper.cpp` L438-L470](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/cpp/FMU2/FMU2Wrapper.cpp#L438-L470)) was read but not debugged. **Root cause not determined.**
- Inference: an FMU-based test path should support exporting from the C target only, and treat `build.target="Cpp"` with an exported FMU as a `ConfigError`.

### 4. Libraries, extra sources, `Resources/`; self-contained and relocatable

**What goes where (measured with `Pkg.MRes` and `Pkg.MShared`, C target):**

| Input | In the FMU | Relocatable? |
|---|---|---|
| Modelica classes from the package, `extra_sources` and libraries (MSL `CombiTable1Ds` and `Ramp`; `MyLib` from a directory on the library path) | Compiled into `binaries/linux64/<id>.so`. No Modelica source is shipped. `sources/` holds generated C plus the OMC C runtime (`--fmiSources=true` by default, [`Flags.mo` L1269-L1271](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/Flags.mo#L1269-L1271)) | yes |
| OMC C runtime, MSL `ModelicaExternalC` and tables | Compiled from `sources/` and linked statically: `NEEDED` only `libm`, `libc`; `RUNPATH $ORIGIN` | yes |
| C code from `Resources/Include` (`Include=`, `IncludeDirectory=`) | Compiled in (`a = 2·time` correct) | yes |
| Static library `Resources/Library/libpkgoffset.a` | Linked in (`b = time + 100` correct) | yes |
| Shared library `Resources/Library/linux64/libpkgshared.so` **with** a SONAME | Copied to `binaries/linux64/libpkgshared.so`; `NEEDED libpkgshared.so`, `RUNPATH $ORIGIN` (`a = 3·time` correct) | yes |
| The same shared library **without** a SONAME | **Export fails:** `/usr/bin/ld: cannot find -llibpkgshared`. The native `buildModel` builds and runs it | — |
| Data file named by a literal URI: `loadResource("modelica://Pkg/Resources/Data/table.txt")` | Copied to `resources/<absolute source path>`, here `resources/tmp/omc-fmu-export/models/Pkg/Resources/Data/table.txt`. The code calls `OpenModelica_fmuLoadResource("<absolute path>")`; at run time it loaded from `<unzip dir>/resources/tmp/…/table.txt` | yes |
| Data file named by a URI held in a `String` parameter (`Pkg.MUri`) | **Not copied**, no warning (`resources/` is empty). Works in place. After moving the package: `fmi2ExitInitializationMode failed`, `Not possible to open file "/tmp/omc-fmu-export/models/Pkg//tmp/tmp…/resources/Resources/Data/table.txt"` | **no** |
| CVODE (CS with `s:cvode`) | `libsundials_cvode.so.5` and `libsundials_nvecserial.so.5` copied, `RUNPATH $ORIGIN` | yes |

Mechanism (verified):

- `getResources` collects the literal arguments of `OpenModelica_fmuLoadResource` ([`SimCodeUtil.mo` L15376-L15422](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/SimCode/SimCodeUtil.mo#L15376-L15422)). `SimCodeMain` copies each one with `cp -rf` to `resources/<path>` ([`SimCodeMain.mo` L782-L799](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/SimCode/SimCodeMain.mo#L782-L799)).
- Only an unresolved `OpenModelica_uriToFilename` call raises warning 597 and copies every loaded package's directory ([`SimCodeUtil.mo` L15400-L15406](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/SimCode/SimCodeUtil.mo#L15400-L15406); [`Error.mo` L1112-L1113](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/Error.mo#L1112-L1113)). The `String`-parameter case compiled to `OpenModelica_fmuLoadResource(file)` and hit neither branch.
- External libraries are looked up with CMake `find_library` over the `LibraryDirectory` and its `linux64` / `x86_64-linux` subdirectories (generated `CMakeLists.txt`). With `RUNTIME_DEPENDENCIES_LEVEL=modelica` they are installed next to the binary, excluding system libraries ([`fmitlm.rst` L134-L145](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/doc/UsersGuide/source/fmitlm.rst#L134-L145)).
- This matches the FMI rule that an FMU "should contain all resources that are required to load and execute a shared library" ([`2_3_fmu_distribution.adoc` L95](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/2_3_fmu_distribution.adoc#L95)).

**Relocation test (measured):**

- Copied `MRes.fmu`, `MShared.fmu` and two CS FMUs to `/tmp/omc-fmu-export/moved/`, and renamed the package and library directories away.
- All ran with FMPy (which unzips to a fresh temp directory per run) and gave the same values as before the move.
- Only `MUri.fmu` broke, as in the table.
- `platforms={"dynamic"}` produced the same `CMakeLists.txt` and the same `NEEDED` list as the default `{"static"}`. In 1.27.2 both branches run the same CMake command ([`CevalScriptBackend.mo` L3859-L3894](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L3859-L3894)).

### 5. Cache key and the `.mos` driver

**The driver (verified by running an mtools-style script):**

- Stages 1–6 of `build_script` (`src/mtools/internal/omc/script.py:81-118`: options, library path, `loadModel`, `loadFile`, `getLoadedLibraries()`, `getSimulationOptions`) run unchanged before `buildModelFMU`.
  - `buildModelFMU` reads `__OpenModelica_commandLineOptions` from the model and restores the flags afterwards, like `buildModel` ([`CevalScriptBackend.mo` L4355](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L4355)).
  - A `loadString` wrapper also works (section 2).
- Only the build stage changes:

  ```
  result := buildModelFMU(<model>, version="2.0", fmuType="me", fileNamePrefix="model");
  <errors section 17>
  if result == "" then if regularFileExists("model_FMU.makefile") then exit(18); else exit(17); end if; end if;
  ```

  - `buildModelFMU` returns the absolute path `<cwd>/<fileNamePrefix>.fmu`, or `""` on any failure ([`CevalScriptBackend.mo` L4434](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L4434)). `buildModel` returns a tuple; today's check is `result[1] == ""` (`script.py:121-127`).
  - `<prefix>_FMU.makefile` exists once translation succeeded.
- Measured exits:
  - `Pkg.M`: exit 0, `model.fmu`.
  - `Pkg.BrokenM` (type error): exit 17, only `build.mos` and `omc.out` left.
  - `Pkg.BrokenC` (C syntax error in `Include`): exit 18. The error text is `Error: Error building simulator. Build log: cmd: cd '210.fmutmp/sources/' && … cmake …` with the CMake log. It still contains the compiler line `…/BrokenC_includes.h:7:40: error: expected expression`, which today's compile filter keeps.
- Side effects to know:
  - The build happens in `<hash>.fmutmp/` in the current directory, and the `.fmu` is zipped from it ([`CevalScriptBackend.mo` L4448](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L4448), [L4508](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L4508)).
  - The directory is removed on success ([L4520](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L4520)) but **left behind after a compile failure** (measured). mtools' throwaway build directory absorbs that.
  - The `zip` binary must be on `PATH` (L4508).
  - The default `--fmiFilter=protected` builds with `-DCMAKE_BUILD_TYPE=Release` ([L3836-L3837](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L3836-L3837)).
- **Cost (measured, 4 cores):** native `buildModel(Pkg.M)` took 1.9–3.0 s; `buildModelFMU(Pkg.M)` took 6.6–8.4 s (C), 5.5 s (Cpp). The C FMU compiles the whole runtime from source with CMake. `M.fmu` is 1.06 MB with 273 entries.

**What the cache key needs beyond `cache_key` (`src/mtools/internal/omc/cache.py:68-96`):**

| Part | Why | Status today |
|---|---|---|
| Artefact kind (native build vs FMU) | Same sources and flags give a different product | missing |
| `version`, `fmuType`, `platforms` | `buildModelFMU` arguments, not flags | missing (covered by `backend_version` only while they are hard-coded in the template) |
| FMU flags `--fmiFlags`, `--fmiFilter`, `--fmiSources`, `--fmuRuntimeDepends`, `--fmuCMakeBuild` | Change solver, exposed variables and contents | covered if they arrive through `omc_flags`; must be added if mtools sets them itself |
| CMake version | The C FMU is configured and built by CMake (`Autoconf.cmake`, [`CevalScriptBackend.mo` L3859-L3894](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L3859-L3894)) | missing |
| The C compiler OMC actually uses | CMake gets `-DCMAKE_C_COMPILER=<basename of OMC's configured compiler>` ([L3832](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScriptBackend.mo#L3832)), measured `clang`. The native makefile also has `CC=clang` | **`compiler_version()` hashes `$CC` or `gcc --version` (`cache.py:105-106`), which is not the compiler OMC used here. This gap exists for native builds too** |
| CS + CVODE tolerance | Compiled in from `experiment(Tolerance=…)` (section 1) | in the source hash only if it comes from the model; a run-settings tolerance would have to become a build value, like ADR 0001 variants |
| Build-time parameter values | Variants work as for native builds (section 2) | covered (`build_values`) |
| Resource files | Literal-URI files are copied from the package's `Resources/`, which the package-root hash already covers | covered. Runtime-only URIs make the cached FMU depend on the source path, so a hit `_relocate`d from another checkout would point at the old path (inference) |

- **No output-based validation:** the GUID is a fresh UUID per export ([`CodegenFMU.tpl` L100](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Template/CodegenFMU.tpl#L100)) and is compiled into the binary. `generationDateAndTime` is in the XML. Two exports of identical inputs differed in both `modelDescription.xml` and the `.so` (measured).
- The FMU also embeds absolute source paths (`info.filename`, resource paths). The existing input-based key plus `getLoadedLibraries()` validation (`cache.py:167-184`) applies unchanged (inference).

### 6. Signal names and types vs the native `.mat`

**Names (measured, `Pkg.M`):**

| Variable kind | Native `.mat` (no `-emit_protected`) | FMU `modelDescription.xml` (default filter) |
|---|---|---|
| States, algebraic, output, discrete Integer and Boolean | `x`, `xs[1]`, `xs[2]`, `out`, `w`, `cnt`, `flag` | same names |
| Derivatives | `der(x)`, `der(xs[1])`, `der(xs[2])` | same names (`local`) |
| Alias `y = x` | `y` (dataInfo `+2`, shares column of `x`) | `y`, same `valueReference` as `x` |
| Negated alias `z = -x` | `z` (dataInfo `-2`) | `z`, own `valueReference`; FMPy returned `-x` |
| Protected `hidden`, internal `$whenCondition1` | only with `-emit_protected` | only with `--fmiFilter=internal`, as `hidden` and **`_D_whenCondition1`** (`$` → `_D_`, [`CodegenFMUCommon.tpl` L517](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Template/CodegenFMUCommon.tpl#L517)) |
| `time` | `time` | not listed (implicit independent variable, [FMI 2.0.4 L779-L784](https://github.com/modelica/fmi-standard/blob/v2.0.4/docs/2_2_common_schema.adoc#L779-L784)); FMPy adds a `time` column |

- **Set comparison (script output):** 12 non-parameter FMU variables vs 12 `.mat` trajectory columns, with no difference either way. With `--fmiFilter=internal` against `-emit_protected`, the only difference is `_D_whenCondition1` vs `$whenCondition1`.
- **`Pkg.MRes` (MSL components):** 7 vs 7 signals, no difference. The FMU additionally lists the String parameters `tab.tableName` and `tab.delimiter`, which the `.mat` does not store.
- The filter options are documented in [`Flags.mo` L1260-L1268](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Util/Flags.mo#L1260-L1268).

**Types (measured):**

- FMPy result dtypes: Real `float64`, Integer `int32`, Boolean `bool` ([FMPy `simulation.py` L111](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L111)).
- The backend spec casts Integer and enumeration columns to `int64` and Boolean to `bool` from `_init.xml` types. With an FMU, the XML element (`<Real/>`, `<Integer/>`, `<Boolean/>`, `<Enumeration/>`, `<String/>`) gives the same information.

### Other observations

- **FMPy and CVODE trip over time events at grid points (measured, not root-caused).** The C FMU of `Pkg.M` (`when sample(0.1, 0.1)`) failed in two cases:
  - With FMPy ME CVode at output interval 0.01 and 0.03: `CVode error (code -27) … tout too close to t0 to start integration`. Intervals 0.05, 0.1 and 0.0125 ran.
  - As a CS FMU with embedded CVODE at communication step 0.1: `fmi2DoStep: ##CVODE## -27 error occurred at time = 0.6`.

  Inference: a time event a few ulps from a communication or output point (FMPy uses `start + (n+1)·interval`, [`simulation.py` L1093](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1093), [L1289](https://github.com/CATIA-Systems/FMPy/blob/v0.3.32/src/fmpy/simulation.py#L1289); 6·0.1 = 0.6000000000000001) leaves CVODE a zero-length step. This contradicts the prior note's "#882 not reproduced with OMC-exported FMUs", which used other event times. It matters for "Test FMUs for CI" on the map.
- **CS Euler is a different model of accuracy:** its error is O(step), so a CS export compared against a native run or an ME run will not match within solver tolerances (prior note: |Δ| 0.35 on VanDerPol).
- **Notifications:** loading `MyLib` happened "due to usage" during `buildModelFMU`, after the `getLoadedLibraries()` stage. That is the same as `buildModel`, so a library that is only auto-loaded during translation is missing from the build record (not specific to FMUs).

## Open questions

- Why the Cpp ME FMU mis-handles `sample()` under FMPy CVode (section 3). Not debugged; the recommendation to export from C only does not depend on it.
- Whether FMI 3.0 export exists on OpenModelica `master` or a later release. Only the v1.27.2 tag was checked.
- Whether `causality` always equals `isValueChangeable` for every model. The code path is shared (section 2), but only one model with seven parameter kinds was measured. Records, enumerations and `fixed=false` parameters with a binding were not exercised.
- The exact trigger of the CVODE `-27` errors (section "Other observations"): FMPy grid arithmetic vs OMC's sample-time arithmetic is a hypothesis.
- Whether a cached FMU should be unzipped once (FMPy `extract`) and reused across runs, or unzipped per run as `simulate_fmu(filename)` does. That is a caching ticket.
- Cpp FMUs with `loadResource` and external libraries were not tested; the Cpp path skips resource copying (L4452-L4466), so they are probably not relocatable (inference).

## Reproduction

Everything is under `/tmp/omc-fmu-export/` (scratch, not in the repo): models in `models/Pkg/` and `libs/MyLib/`, scripts in `scripts/`, outputs in `work/<case>/`. Nothing was added to `pyproject.toml`. OMC sources are read from a partial clone at `v1.27.2`.

```bash
# export: fmu.sh <workdir> <class> <extra buildModelFMU args> [omc flags] [mos lines before the build]
# env TARGET=--simCodeTarget=Cpp switches the target
S=/tmp/omc-fmu-export/scripts W=/tmp/omc-fmu-export/work
for t in me cs me_cs; do $S/fmu.sh $W/fmu20_$t Pkg.M ", version=\"2.0\", fmuType=\"$t\""; done
$S/fmu.sh $W/fmu_default Pkg.M ""                                    # ME only
$S/fmu.sh $W/fmu30 Pkg.M ', version="3.0", fmuType="me"'            # Unknown FMU version 3.0
$S/fmu.sh $W/fmu10cs Pkg.M ', version="1.0", fmuType="cs"'          # not supported
$S/fmu.sh $W/cs_cvode Pkg.M ', version="2.0", fmuType="cs"' '--fmiFlags=s:cvode'
$S/fmu.sh $W/variant Pkg_M_mtools_variant ', version="2.0", fmuType="me", fileNamePrefix="model"' "" \
  'ok := loadString("model Pkg_M_mtools_variant extends Pkg.M(g=1.5, n=3, useB=false); end Pkg_M_mtools_variant;");'
TARGET=--simCodeTarget=Cpp $S/fmu.sh $W/cpp_me Pkg.M ', version="2.0", fmuType="me"'
TARGET=--simCodeTarget=Cpp $S/fmu.sh $W/cpp_cs Pkg.M ', version="2.0", fmuType="cs"'   # warning, ME
$S/fmu.sh $W/mres Pkg.MRes ', version="2.0", fmuType="me"'
$S/fmu.sh $W/mshared Pkg.MShared ', version="2.0", fmuType="me"'
$S/fmu.sh $W/muri Pkg.MUri ', version="2.0", fmuType="me"'
$S/fmu.sh $W/filter_internal Pkg.M ', version="2.0", fmuType="me"' '--fmiFilter=internal'
$S/mtools_like.sh $W/mt_Pkg.BrokenC Pkg.BrokenC                     # exit=18

# native build and run for comparison
cd $W/native_M && omc $S/native_M.mos && ./model -outputFormat=mat -r=res.mat && ./model -outputFormat=mat -emit_protected -r=res_prot.mat

# readers (Python -I, scripts outside the data directories)
P="uv run --no-project --python 3.11 --with numpy --with scipy --with fmpy==0.3.32 python -I"
$P $S/vars.py $W/native_M/model_init.xml                 # causality / isValueChangeable table
$P $S/vars.py $W/fmu20_me/x/modelDescription.xml         # causality / variability table
$P $S/compare_names.py $W/fmu20_me/x/modelDescription.xml $W/native_M/res.mat
$P $S/runfmu.py $W/fmu20_me/M.fmu ModelExchange '{"n": 3}' x '{"output_interval": 0.05}'   # refused
$P $S/runfmu.py $W/decay_cvode/Decay.fmu CoSimulation - x '{"output_interval": 0.1, "relative_tolerance": 1e-12}'
```

`Pkg.M` (the parameter-kinds model):

```modelica
within Pkg;
model M "Parameter kinds, aliases, discrete and protected variables"
  parameter Real k = 1;  parameter Real k2 = 2*k;  parameter Integer n = 2;
  parameter Boolean useB = true;  parameter Real g = 9.81 annotation(Evaluate = true);
  parameter Real x0 = 1;  parameter Real y0[2] = {7, 8};  final parameter Real fk = 3;
  parameter Real pfree(fixed = false);
  Real x(start = x0, fixed = true);  Real xs[n](each start = 1, each fixed = true);
  Real y;  Real z;  Real w;  output Real out;  Integer cnt(start = 0, fixed = true);  Boolean flag;
protected
  parameter Real pp = 0.5;  Real hidden;
initial equation
  pfree = 2*x0;
equation
  der(x) = -k*x;
  for i in 1:n loop der(xs[i]) = -i*xs[i]; end for;
  y = x;  z = -x;
  if useB then w = g*x; else w = -g*x; end if;
  out = w + pp + k2 + fk + pfree + y0[1];  hidden = 2*x;  flag = x > 0.5;
  when sample(0.1, 0.1) then cnt = pre(cnt) + 1; end when;
  annotation(experiment(StartTime = 0, StopTime = 1, Interval = 0.01, Tolerance = 1e-6));
end M;
```

The other models:

- `Pkg.Decay`: `der(x) = -k*x`, `Tolerance=1e-6`; a wrapper `DecayTight` sets `Tolerance=1e-10`.
- `Pkg.MRes`: `Gain` from `Resources/Include`, `Offset` from `Resources/Library/libpkgoffset.a`, a `CombiTable1Ds` reading `modelica://Pkg/Resources/Data/table.txt`, `MyLib.twice`, a constant `MyLib.Scale.y = 4.5`, and an MSL `Ramp`.
- `Pkg.MShared`: a function from `Resources/Library/linux64/libpkgshared.so`, built with `cc -shared -fPIC [-Wl,-soname,libpkgshared.so]`.
- `Pkg.MUri`: `CombiTable1Ds` with `fileName = loadResource(file)` and `parameter String file`.
- `Pkg.BrokenM` (`Integer t = 1.5`) and `Pkg.BrokenC` (a C syntax error in `Include`).

Key numbers:

| Case | Result |
|---|---|
| CS Euler `Pkg.M`, step 0.1 / 0.01 | `x(1)` = 0.3486784401 / 0.3660323412732296 |
| CS CVODE `Pkg.Decay`, `Tolerance=1e-6`, step 0.1, FMPy rtol default / 1e-3 / 1e-12 | 0.36788040238055253 (all) |
| CS CVODE `DecayTight`, `Tolerance=1e-10`, step 0.1 | 0.3678794419755792 (all rtol) |
| FMPy ME CVode `Pkg.M` C FMU, interval 0.05 | 33 rows, `x(1)`=0.3678751723442507, `cnt`=10 |
| FMPy ME CVode `Pkg.M` Cpp FMU, interval 0.05 | 5595 rows, last t=0.9999999991706195, `cnt`=0, `x(1)`=0.36807651075951375 |
| Export time `Pkg.M` | native 1.9–3.0 s; FMU C 6.6–8.4 s; FMU Cpp 5.5 s |
| FMU size `Pkg.M` | C ME 1,064,883 B (273 entries); CS+CVODE 1,328,267 B; Cpp 880,550 B (30 entries) |
