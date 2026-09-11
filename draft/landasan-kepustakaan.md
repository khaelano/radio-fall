# 2. Landasan Kepustakaan

Bab ini menjelaskan hubungan antara gerakan jatuh, pembentukan sinyal Doppler,
pengolahan sinyal, dan keputusan klasifikasi. Pembahasan dimulai dari konsep
jatuh sebagai objek yang dideteksi. Pembahasan kemudian bergerak menuju
pengindraan manusia berbasis gelombang radio, radar *continuous-wave* (CW),
efek Doppler, representasi waktu--frekuensi, klasifikasi, dan evaluasi sistem.
Urutan tersebut digunakan agar teori yang disajikan mendukung secara langsung
alur pengukuran pada penelitian ini.

## 2.1. Jatuh dan Sistem Deteksi Jatuh

Jatuh perlu didefinisikan secara operasional sebelum sebuah sistem deteksi
dikembangkan. Hu dkk. merangkum jatuh sebagai perpindahan yang tidak disengaja
menuju lantai atau posisi yang lebih rendah. Mereka juga menunjukkan bahwa
definisi dan kriteria deteksi belum seragam antarpublikasi radar. Perbedaan
tersebut dapat memengaruhi penentuan kelas, anotasi data, dan perbandingan
kinerja sistem [@huRadarBasedFallDetection2024]. Dalam penelitian ini, jatuh
didefinisikan sebagai perpindahan tubuh yang tidak terkendali menuju posisi
yang lebih rendah akibat kehilangan keseimbangan dan diakhiri dengan kontak
tubuh terhadap lantai atau permukaan pengaman.

Kejadian jatuh merupakan gerakan dinamis yang terdiri atas beberapa perubahan
keadaan. Tubuh mengalami penurunan posisi dengan percepatan yang relatif cepat,
kemudian mengalami deselerasi ketika mencapai permukaan. Setelah itu, korban
dapat bergerak kembali, tetap berbaring, atau tidak mampu berdiri. Amin dkk.
menjelaskan bahwa perubahan cepat pada awal jatuh dan perlambatan pada akhir
gerakan menghasilkan sinyal radar yang tidak stasioner. Oleh karena itu,
informasi tentang perubahan gerak terhadap waktu lebih penting daripada satu
nilai amplitudo atau frekuensi yang berdiri sendiri
[@aminRadarSignalProcessing2016].

Fase setelah jatuh juga memiliki makna praktis. Kondisi ketika seseorang tetap
berada di lantai selama satu jam atau lebih disebut *long lie*. Tinjauan
sistematis Blackburn dkk. menunjukkan bahwa *long lie* berkaitan dengan dampak
fisik dan klinis yang merugikan. Penggunaan alarm pribadi pada kasus yang
ditinjau juga masih rendah. Hasil tersebut mendukung kebutuhan akan deteksi dan
pemberian peringatan secara otomatis tanpa menunggu tindakan korban
[@blackburnExploringImpactExperiencing2022]. Meskipun demikian, radar CW
frekuensi tunggal pada penelitian ini tidak dapat memastikan postur statis atau
keadaan klinis korban. Sistem dibatasi pada pengenalan transisi gerak yang
menyerupai kejadian jatuh.

Kesulitan deteksi muncul karena sebagian aktivitas sehari-hari memiliki bagian
gerak yang menyerupai jatuh. Duduk cepat, membungkuk, berlutut, jongkok, dan
berbaring secara sengaja dapat menghasilkan perubahan kecepatan atau energi
yang besar. Amin dkk. mengidentifikasi kemiripan jatuh dengan gerakan duduk dan
berlutut sebagai salah satu penyebab alarm palsu. Liu dkk. juga menemukan bahwa
sebagian kesalahan pada data mereka berasal dari gerakan jongkok dan berlutut
yang dilakukan dengan cepat [@aminRadarSignalProcessing2016;
@liuAutomaticFallDetection2011]. Dengan demikian, kelas non-jatuh dalam
pengujian tidak cukup hanya berisi keadaan diam atau berjalan. Kelas tersebut
perlu memuat aktivitas yang secara gerak paling berpotensi mengacaukan sistem.

Sistem deteksi jatuh secara umum dapat dibedakan menjadi sistem yang dikenakan
pada tubuh dan sistem yang ditempatkan di lingkungan. Perangkat *wearable*
dapat mengukur percepatan atau orientasi tubuh secara langsung, tetapi
kinerjanya bergantung pada penggunaan dan penempatan perangkat. Igual dkk.
menunjukkan bahwa pengujian perangkat pada posisi tubuh yang distandardisasi
belum tentu menggambarkan cara perangkat dibawa dalam kehidupan sehari-hari.
Sistem berbasis kamera tidak memerlukan perangkat pada tubuh, tetapi dapat
menghadapi oklusi dan persoalan privasi di ruang hunian
[@igualChallengesIssuesTrends2013; @huRadarBasedFallDetection2024]. Kondisi
tersebut mendorong penggunaan radar sebagai pendekatan nonkontak dan
*device-free*.

## 2.2. Pengindraan Manusia Berbasis Gelombang Radio

Pengindraan berbasis radio memanfaatkan perubahan sinyal yang merambat dari
pemancar menuju penerima setelah berinteraksi dengan lingkungan. Tubuh manusia
bertindak sebagai target yang memantulkan dan menghamburkan sebagian energi
gelombang. Ketika tubuh bergerak, panjang lintasan dan fase komponen sinyal
pantul berubah terhadap waktu. Perubahan tersebut dapat digunakan untuk
menurunkan informasi gerak tanpa memasang sensor pada tubuh
[@liuWirelessSensingHuman2020].

Sinyal yang diterima tidak hanya berasal dari lintasan langsung antara sensor
dan tubuh. Dinding, lantai, plafon, furnitur, dan objek lain menghasilkan
pemantulan tambahan. Akibatnya, penerima mengamati gabungan komponen statis dan
dinamis melalui beberapa lintasan atau *multipath*. Komponen statis dapat
membentuk *clutter*, sedangkan perubahan tata letak dapat mengubah distribusi
sinyal meskipun aktivitas yang dilakukan tetap sama. Survei pengindraan nirkabel
dan studi DeFall menunjukkan bahwa ketergantungan terhadap lingkungan merupakan
masalah generalisasi yang penting pada sistem berbasis WiFi CSI
[@liuWirelessSensingHuman2020; @huDeFallEnvironmentIndependentPassive2022].
Radar Doppler juga menghadapi *clutter*, oklusi, dan pelemahan tanda gerak pada
arah yang tidak menguntungkan [@aminRadarSignalProcessing2016].

Pengindraan radio untuk aktivitas manusia dapat menggunakan WiFi CSI atau radar
khusus. CSI merepresentasikan respons kanal pada subpembawa WiFi dan dapat
menangkap gangguan kanal akibat gerakan tubuh. Pendekatan tersebut memanfaatkan
perangkat komunikasi yang tersedia, tetapi sinyalnya dipengaruhi konfigurasi
perangkat dan *multipath*. Radar khusus mengendalikan bentuk sinyal pancar dan
dapat menghasilkan informasi Doppler, jarak, atau sudut sesuai arsitektur
perangkatnya [@liuWirelessSensingHuman2020; @huRadarBasedFallDetection2024].
Penelitian ini menggunakan radar CW frekuensi tunggal. Oleh karena itu, fokus
pengindraannya adalah perubahan gerak radial, bukan estimasi jarak atau
pembentukan citra tubuh.

Radar tidak merekam citra visual dan tidak bergantung pada pencahayaan. Dua
karakteristik tersebut mendukung penggunaannya di dalam ruangan
[@aminRadarSignalProcessing2016; @huRadarBasedFallDetection2024]. Namun,
pengindraan radio tidak dapat dinyatakan sepenuhnya bebas dari persoalan
privasi. Windl dkk. menemukan bahwa pemahaman pengguna tentang kemampuan
inferensi sensor radio dapat memengaruhi persepsi mereka terhadap teknologi
tersebut [@windlPrivacySolutionMenace2025]. Keunggulan privasi dalam penelitian
ini karena tidak direkamnya citra visual dan tidak digunakannya identitas
subjek, bukan karena sinyal radio dianggap tidak mengandung informasi sensitif.

## 2.3. Dasar Gelombang Radio

Gelombang radio merupakan gelombang elektromagnetik yang dapat dinyatakan
melalui amplitudo, frekuensi, fase, dan panjang gelombang. Hubungan antara
frekuensi pembawa $f_c$, panjang gelombang $\lambda$, dan kecepatan rambat
gelombang elektromagnetik $c$ dinyatakan sebagai

$$
\lambda = \frac{c}{f_c}.
$$

Pada frekuensi yang lebih tinggi, panjang gelombang menjadi lebih pendek.
Hubungan ini penting karena pergeseran Doppler yang dihasilkan oleh kecepatan
target bergantung pada panjang gelombang radar
[@aminRadarSignalProcessing2016].

Amplitudo menyatakan besar sinyal, sedangkan fase menyatakan posisi suatu
gelombang dalam siklusnya. Pada radar, perubahan jarak lintasan pergi-pulang
antara sensor dan target menyebabkan perubahan fase sinyal pantul. Radar
Doppler memperoleh informasi gerak dengan mengamati perubahan fase tersebut
dari waktu ke waktu [@aminRadarSignalProcessing2016]. Amplitudo keluaran juga
dapat berubah akibat kekuatan pantulan, pola antena, jarak, orientasi target,
dan interferensi antarlintasan. Oleh karena itu, amplitudo tidak dapat
ditafsirkan hanya sebagai ukuran kecepatan tubuh.

Tubuh manusia bukan target titik yang kaku. Torso, tangan, dan kaki memiliki
luas pantul dan pola gerak yang berbeda. Sinyal yang diterima merupakan
superposisi pantulan dari bagian-bagian tubuh tersebut. Konsekuensinya, satu
aktivitas dapat menghasilkan beberapa komponen frekuensi yang berubah terhadap
waktu [@aminRadarSignalProcessing2016; @kimHumanActivityClassification2009].
Sifat ini menjadi dasar penggunaan tanda *micro-Doppler* untuk membedakan
aktivitas manusia.

## 2.4. Radar Doppler *Continuous-Wave* dan HB100

Radar CW memancarkan sinyal secara terus-menerus. Pada radar CW dengan
frekuensi tetap, sinyal pantul dicampur dengan salinan sinyal pancar untuk
menghasilkan komponen berfrekuensi rendah pada keluaran. Komponen tersebut
mewakili selisih frekuensi yang disebabkan oleh gerak radial target. Berbeda
dengan radar pulsa atau FMCW, radar CW frekuensi tunggal tidak memberikan
informasi waktu tunda yang dapat digunakan untuk menghitung jarak target secara
langsung [@huRadarBasedFallDetection2024; @aminRadarSignalProcessing2016].

HB100 merupakan modul transiver Doppler CW pita-X. Modul ini menggunakan
frekuensi pancar nominal 10,525 GHz, antena *patch* bistatik, serta catu daya
sekitar 5 V. Thiel dkk. melaporkan lebar berkas setengah daya sekitar 80 derajat
pada bidang-H dan 40 derajat pada bidang-E. Mereka juga menegaskan bahwa
keluaran HB100 terutama berkaitan dengan perpindahan radial target dan bahwa
modul tersebut dirancang sebagai sensor gerak berbiaya dan berdaya rendah
[@thielLowCostXbandDoppler2025]. Karakteristik tersebut sesuai untuk menguji
sistem sederhana, tetapi juga membuat hasil pengukuran bergantung pada orientasi
sensor dan lintasan target di dalam berkas antena.

Penggunaan satu HB100 menghasilkan batas informasi yang perlu dinyatakan sejak
awal. Sensor dapat menunjukkan adanya komponen gerak, tetapi tidak dapat
menentukan jarak, sudut, identitas, atau postur statis secara langsung. Selain
itu, sumber pantulan yang berbeda di dalam cakupan antena tercampur pada satu
keluaran. Sistem dengan satu sensor karena itu lebih sesuai untuk kondisi satu
orang dan lingkungan terkendali daripada kondisi yang memuat beberapa orang
atau beberapa target bergerak secara bersamaan
[@aminRadarSignalProcessing2016].

## 2.5. Efek Doppler dan *Micro-Doppler*

### 2.5.1. Dasar Efek Doppler

Efek Doppler pada radar adalah perubahan frekuensi sinyal pantul akibat gerak
relatif target terhadap radar. Untuk target yang bergerak dengan kecepatan
$v(t)$ dan membentuk sudut $\theta$ terhadap garis pandang radar, komponen
kecepatan radialnya adalah $v(t)\cos\theta$. Pada radar monostatik, besar
frekuensi Doppler dapat ditulis sebagai

$$
f_D(t) = \frac{2v(t)\cos\theta}{\lambda}.
$$

Faktor dua muncul karena gelombang menempuh lintasan dari radar menuju target
dan kembali ke radar. Persamaan tersebut menunjukkan bahwa frekuensi Doppler
bergantung pada kecepatan, panjang gelombang, dan sudut gerak
[@aminRadarSignalProcessing2016].

Radar mengukur kecepatan radial, bukan besar kecepatan tiga dimensi secara
langsung. Gerakan yang sejajar dengan garis pandang menghasilkan komponen
Doppler yang lebih kuat. Sebaliknya, ketika arah gerak mendekati tegak lurus
terhadap garis pandang, nilai $\cos\theta$ mendekati nol sehingga komponen
Doppler melemah. Thiel dkk. memperlihatkan ketergantungan HB100 terhadap
komponen radial tersebut, sedangkan Liu dkk. menunjukkan secara eksperimental
bahwa arah jatuh memengaruhi kinerja deteksi
[@thielLowCostXbandDoppler2025; @liuDopplerRadarSensor2012].

### 2.5.2. *Micro-Doppler* Gerakan Manusia

Gerak translasi utama tubuh menghasilkan komponen Doppler makro. Gerakan
tambahan dari anggota badan menghasilkan modulasi Doppler yang disebut
*micro-Doppler*. Pada aktivitas berjalan, misalnya, pantulan torso membentuk
komponen utama, sedangkan ayunan tangan dan kaki menghasilkan komponen tambahan
yang berubah secara periodik. Kim dan Ling menunjukkan bahwa ciri yang
diekstraksi dari spektrogram *micro-Doppler* dapat digunakan untuk membedakan
tujuh aktivitas manusia dengan SVM [@kimHumanActivityClassification2009].

Pada kejadian jatuh, torso dan anggota badan tidak bergerak sebagai satu benda
kaku. Perubahan kecepatan setiap bagian tubuh menghasilkan tanda Doppler yang
menyebar pada waktu dan frekuensi. Pola tersebut berbeda dari aktivitas
periodik seperti berjalan, tetapi dapat tumpang tindih dengan transisi postur
yang cepat. Oleh karena itu, *micro-Doppler* tidak menjadi bukti jatuh secara
tunggal. Tanda tersebut harus dianalisis bersama durasi, energi, rentang
frekuensi, dan susunan temporal gerak
[@aminRadarSignalProcessing2016; @liuAutomaticFallDetection2011].

### 2.5.3. Efek Doppler untuk Deteksi Jatuh

Pemanfaatan Doppler untuk deteksi jatuh didasarkan pada perubahan kecepatan
radial selama transisi tubuh menuju permukaan. Liu dkk. membentuk spektrogram
dari sinyal radar, mencari lonjakan energi, lalu mengekstraksi MFCC untuk
membedakan jatuh dan non-jatuh. Studi tersebut menunjukkan bahwa jatuh dapat
menghasilkan rentang frekuensi dan energi yang lebih besar daripada beberapa
aktivitas pembanding. Namun, jongkok dan berlutut cepat tetap menghasilkan
kesalahan [@liuAutomaticFallDetection2011]. Dengan demikian, besar energi dapat
digunakan untuk menemukan kandidat kejadian, tetapi keputusan akhir memerlukan
informasi pola yang lebih lengkap.

Posisi radar menentukan komponen gerak yang dapat diamati. Liu dkk. melaporkan
bahwa radar yang dipasang di plafon menghasilkan kinerja yang lebih stabil
terhadap perubahan arah jatuh daripada radar yang dipasang di dinding pada
konfigurasi eksperimen mereka. Radar dinding memiliki ketergantungan yang lebih
kuat terhadap arah gerak [@liuDopplerRadarSensor2012]. Penelitian ini tetap
menggunakan pemasangan dinding dengan arah 45 derajat ke bawah. Konfigurasi
tersebut harus dipertahankan selama pengumpulan data dan keterbatasannya perlu
dievaluasi melalui variasi arah jatuh.

## 2.6. Pengolahan Sinyal Radar Doppler

Keluaran analog radar perlu diubah menjadi rangkaian data digital sebelum dapat
dianalisis. Tahap akuisisi mencakup penguatan, penyaringan, dan pencuplikan.
Frekuensi pencuplikan harus cukup untuk merepresentasikan rentang Doppler yang
menjadi perhatian. Komponen DC, gangguan catu daya, derau, dan gerakan di luar
kejadian dapat mendominasi sinyal jika tidak ditangani. Sistem Doppler yang
dikembangkan Imamura dkk., sebagai contoh, menerapkan penyaringan, pemicu
berbasis amplitudo, pembentukan jendela, STFT, dan normalisasi sebelum
klasifikasi [@imamuraFallDetectionSingle2022]. Pemilihan parameter setiap tahap
tetap harus ditentukan dari karakterisasi perangkat dan data penelitian ini.

Sinyal jatuh bersifat tidak stasioner karena kandungan frekuensinya berubah
selama kejadian. Transformasi Fourier atas seluruh rekaman dapat menunjukkan
kandungan frekuensi global, tetapi menghilangkan lokasi waktu setiap komponen.
STFT mengatasi keterbatasan tersebut dengan menghitung transformasi Fourier pada
jendela yang digeser sepanjang sinyal. Untuk sinyal diskret $x[n]$ dan fungsi
jendela $w[n-m]$, STFT dapat ditulis sebagai

$$
X(m,\omega)=\sum_{n=-\infty}^{\infty}x[n]w[n-m]e^{-j\omega n}.
$$

Spektrogram kemudian diperoleh dari kuadrat magnitudo STFT,

$$
S(m,\omega)=|X(m,\omega)|^2.
$$

Representasi tersebut memperlihatkan perubahan distribusi energi terhadap
waktu dan frekuensi. Amin dkk. menempatkan STFT sebagai salah satu metode utama
untuk menganalisis sinyal jatuh yang tidak stasioner
[@aminRadarSignalProcessing2016].

Ukuran jendela membentuk kompromi antara resolusi waktu dan resolusi frekuensi.
Jendela pendek lebih peka terhadap perubahan cepat, tetapi menghasilkan
resolusi frekuensi yang lebih rendah. Jendela panjang memberikan pemisahan
frekuensi yang lebih baik, tetapi dapat mengaburkan perubahan singkat. Oleh
karena itu, ukuran jendela dan tumpang tindih tidak boleh dipilih hanya karena
umum digunakan pada studi lain. Nilainya perlu disesuaikan dengan frekuensi
pencuplikan, durasi jatuh, dan rentang Doppler HB100 yang terukur.

Informasi dari domain waktu dan waktu--frekuensi dapat diringkas menjadi fitur.
Fitur kandidat pada penelitian ini meliputi durasi aktivitas, energi, frekuensi
Doppler maksimum, rentang frekuensi, serta bentuk perubahan energi sepanjang
waktu. Studi terdahulu menggunakan fitur spektrogram, MFCC, karakteristik
*wavelet*, dan citra spektrogram untuk tujuan yang sama
[@kimHumanActivityClassification2009; @liuAutomaticFallDetection2011;
@suDopplerRadarFall2015; @sadreazamiContactlessFallDetection2021]. Fitur yang
akhirnya digunakan harus ditentukan melalui data pelatihan dan validasi, bukan
berdasarkan data uji.

## 2.7. Klasifikasi Jatuh dan Non-Jatuh

Deteksi pada penelitian ini dirumuskan sebagai klasifikasi biner. Kelas positif
menyatakan jatuh, sedangkan kelas negatif menyatakan aktivitas non-jatuh.
Masukan model dapat berbentuk fitur numerik, urutan sampel atau fitur, maupun
spektrogram. Bentuk masukan menentukan keluarga model yang relevan dan jumlah
data yang diperlukan.

Pendekatan berbasis fitur memisahkan ekstraksi karakteristik sinyal dari proses
klasifikasi. Kim dan Ling menggunakan enam fitur spektrogram bersama SVM untuk
klasifikasi aktivitas. Liu dkk. menggunakan MFCC bersama SVM dan kNN untuk
membedakan jatuh dari non-jatuh [@kimHumanActivityClassification2009;
@liuAutomaticFallDetection2011]. Pendekatan ini memungkinkan hubungan antara
fitur fisik dan keputusan model diperiksa. Namun, keberhasilannya bergantung
pada kemampuan fitur yang dirancang untuk mempertahankan perbedaan antarkelas.

Pendekatan *deep learning* mempelajari representasi langsung dari data yang
lebih terstruktur. CNN dapat mempelajari pola lokal pada spektrogram, sedangkan
LSTM dirancang untuk memodelkan keterkaitan dalam urutan. Sadreazami dkk.
menggunakan CNN pada citra spektrogram untuk klasifikasi jatuh, sementara
Imamura dkk. menggunakan LSTM pada karakteristik waktu--frekuensi dari satu
radar Doppler [@sadreazamiContactlessFallDetection2021;
@imamuraFallDetectionSingle2022]. Keuntungan pembelajaran fitur tersebut harus
dipertimbangkan bersama kebutuhan data, biaya komputasi, dan risiko
*overfitting*.

Model akhir belum ditentukan pada tahap penyusunan landasan kepustakaan ini.
Pemilihan akan dilakukan melalui perbandingan beberapa kandidat dengan prosedur
validasi yang sama. Model sederhana berbasis fitur diperlukan sebagai
*baseline*. Model berbasis urutan atau spektrogram dapat ditambahkan jika
jumlah dan keragaman data mencukupi. Data uji tidak digunakan untuk memilih
model atau parameter. Data tersebut hanya digunakan untuk menilai konfigurasi
akhir agar estimasi kinerja tidak terlalu optimistis.

## 2.8. Evaluasi Sistem Deteksi Jatuh

Keluaran klasifikasi dapat dirangkum sebagai *true positive* (TP), *false
positive* (FP), *true negative* (TN), dan *false negative* (FN). TP adalah
kejadian jatuh yang dikenali sebagai jatuh. FP adalah aktivitas non-jatuh yang
memicu alarm. TN adalah aktivitas non-jatuh yang ditolak dengan benar. FN
adalah kejadian jatuh yang tidak terdeteksi
[@huRadarBasedFallDetection2024].

Metrik utama dihitung sebagai

$$
\operatorname{Precision}=\frac{TP}{TP+FP},
$$

$$
\operatorname{Recall}=\frac{TP}{TP+FN},
$$

$$
\operatorname{Specificity}=\frac{TN}{TN+FP},
$$

$$
F_1=2\frac{\operatorname{Precision}\times\operatorname{Recall}}
{\operatorname{Precision}+\operatorname{Recall}},
$$

dan

$$
\operatorname{FPR}=\frac{FP}{FP+TN}.
$$

*Recall* mengukur proporsi jatuh yang berhasil dideteksi. *Precision* mengukur
proporsi alarm jatuh yang benar, sedangkan *specificity* dan FPR menunjukkan
kemampuan sistem menolak aktivitas non-jatuh. Pada data yang jumlah aktivitas
non-jatuhnya jauh lebih besar daripada jatuh, akurasi dapat memberikan gambaran
yang terlalu baik. Karena itu, akurasi tidak digunakan sebagai satu-satunya
ukuran [@huRadarBasedFallDetection2024;
@sadreazamiContactlessFallDetection2021].

Evaluasi juga perlu memperhatikan satuan keputusan. Metrik per-*window* menilai
setiap potongan sinyal secara terpisah, sedangkan metrik per-kejadian menilai
apakah satu kejadian jatuh menghasilkan alarm. Pada data *sequence*, beberapa
*window* yang berdekatan dapat berasal dari satu kejadian yang sama. Pemisahan
ini diperlukan agar satu jatuh tidak dihitung sebagai banyak keberhasilan.
Selain itu, latensi dihitung dari waktu acuan kejadian sampai alarm pertama.
Pengukuran tersebut menghubungkan kinerja klasifikasi dengan tujuan pemberian
pertolongan secara cepat.

Pemisahan data perlu mencegah sampel yang sangat mirip masuk ke pelatihan dan
pengujian. Sadreazami dkk. menggunakan skema *leave-one-subject-out* untuk
menilai model pada subjek yang tidak digunakan dalam pelatihan
[@sadreazamiContactlessFallDetection2021]. Penelitian ini perlu memisahkan data
berdasarkan subjek atau sesi pengukuran jika jumlah subjek memungkinkan. Jika
ruang lingkup data belum mendukung pengujian lintas subjek, keterbatasan
tersebut harus dinyatakan dan hasil tidak boleh digeneralisasi ke pengguna baru.

## 2.9. Penelitian Terkait

Penelitian awal tentang *micro-Doppler* menunjukkan bahwa aktivitas manusia
dapat dibedakan melalui pola waktu--frekuensi. Penelitian deteksi jatuh kemudian
mengembangkan alur yang mencakup segmentasi kandidat gerak, pembentukan
spektrogram atau representasi waktu--skala, ekstraksi fitur, dan klasifikasi.
Perkembangan berikutnya mengganti sebagian rekayasa fitur dengan CNN atau LSTM.
Meskipun angka kinerja yang dilaporkan sering tinggi, perbandingan langsung
tetap harus dilakukan secara hati-hati karena perangkat, subjek, aktivitas,
lingkungan, dan skema validasinya berbeda
[@igualChallengesIssuesTrends2013; @huRadarBasedFallDetection2024].

Tabel berikut merangkum penelitian yang paling relevan dengan penggunaan radar
Doppler dan representasi waktu--frekuensi.

| Penelitian | Sensor dan data | Representasi dan metode | Temuan yang relevan | Batas yang perlu diperhatikan |
|---|---|---|---|---|
| Kim dan Ling [@kimHumanActivityClassification2009] | Radar CW 2,4 GHz; 12 subjek; tujuh aktivitas | Enam fitur spektrogram dan SVM | Menunjukkan bahwa tanda *micro-Doppler* dapat digunakan untuk klasifikasi aktivitas manusia | Tidak dirancang khusus sebagai detektor jatuh |
| Liu dkk. [@liuAutomaticFallDetection2011] | Dua radar Doppler; 109 jatuh dan 341 aktivitas non-jatuh | STFT, kurva lonjakan energi, MFCC, SVM, dan kNN | AUC yang dilaporkan berada sekitar 0,91--0,97; jongkok dan berlutut menjadi sumber kesalahan | Data merupakan data percontohan dan sebagian besar kejadian diperagakan |
| Liu dkk. [@liuDopplerRadarSensor2012] | Radar pada lantai, dinding, dan plafon; arah serta posisi jatuh divariasikan | Spektrogram, MFCC, dan SVM | Radar plafon menghasilkan AUC 0,949 dan radar dinding 0,858 pada konfigurasi perbandingan; arah jatuh memengaruhi hasil | Konfigurasi sensor dan jumlah subjek terbatas sehingga angka tidak dapat dipindahkan langsung ke HB100 |
| Su dkk. [@suDopplerRadarFall2015] | Radar Doppler; data laboratorium, kamar mandi, dan apartemen lansia | *Wavelet transform*, penyaringan kandidat, dan klasifikasi | Evaluasi mencakup 13 jatuh nyata di apartemen; metode menunjukkan bahwa data hunian menghasilkan sumber alarm palsu yang tidak selalu muncul di laboratorium | Jumlah jatuh nyata tetap kecil dan kondisi data berbeda antarkumpulan |
| Sadreazami dkk. [@sadreazamiContactlessFallDetection2021] | Radar UWB; sepuluh subjek; 336 sampel sebelum augmentasi | STFT, citra spektrogram, dan CNN | Dengan *leave-one-subject-out*, model mencapai akurasi 95,83% dan *specificity* 97,82% sebelum augmentasi | Menggunakan informasi jarak dari UWB dan perangkat yang berbeda dari radar CW frekuensi tunggal |
| Imamura dkk. [@imamuraFallDetectionSingle2022] | Satu radar Doppler CW di plafon; dua subjek | Penyaringan, STFT, dan LSTM | Validasi melaporkan akurasi 98% untuk jatuh cepat dan 93% untuk jatuh lambat; eksperimen menunjukkan penurunan *recall* ketika jarak bertambah | Hanya dua subjek sehat dan pengujian dilakukan di laboratorium |

Studi berbasis WiFi memperluas persoalan dari klasifikasi dalam satu ruangan
menuju generalisasi lintas lingkungan dan pengguna. DeFall berupaya mengekstrak
karakteristik yang lebih independen terhadap lingkungan, sedangkan FallDar
menunjukkan bahwa perubahan lingkungan, variasi cara jatuh, dan perbedaan
pengguna dapat menurunkan kinerja sistem
[@huDeFallEnvironmentIndependentPassive2022;
@yangRethinkingFallDetection2023]. Walaupun teknologi WiFi berbeda dari HB100,
temuan tersebut menegaskan bahwa kinerja pada satu konfigurasi ruangan tidak
dapat dianggap mewakili ruangan atau pengguna lain.

Tinjauan atas penelitian terkait menghasilkan tiga pola. Pertama,
representasi waktu--frekuensi digunakan secara konsisten karena gerakan jatuh
bersifat tidak stasioner. Kedua, aktivitas transisi postur yang cepat merupakan
sumber alarm palsu penting. Ketiga, hasil dipengaruhi oleh posisi sensor, arah
gerak, jarak, subjek, dan lingkungan. Karena itu, kontribusi penelitian tidak
cukup dinyatakan melalui pemilihan model dengan akurasi tertinggi. Kontribusi
juga perlu mencakup rancangan data, aktivitas pembanding, prosedur validasi, dan
analisis sumber kesalahan.

## 2.10. Sintesis dan Celah Penelitian

Literatur menunjukkan bahwa radar Doppler dapat membedakan aktivitas melalui
perubahan fase, frekuensi radial, dan tanda *micro-Doppler*. STFT dan
spektrogram menyediakan representasi yang sesuai untuk gerakan jatuh yang
berubah terhadap waktu. Fitur manual yang dipadukan dengan SVM atau kNN serta
fitur yang dipelajari oleh CNN atau LSTM sama-sama telah menghasilkan kinerja
yang menjanjikan pada konfigurasi masing-masing
[@liuAutomaticFallDetection2011; @suDopplerRadarFall2015;
@sadreazamiContactlessFallDetection2021;
@imamuraFallDetectionSingle2022]. Literatur tersebut mendukung kelayakan dasar
penggunaan sinyal Doppler, tetapi belum menetapkan satu model yang selalu lebih
baik untuk semua perangkat dan kondisi.

Kesenjangan utama terletak antara kinerja eksperimen terkendali dan kebutuhan
penerapan nyata. Sebagian besar data jatuh diperagakan karena kejadian nyata
jarang, sulit direkam, dan tidak etis untuk dipaksakan pada lansia. Selain itu,
prosedur pengumpulan data dan definisi aktivitas berbeda antarpublikasi.
Kondisi ini membatasi perbandingan metode dan generalisasi hasil
[@igualChallengesIssuesTrends2013; @huRadarBasedFallDetection2024]. Penelitian
berskala kecil perlu menyatakan hasil sebagai bukti pada konfigurasi yang diuji,
bukan sebagai bukti kesiapan klinis.

Kesenjangan berikutnya berkaitan dengan perangkat sederhana. Sebagian studi
terbaru menggunakan UWB atau FMCW yang menyediakan informasi jarak, sedangkan
HB100 CW frekuensi tunggal hanya menyediakan keluaran gerak gabungan. Modul
HB100 telah dikarakterisasi sebagai sensor Doppler pita-X berbiaya rendah,
tetapi artikel Thiel dkk. tidak mengevaluasinya untuk klasifikasi jatuh
[@thielLowCostXbandDoppler2025]. Oleh karena itu, masih diperlukan evaluasi yang
secara khusus menghubungkan keluaran HB100, representasi temporal dan
waktu--frekuensi, aktivitas non-jatuh yang menyerupai jatuh, serta kinerja
klasifikasi pada data *sequence*.

Berdasarkan sintesis tersebut, penelitian ini diarahkan untuk menjawab celah
yang terbatas dan terukur. Penelitian mengevaluasi satu HB100 pada posisi tetap
di lingkungan dalam ruangan yang terkendali. Evaluasi mencakup variasi arah
gerak, aktivitas non-jatuh yang berpotensi menimbulkan alarm, dan waktu
terjadinya jatuh di dalam *sequence*. Sinyal dianalisis pada domain waktu dan
waktu--frekuensi. Beberapa kandidat model dibandingkan menggunakan prosedur
validasi yang sama, sedangkan model akhir dinilai menggunakan *precision*,
*recall*, F1-score, *specificity* atau FPR, dan latensi. Ruang lingkup ini tidak
dimaksudkan untuk membuktikan generalisasi kepada seluruh lansia dan ruangan.
Tujuannya adalah memperoleh dasar empiris mengenai kemampuan, sumber kesalahan,
dan batas penerapan satu radar Doppler berbiaya rendah untuk deteksi jatuh.
