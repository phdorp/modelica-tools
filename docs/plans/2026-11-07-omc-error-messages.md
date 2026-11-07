# OMC Error Messages Implementation Plan

**Goal:** When OMC fails to translate a model, the exception mtools raises carries OMC's own diagnostics (location, severity, text).

**Architecture:** OMC writes diagnostics to stderr, but the vendored pydelica compile step (`_compile_without_source_copy`) builds exception messages from stdout only. A pure helper extracts and filters OMC's stderr (falling back to stdout). The compile step re-raises pydelica's exception with a message built from it, keeping the original exception type. The make and simulate steps already report well and only get regression tests.

**Tech Stack:** Python 3.11, pydelica 0.6.3 (vendored compile step), OpenModelica 1.27.2, pytest.

**Spec:** `docs/specs/2026-11-07-omc-error-messages-spec.md`

## Global Constraints

- Exception types stay unchanged: `OMParsingError` for syntax errors, `OMExecutionError` for other OMC translation failures, `OMBuildError` where pydelica's stdout scan or a non-zero exit raises it.
- Message header, verbatim: `OMC failed to translate '<absolute source path>' (exit code <n>):`, then the diagnostics one per line.
- Filtered out of diagnostics: blank lines, lines starting with `Notification:`, `Execution failed!`, lines starting with `Failed to parse file`.
- The original pydelica exception is chained as `__cause__`.
- No changes to `SessionBuilder`, `SessionDirector`, `sim_tools`, or pydelica upstream.
- Branch: `fix/omc-error-messages` (from `main`). Commits follow conventional-commit style.
- Checks: `uv run pytest tests`, `uv run mypy src tests`, `uv run isort --check-only src tests examples`.

## Review Focus

1. Over-determined model (two equations for one variable): message contains `Too many equations, over-determined system`. Test in Task 2.
2. Model that builds with OMC warnings but no errors: `SessionBuilder` still succeeds. Test in Task 2.
3. Reference to a missing library class (`Modelica.Blocks.Sources.NoSuchBlock`): message names the missing class. Test in Task 2.
4. OMC failure with empty stderr but diagnostics on stdout: the stdout fallback produces them. Test in Task 1.
5. Multi-line diagnostics with indented continuation lines: kept in order and unindented text not merged. Test in Task 1.

## File Structure

- `src/mtools/internal/pydelica_patch.py`: add `_omc_diagnostics` and `_translation_error_message`. Change the OMC-run error handling in `_compile_without_source_copy` to use them.
- `tests/session_tools/test_omc_diagnostics.py` (new): unit tests for the helpers, plus real-OMC tests through `SessionBuilder` with broken models written to `tmp_path`.

## Tasks

### Task 1: Diagnostics extraction helpers

**Files:**
- Modify: `src/mtools/internal/pydelica_patch.py` (new module-level functions next to `_prepare_c_incls`)
- Test: `tests/session_tools/test_omc_diagnostics.py`

**Interfaces:**
- Produces:
  - `_omc_diagnostics(stdout: str, stderr: str) -> str`: filtered stderr lines joined by `\n`; if none remain, filtered stdout lines; `""` if both are empty after filtering.
  - `_translation_error_message(source_file: pathlib.Path, returncode: int, stdout: str, stderr: str) -> str`: header line + `\n` + `_omc_diagnostics(...)`.

- [ ] **Step 1: Write the failing tests**

```python
IMBALANCED_STDERR = (
    "Notification: Automatically loaded package Complex 4.1.0 due to uses annotation from Modelica.\n"
    "Error: Too few equations, under-determined system. The model has 1 equation(s) and 2 variable(s).\n"
    "[/m/Imbalanced.mo:3:3-3:9:writable] Warning: Variable y does not have any remaining equation to be solved in.\n"
    "  The original equations were:\n"
    "\n"
    "Execution failed!\n"
)

def test_omc_diagnostics_keeps_errors_warnings_and_continuations_in_order():
    assert _omc_diagnostics("", IMBALANCED_STDERR).splitlines() == [
        "Error: Too few equations, under-determined system. The model has 1 equation(s) and 2 variable(s).",
        "[/m/Imbalanced.mo:3:3-3:9:writable] Warning: Variable y does not have any remaining equation to be solved in.",
        "  The original equations were:",
    ]

def test_omc_diagnostics_drops_parse_boilerplate():
    stderr = "Failed to parse file: /m/S.mo!\n\n[/m/S.mo:3:1-3:1:writable] Error: Missing token: SEMICOLON\n\nExecution failed!\n"
    assert _omc_diagnostics("", stderr) == "[/m/S.mo:3:1-3:1:writable] Error: Missing token: SEMICOLON"

def test_omc_diagnostics_falls_back_to_stdout():
    assert _omc_diagnostics("Error: boom\n", "Notification: x\n") == "Error: boom"

def test_omc_diagnostics_empty():
    assert _omc_diagnostics("", "") == ""

def test_translation_error_message_header(tmp_path):
    message = _translation_error_message(tmp_path / "M.mo", 1, "", "Error: boom\n")
    assert message == f"OMC failed to translate '{tmp_path / 'M.mo'}' (exit code 1):\nError: boom"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/session_tools/test_omc_diagnostics.py -v`
Expected: collection error, `ImportError: cannot import name '_omc_diagnostics'`.

- [ ] **Step 3: Implement both functions in `src/mtools/internal/pydelica_patch.py`**

Apply the filtering exactly as listed in Global Constraints. `rstrip()` each line before filtering. Keep leading indentation.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/session_tools/test_omc_diagnostics.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**: `feat: extract OMC diagnostics from compiler output`

### Task 2: Raise translation failures with OMC diagnostics

**Files:**
- Modify: `src/mtools/internal/pydelica_patch.py`, the `try/except` around `pde.parse_error_string_compiler(_gen.stdout, _gen.stderr)` and the following `if _gen.returncode != 0` block in `_compile_without_source_copy`
- Test: `tests/session_tools/test_omc_diagnostics.py`

**Interfaces:**
- Consumes: `_translation_error_message(source_file, returncode, stdout, stderr)` from Task 1.
- Produces: no new names. Behaviour only.

- [ ] **Step 1: Write the failing tests** (real OMC; helper `_build(tmp_path, name, source) -> pytest.ExceptionInfo` writes `tmp_path / f"{name}.mo"` and runs `session_tools.SessionBuilder(path)` under `pytest.raises(Exception)`)

```python
def test_syntax_error_reports_missing_token(tmp_path):
    exc = _build(tmp_path, "Syntax", "model Syntax\n  Real x(start=1)\nequation\n  der(x) = -x;\nend Syntax;\n")
    assert exc.type is pydelica.exception.OMParsingError
    assert f"OMC failed to translate '{tmp_path / 'Syntax.mo'}' (exit code 1):" in str(exc.value)
    assert "Missing token: SEMICOLON" in str(exc.value)
    assert ":3:1-3:1:" in str(exc.value)

def test_under_determined_model_reports_counts_and_free_variable(tmp_path):
    exc = _build(tmp_path, "Imbalanced", "model Imbalanced\n  Real x(start=1);\n  Real y;\nequation\n  der(x) = -x;\nend Imbalanced;\n")
    assert exc.type is pydelica.exception.OMExecutionError
    msg = str(exc.value)
    assert "Too few equations, under-determined system. The model has 1 equation(s) and 2 variable(s)." in msg
    assert "Variable y does not have any remaining equation" in msg
    assert "Notification:" not in msg
    assert "Failed to execute compiled code" not in msg
    assert isinstance(exc.value.__cause__, pydelica.exception.OMExecutionError)

def test_over_determined_model_reports_too_many_equations(tmp_path):
    exc = _build(tmp_path, "Over", "model Over\n  Real x(start=1);\nequation\n  der(x) = -x;\n  x = 1;\nend Over;\n")
    assert "Too many equations, over-determined system" in str(exc.value)

def test_undeclared_variable_reports_name_and_scope(tmp_path):
    exc = _build(tmp_path, "Undeclared", "model Undeclared\n  Real x(start=1);\nequation\n  der(x) = -k*x;\nend Undeclared;\n")
    assert "Variable k not found in scope Undeclared" in str(exc.value)

def test_missing_library_class_is_named(tmp_path):
    exc = _build(tmp_path, "MissingLib", "model MissingLib\n  Modelica.Blocks.Sources.NoSuchBlock b;\nend MissingLib;\n")
    assert "NoSuchBlock" in str(exc.value)

def test_model_with_warnings_still_builds(tmp_path):
    path = tmp_path / "Warn.mo"
    path.write_text("model Warn\n  parameter Real p(start=1);\n  Real x(start=1);\nequation\n  der(x) = -p*x;\nend Warn;\n")
    session_tools.SessionBuilder(path)  # no exception
```

Every fixture above was checked against OMC 1.27.2. Its stderr contains each asserted phrase, and `Warn.mo` exits 0 with two `Warning:` lines.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/session_tools/test_omc_diagnostics.py -v`
Expected: `test_syntax_error…`, `test_under_determined…`, `test_over_determined…`, `test_undeclared…`, `test_missing_library…` FAIL (the phrase is missing from the message). `test_model_with_warnings_still_builds` passes.

- [ ] **Step 3: Implement in `_compile_without_source_copy`**

In the `except pde.OMParsingError`, `except pde.OMExecutionError`, and non-lexer `except pde.OMBuildError` branches: build `message = _translation_error_message(modelica_source_file, _gen.returncode, _gen.stdout, _gen.stderr)`, `self._logger.error(message)` (replacing the `Failed to run command` / `Traceback:` error logs; keep `Failed to run command` at DEBUG), then `raise type(e)(message) from e`. Leave the `FileNotFoundError` branch and the `lexer failed` warning branch unchanged. The `if _gen.returncode != 0` block raises `pde.OMBuildError(_translation_error_message(...))`.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/session_tools/test_omc_diagnostics.py tests/session_tools/test_pydelica_patch.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**: `fix: include OMC diagnostics in model translation errors`

### Task 3: Pin already-working failure reports

**Files:**
- Test: `tests/session_tools/test_omc_diagnostics.py`

**Interfaces:**
- Consumes: the `_build` test helper from Task 2.

- [ ] **Step 1: Write the regression tests**

```python
def test_c_compiler_error_in_external_function_is_reported(tmp_path):
    source = (
        "model BrokenC\n  function f\n    input Real x;\n    output Real y;\n"
        '  external "C" y = brokenF(x) annotation(Include="double brokenF(double x) { return x +; }");\n'
        "  end f;\n  Real x(start=1);\nequation\n  der(x) = f(x);\nend BrokenC;\n"
    )
    exc = _build(tmp_path, "BrokenC", source)
    assert exc.type is pydelica.exception.OMBuildError
    assert "error: expected expression" in str(exc.value)

def test_violated_assert_reports_message_and_time(tmp_path):
    path = tmp_path / "Assertion.mo"
    path.write_text('model Assertion\n  Real x(start=1);\nequation\n  der(x) = 1;\n  assert(x < 1.5, "x exceeded limit");\nend Assertion;\n')
    builder = session_tools.SessionBuilder(path)
    with pytest.raises(pydelica.exception.OMAssertionError, match="x exceeded limit"):
        builder.session.simulate(model_name="Assertion")
```

The C compiler's wording differs between gcc and clang. If `expected expression` does not match on the devcontainer's compiler, assert on `brokenF` plus `error:` instead.

- [ ] **Step 2: Run**

Run: `uv run pytest tests/session_tools/test_omc_diagnostics.py -v`
Expected: all pass. These tests pin existing behaviour, so a failure here means a regression and must be investigated, not the test changed.

- [ ] **Step 3: Full checks**

Run: `uv run pytest tests && uv run mypy src tests && uv run isort --check-only src tests examples`
Expected: all pass, no mypy errors, isort clean.

- [ ] **Step 4: Commit**: `test: pin C build and assertion failure reports`

## Self-review

1. **Spec coverage:** stories 1, 5, 6 → Task 2 syntax test; 2, 3, 7, 8 → Task 2 imbalance test; 4 → undeclared test; 9, 10 → Task 3; 11 → covered by the shared `SessionBuilder` path that the comparison bases use; 12 → `test_model_with_warnings_still_builds`. Logging decision → Task 2 Step 3. Filtering → Task 1.
2. **Step scan:** each code step names the function, file, and exact values.
3. **Type consistency:** `_omc_diagnostics(stdout, stderr)` and `_translation_error_message(source_file, returncode, stdout, stderr)` are used with the same argument order in Tasks 1 and 2.
4. **Review Focus:** 1 → `test_over_determined…`; 2 → `test_model_with_warnings_still_builds`; 3 → `test_missing_library_class_is_named`; 4 → `test_omc_diagnostics_falls_back_to_stdout`; 5 → `test_omc_diagnostics_keeps_errors_warnings_and_continuations_in_order`.
5. **Proportion:** the code blocks are test assertions. Implementation bodies are left to the signatures.
