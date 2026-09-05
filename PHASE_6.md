# PHASE 6 — AUTONOMOUS OFFICE OPERATIONS & MULTI-PROJECT SCHEDULING

## 1. Objective

Phase 6 mentransformasikan Aether Office dari eksekusi alur kerja kolaboratif berbasis satu proyek (*single-project workflow* Phase 5) menjadi **Sistem Operasional Kantor Otonom Multi-Proyek (*Autonomous Office Operations & Multi-Project Scheduling*)**.

Sistem kini mampu mengoperasikan banyak proyek secara simultan (*multi-project concurrent scheduling*) dengan memanfaatkan satu kesatuan *shared workforce pool*, mencegah *over-allocation*, menghitung urgensi tenggat waktu (*deadline urgency*), menegakkan keadilan alokasi sumber daya (*fair resource allocation & starvation prevention*), mengunci penugasan secara atomik (*atomic employee reservation lock*), melacak penggunaan token/biaya komputasi (*cost & usage tracking*), menerapkan batas anggaran (*budget enforcement & warning thresholds*), serta memulihkan kegagalan pekerja secara otomatis (*self-healing failure recovery*).

---

## 2. Architecture Overview

Arsitektur operasional multi-proyek Phase 6 dibangun di atas pemisahan tanggung jawab yang modular dan deterministik:

```text
USER / MULTIPLE INITIATIVES
  │
  ├── Proyek A (CRITICAL — SaaS Landing Page)
  ├── Proyek B (HIGH — Aplikasi Mobile)
  ├── Proyek C (NORMAL — Kampanye SEO)
  └── Proyek D (LOW — Riset Internal)
          │
          ▼
   OFFICE ORCHESTRATOR (`office.py`)
          │
   ┌──────┴────────────────────────┐
   ↓                               ↓
PROJECT REGISTRY & QUEUE    RESOURCE MANAGER (`resources.py`)
(`projects.py`, `office_queue.py`)          │
   │                               ↓
   ↓                        WORKFORCE POOL (Shared Employees)
GLOBAL WORK QUEUE                  │
(Ready, Blocked, Running)          │
   │                               │
   └───────────────┬───────────────┘
                   ↓
         SCHEDULER ENGINE (`scheduler.py`)
                   │
         ┌─────────┴─────────┐
         │ (Deterministic    │
         │  Matching & Lock) │
         ▼                   ▼
    USAGE TRACKER      BUDGET MANAGER
    (`usage.py`)       (`budget.py`)
         │                   │
         └─────────┬─────────┘
                   ↓
         DISPATCH / EXECUTION
                   │
                   ▼
         EMPLOYEE AGENTS (`agents/generic.py`)
                   │
                   ▼
         ARTIFACTS & REVIEWS
                   │
                   ▼
         RELEASE LOCK & RE-TICK
```

---

## 3. Project Registry (`projects.py`)

Model data `Project` mengelola siklus hidup proyek secara independen dengan struktur:
- `project_id`: Identitas unik proyek.
- `name`: Nama proyek (e.g. `AI Landing Page`).
- `description`: Deskripsi objektif pekerjaan.
- `status`: Enum status operasional:
  - `PLANNED`: Terdaftar, belum aktif.
  - `READY`: Siap dijadwalkan ke antrean eksekusi.
  - `RUNNING`: Sedang aktif berjalan dan menerima alokasi sumber daya.
  - `PAUSED`: Operasional dijeda sementara.
  - `BLOCKED`: Terhenti karena anggaran habis atau hambatan fatal.
  - `COMPLETED`: Seluruh tugas proyek selesai.
  - `FAILED`: Gagal memenuhi kriteria akhir.
  - `CANCELLED`: Dibatalkan oleh pengguna.
- `priority`: Enum prioritas dasar: `CRITICAL` (100.0), `HIGH` (50.0), `NORMAL` (20.0), `LOW` (5.0).
- `deadline`: String ISO-8601 batas waktu penyelesaian.
- `owner_employee_id`: Penanggung jawab proyek.
- `team_id`: Tim proyek terkait.
- `budget`: Pagu dana anggaran komputasi dalam USD.
- `spent`: Total dana komputasi yang telah terpakai.
- `metadata`: Metadata arbitrer terstruktur JSON.

`ProjectRegistry` menyinkronkan status proyek secara langsung ke basis data SQLite dan menerbitkan *event lifecycle* ke `EventBus`.

---

## 4. Project Queue (`office_queue.py`)

`ProjectQueue` bertanggung jawab menentukan urutan prioritas proyek yang berhak mendapatkan alokasi karyawan terlebih dahulu.

### Formula Pemeringkatan Proyek:
$$\text{ProjectScore} = \text{BasePriorityWeight} + \text{DeadlineUrgency} + \text{StarvationBonus}$$

- Proyek non-aktif (`PAUSED`, `BLOCKED`, `COMPLETED`, `FAILED`) langsung diberi skor `-1000.0` sehingga tidak akan menyerap sumber daya kantor.
- Pemeringkatan bersifat **100% deterministik** menggunakan *tuple key* `(-score, project_id)`. Tidak ada LLM atau fungsi acak tak berdasar yang digunakan untuk membuat keputusan penjadwalan.

---

## 5. Global Work Queue (`office_queue.py`)

`WorkQueue` mengelola antrean tugas global dari seluruh proyek aktif dan mempartisinya ke dalam 4 kategori:
1. **Ready Tasks**: Tugas yang proyeknya aktif (`READY`/`RUNNING`), status tugas `PENDING` atau `READY`, dan **seluruh dependensi prasyaratnya telah selesai (`TASK_COMPLETED`)**.
2. **Blocked Tasks**: Tugas yang dependensi prasyaratnya belum terpenuhi atau proyeknya berstatus `PAUSED`/`BLOCKED`.
3. **Running Tasks**: Tugas yang sedang dikunci reservasi dan dijalankan karyawan (`TASK_IN_PROGRESS` atau `ASSIGNED`).
4. **Waiting Review / Completed Tasks**: Tugas dalam peninjauan mutu atau telah selesai.

---

## 6. Resource Manager & Workforce Capacity (`resources.py`)

`ResourceManager` memantau ketersediaan seluruh personil kantor secara terpusat:
- Memantau ketersediaan: `available`, `busy`, `offline`.
- Mengetahui beban kerja aktif (*active workload*) tiap personil.
- Menghitung kapasitas workforce kantor (*office-level workforce capacity*):
  - `total_employees`: Jumlah total karyawan terdaftar.
  - `available`: Karyawan aktif yang tidak terkunci dan siap menerima tugas.
  - `busy`: Karyawan yang sedang memegang tugas aktif.
  - `offline`: Karyawan dalam status non-aktif/offline.
  - `utilization`: Rasio beban kerja $\frac{\text{busy}}{\text{total}}$.
- Menghitung profil utilisasi per karyawan (`get_employee_utilization`).

---

## 7. Employee Resource Lock (`resources.py` & `db.py`)

Untuk mencegah terjadinya *double assignment* atau *race condition* ketika beberapa proyek meminta karyawan yang sama secara bersamaan, Phase 6 menerapkan **Atomic Employee Reservation Lock**:
- Menggunakan tabel SQLite `employee_reservations` dengan *primary key* pada `employee_id`.
- Metode `reserve_employee(employee_id, task_id, project_id)` mengunci karyawan secara atomik. Jika ada entitas lain yang mencoba memesan karyawan yang sama, basis data akan menolak dengan `IntegrityError` dan metode mengembalikan `False`.
- Karyawan otomatis diperbarui statusnya menjadi `availability = 'busy'` dan `live_state = 'WORKING'`.
- Setelah tugas selesai atau gagal, metode `release_employee(employee_id)` menghapus kunci reservasi dan mengembalikan status karyawan menjadi `availability = 'available'` dan `live_state = 'IDLE'`.

---

## 8. Scheduler Engine (`scheduler.py`)

`SchedulerEngine` merupakan jantung operasional Phase 6 yang mengeksekusi siklus penjadwalan melalui metode:
```python
scheduler.tick(execute=True)
```

### Alur Siklus Tick:
1. Menerbitkan `EVENT_SCHEDULE_TICK` untuk observabilitas.
2. Memindai seluruh tugas siap (*ready tasks*) lintas proyek aktif.
3. Memeriksa kecukupan anggaran proyek (*budget check*). Jika proyek kehabisan anggaran, proyek diubah otomatis menjadi `BLOCKED`.
4. Mengumpulkan pool karyawan yang sedang tersedia (*available workforce pool*).
5. Menjalankan `TaskMatcher` deterministik untuk mencocokkan tugas dengan karyawan terbaik berdasarkan keahlian teknis (*capabilities*), peran (*role*), dan departemen.
6. Melakukan reservasi atomik (*atomic lock*) pada karyawan terpilih.
7. Memperbarui status tugas ke `IN_PROGRESS` dan mencatat penugasan.
8. Menjalankan eksekusi tugas (melalui *agent worker*, alur delegasi, atau simulasi deterministik).
9. Mencatat konsumsi token dan estimasi biaya komputasi ke `UsageTracker` dan `BudgetManager`.
10. Menandai tugas `COMPLETED` dan melepaskan reservasi karyawan (*release employee lock*).
11. Menjalankan *starvation prevention tick* untuk memperbarui kompensasi proyek yang belum terlayani.
12. Menyimpan rekam jejak eksekusi scheduler (*scheduler run*) ke basis data SQLite.

---

## 9. Task & Project Priority Scoring

Skor gabungan penentuan urutan tugas:
$$\text{TaskCompositeScore} = \text{ProjectScore} + (\text{TaskPriority} \times 10.0)$$

Bobot prioritas proyek:
- `CRITICAL`: 100 poin
- `HIGH`: 50 poin
- `NORMAL`: 20 poin
- `LOW`: 5 poin

Penugasan selalu mendahulukan tugas berbobot tertinggi dengan pemecah seri (*tie-breaking*) alfabetis `task_id` yang konsisten.

---

## 10. Fair Resource Allocation & Starvation Prevention

Untuk mencegah proyek berprioritas rendah (`LOW`) mengalami *starvation* (tidak pernah memperoleh karyawan karena dominasi proyek `CRITICAL`/`HIGH`):
- Setiap kali satu siklus `tick()` selesai, proyek aktif yang memiliki tugas siap namun **tidak terlayani** (*unserved*) akan mendapatkan kenaikan `starvation_counter` (+1).
- Setiap tick starvation memberikan bonus skor deterministik:
  $$\text{StarvationBonus} = \min(\text{starvation\_counter} \times 10.0, 100.0)$$
- Ketika proyek yang lapar akhirnya terlayani dan memperoleh giliran eksekusi, `starvation_counter` langsung di-reset kembali ke `0`.

---

## 11. Deadline Urgency

Tenggat waktu diperhitungkan secara deterministik tanpa campur tangan LLM:
- Deadline telah terlampaui ($\le 0$ jam tersisa): **+50.0 poin** (urgensi darurat maksimal).
- $\le 24$ jam tersisa: **+40.0 poin**.
- $\le 72$ jam tersisa: **+25.0 poin**.
- $\le 168$ jam tersisa (1 minggu): **+10.0 poin**.
- Tugas tanpa deadline tetap valid dengan skor urgensi 0.0.

---

## 12. Multi-Project Execution

Scheduler Phase 6 mengoperasikan banyak proyek secara simultan di atas satu *shared workforce pool*:
- Tidak ada sekat atau pembatasan kaku per proyek (*no isolated workforce*).
- Karyawan spesialis (misal `backend_developer`, `qa_engineer`, atau `software_architect`) dapat mengerjakan tugas Proyek A pada Tick 1, lalu setelah selesai dan dilepas kuncinya, dapat mengerjakan tugas Proyek B pada Tick 2.
- Tidak terjadi tumpang tindih penugasan (*zero double reservation*).

---

## 13. Soft Preemption Policy

Sistem menerapkan kebijakan *soft preemption*:
- Karyawan yang sedang aktif mengeksekusi tugas tidak diinterupsi secara kasar (*no hard preemption*) demi mencegah *state corruption* dan hilangnya progres kerja.
- Namun jika karyawan baru berada di tahap antrean reservasi tugas berprioritas rendah dan belum aktif beroperasi, tugas berkategori `CRITICAL` berhak dialokasikan terlebih dahulu pada evaluasi scheduler berikutnya.

---

## 14. Token Usage Tracking (`usage.py`)

`UsageTracker` mencatat konsumsi sumber daya komputasi secara *provider-agnostic*:
- Pelacakan per: `organization_id`, `project_id`, `task_id`, `employee_id`, `model`.
- Metrik tersimpan:
  - `input_tokens`
  - `output_tokens`
  - `total_tokens`
  - `requests`
  - `estimated_cost`
- Menyediakan fungsi agregasi tingkat proyek (`get_project_usage`) dan tingkat kantor (`get_total_usage`).

---

## 15. Model Pricing Configuration (`budget.py`)

Biaya komputasi dihitung berdasarkan tabel konfigurasi harga standar (per 1.000 token):
```python
DEFAULT_MODEL_PRICING = {
    "default": {"input_cost_per_1k": 0.0015, "output_cost_per_1k": 0.0020},
    "mock-model": {"input_cost_per_1k": 0.0010, "output_cost_per_1k": 0.0020},
    "gpt-4o": {"input_cost_per_1k": 0.0050, "output_cost_per_1k": 0.0150},
    "gpt-4o-mini": {"input_cost_per_1k": 0.00015, "output_cost_per_1k": 0.0006},
    "claude-3-5-sonnet": {"input_cost_per_1k": 0.0030, "output_cost_per_1k": 0.0150},
    "gemini-1.5-pro": {"input_cost_per_1k": 0.00125, "output_cost_per_1k": 0.0050},
    "gemini-1.5-flash": {"input_cost_per_1k": 0.000075, "output_cost_per_1k": 0.0003},
}
```
Formula estimasi biaya:
$$\text{Cost} = \left(\frac{\text{input\_tokens}}{1000} \times \text{input\_rate}\right) + \left(\frac{\text{output\_tokens}}{1000} \times \text{output\_rate}\right)$$

---

## 16. Project Budget & Threshold Enforcement (`budget.py`)

Setiap proyek dapat memiliki pagu anggaran finansial:
- Memantau `budget`, `spent`, dan `remaining`.
- Ambang batas peringatan (*warning thresholds*):
  - Terpakai $\ge 80\%$: Menerbitkan `EVENT_BUDGET_WARNING` (Peringatan 80%).
  - Terpakai $\ge 90\%$: Menerbitkan `EVENT_BUDGET_WARNING` (Peringatan 90%).
  - Terpakai $\ge 100\%$ ($spent \ge budget$): Menerbitkan `EVENT_BUDGET_EXCEEDED` dan proyek langsung diubah statusnya menjadi `BLOCKED`.
- Tugas pada proyek `BLOCKED` tidak akan dialokasikan sumber daya baru hingga anggaran ditambah.

---

## 17. Cost-Aware Scheduling

Scheduler dapat mempertimbangkan faktor biaya secara deterministik:
- Untuk proyek dengan prioritas `LOW`, karyawan dengan konfigurasi model berbiaya murah (*cheaper model*) mendapatkan bonus skor kecocokan (+10 poin).
- Untuk proyek dengan prioritas `CRITICAL`, kualitas dan keahlian spesifik karyawan tetap menjadi prioritas utama.

---

## 18. Office Operational State (`office.py`)

Model `OfficeState` menyediakan *snapshot* real-time kondisi kantor Aether Office:
```python
state = orch.office_status()
```
Berisi data metrik:
- `active_projects`, `paused_projects`, `blocked_projects`, `completed_projects`
- `total_employees`, `available_employees`, `busy_employees`, `offline_employees`
- `queued_tasks`, `running_tasks`, `completed_tasks`, `failed_tasks`
- `total_token_usage`, `total_cost`, `timestamp`

Setiap perubahan status memancarkan `EVENT_OFFICE_STATE_CHANGED`.

---

## 19. Event System Extensions (`events.py`)

19 event baru telah ditambahkan ke `events.py` dan terintegrasi penuh ke alur replay EventBus:
- `project_created`, `project_started`, `project_paused`, `project_resumed`, `project_completed`, `project_failed`
- `task_queued`, `task_dequeued`, `task_scheduled`, `task_preempted`
- `employee_reserved`, `employee_released`, `employee_overloaded`
- `schedule_tick`, `resource_conflict`
- `usage_recorded`, `budget_warning`, `budget_exceeded`
- `office_state_changed`

Semua event bersifat *replayable* dan tersimpan rapi pada tabel SQLite `events`.

---

## 20. Database Migrations (`db.py`)

Tabel baru yang ditambahkan di Phase 6:
- `project_queue`: Pelacakan bobot prioritas, durasi tunggu, dan *starvation counter*.
- `employee_reservations`: Penguncian atomik penugasan karyawan (*atomic reservation lock*).
- `usage_records`: Catatan konsumsi token dan estimasi biaya per proyek, tugas, model, dan karyawan.
- `project_budgets`: Pagu anggaran, pengeluaran kumulatif, dan status pemblokiran proyek.
- `scheduler_runs`: Audit rekam jejak tiap siklus penjadwalan dan metrik performanya.

Migrasi kolom pada tabel `projects`:
- `description`, `priority`, `deadline`, `owner_employee_id`, `team_id`, `budget`, `spent`, `started_at`, `completed_at`, `metadata`.

Seluruh migrasi mempertahankan kompatibilitas penuh dengan tabel Phase 1–5.

---

## 21. CLI Observability (`cli.py`)

Subcommand baru yang tersedia:
```bash
# Daftar seluruh proyek
python cli.py projects

# Rincian proyek tertentu
python cli.py project <id>

# Pantau antrean proyek dan tugas
python cli.py queue

# Pantau jadwal dan reservasi aktif
python cli.py schedule

# Pantau kapasitas workforce kantor
python cli.py resources

# Laporan token usage
python cli.py usage

# Laporan biaya komputasi & anggaran
python cli.py costs

# Dashboard status operasional kantor
python cli.py office

# Jalankan 1 siklus scheduler
python cli.py scheduler-tick [--execute]

# Jeda & lanjutkan proyek
python cli.py project-pause <id>
python cli.py project-resume <id>
```

Tampilan CLI menggunakan tata bahasa Indonesia yang sopan dan representasi visual yang jelas (indikator status, tabel, dan format angka).

---

## 22. Failure Handling & Self-Healing

Jika terjadi kegagalan karyawan saat eksekusi tugas:
1. `SchedulerEngine` menangkap exception secara terisolasi.
2. Reservasi karyawan langsung dilepaskan (`release_employee`), mengembalikan karyawan ke status `available` dan `IDLE`.
3. Tugas ditandai `TASK_FAILED`.
4. Mekanisme *automatic recovery* langsung me-requeue tugas kembali ke status `TASK_READY`.
5. Pada tick scheduler berikutnya, tugas yang gagal akan dijadwalkan ulang secara deterministik kepada kandidat karyawan lain yang memenuhi syarat.

---

## 23. Determinism Guarantees

- **No Random Seeds**: Seluruh pemeringkatan kandidat, seleksi proyek, dan pemecah seri (*tie-breaking*) menggunakan aturan deterministik murni.
- Proyek dengan skor sama diurutkan alfabetis berdasarkan `project_id`.
- Tugas dengan skor sama diurutkan alfabetis berdasarkan `task_id`.
- Kandidat karyawan dengan skor kecocokan sama diurutkan berdasarkan beban terendah, jumlah kapabilitas, lalu `employee_id`.

---

## 24. Multi-Project Simulation (5 Proyek, 20 Karyawan, 50 Tugas)

Pengujian integrasi multi-proyek berhasil memvalidasi:
- **5 Proyek Aktif**:
  - Proyek A: SaaS Landing Page (`CRITICAL`, budget: $20)
  - Proyek B: Mobile App (`HIGH`, budget: $30)
  - Proyek C: SEO Campaign (`NORMAL`, budget: $15)
  - Proyek D: Product Research (`NORMAL`, budget: $10)
  - Proyek E: Internal Dashboard (`LOW`, budget: $10)
- **20 Karyawan Indonesia** dari berbagai peran dan departemen.
- **50 Tugas** dengan rantai dependensi antar-tugas.
- Hasil: Seluruh 50 tugas tuntas diselesaikan (`50 completed, 0 running, 0 queued`), kapasitas workforce kembali 100% `available` (20/20), dan tidak ada reservasi yang tertinggal.

---

## 25. Load Test Simulation (10 Proyek, 50 Karyawan, 100 Tugas)

Pengujian beban deterministik berhasil memvalidasi:
- **10 Proyek Simultan** (`CRITICAL`, `HIGH`, `NORMAL`).
- **50 Karyawan**.
- **100 Tugas**.
- Scheduler mampu mengeksekusi, mengunci, menyelesaikan, dan mencatat metrik tanpa ada korupsi status basis data atau *memory leak*.
- Seluruh 10 proyek berhasil mencapai status `COMPLETED`.
- Waktu eksekusi rata-rata per tick berada pada rentang $< 1.0\text{ ms}$ untuk evaluasi murni.

---

## 26. Limitations

- **Single-Node Execution**: Scheduler Phase 6 dirancang untuk satu instans Aether Office terpusat (menggunakan SQLite WAL mode). Belum mendukung arsitektur multi-node cluster terdistribusi (seperti Celery, Ray, atau Kubernetes).
- **Synchronous Ticks**: Penjadwalan dijalankan per tick (baik berbasis loop interval ataupun pemicu eksplisit), bukan model fully-asynchronous actor loop.
- **No Dynamic Currency Conversion**: Estimasi biaya saat ini mengasumsikan mata uang USD ($).

---

## 27. Phase 7 Recommendation

Rekomendasi pengembangan untuk Phase 7+:
1. **Interactive Real-Time Web Dashboard**: Membangun antarmuka visual (React/Vite) yang mengonsumsi `OfficeState`, status antrean, grafik anggaran, dan streaming log secara real-time via WebSocket/SSE.
2. **Dynamic Cron Schedules & Heartbeat Loop**: Mengintegrasikan scheduler background daemon yang berjalan terus-menerus dengan interval tick dinamis yang dapat diatur via konfigurasi.
3. **Adaptive Workforce Scaling**: Rekomendasi otomatis penambahan peran/karyawan baru ketika kapasitas utilisasi kantor mencapai $> 90\%$ dalam durasi tertentu.
