# WRITING.md — Panduan Gaya Penulisan Laporan

Dokumen ini merangkum esensi gaya penulisan artikel-artikel referensi yang
digunakan dalam penelitian ini, beserta contoh rangkaian kata dan pola kalimat
yang dapat dipakai saat menulis laporan. Panduan ini ditulis dalam bahasa
Indonesia, tetapi setiap pola disertai contoh asli dari artikel berbahasa
Inggris agar mudah ditelusuri kembali ke sumbernya.

## 1. Artikel yang Dianalisis

| Artikel (nama pendek) | Ciri gaya yang dianalisis |
| --------------------- | ------------------------- |
| Hybrid 1D-CNN-LSTM for Early Leakage Detection in Supercritical Boilers (Pan & Yang, 2025) | Abstrak, pendahuluan, hasil, ambang batas adaptif, kesimpulan |
| Real-World Steam Powerplant Boiler Tube Leakage Detection Using Hybrid Deep Learning (Khalid dkk., 2024) | Pendahuluan, metodologi, hasil, trade-off, kesimpulan |
| Opt-TCAE (Kim dkk., 2023) | Pendahuluan, teori, kontribusi, batasan metode |
| Data Driven Leakage Detection and Classification of a Boiler Tube (Sohaib & Kim, 2019) | Metode, hasil, perbandingan algoritma, kesimpulan |
| Intelligent Steam Power Plant Boiler Waterwall Tube Leakage Detection (Khalid dkk., 2020) | Pendahuluan, metodologi bertahap |
| Leakage Detection of Steam Boiler Tube Using PCA (Yu dkk., 2016) | Definisi masalah, metode statistik, hasil |
| Advances in FDD for TPPs: A Review (Khalid dkk., 2023) | Abstrak review, klasifikasi metode, kesimpulan |
| A Pipeline Leakage Detection Method Using Enhanced SVM-based AE (Yuan dkk., 2026) | Abstrak, kontribusi, hasil dengan standar deviasi |
| Empirical Evaluation of Gated Recurrent Neural Networks (Chung dkk., 2014) | Abstrak perbandingan, kesimpulan yang hati-hati |
| Learning Phrase Representations using RNN Encoder-Decoder (Cho dkk., 2014) | Pendahuluan, kontribusi, kesimpulan |
| Gradient-Based Learning Applied to Document Recognition (LeCun dkk., 1998) | Latar belakang teori, penjelasan konsep |
| Deteksi Kebocoran Pipa Air Menggunakan Machine Learning (paper Indonesia) | Diksi akademik Indonesia, pelaporan hasil |

## 2. Esensi Gaya Penulisan

### 2.1. Satu Paragraf, Satu Ide

Setiap paragraf dimulai dari kalimat utama yang menyatakan ide pokok, lalu
diikuti penjelasan, bukti atau contoh, dan diakhiri kalimat penutup yang
menyambung ke paragraf berikutnya. Artikel referensi hampir tidak pernah
mencampur dua ide besar dalam satu paragraf.

### 2.2. Alur Piramida: dari Umum ke Khusus

Pendahuluan bergerak dari konteks luas (industri, statistik kebocoran) ke
masalah spesifik, lalu ke celah penelitian, dan berakhir pada kontribusi
penelitian. Hasil bergerak dari metrik umum ke angka spesifik lalu ke
interpretasi.

### 2.3. Kalimat Pendek, Langsung, dan Satu Makna

Artikel-artikel referensi menggunakan kalimat yang ringkas. Satu kalimat
menyatakan satu fakta. Pola umumnya: subjek (model/metode) + kata kerja
(menghasilkan, mencapai, menunjukkan) + objek (angka/hasil). Gaya ini sejalan
dengan kaidah Simplified Technical English yang dipakai di laporan ini.

### 2.4. Objektivitas dan Kehati-hatian (Hedging)

Klaim dibatasi dengan kata seperti "dapat", "cenderung", "sekitar",
"kemungkinan", "sejauh pengetahuan penulis". Artikel referensi tidak
menulis klaim mutlak kecuali hasil benar-benar konsisten.

### 2.5. Angka Selalu Disertai Konteks dan Sumber

Setiap angka statistik industri diberi sumber. Setiap angka hasil diberi
konteks percobaan (jumlah sampel, seed, dataset) dan pembanding.

### 2.6. Tabel dan Gambar Dikenalkan oleh Kalimat Sebelumnya

Tidak ada tabel atau gambar yang muncul tanpa kalimat pengantar. Pola
standarnya: "Hasil disajikan pada tabel berikut" atau "Gambar N menunjukkan
...".

## 3. Struktur Tiap Bagian dan Pola Kalimat

### 3.1. Abstrak

Abstrak artikel referensi bergerak dalam lima langkah:

1. Konteks dan pentingnya masalah.
2. Keterbatasan/celah metode yang ada.
3. Metode yang diusulkan dan data yang digunakan.
4. Hasil kuantitatif utama.
5. Pernyataan kontribusi/kegunaan.

Contoh pola asli (Pan & Yang, 2025):

> "Under the high-temperature and high-pressure steam conditions ... this leads
> to frequent pipeline leakage failures ... The results show that ... the leak
> detection parameters corrected by neural networks exhibit faster response
> times and significantly lower false alarm rates."

Pola Indonesia yang dapat dipakai:

> "Kebocoran tube water wall merupakan penyebab utama ... Pada kondisi
> tersebut, metode ... memiliki keterbatasan ... Penelitian ini mengusulkan ...
> Hasil menunjukkan ... Model yang diusulkan mendeteksi ... dengan False Alarm
> Rate ... Waktu deteksi ini ... lebih awal dibandingkan ..."

### 3.2. Pendahuluan

Struktur pendahuluan yang konsisten di semua artikel:

1. **Konteks luas** — peran PLTU, pentingnya keandalan, dengan statistik
   bersumber (misalnya 54% forced outage, biaya USD 2–10 juta).
2. **Definisi masalah** — kebocoran tube, dampaknya, mengapa deteksi dini
   penting.
3. **Tinjauan literatur per keluarga metode** — setiap studi dijelaskan dalam
   satu-dua kalimat dengan pola "penulis + metode + hasil", diakhiri
   keterbatasan studi tersebut.
4. **Pernyataan celah** — diawali "However", "Despite", "Nevertheless".
5. **Kontribusi** — diawali "This paper/study proposes ...", dirinci menjadi
   poin kontribusi.
6. **Struktur artikel** — "Artikel ini disusun sebagai berikut. Bagian 2
   menjelaskan ...".

Contoh pola tinjauan literatur (Khalid dkk., 2024):

> "Kim et al. [21] proposed an acoustic-emission-based diagnostic system
> utilizing SVMs ... with high accuracy during operation. Park et al. [22]
> developed a machine-learning-based fault-detection approach ... However,
> these systems tend to be rigid and struggle to adapt to unforeseen
> scenarios."

Pola Indonesia yang dapat dipakai:

> "Pan dan Yang [@panHybrid1DCNNLSTMEarly2025] mengusulkan arsitektur 1D-CNN-LSTM
> yang mencapai akurasi 99,14%. Khalid dkk. [@khalidRealWorldSteamPowerplant2024]
> mengembangkan model hibrida CNN-SVM ... Namun, kedua studi tersebut
> menggunakan data berlabel sehingga tidak dapat diterapkan langsung pada
> kondisi kebocoran yang langka."

### 3.3. Tinjauan Pustaka dan Teori

Pola penjelasan teori yang dipakai artikel referensi:

1. Definisi konsep ("X merupakan ... yang digunakan untuk ...").
2. Mekanisme kerja ("Cara kerja X dimulai dari ...").
3. Persamaan bernomor, lalu penjelasan setiap simbol ("di mana X adalah ...,
   Y adalah ..., dan Z adalah ...").
4. Alasan penggunaan dalam penelitian ("Dalam penelitian ini, X digunakan
   karena ...", "Dibandingkan dengan ..., X mencegah ...").

Contoh pola asli (Real-World, 2024):

> "The Min–Max normalization is defined by the following equation: ...
> where X is the raw data point, X_min is the minimum value ... Compared with
> methods based on mean and variance, Min–Max normalization prevents larger
> sensor values from dominating the feature space."

Pola Indonesia yang dapat dipakai:

> "Standarisasi z-score mengubah data sehingga memiliki rata-rata nol dan
> standar deviasi satu. Nilai z dihitung menggunakan persamaan berikut.
> di mana x adalah data asli, μ adalah rata-rata data pelatihan, dan s adalah
> standar deviasi data pelatihan. Metode ini dipilih karena ..."

### 3.4. Metodologi

Ciri metodologi artikel referensi:

- Diawali gambaran umum bertahap: "Metode yang diusulkan terdiri atas empat
  tahap utama. Tahap pertama ... Tahap kedua ...".
- Setiap tahap diberi subbagian sendiri dan dijelaskan dengan urutan
  masukan-proses-keluaran.
- Konfigurasi eksperimen dilaporkan eksplisit: jumlah data, pembagian data,
  parameter, jumlah pengulangan (seed).
- Alasan pemilihan parameter dijelaskan, bukan hanya disebutkan.

Contoh pola asli (Intelligent Steam, 2020):

> "The proposed model is divided into four main stages ... In the first stage,
> the key monitoring variables that are sensitive to waterwall tube leakage are
> identified. The second stage is the data preprocessing phase ..."

Pola Indonesia yang dapat dipakai:

> "Penelitian ini menggunakan pembagian data bersih. Data pelatihan terdiri
> atas window yang berakhir sebelum 12 Mei 2023. Data validasi terdiri atas
> 20% terakhir data pelatihan. Window kebocoran hanya digunakan untuk
> evaluasi. Pembagian ini memastikan model hanya mempelajari pola operasi
> normal."

### 3.5. Hasil

Struktur bagian hasil yang konsisten:

1. **Definisi metrik** terlebih dahulu sebelum angka dilaporkan.
2. **Kalimat pengantar tabel/gambar**.
3. **Laporan angka utama** dengan pola "Model X menghasilkan akurasi Y%".
4. **Interpretasi sebab-akibat** ("Hal ini karena ...", "Kondisi ini
   menunjukkan ...").
5. **Perbandingan dengan baseline atau studi lain**.

Contoh pola asli (Sohaib & Kim, 2019):

> "The performance of the leakage classification model developed was evaluated
> using the k-fold cross validation technique ... It can be observed that the
> average accuracy of the developed model is 99.2%. ... The proposed model
> outperformed all of the other algorithms. The average classification
> accuracies of PCA + KNN, GA + DNN, SFP + SVM, and the proposed model are
> 91.65%, 94.67%, 95%, and 99.2%, respectively."

Pola Indonesia yang dapat dipakai:

> "Hasil perbandingan disajikan pada tabel berikut. Model CNN-GRU menghasilkan
> RMSE 2,90 ± 0,10 ton/jam. Nilai ini lebih kecil dibandingkan model CNN-LSTM,
> yaitu 3,45 ± 0,08 ton/jam. Perbedaan ini menunjukkan bahwa ... Model LSTM
> menghasilkan FAR terendah, yaitu 0,07%, tetapi median alarm pertamanya lebih
> lambat dibandingkan model CNN-GRU."

### 3.6. Pembahasan

Bagian pembahasan membahas:

- Trade-off antar metode ("Meskipun ... menghasilkan ..., model ... tetap
  dipilih karena ...").
- Keterbatasan ("Keterbatasan penelitian ini adalah ...").
- Implikasi praktis ("Hasil ini menunjukkan bahwa ... pada penerapan").
- Perbandingan dengan studi lain.

Contoh pola asli (Pan & Yang, 2025):

> "Although 4C2L improves training loss and training set accuracy, its test set
> accuracy significantly decreases, likely due to overfitting caused by
> increased network depth."

Pola Indonesia yang dapat dipakai:

> "Model gabungan mendeteksi kebocoran lebih awal dibandingkan model per unit.
> Namun, FAR model gabungan pada data normal Unit 1 meningkat dari 0,85%
> menjadi 1,23%. Peningkatan FAR merupakan trade-off dari penggabungan data
> dua unit."

### 3.7. Kesimpulan

Struktur kesimpulan artikel referensi:

1. Pernyataan kontribusi ("Penelitian ini menghasilkan/mengevaluasi ...").
2. Ringkasan temuan kunci dengan angka.
3. Pernyataan manfaat/kegunaan.
4. Saran untuk penelitian lanjutan (singkat).

Contoh pola asli (Yuan dkk., 2026):

> "The model achieved perfect classification (100% accuracy) under quiet
> settings, and maintained accuracies of 92.3%, 88.1%, and 85.4% ... Future
> work will focus on adaptive noise modeling and online threshold learning."

Pola Indonesia yang dapat dipakai:

> "Algoritma yang direkomendasikan untuk data lapangan PLN Nusantara Power
> adalah CNN-GRU. Model ini mendeteksi kebocoran pada 13 Mei 2023 dengan
> median alarm pertama pukul 08.05 dan FAR rata-rata 0,33%. Penelitian
> selanjutnya perlu menguji ketahanan model terhadap kombinasi beberapa sensor
> yang rusak secara bersamaan."

## 4. Rangkaian Kata dan Transisi

### 4.1. Transisi antar kalimat dan paragraf

| Fungsi | Pola Indonesia | Contoh asli pada artikel |
| ------ | -------------- | ------------------------ |
| Menyatakan kontras | "Namun, ..." | "However, ..." |
| Menambah informasi | "Selain itu, ..." / "Lebih lanjut, ..." | "Furthermore, ..." / "Moreover, ..." |
| Menyatakan akibat | "Oleh karena itu, ..." / "Dengan demikian, ..." | "Therefore, ..." / "Thus, ..." |
| Memberi contoh | "Sebagai contoh, ..." | "For example, ..." |
| Menyatakan perbandingan | "Sebaliknya, ..." / "Dibandingkan dengan ..., ..." | "In contrast, ..." / "Compared with ..., ..." |
| Mempertegas | "Secara khusus, ..." / "Khususnya, ..." | "Specifically, ..." / "Notably, ..." |
| Menyimpulkan sebagian | "Secara keseluruhan, ..." | "Overall, ..." |
| Menyatakan urutan | "Pertama, ... Kedua, ... Ketiga, ..." | "First, ... Second, ... Third, ..." |

### 4.2. Pelaporan angka dan perbandingan

| Fungsi | Pola Indonesia | Contoh asli pada artikel |
| ------ | -------------- | ------------------------ |
| Melaporkan hasil | "Model X menghasilkan akurasi Y%." | "The proposed model yielded a 99.2% average classification accuracy." |
| Melaporkan hasil | "Hasil menunjukkan bahwa ..." | "The results show that ..." / "The results indicate that ..." |
| Membandingkan | "lebih baik dibandingkan ..., yaitu ..." | "outperformed ... with ..." |
| Menyatakan selisih | "peningkatan sekitar ... dibandingkan ..." | "an improvement of approximately 1.6% higher than CNN" |
| Menyatakan konsistensi | "sejalan dengan temuan ..." | "consistent with ..." / "in agreement with ..." |
| Menyatakan keterbatasan | "terbatas pada ..." | "limited to ..." |

### 4.3. Kehati-hatian (hedging)

| Pola Indonesia | Contoh asli pada artikel |
| ------------- | ------------------------ |
| "dapat" | "can" / "may" |
| "cenderung" | "tends to" |
| "sekitar" | "approximately" |
| "kemungkinan disebabkan oleh" | "likely due to" |
| "sejauh pengetahuan penulis" | "to the best of the authors' knowledge" |
| "perlu dicatat bahwa" | "it is worth pointing out that" |
| "dapat diamati bahwa" | "it can be observed that" |
| "terlihat jelas bahwa" | "it is evident from ... that" |

### 4.4. Sitasi

- Sitasi diletakkan tepat setelah klaim, bukan di akhir paragraf secara umum.
- Pola penulis sebagai subjek: "Pan dan Yang [15] mengusulkan ...".
- Pola klaim sebagai subjek: "Kebocoran tube menyumbang 54% dari total
  gangguan [22]".
- Untuk perbandingan beberapa sumber: "Beberapa studi [12; 14] menunjukkan
  ...".

## 5. Diksi yang Disarankan dan Dihindari

Disarankan:

- Gunakan istilah teknis yang konsisten: "ambang batas", "residual",
  "window", "data pelatihan", "data validasi", "data pengujian", "alarm",
  "deteksi dini".
- Gunakan kata kerja hasil yang presisi: "menghasilkan", "mencapai",
  "menunjukkan", "meningkat", "menurun", "mendeteksi".
- Gunakan kalimat aktif: "Model mendeteksi kebocoran pada ...", bukan
  "Kebocoran terdeteksi oleh model".

Dihindari:

- Ungkapan berbunga-bunga atau metafora.
- Kata ganti orang pertama yang berlebihan ("saya", "kami") dalam laporan
  formal; artikel referensi memakai "penelitian ini", "studi ini".
- Klaim mutlak tanpa data ("pasti", "selalu").
- Mengulang kata yang sama terlalu dekat tanpa alasan; gunakan sinonim yang
  sudah baku, tetapi jangan mengganti istilah teknis dengan sinonim.

## 6. Contoh Paragraf Model (Bahasa Indonesia)

Contoh paragraf hasil, mengikuti pola artikel referensi (definisi metrik,
kalimat pengantar tabel, angka, interpretasi):

> False Alarm Rate (FAR) menyatakan proporsi alarm yang dipicu pada kondisi
> normal. Hasil perbandingan FAR antar arsitektur disajikan pada tabel
> berikut. Model LSTM menghasilkan FAR terendah, yaitu 0,07%. Model CNN-GRU
> menghasilkan FAR 0,33%, sedangkan model Transformer menghasilkan FAR
> tertinggi sebesar 1,60%. Nilai FAR model Transformer melampaui batas satu
> persen pada konfigurasi α=3 dan persistensi 2. Perbedaan FAR ini
> menunjukkan bahwa model dengan residual lebih rapat tidak selalu
> menghasilkan FAR lebih rendah. Model CNN-GRU tetap direkomendasikan karena
> menyeimbangkan FAR yang rendah dan waktu alarm pertama yang cepat.

Contoh paragraf pembahasan, mengikuti pola trade-off pada artikel referensi:

> Perbandingan antar algoritma menunjukkan adanya trade-off antara kecepatan
> deteksi, kestabilan pada kondisi normal, dan kualitas prediksi. Model
> recurrent sederhana menghasilkan residual paling rapat dan FAR paling
> rendah, tetapi alarm pertama lebih lambat. Model konvolusional mendeteksi
> paling awal tetapi menghasilkan residual paling lebar. Kondisi ini sejalan
> dengan temuan Chung dkk. bahwa GRU menghasilkan performa sebanding dengan
> LSTM dengan jumlah parameter lebih sedikit. Oleh karena itu, pemilihan
> algoritma tidak dapat dilakukan hanya berdasarkan satu metrik, tetapi harus
> mempertimbangkan seluruh kriteria secara bersamaan.

## 7. Checklist Sebelum Menulis Bab

- [ ] Setiap paragraf hanya berisi satu ide pokok.
- [ ] Kalimat pengantar tabel/gambar selalu ada sebelum tabel/gambar.
- [ ] Setiap angka hasil disertai konteks (seed, jumlah sampel, dataset).
- [ ] Setiap klaim literatur disertai sitasi tepat setelah klaim.
- [ ] Klaim dibatasi dengan kata kehati-hatian ("dapat", "cenderung",
  "sekitar") kecuali hasil benar-benar konsisten.
- [ ] Istilah teknis konsisten di seluruh bab (sesuai daftar istilah pada
  AGENTS.md).
- [ ] Struktur bab mengikuti alur: konteks, masalah, celah, kontribusi,
  metode, hasil, pembahasan, kesimpulan.
- [ ] Angka di laporan diverifikasi terhadap hasil eksperimen yang
  dieksekusi.
