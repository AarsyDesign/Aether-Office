# Phase 1.5 — Reliability & Error Handling

**Status:** Complete
**Date:** 2026-09-04
**Tests:** 50/50 pass
**Changes:** 12 files modified/created

---

## What Changed

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `result.py` | 28 | `AgentResult` — standardized return contract |
| `test_reliability.py` | 420 | 50 unit tests with mock LLM |

### Modified Files

| File | Change |
|------|--------|
| `llm.py` | Full rewrite — retry, validation, error types, `call_llm_with_retry` |
| `status.py` | Added `RETRYING` state + `validate_transition()` |
| `db.py` | Transition validation in `update_task_status`, `:memory:` compat |
| `agents/base.py` | `AgentResult` return, `_safe_run()`, `_write_file` returns bool |
| `agents/pm.py` | `AgentResult` return, field validation, error handling |
| `agents/conceptor.py` | `AgentResult` return, output length validation |
| `agents/developer.py` | `AgentResult` return, `detect_truncation()`, integrity checks |
| `agents/qa.py` | `AgentResult` return, `categorize_test_error()`, `validate_qa_response()` |
| `orchestrator.py` | Per-phase error boundary, `_run_phase()`, graceful failure |
| `cli.py` | Top-level try/except, exit codes |

---

## Architecture Changes

### AgentResult Contract

Semua agent sekarang return `AgentResult`:

```python
@dataclass
class AgentResult:
    success: bool
    output: Any           # str | dict | None
    files: list[str]
    error: str | None
    usage: dict | None
    events: list[dict]
```

### LLM Error Hierarchy

```
LLMError (base)
├── LLMAuthError       → never retry (401/403)
├── LLMRateLimitError  → retry with backoff (429)
├── LLMTimeoutError    → retry with backoff (timeout/connection)
└── LLMResponseError   → retry (empty/malformed/invalid)
```

### Retry Strategy

```
call_llm_with_retry(max_retries=3):
  attempt 0: call
  attempt 1: wait 5s, call
  attempt 2: wait 10s, call
  attempt 3: wait 20s, call → raise LLMError

LLMAuthError: never retry (fatal)
```

### Task State Machine

```
BACKLOG → READY → IN_PROGRESS → REVIEW → QA → DONE
                     ↓   ↑        ↓
                   BLOCKED      FAILED → IN_PROGRESS
                     ↓   ↑        ↓
                   READY      RETRYING → IN_PROGRESS
```

Transition validation logs `invalid_transition` event but doesn't block.

### Failure Boundary

```
Orchestrator.run()
  ├─ _run_phase("pm")       → PM crash → FAILED + event → stop
  ├─ _run_phase("conceptor") → Conceptor crash → FAILED + event → stop
  ├─ _run_phase("developer") → Developer crash → FAILED + event → stop
  └─ _run_phase("qa") × N   → QA crash → FAILED + event → stop
                              Developer fix crash → FAILED + event → stop
```

Each phase wrapped in try/except. AgentResult.success=false stops pipeline.

### Truncation Detection

`detect_truncation(output)` checks:
- Odd code fence count (unclosed ```)
- Unbalanced braces `{}` (incomplete JSON)
- Abrupt ending (no trailing newline)
- CONFIG block incomplete

If truncation + 0 files extracted → FAIL.

### Test Error Categorization

```python
TEST_FAIL        # Assertion failed, exit non-zero
RUNNER_FAIL      # Import/module error
COMMAND_NOT_FOUND # exit 127 or not found
TIMEOUT          # subprocess timeout
APP_CRASH        # SyntaxError, NameError, etc.
```

---

## Event Types (Complete)

```
pipeline.started / pipeline.completed / pipeline.failed
agent.started / agent.completed / agent.failed
task.created / task.completed / task.failed
file_generated / file_write_failed
validation_failed
test_started / test_passed / test_failed
invalid_transition
```

---

## Test Results

```
TestAgentResult              (4 tests)  ✅
TestStateMachine             (7 tests)  ✅
TestLLMCleaning              (5 tests)  ✅
TestLLMClient                (2 tests)  ✅
TestLLMRetry                 (3 tests)  ✅
TestTruncationDetection      (5 tests)  ✅
TestDatabase                 (5 tests)  ✅
TestQAErrorCategorization    (5 tests)  ✅
TestQAValidation             (5 tests)  ✅
TestPMAgent                  (4 tests)  ✅
TestDeveloperAgent           (3 tests)  ✅
TestOrchestrator             (1 test)   ✅
─────────────────────────────────────────
Total:                       50 tests   ✅ ALL PASS
```

---

## Bugs/Edge Cases Handled

| Issue | Handling |
|-------|----------|
| LLM timeout | Retry with backoff, then FAIL |
| LLM returns null content | `LLMResponseError`, retry |
| LLM returns malformed JSON | `LLMResponseError`, retry |
| LLM returns empty response | `LLMResponseError`, retry |
| LLM 401/403 | `LLMAuthError`, no retry |
| LLM 429 | `LLMRateLimitError`, retry with backoff |
| PM returns non-dict | Validation error, FAIL |
| PM missing required fields | Validation error, FAIL |
| PM produces 0 tasks | Validation error, FAIL |
| Developer output truncated | Detected, FAIL |
| Developer config JSON invalid | Warning logged, continues |
| QA returns non-dict | Validation error, FAIL |
| QA missing verdict | Default FAIL |
| Test command timeout | `TIMEOUT` category |
| Test runner crash | `RUNNER_FAIL` category |
| Test command not found | `COMMAND_NOT_FOUND` category |
| Agent crashes unexpectedly | Caught, event logged, pipeline stops |
| Invalid state transition | Logged as event, allowed |

---

## Known Issues

1. **Token limit unchanged** — 4096 tokens still limit Developer output
2. **No chunked output** — Phase 2 concern
3. **No streaming** — Phase 2 concern
4. **No resume** — Pipeline restarts from scratch on failure

---

## Acceptance Criteria

```
✅ Pipeline tidak crash tanpa error yang tercatat
✅ Retry memiliki batas (3 attempts max)
✅ Semua agent memiliki AgentResult contract yang konsisten
✅ Invalid LLM response terdeteksi (empty, malformed, null)
✅ Truncated output terdeteksi (code fence, braces, abrupt)
✅ Task state konsisten dengan transition validation
✅ Failure tercatat di event log (agent.failed, pipeline.failed)
✅ Test failure dibedakan dari test runner failure (6 categories)
✅ Unit test reliability tersedia (50 tests)
✅ PHASE_1_5.md dibuat
```

---

## Recommendations for Phase 2

1. **Chunked Developer** — split output per file, validate each independently
2. **Streaming** — real-time output via SSE
3. **Resume pipeline** — continue dari phase terakhir yang berhasil
4. **Multiple models** — assign model berbeda per agent
5. **Token budget** — dynamic max_tokens based on task complexity
