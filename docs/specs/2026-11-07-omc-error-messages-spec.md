# OMC Error Messages Spec

Status: ready-for-agent
Source: Conversation on 2026-11-07 ("pass the information omc provides to the user when using the mtools framework to run a model")

## Problem Statement

When a Modelica model fails to compile, an mtools user does not learn why.
Every run path (`sim_tools.simulate`, the reference-comparison test bases, the
CLI) builds the model through `SessionBuilder`. When OMC rejects the model,
the exception the user sees has no diagnostic content:

| Model defect | Exception raised today | Message today |
|---|---|---|
| Syntax error (missing `;`) | `OMParsingError` | *(empty)* |
| Too few equations | `OMExecutionError` | `Failed to execute compiled code: Error processing file: … # Error encountered! Exiting… # Please check the error message and the flags.` |
| Undeclared variable | `OMExecutionError` | same as above |

OMC does report the cause: `Error: Missing token: SEMICOLON`,
`Error: Too few equations, under-determined system. The model has 1 equation(s)
and 2 variable(s).`, `Error: Variable k not found in scope Undeclared.` These
lines go to OMC's **stderr**. The vendored compile step
(`_compile_without_source_copy`, a copy of pydelica 0.6.3's
`Compiler.compile`) builds its exception messages from **stdout** only, so the
cause is lost. The message `Failed to execute compiled code` also suggests a
runtime failure when nothing has been executed yet.

Users have to rerun `omc` by hand to find out what is wrong with their model.

## Solution

When OMC fails to translate a model, the exception mtools raises carries OMC's
own diagnostics: the source location, severity, and text of each error and
warning, as OMC printed them. The user reads the cause directly in the
traceback or test failure without rerunning OMC.

Failures that already report well stay as they are, and tests pin that
behaviour: C compiler errors from the generated-code build step, and runtime
assertion failures during simulation.

## User Stories

1. As a model developer, I want a syntax error to raise an exception whose
   message contains OMC's parse error with file, line, and column, so that I can
   jump to the broken line.
2. As a model developer, I want an under-determined or over-determined model to
   raise an exception whose message contains OMC's equation/variable count, so
   that I know the model is imbalanced and by how much.
3. As a model developer, I want OMC's follow-up warnings for an imbalanced model
   (e.g. "Variable y does not have any remaining equation to be solved in")
   in the message, so that I know which variable is unconstrained.
4. As a model developer, I want an undeclared identifier to raise an exception
   naming the identifier and the scope, so that I can fix the typo or add the
   declaration.
5. As a model developer, I want the message to name the source file OMC was
   compiling, so that I can tell which model in a sweep or test suite failed.
6. As a model developer, I want the message to say the failure happened while
   OMC translated the model, not "Failed to execute compiled code", so that I do
   not look for a runtime problem.
7. As a model developer, I want OMC's "Automatically loaded package"
   notifications left out of the message, so that the actual error is not
   buried under noise.
8. As an existing mtools user, I want the exception types to stay the same
   (`OMParsingError` for syntax errors, `OMExecutionError` for other OMC
   translation failures), so that my existing `except` clauses keep working.
9. As a model developer, I want a C compiler error in an external function to
   keep surfacing the compiler's message, so that this already-working case does
   not regress.
10. As a model developer, I want a violated `assert` during simulation to keep
    surfacing the assertion text and simulation time, so that this
    already-working case does not regress.
11. As a test author using the reference-comparison bases, I want the same
    diagnostics in a failing pytest run, so that a red test tells me why the
    candidate model did not build.
12. As a model developer whose model builds but produces OMC warnings, I want
    the build to succeed as before, so that diagnostics handling does not turn
    warnings into failures.
13. As a model developer running a Hydra app, I want a failed translation shown
    once, with real line breaks and without OMC's follow-on noise, so that the
    terminal output is short and readable.

## Implementation Decisions

- **Where the fix lives.** The patched compile step in the pydelica patch module
  is the only place that runs OMC's translation. The fix goes there. No change
  to `SessionBuilder`, `SessionDirector`, or `sim_tools`.
- **Diagnostics extraction.** A small pure function turns OMC's stdout and
  stderr into a diagnostics text. It:
  - takes stderr lines, dropping blank lines, lines starting with
    `Notification:`, and OMC's trailing boilerplate (`Execution failed!`,
    `Failed to parse file: …`);
  - keeps everything else in order, including indented continuation lines and
    `Warning:` lines;
  - falls back to stdout, with the same filtering, when stderr has nothing left;
  - drops OMC's follow-on `Error: Failed to load package …` lines when another
    `Error:` line is present, since they only repeat that the load failed.
- **Message shape.** One header line, then the diagnostics verbatim:

  ```
  Modelica translation failed for '<absolute source path>':
  [<file>:3:1-3:1:writable] Error: Missing token: SEMICOLON
  ```

  OMC's exit code is left out of the message (it is always non-zero here) and
  logged at DEBUG with the command line.

- **Exception types are preserved.** Translation failures raise the same
  pydelica exception class as today: `OMParsingError` when OMC reports
  `Failed to parse file`, `OMExecutionError` for other non-zero exits, and
  `OMBuildError` where pydelica's stdout scan raises it. The raised object is a
  private subclass of that class whose `repr()` returns the message, because
  Hydra's instantiate wrapper (`Error in call to target …`) formats the cause
  with `repr()` and would otherwise escape the newlines. `except` clauses on the
  pydelica types keep working. The original pydelica exception is chained as
  `__cause__`. The model build stays in `SessionDirector.__init__`: moving it
  out of `hydra_zen.instantiate` makes Hydra print a full stack trace instead
  of its compact message.
- **Logging.** The diagnostics are not logged at ERROR, because the exception
  already carries them and an ERROR log printed them twice. The compile step
  logs the command, exit code, and message at DEBUG. The vendored compile step
  also swallows the `print(out_string)` inside pydelica's parse helper, which
  dumps OMC's stdout banner (`Error processing file: …`,
  `# Error encountered! Exiting...`) to the terminal.
- **Unchanged paths.** The make/C-compiler step and the simulation step already
  include the relevant output. They are not modified, only covered by
  regression tests.

## Testing Decisions

- **Seam: `SessionBuilder(<path to .mo>)`** against real OMC. It is the single
  entry point every mtools run path uses to build a model. Tests write small
  broken models into `tmp_path`, construct a `SessionBuilder`, and assert on the
  raised exception's type and message. No mocking of OMC.
- Assertions check OMC's stable diagnostic phrases (`Missing token: SEMICOLON`,
  `Too few equations, under-determined system`,
  `Variable k not found in scope`), the header text, and the absence of
  `Notification:` lines. They do not match whole messages, so minor OMC wording
  changes elsewhere do not break them.
- The diagnostics-extraction function also gets fast unit tests over captured
  stdout/stderr strings (filtering, ordering, stdout fallback).
- One end-to-end test runs `sim_tools.simulate_run` on a broken `tmp_path`
  package, through `hydra_zen.instantiate`. It asserts that the diagnostics
  appear once, unescaped, without the `Failed to load package` follow-on, with
  no ERROR log records and no stdout banner.
- Regression tests at the same seam: a broken external C function (make step)
  and a violated `assert` (via `session.simulate`).
- Prior art: `tests/session_tools/test_pydelica_patch.py` (patch unit tests,
  `tmp_path` models, `SessionBuilder(model_path)`);
  `tests/session_tools/test_session_builder.py` (real-OMC integration tests).

## Out of Scope

- Changing pydelica upstream. The vendored compile copy is already the
  project's integration point.
- New mtools-specific exception classes or structured diagnostic objects
  (severity/location fields). Messages are enough for the stated need.
- Rewording runtime simulation failures or changing `assert` severity handling.
- Raising the log level of OMC warnings on successful builds (currently logged
  at ERROR), or suppressing pydelica's stdout prints outside the translation
  error path (e.g. in simulation).
- Hydra's own framing lines (`Error executing job with overrides: …`,
  `Error in call to target …`, `full_key: …`). They belong to the app's Hydra
  runner.

## Further Notes

- Observed with OpenModelica 1.27.2 and pydelica 0.6.3. The `-q` default build
  flag does not affect what OMC writes to stderr; it was ruled out as the cause.
- If pydelica is upgraded past 0.6.x, the version guard in the patch module
  already forces a review of the vendored compile step. This change must be
  carried forward then.
