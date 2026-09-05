# Contributing to Aether Office

Thank you for your interest in contributing to **Aether Office**! We welcome contributions from developers worldwide to make autonomous AI workforce operations more reliable, transparent, and intelligent.

---

## 🛠️ Development Setup

### 1. Prerequisites
- Python 3.10, 3.11, or 3.12
- `git`
- `uv` (recommended) or `pip` + `virtualenv`

### 2. Clone the Repository
```bash
git clone https://github.com/your-username/aether-office.git
cd aether-office
```

### 3. Create a Virtual Environment & Install
Using `uv`:
```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

Or using standard `pip`:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

---

## 🧪 Running Tests

Aether Office maintains a rigorous test suite covering all architectural phases (reliability, chunked developer, streaming event bus, workforce simulation, multi-project scheduler, runtime engine, objective-to-outcome, and adaptive planning).

### Run all tests:
```bash
pytest -v
```

### Run specific phase test suite:
```bash
# Phase 9: Adaptive Planning & Intelligence
pytest test_adaptive_planning.py -v

# Phase 8: Objective-to-Outcome Engine
pytest test_objective.py -v

# Phase 7: Persistent Runtime & Heartbeat
pytest test_runtime.py -v

# Phase 6: Autonomous Office Operations & Multi-Project Scheduling
pytest test_office_operations.py -v

# Phase 5: Dynamic Team Collaboration & Delegation
pytest test_collaboration.py -v

# Phase 4: Workforce & Organization
pytest test_workforce.py -v

# Phase 3: Real-Time Event Streaming
pytest test_streaming.py -v

# Phase 1 & 2: Reliability & Chunked Developer
pytest test_reliability.py -v
```

> [!IMPORTANT]
> **Zero Regression Guarantee**: Pull requests must maintain 100% test pass rate across all 235+ tests.

---

## 📐 Architecture Principles

When proposing changes, please adhere to our core principles:

1. **Deterministic Validation Over Raw LLM**:
   - LLM output is never trusted directly for state transitions, database writes, or task assignments.
   - All proposed plans must pass through `PlanValidator`.
2. **Crash Resilience & Idempotency**:
   - Scheduler ticks and worker dispatch operations must remain idempotent.
   - Systems must recover smoothly from cold-start restarts without corrupting budget or task states.
3. **Backward Compatibility**:
   - Keep existing interfaces intact (`OfficeOrchestrator`, `SchedulerEngine`, `LegacyObjectivePlanner`).
   - Do not silently break existing API contracts.
4. **Clean Abstractions**:
   - Avoid monolithic files; keep planning strategies, risk evaluators, and scheduling isolated in their respective modules.

---

## 🚀 Pull Request Workflow

1. Fork the repository and create your branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your additions, ensuring clean type hints and documentation.
3. Add corresponding unit and integration tests in the appropriate `test_*.py` file.
4. Ensure the entire test suite passes (`pytest -v`).
5. Commit your changes with descriptive messages:
   ```bash
   git commit -m "feat(planner): add support for XYZ strategy"
   ```
6. Push to your fork and submit a Pull Request targeting `main`.
