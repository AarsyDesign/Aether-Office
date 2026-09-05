# PHASE 3 — REAL-TIME EVENT STREAMING & MULTI-AGENT FOUNDATION

## 1. Problem

Pada Phase 1, 1.5, dan 2, Aether Office berhasil membangun core reliability dan chunked developer pipeline (planner, topological sort, file-based generation, validation, resume, retry, targeted fix). Namun, arsitektur event dan komunikasinya masih memiliki keterbatasan mendasar:

1. **Tight Coupling to Hardcoded Roles**: Log event terikat langsung pada nama role hardcoded (`pm`, `conceptor`, `developer`, `qa`) tanpa identitas agent unik (`agent_id`). Ini menghalangi skenario masa depan di mana sebuah tim memiliki banyak developer (`developer_001`, `developer_002`) atau spesialis role baru (Designer, Copywriter, DevOps, dsb.).
2. **Missing Streaming & Bus Abstraction**: Tidak ada layer perantara antara eksekusi agent dan consumer tampilan. CLI mengandalkan print langsung dan polling pasif ke SQLite.
3. **No Formal Agent State Model**: State agent tidak memiliki standar terpadu (IDLE, THINKING, PLANNING, WORKING, WAITING, RETRYING, TESTING, COMPLETED, FAILED, BLOCKED). UI di masa depan membutuhkan status real-time tanpa harus merekonstruksi ribuan baris event log lama.
4. **No Event Replay Capability**: Sistem belum memiliki cara sederhana untuk memuat project, membaca state terkini, dan melakukan replay event secara berurutan untuk presentation layer.

---

## 2. Event Architecture

Phase 3 memperkenalkan pemisahan tegas 4 layer:

```text
┌─────────────────────────────────────────────────────────┐
│                    AGENT EXECUTION                      │
│     (PM, Conceptor, Planner, Developer, QA, Future)     │
└────────────────────────────┬────────────────────────────┘
                             │ emits Event envelopes
                             ▼
┌─────────────────────────────────────────────────────────┐
│                      EVENT BUS                          │
│     - Thread-safe pub/sub                               │
│     - Subscriber exception isolation                    │
│     - Zero external dependencies                        │
└──────────────┬───────────────────────────┬──────────────┘
               │                           │
               ▼                           ▼
┌───────────────────────────┐ ┌───────────────────────────┐
│     STREAMING LAYER       │ │    PERSISTENCE & STATE    │
│  - Stream abstraction     │ │  - SQLite `events` table  │
│  - Queue iterator         │ │  - SQLite `agent_states`  │
│  - Subscriptions          │ │  - Event Replay           │
└──────────────┬────────────┘ └───────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────┐
│               PRESENTATION CONSUMERS                    │
│        (CLI Live Progress, Future WebSocket/UI)         │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Event Envelope

Semua event di seluruh sistem distandarkan ke satu schema dataclass:

```python
@dataclass
class Event:
    event_type: str
    project_id: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=_now_iso)
    task_id: Optional[int | str] = None
    agent_id: Optional[str] = None
    agent_role: Optional[str] = None
    status: Optional[str] = None
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
```

### Serialisasi & Deserialisasi
- `to_dict()`: Menghasilkan format JSON-serializable dictionary.
- `from_dict(d)`: Merekonstruksi instance `Event` lengkap.

---

## 4. Event Bus

`EventBus` diimplementasikan secara dependency-light pada `events.py`:

```python
class EventBus:
    def subscribe(self, handler: Callable[[Event], None]) -> None
    def unsubscribe(self, handler: Callable[[Event], None]) -> None
    def publish(self, event: Event) -> None
```

### Karakteristik Utama
- **Synchronous by default**: Ringan, deterministik, dan bebas async framework eksternal.
- **Thread-safe**: Dilindungi oleh reentrant lock (`threading.Lock`).
- **Subscriber Exception Isolation**: Jika subscriber mengalami crash atau melempar exception, exception tersebut diisolasi, dicatat ke `subscriber_errors`, dan **tidak menghentikan publisher maupun subscriber lainnya**.
- **Bridged to Database**: `Database` class bertindak sebagai subscriber/layer penyimpanan SQLite terpadu.

---

## 5. Streaming Layer

Abstraksi `Stream` menghubungkan `EventBus` dengan consumer realtime (CLI, WebSocket, SSE, atau UI):

```python
stream = Stream(event_bus)
stream.publish(event)
stream.subscribe(callback)
for event in stream.iter_events(timeout=0.1):
    # Process event
stream.close()
```

- Menggunakan `queue.Queue` internal yang thread-safe.
- Mendukung generator `iter_events()` dengan timeout.
- Pemanggilan `close()` mengirim sentinel `None` yang melepaskan iterasi tanpa deadlock.

---

## 6. Agent State Model

State agent dibakukan dalam 10 state standar (`registry.py`):

```text
IDLE
THINKING
PLANNING
WORKING
WAITING
RETRYING
TESTING
COMPLETED
FAILED
BLOCKED
```

### Validasi Transisi
- Fungsi `validate_agent_state(state)`: Memastikan state terdaftar.
- Fungsi `validate_agent_transition(from_state, to_state)`: Memverifikasi keabsahan transisi (misalnya `IDLE -> THINKING`, `WORKING -> RETRYING`, dsb.).
- Agent memancarkan event `agent_state_changed` pada setiap transisi, memuat `previous_state`, `state`, `agent_id`, dan detail tugas.

---

## 7. Agent Registry

Registry in-memory yang thread-safe untuk mengelola identitas dan manifest agent (`registry.py`):

```python
registry.register(manifest)
registry.get("developer_001")
registry.list()
registry.find_by_role("developer")
registry.find_by_department("engineering")
registry.update_status("developer_001", "WORKING")
```

- Menolak pendaftaran `agent_id` duplikat (`ValueError`).
- Menyediakan pencarian multi-agent berdasarkan `role` maupun `department`.

---

## 8. Separate Agent Identity from Role

Identitas agent (`agent_id`) dipisahkan secara tegas dari peran fungsional (`role`):

```text
Agent Manifest
 ├── id: "developer_001"        (Identity)
 ├── name: "Full-Stack Dev"     (Display Name)
 ├── role: "developer"          (Functional Role)
 ├── department: "engineering"  (Department)
 ├── capabilities: [...]        (Skills)
 ├── model: Optional[str]       (Future model routing)
 └── status: "WORKING"          (Live State)
```

Ini memungkinkan skenario:
- `developer_001` (backend specialist)
- `developer_002` (frontend specialist)
- `developer_003` (mobile specialist)

Semuanya memiliki role `developer`, namun dapat dialokasikan ke tugas berbeda.

---

## 9. Organization-Ready Architecture

Fondasi hirarki organisasi disiapkan:

```text
Organization (Aether Office)
    ├── Department: Engineering
    │     ├── developer_001 (Full-Stack Developer)
    │     ├── planner_001   (Software Architect & Planner)
    │     └── qa_001        (QA Engineer)
    │
    └── Department: Product
          ├── pm_001        (Project Manager)
          └── conceptor_001 (Conceptor Analyst)
```

Diinisialisasi secara otomatis melalui `create_default_organization()`.

---

## 10. Event Persistence

Penyimpanan event tetap menggunakan SQLite (`tasks.db`) dengan pemisahan tegas antara **Event Log** dan **Current State**:

### Tabel `events`
Menyimpan riwayat append-only dari seluruh event yang terjadi:
- Kolom: `id`, `project_id`, `event_type`, `agent_role`, `task_id`, `data`, `created_at`, `event_id`, `agent_id`, `status`.

### Tabel `agent_states`
Menyimpan status **saat ini** dari setiap agent:
- Kolom: `agent_id`, `project_id`, `agent_role`, `state`, `details`, `updated_at` (PRIMARY KEY: `agent_id`, `project_id`).
- Memungkinkan API dan UI memanggil `db.get_agent_state(agent_id, project_id)` atau `db.get_all_agent_states(project_id)` secara instan $O(1)$ tanpa perlu memutar ulang ribuan baris log.

---

## 11. Event Replay

Dukungan replay SQLite tersedia via method `replay_events`:

```python
replayed = db.replay_events(project_id, since_id=None, handler=streamer.on_event)
```

CLI juga menyediakan perintah replay langsung:
```bash
python cli.py replay <project_id>
```
Yang memutar ulang urutan event project secara berurutan dan memformatnya kembali ke layar.

---

## 12. Existing Agent Integration

Seluruh agent Phase 1–2 terintegrasi ke event & state system:

1. **PM (`agents/pm.py`)**:
   - `IDLE` → `THINKING` (analisis brief) → `WORKING` (pembuatan task & docs) → `COMPLETED`
2. **Conceptor (`agents/conceptor.py`)**:
   - `IDLE` → `THINKING` (analisis context) → `WORKING` (requirements & test plan) → `COMPLETED`
3. **Planner (`agents/planner.py`)**:
   - `PLANNING` (arsitektur & dependency graph) → `COMPLETED`
4. **Developer (`agents/developer.py`)**:
   - `PLANNING` → `WORKING` (per unit dengan progress `x/y`) → `RETRYING` (jika terjadi syntax/truncation error) → `WORKING` → `COMPLETED`
5. **QA (`agents/qa.py`)**:
   - `TESTING` → `COMPLETED` (`PASS`) atau `FAILED` (`FAIL` dengan daftar bugs)

---

## 13. CLI Streaming

CLI kini terhubung langsung ke `EventBus` via `CLIProgressStreamer`:

```text
[AETHER OFFICE]

17:19:27  PM          THINKING
17:19:28  PM          WORKING
17:19:28  PM          COMPLETED

17:19:28  CONCEPTOR   THINKING
17:19:28  CONCEPTOR   WORKING
17:19:28  CONCEPTOR   COMPLETED

17:19:29  PLANNER     PLANNING
17:19:29  PLANNER     COMPLETED

17:19:29  DEVELOPER   WORKING
17:19:29  DEVELOPER   a.py          1/3
17:19:30  DEVELOPER   b.py          2/3
17:19:30  DEVELOPER   c.py          3/3
17:19:31  DEVELOPER   COMPLETED

17:19:31  QA          TESTING
17:19:31  QA          PASS

PROJECT COMPLETE
```

---

## 14. Tests

Pengujian dilakukan menggunakan `pytest` dengan total **112 tests lulus (100%)**:

- **79/79** Tests Phase 1, 1.5, dan 2 (`test_reliability.py`):
  - AgentResult defaults & failure serialization
  - State machine transitions & status validation
  - LLM cleaning, reasoning extraction, truncation detection
  - Database tasks, events, audit log, dev units
  - QA error categorization & response validation
  - LLM retry on timeout & third attempt success
  - PMAgent, DeveloperAgent chunking, resume, retry, fix cycle
  - Planner circular dependency & topological sort
  - Full pipeline integration simulations (3-file project, retry, failure stops)
- **33/33** Tests Phase 3 (`test_streaming.py`):
  - Event envelope defaults, UUID generation, dict serialization/deserialization
  - Identity vs Role separation
  - EventBus pub/sub, unsubscribe, multiple subscribers
  - EventBus subscriber exception isolation
  - Stream abstraction queue, iterator, close unblocking, delegation
  - Agent state validation & transition rules (valid & invalid)
  - Agent registry registration, duplicate ID rejection, list, role filtering, department filtering, status updates
  - Default organization hierarchy & specialist auto-registration
  - SQLite event persistence with envelope fields
  - Direct current state querying without replay
  - Event replay with handler callback
  - CLI progress streamer formatting & visual rhythm
  - Agent state change emissions (PM, Conceptor, Planner, Developer, QA)
  - Developer retry state transition emission
  - Pipeline lifecycle events (`pipeline_started`, `pipeline_completed`)

---

## 15. Known Issues & Backward Compatibility

- **Windows Console Encoding**: Diatasi dengan rekonfigurasi `sys.stdout` UTF-8 pada `cli.py` sehingga output emoji dan karakter unicode berjalan lancar di terminal Windows.
- **SQLite Concurrency & In-Memory Paths**: Diatasi dengan penanganan `:memory:` yang tidak memicu pemanggilan `mkdir()` atau `WAL` pragma pada path memory virtual.
- **100% Backward Compatibility**: Seluruh pemanggilan fungsi lama (seperti `db.log_event("p1", "test.event", "pm", data={...})`, `db.get_events()`, dsb.) tetap berjalan tanpa perubahan.

---

## 16. Phase 4 Recommendation

Tahap berikutnya adalah **Phase 4 — AI Office Organization & Workforce**.

Fokus utama Phase 4:
1. **Multi-Profession Workforce Foundations**:
   - Penambahan katalog profesi AI (Designer, Researcher, Marketing, Sales, Finance, HR, Copywriter, DevOps, Legal, Content Creator, dsb.).
2. **Employee Profiles & Capabilities**:
   - Pendefinisian spesifikasi keahlian, personality, background context, dan system prompt khusus per karyawan virtual.
3. **Model Assignment / Multi-Model Routing**:
   - Pemetaan model LLM sesuai spesialisasi peran (misal: reasoning model untuk PM/Legal, coding model untuk Developer, creative model untuk Copywriter).
4. **Task Assignment & Collaboration**:
   - Mekanisme penugasan tugas dinamis antar agent dalam satu departemen atau lintas departemen.
5. **Organizational Memory**:
   - Penyimpanan memori jangka panjang per agent dan per tim.
