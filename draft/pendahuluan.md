# 1. Pendahuluan (Draf)

## 1.1. Latar Belakang

Jatuh merupakan permasalahan kesehatan global dan menjadi penyebab kematian
akibat cedera tidak disengaja terbesar kedua di dunia. World Health Organization
memperkirakan bahwa sekitar 684.000 kematian akibat jatuh terjadi setiap tahun
[@worldhealthorganizationFalls2021]. Dalam penelitian yang dilakukan di
Indonesia, Susilowati dkk. menemukan bahwa 29,0% partisipan lansia mengalami
sedikitnya satu kali jatuh selama 12 bulan sebelum pengambilan data
[@susilowatiPrevalenceRiskFactors2020]. Temuan ini menunjukkan bahwa
permasalahan jatuh juga relevan dalam konteks Indonesia.

Dampak kejadian jatuh dapat memburuk apabila korban tidak segera memperoleh
bantuan. Blackburn dkk. melaporkan bahwa kondisi ketika korban tetap berada di
lantai selama lebih dari satu jam setelah jatuh berasosiasi dengan cedera serius,
perawatan di rumah sakit, dan perpindahan ke fasilitas perawatan jangka panjang
[@blackburnExploringImpactExperiencing2022]. Oleh karena itu, deteksi jatuh
secara cepat diperlukan untuk memperpendek waktu antara kejadian dan pemberian
bantuan sehingga berpotensi mengurangi risiko dampak akibat keterlambatan
penanganan [@huRadarBasedFallDetection2024].

Berbagai solusi telah dikembangkan untuk mendeteksi jatuh. Beberapa pendekatan
yang sering digunakan adalah perangkat *wearable* dan kamera. Namun, kedua
pendekatan tersebut memiliki keterbatasan. Perangkat *wearable* bergantung pada
daya baterai dan kepatuhan pengguna untuk mengenakannya secara konsisten
[@maitreFallDetectionUWB2021]. Kamera tidak memerlukan perangkat yang dikenakan
oleh pengguna, tetapi kinerjanya dapat dipengaruhi oleh kondisi pencahayaan dan
pandangan yang terhalang oleh objek [@liuWirelessSensingHuman2020]. Selain itu,
pengumpulan data visual melalui kamera dapat menimbulkan kekhawatiran mengenai
privasi pengguna [@yangRethinkingFallDetection2023].

Keterbatasan tersebut mendorong kebutuhan akan solusi deteksi jatuh yang tidak
memerlukan perangkat pada tubuh dan tidak merekam citra visual pengguna.
Penginderaan berbasis radio merupakan salah satu alternatif yang berpotensi
memenuhi kebutuhan tersebut. Pendekatan ini memanfaatkan perubahan lintasan
propagasi gelombang radio akibat keberadaan dan pergerakan tubuh manusia
[@wangWiFallDeviceFreeFall2017]. Salah satu informasi sinyal yang dapat
digunakan adalah *Channel State Information* (CSI) Wi-Fi. CSI Wi-Fi menyediakan
informasi mengenai fase dan amplitudo kanal pada sejumlah *subcarrier*
[@liuWirelessSensingHuman2020]. Perubahan CSI akibat pergerakan manusia dapat
digunakan sebagai indikator untuk mendeteksi jatuh
[@wangWiFallDeviceFreeFall2017].

Penelitian terdahulu telah menunjukkan bahwa perubahan CSI dapat digunakan
untuk membangun sistem deteksi jatuh tanpa perangkat yang dikenakan oleh
pengguna [@wangWiFallDeviceFreeFall2017]. Wang dkk. melaporkan bahwa perbedaan
fase antarantena dapat menghasilkan sinyal yang lebih sensitif terhadap aktivitas
dibandingkan amplitudo pada konfigurasi penelitian mereka
[@wangRTFallRealTimeContactless2017]. Temuan ini menunjukkan potensi penggunaan
perubahan temporal fase relatif sebagai representasi dinamika gerakan pada
kejadian jatuh.

Berdasarkan permasalahan dan hasil penelitian terdahulu tersebut, penelitian ini
mengembangkan dan mengevaluasi sistem deteksi jatuh berbasis perubahan temporal
fase relatif CSI Wi-Fi. Model berbasis perubahan amplitudo digunakan sebagai
pembanding untuk menilai kontribusi fase relatif, sedangkan sensor MR60FDA2
digunakan sebagai sensor referensi untuk membantu pelabelan dan membandingkan
keluaran deteksi sistem yang dikembangkan.

## 1.2. Rumusan Masalah

Berdasarkan latar belakang yang telah dijelaskan, rumusan masalah pada
penelitian ini adalah sebagai berikut.

1. Bagaimana mengembangkan sistem deteksi jatuh berdasarkan perubahan temporal
   fase relatif *Channel State Information* Wi-Fi?
2. Bagaimana kinerja sistem berbasis fase relatif dalam membedakan aktivitas
   jatuh dan non-jatuh dengan MR60FDA2 sebagai sensor referensi?
3. Bagaimana perbandingan kinerja sistem berbasis fase relatif dengan sistem
   berbasis perubahan amplitudo CSI pada data dan kondisi pengujian yang sama?

## 1.3. Tujuan Penelitian

Berdasarkan rumusan masalah tersebut, tujuan penelitian ini adalah sebagai
berikut.

1. Mengembangkan sistem deteksi jatuh berdasarkan perubahan temporal fase relatif
   *Channel State Information* Wi-Fi.
2. Mengevaluasi kinerja sistem berbasis fase relatif dalam membedakan aktivitas
   jatuh dan non-jatuh dengan MR60FDA2 sebagai sensor referensi.
3. Membandingkan kinerja sistem berbasis fase relatif dengan sistem berbasis
   perubahan amplitudo CSI pada data dan kondisi pengujian yang sama.

## 1.4. Manfaat Penelitian

Penelitian ini diharapkan dapat memberikan bukti empiris mengenai pemanfaatan
perubahan temporal fase relatif CSI Wi-Fi sebagai representasi gerakan untuk
mendeteksi jatuh. Hasil penelitian juga diharapkan dapat memberikan informasi
mengenai perbandingan kinerja fitur fase relatif dan perubahan amplitudo CSI
dalam membedakan aktivitas jatuh dan non-jatuh. Selain itu, penelitian ini dapat
menjadi bahan rujukan untuk pengembangan sistem penginderaan aktivitas manusia
yang tidak memerlukan perangkat yang dikenakan pada tubuh dan tidak merekam
citra visual pengguna. Sistem yang dikembangkan juga diharapkan dapat menjadi
dasar bagi pengembangan sistem pemantauan yang memberikan pemberitahuan ketika
mendeteksi kejadian jatuh.

## 1.5. Batasan Masalah

Batasan masalah yang ditetapkan dalam penelitian ini adalah sebagai berikut.

1. Penelitian berfokus pada deteksi kejadian jatuh di lingkungan dalam ruangan.
2. Data CSI diperoleh menggunakan konfigurasi perangkat Wi-Fi yang ditetapkan
   dalam rancangan eksperimen. Hasil penelitian dibatasi pada karakteristik
   perangkat dan konfigurasi tersebut.
3. Kejadian jatuh dilakukan secara terkontrol sehingga data yang diperoleh tidak
   mewakili seluruh variasi kejadian jatuh alami.
4. Fase relatif CSI digunakan sebagai fitur utama, sedangkan perubahan
   amplitudo digunakan sebagai pembanding.
5. MR60FDA2 digunakan untuk membantu menentukan label dan waktu kejadian serta
   sebagai pembanding keluaran deteksi.
6. Penelitian tidak mengklaim kemampuan generalisasi terhadap subjek, posisi,
   orientasi, atau ruangan yang tidak tercakup dalam data pengujian.
7. Sistem ditujukan untuk mendeteksi kejadian jatuh ketika atau setelah kejadian
   berlangsung. Penelitian tidak membahas prediksi risiko jatuh sebelum kejadian.
