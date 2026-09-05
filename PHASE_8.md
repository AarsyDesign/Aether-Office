# PHASE 8 — OBJECTIVE-TO-OUTCOME ENGINE

## 1. Objective Architecture

Phase 8 mentransformasikan Aether Office dari sekadar **Task Execution Engine** menjadi **Objective → Plan → Execution → Evaluation → Outcome Engine**.

Pengguna (*business stakeholder*) tidak lagi perlu mengetahui detail operasional tingkat rendah seperti karyawan mana yang harus dipilih, dekomposisi task apa yang perlu dibuat, urutan dependency DAG, kapan scheduler engine melakukan detak jantung (*heartbeat tick*), atau bagaimana resource dialokasikan. Pengguna cukup mendefinisikan sebuah **Objective** bisnis tingkat tinggi beserta kriteria penerimaannya (*Acceptance Criteria*).

Arsitektur Phase 8 dirancang sebagai layer orkestrasi tingkat tinggi di atas fondasi Phase 1–7 tanpa menduplikasi scheduler, resource manager, ataupun worker pool:

```text
               USER INTERFACE / CLIENT / CLI
                             │
                             ▼
                    OBJECTIVE API LAYER
                             │
                             ▼
                   OBJECTIVE ORCHESTRATOR
                (`objective_orchestrator.py`)
                             │
       ┌─────────────────────┼─────────────────────┐
       ▼                     ▼                     ▼
OBJECTIVE MODEL      OBJECTIVE PLANNER     OUTCOME EVALUATOR
(`objectives.py`)     (`planner.py`)        (`evaluator.py`)
       │                     │                     │
       │       ┌─────────────┴─────────────┐       │
       │       ▼                           ▼       │
       │  EXECUTION PLAN            PLAN VALIDATOR │
       │  (Milestones & DAG)        (Kahn's Sort)  │
       │       │                           │       │
       └───────┼───────────────────────────┴───────┘
               ▼
     PROJECT / TASK MATERIALIZATION
     (ProjectRegistry & WorkQueue)
               │
               ▼
      OFFICE SCHEDULER & WORKFORCE
      (TaskMatcher multi-factor scoring)
               │
               ▼
      DELIVERABLES & ARTIFACTS
          (`ArtifactStore`)
               │
               ▼
    EVALUATION & REVISION LOOP
(Pass → Completed | Needs Revision → Re-queue)
```

---

## 2. Objective Lifecycle

Lifecycle sebuah `Objective` dikelola secara ketat melalui state machine eksplisit berbasis Enum `ObjectiveStatus` (`objectives.py`):

```text
                CREATED
                   ↓
                PLANNING
               ↙        ↘
        [Invalid Plan]    [Valid Plan]
             ↓                 ↓
          FAILED             READY
                               ↓
                           EXECUTING
                          ↙         ↘
               [Max Revs Exceeded]   [All Tasks Done]
                      ↓                     ↓
                    FAILED              EVALUATING
                                       ↙     ↓      ↘
                       [All Criteria Met]  [Fixable]  [Unrecoverable]
                                ↓             ↓              ↓
                            COMPLETED     EXECUTING        FAILED
                                        (Revision Loop)
```

### Matriks Transisi Status yang Diizinkan:
- `CREATED` → `PLANNING`, `CANCELLED`
- `PLANNING` → `READY`, `FAILED`, `CANCELLED`
- `READY` → `EXECUTING`, `CANCELLED`
- `EXECUTING` → `EVALUATING`, `FAILED`, `CANCELLED`
- `EVALUATING` → `COMPLETED`, `EXECUTING` (untuk siklus revisi), `FAILED`, `CANCELLED`
- `FAILED` → `PLANNING` (re-planning yang diperkenankan)
- `CANCELLED` → *Terminal*
- `COMPLETED` → *Terminal*

Transisi di luar aturan di atas akan memicu pengecualian `InvalidObjectiveStateTransition`.

---

## 3. Planning

`ObjectivePlanner` (`planner.py`) bertanggung jawab mendekomposisi sebuah `Objective` bisnis menjadi urutan tonggak pencapaian (*Milestones*) dan rincian pekerjaan teknis (*WorkTasks*).

Setiap perancangan menghasilkan struktur 4-Milestone standar:
1. **Milestone 1: Riset & Spesifikasi** (`conceptor` / `requirements_analysis`, `acceptance_criteria`)
2. **Milestone 2: Desain & Arsitektur** (`planner` / `software_architecture`, `implementation_planning`)
3. **Milestone 3: Implementasi & Konstruksi** (`developer` / `python`, `modular_coding`, `debugging`)
4. **Milestone 4: QA & Verifikasi Kualitas** (`qa` / `automated_testing`, `code_review`, `bug_diagnosis`)

Planner menghitung estimasi biaya token/finansial serta mengidentifikasi seluruh keahlian teknis (*required skills*) yang dibutuhkan.

---

## 4. ExecutionPlan

Struktur data `ExecutionPlan` membungkus cetak biru eksekusi sebelum tugas-tugas dimasukkan ke dalam antrean kerja:

```python
@dataclass
class ExecutionPlan:
    id: str
    objective_id: str
    milestones: list[Milestone]
    tasks: list[dict]
    dependencies: dict[str, list[str]]
    estimated_cost: float
    required_skills: list[str]
    is_valid: bool = True
    validation_error: Optional[str] = None
    created_at: str = ...
```

### Validasi Plan (`PlanValidator`):
Sebelum plan dieksekusi, `PlanValidator.validate_plan()` memvalidasi 7 parameter kritis:
1. **Kelengkapan Task**: Memastikan daftar task tidak kosong dan ID unik.
2. **Integritas Referensi Dependency**: Setiap dependensi harus menunjuk ke ID task yang valid.
3. **Pendeteksian Siklus (DAG)**: Menggunakan algoritma *Kahn's Topological Sort*.
4. **Kelayakan Keahlian**: Setiap task wajib memiliki kualifikasi role atau kemampuan teknis minimal.
5. **Ketersediaan Tenaga Kerja**: Menverifikasi bahwa organisasi memiliki personel aktif yang mampu menangani task tersebut.
6. **Kecukupan Anggaran**: Memastikan estimasi biaya tidak melampaui batasan anggaran objective.

Jika plan tidak valid, status Objective langsung dialihkan ke `FAILED` disertai alasan kegagalan yang jelas tanpa membuang komputasi eksekusi.

---

## 5. Dependency Graph

Hubungan ketergantungan antar task dimodelkan sebagai *Directed Acyclic Graph* (DAG).

Contoh graf dependensi:
```text
[t1_research] ──► [t2_design] ──► [t3_impl] ──► [t4_qa]
```

- Task `t1_research` tidak memiliki dependensi (in-degree = 0) dan langsung berstatus `READY`.
- Task `t2_design` terkunci hingga `t1_research` berstatus `COMPLETED`.
- Jika terjadi sirkularitas (misal: `A → B → C → A`), `PlanValidator` mendeteksi siklus melalui verifikasi in-degree simpul dan menolak plan secara instan.

---

## 6. Workforce Matching

Phase 8 menyempurnakan `TaskMatcher` (`matcher.py`) dengan formula penilaian multi-faktor:

$$\text{Match Score} = S_{\text{role}} + S_{\text{dept}} + S_{\text{caps}} + S_{\text{priority}} - P_{\text{workload}} + S_{\text{cost}} + S_{\text{history}}$$

Rincian Komponen Skor:
1. **Role Compatibility** ($+20$): Kesesuaian peran yang diinginkan (`preferred_role`).
2. **Department Match** ($+5$): Keselarasan departemen fungsional.
3. **Skill & Capability** ($+10$ per kecocokan): Kesesuaian eksak atau keterkaitan fungsional kemampuan personel.
4. **Priority Alignment** ($+5$): Penyesuaian ketersediaan personel terhadap urgensi proyek.
5. **Workload Suitability** (Penalti $-2$ per active task, $-1$ per queued task): Mencegah *bottleneck* pada personel sibuk.
6. **Cost Efficiency** ($+5$ untuk model hemat, $-3$ untuk model mahal pada task berprioritas rendah).
7. **Historical Performance** ($+1$ per 5 tugas terselesaikan, maks $+5$): Rekam jejak keberhasilan tugas sebelumnya.

---

## 7. Execution

Tahapan eksekusi Objective dijalankan secara terkoordinasi:
1. `ObjectiveOrchestrator` mematerialisasikan `Project` dan mendaftarkannya ke `ProjectRegistry`.
2. Proyek diberi penanda `metadata={"objective_id": objective.id}`.
3. Tugas-tugas diinjeksi ke `WorkQueue`.
4. `SchedulerEngine` Phase 6/7 menjadwalkan tugas sesuai kesiapan dependensi dan reservasi karyawan via `ResourceManager`.
5. Karyawan (`TaskWorker` / LLM) memproses tugas dan menghasilkan luaran serta artefak ke dalam `ArtifactStore`.
6. Selama objektif berlangsung, status proyek dijaga tetap aktif (`RUNNING`) guna mendukung siklus revisi jika evaluasi belum terpenuhi.

---

## 8. Artifact Evaluation

Sistem Phase 8 secara tegas membedakan:
- **`TASK COMPLETED`**: Pekerjaan satuan unit selesai dieksekusi oleh pekerja.
- **`OBJECTIVE ACHIEVED`**: Seluruh kriteria penerimaan bisnis telah divalidasi dan terpenuhi oleh artefak yang dihasilkan.

`OutcomeEvaluator` (`evaluator.py`) menguji luaran dan artefak terhadap `AcceptanceCriteriaSet` yang mendukung 5 tipe kriteria:
1. `CriterionType.TEXT`: Memeriksa keberadaan kata kunci atau luaran wajib pada deliverables.
2. `CriterionType.BOOLEAN`: Memeriksa indikator kebenaran kondisi bisnis.
3. `CriterionType.ARTIFACT`: Memastikan keberadaan berkas artefak (`document`, `code`, `spec`, dll.) pada `ArtifactStore`.
4. `CriterionType.TASK`: Memastikan seluruh tugas atau tugas spesifik berstatus selesai.
5. `CriterionType.TEST`: Memeriksa hasil pengujian otomatis dan nihil kegagalan regresi.

Evaluator menghasilkan 3 kemungkinan vonis:
- **`PASS`**: Seluruh kriteria terpenuhi → Objektif dan proyek ditutup sebagai `COMPLETED`.
- **`NEEDS_REVISION`**: Terdapat kriteria wajib yang belum terpenuhi namun batas revisi belum habis → Memicu siklus revisi.
- **`FAIL`**: Batas revisi terlampaui atau terjadi kegagalan fatal yang tidak dapat diperbaiki → Objektif dialihkan ke `FAILED`.

---

## 9. Revision Loop

Jika evaluasi menghasilkan `NEEDS_REVISION`, sistem memicu mekanisme koreksi mandiri (*Self-Correction Loop*):

```text
EXECUTE TASKS ──► EVALUATE ARTIFACTS ──► [NEEDS_REVISION]
       ▲                                         │
       │                                         ▼
       └────────── RUN REVISION TASK ◄─── GENERATE TARGETED TASK
```

1. Evaluator menganalisis kriteria yang gagal dan merumuskan umpan balik spesifik.
2. Evaluator menyusun tugas revisi terarah (`f"{objective.id}_rev_{n}"`) dengan prioritas tinggi (`priority=15`) dan dependensi pada tugas deliverable sebelumnya.
3. `revision_count` dinaikkan ($+1$).
4. Jika `revision_count >= max_revisions`, loop dihentikan secara aman dan objektif ditetapkan sebagai `FAILED` disertai rekam jejak kegagalan, mencegah terjadinya *infinite loop*.

---

## 10. Recovery

Objektif dan status eksekusinya dipersistensikan secara real-time ke dalam tabel SQLite `objectives`, `execution_plans`, dan `objective_evaluations` dengan mode WAL (*Write-Ahead Logging*).

Saat terjadi kegagalan proses tak terduga (*crash* / *restart*):
- Metode `ObjectiveOrchestrator.recover_in_flight_objectives()` dijalankan saat *cold-start*.
- Objektif berstatus `PLANNING` dipulihkan ke `CREATED` agar dapat direncanakan ulang secara bersih.
- Objektif berstatus `EVALUATING` dikembalikan ke `EXECUTING` agar evaluasi ulang dapat dilakukan secara deterministik terhadap artefak yang telah tersimpan di basis data.
- Objektif berstatus `EXECUTING` tetap berada pada jalurnya dan scheduler melanjutkan eksekusi tugas yang belum selesai.

---

## 11. CLI

Command Line Interface Aether Office diperkaya dengan sub-perintah `objective` berbahasa Indonesia:

```bash
# 1. Membuat objektif baru
python cli.py objective create "Sistem Presensi Karyawan Geofencing" --budget 150.0 --criteria "Penyelesaian Tugas,Dokumen Deliverable"

# 2. Menampilkan daftar objektif
python cli.py objective list

# 3. Melihat rincian objektif, kriteria, dan riwayat evaluasi
python cli.py objective show obj_a47a6e47

# 4. Menjalankan pipeline Objective -> Plan -> Execution -> Evaluation -> Outcome
python cli.py objective run obj_a47a6e47 --ticks 30

# 5. Memeriksa status akhir objektif
python cli.py objective status obj_a47a6e47

# 6. Membatalkan objektif yang sedang berjalan
python cli.py objective cancel obj_a47a6e47 --reason "Prioritas dialihkan"
```

---

## 12. Events

Phase 8 memperkenalkan 9 tipe event formal yang disiarkan melalui `EventBus`:

| Tipe Event | Deskripsi |
| :--- | :--- |
| `objective_created` | Objektif baru berhasil didaftarkan |
| `objective_planning_started` | Perencanaan dan dekomposisi milestone dimulai |
| `objective_plan_created` | Rencana eksekusi (DAG) valid terbentuk |
| `objective_plan_failed` | Perencanaan gagal akibat validasi atau batasan sumber daya |
| `objective_started` | Proyek dimaterialisasi dan eksekusi tugas dimulai |
| `objective_evaluation_started` | Evaluasi deliverable terhadap kriteria penerimaan dimulai |
| `objective_revision_requested` | Evaluasi meminta siklus koreksi dan tugas perbaikan diinjeksi |
| `objective_completed` | Seluruh kriteria penerimaan terpenuhi dengan sukses |
| `objective_failed` | Objektif gagal (anggaran habis, siklus revisi melampaui batas, dll.) |

---

## 13. Testing

Pengujian dilakukan secara menyeluruh mencakup unit test, integration test, dan simulasi skenario kegagalan:

### Cakupan Pengujian (`test_objective.py`):
1. `test_objective_lifecycle`: Validasi state machine positif dari `CREATED` hingga `COMPLETED`.
2. `test_objective_invalid_transitions`: Pencegahan transisi status ilegal.
3. `test_objective_planning_success`: Pembuatan 4 milestone dan graf DAG linier yang valid.
4. `test_plan_validation_circular_dependency`: Deteksi siklus ketergantungan tugas.
5. `test_plan_validation_invalid_dependency`: Penolakan dependensi ke task yang tidak ada.
6. `test_plan_validation_no_matching_employee`: Penolakan plan jika keahlian tidak tersedia di kantor.
7. `test_plan_validation_budget_exceeded`: Penolakan plan jika estimasi melampaui batas anggaran.
8. `test_skill_based_workforce_matching`: Penilaian kecocokan multi-faktor dan spesialisasi role.
9. `test_artifact_evaluation_pass`: Verifikasi kriteria penerimaan yang lolos evaluasi.
10. `test_artifact_evaluation_needs_revision`: Verifikasi deteksi kegagalan parsial kriteria.
11. `test_self_correction_revision_loop`: Pengujian siklus revisi end-to-end yang berhasil diperbaiki.
12. `test_max_revisions_exceeded`: Penghentian loop saat mencapai batas revisi maksimal.
13. `test_objective_restart_recovery`: Pemulihan status objektif setelah proses berhenti mendadak.
14. `test_end_to_end_objective_to_outcome`: Pembuktian seluruh pipa dari input sasaran hingga luaran sukses.
15. `test_objective_cancel`: Pembatalan objektif dan penanganan status terkait.

### Hasil Eksekusi Test Suite:
```text
============================ 214 passed in 41.65s =============================
- Existing tests (Phase 1–7): 199 passed / 0 failed
- Phase 8 tests             : 15 passed / 0 failed
- Total                     : 214 passed / 0 failed (100% PASS)
```

---

## 14. Known Limitations

1. **Single Node Execution**: Orkestrasi Phase 8 dirancang untuk arsitektur *Single-Node* dengan konkurensi multi-threading; belum mendukung klaster multi-mesin terdistribusi.
2. **Deterministic Planner Templates**: `ObjectivePlanner` saat ini memetakan sasaran ke 4 milestone arsitektur standar (Riset, Desain, Implementasi, QA). Dekomposisi berbasis LLM dinamis secara penuh dapat diaktifkan pada iterasi lanjutan setelah fondasi stabil.
3. **Synchronous Evaluation Step**: Evaluasi artefak dilakukan saat seluruh rangkaian tugas dalam milestone/proyek selesai; evaluasi perantara (*in-flight intermediate milestone gate*) belum diaktifkan secara otomatis.

---

## 15. Example Objective

Contoh deklarasi objektif bisnis lengkap:

```python
from objectives import (
    Objective,
    ObjectiveStatus,
    AcceptanceCriteriaSet,
    AcceptanceCriterion,
    CriterionType,
)
from projects import ProjectPriority

# 1. Definisikan Kriteria Penerimaan
criteria = AcceptanceCriteriaSet.from_list([
    AcceptanceCriterion(
        name="Semua Tugas Selesai",
        criterion_type=CriterionType.TASK,
        description="Semua subtask teknis harus berstatus COMPLETED",
    ),
    AcceptanceCriterion(
        name="Dokumen Deliverable Terbentuk",
        criterion_type=CriterionType.ARTIFACT,
        target_value="Dokumen",
        description="Harus terdapat dokumen deliverable di ArtifactStore",
    ),
    AcceptanceCriterion(
        name="Kata Kunci Mandatory",
        criterion_type=CriterionType.TEXT,
        target_value="ENTERPRISE_READY",
        description="Deliverable wajib memenuhi standar kesiapan enterprise",
    ),
])

# 2. Buat Objektif Bisnis
objective = Objective(
    id="obj_saas_landing",
    title="Buatkan Landing Page SaaS untuk Produk X",
    description="Landing page modern dengan fitur pricing, hero section, dan integrasi checkout",
    priority=ProjectPriority.HIGH,
    budget=100.0,
    acceptance_criteria=criteria,
    max_revisions=2,
)

# 3. Jalankan melalui ObjectiveOrchestrator
# orkestrator akan merencanakan, memvalidasi DAG, mendaftarkan proyek,
# menugaskan karyawan dengan match score tertinggi, mengevaluasi artefak,
# dan melakukan siklus revisi jika diperlukan hingga status COMPLETED tercapai.
```
