# Integrasi Zotero

Dokumen ini menjelaskan cara berinteraksi dengan library Zotero lokal dari
repo ini: membaca koleksi/items, mengimpor paper lengkap dengan PDF, dan
melengkapi metadata. Semua contoh sudah teruji pada Zotero 10.0.1
(Flatpak `org.zotero.Zotero`) dengan data di `/home/khaelano/Zotero/`.

## Prasyarat

- Zotero harus sedang berjalan. Dari shell:
  `setsid flatpak run org.zotero.Zotero` (perlu escalation/approval).
- API lokal aktif di `http://localhost:23119`
  (pref `extensions.zotero.httpServer.localAPI.enabled = true`).
- Sandbox memblokir koneksi ke localhost: semua `curl`/HTTP ke Zotero
  dijalankan dengan `sandbox_permissions: "require_escalated"`.

## Arsitektur API

- `/api/...` — API lokal resmi, **read-only** (satu-satunya pengecualian
  `/api/local/authorize` untuk mendapatkan API key).
- `/connector/...` — jalur tulis resmi (dipakai ekstensi browser Zotero),
  **tanpa API key**. Endpoint yang relevan: `saveItems`, `updateSession`,
  `saveAttachment`.
- Better BibTeX (jika terpasang) merespons di
  `GET /better-bibtex/cayw?probe=true` → `ready`. Debug bridge
  (`/debug-bridge/execute`) tidak aktif secara default.

## Membaca library

```bash
# Daftar koleksi (metadata berisi key + jumlah item)
curl -s "http://localhost:23119/api/users/0/collections?format=json"

# Item top-level dalam satu koleksi
curl -s "http://localhost:23119/api/users/0/collections/EFJFE3FJ/items/top?format=json&limit=50"

# Semua item top-level library (total ada di header total-results)
curl -s "http://localhost:23119/api/users/0/items/top?format=json&limit=100"

# Anak dari satu item (mis. lampiran PDF)
curl -s "http://localhost:23119/api/users/0/items/{KEY}/children?format=json"

# Pencarian berdasarkan judul/pencipta/tahun
curl -s "http://localhost:23119/api/users/0/items/top?q=fall%20detection&qmode=titleCreatorYear&format=json"
```

Contoh cek duplikat sebelum import: `q=Doppler` / `q=radar` → hasil kosong
berarti paper belum ada di library.

## Menulis: import paper + PDF

Alur resminya adalah **session**: `saveItems` → (opsional) `updateSession`
untuk mengarahkan/memindahkan item ke koleksi tertentu → `saveAttachment`
untuk tiap PDF. `id` pada tiap item adalah connector key yang dipakai
`saveAttachment` untuk menemukan parent-nya.

### 1. Buat item (POST /connector/saveItems)

```bash
curl -s -X POST "http://localhost:23119/connector/saveItems" \
  -H "Content-Type: application/json" \
  -d '{
    "sessionID": "sid-import-1",
    "uri": "https://ieeexplore.ieee.org/document/10420485",
    "items": [
      {
        "id": "conn-01",
        "itemType": "journalArticle",
        "title": "Radar-Based Fall Detection: A Survey",
        "creators": [
          {"creatorType": "author", "firstName": "Shuting", "lastName": "Hu"}
        ],
        "date": "2024",
        "publicationTitle": "IEEE Robotics & Automation Magazine",
        "volume": "31",
        "issue": "3",
        "pages": "170-185",
        "DOI": "10.1109/MRA.2024.3352851",
        "url": "https://ieeexplore.ieee.org/document/10420485",
        "collections": ["EFJFE3FJ"],
        "extra": "Imported by Codex (radio-fall-detection RAG)"
      }
    ]
  }'
```

Respon sukses: `201`. Kolom `itemType` yang umum: `journalArticle`,
`conferencePaper`. Creator: `creatorType: "author"`, nama dipecah
`firstName`/`lastName`.

### 2. Arahkan session ke koleksi (POST /connector/updateSession)

Secara default item tersimpan ke koleksi yang sedang **dipilih di UI Zotero**
(`getSaveTarget`). Field `collections` pada item juga dihormati, tetapi cara
paling pasti adalah update session:

```bash
curl -s -X POST "http://localhost:23119/connector/updateSession" \
  -H "Content-Type: application/json" \
  -d '{"sessionID": "sid-import-1", "target": "C13"}'
```

`target` = treeViewID `C<collectionID>` dengan **angka internal** (bukan key
API). Ambil dari sqlite secara read-only (aman dibaca saat Zotero berjalan;
**jangan menulis** sqlite selama Zotero hidup):

```bash
python3 -c "import sqlite3; c=sqlite3.connect('file:/home/khaelano/Zotero/zotero.sqlite?mode=ro&immutable=1', uri=True); print(c.execute(\"SELECT collectionID, collectionName, parentCollectionID, key FROM collections\").fetchall())"
```

Perhatikan: koleksi yang sudah di-delete ada di tabel `deletedCollections` —
pastikan memakai `collectionID` dari koleksi yang masih aktif. Contoh nyata:
koleksi "Skripskuy" aktif = ID 13 (key `EFJFE3FJ`), sedangkan ID 12 dengan
nama sama sudah di-delete.

### 3. Attach PDF (POST /connector/saveAttachment)

Body request = byte file PDF; metadata parent ada di header `X-Metadata`:

```bash
curl -s -X POST "http://localhost:23119/connector/saveAttachment" \
  -H "Content-Type: application/pdf" \
  -H "X-Metadata: {\"sessionID\":\"sid-import-1\",\"parentItemID\":\"conn-01\",\"title\":\"Radar-Based Fall Detection: A Survey\",\"url\":\"https://ieeexplore.ieee.org/document/10420485\"}" \
  --data-binary "@Resources/Papers/radar-based-fall-detection-survey-2024.pdf"
```

Respon sukses: `201`. Zotero membuat attachment dengan nama otomatis
(mis. `Hu et al. - 2024 - Radar-Based Fall Detection A Survey.pdf`).

### Detail penting

- Session kedaluwarsa ±10 menit (1 menit jika >10 session aktif). Kerjakan
  `saveItems` → `updateSession` → `saveAttachment` dalam satu rangkaian
  berurutan.
- `saveItems` bisa menerima banyak item sekaligus (terbukti 17 item dalam
  satu request).
- Verifikasi hasil: baca koleksi lewat API, lalu cek children tiap item
  untuk memastikan PDF terpasang.
- Otorisasi `/api/local/authorize` (klik "Allow" di Zotero) hanya diperlukan
  untuk mutasi di luar endpoint connector; alur di atas tidak
  membutuhkannya.

## Melengkapi metadata dari sumber eksternal

`tools/index.json` hanya memuat judul/tahun/DOI/URL. Untuk import yang rapi,
penulis dan venue diambil dari OpenAlex (fallback Crossref):

- Bulk berdasarkan DOI (pipe `|` = OR):
  `https://api.openalex.org/works?per-page=100&filter=doi:10.1|10.2|...`
- Tanpa DOI, cari judul:
  `https://api.openalex.org/works?per-page=8&filter=title.search:<judul>,publication_year:<tahun>`
- Fallback DOI: `https://api.crossref.org/works/<doi>`

Perbaikan manual yang pernah diperlukan (bahan QA):

- Tipe: "Biomedical Signal Processing and Control" dan jurnal IEEE
  (Transactions/Magazine/Open Journal) harus `journalArticle`, bukan
  `conferencePaper`.
- Venue konferensi sering kosong di OpenAlex: EMBC, PervasiveHealth, IES,
  IECON, ICECAI, AMS — isi manual dari halaman pertama PDF.
- Tahun lebih baik memakai tahun terbit jurnal (mis. TBME 2015, JBHI 2021)
  daripada tahun online-first OpenAlex.
- Nama penulis bisa terbalik di OpenAlex (mis. "Liu Liang" → "Liang Liu").

## Rekap praktik: import 18 paper (2026-09-01)

1. Metadata 18 paper diambil dari OpenAlex/Crossref → `/tmp/zotero_meta_final.json`.
2. `saveItems` (18 item, `collections: ["EFJFE3FJ"]`) → 201.
3. `updateSession` target `C13` (Skripskuy) → 200.
4. `saveAttachment` untuk 18 PDF → 201 semua.
5. Verifikasi: koleksi Skripskuy berisi 18 item, masing-masing 1 lampiran PDF.
