# PHASE 5 — DYNAMIC TEAM COLLABORATION & TASK DELEGATION

## 1. Objective

Phase 5 mentransformasikan Aether Office dari organisasi virtual yang sekadar mampu menyimpan dan menginstansiasi personil (*workforce foundation* Phase 4) menjadi **Collaborative AI Development Company & Virtual Office** yang sepenuhnya dinamis:
- Menganalisis kebutuhan proyek dan memecah sasaran menjadi Directed Acyclic Graph (DAG) tugas (*subtask decomposition*).
- Membentuk tim proyek lintas fungsi secara otomatis dan deterministik (*dynamic project team assembly*).
- Mendelegasikan pekerjaan ke personil terbaik dengan menyeimbangkan kecocokan peran, keahlian teknis, dan beban kerja (*workload balancing*).
- Menjalankan eksekusi tugas yang teratur sesuai prasyarat dependensi (*dependency-aware topological execution*).
- Menghasilkan deliverable berstruktur (*versioned artifacts*).
- Melakukan serah terima konteks dan deliverable secara eksplisit (*explicit artifact handoffs*).
- Menjalankan siklus peninjauan mutu antar-rekan sejawat (*peer review & revision loop*).
- Menyelenggarakan komunikasi terstruktur berbasis tugas (*structured internal discussions*).
- Mengisolasi kegagalan dan melakukan pengalihan tugas otomatis ke personil alternatif (*dynamic reassignment*).

---

## 2. Architecture Overview

Arsitektur kolaborasi Phase 5 mengintegrasikan seluruh subsistem secara terpisah (*separation of concerns*):

```text
                                USER BRIEF
                                    │
                                    ▼
                         WORKFLOW ENGINE / ORCHESTRATOR
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
  TASK DECOMPOSER              TEAM BUILDER              DEPENDENCY GRAPH
 (Breaks brief into DAG)   (Deterministic Matcher)   (Topological sort & cycle check)
       │                            │                            │
       └────────────────────────────┼────────────────────────────┘
                                    ▼
                            DELEGATION ENGINE
                                    │
                 ┌──────────────────┴──────────────────┐
                 ▼                                     ▼
        EMPLOYEE EXECUTION                     ARTIFACT CREATION
        (AgentFactory / Generic)               (Code, Copy, Design, Docs)
                 │                                     │
                 └──────────────────┬──────────────────┘
                                    ▼
                              PEER REVIEW
                      (Approve / Changes Requested)
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                     (Approved)        (Changes Needed)
                         │                     │
                         ▼                     ▼
                  ARTIFACT HANDOFF         RE-EXECUTION /
                  (To downstream)         REASSIGNMENT
                         │
                         ▼
                   NEXT IN DAG ───► PROJECT COMPLETED
```

---

## 3. Team Model (`team.py`)

Tim proyek dimodelkan dalam class `ProjectTeam`:
- **Atribut**:
  - `team_id`: Identitas unik tim (e.g. `team_60efb79d`).
  - `project_id`: ID proyek target.
  - `name`: Nama tim (e.g. `Tim Peluncuran SaaS`).
  - `objective`: Sasaran utama kerja tim.
  - `employee_ids`: Daftar ID personil yang tergabung.
  - `lead_employee_id`: Personil yang memimpin tim (e.g. PM atau Architect).
  - `status`: `active`, `completed`, atau `disbanded`.
  - `metadata`: Ekstensi fleksibel.
  - `created_at`, `updated_at`.
- **Operasi Tim**:
  - `add_employee(employee_id, role=None)`: Menambah personil & memancarkan event `team_member_added`.
  - `remove_employee(employee_id)`: Mengeluarkan personil & memancarkan event `team_member_removed`.
  - `set_lead(employee_id)`: Menetapkan ketua tim.
  - `get_active_members(org)`: Mengambil objek `Employee` aktif.
  - `get_member_roles(org)` & `get_member_capabilities(org)`.
  - `close(status="completed")`: Menutup siklus kerja tim.

### TeamBuilder Deterministik:
`TeamBuilder.build_team()` menyusun tim tanpa ketergantungan pada LLM dengan hierarki seleksi:
1. Role match terhadap peran yang diinginkan (`preferred_roles`).
2. Capability match terhadap seluruh keahlian yang dibutuhkan tugas (`required_capabilities`).
3. Department match.
4. Ketersediaan & status personil (`active` dan `available`).
5. Workload balancing (memprioritaskan personil dengan active tasks paling sedikit).
6. Penentuan ketua tim (memprioritaskan Product Manager atau Software Architect).

---

## 4. Work Task Model & State Machine (`tasks.py`)

Tugas internal dikelola oleh class `WorkTask`:
- **Atribut**:
  - `task_id`, `project_id`, `parent_task_id`, `title`, `description`.
  - `status`: Status eksekusi tugas.
  - `priority`: Angka prioritas (default 0).
  - `assigned_employee_id`, `assigned_team_id`.
  - `required_capabilities`, `preferred_role`.
  - `dependencies`: Daftar `task_id` prasyarat.
  - `artifacts`: Daftar `artifact_id` yang dihasilkan.
  - `result`: Hasil eksekusi.
  - `created_at`, `started_at`, `completed_at`.

### Status & State Transition Validation:
```text
  PENDING
     │
     ├──► READY ──► ASSIGNED ──► IN_PROGRESS ──► WAITING_REVIEW ──► COMPLETED
     │      ▲          │             │                 │
     │      │          ▼             ▼                 │ (Changes Requested)
     │      └────── FAILED ◄─────────┴─────────────────┘
     ▼
  BLOCKED ──► READY
```

- Transisi divalidasi ketat oleh `validate_work_task_transition(from_state, to_state)`. Percobaan transisi ilegal (misal langsung `PENDING` ke `COMPLETED`) akan memicu `ValueError`.

---

## 5. Subtask Decomposition (`tasks.py`)

`TaskDecomposer` menguraikan brief proyek menjadi rangkaian subtasks:
- **LLM-Based Decomposition**: Menginstruksikan LLM menyusun daftar subtask berformat JSON dengan dependensi spesifik, kebutuhan kapabilitas, dan rekomendasi peran.
- **Deterministic Heuristic Fallback**: Jika LLM offline atau terjadi kegagalan respons, template dekomposisi berbasis domain (misal: SaaS Landing Page atau Modul Web) langsung diaktifkan secara otomatis.
- **Topological Ordering & Cycle Detection**: `topological_sort()` menyusun urutan eksekusi tugas dan mendeteksi adanya ketergantungan melingkar (*circular dependency*), memicu `CircularDependencyError` jika terdeteksi.

---

## 6. Dependency-Aware Execution (`workflow.py`)

Eksekusi tugas tidak dilakukan secara acak atau langsung paralel tanpa aturan:
1. Seluruh tugas dievaluasi terhadap status dependensinya via `is_task_ready(task, all_tasks)`.
2. Tugas hanya dieksekusi bila **semua dependensi prasyaratnya berstatus `COMPLETED`**.
3. Jika masih ada tugas yang belum selesai namun tidak ada tugas yang siap (*deadlock* karena dependensi tidak terpenuhi), tugas otomatis ditandai `BLOCKED` dan workflow memancarkan event `task_blocked`.

---

## 7. Artifact System (`artifacts.py`)

Deliverable antar-karyawan dikelola oleh model `Artifact`:
- **Atribut**: `artifact_id`, `task_id`, `project_id`, `type`, `name`, `path`, `content`, `created_by`, `version`, `metadata`, `created_at`.
- **Tipe Standar**: `document`, `code`, `design`, `research`, `copy`, `report`, `data`, `test_result`.
- **Versioning**: Pemanggilan `create_new_version(new_content, updated_by)` menaikkan nomor versi (`v1 -> v2 -> v3`), mencatat riwayat pembuat dan cuplikan konten sebelumnya dalam `metadata["version_history"]`.
- **ArtifactStore**: Mengelola penyimpanan in-memory dan sinkronisasi ke tabel `artifacts` SQLite, memancarkan event `artifact_created` dan `artifact_updated`.

---

## 8. Handoff System (`handoff.py`)

Serah terima hasil kerja dilakukan secara formal melalui class `Handoff`:
- **Atribut**: `handoff_id`, `from_employee_id`, `to_employee_id`, `task_id`, `project_id`, `artifact_ids`, `message`, `status`.
- **Siklus Status**:
  ```text
  CREATED ──► RECEIVED ──► ACCEPTED
     │            │
     ▼            ▼
  REJECTED ◄──────┘
  ```
- **Context Packager**: `get_artifact_context(artifact_store)` merangkum dokumen dan kode dari artifact upstream menjadi konteks markdown yang langsung disuntikkan ke personil penerima pada tugas turunan.

---

## 9. Peer Review System (`reviews.py`)

Penjaminan mutu output kerja ditangani melalui class `Review` dan `ReviewRouter`:
- **Atribut**: `review_id`, `artifact_id`, `task_id`, `reviewer_employee_id`, `author_employee_id`, `status`, `score`, `feedback`, `required_changes`.
- **Siklus Status**:
  - `PENDING`: Menunggu peninjauan.
  - `APPROVED`: Hasil kerja disetujui (skor 1.0).
  - `CHANGES_REQUESTED`: Meminta perbaikan disertai daftar poin revisi.
  - `REJECTED`: Ditolak.
- **ReviewRouter**: Memasangkan pembuat artifact dengan peninjau yang kompeten:
  - Developer (Backend / Frontend) → QA Engineer (`automated_testing`, `code_review`).
  - Copywriter → Content / Marketing Strategist / PM.
  - UI Designer → UX Designer / PM.
  - SEO Specialist → Marketing Strategist / PM.

---

## 10. Structured Internal Discussion (`discussion.py`)

Komunikasi internal berfokus pada penyelesaian tugas tanpa percakapan bebas tak terarah:
- **Tipe Pesan Terstruktur**:
  - `QUESTION`: Pertanyaan teknis/spesifikasi.
  - `ANSWER`: Jawaban klarifikasi.
  - `REQUEST`: Permintaan bantuan atau input.
  - `CLARIFICATION`: Penjelasan batasan.
  - `DECISION`: Keputusan arsitektur/desain final.
  - `WARNING`: Peringatan risiko teknis.
  - `HANDOFF`: Catatan serah terima.
  - `REVIEW_FEEDBACK`: Catatan peninjauan rekan sejawat.
- Setiap pesan memancarkan event `discussion_message` pada EventBus.

---

## 11. Delegation Engine & Workload Tracking (`delegation.py`, `workforce.py`)

`DelegationEngine` bertindak sebagai eksekutor operasional tugas:
1. Mencari personil terbaik via `TaskMatcher`.
2. Menghitung penalti beban kerja (`-2` poin per `active_tasks`).
3. Menginstansiasi agen via `AgentFactory`.
4. Mengeksekusi instruksi, menyimpan artifact deliverable, dan menjalankan peer review.
5. Memperbarui metrik personil (`active_tasks` berkurang, `completed_tasks` bertambah).

---

## 12. Dynamic Reassignment & Failure Handling (`delegation.py`)

Jika eksekusi tugas mengalami kegagalan:
- Kegagalan diklasifikasikan ke dalam kategori: `EXECUTION_ERROR`, `VALIDATION_ERROR`, `REVIEW_REJECTED`, `DEPENDENCY_ERROR`, `NO_EMPLOYEE_AVAILABLE`, `TIMEOUT`.
- `DelegationEngine` mengisolasi personil yang gagal, mencari personil alternatif yang memiliki kapabilitas setara dari kandidat tim atau organisasi, mengalihkan penugasan (*reassignment*), dan memancarkan event `employee_reassigned`.

---

## 13. Collaborative Workflow State Machine (`workflow.py`)

`WorkOrchestrator` memandu alur kerja menyeluruh:
- **State Workflow**:
  - `PENDING`
  - `TASK_ANALYZED`
  - `TEAM_FORMED`
  - `TASKS_DELEGATED`
  - `EXECUTION`
  - `REVIEW`
  - `HANDOFF`
  - `PROJECT_COMPLETE`
  - `BLOCKED`
  - `FAILED`
  - `ESCALATED`

---

## 14. Event System & Replay (`events.py`)

Phase 5 menambahkan 14 event constants baru:
- `EVENT_TEAM_CREATED = "team_created"`
- `EVENT_TEAM_MEMBER_ADDED = "team_member_added"`
- `EVENT_TEAM_MEMBER_REMOVED = "team_member_removed"`
- `EVENT_TASK_DECOMPOSED = "task_decomposed"`
- `EVENT_TASK_BLOCKED = "task_blocked"`
- `EVENT_ARTIFACT_HANDOFF = "artifact_handoff"`
- `EVENT_REVIEW_REQUESTED = "review_requested"`
- `EVENT_REVIEW_COMPLETED = "review_completed"`
- `EVENT_DISCUSSION_STARTED = "discussion_started"`
- `EVENT_DISCUSSION_MESSAGE = "discussion_message"`
- `EVENT_DELEGATION_COMPLETED = "delegation_completed"`
- `EVENT_WORKFLOW_COMPLETED = "workflow_completed"`
- `EVENT_WORKFLOW_FAILED = "workflow_failed"`
- `EVENT_EMPLOYEE_REASSIGNED = "employee_reassigned"`

Seluruh event dapat dicatat di SQLite dan diputar ulang (*replay*) tanpa distorsi.

---

## 15. Database Schema & Persistence (`db.py`)

SQLite (`tasks.db`) diperluas dengan 9 tabel relasional baru:
1. `teams`: `id`, `project_id`, `name`, `objective`, `lead_employee_id`, `status`, `metadata`, `created_at`, `updated_at`.
2. `team_members`: `team_id`, `employee_id`, `role`, `joined_at`, `PRIMARY KEY (team_id, employee_id)`.
3. `work_tasks`: `task_id`, `project_id`, `parent_task_id`, `title`, `description`, `status`, `priority`, `assigned_employee_id`, `assigned_team_id`, `required_capabilities`, `preferred_role`, `dependencies`, `artifacts`, `result`, `created_at`, `started_at`, `completed_at`, `metadata`.
4. `task_dependencies`: `task_id`, `depends_on_task_id`, `PRIMARY KEY (task_id, depends_on_task_id)`.
5. `artifacts`: `artifact_id`, `task_id`, `project_id`, `type`, `name`, `path`, `content`, `created_by`, `version`, `metadata`, `created_at`.
6. `handoffs`: `handoff_id`, `from_employee_id`, `to_employee_id`, `task_id`, `project_id`, `artifact_ids`, `message`, `status`, `created_at`, `updated_at`.
7. `reviews`: `review_id`, `artifact_id`, `task_id`, `reviewer_employee_id`, `author_employee_id`, `status`, `score`, `feedback`, `required_changes`, `created_at`, `updated_at`.
8. `discussions`: `discussion_id`, `project_id`, `task_id`, `topic`, `status`, `created_at`, `updated_at`.
9. `discussion_messages`: `message_id`, `discussion_id`, `sender_employee_id`, `recipient_employee_id`, `task_id`, `message_type`, `content`, `created_at`.

---

## 16. CLI Commands (`cli.py`)

Perintah inspeksi dan eksekusi kolaboratif Phase 5:
```bash
# Inspeksi tim proyek
python cli.py teams
python cli.py team <team_id>

# Inspeksi daftar tugas kerja
python cli.py tasks
python cli.py tasks --project <project_id>
python cli.py task <task_id>

# Inspeksi hasil kerja dan artifact
python cli.py artifacts
python cli.py artifacts --project <project_id>

# Inspeksi peer review
python cli.py reviews
python cli.py reviews --project <project_id>

# Status workflow
python cli.py workflow <project_id>

# Menjalankan workflow kolaborasi
python cli.py workflow-run <project_id> --brief "Buat landing page SaaS akuntansi"
```

---

## 17. Tests & Verification (`test_collaboration.py`)

Seluruh rangkaian pengujian (Phase 1–5) lulus 100%:
- **158 tests lulus**:
  - `test_reliability.py`: **79/79 passed** (Phase 1, 1.5, 2)
  - `test_streaming.py`: **33/33 passed** (Phase 3)
  - `test_workforce.py`: **26/26 passed** (Phase 4)
  - `test_collaboration.py`: **20/20 passed** (Phase 5)
- **Cakupan Pengujian Phase 5**:
  - Pembuatan tim, penambahan anggota, penghapusan anggota, dan penunjukan ketua tim.
  - State machine validasi transisi status tugas.
  - Topological sort dan deteksi circular dependency.
  - Penalti workload pada TaskMatcher.
  - Pembuatan artifact dan versioning beruntun.
  - Siklus handoff (terima, tolak, ekstraksi konteks).
  - Siklus peer review (approve, perbaikan, router pairing).
  - Diskusi terstruktur antar-personil.
  - Reassignment otomatis ketika personil pertama gagal.
  - **Simulasi Integrasi End-to-End**: Skenario "Create SaaS Landing Page" dengan 6 personil Indonesia (Panji Nugroho, Maya Anggraini, Citra Dewi, Bagas Aditya, Surya Pratama, Ratna Sari), dekomposisi tugas, pembentukan tim dinamis, eksekusi topological, pembuatan artifact, serah terima handoff, peninjauan peer review, hingga status `PROJECT_COMPLETE` tanpa hardcoded ID.

---

## 18. Known Limitations

- Subtask decomposition otomatis menggunakan template heuristik terverifikasi jika LLM tidak dikonfigurasi dengan API key aktif.
- Transisi handoff dan review saat ini beroperasi pada proses sinkronous deterministik.

---

## 19. Phase 6 Recommendation

Dengan tuntasnya kolaborasi tim dan delegasi tugas di Phase 5, fondasi siap melangkah ke **Phase 6 — Autonomous Office Operations & Multi-Project Scheduling**:
1. **Multi-Project Parallel Scheduling**: Orkestrasi beberapa proyek secara serentak dengan alokasi personil bersama (*shared workforce pool*) dan queue priority.
2. **Dynamic Project Budgeting & Token Economy**: Pelacakan biaya komputasi, penggunaan token LLM, dan efisiensi biaya per tim proyek.
3. **Interactive Workspace Web Dashboard**: Visualisasi real-time alur kerja kanban tim, linimasa dependensi tugas, dan pratinjau artifact secara grafis.
