---
status: accepted
---

# Saved results default to `.mat`, written by mtools from the result

`save_solutions` writes each result as `.mat` by default, and as `.csv` when the run config sets `output_format=csv`. The plotting tool reads both. mtools writes the `.mat` from the returned DataFrame, so the saved file holds exactly the returned columns and rows. It uses OMC's MATLAB v4 binTrans layout, so OpenModelica's `readSimulationResult` and mtools' own reader can open it. The Modelica type of each column goes in an extra `mtools_types` matrix after `data_2`, which OMC's reader ignores. Reading a saved `.mat` therefore gives back `bool` and `int64` columns without the build's `_init.xml`. We chose `.mat` as the default because it is OMC's native format, it stores full double precision, and it is smaller than CSV for long runs.

This reverses two Out of Scope items in the [OMC backend spec](../specs/2026-11-08-omc-backend-spec.md): the plotting tool reading `.mat` files, and the plotting tool reading only CSVs.

## Considered Options

- **Copy OMC's `_res.mat` from the run directory.** This needs no writer, but the file has every variable regardless of `variable_filter`, holds parameter aliases on Cpp, and loses the Boolean and Integer types once it is apart from `_init.xml`. Rejected.
- **A `save_solutions` argument only.** This leaves no Hydra override, so every entry point would need its own flag. Rejected; `save_solutions` still takes the format as an argument, defaulting to `mat`.

## Consequences

- `save_solutions` writes `.mat` unless it is told otherwise, which is a breaking change for scripts that read the saved CSVs.
- A result without rows cannot be written as `.mat`, because the reader treats a `data_2` with no columns as an unfinished file.
