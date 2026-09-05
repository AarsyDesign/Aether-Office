# PHASE 7 — RUNTIME ENGINE

## 1. Runtime Architecture

Phase 7 mentransformasikan Aether Office dari sistem batch yang digerakkan secara manual (*manual / on-demand tick scheduling*) menjadi **Sistem Operasional Kantor Berkelanjutan (*Autonomous Persistent Runtime Engine*)**.

Runtime Engine bertindak sebagai sistem operasi (*office operating system*) yang mengelola *lifecycle*, detak jantung penjadwalan periodik (*heartbeat loop*), *worker execution boundary*, pencatatan *artifacts & deliverables*, pelacakan *real usage/cost*, penegakan anggaran proyek, penanganan sinyal sistem operasi (`SIGINT`/`SIGTERM`), dan pemulihan otomatis saat *cold start*.

```text
               ┌─────────────────────────────────────────────────┐
               │                OFFICE ORCHESTRATOR               │
               │                   (`office.py`)                 │
               └────────────────────────┬────────────────────────┘
                                        │
                                        ▼
               ┌─────────────────────────────────────────────────┐
               │                  OFFICE RUNTIME                 │
               │                   (`runtime.py`)                │
               │    start() │ stop() │ run() │ tick() │ status() │
               └────────────────────────┬────────────────────────┘
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
              SCHEDULER HEARTBEAT            SIGNAL & LIFECYCLE
             (Configurable Interval)         (SIGINT / SIGTERM)
                         │
                         ▼
              SCHEDULER ENGINE TICK
                 (`scheduler.py`)
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
    COLD-START RECOVERY     DISTRIBUTED LOCK
    (Heal Orphant / Stale)  (office_scheduler)
             │                       │
             └───────────┬───────────┘
                         ▼
                 WORKER BOUNDARY
                 (`TaskWorker`)
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   TASK EXECUTION   ARTIFACT CREATION  USAGE & BUDGET
  (Worker Lifecycle) (`ArtifactStore`) (`UsageTracker` /
   IDLE → RESERVED   (Linked to task,   `BudgetManager`)
   → EXECUTING        project, worker,
   → SUCCESS/FAILURE  and timestamp)
   → RELEASED
```

---

## 2. Lifecycle

Lifecycle `OfficeRuntime` dikontrol secara ketat melalui state machine berbasis thread/proses:

1. **INITIALIZING / COLD-START**:
   - `OfficeRuntime(orchestrator, config)` diinstansiasi.
   - Mengambil konfigurasi dari `RuntimeConfig` (atau environment).
   - Menghubungkan `TaskWorker` ke `SchedulerEngine`.
   - Menjalankan **Cold-Start Recovery** otomatis (`orchestrator.recover_from_crash(timeout_seconds=0.0)`):
     - Membebaskan *stale employee reservations* dari proses sebelumnya yang terhenti mendadak.
     - Mengembalikan tugas `IN_PROGRESS` yang belum selesai kembali ke `READY`.

2. **STARTING (`start()`)**:
   - Menolak *duplicate runtime* (`_is_running` guard).
   - Menerbitkan event `runtime_started`.
   - Menginisialisasi thread latar belakang berdedikasi (*daemon thread*) atau berjalan secara *blocking* (*foreground*).

3. **RUNNING (`run()` / Heartbeat Loop)**:
   - Menjalankan satu siklus `tick(execute=True)`.
   - Tidur secara terfragmentasi (*responsive slice sleeping*, default slice 50ms) untuk memeriksa `_stop_requested` tanpa penundaan.
   - Mengulang siklus hingga `stop()` dipanggil atau `max_ticks` tercapai.

4. **STOPPING / SHUTDOWN (`stop()`)**:
   - Menandai bendera `_stop_requested = True`.
   - Menunggu *tick* dan operasi pekerja yang sedang berjalan selesai secara aman (*graceful wait with timeout*).
   - Membebaskan kunci terdistribusi `office_scheduler` pada database.
   - Mengirimkan event `runtime_stopped` secara idempoten.

5. **STATUS QUERY (`status()`)**:
   - Menyajikan metrik operasional langsung: `is_running`, `ticks_count`, `uptime_seconds`, `heartbeat_interval`, rincian `config`, dan snapshot `office_state`.

---

## 3. Scheduler Heartbeat

Loop detak jantung (*heartbeat*) berjalan secara kontinu tanpa *busy-loop*:

```text
    START
      │
      ▼
┌──────────────┐
│  COLD START  │ (Sembuhkan stale lock & orphan task)
└──────┬───────┘
       │
       ▼  ◄───────────────────────────────────────┐
┌──────────────┐                                  │
│ LOCK ACQUIRE │ (Atomic SQLite lock with TTL)    │
└──────┬───────┘                                  │
       │                                          │
       ▼                                          │
┌──────────────┐                                  │
│  EVALUATE    │ (Peringkat proyek & tugas READY) │
└──────┬───────┘                                  │
       │                                          │
       ▼                                          │
┌──────────────┐                                  │
│   DISPATCH   │ (Cocokkan employee & reserve)    │
└──────┬───────┘                                  │
       │                                          │
       ▼                                          │
┌──────────────┐                                  │
│ EXECUTE WORK │ (TaskWorker isolasi boundary)    │
└──────┬───────┘                                  │
       │                                          │
       ▼                                          │
┌──────────────┐                                  │
│ RECORD & ACC │ (Simpan artifact, usage, budget) │
└──────┬───────┘                                  │
       │                                          │
       ▼                                          │
┌──────────────┐                                  │
│ RELEASE RES  │ (Bebaskan employee & scheduler)  │
└──────┬───────┘                                  │
       │                                          │
       ▼                                          │
┌──────────────┐                                  │
│ RESPONSIVE   │                                  │
│    SLEEP     ├──────────────────────────────────┘
└──────────────┘
```

* **Anti Busy-Loop**: Runtime tidak melakukan polling ketat pada CPU. Tidur interval diatur oleh `heartbeat_interval` dengan *micro-slice* (50 ms).
* **Deterministic Single Runner**: Jika ada dua instance runtime berjalan pada database yang sama, instance kedua akan tertahan oleh `acquire_scheduler_lock` hingga TTL kedaluwarsa atau lock dibebaskan.

---

## 4. Worker Lifecycle

Setiap pekerja dieksekusi melalui kelas `TaskWorker` (`runtime.py`) yang memiliki status transisi eksplisit dan terisolasi:

```text
   IDLE
    │
    ▼
 RESERVED     (Karyawan dikunci, Worker memegang task)
    │
    ▼
EXECUTING     (Agen/Executor menjalankan logika instruksi)
    │
 ┌──┴──────────┐
 ▼             ▼
SUCCESS     FAILURE   (Boundary menangkap semua exception tanpa crash)
 └──┬──────────┘
    │
    ▼
 RELEASED     (Status dibersihkan, Karyawan dibebaskan kembali)
```

### Worker State Definition:
* `IDLE`: Pekerja siap menerima penugasan baru.
* `RESERVED`: Pekerja telah mengikat `task_id` dan `employee_id`. Event `worker_reserved` diterbitkan.
* `EXECUTING`: Pekerja mulai menjalankan logika agen. Event `task_started` diterbitkan.
* `SUCCESS`: Eksekusi berhasil, menghasilkan `AgentResult(success=True)`.
* `FAILURE`: Eksekusi mengalami kesalahan atau exception, menghasilkan `AgentResult(success=False, error=...)`.
* `RELEASED`: Pekerja melepaskan semua referensi penugasan. Event `worker_released` diterbitkan.

---

## 5. Execution Flow

Alur data penuh dari antrean hingga penyelesaian tugas:

```text
1. READY TASK (WorkTask berstatus PENDING/READY)
        ↓
2. SCHEDULER MATCHING (TaskMatcher mencocokkan keahlian & peran karyawan)
        ↓
3. EMPLOYEE RESERVATION (ResourceManager mengunci karyawan secara atomik)
        ↓
4. TASK DISPATCH (Event task_dispatched dipublikasikan)
        ↓
5. WORKER EXECUTION (TaskWorker mengeksekusi agen atau executor)
        ↓
6. AGENT RESULT (Kontrak AgentResult: success, output, files, usage, error)
        ↓
7. ARTIFACT CREATION (ArtifactStore menyimpan deliverable yang terindeks)
        ↓
8. USAGE RECORDING (UsageTracker mencatat konsumsi token riil)
        ↓
9. BUDGET UPDATE (BudgetManager memperbarui biaya dan memeriksa batas anggaran)
        ↓
10. TASK STATE UPDATE (WorkQueue menandai tugas sebagai COMPLETED atau REQUEUED)
        ↓
11. EMPLOYEE RELEASE (ResourceManager melepaskan kunci karyawan)
```

---

## 6. Failure Handling

`OfficeRuntime` dan `TaskWorker` menerapkan isolasi kegagalan berlapis (*multi-layer failure isolation*):

1. **Execution Exception Boundary**:
   - Kegagalan di dalam agen LLM, *tool execution*, atau sintaks Python tidak akan mematikan proses orchestrator.
   - `TaskWorker` menangkap semua `Exception`, mengubah status menjadi `WorkerState.FAILURE`, menghasilkan `AgentResult(success=False, error=str(ex))`, dan tetap mengeksekusi blok `finally` untuk melepaskan penugasan (`WorkerState.RELEASED`).
2. **Scheduler Task Requeueing**:
   - Jika worker gagal menyelesaikan tugas, scheduler menandai tugas `FAILED`, melepaskan karyawan, dan secara otomatis memanggil `requeue_task(task_id)` agar dapat dijadwalkan ulang pada giliran berikutnya.
3. **Budget Overflow Protection**:
   - Jika proyek melebihi anggaran yang dialokasikan, scheduler memblokir proyek, membatalkan reservasi, dan menerbitkan event `budget_exceeded`.

---

## 7. Shutdown Behavior

Graceful shutdown diimplementasikan untuk menangani sinyal sistem operasi:
* `SIGINT` (Ctrl+C di terminal / keyboard interrupt)
* `SIGTERM` (sinyal penghentian proses dari container / systemd)

Langkah penanganan saat shutdown:
1. **Berhenti Menerima Tugas Baru**: `_stop_requested = True` menghentikan detak scheduler berikutnya.
2. **Selesaikan Operasi yang Sedang Berjalan**: Jika ada *tick* atau *task execution* yang sedang berlangsung di thread pekerja, runtime menunggu thread bergabung (*thread join*) hingga batas waktu `timeout`.
3. **Bebaskan Sumber Daya**:
   - Kunci terdistribusi scheduler (`office_scheduler`) pada database SQLite segera dihapus (`release_scheduler_lock`).
   - Karyawan yang telah menyelesaikan tugas dilepaskan ke kolam ketersediaan (*availability pool*).
4. **Persistensi State**: Seluruh perubahan state disimpan secara langsung ke SQLite (didukung mode WAL & *thread-safe connection*).
5. **Keluaran Bersih**: Menerbitkan event `runtime_stopped` secara idempoten dan mencatat log konfirmasi.

---

## 8. Configuration

Seluruh parameter runtime dipusatkan dalam kelas `RuntimeConfig` (`runtime.py`):

| Parameter | Tipe | Default | Keterangan |
| :--- | :--- | :--- | :--- |
| `heartbeat_interval` | `float` | `5.0` | Interval detak jantung dalam detik antar penjadwalan |
| `reservation_ttl` | `float` | `300.0` | Batas waktu reservasi karyawan sebelum dianggap kedaluwarsa |
| `scheduler_lock_ttl` | `float` | `30.0` | Masa berlaku kunci scheduler untuk mencegah *split-brain* |
| `max_concurrent_tasks` | `int` | `10` | Batas maksimum tugas yang dapat berjalan serentak |
| `worker_timeout` | `float` | `60.0` | Batas waktu eksekusi bagi satu worker |
| `retry_policy` | `dict` | `{"max_retries": 3, "backoff_factor": 2.0}` | Kebijakan percobaan ulang jika eksekusi gagal |
| `output_dir` | `str` | `"./output"` | Direktori tempat output file dan artefak disimpan |

Konfigurasi dapat dimuat dari dictionary, file YAML, atau ditimpa melalui argumen CLI.

---

## 9. CLI

Perintah CLI `office` Phase 6 telah diperluas di Phase 7 dengan terminologi bahasa Indonesia yang konsisten:

### 1. `office status` (atau `office` tanpa argumen)
Menampilkan dashboard operasional kantor lengkap dengan metrik runtime:
```bash
python cli.py office status
```
*Output*: Status runtime (`🟢 AKTIF` / `⚪ STANDBY / SIAP`), total ticks, interval heartbeat, ringkasan proyek, status tenaga kerja (*workforce*), antrean tugas, dan penggunaan token.

### 2. `office start`
Memulai runtime engine kontinu dengan penanganan sinyal aman:
```bash
python cli.py office start [--heartbeat 2.0] [--max-ticks 100]
```

### 3. `office stop`
Mengirimkan sinyal penghentian runtime dan membebaskan kunci scheduler terdistribusi:
```bash
python cli.py office stop
```

### 4. `office tick`
Menjalankan satu siklus deterministik detak jantung runtime:
```bash
python cli.py office tick [--no-execute]
```

---

## 10. Observability

Phase 7 melengkapi fondasi observability event-driven (`events.py`):

| Nama Event | Waktu Emisi | Payload Utama |
| :--- | :--- | :--- |
| `runtime_started` | Saat runtime loop dimulai | `config` snapshot |
| `runtime_stopped` | Saat runtime loop berhenti | `total_ticks` |
| `scheduler_tick_started` | Sebelum scheduler mengevaluasi antrean | `tick_number` |
| `scheduler_tick_completed` | Setelah scheduler menyelesaikan 1 siklus | `tick_number`, tugas selesai/terjadwal/gagal |
| `task_dispatched` | Saat tugas siap diserahkan ke pekerja | `task_id`, `project_id`, `employee_id` |
| `task_started` | Saat agen mulai mengeksekusi instruksi | `worker_id`, `task_title` |
| `task_completed` | Saat eksekusi tugas berhasil | `result` data |
| `task_failed` | Saat eksekusi tugas gagal | `reason` error |
| `worker_reserved` | Saat pekerja mengunci tugas & karyawan | `worker_id`, `employee_id` |
| `worker_released` | Saat pekerja selesai dan dibebaskan | `worker_id`, `employee_id` |
| `budget_warning` | Saat penggunaan proyek melewati 80% | `spent`, `budget`, `ratio` |
| `budget_exceeded` | Saat penggunaan proyek melewati 100% | `spent`, `budget` |

---

## 11. Testing

Pengujian komprehensif Phase 7 diimplementasikan pada `test_runtime.py` yang mencakup 12 skenario pengujian unit dan integrasi:

1. `test_runtime_start`: Memvalidasi inisialisasi state running dan emisi event `runtime_started`.
2. `test_runtime_stop`: Memvalidasi penghentian bersih thread dan pembebasan scheduler lock.
3. `test_runtime_heartbeat`: Memvalidasi periodisitas siklus detak jantung dan akumulasi `ticks_count`.
4. `test_graceful_shutdown`: Memvalidasi bahwa tugas yang sedang berlangsung selesai dengan aman saat `stop()` dipanggil.
5. `test_scheduler_continuous_execution`: Memvalidasi eksekusi tugas antrean multi-tick secara berkelanjutan.
6. `test_worker_execution`: Memvalidasi siklus hidup `TaskWorker` (`IDLE -> RESERVED -> EXECUTING -> SUCCESS -> RELEASED`).
7. `test_worker_failure`: Memvalidasi batas kegagalan pekerja tanpa merusak orchestrator.
8. `test_artifact_creation`: Memvalidasi pembuatan deliverable `Artifact` yang terhubung ke task, project, employee, dan timestamp.
9. `test_usage_recording_after_execution`: Memvalidasi pencatatan token input/output pada `UsageTracker`.
10. `test_budget_update_after_execution`: Memvalidasi penambahan biaya terpakai pada anggaran proyek.
11. `test_end_to_end_project_execution`: Tes integrasi penuh end-to-end yang membuktikan rantai aliran:
    `CREATE PROJECT` ➔ `CREATE TASK` ➔ `SCHEDULER` ➔ `RESERVE EMPLOYEE` ➔ `EXECUTE AGENT` ➔ `CREATE RESULT` ➔ `RECORD USAGE` ➔ `UPDATE BUDGET` ➔ `COMPLETE TASK` ➔ `RELEASE EMPLOYEE`.
12. `test_runtime_restart_recovery`: Memvalidasi *cold-start recovery* saat proses sebelumnya mati tanpa shutdown bersih.

### Hasil Verifikasi:
```text
test_runtime.py: 12 passed in 2.38s
Full Test Suite: 199 passed in 41.15s (100% pass rate, 0 failed, 0 regressions)
```

---

## 12. Known Limitations

1. **Single Machine Concurrency**: `OfficeRuntime` saat ini berjalan dalam satu node Python (menggunakan threading & SQLite terdistribusi via database locks). Belum mendukung multi-node cluster yang tersebar di beberapa mesin terpisah.
2. **Worker Pool Scale**: Saat ini worker diinstansiasi sesuai permintaan tugas dalam proses. Belum menggunakan antrean pesan eksternal seperti Redis/RabbitMQ.
3. **Long Running LLM Calls**: Jika pemanggilan model LLM membutuhkan waktu lebih dari `worker_timeout`, thread worker akan menunggu respons atau terputus sesuai timeout HTTP client.

---

## 13. Production Deployment Notes

1. **SQLite WAL Mode**:
   Koneksi SQLite di `db.py` dikonfigurasi dengan `PRAGMA journal_mode=WAL;` dan `check_same_thread=False` untuk memastikan performa tinggi dan keamanan konkurensi antar thread worker dan scheduler.
2. **Systemd Service Example**:
   Untuk menjalankan Aether Office sebagai background daemon di Linux/Ubuntu:
   ```ini
   [Unit]
   Description=Aether Office Persistent Runtime Engine
   After=network.target

   [Service]
   Type=simple
   User=aether
   WorkingDirectory=/opt/aether-office
   ExecStart=/usr/local/bin/uv run python cli.py office start --heartbeat 5.0
   Restart=on-failure
   RestartSec=10s
   KillSignal=SIGTERM
   TimeoutStopSec=30s

   [Install]
   WantedBy=multi-user.target
   ```
3. **Monitoring & Logging**:
   Langganan stream event `office` dapat disambungkan ke CLI streamer atau forwarded ke centralized logging (ELK / Loki) dengan memanfaatkan `EventBus.subscribe`.
