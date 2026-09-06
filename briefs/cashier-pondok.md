# Aplikasi Kasir Pondok Pesantren Taqribbussunnah

## Visi

Aplikasi kasir (Point of Sale) sederhana untuk koperasi/toko di lingkungan Pondok Pesantren Taqribbussunnah. Dirancang untuk digunakan oleh ustadz, pengurus, atau santri yang bertugas mengelola kasir harian.

---

## Problem

- Transaksi koperasi/toko pondok masih pakai buku catatan manual
- Sulit melacak stok barang, pendapatan, dan pengeluaran harian
- Tidak ada laporan keuangan yang otomatis
- Hanya perlu komputer/laptop biasa — tidak perlu printer struk

---

## Target User

- **Primary:** Pengurus koperasi pondok / ustadz yang bertugas kasir
- **Secondary:** Pengawas keuangan pondok (untuk lihat laporan)
- **MVP:** 1 user aktif di 1 device

---

## Fitur Utama

### 1. Manajemen Produk
- CRUD produk (nama, harga jual, stok, satuan)
- Kategori: Makanan, Minuman, Alat Tulis, Kebersihan, Lainnya
- Foto opsional (opsional untuk MVP)
- Cari & filter produk

### 2. Transaksi Kasir
- Pilih produk → qty → subtotal
- Keranjang belanja (add, update qty, remove)
- Hitung total otomatis
- Metode bayar: Tunai
- Hitung kembalian otomatis
- Simpan transaksi ke database

### 3. Riwayat Transaksi
- Daftar transaksi harian
- Detail per transaksi (list item, total, waktu)
- Filter berdasarkan tanggal
- Batalkan transaksi (dengan catatan)

### 4. Laporan Keuangan
- Ringkasan harian: total penjualan, total item terjual
- Ringkasan bulanan: grafik sederhana
- Laba/rugi sederhana (harga jual - harga beli)
- Export ke CSV

### 5. Manajemen Stok
- Stok berkurang otomatis saat transaksi
- Notifikasi stok menipis (< 5 item)
- History perubahan stok

---

## Technical Requirements

- **Backend:** Python Flask
- **Frontend:** HTML + CSS + vanilla JavaScript (no frameworks)
- **Database:** SQLite
- **Testing:** pytest untuk backend
- **No printer integration** (MVP)

---

## UI Requirements

- Tampilan bersih, sederhana, mudah dipahami
- Warna: Biru navy (#1a365d) sebagai primary
- Font: Sistem default, minimum 14px untuk keterbacaan
- Responsive: bisa dibuka di laptop (1366x768) atau tablet
- Layout: Sidebar navigasi + area konten utama

---

## Constraints

- Tidak perlu login untuk MVP (1 device, 1 user)
- Single-page feel (toggle views via JavaScript)
- Tidak perlu framework CSS
- Semua kode jalan dengan `pip install flask` saja
- Offline-first: semua data lokal, tidak perlu internet

---

## Acceptance Criteria

1. ✅ User bisa tambah, edit, hapus produk
2. ✅ User bisa pilih produk ke keranjang
3. ✅ User bisa ubah qty item di keranjang
4. ✅ User bisa hapus item dari keranjang
5. ✅ Total & kembalian dihitung otomatis
6. ✅ Transaksi tersimpan ke database
7. ✅ Riwayat transaksi bisa dilihat per hari
8. ✅ Detail transaksi menampilkan list item
9. ✅ Laporan harian menampilkan total penjualan
10. ✅ Stok berkurang otomatis setelah transaksi
11. ✅ Notifikasi stok menipis muncul
12. ✅ Semua data persist setelah refresh
13. ✅ Aplikasi jalan dengan `python app.py`
14. ✅ Semua test pytest PASS

---

## File Structure (Expected Output)

```
projects/aplikasi-kasir-pondok/
├── app.py              # Main Flask app
├── core.py             # Core business logic
├── models.py           # SQLite models
├── templates/
│   └── index.html      # Single page app
├── static/
│   ├── style.css       # Styles
│   └── app.js          # Frontend logic
├── test_core.py        # pytest tests
├── requirements.txt    # Dependencies
├── brief.md            # This file
└── README.md           # Setup instructions
```
