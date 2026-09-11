# 2. Landasan Kepustakaan

Deteksi jatuh berbasis Wi-Fi menghubungkan dua persoalan: perubahan gerakan tubuh dan perubahan kanal komunikasi yang dapat diamati oleh perangkat. Hubungan keduanya tidak selalu langsung karena sinyal juga dipengaruhi lingkungan dan galat pengukuran. Bab ini membahas dasar hubungan tersebut, pembentukan representasi CSI, serta prinsip klasifikasi dan evaluasi. Pembahasan diarahkan pada perubahan temporal fase relatif sebagai representasi utama dan perubahan amplitudo sebagai pembanding.

## 2.1. Jatuh sebagai Objek Deteksi

### 2.1.1. Definisi Jatuh

World Health Organization mendefinisikan jatuh sebagai kejadian yang menyebabkan seseorang tanpa sengaja berada di tanah, lantai, atau permukaan lain yang lebih rendah [@worldhealthorganizationFalls2021]. Unsur ketidaksengajaan membedakannya dari perubahan postur yang direncanakan. Dengan demikian, penurunan posisi tubuh saja belum cukup untuk menentukan bahwa suatu kejadian merupakan jatuh.

Dalam penelitian ini, definisi operasional yang digunakan untuk penyusunan kelas adalah transisi tubuh akibat kehilangan kendali atau keseimbangan menuju lantai atau permukaan pengaman. Apabila data diperoleh melalui peragaan, kelas positif merepresentasikan simulasi transisi tersebut, bukan bukti terjadinya jatuh alami. Duduk, berjongkok, atau berbaring yang dilakukan secara terkendali termasuk non-jatuh. Batas waktu kejadian dan kriteria anotasinya perlu dinyatakan dalam metodologi agar definisi tersebut dapat diterapkan secara konsisten.

### 2.1.2. Dampak Kejadian Jatuh

Jatuh dapat menyebabkan cedera ringan hingga berat, termasuk memar, patah tulang, dan trauma kepala. Dampaknya juga dapat meningkatkan kebutuhan perawatan jangka panjang [@worldhealthorganizationFalls2021]. Persoalan setelah jatuh tidak terbatas pada cedera saat benturan. Ketidakmampuan bangkit dapat membuat seseorang tetap berada di lantai dan bergantung pada kedatangan bantuan.

Blackburn dkk. membahas *long lie*, yaitu keadaan tetap berada di lantai sekitar satu jam atau lebih setelah jatuh. Tinjauan mereka menemukan bukti yang masih terbatas mengenai dampak fisik dan klinis jangka panjang, dengan variasi populasi, cara pengukuran, dan ketergantungan pada ingatan pasien [@blackburnExploringImpactExperiencing2022]. Karena itu, hubungan antara *long lie* dan luaran kesehatan yang buruk perlu dibaca sebagai sintesis bukti yang terbatas, bukan kepastian sebab-akibat untuk setiap korban.

Deteksi otomatis berfungsi mempercepat pengenalan kejadian dan penyampaian peringatan ketika korban tidak mampu meminta bantuan. Igual dkk. menempatkan pemberian bantuan setelah jatuh dan pengurangan waktu berada di lantai sebagai manfaat potensial detektor [@igualChallengesIssuesTrends2013]. Namun, alarm hanya merupakan salah satu tahap dalam pemberian pertolongan. Kecepatan respons tetap bergantung pada penerimaan peringatan dan tindakan penolong.

### 2.1.3. Karakteristik Gerakan Jatuh

Becker dkk. membagi kejadian jatuh secara konseptual menjadi fase sebelum jatuh, gerakan jatuh, benturan, istirahat, dan pemulihan [@beckerProposalMultiphaseFall2012]. Pembagian ini membantu memisahkan kondisi awal, transisi gerak, dan keadaan setelah kejadian. Fase-fase tersebut tidak harus mempunyai durasi yang sama atau seluruhnya terlihat jelas dalam setiap rekaman.

Pada model jatuh yang digunakan DeFall, kecepatan tubuh meningkat selama penurunan lalu berkurang ketika tubuh mencapai permukaan. Susunan kecepatan dan percepatan terhadap waktu digunakan untuk membedakan jatuh dari aktivitas lain [@huDeFallEnvironmentIndependentPassive2022]. Namun, FallDar memperlihatkan bahwa gerakan menahan tubuh pada furnitur, jatuh dari kursi, dan variasi gerakan anggota badan dapat menghasilkan pola berbeda [@yangRethinkingFallDetection2023]. Oleh karena itu, satu lonjakan sinyal tidak dapat diperlakukan sebagai bentuk universal jatuh.

### 2.1.4. Aktivitas Non-Jatuh yang Menyerupai Jatuh

Aktivitas sehari-hari atau *activities of daily living* (ADL) dapat menghasilkan bagian gerak yang menyerupai jatuh. RT-Fall membahas duduk dan berbaring sebagai transisi yang juga diikuti penurunan aktivitas, sedangkan FallDeFi memasukkan membungkuk untuk mengambil benda, melompat, duduk, dan berdiri sebagai aktivitas pembanding [@wangRTFallRealTimeContactless2017; @palipanaFallDeFiUbiquitousFall2017]. Kesamaannya terletak pada perubahan posisi, durasi singkat, atau perubahan energi sinyal, bukan pada makna kejadian.

Duduk cepat dan berbaring sengaja perlu dibedakan melalui urutan gerak serta konteks akhir transisi. Berjongkok dan berlutut juga relevan sebagai kandidat pembanding karena sama-sama menurunkan tubuh. Dalam rancangan penelitian ini, aktivitas tersebut perlu dipertimbangkan untuk menguji batas keputusan sistem, bukan langsung diasumsikan menghasilkan alarm palsu. Kinerja terhadap kelas negatif yang sulit lebih informatif daripada pengujian yang hanya membandingkan jatuh dengan keadaan diam.

## 2.2. Sistem Deteksi Jatuh

### 2.2.1. Sistem Berbasis Perangkat *Wearable*

Sistem *wearable* memperoleh pengukuran dari sensor yang dikenakan, misalnya akselerometer untuk percepatan atau giroskop untuk perubahan orientasi. Kedekatan sensor dengan tubuh memungkinkan pengamatan gerak tanpa bergantung pada cakupan sensor ruangan. Namun, manfaat tersebut mensyaratkan perangkat dipakai dan ditempatkan secara sesuai. Igual dkk. menunjukkan bahwa posisi perangkat yang distandardisasi dalam eksperimen belum tentu mencerminkan cara pengguna membawa perangkat sehari-hari [@igualChallengesIssuesTrends2013].

### 2.2.2. Sistem Berbasis Kamera

Sistem kamera mengenali jatuh melalui perubahan bentuk tubuh, posisi, atau rangkaian citra. Informasi visual membantu menghubungkan gerak dengan postur dan keadaan ruang, tetapi pengamatan dapat terganggu ketika tubuh tertutup objek. Kamera biasa juga memerlukan pencahayaan yang memadai; kamera inframerah atau kedalaman memiliki karakteristik pencahayaan berbeda. RT-Fall membahas perkembangan kamera kedalaman sekaligus keterbatasan cakupan pandang dan privasi pada pendekatan visual [@wangRTFallRealTimeContactless2017].

### 2.2.3. Sistem Berbasis Gelombang Radio

Sistem radio mengamati perubahan sinyal akibat interaksi gelombang dengan manusia. Perangkat dapat ditempatkan di lingkungan sehingga pengguna tidak perlu membawa sensor. WiFall menunjukkan penerapan prinsip tersebut menggunakan CSI dari perangkat Wi-Fi komoditas [@wangWiFallDeviceFreeFall2017]. Kemampuan mengamati gangguan kanal tanpa citra mendukung pemantauan dalam ruangan, tetapi cakupan efektifnya tetap dipengaruhi lintasan propagasi, posisi perangkat, dan penghalang.

### 2.2.4. Perbandingan Pendekatan Deteksi Jatuh

Tabel 2.1 merangkum perbedaan yang relevan bagi pemilihan pengindraan dalam penelitian ini. Perbandingan berfokus pada kebutuhan operasional, bukan pemeringkatan akurasi karena setiap pendekatan diuji dengan perangkat dan data berbeda [@igualChallengesIssuesTrends2013; @wangRTFallRealTimeContactless2017].

Tabel 2.1. Perbandingan pendekatan deteksi jatuh.

| Aspek | *Wearable* | Kamera | Wi-Fi CSI |
| --- | --- | --- | --- |
| Perangkat pada tubuh | Diperlukan | Tidak diperlukan | Tidak diperlukan |
| Pencahayaan | Bukan dasar pengukuran inersial | Berpengaruh pada kamera biasa; berbeda untuk inframerah/kedalaman | Bukan dasar pengukuran kanal |
| Informasi utama | Percepatan/orientasi lokal tubuh | Bentuk, postur, dan gerak visual | Perubahan respons kanal |
| Pengaruh lingkungan/penggunaan | Posisi, kepatuhan pemakaian, dan daya perangkat | Oklusi dan cakupan pandang | *Multipath*, penghalang, dan tata letak perangkat |
| Privasi | Merekam gerak pemakai | Dapat merekam citra dan identitas | Tidak merekam citra, tetapi dapat mengungkap aktivitas |

Wi-Fi dipilih sebagai sarana menguji informasi gerak yang terkandung dalam kanal komunikasi menggunakan perangkat yang mendukung ekstraksi CSI. Pemilihan ini sejalan dengan demonstrasi WiFall, tetapi tidak berarti setiap perangkat Wi-Fi menyediakan akses CSI [@wangWiFallDeviceFreeFall2017; @palipanaFallDeFiUbiquitousFall2017]. Selain itu, ketiadaan citra tidak menghapus seluruh persoalan privasi. Windl dkk. menemukan bahwa persepsi privasi pengindraan radio bergantung pada konteks penggunaan dan informasi yang dapat disimpulkan dari sensor [@windlPrivacySolutionMenace2025].

## 2.3. Pengindraan Manusia Berbasis Gelombang Radio

### 2.3.1. Prinsip *Device-Free Sensing*

*Device-free sensing* mengamati manusia tanpa mensyaratkan perangkat pengindraan pada tubuhnya. Pemancar mengirim sinyal, lingkungan membentuk propagasinya, dan penerima mengukur sinyal yang telah melewati kanal. Kehadiran serta gerakan tubuh mengubah sebagian komponen sinyal sehingga aktivitas dapat diinferensikan dari perubahan pengukuran [@liuWirelessSensingHuman2020]. Istilah *device-free* merujuk pada pengguna yang diamati; sistem tetap memerlukan perangkat pemancar dan penerima.

### 2.3.2. Interaksi Gelombang Radio dengan Tubuh dan Lingkungan

Pemantulan menghasilkan lintasan yang kembali dari permukaan, sedangkan hamburan menyebarkan energi ke berbagai arah. Difraksi memungkinkan gelombang merambat di sekitar tepi penghalang. WiFall memasukkan pengaruh pemantulan, difraksi, dan hamburan dalam pembahasan respons kanal serta memodelkan kontribusi lintasan langsung, lantai, plafon, dan tubuh [@wangWiFallDeviceFreeFall2017]. Penyerapan oleh material merupakan mekanisme pelemahan energi; dalam model kanal efektif, pelemahan tersebut tercakup pada koefisien lintasan dan tidak dipisahkan sebagai pengukuran tersendiri.

Ketika tubuh bergerak, permukaan yang berinteraksi dengan gelombang serta geometri lintasannya ikut berubah. Akibatnya, perubahan pengukuran dapat berasal dari perpindahan tubuh, orientasi, atau perubahan lingkungan. Sistem harus mengenali pola perubahan tersebut, bukan menganggap seluruh gangguan kanal sebagai jatuh.

### 2.3.3. Propagasi *Multipath*

Di dalam ruangan, penerima mengamati superposisi beberapa lintasan propagasi atau *multipath*. Dengan menyederhanakan model kanal yang digunakan FallDar, respons pada frekuensi subcarrier $f_k$ dapat ditulis sebagai

$$
H_k(t)=\sum_{\ell=1}^{L}\alpha_\ell(t)e^{-j2\pi f_k\tau_\ell(t)},
$$

dengan $L$ sebagai jumlah lintasan, $\alpha_\ell(t)$ sebagai koefisien kompleks lintasan, dan $\tau_\ell(t)$ sebagai waktu tundanya [@yangRethinkingFallDetection2023]. Perubahan panjang lintasan mengubah waktu tunda dan fase. Karena komponen tersebut dijumlahkan secara kompleks, kontribusi antarlintasan dapat saling memperkuat atau melemahkan.

Gerakan yang sama tidak harus menghasilkan perubahan amplitudo dan fase yang sama di setiap tempat. Lintasan statis dari dinding atau furnitur membentuk kondisi awal interferensi, sedangkan lintasan yang dipengaruhi tubuh berubah selama gerakan. Konsekuensinya, model yang mempelajari pengukuran langsung dapat sekaligus mempelajari karakteristik ruangan [@yangRethinkingFallDetection2023].

### 2.3.4. Faktor yang Memengaruhi Pengindraan Radio

Posisi dan orientasi tubuh menentukan bagian gerak yang mengubah lintasan secara kuat. Jarak terhadap perangkat, penghalang, dan tata letak ruangan juga memengaruhi sensitivitas. WiFall menunjukkan perubahan kinerja menurut lokasi, tinggi tautan, dan kondisi tautan yang terhalang, sedangkan RT-Fall menemukan bahwa pemindahan furnitur besar dapat mengubah hasil deteksi [@wangWiFallDeviceFreeFall2017; @wangRTFallRealTimeContactless2017].

Perbedaan subjek menambah variasi bentuk gerak, sementara orang atau objek lain yang bergerak menambahkan sumber perubahan kanal. FallDar karena itu memisahkan keragaman lingkungan, gerakan, dan pengguna sebagai masalah yang perlu ditangani [@yangRethinkingFallDetection2023]. Dalam evaluasi, ketiganya tidak dapat digantikan hanya dengan menambah pengulangan aktivitas dari orang yang sama pada satu lokasi.

## 2.4. Wi-Fi, OFDM, dan *Channel State Information*

### 2.4.1. Dasar Komunikasi Wi-Fi

Pada komunikasi Wi-Fi, penerima perlu memperkirakan pengaruh kanal agar dapat memulihkan informasi yang dikirim. Pengaruh tersebut mencakup pelemahan dan perubahan fase akibat propagasi. Pengindraan berbasis Wi-Fi memanfaatkan estimasi kanal yang sama sebagai pengamatan lingkungan, sebagaimana dilakukan WiFall [@wangWiFallDeviceFreeFall2017]. Pembahasan berikut dibatasi pada hubungan sinyal dan respons kanal yang diperlukan untuk memahami CSI.

### 2.4.2. *Orthogonal Frequency-Division Multiplexing*

*Orthogonal frequency-division multiplexing* (OFDM) menggunakan sejumlah subcarrier ortogonal dalam satu kanal. Respons kanal dapat diperkirakan pada subcarrier yang berbeda sehingga variasi kanal terhadap frekuensi tetap terlihat. FallDeFi menjelaskan bahwa pengamatan ini menghasilkan informasi kanal yang lebih terperinci dibandingkan indikator kekuatan sinyal agregat seperti RSSI [@palipanaFallDeFiUbiquitousFall2017]. Namun, jumlah subcarrier yang dapat dibaca melalui alat ekstraksi CSI mengikuti kemampuan perangkat dan tidak selalu sama dengan seluruh subcarrier yang digunakan komunikasi.

### 2.4.3. Respons Kanal

Untuk satu pasangan antena pada subcarrier ke-$k$, hubungan sinyal dapat dinyatakan sebagai

$$
Y_k(t)=H_k(t)X_k(t)+N_k(t),
$$

dengan $X_k(t)$ sebagai sinyal yang dikirim, $Y_k(t)$ sebagai sinyal yang diterima, $H_k(t)$ sebagai respons kanal kompleks, dan $N_k(t)$ sebagai derau. Bentuk ini merupakan penyederhanaan per-subcarrier dari model hubungan masukan–keluaran kanal pada WiFall [@wangWiFallDeviceFreeFall2017]. Pada konfigurasi beberapa antena, respons kanal diperluas menjadi matriks yang menghubungkan antena pemancar dan penerima. Pengukuran CSI merupakan estimasi respons tersebut, sehingga dapat mengandung galat dan bukan nilai kanal ideal yang diketahui secara tepat.

### 2.4.4. *Channel State Information*

CSI merepresentasikan estimasi karakteristik kanal pada subcarrier dan pasangan antena tertentu. Setiap nilainya mempunyai amplitudo dan fase, yang dapat ditulis sebagai

$$
H_k(t)=|H_k(t)|e^{j\phi_k(t)},
$$

dengan $|H_k(t)|$ sebagai amplitudo, $\phi_k(t)$ sebagai fase, dan $j=\sqrt{-1}$. Representasi kompleks ini mempertahankan informasi pelemahan dan pergeseran fase kanal [@liuWirelessSensingHuman2020]. Untuk menyederhanakan notasi, $H$ selanjutnya digunakan bagi CSI terukur apabila tidak sedang dibedakan dari kanal ideal.

Jika pengukuran dilakukan berulang, data tersusun menurut waktu, subcarrier, antena pemancar, dan antena penerima. WiFall, misalnya, membaca beberapa aliran antena dan subcarrier pada setiap paket untuk membentuk representasi aktivitas [@wangWiFallDeviceFreeFall2017]. Dimensi tersebut harus dipertahankan secara konsisten agar pengurangan fase atau perubahan temporal selalu membandingkan komponen yang bersesuaian.

## 2.5. Amplitudo dan Fase CSI

### 2.5.1. Amplitudo CSI

Amplitudo CSI adalah magnitudo respons kanal kompleks. Nilainya menggambarkan besar respons gabungan lintasan pada suatu subcarrier, bukan energi satu pantulan tubuh secara terpisah. Ketika gerakan mengubah fase relatif antarlintasan, superposisi dapat menaikkan atau menurunkan magnitudo. WiFall menggunakan variasi amplitudo tersebut sebagai indikator aktivitas dan masukan klasifikasi [@wangWiFallDeviceFreeFall2017].

Karena merupakan hasil superposisi, perubahan amplitudo tidak selalu sebanding dengan kecepatan atau jarak perpindahan tubuh. Dua aktivitas dapat menghasilkan fluktuasi yang mirip, dan aktivitas yang sama dapat menghasilkan fluktuasi berbeda pada posisi lain. RT-Fall menunjukkan keterbatasan amplitudo untuk memisahkan aktivitas yang berlangsung secara berkesinambungan [@wangRTFallRealTimeContactless2017].

### 2.5.2. Fase CSI

Fase CSI menyatakan sudut respons kanal kompleks. Untuk satu lintasan ideal dengan panjang $d$, komponen fase propagasinya mengikuti $-2\pi d/\lambda$ modulo $2\pi$, dengan $\lambda$ sebagai panjang gelombang. Hubungan ini mengikuti faktor waktu tunda pada model kanal di Bagian 2.3.3. Pada *multipath*, fase CSI adalah sudut jumlah seluruh komponen, sehingga tidak dapat langsung dikonversi menjadi satu jarak tubuh [@yangRethinkingFallDetection2023].

Perubahan fase berpotensi memperlihatkan dinamika yang kurang jelas pada amplitudo. Namun, fase terukur juga menerima pengaruh ketidaksinkronan perangkat. RT-Fall memperoleh indikator aktivitas yang lebih peka melalui selisih fase dua antena, bukan dengan menggunakan fase mentah secara langsung [@wangRTFallRealTimeContactless2017].

### 2.5.3. Perbandingan Informasi Amplitudo dan Fase

Amplitudo dan fase merupakan dua komponen dari respons kanal yang sama, sehingga keduanya membawa informasi yang berkaitan tetapi tidak identik. Amplitudo menggambarkan besar resultan kanal, sedangkan fase menggambarkan sudut resultannya. RT-Fall melaporkan kepekaan selisih fase pada konfigurasi mereka, sementara FallDar menekankan bahwa fitur fase tetap sensitif terhadap lingkungan [@wangRTFallRealTimeContactless2017; @yangRethinkingFallDetection2023]. Kepekaan terhadap perubahan karena itu belum membuktikan keandalan klasifikasi lintas kondisi.

Dalam penelitian ini, perubahan amplitudo dipakai sebagai pembanding karena amplitudo telah digunakan secara langsung pada WiFall dan melalui representasi waktu–frekuensi pada FallDeFi [@wangWiFallDeviceFreeFall2017; @palipanaFallDeFiUbiquitousFall2017]. Perbandingan diarahkan untuk menilai informasi kedua representasi pada rekaman yang sama, bukan mengasumsikan fase relatif lebih unggul sejak awal.

## 2.6. Fase Relatif CSI

### 2.6.1. Keterbatasan Fase Mentah CSI

Fase mentah mengandung fase kanal sekaligus galat pengukuran. Ketidaksinkronan pemancar dan penerima, perbedaan waktu pencuplikan atau penerimaan paket, serta offset perangkat keras dapat menghasilkan perubahan yang tidak berasal dari gerakan. RT-Fall menunjukkan bahwa fase mentah Intel 5300 pada eksperimen mereka tersebar secara tidak stabil, lalu mengurangi pengaruh gangguan bersama dengan menghitung selisih fase antarantena [@wangRTFallRealTimeContactless2017]. Temuan tersebut mendukung pemeriksaan kestabilan fase sebelum penggunaannya sebagai masukan model.

### 2.6.2. Pembentukan Fase Relatif

Untuk dua antena penerima $a$ dan $b$, fase relatif didefinisikan sebagai

$$
\Delta\phi_k(t)=\phi_{k,a}(t)-\phi_{k,b}(t).
$$

Pengurangan dilakukan pada subcarrier, paket, dan antena pemancar yang sama. Apabila kedua rantai penerima mengalami komponen galat fase bersama, komponen tersebut dapat saling menghilangkan dalam pengurangan. RT-Fall menggunakan satu antena pemancar dan dua antena penerima pada perangkat yang sama untuk memanfaatkan sifat tersebut [@wangRTFallRealTimeContactless2017].

Pengurangan ini tidak menghapus semua galat. Offset yang berbeda antarantena, derau, dan ketidakcocokan waktu tetap dapat tersisa. Dengan demikian, dua perangkat penerima yang tidak tersinkronisasi tidak otomatis dapat diperlakukan sebagai pasangan antena yang memiliki galat bersama. Kesesuaian konfigurasi harus diperiksa pada perangkat penelitian.

Bentuk ekuivalen yang langsung menggunakan CSI kompleks adalah

$$
\theta_k(t)=\arg\left(H_{k,a}(t)H_{k,b}^{*}(t)\right),
$$

dengan tanda $*$ sebagai konjugat kompleks. Identitas ini menghasilkan selisih fase terbungkus pada interval utama, misalnya $(-\pi,\pi]$. Nilai $\theta_k$ dan $\Delta\phi_k$ menyatakan besaran sudut yang sama modulo $2\pi$; keduanya tidak selalu sama sebagai bilangan real tanpa penanganan pembungkusan.

### 2.6.3. Perubahan Temporal Fase Relatif

Fase relatif dapat diamati sebagai deret waktu untuk mengikuti dinamika aktivitas. RT-Fall menggunakan perubahan variabilitas selisih fase untuk segmentasi dan informasi waktu–frekuensi untuk membedakan jatuh dari transisi lain. Mereka menemukan bahwa transisi menuju keadaan lebih stabil juga terjadi pada duduk atau berbaring, sehingga segmentasi saja belum menyelesaikan klasifikasi [@wangRTFallRealTimeContactless2017].

Dalam penelitian ini, perubahan temporal dapat direpresentasikan melalui beda sudut sirkular antarsampel,

$$
D_{\phi,k}[n]=\arg\left(e^{j(\theta_k[n]-\theta_k[n-1])}\right).
$$

Bentuk ini menghindari lonjakan semu akibat perpindahan dari $\pi$ ke $-\pi$ pada dua sudut yang sebenarnya berdekatan. Nilainya menyatakan perubahan sudut, bukan kecepatan tubuh. Jika dinyatakan sebagai laju perubahan, selisih tersebut perlu dibagi selang waktu aktual antarsampel. Pilihan antara beda sirkular dan beda fase setelah *unwrapping* merupakan keputusan pengolahan yang harus ditetapkan dalam metodologi.

Pemilihan perubahan temporal fase relatif didasarkan pada potensi mengurangi gangguan bersama sambil mempertahankan perubahan kanal terhadap waktu. Kemampuannya membedakan jatuh dari non-jatuh tetap merupakan pertanyaan empiris. Pola yang ditemukan RT-Fall menjadi dasar hipotesis, bukan hasil yang dapat langsung dipindahkan ke perangkat dan data penelitian ini.

### 2.6.4. Keterbatasan Fase Relatif

Fase relatif tetap bergantung pada geometri antena dan lintasan yang diterima masing-masing antena. Posisi perangkat atau tubuh yang berubah dapat mengubah pola fase, meskipun sebagian galat bersama telah berkurang. FallDar menunjukkan bahwa selisih fase masih sensitif terhadap lingkungan [@yangRethinkingFallDetection2023]. Selain itu, fase pada magnitudo yang sangat kecil dapat menjadi tidak stabil karena sudut resultan mudah berubah oleh derau.

Pembungkusan fase menambahkan ambiguitas: perubahan lebih dari setengah putaran antarsampel tidak dapat dipulihkan hanya dari beda sudut utama. *Unwrapping* juga memerlukan asumsi kesinambungan sehingga celah data panjang dapat merusak hasilnya. Karena itu, pemeriksaan amplitudo, urutan waktu, dan kehilangan paket merupakan bagian dari validitas representasi fase, bukan sekadar pembersihan data tambahan.

## 2.7. Pengolahan dan Representasi CSI

### 2.7.1. Prapemrosesan CSI

Prapemrosesan bertujuan mempertahankan perubahan yang berkaitan dengan aktivitas sambil mengurangi gangguan pengukuran. RT-Fall menggunakan interpolasi dan penyaringan pita, WiFall menggunakan perataan berbobot, sedangkan FallDeFi menggabungkan pengurangan derau berbasis *wavelet* dan analisis komponen utama atau PCA [@wangRTFallRealTimeContactless2017; @wangWiFallDeviceFreeFall2017; @palipanaFallDeFiUbiquitousFall2017]. Perbedaan ini menunjukkan bahwa prapemrosesan mengikuti representasi yang dibangun; seluruh teknik tersebut tidak perlu diterapkan sekaligus.

Teknik yang dipertimbangkan dalam penelitian ini meliputi pemeriksaan urutan waktu dan paket hilang, penanganan pencilan, penyaringan derau, serta pemilihan subcarrier. Interpolasi hanya layak untuk celah yang masih dapat dipertanggungjawabkan; celah panjang perlu ditandai agar tidak membentuk gerakan buatan. Pencilan juga tidak boleh dihapus hanya karena berubah cepat, sebab perubahan cepat dapat menjadi bagian kejadian. Untuk fase, penanganan dilakukan sebagai besaran sudut atau melalui *unwrapping* yang tervalidasi. Jika normalisasi atau pemilihan komponen dipelajari dari data, parameternya ditentukan dari data pelatihan.

### 2.7.2. Segmentasi dan Pembentukan *Window*

Segmentasi menentukan bagian rekaman yang menjadi satu masukan model. Pendekatannya dapat menggunakan pemicu aktivitas atau *window* yang digeser sepanjang deret waktu. RT-Fall menentukan akhir kandidat aktivitas lalu mengambil segmen di sekitarnya, sedangkan FallDar membahas penggunaan *window* dan pergeseran untuk memproses aliran sinyal [@wangRTFallRealTimeContactless2017; @yangRethinkingFallDetection2023]. Pemilihan ukuran harus mempertimbangkan apakah transisi dan konteks sebelum atau sesudahnya tercakup.

*Window* pendek dapat memotong transisi, sedangkan *window* panjang mencampurkan aktivitas lain dan menambah waktu pengamatan. Ketika jendela saling tumpang tindih, beberapa masukan dapat berasal dari kejadian yang sama. Secara konstruksi, potongan tersebut berbagi sampel sehingga tidak merupakan pengamatan independen. Pemisahan data perlu mempertahankan kelompok kejadian atau rekaman agar bagian dari satu kejadian tidak masuk ke pelatihan dan pengujian sekaligus.

### 2.7.3. Representasi Fase Relatif

Representasi fase relatif disusun menurut waktu, subcarrier, dan pasangan antena penerima, dengan antena pemancar yang digunakan dinyatakan secara eksplisit. Perubahan temporal pada Bagian 2.6.3 kemudian dapat dipertahankan sebagai deret waktu atau diringkas menjadi fitur. Representasi deret waktu mempertahankan urutan perubahan, sedangkan fitur merangkum karakteristik seperti penyebaran, besar perubahan, dan durasi. Keduanya merupakan pilihan rancangan yang perlu dibandingkan dengan kebutuhan model, bukan metode yang telah dipastikan optimal.

Pasangan antena harus konsisten sepanjang pengolahan. Pembalikan urutan $a$ dan $b$ mengubah tanda selisih fase sehingga pencampuran urutan dapat mengubah makna masukan. Penggabungan subcarrier juga perlu mempertahankan sifat sirkular fase; rata-rata sudut biasa dapat keliru ketika nilai berada dekat batas pembungkusan.

### 2.7.4. Representasi Perubahan Amplitudo

Dengan $A_{k,a}[n]=|H_{k,a}[n]|$, perubahan amplitudo dapat dibentuk sebagai

$$
D_{A,k,a}[n]=A_{k,a}[n]-A_{k,a}[n-1].
$$

Notasi ini merupakan definisi representasi pembanding dalam penelitian, bukan pernyataan bahwa WiFall atau FallDeFi menggunakan bentuk yang persis sama. Kedua studi tersebut menjadi dasar bahwa amplitudo memuat informasi yang dapat digunakan untuk deteksi jatuh [@wangWiFallDeviceFreeFall2017; @palipanaFallDeFiUbiquitousFall2017]. Apabila dua antena digunakan untuk fase relatif, amplitudo dari antena yang sama dapat dipertahankan sebagai kanal terpisah atau digabung dengan aturan yang dinyatakan jelas.

Kesetaraan perbandingan berarti menggunakan kejadian, label, pembagian data, dan kesempatan penyetelan model yang sama. Kesetaraan tersebut tidak mengharuskan operasi numerik identik karena amplitudo dan fase memiliki sifat berbeda. Penanganan sudut hanya diperlukan untuk fase, sedangkan skala amplitudo mungkin memerlukan normalisasi. Perbedaan pengolahan yang diperlukan harus dilaporkan agar pengaruh representasi tidak tercampur dengan keuntungan prosedur pengujian.

## 2.8. Klasifikasi Jatuh dan Non-Jatuh

### 2.8.1. Klasifikasi Biner

Klasifikasi biner menempatkan jatuh sebagai kelas positif dan non-jatuh sebagai kelas negatif. FallDeFi menggunakan pembagian tersebut untuk membedakan jatuh dari aktivitas pembanding [@palipanaFallDeFiUbiquitousFall2017]. Dalam penelitian ini, label mengikuti definisi operasional pada Bagian 2.1.1. Kandidat transisi yang ditemukan dari sinyal belum otomatis menjadi kelas positif; statusnya ditentukan melalui acuan anotasi.

Untuk masukan berupa *window*, hubungan label dengan waktu kejadian perlu didefinisikan. Jendela dapat memuat awal jatuh, benturan, atau hanya keadaan setelahnya. Ketiga keadaan tersebut tidak dapat diberi makna yang sama tanpa aturan pelabelan. Jendela yang ambigu perlu ditangani secara eksplisit agar model tidak belajar dari target yang saling bertentangan.

### 2.8.2. Pendekatan Klasifikasi

Pendekatan berbasis fitur merangkum karakteristik sinyal sebelum klasifikasi. WiFall menggunakan fitur amplitudo dengan *one-class support vector machine* (SVM), kemudian mengevaluasi *random forest* bersama reduksi dimensi. FallDeFi menggunakan fitur waktu–frekuensi terpilih dengan SVM [@wangWiFallDeviceFreeFall2017; @palipanaFallDeFiUbiquitousFall2017]. Pemisahan fitur dan pengklasifikasi memudahkan pemeriksaan informasi yang dipakai model, tetapi kualitas keputusan tetap bergantung pada representasi tersebut.

Pendekatan berbasis urutan mempertahankan struktur temporal sebagai bagian keputusan. DeFall membandingkan urutan kecepatan dan percepatan dengan templat menggunakan *dynamic time warping* (DTW), sedangkan FallDar mempelajari representasi dari informasi kecepatan dengan jaringan saraf [@huDeFallEnvironmentIndependentPassive2022; @yangRethinkingFallDetection2023]. Keduanya menunjukkan bahwa perbandingan urutan dapat dilakukan melalui pencocokan templat maupun pembelajaran. Model akhir penelitian ini belum ditetapkan; pembahasan tidak diperluas ke arsitektur yang belum relevan dengan bentuk data.

### 2.8.3. Pembentukan Keputusan Deteksi

Keluaran model dapat berupa kelas atau skor yang diubah menjadi keputusan melalui ambang. Prediksi pada satu *window* belum sama dengan satu alarm kejadian karena beberapa jendela berurutan dapat merujuk pada jatuh yang sama. Secara konseptual, keputusan dapat dibentuk dari konsistensi beberapa prediksi, penggabungan rentang positif yang berdekatan, atau pembatasan alarm berulang. Setiap aturan mengubah kompromi antara sensitivitas, alarm palsu, dan waktu deteksi, sehingga harus ditetapkan sebelum pengujian akhir.

## 2.9. MR60FDA2 sebagai Sensor Referensi

### 2.9.1. Prinsip dan Keluaran Sensor

MR60FDA2 merupakan modul radar gelombang milimeter sekitar 60 GHz untuk deteksi keberadaan dan jatuh. Spesifikasi yang disediakan produsen menjelaskan penggunaan FMCW serta konfigurasi pemasangan dan ambang deteksi [@seeedtechnologyco.ltd.MR60FDA2FallDetection2024]. Berbeda dari CSI Wi-Fi, keluarannya telah melalui pemrosesan internal perangkat.

Dokumentasi API menyediakan pembacaan keberadaan manusia melalui `getHuman()` dan status jatuh melalui `getFall()`, serta pengaturan tinggi pemasangan, ambang, dan sensitivitas [@seeedstudioGettingStartedMR60FDA2]. Status tersebut merupakan keputusan sensor. Waktu saat status diterima oleh pencatat tidak dengan sendirinya menyatakan waktu awal jatuh.

### 2.9.2. Peran dalam Penelitian

Dalam penelitian ini, MR60FDA2 diposisikan sebagai sensor pendamping untuk mencatat deteksi pembanding dan membantu pemeriksaan waktu kandidat kejadian. Catatan statusnya dapat disandingkan dengan rekaman CSI dan acuan anotasi untuk menemukan ketidaksesuaian. Dengan peran ini, MR60FDA2 membantu pemeriksaan label, tetapi tidak menjadi satu-satunya penentu kebenaran label. Rincian pemasangan, pencatatan waktu, sinkronisasi, dan penyelesaian perbedaan anotasi ditempatkan pada Bab Metodologi.

### 2.9.3. Keterbatasan sebagai Sensor Referensi

Pengaturan sensitivitas dan kriteria deteksi menunjukkan bahwa keluaran MR60FDA2 mengikuti pemrosesan perangkat [@seeedstudioGettingStartedMR60FDA2]. Sebagai konsekuensi metodologis, keluaran tersebut perlu diperiksa terhadap kemungkinan deteksi terlewat, alarm palsu, dan keterlambatan. Besarnya kesalahan atau keterlambatan tidak diasumsikan dari spesifikasi, melainkan perlu diukur pada konfigurasi penelitian.

Label acuan, keluaran MR60FDA2, dan prediksi CSI harus disimpan sebagai tiga informasi berbeda. Jika prediksi CSI dinilai hanya berdasarkan keluaran MR60FDA2, hasilnya menunjukkan kesesuaian antarsistem, bukan ketepatan terhadap kejadian sebenarnya. Pembedaan ini mencegah kesalahan sensor referensi diwariskan sebagai kebenaran dalam evaluasi.

## 2.10. Dasar Evaluasi Sistem Deteksi Jatuh

### 2.10.1. Matriks Konfusi

Matriks konfusi membandingkan kelas sebenarnya dengan prediksi. *True positive* (TP) adalah jatuh yang dikenali sebagai jatuh, *false positive* (FP) adalah non-jatuh yang dikenali sebagai jatuh, *true negative* (TN) adalah non-jatuh yang dikenali dengan benar, dan *false negative* (FN) adalah jatuh yang terlewat. Definisi ini digunakan dalam evaluasi FallDeFi [@palipanaFallDeFiUbiquitousFall2017]. Unit yang dihitung harus dinyatakan: satu TP dapat berarti satu *window* atau satu kejadian, bergantung pada prosedur evaluasi.

### 2.10.2. Metrik Klasifikasi

*Precision* mengukur proporsi prediksi jatuh yang benar, sedangkan *recall* mengukur proporsi jatuh yang berhasil ditemukan. F1 merupakan rata-rata harmonik keduanya, sebagaimana digunakan FallDeFi [@palipanaFallDeFiUbiquitousFall2017]. Sensitivitas adalah nama lain *recall*, sedangkan spesifisitas mengukur proporsi non-jatuh yang ditolak dengan benar, seperti dalam evaluasi RT-Fall [@wangRTFallRealTimeContactless2017]. Rumusnya adalah

$$
\operatorname{Precision}=\frac{TP}{TP+FP},\qquad
\operatorname{Recall}=\frac{TP}{TP+FN},
$$

$$
\operatorname{Specificity}=\frac{TN}{TN+FP},\qquad
F_1=\frac{2TP}{2TP+FP+FN}.
$$

*False-positive rate* (FPR) dan akurasi dinyatakan sebagai

$$
\operatorname{FPR}=\frac{FP}{FP+TN},\qquad
\operatorname{Accuracy}=\frac{TP+TN}{TP+FP+TN+FN}.
$$

FPR sama dengan satu dikurangi spesifisitas. Akurasi dapat tampak tinggi ketika kelas negatif mendominasi, meskipun banyak jatuh tidak dikenali. Sebagai ilustrasi matematis, pada data dengan 99 non-jatuh dan satu jatuh, prediksi selalu non-jatuh menghasilkan akurasi 99% tetapi *recall* nol. Contoh ini bukan hasil eksperimen. Jika penyebut suatu metrik nol, nilainya tidak terdefinisi secara matematis; aturan pelaporannya harus dijelaskan.

Istilah *false alarm rate* (FAR) tidak boleh disamakan antarpublikasi hanya berdasarkan namanya. FallDar menggunakan jumlah non-jatuh yang salah dikenali dibagi seluruh non-jatuh, sedangkan rumus *false alarm* pada WiFall menggunakan jumlah salah deteksi jatuh dibagi jumlah jatuh [@yangRethinkingFallDetection2023; @wangWiFallDeviceFreeFall2017]. Oleh karena itu, angka hasil perlu dibandingkan setelah penyebutnya diperiksa. Jumlah alarm palsu per jam juga merupakan ukuran berbeda dari FPR.

### 2.10.3. Satuan Evaluasi dan Latensi

Evaluasi per-*window* menilai setiap potongan masukan, sedangkan evaluasi per kejadian menilai apakah satu jatuh memperoleh alarm yang sesuai. Pada evaluasi kejadian, prediksi positif berulang perlu dipadankan dengan kejadian sehingga satu jatuh tidak dihitung berkali-kali. Untuk aliran pemantauan, jumlah TN juga bergantung pada cara waktu tanpa jatuh dibagi menjadi unit evaluasi. Karena itu, FPR per-*window* tidak langsung menggambarkan banyaknya gangguan alarm selama penggunaan.

Latensi deteksi adalah selang antara waktu acuan kejadian dan alarm pertama yang sesuai,

$$
L=t_{\mathrm{alarm}}-t_{\mathrm{acuan}}.
$$

Waktu acuan dapat berupa awal transisi atau benturan, tetapi pilihannya harus disebutkan. Penggunaan sampel setelah kejadian menambah waktu tunggu sebelum keputusan dapat dibuat; waktu komputasi saja tidak mewakili seluruh latensi. Selain itu, latensi tidak mencakup waktu kedatangan penolong. Pemilihan metrik, pembagian data, pemadanan alarm, dan perhitungan waktu yang digunakan dalam penelitian ditetapkan pada Bab Metodologi.

## 2.11. Penelitian Terkait

### 2.11.1. Deteksi Jatuh Menggunakan Amplitudo CSI

WiFall menunjukkan bahwa variasi amplitudo CSI dapat digunakan untuk mengenali jatuh dengan perangkat Wi-Fi komoditas. Sistemnya mencakup pengurangan derau, deteksi anomali, pembentukan representasi, dan klasifikasi. Penggunaan SVD serta *random forest* memperbaiki hasil dibandingkan konfigurasi awal pada pengujian mereka, tetapi kinerja tetap dipengaruhi lokasi dan penghalang [@wangWiFallDeviceFreeFall2017]. Kontribusinya menjadi dasar penggunaan amplitudo sebagai pembanding, bukan jaminan bahwa fitur amplitudo bebas dari pengaruh lingkungan.

FallDeFi mempertahankan amplitudo sebagai sumber informasi, tetapi menekankan fitur waktu–frekuensi dan pemilihan fitur yang tahan terhadap perubahan kondisi. Pengurangan derau berbasis *wavelet*, PCA, dan STFT digunakan sebelum klasifikasi SVM. Penulis melaporkan akurasi sekitar 93% pada kondisi sistem telah dilatih dan mendekati 80% ketika lingkungan berubah [@palipanaFallDeFiUbiquitousFall2017]. Penurunan tersebut menunjukkan pentingnya skema pengujian: kinerja pada kondisi yang dikenal tidak cukup untuk menyatakan generalisasi.

### 2.11.2. Deteksi Jatuh Menggunakan Fase CSI

RT-Fall menggunakan selisih fase antarantena sebagai dasar segmentasi aktivitas. Variasi fase dan profil waktu–frekuensi membantu menentukan kandidat gerakan yang kemudian diklasifikasikan menggunakan SVM. Namun, fitur akhirnya menggabungkan informasi amplitudo dan selisih fase, sehingga RT-Fall bukan eksperimen yang seluruh keputusannya hanya bergantung pada fase relatif [@wangRTFallRealTimeContactless2017].

Pada pengujian kantor dengan model dari tiga subjek dan evaluasi pada tiga subjek lain, RT-Fall melaporkan sensitivitas 93% dan spesifisitas 89%. Penulis juga melaporkan seluruh 620 jatuh pada bagian eksperimen tersebut berhasil disegmentasi [@wangRTFallRealTimeContactless2017]. Kedua hasil ini mengukur tahap berbeda: keberhasilan mengambil segmen tidak sama dengan keberhasilan klasifikasi. Pemisahan tersebut relevan ketika menilai kontribusi fase relatif terhadap sistem secara keseluruhan.

### 2.11.3. Deteksi Jatuh yang Mempertimbangkan Lingkungan dan Pengguna

DeFall mengalihkan representasi dari pola kanal langsung menuju estimasi kecepatan dan percepatan. Urutan tersebut dibandingkan dengan templat yang dibangun menggunakan DTW. Penulis melaporkan tingkat deteksi di atas 95% dan alarm palsu di bawah 1,50% pada pengujian LOS dan NLOS menggunakan satu pasangan transiver [@huDeFallEnvironmentIndependentPassive2022]. Klaim kemandirian lingkungan merujuk pada kemampuan menerapkan templat tanpa pelatihan ulang di lingkungan uji, bukan jaminan bahwa seluruh kondisi propagasi tidak berpengaruh.

FallDar memperluas perhatian ke variasi gerakan dan pengguna. Sistemnya menggabungkan estimasi kecepatan, pembangkitan data jatuh, dan pembelajaran fitur yang mengurangi ketergantungan pada identitas. Penulis melaporkan FAR 5,7% dan *missed alarm rate* 3,4% pada evaluasi keseluruhan [@yangRethinkingFallDetection2023]. Namun, pengumpulan data selama enam bulan tetap menggunakan jatuh yang diperagakan dan data *dummy*, serta memilih rekaman dengan satu orang pada area pengamatan. Durasi pengumpulan yang panjang karena itu tidak sama dengan validasi jatuh alami pada banyak orang secara bersamaan.

### 2.11.4. Perbandingan Penelitian Terkait

Tabel 2.2 membandingkan konfigurasi dan cakupan data, sedangkan Tabel 2.3 memisahkan representasi serta evaluasinya. Pemisahan ini diperlukan agar hasil numerik dibaca bersama kondisi pembentukannya. Jumlah subjek di bawah mengikuti kelompok eksperimen yang dilaporkan; angka dari kelompok berbeda tidak otomatis dijumlahkan sebagai peserta unik.

Tabel 2.2. Perangkat dan cakupan eksperimen penelitian terkait.

| Studi | Perangkat dan konfigurasi | Subjek dan aktivitas |
| --- | --- | --- |
| WiFall [@wangWiFallDeviceFreeFall2017] | Intel 5300; tautan MIMO 3 × 3; satu/dua tautan menurut skenario | Laboratorium: 10 mahasiswa; asrama: 8 orang; ruang uji RF: satu orang. Berjalan, duduk, berdiri, dan jatuh; pengujian satu orang dalam area |
| RT-Fall [@wangRTFallRealTimeContactless2017] | Router 5 GHz dan Intel 5300; satu antena Tx, dua Rx; 100 paket/detik | 6 relawan; empat lingkungan; aliran jatuh, gerakan menyerupai jatuh, dan ADL yang berkesinambungan |
| FallDeFi [@palipanaFallDeFiUbiquitousFall2017] | Dua laptop Intel 5300, masing-masing dua antena; 5,2 GHz | 3 relawan usia 27–30 tahun; lima lingkungan; empat kategori jatuh beserta variasinya; duduk, berdiri, membungkuk, berjalan, dan aktivitas lain; skenario satu/dua orang |
| DeFall [@huDeFallEnvironmentIndependentPassive2022] | Dua laptop Intel 5300; kanal 5,805 GHz, lebar pita 40 MHz | Templat dan verifikasi awal memakai *dummy*; 3 relawan pada eksperimen manusia awal dan 7 relawan tambahan untuk variasi pengguna; jatuh maju, mundur, dan lateral serta non-jatuh |
| FallDar [@yangRethinkingFallDetection2023] | Perangkat Wi-Fi komoditas; satu antena penerima dipakai; pengambilan CSI 1.000 Hz | 5 anggota keluarga pada pengamatan rumah dan 2 relawan pada eksperimen kantor; 21 kelas normal, 6 kelas jatuh dengan 24 subvariasi; juga memakai *dummy*, data sintetis, dan sebagian dataset terbuka |

Tabel 2.3. Representasi, pengolahan, dan batas interpretasi hasil penelitian terkait.

| Studi | Representasi dan metode | Skema/hasil utama | Keterbatasan yang relevan |
| --- | --- | --- | --- |
| WiFall [@wangWiFallDeviceFreeFall2017] | Amplitudo; perataan berbobot, LOF, fitur/SVD; *one-class* SVM dan *random forest* | Tiga skenario dalam ruangan; abstrak melaporkan rata-rata *precision* 94% dan *false alarm* 13% untuk RF | Definisi metrik perlu diperiksa; terpengaruh lokasi/penghalang; belum mengisolasi kontribusi fase |
| RT-Fall [@wangRTFallRealTimeContactless2017] | Selisih fase untuk segmentasi; interpolasi, penyaringan; fitur amplitudo dan fase dengan SVM | Pengujian lintas subjek di kantor: sensitivitas 93%, spesifisitas 89%; juga diuji di lingkungan lain | Fitur gabungan; perubahan furnitur dapat mengubah kinerja |
| FallDeFi [@palipanaFallDeFiUbiquitousFall2017] | Amplitudo; *wavelet*, PCA, STFT, seleksi fitur berurutan, SVM | Pengujian kondisi terlatih dan perubahan lingkungan; akurasi sekitar 93% dan mendekati 80% | Tiga relawan muda; tahap segmentasi memiliki kalibrasi lingkungan |
| DeFall [@huDeFallEnvironmentIndependentPassive2022] | Estimasi kecepatan/percepatan; templat DTW dan keputusan pencocokan | Pemindahan lingkungan tanpa pelatihan ulang; tingkat deteksi >95%, alarm palsu <1,50% pada evaluasi LOS/NLOS | Representasi turunan dan templat jatuh; gerakan orang lain tetap dapat mengganggu |
| FallDar [@yangRethinkingFallDetection2023] | Estimasi kecepatan; augmentasi generatif dan jaringan deteksi dengan pembelajaran identitas | Evaluasi lingkungan, gerak, dan pengguna; FAR 5,7%, *missed alarm rate* 3,4% secara keseluruhan | Campuran jatuh peragaan, *dummy*, dan sintetis; rekaman rumah diseleksi untuk satu orang |

Kelima studi memperlihatkan bahwa perbedaan kinerja tidak hanya berasal dari amplitudo atau fase. Segmentasi, fitur, model, konfigurasi perangkat, dan aktivitas negatif juga berubah. Karena itu, tabel tersebut tidak digunakan untuk menyatakan satu sistem paling baik secara universal. Informasi yang paling relevan bagi penelitian ini adalah faktor mana yang perlu disamakan untuk menguji perbedaan representasi secara langsung.

## 2.12. Sintesis dan Celah Penelitian

### 2.12.1. Sintesis Literatur

CSI menyediakan pengamatan perubahan kanal akibat gerakan, tetapi pengamatan tersebut merupakan gabungan kontribusi tubuh, lingkungan, dan perangkat. WiFall serta FallDeFi menunjukkan kegunaan amplitudo, sedangkan RT-Fall menunjukkan kegunaan selisih fase untuk segmentasi dan klasifikasi berbasis fitur gabungan [@wangWiFallDeviceFreeFall2017; @palipanaFallDeFiUbiquitousFall2017; @wangRTFallRealTimeContactless2017]. Temuan ini mendukung keberadaan informasi aktivitas pada kedua komponen CSI, tanpa menetapkan bahwa salah satunya selalu lebih baik.

Fase relatif mengurangi sebagian gangguan bersama antarantena, tetapi tetap dipengaruhi kanal dan konfigurasi pengukuran. DeFall dan FallDar memperlihatkan upaya mengurangi ketergantungan tersebut melalui representasi gerak yang lebih terstruktur [@huDeFallEnvironmentIndependentPassive2022; @yangRethinkingFallDetection2023]. Dengan demikian, pemilihan representasi harus dinilai bersama ketahanannya terhadap non-jatuh yang menyerupai jatuh, perbedaan subjek, dan perubahan kondisi pengamatan.

### 2.12.2. Keterbatasan Penelitian Sebelumnya

Dalam lima studi yang dibandingkan, amplitudo digunakan secara langsung pada dua sistem awal, RT-Fall menggunakan fitur gabungan, dan dua studi berikutnya menekankan estimasi kecepatan. Cakupan ini tidak cukup untuk menyatakan dominasi amplitudo pada seluruh bidang. Keterbatasan yang lebih spesifik adalah bahwa hasil sistem-sistem tersebut belum secara langsung menjawab perbandingan perubahan temporal fase relatif dan perubahan amplitudo ketika faktor pengujian lain disamakan.

Perbedaan perangkat, representasi, subjek, dan metrik membatasi penarikan kesimpulan lintas artikel. Selain itu, jatuh yang diperagakan tidak sepenuhnya mewakili jatuh alami, sebagaimana ditekankan Igual dkk. dalam pembahasan keterbatasan evaluasi dunia nyata [@igualChallengesIssuesTrends2013]. Karena itu, kinerja penelitian ini perlu dibatasi pada populasi, aktivitas, dan lingkungan yang benar-benar diuji.

### 2.12.3. Celah Penelitian

Berdasarkan literatur yang ditelaah, pertanyaan yang belum terjawab secara langsung adalah bagaimana perubahan temporal fase relatif CSI bekerja sebagai representasi utama ketika dibandingkan dengan perubahan amplitudo pada rekaman, label, kondisi pengujian, dan prosedur evaluasi yang sama. Celah ini merupakan kebutuhan pembuktian untuk rancangan perbandingan tersebut, bukan klaim bahwa penggunaan fase atau perbandingan amplitudo–fase belum pernah diteliti.

Penelitian ini diarahkan untuk menilai perbedaan kemampuan kedua representasi dalam mengenali jatuh dan menolak aktivitas non-jatuh yang serupa. Prediksi CSI dan keluaran MR60FDA2 dinilai terhadap label acuan yang dipisahkan dari keduanya. Perbandingan tersebut diharapkan menjelaskan manfaat dan batas perubahan temporal fase relatif tanpa menyamakan keberhasilan klasifikasi dengan jaminan pertolongan klinis. Prosedur pengumpulan data, pemilihan model, serta pengujian hipotesis dijelaskan pada Bab Metodologi.
