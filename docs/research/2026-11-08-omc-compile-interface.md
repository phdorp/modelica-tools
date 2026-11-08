# OMC compile interface: how mtools should drive the compiler without pydelica

Date: 2026-11-08
Ticket: #44 (map #43, feature #42). Linux only.
Observed with OpenModelica 1.27.2 (Debian package `omc 1.27.2-1`), GNU make, clang, as user `root` in the
agent container. Libraries: `~/.openmodelica/libraries` holds MSL 3.2.3, 4.0.0 and 4.1.0.

Sources (primary, cited inline as **[S1]**–**[S8]**):

- **[S1]** OMC 1.27.2 scripting API docstrings, installed at `/usr/lib/omc/NFModelicaBuiltin.mo`. This is the
  source the User's Guide "Scripting API" chapter is generated from. Cited by line number.
- **[S2]** OMC `Main.mo` at tag `v1.27.2`:
  [`loadLib` L342–386, `translateFile` L388–502, root check L764–770](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Main/Main.mo#L342-L502).
- **[S3]** OMC `settingsimpl.c` at `v1.27.2`:
  [`SettingsImpl__getModelicaPath` L222–260](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/runtime/settingsimpl.c#L222-L260).
- **[S4]** OMC `CevalScript.mo` at `v1.27.2`:
  [`compileModel` L236–311](https://github.com/OpenModelica/OpenModelica/blob/v1.27.2/OMCompiler/Compiler/Script/CevalScript.mo#L236-L311).
- **[S5]** OMC `Error.mo` at `v1.27.2`: `SIMULATOR_BUILD_ERROR` (id 22, L123) and `ROOT_USER_INTERACTIVE` (id 557, L1032).
- **[S6]** `omc --help` output of 1.27.2. It matches the
  [User's Guide, "Running the compiler from command line"](https://openmodelica.org/doc/OpenModelicaUsersGuide/latest/introduction.html):
  `Usage: omc [Options] (Model.mo | Script.mos) [Libraries | .mo-files]`.
- **[S7]** [User's Guide, OMPython chapter](https://openmodelica.org/doc/OpenModelicaUsersGuide/latest/ompython.html):
  "All of them use ZeroMQ to communicate with the OpenModelica Compiler (OMC)."
- **[S8]** pydelica 0.6.3 `pydelica/options/library.py` and mtools `src/mtools/internal/pydelica_patch.py`.

## Question

What does OpenModelica offer for compiling a model to a simulation binary without pydelica, and which way
should mtools use? The ticket covers five parts:

1. The invocation style: CLI `omc -s`, a generated `.mos` script, or an interactive (ZMQ) session.
2. How libraries are resolved.
3. Multi-file packages compiled in place, including `Resources/Include`.
4. How errors come back.
5. What the C and Cpp `simCodeTarget`s generate, and how they are built.

## Method

1. Read the scripting API docstrings [S1] and the OMC code paths each invocation style goes through [S2]–[S5].
2. Ran each claim against OMC 1.27.2 with throwaway models (Appendix). Each experiment ran in a fresh
   build directory. Timings are wall-clock on a 4-core container, measured once, so they are indicative only.
3. Compared the results with what pydelica 0.6.3 and mtools' patch do today [S8].

## Findings

### 1. Three ways to call OMC

| | CLI: `omc -s Model.mo [libs/files] -i=Class` | Script: `omc [flags] build.mos` | Interactive: `omc --interactive=zmq` |
|---|---|---|---|
| What runs | `translateFile` → `translateModel` with backend [S2 L388–502]. Generates C/C++ sources, `<prefix>.makefile`, `_init.xml`. **Does not run make.** | Any scripting API calls; `buildModel` translates **and** runs `make -j<numProcs>` [S4 L279] | Same API as a script, sent as strings over a socket [S7] |
| Extra inputs | Positional `.mo` files and library **names**, loaded in order, each with version `"default"` [S2 `loadLib`] | `loadFile`, `loadModel(name, {versions}, requireExactVersion=…)`, `setModelicaPath`, `setCommandLineOptions`, `cd` [S1] | same |
| Output file prefix | Class path with `.` → `_` (`MyPkg_Sub_M`) [S2 L445] | Class path **with dots** (`MyPkg.Sub.M`, binary `MyPkg.Sub.M`) unless `fileNamePrefix=` is passed (verified) | same as script |
| Exit code | 1 on parse or translation error; 0 otherwise (verified) | **0 even when `loadFile`/`buildModel` fail**; the script must call `exit(n)` itself (verified: `if r[1] == "" then exit(3); end if;` → exit 3) | n/a (per-call return values) |
| Diagnostics channel | stderr: `[file:l:c-l:c:writable] Error: …`; stdout: `Error processing file:` banner (E3) | Return values echoed on stdout; messages stay in the buffer until `getErrorString()` / `getMessagesStringInternal()` [S1 L2185, L2226] | per call |
| Wall time, trivial MSL model (E1) | omc 1.60 s + `make` 2.38 s (pydelica: no `-j`) = **3.98 s** | **2.11 s** (load + translate + `make -j4`) | lower per build after the first (see below) |
| Root user | works | works | **refused**: `ROOT_USER_INTERACTIVE` for `zmq`/`tcp`/`corba` when `System.userIsRoot()` [S2 L764–770, S5] |
| Python deps | none | none | pyzmq (not in the lockfile), plus port-file handshake and process lifecycle |

Measurements behind the "speed" row:

- **Parallel make matters for C.** C `make -j1` 2.45 s vs `-j4` 1.08 s. The Cpp build is dominated by one
  unity translation unit (`OMCppMCalcHelperMain.cpp`), so `-j` does not help it: `-j1` 5.55 s vs `-j4` 5.79 s.
  `buildModel` passes `-j<numProcs>` (default: all cores, `-n=` overrides) [S4 L279]. pydelica runs
  `make -f` without `-j` (`pydelica_patch.py:586`).
- **A persistent process saves only one library load per build.** `loadModel(Modelica)` alone takes 0.9 s.
  Two fresh `omc -s` translations (MultiBody `DoublePendulum`, `CoupledClutches`) took 2.36 + 1.29 = 3.65 s.
  One `.mos` doing `loadModel` once plus two `translateModel` calls took 2.58 s. An interactive session
  would buy about the same ~1 s per additional model; this is a stand-in, since ZMQ could not run as root
  here and pyzmq is not installed.

How easy each style is to test:

- **CLI and script are both a pure "inputs → argv / script text" step plus one subprocess.** The script text
  can be unit-tested as a string without OMC, as the patch's tests already do for argv.
- **The interactive style adds state across calls.** The error buffer, loaded classes and cwd persist between
  models, so tests need a server fixture and isolation between models.

### 2. Library resolution

OMC's library path:

- **OMC reads `OPENMODELICALIBRARY`, not `MODELICAPATH`.** `getModelicaPath` returns `OPENMODELICALIBRARY` if
  set, otherwise `~/.openmodelica/libraries/` [S3]. Verified: `MODELICAPATH=/x omc` still prints
  `/root/.openmodelica/libraries/`, and `loadModel(MyLib)` fails. With `OPENMODELICALIBRARY=/x:~/.openmodelica/libraries`
  the path is honoured.
- **The docstring says the default also includes `OPENMODELICAHOME/lib/omlibrary/` [S1 L1815], but 1.27.2's
  code only uses `~/.openmodelica/libraries/` [S3].** The `omlibrary` Debian package installs MSL there.
- **`setModelicaPath(…)` sets the same value from inside a script [S1 L1803]** (verified with
  `setModelicaPath("/x:" + getModelicaPath())`).

Version selection:

- **`loadModel(Lib, {"v"})` picks among `Lib v/package.mo` / `Lib v.mo` candidates on the path [S1 L2485].**
  `"default"` means: no version name, then highest main release, and so on.
- **`loadModel(Modelica, {"4.0.0"})` loads MSL 4.1.0** when 4.1.0 is installed, because 4.1.0 declares
  itself compatible without a conversion script. The same upgrade happens for `uses(Modelica(version="4.0.0"))`
  (E1, E4). Only `requireExactVersion=true` [S1] yields 4.0.0 (verified). A version that does not exist fails
  with `Failed to load package MyLib (9.9.9) using MODELICAPATH …`.
- **CLI mode cannot pin a version.** Library names after the model are loaded with `{"default"}` [S2 `loadLib`],
  and the CLI has no `requireExactVersion` flag. The only lever is to restrict `OPENMODELICALIBRARY` to a
  directory that holds only the wanted versions. That is what pydelica does: it symlinks the requested
  `Name Version` entries into a temp dir and sets `OPENMODELICALIBRARY` to it [S8, `pydelica_patch.py:499`].

Auto-loading:

- **Classes are loaded automatically.** `uses` annotations load their libraries ("Automatically loaded package
  MyLib 1.0.0 due to uses annotation"). Unknown top-level names found on the path also load, at default
  version ("… MyLib 2.0.0 due to usage"), even with no library argument. So pydelica's unconditional trailing
  `Modelica` argument (`pydelica_patch.py:477`) is redundant for models that reference MSL.

Problems with pydelica's `{name, version, directory}` spec, all verified:

- **`directory` only works if the same `Name Version` is also on the system path.** `use_library` raises
  `UnknownLibraryError` otherwise (`library.py:60`); `LibrarySetup().use_library("MyLib", "1.0.0", "/x/libs")`
  raises.
- **Only the named library is linked, not its dependencies.** With only `Modelica 4.0.0` on the path, OMC
  prints `Skipped loading package Complex (4.0.0)` and `… ModelicaServices (4.0.0)`. The trivial model still
  builds, but anything that needs `Complex`/`ModelicaServices` would not.
- **Pinning to the exact version works once the dependencies are on the path:** Modelica, Complex and
  ModelicaServices 4.0.0 linked into the restricted directory.

A replacement for the spec, in OMC terms:

- `directory` → prepend the directory to the library path: `setModelicaPath(dir + ":" + getModelicaPath())`,
  or the `OPENMODELICALIBRARY` env var.
- `name` + `version` → `loadModel(name, {version}, requireExactVersion=…)`.
- An unversioned package in place → `loadFile(".../Pkg/package.mo")`.

### 3. Multi-file packages compiled in place, and `Resources/`

Loading packages:

- **`loadFile(".../Pkg/package.mo")` loads the whole directory structure,** sub-packages and `package.order`
  included, "as if loadModel(ClassName) was called". It also appends the directory to the library path for
  that call [S1 L1380].
- **CLI mode handles a `package.mo` the same way:** `omc -s .../MyPkg/package.mo -i=MyPkg.Sub.M` built and ran
  (E5).
- **A leaf file with `within MyPkg.Sub;` cannot be loaded before its parent.** Neither alone, nor as the first
  CLI file with `package.mo` passed after it (pydelica's `extra_models` order: model file first) works. It fails
  with `Failed to insert class M within MyPkg.Sub;` and exit 1. mtools' examples work only because they pass
  `package.mo` files (`examples/tests/reference_models/kinematic_vehicle.py`).

External C resources:

- **The generated makefile references `Resources/` by absolute path, so no copying is needed.** OMC resolves
  the default `IncludeDirectory`/`LibraryDirectory` (`modelica://Pkg/Resources/Include`, `.../Resources/Library`)
  to absolute paths:
  - `CPPFLAGS="-I/abs/src/MyPkg/Resources/Include" …`
  - link lines get `-L…/Resources/Library[/x86_64-linux|/linux64]` and `-Wl,-rpath=…` for each directory,
    plus `-lthrice` for `Library="thrice"`
  - `DIREXTRA=-L"<directory of the file defining the class>"`

  Building from a separate cwd (`build_cli_pkg/`) compiled `#include "twice.c"` and linked `libthrice.a`
  without copying anything. So `_prepare_c_incls`' copy of `Resources/Include/*.c` into
  `<build>/Resources/Include` (`pydelica_patch.py`) is redundant when compiling in place. It existed because
  upstream pydelica compiled a temp copy of the source.

### 4. How errors and warnings come back

| Failure | CLI `omc -s` + `make` (E3) | Script `buildModel` (E3, E3b–e) |
|---|---|---|
| Parse (`Missing token: SEMICOLON`) | exit 1; stderr `Failed to parse file: …!` + `[…:3:1-3:1:writable] Error: Missing token: SEMICOLON` + `Execution failed!`; stdout banner | `loadFile` returns `false`; the message is in the buffer (`kind = syntax`). **Lost if `buildModel` runs before the buffer is read:** the buffer then holds only `Failed to load package Parse (default) …` and `Class Parse not found in scope <top>.` (E3c) |
| Translation (type mismatch) | exit 1; stderr `[…:2:3-2:18:writable] Error: Type mismatch …` | `buildModel` returns `{"", ""}`; buffer has the same text (`kind = translation`, `level = error`, id 135) |
| C build (missing header) | omc exit 0; `make` exit 2, compiler message on make's stderr | `buildModel` returns `{"", ""}`; **one** message, id 22 `Error building simulator. Build log: <entire make log, including every compile command line>` [S4 L306, S5]. The same log is in `<prefix>.log` |
| Warning on success | exit 0; stderr `Warning: The initial conditions are not fully specified …` | result non-empty; buffer has `level = warning` |

- **`getErrorString()` returns the same `[file:l:c-l:c:writable] Error: …` lines as CLI stderr and clears the
  buffer [S1 L2185].** mtools' existing `_omc_diagnostics` filtering applies unchanged.
- **`getMessagesStringInternal()` returns structured records:** file, line/column span, `kind` ∈ {syntax,
  grammar, translation, symbolic, runtime, scripting}, `level` ∈ {internal, notification, warning, error}, and
  `id` [S1 L2216–2234]. They are printed in Modelica record syntax, not JSON, and the 1.27.2 script interpreter
  could not reformat them: `String(m.level)`, `m.info.lineStart` and `msgs[i].message` inside a loop fail with
  `Variable … not found`. Using them means parsing the record text in Python.
- **Errors can be split by stage in a script.** Print markers around `getErrorString()` after each call
  (`print("@@build\n" + getErrorString() + "@@end\n")`), then `exit(n)` with a stage-specific code. `-q` does
  not suppress the echo of statement results on stdout, so markers are needed (E3e).
- **`--showErrorMessages` (CLI) also prints each error as a 4-tuple:** `{"[…] Error: …", "TRANSLATION", "Error", "135"}`
  on stderr, ahead of the plain line (E3c).

### 5. C vs Cpp `simCodeTarget`

| | C (default) | Cpp (`--simCodeTarget=Cpp`) |
|---|---|---|
| Generated by OMC | `M.c`, `M_01exo.c`…`M_18spd.c`, headers, `M.makefile`, `M_init.xml`, `M_info.json`, `M_JacA.bin` | `OMCppM*.cpp/.h`, `M.makefile`, `M_init.xml`, **`M.sh`** |
| Makefile | self-contained, `CC=clang`, `-Os`, links `-lSimulationRuntimeC` | `include $(OMHOME)/include/omc/cpp/ModelicaConfig_gcc.inc` …, builds `OMCppM.so` (model) + `M` (generic main) |
| `make` output | single executable `M` | `M` + `OMCppM.so`; make also `chmod +x M.sh` |
| Build time (E6) | 2.45 s (`-j1`) / 1.08 s (`-j4`) | 5.55 s / 5.79 s |
| `_init.xml` `DefaultExperiment` | present, from the `experiment` annotation (also via `buildModel`) | **absent** |
| Experiment defaults | read from `_init.xml` at runtime | **only in `M.sh`**: `exec ./M -S 0.0 -E 2.0 -H 0.01 -G 200 -P mat -T 1e-6 -I dassl -R <cpp runtime dir> -M <build dir> -r <build dir>/M_res.mat $*` |
| Running the binary bare | uses XML defaults | uses the binary's own defaults: `--solver euler`, `--stop-time 1` (`./M --help`). Exits 0 with the wrong experiment |
| Runtime flags | `-override`, `-r`, `-outputPath`, `-abortSlowSimulation`, `-lv`, … | Boost options: `-S/-E/-H/-G/-T/-I/-P/-F/-U/-B/-R/-M`, `-V` log settings |

- **The build step is the same for both targets:** `make -j<n> -f <prefix>.makefile` with cwd = build dir
  [S4 L279]. `buildModel` handles both (E6, E6d).
- **The makefile is `<prefix>.makefile` for both; there is no `OMCpp<prefix>.makefile`.**
- **OMC flags passed before the script apply to `buildModel` inside it** (`omc --simCodeTarget=Cpp -n=2 b.mos`
  built the Cpp target), as does `setCommandLineOptions("--simCodeTarget=Cpp")` [S1 L1993].

## Recommendation

**Generate a `.mos` script per build and run it as one short-lived `omc` subprocess**, with cwd set to a fresh
build directory. OMC flags (`--simCodeTarget`, `-d=…`, `-n=`) go on the `omc` command line. The script:

1. If custom library directories are given: `setModelicaPath("<dirs>:" + getModelicaPath())`, then stage marker
   + `getErrorString()`.
2. Per library spec: `loadModel(Name, {"version"}, requireExactVersion=<exact>)`. Check the result, print the
   stage marker + `getErrorString()`, and `exit(<load code>)` on failure.
3. `loadFile("<abs path>")` for the model source and each extra file, in place. For a package, pass its
   `package.mo`. Check, print and exit as in step 2.
4. `r := buildModel(<Class>, fileNamePrefix="<Class with . → _>")`. Print the stage marker + `getErrorString()`.
   If `r[1] == ""`, call `exit(<build code>)`.

Why this style:

- It is the only style that can **pin a library version exactly** (`requireExactVersion`) without building a
  symlink farm.
- It **reads the error buffer after every step** (E3c shows the parse error is lost otherwise).
- It **runs `make -jN` inside OMC**, which roughly halves C build time versus pydelica's serial `make`.
- It needs **no new Python dependency**, **works as root**, and leaves no state between builds.
- Diagnostics keep the `[file:…] Error: …` text that mtools' existing filters and error-message spec are built
  around.
- Generating the script is a pure function, so unit tests need no OMC.

Python-side consequences:

- **Translation and C build failures arrive through the same channel.** mtools should tell them apart by
  stage. For C build failures (id 22), keep only the compiler/`make: ***` lines of the embedded build log
  (or read `<prefix>.log`), so the spec's "cause once, no noise" format holds.
- **For Cpp, read the experiment defaults from `M.sh` and pass them explicitly.** OMC writes them only into
  `M.sh`, so the mtools backend should do the same as today's patch.

Alternatives considered:

- **CLI `omc -s` + separate `make`** (what pydelica does). Its diagnostics and exit codes are slightly simpler
  (exit 1 on parse/translation errors, stderr carries the text). But it cannot pin a library version, needs a
  restricted `OPENMODELICALIBRARY` directory for any library spec, depends on file order for `within`, and
  leaves `-j` to mtools. It is a reasonable fallback if script generation proves awkward; the ~1 s difference
  in E1 comes from `-j` and can be closed by passing `-jN` to make.
- **Interactive ZMQ session.** It would save about one MSL load (~0.9 s) per additional model in the same
  process. Against that: OMC refuses to start it as root (agent and plain Docker containers), it adds pyzmq
  and process management, it carries state across builds, and it is the hardest to test. Not worth it now;
  a backend interface that takes "build this model" requests would let it be added later without API changes.

## Notes

- **Environment caveats.** The User's Guide pages fetched are the `latest` build (v1.28.0-dev); the docstrings
  [S1] and code [S2]–[S5] are 1.27.2. The devcontainer (`mcr.microsoft.com/devcontainers/base`) and CI
  (`ubuntu-latest` runner) normally run as a non-root user; this agent ran as root.
- **Flag spelling.** pydelica passes `+i=Class` (legacy `+` flag syntax); `-i=Class` is the documented form
  [S6]. Both worked.
- **Not covered:** Windows (`Compile.bat` path in [S4]), FMU export, `buildModel`'s `simflags`/`cflags`
  arguments, and running the simulation binaries (ticket #45).

## Appendix: experiment inputs

```modelica
// M.mo: trivial MSL model (E1, E6)
model M
  parameter Real k = 2;
  Real x(start = 1, fixed = true);
  Modelica.Blocks.Sources.Constant c(k = 1);
equation
  der(x) = -k*x + c.y;
  annotation(experiment(StopTime = 2, Interval = 0.01), uses(Modelica(version = "4.0.0")));
end M;

// E3 failure models
model Parse  Real x  equation x = 1; end Parse;            // missing ';' after "Real x"
model Trans  Integer t = 1.5; end Trans;
model CBuild
  function f input Real x; output Real y;
  external "C" y = missingF(x) annotation(Include="#include \"no_such_header.h\"");
  end f;
  Real v = f(time);
end CBuild;
model Warn  Real x; equation der(x) = -x; end Warn;

// E5 package layout (each class in its own file, with the matching within clause)
//   src/MyPkg/package.mo                     within; package MyPkg end MyPkg;
//   src/MyPkg/package.order                  Ext, Sub
//   src/MyPkg/Ext.mo                         function Ext ... external "C" y = twice(x)
//                                              annotation(Include = "#include \"twice.c\"");
//   src/MyPkg/Sub/package.mo                 within MyPkg; package Sub end Sub;
//   src/MyPkg/Sub/M.mo                       within MyPkg.Sub; model M Real y = MyPkg.Ext(time) + MyPkg.Sub.Lib(time); end M;
//   src/MyPkg/Sub/Lib.mo                     function Lib ... external "C" y = thrice(x) annotation(Library = "thrice");
//   src/MyPkg/Resources/Include/twice.c      double twice(double x) { return 2*x; }
//   src/MyPkg/Resources/Library/libthrice.a  (static lib with thrice)

// E4 versioned test library: "libs/MyLib 1.0.0/package.mo" and "libs/MyLib 2.0.0/package.mo",
// each `package MyLib ... annotation(version = "<v>"); end MyLib;`
```

```
// build.mos shape used in E3e (stage markers + exit codes)
ok := loadFile("/abs/Trans.mo");
print("@@load\n" + getErrorString() + "@@end\n");
r := buildModel(Trans);
print("@@build\n" + getErrorString() + "@@end\n");
if r[1] == "" then exit(3); end if;
```
