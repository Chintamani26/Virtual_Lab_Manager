---
name: execution-adapter
description: The unified execution contract for main.py (Judge0), circuit.sim and data.ipynb labs. Load before touching backend/app/execution or adding a new lab type.
---

# Execution adapter pattern

## One schema for every lab type
`ExecutionRequest(lab_type, files, mode: run|test, tests)` → `ExecutionResult` (`backend/app/execution/base.py`):
`engine, status (ok|error|timeout|compile_error), stdout, stderr, tests[], tests_passed, tests_total,
duration_ms, cell_outputs?, truth_table?, summary ("4 of 5 Tests Passed")`. Call `.finalize()` before returning.

## Layers
1. **Runners** (`runners.py`) execute one self-contained Python 3.8+ program:
   - `Judge0Runner` — production sandbox (`JUDGE0_URL`, RapidAPI or self-hosted, base64, `wait=true` + polling).
   - `LocalSubprocessRunner` — dev only (`python -I`, rlimits, timeout). Refuses to start in production
     unless `ALLOW_LOCAL_EXECUTION_IN_PRODUCTION=true`.
2. **Harness** (`harness.py`) wraps student code + tests into one program, runs each test with a per-test
   alarm, and prints a single nonce-marked JSON report. Keep it Python 3.8-compatible (Judge0 CE id 71).
3. **Adapters** (`service.py`), selected by `lab_type`:
   - `coding` → `main.py`; tests are Python `assert` snippets executed in the student's module namespace
     (`__name__ != "__main__"`).
   - `notebook` → `data.ipynb` (nbformat 4); code cells run top-to-bottom in one namespace; magics are
     commented out; `cell_outputs[].index` is the cell's position in the notebook.
   - `circuit` → `circuit.sim`; evaluated in-process by `circuit_sim.py` (safe parser, no `eval`);
     tests are `{inputs, expected}` truth-table rows; result includes the full `truth_table`.

## Rules
- Never `eval`/`exec` student code inside the API process. Python always goes through a runner.
- Students' `/run` uses **visible** tests only; `/submit` and faculty `/validate` use visible + hidden.
- Malformed input → `ExecutionInputError` → HTTP 422. Outputs are clipped (`MAX_OUTPUT_CHARS`).
- Every student run is written to `execution_logs` (with a files snapshot) — the tutor reads the latest one.

## Adding a lab type (e.g. `verilog`)
1. Add it to `LabType`, `LAB_FILENAME`, `LAB_LANGUAGE` (`models.py`) and the SQL `CHECK` constraints.
2. Implement a `LabAdapter` returning `ExecutionResult`; register it in `ExecutionService.adapters`.
3. Add a template in `content.py::TEMPLATES`, a frontend editor tab, and tests in `backend/tests`.
