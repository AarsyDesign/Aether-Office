# Panduan Aset Kustom Aether Office (Game Dashboard)

Selamat datang di direktori aset kustom Aether Office!
Game Dashboard Aether Office sudah memiliki aset visual prosedural bawaan (pixel art SVG & 8-bit Web Audio synthesizer) yang langsung berfungsi tanpa konfigurasi tambahan.

Namun, jika Anda ingin menambahkan atau memilih gambar, karakter, atau suara kustom, Anda dapat meletakkan berkas aset di dalam direktori ini sesuai struktur berikut.

---

## Struktur Folder Aset

```text
ui/assets/custom/
├── avatars/          # Foto / sprite pixel art karakter karyawan
│   ├── default.png   # Avatar default umum (rekomendasi: 64x64 atau 128x128 px)
│   ├── engineering_001.png  # Avatar spesifik per ID karyawan
│   ├── product_001.png
│   └── ...
├── rooms/            # Tekstur lantai / wallpaper ruangan
│   ├── floor_tile.png   # Ubin lantai kantor (rekomendasi: 32x32 atau 64x64 px)
│   └── wall_tile.png
├── logo/             # Logo kustom kantor / perusahaan
│   └── logo.png      # Logo retro (rekomendasi: rasio 1:1 atau banner)
└── audio/            # Musik latar (BGM) atau efek suara kustom
    ├── bgm.mp3       # Musik latar (opsional, loop)
    └── coin.wav      # Efek suara saat task selesai
```

---

## Rekomendasi Format & Ukuran Aset

| Tipe Aset | Format Disarankan | Ukuran Disarankan | Keterangan |
| :--- | :--- | :--- | :--- |
| **Avatar Karyawan** | `.png` (transparan) | `64x64` s/d `128x128` | Sprite pixel art (bisa dari itch.io, Kenney.nl, atau OpenGameArt). Nama berkas sesuai ID karyawan (misal `engineering_001.png`) |
| **Logo Kantor** | `.png` (transparan) | `128x128` s/d `256x256` | Tampil di pojok kiri atas HUD |
| **Ubin Lantai** | `.png` | `32x32` / `64x64` | Seamless tile untuk lantai ruangan kantor |
| **Audio BGM** | `.mp3` / `.ogg` | Bebas (< 5MB) | Musik retro 8-bit / chiptune |

---

## Sumber Rekomendasi Aset Gratis (Pixel Art)

1. **Kenney.nl**: [Kenney Game Assets (Micro Studio / Roguelike / RPG)](https://kenney.nl/assets) - Bebas hak cipta (CC0).
2. **Itch.io Game Assets**: Cari tag `pixel-art`, `office`, `top-down-characters`.
3. **OpenGameArt.org**: Koleksi sprite RPG karakter dan tileset kantor retro.

> **Catatan Sistem:**
> Jika folder ini kosong, Game Dashboard secara otomatis merender karakter dan kantor menggunakan procedural SVG Pixel Art bawaan dengan animasi dinamis, sehingga Anda tetap mendapatkan pengalaman visual game yang memukau!
