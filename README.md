<div align="center">

# 🏢 AETHER OFFICE
### Autonomous Multi-Agent AI Office & Adaptive Planning Engine

[![CI](https://github.com/AarsyDesign/Aether-Office/actions/workflows/ci.yml/badge.svg)](https://github.com/AarsyDesign/Aether-Office/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*Ubah visi dan ide Anda menjadi perangkat lunak nyata melalui organisasi AI Multi-Agent yang otonom dan terstruktur.*

[⚡ Quickstart](#-quickstart--cara-instalasi) • [🚀 5 Perintah Utama](#-5-perintah-utama-cara-memakainya) • [🤖 Konfigurasi AI](#-konfigurasi-ai-configyaml) • [❓ FAQ](#-panduan-praktis--tanya-jawab-faq) • [🏛️ Arsitektur](#-arsitektur)

</div>

---

## 🌟 Apa Itu Aether Office?

Bukan sekadar wrapper prompt biasa, **Aether Office** memodelkan **organisasi AI otonom terstruktur secara menyeluruh**:
- **30+ Karyawan AI Spesialis** di **8 Departemen** (*Engineering, Product, Design, Marketing, Research, Operations, Business, Support*).
- **100% Otonom**: Anda tidak perlu memilih peran agen secara manual. Cukup ketik ide atau berikan file brief, tim agen (PM ➔ Conceptor ➔ Developer ➔ QA) akan bekerja secara terkoordinasi.
- **Eksekusi Proyek Nyata**: Agen menghasilkan berkas kode nyata di disk pada folder `projects/<nama-proyek>/`.
- **Adaptive Planning & Evaluator**: Memecah tugas menjadi graf dependensi (DAG) dan menilai kualitas rancangan (skor 0-100) sebelum dieksekusi.

---

## ⚡ Quickstart — Cara Instalasi

### Langkah 1: Setup Lingkungan (1-Klik di Windows)
Cukup jalankan script batch berikut di terminal:
```cmd
.\setup.bat
```
> *Script ini secara otomatis membuat virtual environment `.venv` dan memasang seluruh dependensi Python yang dibutuhkan.*

---

## 🤖 Konfigurasi AI (`config.yaml`)

Sebelum menjalankan agen untuk menghasilkan kode, pastikan konfigurasi AI Anda di file **[config.yaml](config.yaml)** sudah terisi:

```yaml
llm:
  endpoint: "https://openrouter.ai/api/v1"   # Endpoint AI OpenAI-compatible
  api_key: "sk-or-v1-xxxxxxxxxxxxxxxx"      # API Key Anda
  model: "meta-llama/llama-3.3-70b-instruct" # Nama model yang digunakan
```

### Pilihan Penyedia AI yang Didukung:
| Provider | Endpoint | Catatan |
| :--- | :--- | :--- |
| **OpenRouter** *(Cloud)* | `https://openrouter.ai/api/v1` | Sangat direkomendasikan, tersedia banyak model gratis & berbayar |
| **Groq** *(Cloud Super Cepat)* | `https://api.groq.com/openai/v1` | Sangat cepat untuk iterasi kode |
| **Ollama** *(Lokal Gratis)* | `http://localhost:11434/v1` | Tanpa internet, pastikan Ollama sudah aktif |
| **Local Proxy / 9router** | `http://localhost:20128/v1` | Pastikan server proxy lokal Anda sudah dinyalakan |
| **Mode Mock / Offline** | *Tidak butuh konfigurasi* | Tambahkan flag `--mock` untuk simulasi instan gratis |

---

## 🚀 5 Perintah Utama (Cara Memakainya)

Jalankan perintah-perintah ini di **Terminal Windows (PowerShell / CMD)**:

### 1️⃣ Cek Kesehatan Kantor & Kesiapan Agen
Memeriksa status runtime kantor, scheduler, dan jumlah karyawan yang siap bertugas:
```powershell
.\aether.bat office status
```

### 2️⃣ Cek Daftar 30+ Karyawan Spesialis
Melihat seluruh daftar karyawan AI, divisi, keahlian, dan status ketersediaan:
```powershell
.\aether.bat employees
```

### 3️⃣ Jalankan Pembuatan Aplikasi (Langsung Ketik Ide Anda)
Cukup ketik ide atau instruksi yang ingin dibuat, agen akan langsung bekerja secara otonom:
```powershell
.\aether.bat run "Buat aplikasi Kasir POS Desktop dengan SQLite"
```
*(Ingin uji coba cepat tanpa API key? Tambahkan `--mock` di akhir perintah).*

### 4️⃣ Atau Jalankan dari File Brief yang Sudah Ditulis
Jika Anda sudah menyiapkan dokumen brief proyek (misal di folder `briefs/`):
```powershell
.\aether.bat run briefs/cashier-pondok.md
```

### 5️⃣ Cek Daftar Seluruh Proyek yang Pernah Dibuat
Melihat riwayat seluruh proyek yang telah diselesaikan atau sedang berjalan:
```powershell
.\aether.bat list
```

---

## 📁 Di Mana Hasil Kodingan Disimpan?

Setiap kali Anda menjalankan perintah `run`, Aether Office akan otomatis membuat folder proyek baru di:
```text
projects/<nama-proyek>-<timestamp>/
  ├── core.py         # Kode utama logika aplikasi
  ├── test_core.py    # Unit test otomatis yang dibuat oleh agen
  └── docs/           # Rangkuman arsitektur dari PM & Conceptor
```

---

## 📖 Panduan Praktis & Tanya Jawab (FAQ)

### ❓ 1. Apakah Saya Harus Memilih Agent Secara Manual?
> **TIDAK PERLU! Sistem bekerja 100% Otonom.**

Saat Anda menjalankan perintah `.\aether.bat run "..."`, Anda tidak perlu memilih siapa PM, desainer, atau programmer-nya. Sistem Aether Office mengorkestrasi alur kerja secara otomatis:
1. **Project Manager (`Budi Santoso`)** ➔ Membedah brief Anda menjadi daftar tugas terstruktur.
2. **Product Conceptor (`Siti Rahma`)** ➔ Menyusun spesifikasi teknis dan kriteria penerimaan.
3. **Developer (`Eko Prasetyo`)** ➔ Menulis berkas kode nyata file demi file.
4. **QA Engineer (`Ratna Sari`)** ➔ Mengaudit sintaks dan memvalidasi kode.

---

### ❓ 2. Apakah Dijalankan di Terminal atau Cukup Perintah di IDE?
Anda memiliki dua opsi fleksibel:

* **Opsi A: Terminal Bawaan IDE (Sangat Disarankan)**
  Buka terminal terintegrasi di IDE Anda (tekan shortcut ``Ctrl + ` ``), lalu jalankan perintah seperti biasa:
  ```powershell
  .\aether.bat office status
  .\aether.bat run "Buat REST API sederhana dengan FastAPI"
  ```
  > 💡 **Penting untuk Windows PowerShell:** Selalu gunakan awalan `.\` (yaitu `.\aether.bat`), bukan `aether` biasa tanpa titik.

* **Opsi B: Cukup Perintah Chat ke AI di IDE (Pair Programming)**
  Jika Anda sedang menggunakan Antigravity IDE, Anda cukup menulis pesan di chat:
  > *"Tolong jalankan pipeline pengerjaan untuk aplikasi kasir berdasarkan briefs/cashier-pondok.md"*
  
  Asisten AI akan langsung mengeksekusinya di latar belakang dan melaporkan hasilnya kepada Anda.

---

### ❓ 3. Apa Beda `office status` dengan `status <project_id>`?
* **`.\aether.bat office status`** ➔ Memeriksa **kesehatan seluruh kantor** (runtime, detak scheduler, kapasitas karyawan).
* **`.\aether.bat status <project_id>`** ➔ Memeriksa **detail satu proyek tertentu** yang sudah dibuat (contoh: `.\aether.bat status buat-aplikasi-kasir-1788670162`).

---

### ❓ 4. Error `[WinError 10061] No connection could be made...` Apa Artinya?
Pesan ini muncul ketika Aether Office mencoba menghubungi AI, tetapi server AI yang tertera di `config.yaml` **belum aktif atau mati**.
* **Solusinya:**
  1. Jika menggunakan router lokal (port 20128), pastikan server lokal Anda sudah dijalankan.
  2. Atau ganti `endpoint` dan `api_key` di [config.yaml](config.yaml) ke cloud provider seperti OpenRouter / Groq.
  3. Atau gunakan mode offline instan dengan menambahkan flag `--mock`:
     ```powershell
     .\aether.bat run "Ide Proyek Anda" --mock
     ```

---

## 🏛️ Arsitektur

```mermaid
flowchart TD
    User([👤 User Prompt / Brief / CLI]) --> Analyzer[🔍 Objective Analyzer]
    
    subgraph Planning_Intelligence [Adaptive Planning System]
        Analyzer --> Classifier{Domain & Complexity}
        Classifier --> AmbiguityCheck[❓ Ambiguity Gate]
        AmbiguityCheck -->|Clear Scope| StrategySelector[🎯 Planning Strategy Selector]
        StrategySelector --> PlanGen[📋 Execution Plan DAG]
        PlanGen --> Validator[🛡️ Deterministic DAG Validator]
        PlanGen --> Evaluator[🏆 Quality Evaluator 0-100]
    end

    subgraph Runtime_Operations [Scheduler & Real Project Engine]
        Validator --> Scheduler[⏱️ Persistent Scheduler Engine]
        Scheduler --> Matcher[🤝 Capability & Skill Matcher]
        Scheduler --> CodePipeline[🚀 Real Project Pipeline]
        CodePipeline --> DiskWriter[💾 Disk Writer projects/name/]
    end

    subgraph Workforce_Pool [Workforce Pool]
        Matcher --> Emp1[Budi Santoso - PM Lead]
        Matcher --> Emp2[Siti Rahma - Product Conceptor]
        Matcher --> Emp3[Eko Prasetyo - Developer]
        Matcher --> Emp4[Ratna Sari - QA Engineer]
        Matcher --> EmpN[... 30+ Karyawan di 8 Divisi]
    end
```

---

## 🤝 Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE).
