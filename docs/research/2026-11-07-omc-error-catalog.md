# OMC error catalogue: User's Guide error classes through mtools

Date: 2026-11-07
Source: [OpenModelica User's Guide v1.24](https://openmodelica.org/doc/OpenModelicaUsersGuide/OpenModelicaUsersGuide-1.24.pdf)
(build `v1.24.5-3-gf4cb360bf94`). Page numbers below are the guide's printed page numbers.
Observed with OpenModelica 1.27.2, pydelica 0.6.3, mtools branch `test/omc-error-catalog`.

## Question

Which error classes does the User's Guide document? How does mtools present each one to the user,
judged against the format agreed in `docs/specs/2026-11-07-omc-error-messages-spec.md`?

## Method

1. Extracted the guide text and located every section that shows or describes an error or failure.
2. For each class, wrote a minimal model and confirmed the error with raw OMC
   (`omc -s Model.mo Modelica -q`, then `make` and the binary for runtime errors).
3. Ran each model through `SessionBuilder(path)` and, if it built, `builder.session.simulate(model_name=...)`.
   For each one, recorded the exception type, `str(exc)`, `repr(exc) == str(exc)`, captured stdout/stderr, and log records at WARNING or above.
   `sim_tools.simulate_run` calls `session.simulate` outside `hydra_zen.instantiate`
   (`src/mtools/internal/sim_tools.py:109`), so runtime errors reach a Hydra app unwrapped and look the same.
4. Pinned the well-formatted cases in `tests/session_tools/test_omc_error_catalog.py`.

## Where the guide documents errors

| Guide section | Page | What it shows |
|---|---|---|
| 1.2.2 Using the Interactive Mode | 5–6 | `Type mismatch in binding`, `Argument 'a' of der is not differentiable` |
| 1.4 Running the compiler from command line | 25–26 | `Failed to load package`, `Simulation Failed. Model: … does not exist!` |
| 3.2.5 Messages Browser | 35 | Error kinds: Syntax, Grammar, Translation, Symbolic, Simulation, Scripting |
| 3.15.4 Simulation Flags | 47 | Log streams, incl. `LOG_DIVISION`, `LOG_ASSERT`, `LOG_NLS`, `LOG_LS` |
| 6.1 Integration Methods | 87–89 | DASSL/IDA solvers and their failure flags (`idaMaxErrorTestFails`, …) |
| 6.3 Initialization | 89–95 | Initialization problem, start values, homotopy fallback |
| 6.4 Algebraic Solvers | 95–96 | Linear/nonlinear solvers and fallbacks, `-lv=LOG_LS/LOG_NLS` |
| 7.1.3 Simulate and Start the Debugger | 97 | Chattering example (`Debugging.Chattering.ChatteringEvents1`) |
| 9.2–9.8 Porting libraries | 107–112 | Missing `each`, conditional-component access, partial-package lookup, `=` in algorithms, public function variables, expression subscripting, incomplete initial conditions |
| 18.1 PDEModelica1 language elements | 293 | `Missing token: SEMICOLON` |
| 23.2 Calling external Python code | 329–333 | `Error building simulator. Build log: …` (C compile failure) |
| 29.2 Debug flags (`warnMinMax`) | 461 | min/max violations are warnings by default |
| 30.1 C Runtime Simulation Flags | 463 | `-abortSlowSimulation` ("Aborts if the simulation chatters"), `-alarm` |

## Findings

Verdicts: **OK**: meets the spec format (cause present, shown once, real line breaks, no notification
noise, correct file and line). **Acceptable**: cause present and readable, with minor noise. **Defect**:
cause missing, duplicated, garbled, or misleading. **Not reproducible**: OMC 1.27.2 accepts the model.

### Translation errors (`SessionBuilder`)

All raise the readable private subclass of the pydelica type. `repr == str`, there are no literal `\n` escapes, and the
message starts with `Modelica translation failed for '<path>':`. Nothing is printed to stdout or logged
at WARNING or above.

| Error class | Guide | Model | Observed (after the header line) | Verdict | Suggested fix |
|---|---|---|---|---|---|
| Type mismatch in binding | 1.2.2, p. 5 | `TypeMismatch` (pinned) | `OMExecutionError`: `[…/TypeMismatch.mo:2:3-2:18:writable] Error: Type mismatch in binding t = 1.5, expected subtype of Integer, got type Real.` | OK | — |
| `der` of a non-Real | 1.2.2, p. 6 | `DerInteger` (pinned) | `OMExecutionError`: `[…:5:3-5:13:writable] Error: Argument 'a' of der is not differentiable.` | OK | — |
| Missing `;` (syntax) | 18.1, p. 293 | already covered: `test_syntax_error_reports_missing_token` | `OMParsingError`: `[…:3:1-3:1:writable] Error: Missing token: SEMICOLON` | OK | — |
| Missing `each` on array modifier | 9.2, p. 107 | `ArrayModifierWithoutEach` (pinned) | `OMExecutionError`, two lines: `[…:7:11-7:16:writable] Notification: From here:` then `[…:3:5-3:21:writable] Error: Non-array modification 'r' for array component 'p', possibly due to missing 'each'.` | OK | Keep the `From here:` line. The filter only drops lines that *start* with `Notification:`, so this location-prefixed context line survives. It is the only pointer to the offending modifier (line 7); the error itself points at the declaration (line 3). The pinned test asserts it stays. |
| Conditional component used outside `connect` | 9.3, p. 108 | Appendix A1 | Builds and simulates; no error. | Not reproducible | — (OMC 1.27.2 accepts the pattern the guide calls illegal) |
| Lookup in a partial package | 9.4, p. 109 | `PartialPackageLookup` (pinned) | `OMExecutionError`: `[…:11:3-11:21:writable] Error: P is partial, name lookup is not allowed in partial classes.` | OK | — |
| `=` instead of `:=` in an algorithm | 9.5, p. 110 | `AlgorithmEquality` (pinned) | `OMParsingError`: `[…:7:7-7:8:writable] Error: Parse error: Algorithms can not contain equations ('='), use assignments (':=') instead` | OK | — |
| Public non-input/output function variable | 9.6, p. 110 | `PublicFunctionVariable` (pinned) | `OMExecutionError`: `[…:5:5-5:11:writable] Error: Invalid public variable z, function variables that are not input/output must be protected.` | OK | — |
| Expression subscripting `(x.*y)[2]` | 9.7, p. 111 | Appendix A2 | Builds and simulates. | Not reproducible | — (now supported, as the guide anticipates) |
| Too few / too many equations | 3.2.5 "Symbolic", p. 35 | already covered | `Too few equations, under-determined system…` plus the `Variable y does not have any remaining equation` warning | OK | — |
| Structurally singular system | 3.2.5 "Symbolic", p. 35 | `StructurallySingular` (pinned) | `OMExecutionError`: `Error: Internal error IndexReduction.pantelidesIndexReduction failed! Found empty set of continuous equations. Use -d=bltdump to get more information.` / `Error: Internal error Transformation Module PFPlusExt index Reduction Method Pantelides failed!` | OK (format) | The format is right, but OMC's wording is cryptic and gives no file or line. mtools cannot improve this without inventing diagnostics, so no change is proposed. |
| Undeclared variable, missing library class | 1.4, p. 25 | already covered | `Variable k not found in scope …`, class name in message | OK | — |

### Build warnings on a successful translation

| Error class | Guide | Model | Observed | Verdict | Suggested fix |
|---|---|---|---|---|---|
| "The initial conditions are not fully specified" | 9.8, p. 112 (also 6.3.1) | `test_build_warning_is_logged_without_notifications` | **Before:** the warning was silently lost. pydelica logged OMC's whole stderr as one ERROR record. mtools always loads `Modelica`, so that record always contains `Notification: Automatically loaded package`, and `_OmcPassthroughFilter` (`session_tools.py`) dropped the whole record, warning included. This affected **every** OMC warning on a successful build. **After:** one ERROR record with just `Warning: The initial conditions are not fully specified. For more information set -d=initialization. …` | Defect, **fixed** (`d3e4a66`) | The compile step now logs `_omc_diagnostics("", stderr)` instead of raw stderr. The log level stays ERROR, because the spec puts changing it out of scope; WARNING would be the natural level, and that is a separate decision. |

### C compiler / make step

| Error class | Guide | Model | Observed | Verdict | Suggested fix |
|---|---|---|---|---|---|
| C compile error in external code (missing header) | 23.2, p. 329–330 | Appendix A3 (the syntax-error variant is already pinned: `test_c_compiler_error_in_external_function_is_reported`) | Plain `pydelica.exception.OMBuildError` (not the readable subclass), `Model build failed with exit code 2:\n\tIn file included from MissingHeader_functions.c:7:\n./MissingHeader_includes.h:7:10: fatal error: 'no_such_header.h' file not found …\nmake: *** […] Error 1`. The same text is **also** logged at ERROR by `PyDelica.Compiler`. | Defect (shown twice; no source-file header; `repr()` escapes newlines under Hydra; stray leading tab; make noise) | Route the make step through the same handler as translation: readable subclass, header `Modelica build failed for '<source>':`, compiler output once, log only at DEBUG. The code is in the vendored compile step, but the spec explicitly left the make step unmodified, so this needs **your decision**. It would also change the pinned exact-type assertion `exc.type is OMBuildError` to `issubclass`. |

### Runtime / simulation errors (`session.simulate`)

Common to every runtime case: pydelica's `parse_error_string_simulate` unconditionally `print()`s
the whole simulation log to stdout. Every runtime failure is therefore shown **twice**: once on
stdout, once in the exception. Successful runs also print their `LOG_SUCCESS` lines. None of these
exceptions use the readable-`repr` subclass. mtools does not reformat runtime errors (spec: out of scope).

| Error class | Guide | Model | Observed | Verdict | Suggested fix |
|---|---|---|---|---|---|
| Violated `assert` | 16.1, p. 254; 3.15.4 `LOG_ASSERT` | already covered | `OMAssertionError: Simulation run failed:\n<raw log>` with message and time | Acceptable | See R1 |
| Division by zero at initialization | 3.15.4 `LOG_DIVISION`, p. 47 | `DivisionByZero` (pinned) | builtin `ZeroDivisionError: division by zero at time 0, (a=1) / (b=0), where divisor b expression is: p` | OK (concise, names the divisor) | Lost context: "at initialization" and the model file are not mentioned. Optional, see R1. |
| Division by zero during simulation | 3.15.4 `LOG_DIVISION`, p. 47 | `DivisionByZeroDuringSimulation` (pinned) | `ZeroDivisionError: division by zero at time 0.5000000000500024, (a=1) / (b=0), where divisor b expression is: if d > 0.0 then d else 0.0` | OK | — |
| Nonlinear system fails at initialization | 6.3, p. 89; 6.4, p. 95 | `InitializationNonlinearFailure` (pinned) | `OMAssertionError: Simulation run failed:` / `LOG_ASSERT \| debug \| Solving non-linear system 2 failed at time=0.` / `\| \| \| For more information please use -lv LOG_NLS.` / `LOG_ASSERT \| info \| simulation terminated by an assertion at initialization` | Acceptable (cause present; column-padding noise) | R1 |
| Nonlinear system fails during simulation | 6.4, p. 95 | Appendix A4 | **No exception.** Log: `Solving non-linear system 8 failed at time=0.168.` … `Integrator attempt to handle a problem with a called assert.` … `The simulation finished successfully.` (exit code 0) | Defect (silent; results after t≈0.168 are not a solution) | OMC reports success itself, so the only signal is the debug-level `LOG_ASSERT`. R2. |
| Singular linear system | 6.4, p. 95 | Appendix A5 | `OMExecutionError: [255] Simulation failed with: LOG_SUCCESS \| info \| The initialization finished successfully …` (first log line glued onto the header) … `Error solving linear system of equations (no. 12) at time 0.500000.` … `Solving linear system 12 failed at time=0.500000000150874.` | Defect (garbled header; cause buried under the log; misleading first line "finished successfully") | R1 |
| Integrator (DASSL) failure | 6.1, p. 87–89 | Appendix A6 | `OMExecutionError: [249] Simulation failed with: LOG_SUCCESS \| info \| The initialization …` / `DASKR--  AT T (=R1) AND STEPSIZE H (=R2) THE ␣␣␣…` (trailing blanks) / `DDASSL had repeated error test failures …` / `model terminate \| Integrator failed. \| Simulation terminated at time 0.00049999` | Defect (same glued header; Fortran banner noise; key line `Integrator failed` is last) | R1 |
| Variable outside `min`/`max` | 29.2 `warnMinMax`, p. 461 | Appendix A7 | **No exception.** `LOG_ASSERT \| info \| [….mo:2:3-2:43:writable]` / `The following assertion has been violated at time 0.502000` / `((x <= 1.0)) --> "Variable violating max constraint: x <= 1.0, has value: 1.004"`, then `The simulation finished successfully.` | By design (OMC default: warning) | The message is well formed but visible only in the stdout dump. R2. |
| Chattering | 7.1.3, p. 97; 30.1 `-abortSlowSimulation`, p. 463 | Appendix A8 | Build OK. `simulate` **never returns** (killed after 60 s and 120 s). The OMC log says `Chattering detected around time 1.0000000001..1.0000000199 (100 state events in a row …)` at info level. pydelica's `subprocess.run` has no timeout. | Defect (hang; nothing shown until the process exits) | R3 |
| Model does not exist | 1.4, p. 26 | `simulate(model_name="NoSuchModel")` on a built session | `pydelica.exception.BinaryNotFoundError: Failed to retrieve binary for model 'NoSuchModel'` (cause: `KeyError`) | Acceptable | Optional: list the built model names. |

### Suggested follow-ups for runtime errors (need your decision; not local to the diagnostics helpers)

- **R1: readable runtime failures.** Wrap the patched `Session.simulate` (`_simulate_with_cpp_options`
  already wraps it) the way the compile step was wrapped. Swallow pydelica's `print`. Re-raise the
  same pydelica types (and `ZeroDivisionError`) as readable subclasses, with a header such as
  `Simulation of '<model>' failed:` on its own line. Filter the log to `LOG_ASSERT`, `warning`/`error`
  lines and their `|` continuations. Drop `LOG_SUCCESS` and the `DASKR--` banner. This mirrors the
  translation design but changes `str(exc)` of runtime exceptions users may match on.
- **R2: surface non-fatal runtime asserts.** Log `LOG_ASSERT` lines from a successful run at WARNING
  (e.g. failed nonlinear systems, min/max violations) instead of only printing the raw log.
  Separately, consider whether a failed nonlinear system during simulation should fail the run.
- **R3: don't hang on chattering.** Pass `-abortSlowSimulation` by default and/or add a configurable
  simulation timeout. Both change runtime behaviour, so they are your call.

## Appendix: models that are not pinned

```modelica
// A1 — §9.3, accepted by OMC 1.27.2
model ConditionalComponentAccess
  connector RealInput = input Real;
  parameter Boolean activateIn1 = true;
  RealInput u1_in if activateIn1;
  Real u1;
equation
  if activateIn1 then u1 = u1_in; end if;
end ConditionalComponentAccess;

// A2 — §9.7, accepted by OMC 1.27.2
model ExpressionSubscript
  Real x[3] = {1, 2, 3}*time;
  Real y[3] = {4, 5, 6};
  Real z;
equation
  z = (x .* y)[2];
end ExpressionSubscript;

// A3 — §23.2, C build failure
model MissingHeader
  function f
    input Real x;
    output Real y;
  external "C" y = missingF(x) annotation(Include="#include \"no_such_header.h\"");
  end f;
  Real v = f(time);
end MissingHeader;

// A4 — §6.4, x*exp(x) >= -1/e, so no solution once -0.2 - time < -0.368
model NonlinearSystemFailure
  Real x(start = -0.5);
equation
  x*exp(x) = -0.2 - time;
end NonlinearSystemFailure;

// A5 — §6.4, matrix [[1, a], [a, 1]] is singular for a = 1
model LinearSystemSingular
  Real a = if time > 0.5 then 1 else 0.5;
  Real x, y;
equation
  x + a*y = 1;
  a*x + y = 0;
end LinearSystemSingular;

// A6 — §6.1, finite escape time at t = 5e-4
model IntegratorFailure
  Real x(start = 1, fixed = true);
equation
  der(x) = x^3*1e3;
end IntegratorFailure;

// A7 — §29.2 warnMinMax
model MinMaxViolation
  Real x(start = 0, fixed = true, max = 1);
equation
  der(x) = 2;
end MinMaxViolation;

// A8 — §7.1.3 / §30.1, sliding mode at x = 0 from t = 1
model Chattering
  Real x(start = 1, fixed = true);
equation
  der(x) = if x > 0 then -1 else 1;
  annotation(experiment(StopTime = 2));
end Chattering;
```

## Notes

- The guide documents 1.24; observations are on 1.27.2. Message texts matched the guide where it
  quotes them (type mismatch, `der`, missing semicolon). Two of the guide's porting errors (§9.3, §9.7) no longer
  reproduce.
- Not covered: OMEdit/OMNotebook-only and scripting-API errors (`getErrorString`, package manager
  download failures, §2), which mtools never triggers, and FMI/OMSimulator errors.
