# Peta Sumber untuk Outline Landasan Kepustakaan

Dokumen ini memetakan setiap poin dalam outline Bab 2 ke sumber yang dapat
digunakan. Kutipan berbahasa Inggris dipertahankan dalam bentuk asli. Kutipan
berfungsi sebagai bukti penelusuran; naskah skripsi sebaiknya memparafrasekan
isinya dan memakai kunci sitasi Zotero yang telah diverifikasi.

## A. Bank Kutipan Terverifikasi

### K01 — Definisi jatuh dan fase kejadian

**Sumber:** Becker dkk., *Proposal for a Multiphase Fall Model Based on
Real-World Fall Recordings with Body-Fixed Sensors*, bagian model fase jatuh.

> “Falls can be separated into a pre-fall, falling, impact, resting, and recovery phase.”

Tautan: <https://doi.org/10.1007/s00391-012-0403-6>

### K02 — Definisi *long lie*

**Sumber:** Blackburn dkk., *Exploring the Impact of Experiencing a Long Lie
Fall on Physical and Clinical Outcomes*, bagian pendahuluan.

> “Unable to get up from the floor for over one hour following a fall.”

Tautan: <https://doi.org/10.1016/j.ienj.2022.101148>

### K03 — Tujuan sistem deteksi jatuh

**Sumber:** Igual, Medrano, dan Plaza, *Challenges, Issues and Trends in Fall
Detection Systems*, bagian pendahuluan.

> “An assistive device whose main objective is to alert when a fall event has occurred.”

Tautan: <https://doi.org/10.1186/1475-925X-12-66>

### K04 — Gerakan biasa yang menyerupai jatuh

**Sumber:** Vlaeyen dkk., *Fall Incidents Unraveled*, bagian pembahasan.

> “The distinction between occasional sudden movements (e.g. lie down) and falls is essential.”

Tautan: <https://doi.org/10.1186/1471-2318-13-103>

### K05 — Keterbatasan kamera, *wearable*, dan radar

**Sumber:** Yang dkk., *Rethinking Fall Detection With Wi-Fi*, bagian
pendahuluan.

> “Cameras have the risk of privacy leakage, wearable sensors are intrusive to users and radars are expensive.”

Tautan: <https://doi.org/10.1109/TMC.2022.3188779>

### K06 — Persoalan penggunaan di kondisi nyata

**Sumber:** Igual, Medrano, dan Plaza, bagian abstrak.

> “Challenges regarding performance under real-life conditions, usability, and user acceptance.”

Gunakan K03 dan K06 bersama untuk membatasi klaim manfaat sistem deteksi.

### K07 — Interaksi gelombang, manusia, dan objek

**Sumber:** Liu dkk., *Wireless Sensing for Human Activity: A Survey*, bagian
prinsip pengindraan nirkabel.

> “The wireless signals are reflected by the human body and surrounding objects.”

Tautan: <https://doi.org/10.1109/COMST.2019.2934489>

### K08 — Definisi CSI

**Sumber:** Wang, Wu, dan Ni, *WiFall: Device-Free Fall Detection by Wireless
Networks*, §3.1.

> “CSI is information that estimates the channel properties of a communication link.”

Tautan: <https://doi.org/10.1109/TMC.2016.2557792>

### K09 — CSI, OFDM, dan nilai kompleks

**Sumber:** Yang dkk., *CSI-Based Human Sensing Using Model-Based Approaches:
A Survey*, §2.1.

> “CSI consists of a set of complex values.”

Tautan: <https://doi.org/10.1093/jcde/qwab003>

### K10 — Resolusi CSI pada *subcarrier*

**Sumber:** Wang dkk., *RT-Fall*, bagian pendahuluan.

> “CSI on commercial WiFi devices reveals multipath channel features at the granularity of OFDM subcarriers.”

Tautan: <https://doi.org/10.1109/TMC.2016.2557795>

### K11 — CSI menangkap efek propagasi

**Sumber:** Armenta-Garcia, Gonzalez-Navarro, dan Caro-Gutierrez, *Wireless
Sensing Applications with Wi-Fi Channel State Information*, abstrak.

> “CSI captures multipath effects, attenuations, and phase shifts in signal propagation.”

Tautan: <https://doi.org/10.1016/j.comcom.2024.06.011>

### K12 — Makna amplitudo CSI

**Sumber:** Wang dkk., *A Survey on Human Behavior Recognition Using Channel
State Information*, bagian Amplitude.

> “CSI amplitude is the quantification of the signal power attenuation after multi-path fading.”

Tautan: <https://doi.org/10.1109/ACCESS.2019.2949123>

### K13 — Selisih fase dibandingkan amplitudo

**Sumber:** Wang dkk., *RT-Fall*, abstrak.

> “The CSI phase difference over two antennas is a more sensitive base signal than amplitude.”

K10 dan K13 tidak membuktikan bahwa fase relatif selalu lebih unggul pada
semua perangkat atau lingkungan.

### K14 — Sumber galat fase CSI

**Sumber:** Yang dkk., *CSI-Based Human Sensing Using Model-Based Approaches:
A Survey*, bagian phase calibration.

> “Imperfect synchronization between the sender and receiver also results in some phase errors.”

Galat yang dibahas meliputi SFO, STO, CFO, dan CPO.

### K15 — Offset antarantena tidak selalu hilang

**Sumber:** Tadayon dkk., *On Phase Offsets of 802.11ac Commodity WiFi*,
abstrak.

> “The phase offset between receive antennas is due to random phase rotations.”

Tautan: <https://arxiv.org/abs/2005.03755>

### K16 — Ketergantungan fase pada lingkungan

**Sumber:** Yang dkk., *Rethinking Fall Detection With Wi-Fi*, §2.

> “The CSI phase difference is highly sensitive to the environment.”

K16 harus disandingkan dengan K13 agar pembahasan fase relatif tidak berat
sebelah.

### K17 — Tahapan pemrosesan fase

**Sumber:** Sanam dan Godrich, *Channel Phase Processing in Wireless Networks
for Human Activity Recognition*, abstrak.

> “A CSI phase sanitization method to remove phase impairments.”

Tautan: <https://arxiv.org/abs/2303.16873>

### K18 — Representasi waktu–frekuensi

**Sumber:** Palipana dkk., *FallDeFi*, abstrak.

> “We use the conventional Short-Time Fourier Transform (STFT) to extract time-frequency features.”

Tautan: <https://doi.org/10.1145/3161183>

### K19 — Pengaruh konfigurasi *window*

**Sumber:** Hu dkk., *Challenges in Studying Falls of Community-Dwelling Older
Adults in the Real World*, bagian Practical Consideration.

> “Increasing the window size results in fewer false alarms.”

Tautan: <https://doi.org/10.1109/SMARTCOMP.2017.7946993>

Studi ini mengevaluasi *alarm-suppression window* pada data jatuh nyata. Nilai
ukurannya tidak boleh dipindahkan langsung ke segmentasi CSI, tetapi sumber ini
mendukung prinsip bahwa definisi *window* memengaruhi hasil evaluasi.

### K20 — CSI sebagai indikator aktivitas

**Sumber:** Wang, Wu, dan Ni, *WiFall*, abstrak.

> “WiFall employs physical layer Channel State Information (CSI) as the indicator of activities.”

### K21 — Ketahanan terhadap perpindahan lingkungan

**Sumber:** Hu dkk., *DeFall*, abstrak.

> “Environment-independent fall detection without any retraining procedures when the environment changes.”

Tautan: <https://doi.org/10.1109/JIOT.2021.3116136>

### K22 — Keluaran deteksi MR60FDA2

**Sumber:** Seeed Studio, *Getting Started with MR60FDA2*, bagian Fall Module
API.

> “Returns true if a fall is detected and false if not.”

Tautan: <https://wiki.seeedstudio.com/getting_started_with_mr60fda2_mmwave_kit/>

Datasheet: <https://files.seeedstudio.com/wiki/mmwave-for-xiao/mr60/datasheet/MR60FDA2_Fall_Detection_Module_Datasheet.pdf>

### K23 — Evaluasi per kejadian dan latensi

**Sumber:** *Lightweight Multi-channel Fall Detection on Smartphone
Accelerometers with Probabilistic Calibration and Event-Level Evaluation*,
§2.6.

> “Latency is the time from the actual fall onset to the first alarm raised by the system.”

Tautan: <https://doi.org/10.1007/s11063-026-11851-4>

### K24 — Data jatuh alami dan hasil laboratorium

**Sumber:** Igual, Medrano, dan Plaza, bagian tantangan evaluasi.

> “Most studies did not include real falls of elderly people.”

K24 mendukung pembatasan generalisasi ketika data jatuh diperagakan oleh
subjek sehat.

### K25 — Privasi RF bukan persoalan yang otomatis selesai

**Sumber:** Windl dkk., *Privacy Solution or Menace? Investigating Perceptions
of Radio-Frequency Sensing*, bagian temuan.

> “Participants’ privacy perceptions of RF sensing were highly context-dependent.”

Tautan: <https://www.usenix.org/conference/usenixsecurity25/presentation/windl>

## B. Pemetaan Setiap Poin Outline

### 2.1. Jatuh sebagai Objek Deteksi

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| Pengertian jatuh | Becker dkk.; definisi konsensus dalam artikel | K01 |
| Definisi operasional penelitian | Becker dkk.; Igual dkk. | K01, K03; definisi akhir tetap keputusan operasional penelitian |
| Batas jatuh dan perubahan postur | Vlaeyen dkk.; RT-Fall | K04, K13 |
| Dampak fisik dan klinis | Blackburn dkk. | K02; baca bagian Results dan Discussion |
| Kondisi *long lie* | Blackburn dkk. | K02 |
| Pentingnya pertolongan cepat | Igual dkk.; Blackburn dkk. | K03, K02 |
| Tahap sebelum, ketika, dan setelah jatuh | Becker dkk.; Vlaeyen dkk. | K01 |
| Perubahan posisi dan kecepatan tubuh | Becker dkk.; DeFall | K01, K21 |
| Perbedaan jatuh dan aktivitas sehari-hari | Vlaeyen dkk.; RT-Fall | K04, K13 |
| Duduk cepat | FallDar; RT-Fall | K04; lihat daftar aktivitas normal FallDar dan §3.2 RT-Fall |
| Membungkuk | WiFall; FallDar | K20; tabel aktivitas pada kedua paper |
| Jongkok dan berlutut | FallDar; tinjauan Hu dkk. | K04; daftar aktivitas normal FallDar |
| Berbaring secara sengaja | Vlaeyen dkk. | K04 |
| Aktivitas lain pemicu alarm palsu | FallDar; Igual dkk. | K04, K24 |

### 2.2. Sistem Deteksi Jatuh

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| Prinsip sistem *wearable* | Igual dkk. | K03, K06; bagian Wearable Devices |
| Kelebihan *wearable* | Igual dkk. | bagian Wearable Devices; pengukuran mengikuti tubuh |
| Ketergantungan penggunaan/penempatan | Igual dkk.; RT-Fall | K06; bagian keterbatasan *on-body* RT-Fall |
| Prinsip sistem kamera | Igual dkk.; tinjauan visi 2024 | K05; bagian Computer Vision |
| Kelebihan kamera | Tinjauan visi 2024 | kemampuan menangkap bentuk, postur, dan konteks spasial |
| Pencahayaan dan oklusi | Tinjauan visi 2024; Igual dkk. | bagian Challenges/Limitations |
| Privasi kamera | FallDar; Igual dkk. | K05 |
| Prinsip sistem radio | Liu dkk.; WiFall | K07, K08 |
| Kelebihan sistem radio | WiFall; RT-Fall | K20, K13 |
| Ketergantungan lingkungan | FallDar; DeFall | K16, K21 |
| Perbandingan kebutuhan perangkat | Igual dkk.; FallDar | K05, K06 |
| Ketergantungan pencahayaan | Tinjauan visi 2024; RT-Fall | bagian Related Work |
| Perbandingan privasi | FallDar; Windl dkk. | K05, K25 |
| Alasan memilih Wi-Fi | WiFall; RT-Fall | K20, K10 |

### 2.3. Pengindraan Manusia Berbasis Gelombang Radio

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| Pemancar, penerima, dan lingkungan | Liu dkk.; Yang dkk. 2021 | K07, K09 |
| Tubuh sebagai pengubah kanal | Liu dkk.; Armenta-Garcia dkk. | K07, K11 |
| Pengamatan tanpa sensor pada tubuh | WiFall; RT-Fall | K20, K13 |
| Pemantulan | Liu dkk.; Armenta-Garcia dkk. | K07, K11 |
| Hamburan | Liu dkk. | bagian prinsip propagasi; K07 |
| Difraksi | WiFall, §3.1 | uraian reflection, diffraction, and scattering |
| Penyerapan | Liu dkk. | bagian mekanisme interaksi sinyal |
| Perubahan lintasan akibat gerakan | Armenta-Garcia dkk.; FallDar | K11, K16 |
| Pembentukan *multipath* | RT-Fall; Armenta-Garcia dkk. | K10, K11 |
| Superposisi sinyal pada penerima | DeFall; FallDar | model sinyal pada bagian preliminaries |
| Pengaruh gerak pada panjang lintasan/fase | Yang dkk. 2021; RT-Fall | K09, K13 |
| Pengaruh perubahan lingkungan | FallDar; DeFall | K16, K21 |
| Posisi dan orientasi tubuh | FallDar | §2 Observations and Motivations |
| Jarak terhadap perangkat | WiFall; RT-Fall | bagian eksperimen terhadap lokasi dan jarak |
| Tata letak ruangan | FallDeFi; DeFall | K18, K21 |
| Perbedaan subjek | FallDar | evaluasi cross-user |
| Objek atau orang lain | RT-Fall; FallDar | bagian robustess dan limitations |

### 2.4. Wi-Fi, OFDM, dan CSI

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| Peran pemancar dan penerima | Yang dkk. 2021 | §2.1 dan kerangka sistem |
| Kanal komunikasi nirkabel | WiFall | K08 |
| Pengaruh lingkungan pada penerimaan | Armenta-Garcia dkk. | K11 |
| Pembagian kanal menjadi *subcarrier* | Yang dkk. 2021; RT-Fall | K09, K10 |
| Sinyal pada setiap *subcarrier* | Yang dkk. 2021 | K09 dan Persamaan (1) |
| Respons kanal yang lebih rinci | RT-Fall | K10 |
| Hubungan \(X_k,Y_k,H_k,N_k\) | Yang dkk. 2021; survei Wi-Fi CSI 2023 | bagian channel model; gunakan notasi sumber secara konsisten |
| Definisi CSI | WiFall; Yang dkk. 2021 | K08, K09 |
| CSI per *subcarrier* | RT-Fall | K10 |
| Dimensi *subcarrier*, antena, waktu | Yang dkk. 2021; survei Wi-Fi sensing | bagian CSI representation |
| CSI sebagai nilai kompleks | Yang dkk. 2021 | K09 |
| Amplitudo dan fase CSI | Yang dkk. 2021 | Persamaan (1) dan penjelasannya |

### 2.5. Amplitudo dan Fase CSI

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| Pengertian amplitudo CSI | Wang dkk., survei HAR | K12 |
| Perubahan amplitudo akibat *multipath* | Armenta-Garcia dkk.; Wang dkk. | K11, K12 |
| Pengaruh gerakan pada amplitudo | WiFall; RT-Fall | K20; §4.1 RT-Fall |
| Keterbatasan amplitudo | RT-Fall; FallDeFi | K13, K18 |
| Pengertian fase CSI | Yang dkk. 2021 | K09 dan Persamaan (1) |
| Fase dan panjang lintasan | Liu dkk.; Yang dkk. 2021 | model propagasi dan model Fresnel |
| Perubahan fase akibat gerakan | RT-Fall | K13 |
| Sensitivitas fase | RT-Fall | K13 |
| Perbedaan informasi amplitudo/fase | Yang dkk. 2021; RT-Fall | K09, K13 |
| Sensitivitas terhadap lingkungan | FallDar | K16 |
| Alasan amplitudo menjadi pembanding | WiFall dan RT-Fall | K20, K13 |

### 2.6. Fase Relatif CSI

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| *Phase offset* | RT-Fall; Tadayon dkk. | K14, K15 |
| Ketidaksinkronan Tx–Rx | Yang dkk. 2021 | K14 |
| Pergeseran waktu pencuplikan | Yang dkk. 2021 | pembahasan SFO dan STO setelah K14 |
| Gangguan perangkat keras | Tadayon dkk. | K15 |
| Fase mentah tidak langsung andal | RT-Fall; Yang dkk. 2021 | K14 |
| Selisih fase dua antena | RT-Fall | K13 |
| Galat bersama yang dapat berkurang | RT-Fall | §4.2.1 Phase Calibration |
| Persyaratan konfigurasi antena | RT-Fall | rancangan 1 Tx dan 2 Rx |
| Fase mentah vs fase relatif | RT-Fall | §4.2 dan Gambar 5 |
| Perubahan fase relatif terhadap waktu | RT-Fall | §4.2–§5.1 |
| Hubungan temporal dengan gerak | RT-Fall | K13 |
| Pola selama jatuh | RT-Fall | §4.2.4 |
| Perbedaan jatuh/non-jatuh | RT-Fall; FallDar | K13, K16 |
| Alasan memilih fase relatif | RT-Fall | K13, tetapi wajib dibatasi oleh K16 |
| Ketergantungan konfigurasi antena | Tadayon dkk.; RT-Fall | K15, K13 |
| Pengaruh posisi/orientasi | FallDar | K16 |
| Pengaruh *multipath* | FallDar; Armenta-Garcia dkk. | K16, K11 |
| Pembungkusan/ambiguitas fase | Yang dkk. 2021; Sanam dan Godrich | K14, K17 |

### 2.7. Pengolahan dan Representasi CSI

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| Data hilang dan pencilan | Armenta-Garcia dkk.; survei CSI 2023 | bagian Data Preprocessing |
| Penyaringan derau | Sanam dan Godrich | K17 |
| Pemilihan/penggabungan *subcarrier* | WiFall; FallDeFi | metode PCA dan stream/subcarrier selection |
| Normalisasi | FallDeFi; survei CSI 2023 | bagian preprocessing |
| Penanganan pembungkusan fase | Sanam dan Godrich; Yang dkk. 2021 | K17, bagian phase calibration |
| Segmentasi aktivitas | RT-Fall | varians selisih fase untuk segmentasi |
| Ukuran dan pergeseran *window* | Hu dkk. 2017; FallDar | K19; §7.4 FallDar |
| Hubungan *window* dan durasi jatuh | Becker dkk.; FallDar | K01; §7.4 FallDar |
| Korelasi antar-*window* | Hu dkk. 2017; artikel evaluasi per kejadian 2026 | K19, K23 |
| Susunan waktu/subcarrier/antena | Yang dkk. 2021 | K09 |
| Pembentukan perubahan fase relatif | RT-Fall | K13 dan §4.2.1 |
| Fitur/deret waktu masukan | RT-Fall; FallDar | bagian feature extraction |
| Perubahan temporal amplitudo | WiFall; RT-Fall | K20, §4.1 RT-Fall |
| Pemilihan/agregasi amplitudo | WiFall; FallDeFi | metode masing-masing |
| Representasi pembanding | RT-Fall | K13 |
| Kesetaraan pengolahan | bukan fakta literatur tunggal | harus ditetapkan sebagai prinsip desain eksperimen di Bab 3 |

### 2.8. Klasifikasi Jatuh dan Non-Jatuh

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| Jatuh sebagai kelas positif | Hu dkk. 2024; Igual dkk. | bagian metrik evaluasi |
| Non-jatuh sebagai kelas negatif | Hu dkk. 2024; WiFall | bagian evaluasi dan dataset |
| Hubungan definisi dan anotasi | Hu dkk. 2024 | pembahasan variasi definisi jatuh |
| Pendekatan berbasis fitur | WiFall; FallDeFi | K20, K18 |
| Pendekatan deret waktu | RT-Fall; FallDar | K13, bagian model |
| Model lain hanya jika relevan | tinjauan metodologis | keputusan struktur penulisan, bukan klaim empiris |
| Keluaran jatuh/non-jatuh | WiFall; RT-Fall | bagian system overview |
| Prediksi *window* vs alarm kejadian | Hu dkk. 2017; evaluasi 2026 | K19, K23 |
| Penggabungan prediksi berurutan | evaluasi per kejadian 2026 | bagian event-level post-processing |

### 2.9. MR60FDA2 sebagai Sensor Referensi

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| Teknologi sensor | datasheet Seeed Studio | radar 60 GHz; tautan pada K22 |
| Jenis keluaran | dokumentasi API | K22 |
| Kemampuan relevan | datasheet dan Wiki | keberadaan, jatuh, ambang, sensitivitas |
| Membantu menentukan kejadian/waktu | dokumentasi keluaran | K22; penerapannya harus dijelaskan di Bab 3 |
| Menjadi pembanding keluaran | dokumentasi keluaran | K22 |
| Mendukung pemeriksaan label | keputusan protokol penelitian | jangan mengklaim sensor sebagai label mutlak |
| Bukan *ground truth* absolut | tidak dijamin oleh datasheet | inferensi metodologis dari sifat keluaran biner perangkat |
| Potensi keterlambatan/kesalahan | parameter sensitivitas dan rata-rata frame | dokumentasi Wiki; harus diuji secara empiris |
| Pembedaan tiga keluaran | prinsip desain penelitian | label acuan, keluaran MR60FDA2, dan prediksi CSI harus disimpan terpisah |

### 2.10. Dasar Evaluasi

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| TP, FP, TN, FN | Hu dkk., *Radar-Based Fall Detection: A Survey* | bagian evaluation metrics |
| *Precision* | Hu dkk.; FallDeFi | definisi metrik pada bagian evaluasi |
| *Recall*/sensitivitas | Hu dkk.; RT-Fall | bagian performance metrics |
| *Specificity* | Hu dkk.; RT-Fall | bagian performance metrics |
| F1 | Hu dkk.; FallDeFi | bagian evaluasi |
| FPR | Hu dkk.; DeFall | bagian evaluasi |
| Keterbatasan akurasi | artikel evaluasi 2026 | membahas F1/AUPRC untuk ketidakseimbangan kelas |
| Evaluasi per-*window* | artikel evaluasi 2026 | bagian window-level metrics |
| Evaluasi per kejadian | artikel evaluasi 2026 | bagian event-level metrics |
| Latensi | artikel evaluasi 2026 | K23 |
| Alasan membedakan unit evaluasi | Hu dkk. 2017; artikel evaluasi 2026 | K19, K23 |

### 2.11. Penelitian Terkait

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| Deteksi berbasis amplitudo | WiFall | K20 |
| Representasi amplitudo | WiFall; FallDeFi | K20, K18 |
| Metode klasifikasi amplitudo | WiFall; FallDeFi | one-class SVM, RF, dan feature-based classifier |
| Keterbatasan amplitudo | RT-Fall; FallDar | K13, K16 |
| Deteksi berbasis fase | RT-Fall | K13 |
| Koreksi/pembentukan fase | RT-Fall; Yang dkk. 2021 | K14, §4.2.1 RT-Fall |
| Metode deteksi fase | RT-Fall | variance-based segmentation dan klasifikasi fitur |
| Keterbatasan fase | Tadayon dkk.; FallDar | K15, K16 |
| Perubahan ruangan | FallDeFi; DeFall | K18, K21 |
| Posisi dan orientasi | FallDar | K16 |
| Generalisasi pengguna | FallDar | evaluasi cross-user |
| Batas eksperimen terkontrol | Igual dkk. | K24 |
| Perbandingan perangkat/data/metode | semua paper terkait | sajikan sebagai tabel sintesis, bukan perbandingan angka mentah |

### 2.12. Sintesis dan Celah Penelitian

| Poin outline | Sumber utama | Bukti |
|---|---|---|
| CSI merepresentasikan perubahan kanal | WiFall; Armenta-Garcia dkk. | K08, K11 |
| Amplitudo dan fase berbeda | Yang dkk. 2021; RT-Fall | K09, K13 |
| Fase mentah bermasalah | Yang dkk. 2021; Tadayon dkk. | K14, K15 |
| Fase relatif mengurangi sebagian galat | RT-Fall | §4.2.1; jangan menulis “menghilangkan semua galat” |
| Fase relatif sensitif terhadap gerak | RT-Fall | K13 |
| Fase relatif sensitif terhadap lingkungan | FallDar | K16 |
| Pengaruh aktivitas, subjek, orientasi, lingkungan | FallDar; DeFall | K16, K21 |
| Dominasi amplitudo atau fitur gabungan | WiFall, FallDeFi, RT-Fall | K20, K18, K13 |
| Perbandingan dalam kondisi identik | RT-Fall paling dekat | K13; celah harus dibatasi pada konfigurasi penelitian sekarang |
| Ketergantungan perangkat | Tadayon dkk.; survei CSI | K15, K11 |
| Keterbatasan jumlah subjek/lingkungan | Igual dkk.; FallDar | K24 dan limitations FallDar |
| Perbedaan definisi/evaluasi | Hu dkk. 2024; Igual dkk. | bagian challenges |

## C. Rumusan Celah yang Didukung Bukti

RT-Fall sudah menggunakan selisih fase antarantena. Karena itu, penelitian ini
tidak boleh mengklaim sebagai penggunaan fase relatif pertama untuk deteksi
jatuh. Rumusan yang lebih defensibel adalah:

> Literatur menunjukkan bahwa selisih fase CSI berpotensi lebih sensitif
> terhadap aktivitas dibandingkan amplitudo pada konfigurasi tertentu. Namun,
> fase relatif tetap dipengaruhi oleh galat perangkat dan perubahan lingkungan.
> Oleh karena itu, belum diketahui apakah perubahan temporal fase relatif
> menghasilkan kinerja deteksi jatuh yang lebih baik daripada perubahan
> amplitudo pada perangkat, konfigurasi antena, aktivitas, subjek, dan kondisi
> pengujian yang digunakan dalam penelitian ini.

Rumusan tersebut ditopang bersama oleh K13, K14, K15, dan K16.

## D. Sumber yang Masih Perlu Ditambahkan ke Zotero

Sebelum bagian ini dipakai dalam draf akhir, periksa atau tambahkan sumber
berikut ke koleksi Zotero dan salin `citationKey` yang dihasilkan Better
BibTeX:

1. Becker dkk. — multiphase fall model based on real-world falls.
2. Vlaeyen dkk. — real-life fall phases and fall-like movements.
3. Yang dkk. — model-based CSI sensing survey.
4. Armenta-Garcia dkk. — CSI applications and preprocessing survey.
5. Wang dkk. — survey on human behavior recognition using CSI.
6. Tadayon dkk. — phase offsets of commodity Wi-Fi.
7. Sanam dan Godrich — CSI phase processing.
8. Hu dkk. — real-world fall data, alarm windows, and false alarms per hour.
9. Dokumentasi dan datasheet MR60FDA2.
10. Artikel evaluasi per kejadian 2026, jika benar-benar akan digunakan.

Sumber yang sudah tercantum dalam draf proyek tetap perlu diverifikasi terhadap
field `citationKey` Zotero sebelum teks Bab 2 diselesaikan.
