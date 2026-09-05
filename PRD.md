# PRD — AI DEVELOPMENT TEAM

## 1. Product Vision

Membangun sebuah **AI Development Team** yang memungkinkan satu manusia memberikan ide/project software, kemudian beberapa AI dengan role berbeda bekerja secara terkoordinasi dari konsep hingga verifikasi.

Core philosophy:

> **THINK → BUILD → VERIFY → IMPROVE**

Produk ini nantinya dapat dikembangkan menjadi **AI Office** yang memvisualisasikan setiap agent sebagai karakter/karyawan virtual.

---

## 2. Problem

Saat menggunakan AI untuk development, manusia masih harus:

* memecah pekerjaan
* menentukan AI mana yang mengerjakan
* memindahkan konteks antar proses
* memantau progress
* menguji hasil
* meminta perbaikan

Sistem ini bertujuan mengurangi koordinasi manual tersebut.

---

## 3. Target User

**Primary:** satu developer / creator / founder yang ingin membangun software dengan bantuan beberapa AI specialist.

**MVP:** satu user.

---

## 4. Core Roles

### Project Manager

Mengatur project, task, prioritas, dependency, dan handoff.

### Conceptor

Mengubah ide menjadi product brief, requirements, user stories, dan acceptance criteria.

### Developer

Mengubah requirements menjadi implementasi software.

### QA

Menguji implementasi berdasarkan acceptance criteria dan melaporkan PASS/FAIL.

---

## 5. Core Workflow

```text
User
 ↓
Project Manager
 ↓
Conceptor
 ↓
Developer
 ↓
QA
 ↓
DONE
```

Jika QA gagal:

```text
QA FAIL
 ↓
Developer FIX
 ↓
QA RETEST
 ↓
PASS
```

Project Manager menjadi koordinator utama.

---

## 6. Core Features

### Agent Runtime

Setiap agent memiliki:

* role
* skill/instruction
* tools
* memory
* permissions
* state

Agent tidak harus menggunakan model AI yang berbeda.

### Orchestrator

Mengatur:

* task assignment
* workflow
* dependency
* handoff
* retry
* failure handling

### Task Management

Status:

```text
BACKLOG
READY
IN_PROGRESS
BLOCKED
REVIEW
QA
DONE
FAILED
```

### Shared Memory

Semua agent dapat mengakses sumber informasi project yang relevan.

Minimal:

```text
/docs
  product.md
  requirements.md
  decisions.md
  testing.md
```

### Event System

Catat aktivitas seperti:

```text
agent.started
agent.completed
task.created
task.assigned
task.completed
task.failed
handoff.created
qa.pass
qa.fail
```

Event ini nantinya menjadi sumber data untuk **AI Office visualization**.

### Audit Log

Semua tindakan penting dapat dilacak.

---

## 7. MVP Test Project

Gunakan project percobaan:

**Todo App**

Fitur:

* login
* tambah task
* edit task
* hapus task
* completed status
* kategori
* deadline
* dashboard sederhana

Tujuannya bukan membuat Todo App yang istimewa, tetapi menguji apakah AI team mampu menyelesaikan software end-to-end.

---

## 8. Success Criteria

MVP dianggap berhasil apabila user dapat memberikan satu project brief dan sistem mampu:

1. PM membuat task.
2. Conceptor menghasilkan requirements.
3. Developer menghasilkan implementation.
4. QA melakukan testing.
5. QA dapat menghasilkan FAIL.
6. Developer memperbaiki bug.
7. QA melakukan retest.
8. Project mencapai DONE.
9. Seluruh proses memiliki task history dan event history.

Manusia tidak perlu mengatur setiap handoff secara manual.

---

## 9. Non-Goals

Belum dibuat pada MVP:

* AI Office visualization
* avatar
* pixel art
* RPG mechanics
* XP/level
* multiplayer
* billing
* SaaS multi-tenant
* banyak provider/model
* agent role yang terlalu banyak

---

## 10. Future Vision

Setelah Agent Runtime stabil, tambahkan:

```text
UI/UX Designer
Visual Designer
Backend Specialist
DevOps
Security
Technical Writer
Researcher
```

Kemudian bangun:

**AI Office**

di mana karakter visual merepresentasikan state agent secara real-time:

```text
THINKING → character thinking
WORKING  → character working
WAITING  → character idle
TESTING  → character testing
DEPLOYING → character at server
DONE → character completed
```

Dengan demikian visualisasi bukan simulasi palsu, tetapi representasi dari aktivitas agent yang benar-benar terjadi di runtime.
