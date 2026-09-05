# PHASE 9 — ADAPTIVE PLANNING & INTELLIGENCE

Aether Office Phase 9 mengonversi perencana statis (Fixed 4-Milestone Planner: *Riset → Desain → Implementasi → QA*) menjadi **Adaptive Planning System**. Sistem cerdas ini mengevaluasi karakteristik objektif pengguna (domain, kompleksitas, ambiguitas, risiko, kapabilitas workforce, pagu anggaran, dan tenggat waktu) untuk merumuskan struktur dekomposisi rencana eksekusi (*ExecutionPlan*) yang optimal dan realistis.

---

## 1. ARCHITECTURE

Phase 9 mempertahankan fondasi runtime dan scheduling Phase 1–8 tanpa merusak atau mengubah komponen inti (`SchedulerEngine`, `OfficeRuntime`, `OfficeOrchestrator`, `ProjectRegistry`, `ProjectQueue`, `WorkQueue`, `ResourceManager`, `UsageTracker`, `BudgetManager`, `ArtifactStore`).

```text
                        USER OBJECTIVE
                              ↓
                      OBJECTIVE ANALYZER
                              ↓
                      PLANNING STRATEGY
                (Software / Research / Marketing /
                 Content / Analysis / General)
                              ↓
                        EXECUTION PLAN
                              ↓
                        PLAN VALIDATOR
                        (Deterministic)
                              ↓
                    PLAN QUALITY EVALUATOR
                    (Completeness, DAG, Cap,
                     Budget, Acceptance)
                              ↓
                        PLAN OPTIMIZER
                    (Critical Path, Parallel,
                     Model Cost Downscaling)
                              ↓
                   INTERMEDIATE MILESTONE GATES
                              ↓
                      OFFICE RUNTIME
                              ↓
                     SCHEDULER ENGINE
                              ↓
                   SHARED WORKFORCE POOL
```

---

## 2. OBJECTIVE ANALYZER

`ObjectiveAnalyzer` mengurai struktur teks objektif untuk mengekstrak metrik kuantitatif dan kualitatif sebelum pembentukan tugas:

### `ObjectiveAnalysis` Data Structure
* `objective_id`: Identifikasi objektif target.
* `objective_type`: Tipe domain terklasifikasi (`SOFTWARE`, `RESEARCH`, `MARKETING`, `CONTENT`, `ANALYSIS`, `GENERAL`).
* `complexity`: Tingkat kerumitan (`SIMPLE`, `STANDARD`, `COMPLEX`).
* `ambiguity_score`: Skor keambiguan (0.0 = konkret & terukur, 1.0 = sangat kabur).
* `needs_clarification`: Boolean penanda apakah objektif harus diklarifikasi sebelum diizinkan masuk tahap perencanaan.
* `clarifications`: Koleksi `ClarificationRequest` yang merinci pertanyaan esensial.
* `required_capabilities`: Daftar kapabilitas teknis yang diwajibkan untuk menuntaskan objektif.
* `estimated_deliverables`: Estimasi artefak atau luaran yang dihasilkan.
* `estimated_duration`: Estimasi durasi pengerjaan dalam jam kerja/tick.
* `estimated_cost`: Estimasi biaya pemakaian model token dalam USD.
* `risks`: Daftar `RiskAssessment` hasil audit risiko.
* `confidence`: Nilai keyakinan planner (0.0 – 1.0).

---

## 3. CLASSIFICATION

Classifier domain menerapkan *weighted intent pattern scoring* dengan pembobotan 2x pada judul untuk menangkap maksud esensial objektif:

1. **SOFTWARE**: Pengembangan aplikasi, modul API, autentikasi OAuth, database, web portal, atau bug fixing.
2. **RESEARCH**: Riset pasar, investigasi kompetitor, studi literatur, benchmarking model, atau analisis komparasi.
3. **MARKETING**: Kampanye pemasaran produk, strategi promosi digital, lead generation, konten iklan, atau sales funnel.
4. **CONTENT**: Penulisan artikel/blog, penyusunan katalog produk, copy editorial, newsletter, atau dokumentasi panduan.
5. **ANALYSIS**: Analitik metrik bisnis, evaluasi laporan keuangan, analisis churn/retensi, atau visualisasi BI.
6. **GENERAL**: Objektif koordinasi, operasional umum, atau instruksi yang tidak memiliki karakteristik spesifik di atas.

---

## 4. PLANNING STRATEGY

Setiap domain ditangani oleh strategi khusus (`PlanningStrategy`) yang memecah objektif menjadi milestone dan tugas yang terkoordinasi:

* **SoftwarePlanningStrategy**:
  `Discovery → Design → Implementation → Testing → Deployment`
* **ResearchPlanningStrategy**:
  `Scope Definition → Data Collection → Comparative Analysis → Synthesis & Insights → Executive Report`
* **MarketingPlanningStrategy**:
  `Market & Audience Research → Campaign Strategy → Creative Content Production → Multi-Channel Distribution → Analytics & Measurement`
* **ContentPlanningStrategy**:
  `Content Brief → Source Research → Writing & Production → Editorial Review → Publishing Preparation`
* **AnalysisPlanningStrategy**:
  `Data Extraction → Data Cleaning & Processing → Statistical Analysis → Quality Validation → Strategic Recommendations`
* **GeneralPlanningStrategy**:
  `Definisi Sasaran → Perencanaan Alur → Eksekusi Utama → Evaluasi Akhir`

---

## 5. COMPLEXITY

Tingkat kompleksitas dievaluasi melalui `ObjectiveComplexity`:

* **SIMPLE** (Target 3–5 tugas):
  Objektif spesifik berlingkup kecil dengan parameter terdefinisi langsung.
* **STANDARD** (Target 5–15 tugas):
  Objektif dengan alur bertingkat yang memerlukan kolaborasi beberapa disiplin ilmu.
* **COMPLEX** (Target 15+ tugas):
  Objektif berskala enterprise, arsitektur terdistribusi, migrasi heterogen, multi-channel, atau memerlukan kepatuhan audit regulasi ketat.

---

## 6. AMBIGUITY DETECTION

Mendeteksi deskripsi yang belum cukup jelas atau mengandung kata sifat subjektif (contoh: *"bagus"*, *"keren"*, *"canggih"*).

### `ClarificationRequest`
* `question`: Pertanyaan spesifik untuk membatasi lingkup.
* `reason`: Alasan mengapa informasi tersebut dibutuhkan oleh workforce.
* `blocking`: Jika bernilai `True`, `AdaptiveObjectivePlanner` menolak membuat rencana eksekusi dan mengembalikan status `needs_clarification = True` untuk melindungi anggaran pengguna.
* `priority`: Tingkat urgensi klarifikasi (`HIGH`, `MEDIUM`, `LOW`).

---

## 7. RISK ANALYSIS

Komponen `RiskAnalyzer` memindai 7 kategori risiko utama:
1. `HIGH_COMPLEXITY`: Beban koordinasi tinggi dengan dependensi bertingkat.
2. `DEEP_DEPENDENCY`: Rantai jalur kritis yang panjang dan rentan hambatan (bottleneck).
3. `SKILL_SHORTAGE`: Keahlian kunci yang dibutuhkan tidak tersedia dalam workforce aktif.
4. `BUDGET_RISK`: Estimasi biaya mendekati atau melampaui alokasi pagu anggaran.
5. `DEADLINE_RISK`: Estimasi durasi melampaui sisa tenggat waktu objektif.
6. `SINGLE_POINT_OF_FAILURE`: Keahlian spesifik hanya dikuasai oleh satu orang personel.
7. `AMBIGUOUS_REQUIREMENT`: Kebutuhan belum terukur secara objektif.

---

## 8. WORKFORCE-AWARE PLANNING

Planner mengaudit ketersediaan personel dalam organisasi sebelum mengeksekusi rencana:
* Mengidentifikasi apakah peran preferensi (`preferred_role`) dan kapabilitas (`required_capabilities`) dimiliki oleh karyawan berstatus `ACTIVE`.
* Memberikan peringatan (*warning*) atau rekomendasi rekrutmen spesialis jika terjadi defisit kompetensi, tanpa memalsukan kehadiran karyawan (*no fake employees*).

---

## 9. BUDGET-AWARE PLANNING

* Setiap tugas memiliki estimasi token, model tier (`economy`, `standard`, `premium`), dan biaya moneter (USD).
* Jika `estimated_cost > budget`, evaluator mencatat isu pelanggaran anggaran dan memicu `PlanOptimizer` untuk melakukan penurunan model tier tugas non-kritis atau merekomendasikan penyesuaian alokasi biaya.

---

## 10. DEADLINE-AWARE PLANNING

* Menganalisis sisa waktu menuju `objective.deadline`.
* Menghitung jalur kritis (*critical path*) dan mengidentifikasi potensi percepatan melalui eksekusi tugas paralel.
* Menerbitkan peringatan risiko tinggi jika tenggat waktu tidak realistis.

---

## 11. PLAN QUALITY EVALUATION

`PlanQualityEvaluator` memberikan audit kualitas multidimensi (skor 0–100) dan predikat huruf (`A+`, `A`, `B`, `C`, `D`, `F`):
* **Completeness** (0–20 poin): Keberadaan tugas, milestone, peran, dan kapabilitas.
* **Dependency Validity** (0–20 poin): Keabsahan Directed Acyclic Graph (DAG) tanpa siklus/deadlock.
* **Capability Coverage** (0–20 poin): Kesesuaian tugas dengan keahlian tim aktif.
* **Budget Feasibility** (0–20 poin): Kelayakan biaya terhadap alokasi anggaran objektif.
* **Acceptance Criteria Coverage** (0–20 poin): Tingkat ketercakupan kriteria penerimaan pada tugas.

---

## 12. PLAN OPTIMIZATION

`PlanOptimizer` menyempurnakan grafik eksekusi:
1. **Critical Path Calculation**: Menghitung rantai tugas terpanjang dalam topologi DAG.
2. **Parallel Task Tagging**: Menandai tugas-tugas tanpa dependensi langsung yang dapat dijalankan bersamaan.
3. **Graph Cleaning**: Menghapus dependensi duplikat atau transitif berlebih.
4. **Cost Downscaling**: Mengubah model tier tugas pendukung menjadi lebih hemat biaya apabila anggaran ketat.

---

## 13. LLM BOUNDARY & SAFETY

* LLM dapat bertindak sebagai asisten pembantu dekomposisi (`LLMPlannerAssistant`).
* **Prinsip Nol Kepercayaan**: Seluruh keluaran mentah LLM wajib divalidasi oleh `PlanValidator` deterministik.
* Jika terjadi kegagalan format JSON, dependensi sirkular, timeout, atau koneksi terputus, sistem secara otomatis dan aman beralih ke strategi deterministik (*deterministic strategy fallback*) tanpa menginterupsi runtime kantor.

---

## 14. INTERMEDIATE MILESTONE GATING

Phase 9 memperkenalkan gerbang kualitas milestone (*Milestone Gates*):
* Evaluasi kualitas dilakukan pada setiap transisi milestone sebelum tugas milestone berikutnya dijadwalkan.
* Status gerbang: `PENDING`, `PASSED`, `FAILED`, `REVISION_REQUESTED`.
* Jika kriteria gerbang tidak terpenuhi, `MilestoneGateEvaluator` otomatis menyuntikkan tugas revisi terarah ke antrean proyek dengan batasan maksimal revisi (`max_revisions`).

---

## 15. PERSISTENCE

Skema SQLite diperkaya untuk menyimpan rekam jejak perencanaan:
* Tabel `objective_analyses`: Menyimpan riwayat analisis domain, ambiguitas, durasi, estimasi biaya, risiko, dan klarifikasi.
* Tabel `plan_quality_reports`: Menyimpan laporan evaluasi kualitas, skor metrik, isu, dan rekomendasi optimasi.

---

## 16. EVENTS

Integrasi penuh dengan `EventBus` sistem:
* `objective_analysis_started` & `objective_analyzed`
* `planning_strategy_selected`
* `plan_generated` & `plan_validated`
* `plan_quality_evaluated`
* `plan_optimization_started` & `plan_optimization_completed`
* `clarification_required`
* `milestone_evaluation_started`, `milestone_gate_passed`, `milestone_gate_failed`

---

## 17. CLI COMMANDS

Command line interface untuk inspeksi cerdas objektif:
```bash
# Analisis karakteristik, domain, kompleksitas, dan ambiguitas objektif
python cli.py objective analyze <objective_id>

# Perumusan dan tampilan rencana eksekusi adaptif
python cli.py objective plan <objective_id>

# Evaluasi matriks risiko objektif
python cli.py objective risks <objective_id>

# Audit kualitas, kelayakan anggaran, dan keabsahan DAG rencana
python cli.py objective plan-quality <objective_id>
```

---

## 18. KNOWN LIMITATIONS

1. **Single-Node Deployment**: Perencanaan dan runtime beroperasi pada satu node memori lokal/SQLite terisolasi (sesuai batasan non-goals).
2. **Static Risk Rules**: Evaluasi risiko menggunakan aturan heuristik deterministik dan batas ambang kuantitatif; pembelajaran mesin adaptif berbasis historical execution log dapat dikembangkan pada fase berikutnya.

---

## 19. EXAMPLES

### Contoh 1: Perencanaan Objektif Riset
```python
obj = Objective(
    id="obj_comp",
    title="Riset 20 kompetitor AI di Asia Tenggara",
    description="Lakukan studi perbandingan fitur, model harga, dan target pasar.",
    budget=50.0
)
analysis = planner.analyze(obj)
# Hasil: ObjectiveType.RESEARCH, ObjectiveComplexity.STANDARD
plan = planner.plan(obj)
# Hasil: 5 Milestone (Scope, Data Collection, Analysis, Synthesis, Report)
```

### Contoh 2: Deteksi Objektif Ambigius
```python
obj = Objective(id="obj_v", title="Buat website yang bagus", description="")
plan = planner.plan(obj)
# Hasil: is_valid=False, needs_clarification=True,
# Pertanyaan: "Apa ruang lingkup spesifik dan siapa target pengguna dari objektif ini?"
```

---

## 20. MIGRATION & BACKWARD COMPATIBILITY

* `LegacyObjectivePlanner` dipertahankan sebagai alias resmi dari `ObjectivePlanner`.
* Seluruh kode dan pengujian dari Phase 1 hingga Phase 8 tetap berfungsi 100% tanpa perubahan perilaku eksternal.
