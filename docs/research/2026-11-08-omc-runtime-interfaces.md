# OMC runtime interfaces: how C and Cpp simulation binaries take settings and write results

Date: 2026-11-08
Ticket: #45 (map #43, feature #42)
Observed with OpenModelica 1.27.2 on Linux (`omc --simCodeTarget=C|Cpp -s Model.mo`, then `make -f Model.makefile`).

Sources (primary, highest trust first):

- The built binaries themselves: `./Model -help`, `./Model -help=<flag>` (C) and `./Model --help` (Cpp), OMC 1.27.2.
- C runtime source at tag `v1.27.2`:
  [`simulation_input_xml.c`](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/c/simulation/simulation_input_xml.c)
  (`read_experiment` L888–935, `singleOverride` L1288–1323, `doOverride` L1334–1530).
- Cpp runtime source at tag `v1.27.2`:
  [`OMCFactory.cpp`](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/cpp/SimCoreFactory/OMCFactory/OMCFactory.cpp)
  (options L354–396, settings L440–563, `handleOverrides` L570–608, flag aliases L610–628),
  [`XmlPropertyReader.cpp`](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/cpp/Core/DataExchange/XmlPropertyReader.cpp)
  (L57–160),
  [`SimulationMonitor.cpp`](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/SimulationRuntime/cpp/Core/Solver/SimulationMonitor.cpp),
  and the generated `OMCpp<Model>Main.cpp` / `OMCpp<Model>Initialize.cpp`.
- [OpenModelica User's Guide, "Simulation Flags"](https://openmodelica.org/doc/OpenModelicaUsersGuide/latest/simulationflags.html)
  (page build `v1.28.0-dev-1799`). It documents the C runtime only. The Cpp runtime has no user documentation, so its source and `--help` are the references.
- [`scipy.io.loadmat`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.io.loadmat.html) (v1.18.0) and DyMat 0.7 (PyPI sdist, 2015).
- Prior work: `src/mtools/internal/pydelica_patch.py`, `tests/session_tools/test_cpp_target.py`, pydelica 0.6.3
  (`pydelica/__init__.py` `Session.simulate`, `model.py` `write_params`, `solutions.py`).

## Question

How do the simulation binaries from OMC's C and Cpp targets accept run settings and produce results, so that mtools can
configure a run without pydelica? Which parameters can change **without rebuilding** (this decides the build cache key)?
What do time range, tolerance, solver, variable filter, output format, and protected-variable output look like for each target?
Which result files and formats are written, and how can `.mat` be read cheaply? What are the exit codes, failure output,
and timeout mechanisms? Can one built binary run concurrently with different settings?

## Method

1. Wrote scratch models outside the repo (Appendix A): `Rt` (one parameter of each kind), `Struct` (if-equation,
   for-range, and protected parameters), `AssertM` (error and warning asserts), `Chatter`, and `Slow` (a long run for timeouts).
2. Built each one for both targets. Then ran each binary from its own empty working directory with different flags,
   overrides, and edited `_init.xml` copies, and compared result values with the analytic expectation
   (e.g. `x(2) = x0·exp(-2k)`, `w = 5k + kStruct`, `z = 2k·t`).
3. Read the relevant C and Cpp runtime source at tag `v1.27.2` to explain each observation. Every claim below is either
   observed (marked *obs.*) or quoted from source/docs (marked with the file).

## Findings

### 1. What a build produces and what a run needs

| | C (`--simCodeTarget=C`) | Cpp (`--simCodeTarget=Cpp`) |
|---|---|---|
| Executable | `<Model>` (links `libSimulationRuntimeC.so`) | `<Model>`, plus `OMCpp<Model>.so`; solver libs `dlopen`ed from `-R` |
| Run inputs read | `<Model>_init.xml` **and** `<Model>_JacA.bin` (sparsity pattern) from `-inputPath` (default: cwd). `_info.json` is optional. *obs.*: without `_JacA.bin` → rc 255 `Could not open sparsity pattern file` | `<Model>_init.xml` only, from `--input-path` (default: `-M`, the build dir). *obs.*: an input dir containing only `_init.xml` works |
| Experiment defaults | `<DefaultExperiment>` element in `_init.xml` (startTime, stopTime, stepSize, tolerance, solver, outputFormat, variableFilter) | **Compiled in**: `OMCpp<Model>Main.cpp` sets `opts["-S"]…opts["-F"]` from the `experiment` annotation, including absolute `-R`, `-M`, and `-F <builddir>/<Model>_res.mat`. `_init.xml` has no `DefaultExperiment`. The `<Model>.sh` wrapper repeats these values; it `exec ./<Model>`, so it only works with the build dir as cwd |
| Writes into build dir during a run | Nothing (*obs.*, `find -newer` after 16 concurrent runs) | Nothing, **as long as** `-F` is given; without `-F` the result goes to the compiled-in absolute `<builddir>/<Model>_res.mat` (*obs.*) |

### 2. Parameters: what changes without a rebuild

OMC marks this explicitly in `_init.xml`: each `ScalarVariable` has `isValueChangeable="true|false"`. The C runtime
gates overrides on it (`singleOverride`, `simulation_input_xml.c` L1293–1322). Both targets write identical flags for the same model (*obs.*):

| Parameter kind (example) | `causality` (C XML) | `isValueChangeable` | C `-override` | Edited `_init.xml` start (C `-f` / Cpp `--input-path`) |
|---|---|---|---|---|
| Plain tunable `parameter Real k = 2` | `parameter` | true | applied | applied |
| Boolean used in an if-**expression** (`z = if useB then …`) | `parameter` | true | applied | applied |
| State start value (`x(start=1, fixed=true)`) | `local` | true | applied | applied |
| Binding depends on another parameter (`kDep = 2*k`) | `calculatedParameter` | false | warning, ignored; **recomputed from `k`** | silently ignored; recomputed from `k` |
| `annotation(Evaluate=true)` | `calculatedParameter` | false | warning, ignored | silently ignored (value is a literal in generated code) |
| `final parameter` | `calculatedParameter` | false | warning, ignored | silently ignored |
| Array size (`Real y[n]`), for-range (`1:m`) | `calculatedParameter` | false | warning, ignored | silently ignored |
| Boolean selecting an if-**equation** branch | `calculatedParameter` | false | warning, ignored | silently ignored |
| `protected parameter` | `calculatedParameter` | false | warning, ignored | silently ignored |
| `parameter … (fixed=false)` + initial equation | `calculatedParameter` | false | warning, ignored | silently ignored |

The C warning text is `It is not possible to override the following quantity: <name>` / `It seems to be structural, final,
protected or evaluated or has a non-constant binding.` (L1318). An unknown name only gives
`override variable name not found in model: <name>`. **Both cases exit 0** (*obs.*). The Cpp runtime has no override flag:
`-override` is reported as `unrecognized command line options` and ignored, also with rc 0 (*obs.*).
The Cpp `XmlPropertyReader` reads every `start` attribute and does not check `isValueChangeable` (L68–160). Non-changeable values are then overwritten or never read by generated code (`initParameterEquations`), so edits to them are lost **without any message** (*obs.*).

Consequence for the build cache: the set of parameters that can vary within one build is exactly the set with
`isValueChangeable="true"`. OMC computes it during translation, so mtools cannot know it before the first build.
OMC decides which parameters are structural, not the model author, e.g. `useB` (if-expression) is tunable but `useIf`
(if-equation) is not. Values for the rest can only change through translation-time modifiers, which must be part of the cache key.

### 3. Run settings per target

| Setting | C runtime flag (1.27.2) | Cpp runtime flag |
|---|---|---|
| Start / stop time | `-startTime=`, `-stopTime=` | `-S`, `-E` (also accepts `-startTime=`, `-stopTime=`, mapped by `handleOverrides` L572–575) |
| Output grid | `-stepSize=`. If start/stop is given without `-stepSize`, it recomputes `(stop-start)/500` and warns (`read_experiment` L904–913, *obs.* 503 rows). No `numberOfIntervals` flag | `-H` step size, `-G` number of intervals (used only if `-H` ≤ 0, L443–444). Compiled-in `-H` wins over `-G` (*obs.*) |
| Tolerance | `-tolerance=` | `-T` |
| Solver | `-s=` | `-I` (also `-s=`) |
| Variable filter (POSIX ERE, full match) | `-variableFilter=` | `-B` (`std::regex_match`) |
| Output format | `-outputFormat=mat\|csv\|plt\|empty` | `-P mat\|csv\|buffer\|empty` (`plt` → rc 1 `Unknown output-format plt`, *obs.*) |
| Result file name | `-r=` (name used verbatim; relative → **cwd**; the extension is not adjusted to the format, *obs.*: CSV text written to `rel3.mat`) | `-F` (relative → **cwd**; an extension of a known format is rewritten to match `-P`, L517–521) |
| Output directory | `-outputPath=`: only used for the **default** `<Model>_res.<fmt>` name, not for `-r` (*obs.*) | `--output-path`: **not used for the result file** (*obs.*: relative `-F` lands in cwd, default `-F` in the build dir) |
| Input directory | `-inputPath=` | `--input-path` (falls back to `-M`) |
| Protected variables | `-emit_protected` | `-U protected` / `-U all` (`-emit_protected` is mapped to `emit-results protected`, L625) |
| Parameters / start values | `-override=a=1,b=2`; `-overrideFile=<path>`; or `-f=<edited copy of _init.xml>` | Only by editing a copy of `_init.xml` and passing `--input-path` |
| Logging | `-lv=LOG_…`, `-logFormat=text\|xml` | `-V cat=lvl`, `-X txt\|xml` |
| Chatter guard | `-abortSlowSimulation` | none (`-abortSlowSimulation` is on an ignore list, L612, yet still warned as unrecognized, *obs.*) |
| Wall-clock limit | `-alarm=<s>` (SIGALRM) | `-A <s>` (default 360): **ineffective**, see §5 |
| Unknown flag | rc 1, prints usage | warning on stderr, **rc 0** |

**C: `-override` no longer sets experiment settings.** Up to v1.25 `doOverride` accepted
`solver,startTime,stopTime,stepSize,tolerance,outputFormat,variableFilter` as override keys (v1.25.0 L1032). From v1.26
`read_experiment` takes them from dedicated flags (`FLAG_START_TIME` … `FLAG_VARIABLE_FILTER`, v1.27.2 L892–935), and
`-override=stopTime=1` only warns `override variable name not found in model: stopTime` and is ignored (*obs.*). Code written
against older docs, or OMPython-style `-override=stopTime=…`, silently uses the annotation's values on 1.27.2.

**C: `-overrideFile` quirks** (`doOverride` L1348–1398, all *obs.*):

- A last line without a trailing `\n` is **silently dropped**; only `\n`-terminated lines are read.
- Lines whose first or second character is `/` are skipped as comments. A `#` line aborts with rc 1 `Invalid format for value of override flag: (null)`.
- A relative path resolves against cwd.
- Contrary to the guide ("`-overrideFile` CANNOT be used with `-override`"), 1.27.2 merges both; for a duplicate name, the file value wins with a warning.

**Solvers.** C (`-help=s`): `dassl` (default), `ida`, `cvode`, `gbode`, `euler`, `rungekutta` (deprecated), `qss`
(deprecated, experimental), `symSolver`/`symSolverSsc` (need `--symSolver` at translation), `optimization`. All of `dassl`, `ida`,
`cvode`, `gbode`, `euler`, `rungekutta`, `qss` ran on `Rt` (*obs.*). Cpp (installed libs: DASSL, CVode, IDA, Euler, RTEuler,
RK12, Peer): only `dassl`, `cvode`, `ida` work. `euler`, `rk12`, `peer`, `RTEuler` **segfault (rc 139)** on all four test
models. `rungekutta`/`implicit_euler`/unknown names fail with rc 1 `Selected Solver is not available` (*obs.*).

**Cpp DASSL ignores the output grid.** It writes every internal step: 125 rows for `-H 0.1 -E 2`, starting at
`1e-24, 3e-24, …`, even with `-O step`. CVODE and IDA honour the grid (`0 0 0.25 0.5 0.75 1 1 1`) (*obs.*).
Both targets repeat time points at events and at the stop time, so the time column is non-decreasing, not strictly increasing.

### 4. Result files and formats

| | C | Cpp |
|---|---|---|
| Default name | `<Model>_res.<fmt>` in `-outputPath` (else cwd) | compiled-in absolute `<builddir>/<Model>_res.mat` |
| Formats | `mat`, `csv`, `plt`, `empty`; `-noemit` writes nothing | `mat`, `csv`, `buffer`, `empty` |
| CSV numbers | full double precision (`0.01831609502171534`) | **6 significant digits** (`0.0183167`, `1.6383e-20`) and a trailing comma on each line |
| CSV contents | time-varying variables only; **parameters are not written** | same (parameters absent) |
| MAT contents | MATLAB v4, `Aclass = Atrajectory / 1.1 / binTrans`, `name`, `description`, `dataInfo`, `data_1` (parameters, 2 time points), `data_2` (trajectories) | same layout and full precision; parameters included |
| Other files | `<Model>_prof.*` with `-lv=LOG_STATS`/profiling | none observed |
| After a failed run | partial result file left behind (CSV truncated at the failure time). After `-alarm` the `.mat` header is not finalised and the file is **unreadable** | partial file left behind |

The current pydelica path reads only `*_res.csv` (`pydelica/solutions.py`). For the Cpp target, `pydelica_patch._CppRuntimeOptions`
therefore requests CSV and gets 6-digit values. `tests/session_tools/test_cpp_target.py` compares with `rtol=1e-4`, which hides this.

**Python readers for OMC `.mat`** (MATLAB v4 binTrans):

- A ~40-line numpy-only reader (Appendix B) read both C and Cpp files correctly (*obs.*), including parameters from
  `data_1`, negated aliases via the sign of `dataInfo[1]`, and the time abscissa. numpy is already a dependency.
- `scipy.io.loadmat`: "v4 (Level 1.0), v6 and v7 to 7.2 matfiles are supported." scipy is not installed in the mtools venv today.
- DyMat 0.7 (2015, unmaintained): a thin wrapper that calls `scipy.io.loadmat(fileName, chars_as_strings=False)`, so it adds scipy plus a stale package.

### 5. Exit codes, failure output, timeouts

| Situation | C | Cpp |
|---|---|---|
| Success | rc 0, log on **stdout** (`LOG_SUCCESS …`), stderr empty | rc 0, stdout/stderr empty by default |
| Warning-level `assert` (`AssertionLevel.warning`) | rc 0, `LOG_ASSERT \| info` block with file:line on stdout | rc 0, **no output at all** |
| Error `assert` violated | rc **255**, `LOG_ASSERT` blocks on stdout | rc **1**, `ERROR  : solver: DASSL: failed step at t = …: <message>` on stderr. The whole run is **repeated** with the fallback nonlinear solver (kinsol) before failing |
| Integrator / linear-system failure | non-zero: the error catalogue observed 249 (A6, DASSL) and 255 (A5) | rc 1, `… solve failed with idid = …` |
| Chattering | never ends without `-abortSlowSimulation` (error catalogue A8). With it: rc 255 `Chattering detected …` / `Aborting simulation due to chattering…` | DASSL: rc 1 (`idid = 5`). CVODE: runs to the end (46 s, 9 M rows, rc 0) |
| Bad flag value / unknown solver | rc 255 (`-s=nosuch`) | rc 1 |
| Unknown flag | rc 1 | rc 0, warning |
| Missing input file | rc 1 (`can not read file <Model>_init.xml`) or 255 (`_JacA.bin`) | rc 1, `… with error in utility: init xml file has not been read` (after the kinsol retry) |
| Fixed-step solvers | work | rc 139 (SIGSEGV) |
| Wall-clock limit | `-alarm=N` → killed by SIGALRM after N s (shell rc 142, Python `returncode == -14`) | `-A N` has **no effect**. `SimulationMonitor::checkTimeout` only sets a flag that the DASSL/CVODE/IDA loops poll, but runs with `-A 2/3` went on to completion (IDA, 6 s, t = 500 reached) or until an external `timeout 60` |

### 6. Concurrency

One built binary can run concurrently with different settings on **both** targets (*obs.*: 8 C plus 8 Cpp runs in parallel, each
with a different `k`/`kStruct`, all eight analytic results correct, nothing written to either build dir). The conditions:

- each run has its own cwd and an explicit absolute result path (C: `-outputPath` plus default name, or absolute `-r`;
  Cpp: absolute `-F`). Relative names go to cwd, and the Cpp default goes to the shared build dir;
- parameters are passed per run (C: `-override`/`-overrideFile`/`-f` copy; Cpp: a per-run `_init.xml` copy in its own
  `--input-path`). The pydelica approach, `write_params` editing the build dir's `_init.xml` in place, is **not** concurrency-safe.
  For Cpp it is also the only reason parameter changes reach the binary today.

## C-vs-Cpp summary

| Concern | C | Cpp |
|---|---|---|
| Change tunable parameters without rebuild | yes: `-override`, `-overrideFile`, or `-f` | yes, only via an edited `_init.xml` copy |
| Feedback for non-changeable/unknown names | warning on stdout (rc 0) | none |
| Experiment settings without rebuild | yes, dedicated flags (1.26+) or `-f` XML | yes, flags (`-S -E -H -G -T -I -P -B -U`); defaults compiled in |
| Output grid honoured | yes (all solvers) | CVODE/IDA yes, DASSL no |
| Working solvers (this install) | dassl, ida, cvode, gbode, euler, rungekutta, qss | dassl, cvode, ida |
| Result precision | full (mat and csv) | full in mat, 6 digits in csv |
| Parameters in results | mat only | mat only |
| Failure signalling | rc 255/1, log on stdout | rc 1/139, log on stderr, failed runs retried internally |
| Chatter guard / timeout | `-abortSlowSimulation`, `-alarm` | none effective; needs an external timeout |
| Concurrent runs of one build | yes (separate output paths) | yes (separate input copy + absolute `-F`) |

## Recommendation

Facts for the later grilling tickets; the decisions themselves are theirs.

1. **Treat the build directory as immutable, and give every run its own directory.** Run with cwd = run dir and absolute
   paths for all inputs/outputs: C `-inputPath=<build> -outputPath=<run>`; Cpp `--input-path=<run>/input -F <run>/<Model>_res.mat`.
   Never edit files in the build dir. This makes one cached build safe to share across sweep points and parallel runs.
2. **Derive the cache key's "rebuild-only" parameters from the build, not from the model text.** After translation, read
   `isValueChangeable` from `_init.xml`. A requested parameter that is not changeable (or unknown) should be a clear mtools error
   before the run, not left to OMC (a warning with rc 0 on C, silence on Cpp). The key must include the
   source, target, translation flags, and every translation-time modifier.
3. **Pass every experiment setting explicitly as a flag on every run**, never relying on `DefaultExperiment` or the compiled-in
   Cpp defaults. On C always send `-stepSize` with `-startTime`/`-stopTime` (otherwise 500 intervals plus a warning); never use
   `-override` for experiment settings on ≥ 1.26. For tunable parameters on C, prefer `-overrideFile` written by mtools with a
   trailing newline and no `#` comments (no command-line length limit), or `-override` for a few values. On Cpp, write a
   per-run `_init.xml` copy with the changed `start` attributes.
4. **Use `.mat` as the result format on both targets, read with a small in-repo numpy reader.** It has full precision on Cpp,
   includes parameters, and adds no dependency (scipy and DyMat are not needed). Treat any non-zero exit (or negative
   `returncode`) as failure and do not read a partial result file.
5. **Keep C as the primary target; support Cpp with narrower guarantees.** The Cpp runtime has no effective timeout, no
   chatter guard, silent unknown flags, only three working solvers, and DASSL ignores the output grid. mtools needs its own
   `subprocess` timeout for both targets (C's `-alarm` corrupts the `.mat`; an external kill does too). On Cpp, prefer `cvode`/`ida`
   when an equidistant grid matters, or document the DASSL behaviour.
6. **Parse failures per target.** C: stdout `LOG_*` lines (or `-logFormat=xml` for structured parsing), rc 255/1. Cpp: stderr
   `ERROR  :` lines, rc 1/139. The R1/R2 rules in `2026-11-07-omc-error-catalog.md` assume C's stdout format.

## Appendix A: scratch models

```modelica
model Rt
  parameter Real k = 2.0 "tunable";
  parameter Real kEval = 3.0 annotation(Evaluate=true);
  parameter Integer n = 3 "array size";
  parameter Boolean useB = true;
  final parameter Real kFinal = 4.0;
  parameter Real kDep = 2*k "dependent";
  parameter Real kFixedFalse(fixed=false);
  parameter Real kStruct = 1.0;
  Real x(start=1, fixed=true);
  Real y[n];
  Real z;
  Real w;
protected
  Real hidden;
initial equation
  kFixedFalse = 5*k;
equation
  der(x) = -k*x;
  y = fill(kEval*time, n);
  z = if useB then kDep*time else -time;
  w = kFixedFalse + kStruct;
  hidden = kFinal*time;
  annotation(experiment(StartTime=0, StopTime=2, Interval=0.1, Tolerance=1e-6));
end Rt;

model Struct
  parameter Boolean useIf = true "selects an if-equation branch";
  parameter Integer m = 2 "used as a for-loop range";
  parameter Real a = 1.5;
  Real u;
  Real s;
protected
  parameter Real p = 3.0 "protected parameter";
equation
  if useIf then u = a*time; else u = -a*time; end if;
  s = sum(i*p for i in 1:m);
  annotation(experiment(StopTime=1));
end Struct;

model AssertM
  parameter Real lim = 0.5;
  Real x(start=0, fixed=true);
equation
  der(x) = 1;
  assert(x < lim, "x exceeded lim");
  assert(x < 0.2, "soft warning x>0.2", AssertionLevel.warning);
  annotation(experiment(StopTime=1));
end AssertM;

model Chatter
  Real x(start=1, fixed=true);
equation
  der(x) = if x > 0 then -1 else 1;
  annotation(experiment(StopTime=10));
end Chatter;

model Slow
  parameter Real w = 1000;
  Real x(start=0, fixed=true);
equation
  der(x) = sin(w*time);
  annotation(experiment(StopTime=2000, Interval=0.001, Tolerance=1e-10));
end Slow;
```

## Appendix B: numpy-only reader used for verification

```python
import numpy as np

_PREC = {0: "<f8", 1: "<f4", 2: "<i4", 3: "<i2", 4: "<u2", 5: "<u1"}

def read_v4(path):
    """Return {name: 2-D array (mrows x ncols)} for every matrix in a v4 MAT file."""
    out = {}
    with open(path, "rb") as fh:
        while header := fh.read(20):
            mopt, mrows, ncols, _imagf, namlen = np.frombuffer(header, "<i4")
            name = fh.read(namlen)[:-1].decode()
            dtype = np.dtype(_PREC[(mopt // 10) % 10])
            flat = np.frombuffer(fh.read(int(mrows) * int(ncols) * dtype.itemsize), dtype)
            out[name] = flat.reshape((ncols, mrows)).T  # stored column-major
    return out

def _text(mat):
    return ["".join(map(chr, col)).rstrip("\x00 ") for col in mat.T.astype(int)]

def results(path):
    m = read_v4(path)  # Aclass[3] == "binTrans" for OMC (C and Cpp)
    names = _text(m["name"])
    info = m["dataInfo"].T  # per variable: (matrix 0|1|2, signed 1-based row, ...)
    data = {1: m["data_1"], 2: m["data_2"]}
    return {name: np.sign(idx) * (data[2] if which == 0 else data[which])[abs(idx) - 1]
            for name, (which, idx, *_r) in zip(names, info)}
```
