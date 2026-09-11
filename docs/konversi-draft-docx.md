# Konversi Draf Markdown ke DOCX

Skrip `tools/build_draft_docx.py` mengubah satu atau beberapa file Markdown
yang memakai sitasi Pandoc menjadi DOCX. Citation key divalidasi langsung
terhadap field `citationKey` di database Zotero, kemudian metadata item yang
benar-benar disitasi diekspor ke CSL-JSON. Pandoc/Citeproc mengubah sitasi
tersebut menjadi sitasi penulis–tahun dan menghasilkan daftar pustaka.

## Prasyarat

- Zotero dengan Better BibTeX dan field `citationKey`.
- Database Zotero di `~/Zotero/zotero.sqlite`.
- Style CSL di `~/Zotero/styles/harvard-cite-them-right.csl`.
- Pandoc tersedia di `PATH`.

Lokasi database dan style dapat diganti dengan `--zotero-db` dan `--csl`.

## Penggunaan

Dari root repository, perintah berikut membangun gabungan draf Bab 1–3 pada
`draft/naskah-bab-1-3.docx`:

```bash
python3 tools/build_draft_docx.py
```

Validasi citation key tanpa membuat DOCX:

```bash
python3 tools/build_draft_docx.py --check
```

Mengonversi draf lain:

```bash
python3 tools/build_draft_docx.py \
  draft/pendahuluan.md draft/landasan-kepustakaan.md \
  --output draft/bab-1-2.docx \
  --title "Deteksi Jatuh Berbasis Radar Doppler" \
  --subtitle "Draf Bab 1–2"
```

Gunakan citation key Zotero persis seperti berikut:

```markdown
Radar Doppler dapat digunakan untuk mendeteksi jatuh [@huRadarBasedFallDetection2024].
```

Skrip akan berhenti jika ada citation key yang tidak ditemukan di Zotero.
Daftar pustaka tidak perlu ditulis manual di Markdown.

## Catatan

- Secara default, setiap file input dimulai pada halaman baru.
- Gunakan `--no-chapter-breaks` jika beberapa file harus mengalir tanpa page break.
- DOCX hasil konversi perlu dirender ulang setelah perubahan pada draf atau style
  untuk memeriksa layout secara visual.
