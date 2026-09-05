# Phase 1 — AI Dev Team Core Engine

**Status:** MVP built, bugs found & partially fixed
**Date:** 2026-09-04
**LOC:** 1,156 lines Python

---

## What Was Built

Core engine untuk AI Development Team — sistem orkestrasi multi-agent yang menjalankan pipeline: brief → PM → Conceptor → Developer → QA, dengan retry loop otomatis.

### File Structure

```
Aether Office/
├── cli.py              (164 lines) — CLI entry: run/status/events/list
├── config.yaml         — LLM endpoint, api_key, model, settings
├── orchestrator.py     (139 lines) — Pipeline engine, phase sequencing
├── llm.py              (102 lines) — OpenAI-compatible LLM wrapper
├── db.py               (179 lines) — SQLite: tasks, events, audit_log
├── status.py           (31 lines)  — Task state constants + transitions
├── agents/
│   ├── __init__.py     (6 lines)   — Exports
│   ├── base.py         (57 lines)  — Agent base class
│   ├── pm.py           (82 lines)  — Project Manager agent
│   ├── conceptor.py    (86 lines)  — Conceptor/Analyst agent
│   ├── developer.py    (118 lines) — Developer agent
│   └── qa.py           (192 lines) — QA Engineer agent
├── briefs/
│   └── todo-app.md     — MVP test brief
├── projects/           — Generated project output
└── data/
    └── tasks.db        — SQLite database
```

---

## Architecture

### Workflow

```
User (project brief)
  ↓
Project Manager → break into tasks → product.md
  ↓
Conceptor → requirements.md + testing.md
  ↓
Developer → code files + dev_config.json
  ↓
QA → qa_report.md + PASS/FAIL
  ↓
  ↻ if FAIL → Developer fix → QA retest (max 3 cycles)
  ↓
DONE
```

### Database Schema (SQLite)

**projects** — project metadata
| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PK | `name-timestamp` |
| name | TEXT | |
| brief | TEXT | Original brief |
| status | TEXT | ACTIVE/DONE/FAILED |
| output_dir | TEXT | |
| created_at | TEXT | ISO timestamp |
| updated_at | TEXT | |

**tasks** — task tracking
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| project_id | TEXT FK | |
| title | TEXT | |
| description | TEXT | |
| status | TEXT | BACKLOG→READY→IN_PROGRESS→REVIEW→QA→DONE |
| assigned_to | TEXT | |
| priority | INTEGER | 1-5, 5=highest |
| dependencies | TEXT | JSON array |
| result | TEXT | QA result JSON |
| created_at | TEXT | |
| updated_at | TEXT | |

**events** — activity log
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| project_id | TEXT FK | |
| event_type | TEXT | e.g. `pipeline.started`, `task.created` |
| agent_role | TEXT | pm/conceptor/developer/qa |
| task_id | INTEGER | |
| data | TEXT | JSON payload |
| created_at | TEXT | |

**audit_log** — immutable action record
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| project_id | TEXT FK | |
| agent_role | TEXT | |
| action | TEXT | |
| details | TEXT | JSON |
| created_at | TEXT | |

### Event Types

```
pipeline.started / pipeline.completed / pipeline.failed
agent.started / agent.completed
task.created / task.completed / task.failed
file_written
qa.completed
```

---

## Agent Design

### Base Agent (`agents/base.py`)

Semua agent inherit dari `Agent`:
- `run(context)` — override per role
- `_log(event_type, data)` — log ke event system
- `_write_file(rel_path, content)` — tulis ke project output
- `_write_doc(name, content)` — tulis ke docs/ subdir
- `_read_docs()` — baca semua shared docs
- `_read_file(rel_path)` — baca file dari output

### PM Agent (`agents/pm.py`)

**Input:** project brief (markdown text)
**Output:** tasks di DB + `docs/product.md`
**Method:** LLM call dengan JSON mode → parse tasks → insert ke SQLite

Prompt instructs LLM to output:
```json
{
  "project_name": "...",
  "project_description": "...",
  "tasks": [{ "title", "description", "priority", "dependencies" }],
  "tech_stack": "...",
  "file_structure": "..."
}
```

### Conceptor Agent (`agents/conceptor.py`)

**Input:** tasks + product brief
**Output:** `docs/requirements.md` + `docs/testing.md`
**Method:** LLM call → write markdown docs

Requirements doc includes:
- Functional requirements
- User stories
- Acceptance criteria (testable, pass/fail)
- Technical design
- Edge cases
- Testing strategy

### Developer Agent (`agents/developer.py`)

**Input:** requirements + acceptance criteria
**Output:** code files ke disk + `dev_config.json`
**Method:** LLM call → regex parse `### FILE: path` blocks → write files

Regex pattern: `#{2,3}\s*FILE:\s*(.+?)\s*\n```(?:\w*)\s*\n(.*?)```

Output includes CONFIG block:
```json
{
  "main_entry": "app.py",
  "install_command": "pip install -r requirements.txt",
  "run_command": "python app.py",
  "test_command": "pytest"
}
```

### QA Agent (`agents/qa.py`)

**Input:** all code files + requirements + acceptance criteria
**Output:** `docs/qa_report.md` + verdict (PASS/FAIL)
**Method:** 2-phase testing

**Phase 1 — LLM Review:**
- Compare code vs acceptance criteria
- Output structured JSON verdict
- List bugs with fix suggestions
- Suggest test commands

**Phase 2 — Automated Tests:**
- Execute suggested test commands via subprocess
- Capture stdout/stderr/exit code
- Combine with LLM verdict

Output JSON:
```json
{
  "verdict": "PASS" | "FAIL",
  "criteria_results": [{ "criterion", "status", "evidence" }],
  "bugs_found": [{ "title", "description", "file", "fix_suggestion" }],
  "test_commands_to_run": ["pytest", "npm test"],
  "fix_instructions": "..."
}
```

---

## LLM Wrapper (`llm.py`)

Supports semua provider yang kompatibel dengan OpenAI API format:
- OpenAI (GPT-4o)
- Anthropic (via proxy)
- Ollama (local)
- LM Studio / vLLM
- Custom endpoint (gratisan, dll)

Features:
- `data: [DONE]` trailing response handling
- Reasoning model support (`content` vs `reasoning_content`)
- JSON mode via `response_format`
- Retry logic with exponential backoff (3 attempts)
- 300s timeout

---

## CLI Commands

```bash
# Run pipeline
python cli.py run briefs/todo-app.md
python cli.py run briefs/todo-app.md --name my-project

# List projects
python cli.py list

# Check status
python cli.py status <project-id>

# View event history
python cli.py events <project-id>
```

---

## Bugs Found & Fixed During Testing

### 1. `content: null` on reasoning models
**Symptom:** Model returns `reasoning_content` instead of `content`
**Fix:** Check both fields, fallback ke `reasoning_content`

### 2. `data: [DONE]` trailing response
**Symptom:** `json.JSONDecodeError: Extra data`
**Cause:** Server append SSE trailer `"cost":"0"}data: [DONE]`
**Fix:** Strip trailing `data: [DONE]` sebelum JSON parse

### 3. `_write_doc` missing method
**Symptom:** `AttributeError: 'ConceptorAgent' object has no attribute '_write_doc'`
**Fix:** Add `_write_doc()` ke base `Agent` class

### 4. Developer regex too strict
**Symptom:** `0 files written` meski LLM output file blocks
**Fix:** Relax regex dari `### FILE:` jadi `#{2,3}\s*FILE:`

### 5. Free model timeout
**Symptom:** `ReadTimeout` at 300s during Developer phase
**Status:** Partial — retry logic added, but large outputs still problematic
**Root cause:** Free model rate limits + slow inference with 4096 tokens

### 6. `create_project` return type
**Symptom:** `sqlite3.ProgrammingError: type 'dict' is not supported`
**Fix:** Return project_id string, bukan dict

---

## Test Run Results

### Attempt 1 (before fixes)
```
PM:     ✅ 10 tasks created
Conceptor: ✅ Requirements doc: 9010 chars
Developer: ❌ 0 files written (regex bug)
QA:     ❌ FAIL (no code to test)
Retry 1: Developer: 0 files, QA: FAIL
Retry 2: Developer: 3 files, QA: FAIL (1 bug)
Retry 3: Developer: 0 files, QA: FAIL (6 bugs)
Result: FAILED after 3 retries
```

### Attempt 2 (after regex fix)
```
PM:     ✅ 13 tasks created
Conceptor: ✅ Requirements doc: 5040 chars
Developer: Timeout (8192 tokens too large)
Result: CRASH
```

### Attempt 3 (max_tokens back to 4096)
```
PM:     ✅ 11 tasks created
Conceptor: ✅ Requirements doc
Developer: Interrupted (user stopped — too slow)
```

---

## Known Issues

1. **Token limit** — 4096 tokens不够写完整 Flask app + templates + JS
2. **Speed** — Free model terlalu lambat untuk pipeline 4 agent
3. **No streaming** — User tidak lihat progress real-time
4. **No chunked output** — Developer harus output semua file sekaligus
5. **No file continuation** — Kalau output truncate, tidak ada mekanisme resume

---

## What's Next

### Priority 1: Reliability
- **Chunked Developer** — split output jadi multiple LLM calls per file
- **Longer timeout** atau streaming untuk model lambat
- **Graceful truncation** — handle partial output

### Priority 2: Quality
- **Better prompts** — lebih spesifik output format
- **File validation** — verify code syntax sebelum write
- **Test runner** — auto-run pytest/npm test setelah write

### Priority 3: Features
- **Streaming output** — progress real-time
- **Resume pipeline** — continue dari phase terakhir
- **Multiple models** — assign model berbeda per agent

### Priority 4: AI Office (Phase 2)
- Agent visualization sebagai karakter
- Real-time state display
- Task board UI
- Event timeline

---

## Decisions Made

| Decision | Choice | Reason |
|----------|--------|--------|
| Language | Python | Fastest to MVP, stdlib rich |
| Storage | SQLite + markdown | Simple, no server needed |
| LLM format | OpenAI-compatible | Universal standard |
| Interface | CLI | No UI overhead for MVP |
| File parsing | Regex | Flexible, no deps needed |
| Retry | 3 attempts + backoff | Handle transient failures |
| QA approach | LLM + automated | Both review and actual tests |
