                                                                                                                                                                                  Fall detection with a single Doppler radar
                                                                                                                                                                                 sensor and LSTM recurrent neural network




2022 IEEE 65th International Midwest Symposium on Circuits and Systems (MWSCAS) | 978-1-6654-0279-8/22/$31.00 ©2022 IEEE | DOI: 10.1109/MWSCAS54063.2022.9859430
                                                                                                                                                                             Takayuki Imamura                                      Vasily G. Moshnyaga                                        Koji Hashimoto
                                                                                                                                                                       Graduate School of Engineering                           Dept. Electronics Eng.& CS                              Dept. Electronics Eng.& CS
                                                                                                                                                                            Fukuoka University                                      Fukuoka University                                     Fukuoka University
                                                                                                                                                                          Fukuoka 814-0180, Japan                                Fukuoka 814-0180, Japan                                 Fukuoka 814-0180, Japan
                                                                                                                                                                       td212003@cis.fukuoka-u.ac.jp                               vasily@fukuoka-u.ac.jp                                 khashi@fukuoka-u.ac.jp

                                                                                                                                                                      Abstract—Falls are a serious health concern and a main cause                   The traditional approach to Doppler radar-based fall
                                                                                                                                                                   of injuries among elders living independently at home. In this                 detection is to extract several hand-crafted discriminative
                                                                                                                                                                   paper, we describe a new system for real-time automatic fall                   features from the received signals and then apply them to fall
                                                                                                                                                                   detection. In contrast to related formulations, the system employs             classification algorithms. E.g. K-Nearest Neighbors [5], Kernel
                                                                                                                                                                   a single continuous-wave micro-Doppler radar sensor to monitor                 Matching Pursuit [6], Support Vector Machines [7], Bayesian
                                                                                                                                                                   a subject and Long Short-Term Memory based recurrent neural                    Classifiers [8], Fuzzy integrals [9], and their combination [10].
                                                                                                                                                                   network (RNN) to identify falls from the time-frequency                        Choosing the classification features is, however, a complicated
                                                                                                                                                                   characteristics of the sensor’s returns. It does not require extra
                                                                                                                                                                                                                                                  task. It requires domain-specific knowledge of Doppler
                                                                                                                                                                   hardware or big data set to classify abrupt and slow falls from
                                                                                                                                                                                                                                                  signatures and affects both the accuracy and scalability of the
                                                                                                                                                                   non-fall actions with superior detection accuracy.
                                                                                                                                                                                                                                                  solution [11]. In addition, the features vary to a large extent
                                                                                                                                                                      Keywords— Doppler radar, sensor, machine learning, Long                     with size, habits, and the health conditions of monitored
                                                                                                                                                                   Short-Term Memory, RNN, fall detection                                         individuals.
                                                                                                                                                                                                                                                      With advances in deep learning architectures and algorithms,
                                                                                                                                                                                            I.    INTRODUCTION                                    recent efforts in Doppler radar-based fall detection have
                                                                                                                                                                                                                                                  concentrated on statistical modelling of human falls by using
                                                                                                                                                                      Falls are the leading cause of fatal and non-fatal injuries                 deep learning techniques. In contrast to the traditional approach,
                                                                                                                                                                   among older people. According to [1], just in the year 2020,                   these techniques rely on artificial neural networks that learn the
                                                                                                                                                                   27.1% of all adults aged ≥ 65 years reported falling at least                  most informative features and classification boundaries directly
                                                                                                                                                                   once (35 Million cases), 66.1% of all injures registered in this               from input data without human intervention. Jokanovic et al.
                                                                                                                                                                   age group were caused by accidental falls, and 55.1% of all                    [12] used two stacked autoencoders and a logistic regression
                                                                                                                                                                   deaths from unintentional injury were fall-related. Elders living              classifier to categorize falls. Tian et al [13] proposed to use two
                                                                                                                                                                   alone are especially vulnerable to falls as they might not be                  Doppler-radars and two neural networks to capture and process
                                                                                                                                                                   able to rise due to injury or declining muscular activity [2].                 data in horizontal and vertical planes separately and then fuse
                                                                                                                                                                   Therefore, devices capable of detecting falls and calling for                  the results to determine the spatiotemporal patterns of falls.
                                                                                                                                                                   support have become a necessity for elders living                              These methods can distinguish an abrupt fall from no-fall
                                                                                                                                                                   independently at home.                                                         motions, such as sitting, bending and walking. However, they
                                                                                                                                                                      A large number of automatic fall detection technologies have                either require expensive Range-Doppler radars [12] to capture
                                                                                                                                                                   been proposed over the last two decades. (See [3], [4] for                     both the frequency shift and the range or restrict themselves to
                                                                                                                                                                   surveys in the field). Wearable fall detectors are accurate and                multi-radar or multi-antenna installations [13-14]. Yoshino et
                                                                                                                                                                   inexpensive but must be worn all the time, which is difficult for              al [15] presented a convolutional neural network (CNN) based
                                                                                                                                                                   old and forgetful people. Therefore, context-aware systems                     on fall detection from signatures of a single continuous-wave
                                                                                                                                                                   with unobtrusive sensors embedded in the environment are                       Doppler radar that works in the conventional time-frequency
                                                                                                                                                                   considered more suitable for monitoring people at home. In                     domain. While their approach classifies abrupt falls quite well,
                                                                                                                                                                   this article, we focus on the accuracy improvement of Doppler-                 it fails to recognize slow falls accurately.
                                                                                                                                                                   radar based context-aware fall detection systems.                                 In this work, we also use a single continuous-wave micro-
                                                                                                                                                                       Doppler-radar sensor is one of the most promising non-                     Doppler radar sensor that operates in the frequency-time
                                                                                                                                                                   intrusive fall detection modalities: it transmits an electro-                  domain. However, contrary to [15], we employ a Long-Short-
                                                                                                                                                                   magnetic wave over a high-frequency range and measures the                     Term Memory (LSTM) based RNN to improve fall recognition.
                                                                                                                                                                   signal returns. In contrast to optical, ultrasonic and IR sensors,             Compared to CNN, LSTM/RNN is more complex but better at
                                                                                                                                                                   a Doppler-radar sensor outputs snapshots of the subject’s                      learning long-term interdependences in data streams. In
                                                                                                                                                                   velocities. It neither depends on the subject’s occlusion,                     contrast to LSTM based fall detectors (e.g. [16-18]), which also
                                                                                                                                                                   illumination, and distance, nor infringes human privacy. Also,                 rely on Doppler radars for people monitoring, our work does
                                                                                                                                                                   unlike accelerometers, it neither requires direct contact with a               not require large data sets or multiple sensor installations. The
                                                                                                                                                                   subject nor control. However, robust identification of various                 article introduces a real-time LSTM based system that achieves
                                                                                                                                                                   types of falls based on Doppler radar is still a challenge.                    robust fall detection with a single Doppler radar sensor.




                                                                                                                                                                      978-1-6654-0279-8/22/$31.00
                                                                                                                                                                         Authorized                    ©2022
                                                                                                                                                                                    licensed use limited to:    IEEE Brawijaya. Downloaded on September 01,2026 at 11:24:02 UTC from IEEE Xplore. Restrictions apply.
                                                                                                                                                                                                             Universitas
                                                                                                                                        T
  Micro‐                                                                  Digital
                           AMP       N1        N2        LF     ADC



                                                                                        Signal strength
  wave                                                                     Data

           Doppler Radar   Enhancement and Filtering Circuit   8bit MCU
              Module
 Figure 1. Block-diagram of Doppler radar sensor
                                                                                                                       w1                           w2     w3 w4w5

                                                                                                                       Time                   (a)
                                                                                                          100

                                                                                                           80

                                                                                                           60

   Figure 2. The signal waveforms at the output of the Doppler radar module                                40
                                                                                                          Hz
                                                                                                           20

                                                                                                               0
                                                                                                                   0     2         4    6
                                                                                                                                       Time              (c)
                                                                                                                             (b)

                                                                                      Figure 4 (a) An actual input signal with five activity intervals w1,…, w5;
                                                                                      (b) The spectrogram X(w1) of activities in the time interval w1; (c) The
                                                                                      normalized representation of spectrogram X(w1)

                                                                                    by two band-stop/notch filters (N1 and N2) and the low-pass
                                                                                    filter (LF) to reject block frequencies exceeding 60Hz as well
                                                                                    as frequencies induced by the commercial power supply.
                                                                                    Finally, the 8-bit microcontroller unit (MCU) converts the
      Figure 3. A block diagram of the proposed fall detection system               filtered analog signal (4.0Vp-p and 2.5V offset) into a 10 bits
                                                                                    digital representation and sends it to the LSTM-based system
                                                                                    for analysis. Fig.2 exemplifies the sensor performance by
   The main contribution of this work is twofold. First is a                        depicting the output signals of the Doppler module (Fig.2, a),
compact, inexpensive, and non-contact Doppler radar sensor,                         the operational amplifier (Fig.2, b) and the ADC (Fig.2, c),
capable of capturing, filtering, enhancing, and delivering the
                                                                                    respectively.
frequency shift in a digital form with a high level of accuracy.
The second is an LSTM-based fall detection system capable of                        B. The LSTM-based fall-detection
recognizing different fall patterns from the outputs of a single                       Fig.3 shows the proposed LSTM based fall detection system.
Doppler radar sensor. Unlike related formulations, such as [16-                     The system receives a 10-bit digital signal from the sensing
18] that use LSTM and Doppler radar sensors to identify abrupt                      unit and writes it in the FIFO buffer. If the signal amplitude
falls, the proposed system can distinguish fast and slow falls                      overcomes a predefined threshold (T), the controller initiates
from non-fall actions, such as squatting, laying down, etc. The                     the shift-right operation in the successive k-clock cycles to
experiments show that the system works in real-time and has                         collect k+1-signals in the buffer. Else, it only compares the
superior accuracy compared to related work.                                         signal without shifting. After k clock cycles, the collected
              II.     THE PROPOSED FALL DETECTION                                   string of k+1 signals S0 ... Sk is broadcast to the Short-Time
                                                                                    Fourier Transform (STFT) to produce the time-frequency
The proposed fall detection system consists of a Doppler                            spectrogram, X(wi), for the string. The system cuts the DC-
sensor, a small computer board and a server.                                        supply frequencies exceeding 60Hz, normalizes the values and
                                                                                    outputs the spectrogram in 28x28 grayscale representation.
A. The Doppler radar sensor
                                                                                    Fig.4(a) illustrates the process on the example of 50s long
We developed a compact and inexpensive Doppler sensor that                          signal stream captured by the Doppler Radar sensor. The
outputs a signal of frequency proportional to the target’s                          stream reflects five intervals of the subject’s activity (w1-w5).
velocity and processes the signal; Namely, it magnifies, filters,                   Fig. 4(b) shows the spectrogram, X(w1), obtained for the time
and converts the analog signal into a digital representation.                       interval w1; Fig. 4(c) depicts the normalized representation of
  Fig.1 shows the sensor’s block diagram. The Doppler radar                         the spectrogram. The pixel brightness in the figures reflects
module contains a built-in patch antenna and an integrated IQ                       velocity: the faster the motion, the brighter the pixel.
circuitry to compute a phase shift (Doppler frequency)                                 The normalized spectrogram representation is then sent to
between the transmitted (10.5GHz) signal and the reflected                          the LSTM/RNN classifier, which employs a seven-layer
signal. The phase shift is then amplified by almost four orders                     architecture (Fig.5, a) to identify a fall. (Note that dashed
of magnitude by the operational amplifier (AMP) and filtered                        layers in the figure are used only in the training phase).




       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:24:02 UTC from IEEE Xplore. Restrictions apply.
                   Layer 1             Layer 2                     Layer 3          Layer 4
     Input           Fully               Batch                     Dropout
                  connected 1            Norm

                  Layer 7             Layer 6                                        LSTM
                                                                   Layer 5
## Output                            Fully
## Softmax                                          Dropout
                                    connected 2
                                                      (a)

              …                                                              …
       X(t)                         X(t-1)                  X(t)                           X(n)
                                      LSTM                   LSTM               …        LSTM
         LSTM
                        Unfolding
       V(t)                                                                 …
                                             V(t-1)                  V(t)       V(n-1)          V(n)
                                                       (b)
     Figure 5. The LSTM/RNN architecture (a); temporal unfolding (b)
                                                                                                           Figure 6. A photo of the Doppler sensor circuitry (view from the top)
   The classifier processes inputs in subsequences of fixed
length (n=28) and cascades each cell into exactly n copies of
itself by using temporal unfolding [19] with n/2 overlap
between the subsequences. Fig.5 (b) illustrates the unfolding
technique implemented in the classifier. Overall the
architecture has 784 cells in the fully connected input layer,
128 cells in the LSTM (hidden) layer and six cells in the fully
connected output layer.
   The output cells of the LSTM correspond to six classes:
                                                                                                                                Figure 7. Experimental settings
   (1) abrupt fall, induced by balance loss when standing,
  (2) abrupt motion-related fall, caused by a slip, a trip, or a                                       To reduce the data transmission bandwidth between the sensor
      stump,                                                                                           and the system, we use the ADC data sampling frequency of
                                                                                                       100 Hz. The input buffer, STFT and LSTM/RNN and the
   (3) slow-fall or fading, caused by illness or intoxication, etc.
                                                                                                       decision and alert generator were implemented in software by
   (4) squatting,                                                                                      using Python programming language and Pytorch v.19.0
   (5) lying down on the mat, and                                                                      library. Messages from the decision and alert generator to the
   (6) unspecified (i.e., all other no-fall actions, such as                                           caregiver’s phone were conveyed via the LINE Notify free
working, standing, jumping, etc.)                                                                      web-based service and LINE freeware application.
   The probability scores of the classes are calculated by using                                          We trained the classifier on 1000 data samples labelled into
the softmax and the cross-entropy error. The output with the                                           batches by Pytorch, placed in Dataloder and applied as input
maximum probability score determines the classification result                                         for the RNN. To validate the classifier, we utilized 200
for the current time window wj.                                                                        randomly selected samples. The validation results showed that
                                                                                                       the LSTM classifier had detection accuracy of 98% and 93%
   After analyzing the time window wi, the classification                                              for abrupt and slow falls, respectively. After training, the
continues for wi+1, and on. The system decides based on                                                LSTM/RNN classifier was uploaded into the system and tested.
classification results obtained for an interval of 10s. If during
this time it detects a fall, followed by a no-motion (i.e., the
number of low-value inputs exceeds a given threshold), the                                                    IV. EXPERIMENTAL EVALUATION AND RESULTS
alert generator (Fig.3) notifies the pre-specified caregiver with                                      We evaluated the system performance in laboratory settings
a message: “FALL! Help!” Otherwise, the system does not                                                with the sensor being set on the ceiling at the 2.5m height
generate an alert. It only records the fall time and begins                                            observing the room as shown in Fig. 7. Two subjects (male and
processing the next time-window (wi+1) processing.                                                     female, both healthy adults) of 52–181cm height and 51-85 kg
                                                                                                       weight range took part in the experiments.
                             III.     IMPLEMENTATION                                                      In the first experiment, each subject randomly performed the
  The system is realized in hardware and software. Fig. 6                                              following sequence of actions: walking, falling (on the floor
shows the photograph of the doppler sensor circuit. The circuit                                        mat), standing, squatting, walking, slow falling (fading), lying
includes a 10MHz Doppler radar module (NJR4178J) from                                                  on the flow for 5-8 seconds, standing, falling and no motion for
JRC, a low-cost programmable open-source platform (Arduino                                             5-10 sec. All falls have been executed over the floor mat
UNO) with an ATmega328P microcontroller on board, and                                                  positioned at 3m (horizontal) distance (D) from the sensor’s
several IC components in the enhancement and filtering circuit.                                        perpendicular point (see Fig.7). Each subject repeated the
The sensor communicates with a PC (HP Spectre x360,                                                    sequence five times. Thus, we tested 100 real-time actions in
2.8GHz i7 CPU, 16GB DRAM, Win10 OS) via a USB.                                                         total.




       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:24:02 UTC from IEEE Xplore. Restrictions apply.
                        TABLE I. CONFUSION MATRIX                                                                    V. CONCLUSION
                               Output class                               Recall
 True class                                                                                    This article introduced a new automatic system to detect
                  (1)    (2)    (3)    (4)    (5)               (6)      Score (%)
       (1)       100      0      0      0      0                 0         100              falls with a Doppler radar sensor. As the experiments revealed,
       (2)         0      97     3      0      0                 0          97              the system identified falls accurately in real-time. At the same
       (3)         5      0      93     0      2                 0          93              time, we acknowledge that the number of subjects, who
       (4)         0      0      0      99     0                 1          99              participated in the experimental evaluation, was small and the
       (5)         0      0      3      0     97                 0          97
                                                                                            testing was in the laboratory environment. Therefore, we now
       (6)         0      2      0      4      0                 94         94
      Total      105      99     99    103    99                 99                         are extending the study to check system performance on more
 Precision (%)   95.2    97.9  93.9   96.1   98.9               97.9                        subjects, people of different body shapes, heights, and ages.
                                                                                            Future studies will also focus on testing the system in
  Table I shows the results in terms of fall recognition                                    residential settings (rooms, bathrooms, stairs, etc.)
Precision and Recall scores computed for the tested samples.
As one can see, our system has an average precision score of                                                                REFERENCES
96.5% for abrupt falls (classes 1-2) and 93.9% for slow falls,
                                                                                           [1] America's Health Rankings analysis of CDC, Behavioral Risk Factor
while reaching a perfect (100%) recall score for abrupt falls                                  Surveillance     System,        United     Health     Foundation,
with an average recall score of 96.6% for all classes.                                         AmericasHealthRankings.org, accessed 2022.
   The second experiment was dedicated to evaluating the                                   [2] Tinetti, et al. “Predictors and prognosis of inability to get up after falls
                                                                                               among elderly persons”. J. American Medical Association, 269 (1)
impact of distance between the subject and the doppler sensor                                  Jan.1993, 65-70.
on the accuracy of the system. We experimented with the same
                                                                                           [3] M.Mubashir, et al. A survey on fall fetection: principles and approaches,
setting (Fig. 7) and with the same subjects, who repeated the                                  Neurocomputing, vol.100, pp.144–152, Jan. 2013.
same sequence of actions for two distances (D=4m and D= 5m)
                                                                                           [4] T.Xu, et al. New advances and challenges of fall detection systems: A
from the mat to the Doppler sensor.                                                            Survey. Applied Science, MDPI, 2018, 8, 418.
   Table II shows the results in terms of recall score. Although                           [5] L.Liu, et al. Fall detection using doppler radar and classifier fusion. IEEE-
the detection accuracy decreases with the distance from a                                      EMBS Int.Conf. Biomed.& Health Informatics, 2012
subject to the sensor, the system provides a 91% recall score at                           [6] Q.Wu, Y.D.Zhang, W.Tao, M.G.Amin. Fall Detection Based on Sequential
a 5-meter distance and a 96.3% recall score on average at a 3 m                                Modeling of Radar Signal Time-Frequency Features, IEEE ICHI, 2013.
distance.                                                                                  [7] Y.Kim and H.Ling, Human activity classification based on micro-Doppler
                                                                                               signatures using a support vector machine, IEEE Trans. Geoscience &
                                                                                               Remote Sensing (47) 5, pp.1328–1337, May 2009.
      TABLE II. DETECTION ACCURACY (%) VS. DISTANCE FROM SENSOR
                            Output class                 Average                           [8] Q.Wu, Y.Zhang, “Radar-based fall detection based on Doppler time–
  Distance                                                Score                                frequency signatures for assisted living”. IET Radar Sonar Navig., vol. 9,
              (1)    (2)    (3)    (4)     (5)    (6)
                                                                                               issue 2, pp. 164–172, Feb. 2015
     3m       100     98     94     96      98     92      96.3
     4m        96     94     92     94      96     90      93.7                            [9] M.Ren, J.Cai, Y.Zhu, J.Han. Radar signal feature extraction based on
     5m        96     90     90     90      94     88      91.3                                wavelet ridge and high order spectra analysis, IET Int. Radar Conf. 2009,
                                                                                               pp.1-5.
  Table III compares this work with prior studies in terms of                              [10] B.Erol, et al, Range-Doppler Radar Sensor Fusion for Fall Detection, Proc.
the classification model, the number of samples used for                                        IEEE Radar Conf. (RadarConf).
training the respective model, the number of patterns which can                            [11] M. Amin, et al. Radar Signal Processing for Elderly Fall Detection - The
be recognized, and the average fall detection accuracy (Recall                                  future for in-home monitoring, IEEE Signal Processing Magazine, March
Score). In this table, AE abbreviates autoencoders, UWB is                                      2016, p.71-80.
ultra-wide frequency modulated continuous band radar,                                      [12] B.Jokanovic, et al. “Fall detection using deep learning in range-Doppler
FMCW is frequency modulated continuous wave radar. Note                                         radars”. IEEE Trans. Aerospace & Electronic Syst., vol.54, no.1, Feb.2018,
that [12], [13, [15] show simulation results on data sets, while                                pp.180-189.
the others provide results of real-time measurement. We                                    [13] Y.Tian, et al. RF-based fall monitoring using convolutional neural
observe that our system has better fall detection accuracy even                                 networks, Proc.ACM Interact. Mob. Wearable Ubiquitos Technol. 2 (3),
                                                                                                Art.137, Sep.2018.
though it was trained on a small data set and uses a single
                                                                                           [14] J. Hong, et al. Cooperative fall detection using doppler radar and array
Doppler-radar sensor with one transmitter and one antenna.                                      sensor. IEEE Int. Symp. Personal Indoor & Mobile Radio Comm. pp.3492–
                                                                                                3496, 2013.
           TABLE III. COMPARISON WITH RELATED RESEARCH
                   Type &      Number of   Number of Average                               [15] H.Yoshino, et al. Fall detection on a single Doppler-radar sensor by using
                  Number        samples     patterns    Fall                                    convolutional neural networks, IEEE SMC, pp.2875-2878, 2019.
## Work Classifier
                 of sensors         non- fall non- Detection                               [16] J.Maitre, et al.Fall Detection with UWB Radars and CNN-LSTM
                             falls
                 /antennas           fall         fall Acc. (%)                                 Architecture. IEEE J. Biomed.& Health Informatics, Oct. 2020, pp.1-11.
 [12]    2 AE      1 range    408     117   4      3      88
 [13]   2 CNN        2/2    550,541 541    18      40     92                               [17] Y.Sun, et al, Privacy preserving fall Detection with deep learning on mm
 [15]    CNN    FWCW 1/1 500          250   2      2      94                                   wave radar signal. 2019 IEEE VCIP, pp.1-4.
 [16] LSTM+CNN UWB 3/3        600     60    1      1      88                               [18] H. Li, et al. Bi-LSTM network for multimodal continuous human activity
 [17]   LSTM    FMCW 2/2 711         3415   1      6      69                                    recognition and fall detection, IEEE Sensors J. vol.20, no.3 2019, pp.1191-
 [18]   LSTM    FMCW 2/2 n/a          n/a   1      5     84a                                    1201
 Ours   LSTM    FMCW 1/1 600          400   3      3      95                               [19] Hochreiter, Sepp; Schmidhuber, Jürgen (1997). "Long Short-Term
                                             a
                                                 The bi-LSTM accuracy in radar only case
                                                                                                Memory". Neural Computation. 9 (8): 1735–1780.




        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:24:02 UTC from IEEE Xplore. Restrictions apply.

