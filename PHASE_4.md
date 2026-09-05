# PHASE 4 — AI OFFICE ORGANIZATION & WORKFORCE

## 1. Workforce Vision

Aether Office kini bertransformasi dari sekadar pipeline sekuensial 4-agent kaku (`PM → Conceptor → Developer → QA`) menjadi ekosistem **AI Development Company & Virtual Office**. Di Phase 4, agent diperlakukan sebagai **employee** profesional yang beroperasi di dalam wadah organisasi modern dengan spesialisasi peran (*role*), pembagian departemen (*department*), keahlian (*capabilities*), karakter komunikasi (*personality*), pemetaan model (*model assignment*), serta siklus status (*availability* dan *active/inactive*).

Arsitektur ini **tidak hardcoded** dan dirancang untuk menampung puluhan hingga ratusan karyawan AI lintas divisi tanpa perlu membuat class Python baru untuk setiap peran yang diperkenalkan.

---

## 2. Organization Model

Konsep organisasi didefinisikan secara hierarkis dan terpisah:

```text
                    AETHER OFFICE (Kantor Virtual)
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
     Engineering               Product                Marketing
    (Department)            (Department)            (Department)
          │                       │                       │
     ┌────┴────┐             ┌────┴────┐             ┌────┴────┐
     │  ROLES  │             │  ROLES  │             │  ROLES  │
     ├─────────┤             ├─────────┤             ├─────────┤
     │ backend │             │ pm      │             │ copy    │
     │ qa      │             │ concept │             │ seo     │
     │ devops  │             │ research│             │ social  │
     └────┬────┘             └────┬────┘             └────┬────┘
          │                       │                       │
     EMPLOYEES               EMPLOYEES               EMPLOYEES
     - Eko Prasetyo (dev_001)- Budi Santoso (pm_001) - Laras Wulandari (copy_001)
     - Bayu Setiawan (dev_002)- Dewi Lestari (cpt_001)- Maya Anggraini (copy_002)
```

### Prinsip Pemisahan Ketat & Budaya Kerja Indonesia:
- **Role ≠ Employee**: Role adalah deskripsi fungsi kerja; Employee adalah personil spesifik yang mengemban amanah role tersebut.
- **Department ≠ Role**: Department adalah divisi organisasi; Role adalah jabatan kerja di dalam departemen.
- **Employee ≠ Model**: Employee dapat menggunakan model AI mana pun melalui resolusi hierarkis.
- **Nuansa & Etika Kantor Indonesia**: Memadukan efisiensi AI kelas dunia dengan etos kerja Indonesia—menjunjung tinggi asas *gotong royong*, musyawarah mufakat, tata krama/sopan santun yang lugas dan solutif, serta saling mendukung demi kesuksesan bersama.

---

## 3. Department Model

Departemen dikelola oleh `DepartmentRegistry` dengan dukungan dict-like access:
- **Atribut**: `department_id`, `name`, `description`, `default_model`, `agent_ids` (dan alias `employee_ids`).
- **Seed Departments**:
  1. `engineering`: Software development, architecture, QA, infrastructure
  2. `product`: Product planning, requirements, user experience
  3. `design`: UI/UX design, visual identity, design systems
  4. `marketing`: Growth, copy, content, and communications
  5. `research`: Data analytics, market research, and feasibility
  6. `operations`: Project coordination and documentation
  7. `business`: Sales, business development, and finance
  8. `support`: Customer support and community management

---

## 4. Role Catalog

`RoleCatalog` mengelola katalog jabatan yang dapat diperluas dinamis pada runtime tanpa perubahan kode program:
- **Atribut**: `role_id`, `name`, `department`, `description`, `capabilities`, `default_model`, `metadata`.
- **Seed Roles**: Terdiri atas **37 seed roles** yang mencakup 8 divisi organisasi (Product Manager, Backend Developer, Frontend Developer, UI Designer, UX Designer, Copywriter, SEO Specialist, DevOps Engineer, QA Engineer, Data Analyst, dsb.).

---

## 5. Employee Model

Setiap karyawan virtual dimodelkan dalam class `Employee`:

```python
@dataclass
class Employee:
    employee_id: str                          # Identitas unik, e.g. "developer_001"
    name: str                                 # Nama karyawan, e.g. "Eko Prasetyo"
    role: str                                 # Role ID, e.g. "backend_developer"
    department: str = "engineering"           # Department ID
    capabilities: list[str]                   # Kumpulan keahlian
    personality: dict                         # Traits, style komunikasi & keputusan
    model: dict                               # Konfigurasi LLM khusus
    status: str = "active"                    # "active" | "inactive"
    availability: str = "available"           # "available" | "busy" | "offline"
    live_state: str = "IDLE"                  # State eksekusi dari Phase 3
    metadata: dict                            # Ekstensi fleksibel
```

Mendukung pendaftaran banyak karyawan dengan peran yang sama (misal `copywriter_001` "Laras Wulandari" dan `copywriter_002` "Maya Anggraini") dengan kepribadian dan keahlian berbeda.

---

## 6. Capability System

Capabilities diperlakukan sebagai konsep kelas satu (*first-class citizen*):
- Karyawan memiliki daftar kapabilitas (`capabilities`).
- Role menentukan kapabilitas standar/bawaan.
- Task mendefinisikan kapabilitas yang dibutuhkan (`required_capabilities`).
- Menjadi parameter utama dalam penilaian pencocokan tugas (*task matching*).

---

## 7. Personality System

Sistem kepribadian dirancang ringan tanpa membebani logic bisnis:
- **`traits`**: Karakter kerja (misal: `["gotong_royong", "musyawarah_mufakat", "teliti", "ramah", "solutif"]`).
- **`communication_style`**: Gaya komunikasi kantor Indonesia (misal: `santun_profesional`, `ringkas_solutif`, `ramah_tanggap`, `musyawarah_terbuka`).
- **`decision_style`**: Gaya pengambilan keputusan (misal: `musyawarah_mufakat`, `berbasis_data`, `test_driven`, `pragmatis_eksekusi`).

---

## 8. Modular System Prompt Composition

`PromptBuilder` menyusun system prompt secara modular dari 6 blok:
1. **Base Agent Instructions**: Prinsip dasar integritas, akurasi, dan keselamatan kerja AI.
2. **Role & Identity**: Nama karyawan, ID, role, department, dan misi kerja.
3. **Capabilities & Domain Skills**: Deklarasi kompetensi teknis karyawan.
4. **Personality & Style**: Arahan gaya respons dan pendekatan problem-solving.
5. **Task Context**: Deskripsi objektif tugas yang sedang dikerjakan.
6. **Organization Policies**: Standar mutu dan aturan format output perusahaan.

---

## 9. Model Inheritance Hierarchy

Konfigurasi LLM diwariskan secara bertingkat (*most specific configuration wins*):

```text
Employee model config (Tertinggi)
       ↓
Role default
       ↓
Department default
       ↓
Organization default
       ↓
Global config (yaml / settings) (Terendah)
```

Fungsi `resolve_model_config()` menggabungkan parameter secara aman per field (`provider`, `model`, `temperature`, `max_tokens`).

---

## 10. Agent Factory & Generic Agent

`AgentFactory` menghilangkan instansiasi manual:
- Peran dengan logika eksekusi khusus dipetakan otomatis:
  - `pm` / `product_manager` → `PMAgent`
  - `conceptor` → `ConceptorAgent`
  - `planner` / `software_architect` → `PlannerAgent`
  - `developer` / `backend_developer` / `frontend_developer` → `DeveloperAgent`
  - `qa` / `qa_engineer` → `QAAgent`
- **Generic Agent Fallback**: Peran baru apa pun (Copywriter, UI Designer, DevOps, Researcher, dsb.) secara otomatis menggunakan `GenericAgent`, yang memanfaatkan `PromptBuilder` untuk menjalankan tugas kontekstual via LLM.

---

## 11. Employee Registry

`EmployeeRegistry` bertindak sebagai *source of truth* thread-safe:
- `register(employee)`: Menolak duplikasi ID (`ValueError`).
- `get(employee_id)`: Mengambil profil karyawan berdasarkan ID.
- `list()`: Mengambil seluruh karyawan.
- `find_by_role(role)`: Filter berdasarkan peran.
- `find_by_department(dept)`: Filter berdasarkan departemen.
- `find_by_capability(cap)`: Filter berdasarkan keahlian.
- `update_status(employee_id, status)`: Memperbarui status live dan availability.

---

## 12. Hiring & Deactivation Lifecycle

Sistem rekrutmen fondasi:
- **`hire(name, role, department=None, capabilities=None, personality=None, model=None)`**:
  - Otomatis mengalokasikan `employee_id` unik (misal `backend_developer_001`).
  - Menetapkan status `active` dan ketersediaan `available`.
  - Memancarkan event `employee_hired`.
- **`fire(employee_id)`**:
  - Mengubah status karyawan menjadi `inactive`.
  - Mengubah availability menjadi `offline`.
  - Memancarkan event `employee_deactivated`.

---

## 13. Deterministic Task Assignment Matcher

`TaskMatcher` mengevaluasi dan merangking kandidat secara deterministik:
- **Aturan Penilaian**:
  - `Role Match`: **+20 poin** jika role kandidat cocok dengan target tugas.
  - `Department Match`: **+5 poin** jika department kandidat cocok.
  - `Capability Match`: **+10 poin** per keahlian yang cocok dengan `required_capabilities`.
  - **Disqualifikasi**: Kandidat dengan status `inactive` atau availability bukan `available` langsung diberi skor `-1` (diskualifikasi).
- **Metode**: `score_candidate()`, `rank_candidates()`, dan `find_best_employee()`.

---

## 14. Organization Events

Terintegrasi langsung ke `EventBus` Phase 3:
- `employee_hired`
- `employee_activated`
- `employee_deactivated`
- `employee_updated`
- `role_registered`
- `department_registered`
- `task_assigned`
- `task_unassigned`

---

## 15. Organization State & Analytics

Informasi status terkini dapat dibaca langsung tanpa perlu memutar ulang event log:
- `organization.get_employee_count(active_only=False)`
- `organization.get_active_employees()`
- `organization.get_department_stats()`: Menghasilkan statistik jumlah karyawan aktif dan breakdown peran per departemen.

---

## 16. Database Schema & Persistence

SQLite (`tasks.db`) diperluas dengan 6 tabel baru tanpa merusak tabel Phase 1–3:
1. `organizations`: `id`, `name`, `default_model`, `metadata`, `created_at`, `updated_at`.
2. `departments`: `id`, `organization_id`, `name`, `description`, `default_model`, `created_at`.
3. `roles`: `id`, `name`, `department_id`, `description`, `capabilities`, `default_model`, `created_at`.
4. `employees`: `id`, `name`, `role_id`, `department_id`, `capabilities`, `personality`, `model`, `status`, `availability`, `live_state`, `metadata`, `created_at`, `updated_at`.
5. `capabilities`: `id`, `name`, `category`.
6. `employee_capabilities`: `employee_id`, `capability_id`, `PRIMARY KEY(employee_id, capability_id)`.

---

## 17. CLI Workforce Commands

CLI kini dilengkapi perintah inspeksi dan manipulasi workforce:
```bash
# Inspeksi departemen
python cli.py departments

# Inspeksi peran
python cli.py roles
python cli.py roles --department marketing

# Inspeksi karyawan
python cli.py employees
python cli.py employees --role developer
python cli.py employees --department engineering
python cli.py employees --status active

# Rekrut personil baru
python cli.py hire --role copywriter --name "Laras Wulandari" --capabilities "copywriting,messaging,viral_hooks"

# Nonaktifkan personil
python cli.py fire copywriter_001
```

Perintah lama (`run`, `status`, `events`, `replay`, `list`) tetap bekerja 100% tanpa perubahan.

---

## 18. Tests & Verification

Pengujian komprehensif dijalankan menggunakan `pytest`:
- **138 tests lulus (100% pass)**:
  - **79/79** Tests Phase 1, 1.5, dan 2 (`test_reliability.py`)
  - **33/33** Tests Phase 3 (`test_streaming.py`)
  - **26/26** Tests Phase 4 (`test_workforce.py`)
- **Integration Simulation**:
  - Mensimulasikan kantor virtual dengan **3 departemen** (`engineering`, `product`, `marketing`), **5 peran**, dan **10 personil** (Bagas Aditya, Bayu Setiawan, Citra Dewi, Dimas Prasetya, Laras Wulandari, Maya Anggraini, Surya Pratama, Tiara Kusuma, Panji Nugroho, Putri Rahayu).
  - Menguji dua personil dengan peran identik (`copywriter`) memiliki keahlian dan kepribadian berbeda serta dapat ditugaskan secara independen.
  - Memverifikasi algoritma `TaskMatcher` mencocokkan tugas ke karyawan spesifik yang tepat berdasarkan kapabilitas (Bagas Aditya untuk FastAPI/SQLite backend, Laras Wulandari untuk viral hooks copywriting).
  - Menjalankan eksekusi tugas via `AgentFactory`, memvalidasi emisi event, dan memastikan sinkronisasi data ke SQLite.

---

## 19. Known Issues

- Tidak ada issue kritis atau blocker.
- Koneksi database SQLite pada operasi CLI otomatis menyinkronkan data default seed jika database masih kosong.
- Nilai model string lama pada `AgentManifest` secara otomatis dikonversi ke dictionary model envelope pada `Employee`.

---

## 20. Phase 5 Recommendation

Fondasi workforce Phase 4 telah terbukti stabil dan dapat dikembangkan ke **Phase 5 — Dynamic Team Collaboration & Task Delegation**:
1. **Dynamic Multi-Agent Teams**: Pembentukan tim dinamis per proyek (misal: PM membentuk tim beranggotakan 1 Architect, 2 Backend Dev, 1 QA, dan 1 Copywriter).
2. **Autonomous Task Delegation**: PM dan Architect memecah pekerjaan lalu mendelegasikan task ke karyawan terbaik menggunakan `TaskMatcher` secara otomatis saat pipeline berjalan.
3. **Internal Review & Peer Handoff**: Alur kerja kolaborasi di mana output satu karyawan (misal: Copywriter) dapat di-review oleh karyawan lain (misal: Marketing Strategist) sebelum masuk ke implementasi developer.
4. **Team Chat / Discussion Channels**: Simulasi kanal komunikasi antar-karyawan virtual untuk sinkronisasi konteks proyek secara terstruktur.
