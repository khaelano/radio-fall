## 2022 International Electronics Symposium (IES)


                                                                                                                                   Implementation of Fall Detection for The Elderly
                                                                                                                                     Home Support using 24-GHz Radar Sensor
                                                                                                                                   Amran, Elly Purwantini, Ardik Wijayanto, Rusminto Tjatur Widodo, Budi Nur Iman, Edi Satriyanto, Eru Puspita, Hary Oktavianto
## Electrical Engineering Department
## Politeknik Elektronika Negeri Surabaya
                                                                                                                                                                                        Surabaya, Indonesia
                                                                                                                                                                                     ranamran20@gmail.com
                                                                                                                                                                                         hary@pens.ac.id


                                                                                                                                   Abstract— In this paper, we propose a development of a                       contrast sensitivity, or visual field has been consistently
                                                                                                                               smart home system for assisting elderly people by                                reported to increase the likelihood of falling. The extrinsic




## 2022 International Electronics Symposium (IES) | 978-1-6654-8971-3/22/$31.00 ©2022 IEEE | DOI: 10.1109/IES55876.2022.9888595
                                                                                                                               implementing a fall detection using 24-GHz radar sensor. The                     factors are factors from outside the elderly such as the
                                                                                                                               system is mounted on the ceiling of the room and the system                      environment, walking aids, and social support. Research
                                                                                                                               records the doppler frequency shift signals of a body moving
                                                                                                                               with a duration of 2.5 seconds. The recorded signals are
                                                                                                                                                                                                                shows severe injuries occur in the afternoon with a
                                                                                                                               transformed into spectrogram images with a size of 119 x 65                      percentage of 50.5%, which is caused by increasingly
                                                                                                                               pixels. Then the spectrogram images are recognized by the                        dimmer lighting. Early detection and improvement of risk
                                                                                                                               Convolutional Neural Network (CNN) algorithm. There are 3                        factors can significantly reduce the rate of future falls [4].
                                                                                                                               classes to be recognized, namely: falling, vacant, and walking.                            Nowadays there have been many approaches and
                                                                                                                               The dataset was acquired, built, and trained by using Edge                       techniques used to detect falls. Such as wearable devices
                                                                                                                               Impulse platform. The hardware used in the deployment phase                      that use Inertial Measurement Unit (IMU) sensors by
                                                                                                                               is Arduino Nano 33 BLE Sense. The experimental results show                      measuring the change in acceleration on the 3-axes and the
                                                                                                                               an accuracy rate of the training phase and the testing phase of                  change in the angle of pitch, row, and yaw. The drawback of
                                                                                                                               98.1% and 96.30%, respectively.
                                                                                                                                                                                                                the device is that it must always be used, whereas the elderly
                                                                                                                                  Keywords—Elderly home support, fall detection, 24-GHz                         sometimes forgets to use the device and refused on the
                                                                                                                               radar sensor, edge impulse                                                       grounds of discomfort [7]. In addition, the use of cameras in
                                                                                                                                                                                                                fall detection is also sensitive to dark room lighting
                                                                                                                                                     I. INTRODUCTION                                            conditions and violates patient privacy [6]. Currently, there
                                                                                                                                         Elderly, according to Law Number 13 of 1998 is                         have also been several studies that use radar sensors for the
                                                                                                                               someone who has reached the age up to 60 (sixty) years old                       detection of hand movements, heartbeats, and falls, but the
                                                                                                                               and above. In almost five decades, the percentage of                             final processing of data including the application of the
                                                                                                                               Indonesian’s elderly has increased by about twice (1971-                         CNN method is still carried out on computers [5][9][10].
                                                                                                                               2020), that is, to 9.92% (26 million), where the elderly                         Therefore, this research uses a radar sensor to eliminate the
                                                                                                                               women are about one percent more than the elderly men                            shortcomings in the use of the wearable and camera sensors.
                                                                                                                               (10.43% versus 9.42%). The data from the National Socio-                                   In this paper, fall detection is designed by utilizing
                                                                                                                               Economic Survey of Indonesia (Survei Sosial-Ekonomi                              radar sensors to acquire the object movement and the
                                                                                                                               Nasional Indonesia or Susenas) in 2020 shows that 9.80% of                       Convolutional Neural Network (CNN) algorithm to classify
                                                                                                                               the elderly live alone, and the percentage of older women                        the object movement. The doppler frequency shift signals
                                                                                                                               living alone is almost three times that of older men (14.13%                     from the radar sensor are acquired with a duration of 2.5
                                                                                                                               versus 5.06%) [1].                                                               seconds, with a sampling frequency of 1.5 kHz. Then, the
                                                                                                                                         Falls are an unpredictable state, in which the                         acquired signals are converted into a spectrogram with a
                                                                                                                               condition of the elderly is under or on the floor accidentally                   size of 119 x 65 pixels as the input image to the CNN. The
                                                                                                                               with the presence or without witnesses. Falls are one of the                     process of data acquisition, data labeling, spectrogram
                                                                                                                               leading causes of death and injury to the elderly. About 20%                     conversion, and CNN’s model training are carried out on the
                                                                                                                               to 30% of the elderly who have a high degree of disability                       Edge Impulse platform. For the implementation stage, the
                                                                                                                               due to falling will experience a loss of freedom in carrying                     CNN’s model is deployed in the Arduino Nano 33 BLE
                                                                                                                               out daily activities [2]. The incidence of falls in the elderly                  Sense. The doppler frequency shift signals from the radar
                                                                                                                               every year is recorded to be around 30% occur in the elderly                     sensor are acquired by the Arduino Nano 33 BLE Sense to
                                                                                                                               aged 65 years old or older and for the elderly aged 80 years                     be recognized and sends the prediction result to the
                                                                                                                               old or more fall incidence rate increases to 50% worldwide                       smartphone. From the application built in the smartphone,
                                                                                                                               [3]. It is estimated that 646,000 people die every year as a                     the information of the detected object under the fall
                                                                                                                               result of falls, that makes falls the second cause of death                      detection system can be monitored in a real-time.
                                                                                                                               from accidental injuries, after a traffic accident. Two factors                            This paper is organized into four sections. The ﬁrst
                                                                                                                               cause falls in the elderly are, namely, intrinsic factors and                    section describes the background and general description of
                                                                                                                               extrinsic factors. The intrinsic factors of risk fall in the                     the conducted research. The second section discusses the
                                                                                                                               elderly such as gender, influence of medicine, and visual                        system design. The third section informs the experimental
                                                                                                                               impairment. Older women are particularly prone to falling                        results. Finally, the fourth section concludes the results.
                                                                                                                               and increasing the severity of injuries. Then, the elderly who
                                                                                                                               consume a lot of medicines can cause some changes in the
                                                                                                                               body, such as drowsiness and loss of balance so it risks of
                                                                                                                               falls. In addition, damage to visual acuity, stereopsis,


                                                                                                                               978-1-6654-8971-3/22/$31.00 ©2022 IEEE                                     166

                                                                                                                                    Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:36:53 UTC from IEEE Xplore. Restrictions apply.
                     II. SYSTEM OVERVIEW                                         human movement from a distance, especially falling motion,
                                                                                 it is necessary to design a signal conditioning concatenation
A. System Design
                                                                                 based on sensor datasheets. The input frequency is limited to
                                                                                 the range of 60 - 8000 Hz using a band pass filter, however,
                                                                                 to detect human movements, it is only in the range of 40 to
                                                                                 500 Hz. The signal gain can be set in the range from 40 to
                                                                                 73 dB, which can reach the movement of objects up to 15
                                                                                 meters. Fig 3 shows the signal conditioning circuit. The first
                                                                                 operational amplifier is used as the high-pass filter and the
                                                                                 second operational amplifier is used as the low-pass filter.




                        Fig. 1: System Diagram
         Fig 1 illustrates the system diagram block. The
radar sensor is CDM324 24-GHz. The output of the radar
sensor is adjusted by the signal conditioning circuit in order
to conform with the analog to digital converter (ADC) of the
Arduino Pro Mini. The Arduino Pro Mini is used to handle
the signal acquisition. The Arduino Pro Mini listens to the                                        Fig. 3: Signal conditioning circuit
radar sensor for every 2.5 seconds as one data frame and
sends the data frame to the Arduino Nano 33 BLE Sense via                        D. Building the Datasets
serial communication. The Arduino Pro Mini uses a                                    The development of the CNN in this research is shown
sampling frequency of 1.5 kHz. The Arduino Nano 33 BLE                           in Fig 4, divided into two phases, namely the training phase
Sense converts the data frame into the spectrogram and                           and the testing phase. In the training phase, the collected
predict the recognition result. The prediction of the                            datasets consist of several classes namely falling, vacant,
recognition result is sent to the smartphone via Bluetooth                       and walking. Falling class means that an object is detected
communication.                                                                   moving away from the radar sensor, which means the person
                                                                                 has fallen on the floor. Vacant class means that there is no
                                                                                 moving object under the radar sensor. Walking class means
B. CDM324 24-GHz Sensor                                                          that an object is passes under the beam of the radar sensor.
         The CDM324 is a 24-GHz frequency doppler
module with an 80-degree azimuth and 32-degree elevation
wave beam. The sensor's power consumption is 40 mA (at
5V), and the antenna design is also relatively tiny, with three
header pins for simpler integration, resulting in an overall
module size of 25x25x6 mm, as shown in Fig 2. The sensor
is powered by a 5V battery and has a range of up to 15
meters. VCC, IF, and GND is the three pins available.
Where IF-output is a doppler frequency with an amplitude
ranging from -300 to 300 mV as an output.                                                         Fig. 4: Training and testing phases




                                                                                               Fig. 5: Cropping the raw data as dataset
                    Fig. 2: CDM324 radar sensor                                           The datasets are constructed on the Edge Impulse
C. Signal Conditioning Circuit                                                   platform as follows. Firstly, the Arduino Nano 33 BLE Sense
                                                                                 was programmed to capture the radar signals and to send the
         The CDM324 radar sensor does not have an                                radar signals to the PC (Personal Computer) via serial
integrated set of filters and amplifiers. To be able to detect                   communication. In the PC side, a data forwarder program


                                                                           167

     Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:36:53 UTC from IEEE Xplore. Restrictions apply.
developed by Edge Impulse was running. The data forwarder
receives the data from the selected serial port and then
transmits the received data to the Edge Impulse as a raw data.
Secondly, the raw data is labelled manually by hand. Fig 5
shows the labelling process by cropping the raw data for
about 2.5 seconds. The collected datasets in this research is
270 samples. Finally, from 270 samples, the 216 samples are
used to train the CNN’s model for all classes and 54 samples
are used for the validation.
E. Features Extraction
          The objective of feature extraction is to transform
the signal into a representative which enhances the
recognition performance. For this purpose, the radar signals
are converted into spectrograms. The radar signals with a
duration of 2.5 seconds are segmented into overlapping
frames of 200 milliseconds with a stride of 100 milliseconds.
Then 119 frames will be formed. Those frames are processed
using 128 FFT size. The results are spectrogram images with
a size of 119 x 65 pixels. Fig 6 and Fig 7 are an example of a
signal of a falling person and its spectrogram.




                 Fig. 6: Signal of falling person




                                                                                                        Fig. 8: CNN architecture

             Fig. 7: Spectrogram of falling person
F. Convolutional Neural Network                                                                 III. EXPERIMENTAL RESULT
         The CNN classifier architecture is shown in Fig 8.                                The training phase has been done in the Edge
The CNN consists of 2 convolution layers with max-pooling                        Impulse. For the deployment stage, the trained model is
layer and dropout layer among them. The input is a 2-                            implemented in the Arduino Nano 33 BLE Sense. The
dimensional array of 119 x 65 pixels. The convolution                            firmware generated by the Edge Impulse is utilizing Tensor
process is carried out in the first layer with 8 filters and the                 Flow Lite. The Tensor Flow Lite is incapable of training
second layer using 16 filters. The max-pooling layer serves                      models and is only capable of executing inferences. The
by reducing the number of parameters from the convolution                        firmware to be uploaded into the Arduino Nano 33 BLE
process by taking the largest value at a predetermined filter                    Sense requires 374,504 bytes of program storage space and
size. The dropout layer is to set random input units to zero                     87,384 bytes of dynamic memory. The Arduino Nano 33
with a frequency of 0.25 (this rate is defined) at every step                    BLE Sense has a flash memory of 1 Megabytes and SRAM
during training. It means that one in every four input units is                  of 256 kilobytes.
randomly dropped. At the flatten layer, the 2-dimensional                                  The system is implemented in a room with a
array processed in the previous layer is converted into a 1-                     dimensions of 5 x 3 x 3 meter. The system is located on the
dimensional array, to be processed on a dense layer using                        ceiling at the center of the room with the sensor position
the SoftMax function to produce a falls prediction.                              facing down, as illustrated in Fig 9. For the experimental
                                                                                 set-up as shown in Fig 10, a thin mattress is laid out on the
                                                                                 floor so people can demonstrate the movement of walking
                                                                                 and falling safely under the sensor.




                                                                           168

     Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:36:53 UTC from IEEE Xplore. Restrictions apply.
                    Fig. 9: Sensor placement                                                  Fig. 13: Spectrogram of walking person

                                                                                          In the training phase, there were 270 data samples
                                                                                for all classes with 216 data samples for the training phase
                                                                                (each class has 72 samples) and 54 data for the testing phase
                                                                                during data validation of all classes (each class has 18
                                                                                samples). The CNN’s model has obtained an accuracy of
                                                                                98.1% and a loss of 0.08. The confusion matrix of the
                                                                                training phase is shown in Table 1.

                                                                                TABEL I: Confusion Matrix (Validation Set)
## Falling        Vacant      Walking
                                                                                          Falling          94.4%           0%            5.6%
                                                                                          Vacant            0%            100%            0%
                                                                                         Walking            0%             0%            100%
                                                                                         F1-score           0.97           1.00           0.97

                                                                                    The system has been tested using 18 new data in each
                  Fig. 10: Experimental set-up                                  class, bringing the total to 54 test data. Based on the
                                                                                confusion matrix shown in Table II, the overall accuracy is
                                                                                96.30%.
          Fig 11, Fig 12, and Fig 13 show the spectrograms
of falling person, vacant, and walking person.                                  TABEL II: Confusion Matrix (Testing Result)
## Fall        Noise       Walking      Uncertain
                                                                                       Fall          17              0            1            0
                                                                                      Noise          0             18             0            0
                                                                                    Walking          0               0          17             1
                                                                                    F1-score        0.97           1.00       0.94             -




            Fig. 11: Spectogram of falling person




                                                                                 Fig. 14: The notiﬁcation in the smartphone when a falling
                                                                                                     person is detected
                                                                                    When the CNN outputs a prediction of falls, it triggers
                Fig. 12: Spectrogram of vacant                                  the smartphone to pop a notiﬁcation up to inform the user.
                                                                                Fig 14 shows the notiﬁcation in the smartphone. The


                                                                          169

    Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:36:53 UTC from IEEE Xplore. Restrictions apply.
application running in the smartphone also records the                                                 IV. CONCLUSION
CNN’s prediction activities of falling person and walking
person while vacant condition is not reported. The report                                In this research, the fall detection using 24-GHz
generated by the application in the smartphone to the user is                   radar sensor for the elderly home support using CNN was
shown in Fig 15. During the system operating, it consumes a                     proposed. The system was implemented and tested through
current of 56,2 mA to 59,6 mA at 5 Volts working voltage.                       experimentation with three classes. The radar signals are
                                                                                sampled with a duration of 2.5 seconds then are converted
                                                                                into spectrograms with a size of 119 x 65 pixels for the
                                                                                CNN that requires 2-dimensions as the input data. The
                                                                                experimental results showed an accuracy rate of 98.1% in
                                                                                the training phase and 96.30% in the testing phase. When
                                                                                the CNN generates a prediction of falling or walking, a
                                                                                notiﬁcation to the user will be displayed.


## REFERENCES
                                                                                [1]  N. R. Sari, I. Maylasari, F. W. R. Dewi, R. Putrianti, S. W. Nugroho
                                                                                     dan H. Wilson, Statistik Penduduk Lanjut Usia, Indonesia: Badan
                                                                                     Pusat Statistik, 2020.
                                                                                [2] S. Butarbutar, "Karakteristik Lansia dan Kejadian Jatuh di Posyandu
                                                                                     Lansia Kecamatan Sipoholon," 2020.
                                                                                [3] D. R. Sofia, "Status Nutrisi Lansia dan Risiko Jatuh Pada Lansia,"
                                                                                     The Indonesian Journal of Health Science, vol. 11, no. 1, pp. 22-29,
                                                                                     2019.
                                                                                [4] N. Fauziah, "Gambaran Kejadian Jatuh dan Faktor Risiko Jatuh Pada
                                                                                     Lansia di Wilayah Kerja Puskesmas Sekelola Kota Bandung," 2019
                                                                                [5] D. Yacchirema, J. S. de Puga, C. Palau and M. Esteve, "Fall detection
                                                                                     system for elderly people using IoT and Big Data," Procedia
                                                                                     Computer Science, vol. 130, pp. 603-610, 2018
                                                                                [6] N. Zurbuchen, P. Bruegger and A. Wilde, "A Comparison of Machine
                                                                                     Learning Algorithms forFall Detection using Wearable Sensors,"
## 2020 International Conference on Artificial Intelligence in
                                                                                     Information and Communication (ICAIIC), pp. 427-431, 2020.
                                                                                [7] F. Harrou, N. Zerrouki, Y. Sun and A. Houacine, "An Integrated
                                                                                     Vision-Based Approach for Efficient Human Fall Detection in a
                                                                                     Home Environment," IEEE Access, vol. 7, pp. 114966-114974, 2019.
                                                                                [8] L. Anishchenko, A. Zhuravlev and M. Chizh, "Fall Detection Using
                                                                                     Multiple Bioradars and Convolutional Neural Networks," Sensors, vol.
                                                                                     19, no. 5569, 2019.
 Fig. 15: The report generation from the CNN’s prediction                       [9] J. Saluja, J. Casanova and J. Lin, "A Supervised Machine Learning
                                                                                     Algorithm for Heart-rate Detection Using Doppler Motion-Sensing
                                                                                     Radar," IEEE Journal of Electromagnetics, RF and Microwaves in
                                                                                     Medicine and Biology, 2019
                                                                                [10] E. Lourenço Chuma, L. L. Bravo Roger, G. G. de Oliveira, Y. Iano
                                                                                     and D. Pajuelo, "Internet of Things (IoT) Privacy–Protected, Fall
                                                                                     Detection System for the Elderly Using the Radar," 2020 IEEE
                                                                                     International Smart Cities Conference (ISC2), pp. 1-4, 2020.




                                                                          170

    Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:36:53 UTC from IEEE Xplore. Restrictions apply.

