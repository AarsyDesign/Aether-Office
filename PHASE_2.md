# Phase 2 — Chunked Developer & Planner Architecture

**Status:** Complete  
**Date:** 2026-09-05  
**Tests:** 79/79 pass (100%)  
**Changes:** 6 files modified/created (`agents/planner.py`, `agents/developer.py`, `orchestrator.py`, `db.py`, `cli.py`, `agents/conceptor.py`, `llm.py`, `test_reliability.py`)

---

## 1. Masalah yang Diselesaikan

Pada Phase 1 dan 1.5, Developer agent menghasilkan seluruh basis kode proyek dalam **satu LLM prompt raksasa**. Pendekatan monolitik ini menimbulkan sejumlah risiko fatal di lingkungan produksi:
1. **Timeout pada model gratis/lambat:** LLM gagal merespons dalam window waktu (300 detik) saat diminta menulis ribuan baris kode sekaligus.
2. **Pemotongan kode (*Token Truncation*):** Window batas output token (biasanya 4096) memotong kode di tengah jalan, meninggalkan kurung kurawal atau blok *code fence* terbuka.
3. **Kerapuhan generation (*All-or-Nothing failure*):** Kegagalan sintaks atau format pada 1 file merusak seluruh hasil generasi proyek.
4. **Pemborosan siklus perbaikan (*Fix Cycle*):** Ketika QA melaporkan bug kecil di satu file, sistem terpaksa men-generate ulang seluruh proyek dari nol.

Solusi di Phase 2: Mengubah Developer menjadi **task/file-based chunked generation pipeline** di mana **1 unit generasi = 1 file** yang terisolasi, divalidasi sintaksnya, memiliki retry mandiri, dan dapat di-*resume*.

---

## 2. Arsitektur: Sebelum vs Sesudah

### Arsitektur Sebelum (Phase 1 & 1.5)
```text
Requirements
     ↓
Developer (Single LLM Prompt) → [app.py, db.py, models.py, test.py] sekaligus
     ↓
QA (LLM Review + Automated Tests)
     ↓
QA FAIL → Regenerate seluruh project dari awal
```

### Arsitektur Sesudah (Phase 2 — Chunked Developer)
```text
Requirements & Shared Docs
          ↓
  Developer Planner
          ↓
  Implementation Plan (JSON + topological sort)
          ↓
┌──────────────────────────────────────────────┐
│ Loop per Unit File (Sesuai Urutan Dependensi) │
│   1. Cek Resume (lewati jika sudah DONE)     │
│   2. Susun Compact Context                   │
│   3. Generate Unit (Structured JSON / Fallback)│
│   4. Deteksi Truncation                      │
│   5. Validasi Sintaks Python (ast.parse)     │
│   6. Retry Unit (maks 2 percobaan)           │
│   7. Tulis ke Disk                           │
│   8. Catat DB (dev_units) & Emit Events      │
└──────────────────────────────────────────────┘
          ↓
  Developer Selesai
          ↓
         QA
          ↓
   (Jika QA FAIL → Fix Cycle HANYA menargetkan file yang bug)
```

---

## 3. Developer Planner (`agents/planner.py`)

Tahap perancangan arsitektur sebelum penulisan kode. Planner tidak menulis source code, melainkan menentukan:
- File apa saja yang harus dibuat (`what`).
- Di mana file tersebut diletakkan (`where`).
- File mana yang bergantung pada file lain (`depends_on`).

Dokumen hasil perancangan disimpan di `docs/implementation_plan.json`.

### Schema Implementation Unit
```json
{
  "project_summary": "Summary of the project",
  "tech_stack": "Python, Flask, SQLite",
  "files": [
    {
      "path": "database.py",
      "purpose": "Database connection and query helpers",
      "exports": ["Database", "get_connection"],
      "depends_on": [],
      "dependencies": ["sqlite3"],
      "priority": 1
    },
    {
      "path": "models.py",
      "purpose": "Domain data models",
      "exports": ["TodoItem"],
      "depends_on": ["database.py"],
      "dependencies": [],
      "priority": 2
    },
    {
      "path": "app.py",
      "purpose": "Web application entrypoint and routes",
      "exports": ["app"],
      "depends_on": ["database.py", "models.py"],
      "dependencies": ["flask"],
      "priority": 3
    }
  ],
  "generation_order": ["database.py", "models.py", "app.py"]
}
```

---

## 4. Resolusi Dependensi (*Topological Sort*)

File digenerate mengikuti urutan dependensi logis:
$$\text{foundation} \rightarrow \text{models} \rightarrow \text{services/helpers} \rightarrow \text{application} \rightarrow \text{tests}$$

- Menggunakan **Kahn's Algorithm** untuk *topological sorting*.
- Dependensi eksternal (misal: `sqlite3`, `flask`) secara otomatis diabaikan dari graf internal.
- **Pendeteksi Circular Dependency:** Jika terjadi siklus (contoh: $A \rightarrow B \rightarrow C \rightarrow A$), Planner menolak rencana dan mengembalikan error eksplisit: `Circular dependency detected among files: ...`.

---

## 5. Strategi Konteks Antar Chunk (*Compact Context*)

Setiap prompt unit file hanya menerima informasi yang esensial agar tidak membebani context window:
1. **Project Summary & Tech Stack.**
2. **Spesifikasi File Saat Ini:** Jalur (`path`) dan tujuan (`purpose`).
3. **Antarmuka Dependensi (*Dependency Interfaces*):** Ekspor publik (`exports`) dan tujuan dari file-file yang dideklarasikan dalam `depends_on`.
4. **Ringkasan Persyaratan Relevan:** Cuplikan dari `docs/requirements.md` (dibatasi 3.000 karakter).
5. **Daftar File yang Telah Digenerate:** Mencegah redundansi path.

Contoh blok konteks antarmuka dependensi:
```text
## Dependency Interfaces
database.py
  purpose: database connection layer
  exports: Database, connect
```

---

## 6. Format Respons Terstruktur & Fallback

Developer dipaksa mengembalikan **satu file saja** dalam format JSON:
```json
{
  "path": "app.py",
  "content": "def main():\n    pass\n",
  "summary": "Main entry point of the app"
}
```
**Fallback:** Jika LLM mengembalikan blok *markdown code fence* (misalnya model tanpa dukungan JSON murni), parser secara cerdas mengekstrak blok kode terpanjang yang sesuai dengan ekstensi file target.

---

## 7. Strategi Validasi Sintaks & Truncation

1. **Python Syntax Validation:** Menggunakan pustaka standar Python `ast.parse(content, filename=filepath)` in-memory. Jika ada kesalahan kompilasi, error `SyntaxError` langsung terdeteksi sebelum ditulis ke disk. File non-Python dilewati secara aman.
2. **Deteksi Truncation Unit:**
   - Deteksi jumlah ganjil dari backtick code fence (```` ``` ````).
   - Deteksi selisih kurung buka dan kurung tutup (`{`, `(`, `[` vs `}`, `)`, `]`).
   - Deteksi pemotongan mendadak (*abrupt cut-off* tanpa *trailing newline*).

---

## 8. Hirarki Retry

Phase 2 membedakan 2 level retry:
- **LLM-Level Retry (`llm.py`):** Menangani masalah transport, HTTP 429 rate limit, timeout, dan auth error (eksponensial backoff).
- **Unit-Level Retry (`DeveloperAgent`):** Menangani *syntax error*, pemotongan token, atau JSON parse failure pada file tertentu.
  - Nilai konfigurasi: `developer.unit_max_retries: 2`.
  - Jika percobaan ke-1 menghasilkan *syntax error*, agen otomatis mencoba ulang menghasilkan file yang sama. Jika tetap gagal setelah limit habis, unit ditandai `FAILED` dan pipeline berhenti secara aman.

---

## 9. Kemampuan Resume (*Resume Capability*)

Tabel `dev_units` di SQLite (`data/tasks.db`) melacak status setiap file:
$$\text{PENDING} \rightarrow \text{RUNNING} \rightarrow \text{DONE} \ / \ \text{FAILED}$$

Jika proses terhenti di tengah jalan (misal: unit ke-3 gagal dari 5 unit), pemanggilan ulang `Developer.implement()` akan:
1. Membaca status `dev_units`.
2. Mendeteksi unit yang berstatus `DONE` dan langsung menambahkannya ke daftar selesai tanpa memanggil LLM ulang.
3. Melanjutkan eksekusi mulai dari unit yang belum selesai.

---

## 10. Siklus Perbaikan Terarah (*Fix Cycle*)

Saat QA menemukan bug (`QA FAIL`):
1. Orchestrator mengirimkan laporan bug QA ke Developer dalam `fix_context`.
2. Developer mengekstrak nama file yang terdampak dari daftar bug (misal: `database.py`).
3. Planner dan unit loop **hanya menargetkan file yang rusak** tersebut.
4. File lain yang sudah benar tidak di-generate ulang, menghemat token dan waktu secara drastis.

---

## 11. Event System Lengkap (Phase 2)

Event-event baru yang dipancarkan:
```text
developer_planning_started        Payload: {fix_mode: bool}
developer_plan_created            Payload: {file_count: int}
developer_generation_started      Payload: {unit_count: int}
developer_unit_started            Payload: {path: str, attempt: int}
developer_unit_retry              Payload: {path: str, attempt: int, reason: str}
developer_unit_validated          Payload: {path: str, attempt: int}
developer_unit_completed          Payload: {path: str, attempt: int, size: int}
developer_unit_failed             Payload: {path: str, attempt: int, error: str}
developer_generation_completed    Payload: {files_written: int, fix_mode: bool}
developer_generation_failed       Payload: {failed_unit: str, completed: int, total: int}
```

---

## 12. Observabilitas Konsol CLI

Progres generasi file ditampilkan secara transparan dan terstruktur di terminal:
```text
[DEVELOPER] Planning implementation...
[DEVELOPER] 3 units identified

[1/3] database.py
      generating...
      ✓ validated (340 chars)
[2/3] models.py
      generating...
      ✗ Syntax error: line 12
      retry 1/2...
      ✓ validated (512 chars)
[3/3] app.py
      generating...
      ✓ validated (1024 chars)

Developer complete.
```

---

## 13. File yang Diubah & Ditambahkan

| File | Status | Perubahan Utama |
| :--- | :--- | :--- |
| `agents/planner.py` | Baru | Logika Planner, `topological_sort` (Kahn's), pendeteksi circular dependency, pembuatan `docs/implementation_plan.json`. |
| `agents/developer.py` | Modifikasi | Implementasi chunked unit generation, `validate_syntax`, `detect_unit_truncation`, backward-compatible `detect_truncation`, resume logic, dan targeted fix mode. |
| `agents/conceptor.py` | Modifikasi | Perbaikan *indentation syntax*, eliminasi pemanggilan LLM ganda saat menyusun test plan. |
| `orchestrator.py` | Modifikasi | Penyesuaian loop QA attempt agar attempt ke-1 selalu berjalan meskipun `max_retries: 0`. |
| `db.py` | Modifikasi | Tabel `dev_units`, timeout 30s SQLite, WAL journal mode, dan pembersihan status saat inisialisasi project. |
| `llm.py` | Modifikasi | Fleksibilitas pemanggilan `chat(system, user, json_mode)` untuk kompatibilitas multi-gaya. |
| `cli.py` | Modifikasi | Penyesuaian parameter `cmd_list(args=None)` dan konfigurasi otomatis encoding UTF-8 untuk konsol Windows. |
| `test_reliability.py` | Modifikasi | Penambahan 29 unit & integration tests baru (total 79 tests). |

---

## 14. Hasil Pengujian & Simulasi Integrasi

Eksekusi `python -m pytest test_reliability.py -v`:
```text
TestAgentResult                           (4 tests)  ✅
TestStateMachine                          (7 tests)  ✅
TestLLMCleaning                           (5 tests)  ✅
TestTruncationDetection                   (5 tests)  ✅
TestDatabase                              (5 tests)  ✅
TestQAErrorCategorization                 (5 tests)  ✅
TestQAValidation                          (5 tests)  ✅
TestLLMRetry                              (4 tests)  ✅
TestLLMClient                             (2 tests)  ✅
TestPMAgent                               (4 tests)  ✅
TestDeveloperAgent (Legacy compat)        (3 tests)  ✅
TestOrchestrator                          (1 test)   ✅
TestTopologicalSort                       (5 tests)  ✅
TestUnitTruncation                        (5 tests)  ✅
TestSyntaxValidation                      (3 tests)  ✅
TestDeveloperAgentChunked                 (6 tests)  ✅
TestPlanner                               (4 tests)  ✅
TestDevUnitsDB                            (3 tests)  ✅
TestIntegrationSimulation                 (3 tests)  ✅
──────────────────────────────────────────────────────────
Total:                                    79 tests   ✅ ALL PASS (100%)
```

### Rincian Simulasi Integrasi yang Diverifikasi:
1. **Simulasi 1 (`test_3_file_project_success`):**
   `PM` $\rightarrow$ `Conceptor` $\rightarrow$ `Planner` $\rightarrow$ `3 unit files (a.py, b.py, c.py)` $\rightarrow$ `QA PASS` $\rightarrow$ `Pipeline DONE`.
2. **Simulasi 2 (`test_3_file_project_retry_then_success`):**
   File ke-2 mengalami *syntax error* pada percobaan pertama $\rightarrow$ memicu unit retry $\rightarrow$ percobaan kedua berhasil $\rightarrow$ file ke-3 digenerate $\rightarrow$ `QA PASS` $\rightarrow$ `Pipeline DONE`.
3. **Simulasi 3 (`test_unit_failure_stops_pipeline`):**
   File ke-2 gagal secara permanen $\rightarrow$ retry exhausted $\rightarrow$ file ke-3 tidak dijalankan $\rightarrow$ Pipeline berhenti secara *graceful* dengan status `FAILED`.

---

## 15. Known Issues & Rekomendasi Phase 3

### Known Issues
1. **Dynamic Token Allocation:** `max_tokens` per call masih statis (4096). Untuk file yang sangat pendek, alokasi token dapat dioptimalkan.
2. **Linting Lanjutan:** Saat ini validasi sintaks baru mencakup parser AST bawaan Python, belum mengecek missing import eksternal sebelum runtime.

### Rekomendasi untuk Phase 3
1. **Real-Time Streaming Progress (SSE / WebSocket):** Memancarkan progress event unit secara real-time ke UI frontend.
2. **Visual AI Office Integration:** Menghubungkan transisi event (`developer_unit_started`, `developer_unit_validated`, `qa.completed`) langsung ke state karakter/karyawan virtual (THINKING, WORKING, TESTING, DONE).
3. **Multi-Model Routing:** Memberikan opsi model reasoning tinggi untuk PM & Planner, dan model cepat berbiaya rendah untuk unit generator sederhana.
