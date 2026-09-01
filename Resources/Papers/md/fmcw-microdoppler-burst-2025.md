                                                                                                                                                                                                             2025 6th International Conference on Electronic Communication and Artificial Intelligence (ICECAI)

                                                                                                                                                                                         Lightweight Fall Detection Based on FMCW Micro-
                                                                                                                                                                                           Doppler and Power Burst Signatures Extraction




2025 6th International Conference on Electronic Communication and Artificial Intelligence (ICECAI) | 979-8-3315-1476-1/25/$31.00 ©2025 IEEE | DOI: 10.1109/ICECAI66283.2025.11170524
                                                                                                                                                                                                                     Run Jia                                                                         Binke Huang*
                                                                                                                                                                                             School of Information and Communications Engineering                              School of Information and Communications Engineering
                                                                                                                                                                                                            Xi’an Jiaotong University                                                          Xi’an Jiaotong University
                                                                                                                                                                                                              Xi’an 710049, China                                                                Xi’an 710049, China
                                                                                                                                                                                                             jiarun@stu.xjtu.edu.cn                                                          *
                                                                                                                                                                                                                                                                                              bkhuang@mail.xjtu.edu.cn

                                                                                                                                                                                           Abstract—Nowadays, the aging problem is intensified, and the                   network to complete fall detection based on range-doppler
                                                                                                                                                                                       demand for the elderly fall detection at home is increased. The fall               histogram.
                                                                                                                                                                                       detection system based on millimeter-wave frequency modulated
                                                                                                                                                                                       continuous wave (FMCW) radar shows its advantages. This paper                          Previous fall detection models often use micro-Doppler
                                                                                                                                                                                       proposes a lightweight fall detection system based on FMCW                         spectrogram for direct training, which leads to a large amount of
                                                                                                                                                                                       radar. The noise is removed by ordered statistics constant false                   computation. In this paper, the motion events are detected, and
                                                                                                                                                                                       alarm rate (OS-CFAR) filter. After that, the power burst curve                     the one-dimensional micro-Doppler frequency estimations of
                                                                                                                                                                                       (PBC) is used to detect motion events. The micro-Doppler                           different parts are extracted from the velocity-time spectrum by
                                                                                                                                                                                       frequency estimations of human body parts are extracted by                         using power burst curve (PBC). Finally, a lightweight network
                                                                                                                                                                                       CLEAN, density-based spatial clustering of applications with noise                 is proposed, which uses one-dimensional curves to detect falls.
                                                                                                                                                                                       (DBSCAN) and k-nearest neighbors (KNN) algorithm. Finally, 1D
                                                                                                                                                                                       convolutional neural network (1D-CNN) and bidirectional long                           The rest of this paper is organized as follows. The Section Ⅱ
                                                                                                                                                                                       short-term memory (Bi-LSTM) network are used to make the final                     introduces the FMCW radar, radar parameters setting and data
                                                                                                                                                                                       detection. The accuracy of the fall detection model is 93.23%, with                acquisition method. The Section Ⅲ introduces the signal model
                                                                                                                                                                                       precision, recall and F1 score exceeding 90%.                                      and signal processing methods, including radar data
                                                                                                                                                                                                                                                                          preprocessing and feature extraction. The Section Ⅳ introduces
                                                                                                                                                                                           Keywords—Deep learning, fall detection, lightweight network,                   the lightweight deep learning network architecture for fall
                                                                                                                                                                                       millimetre-wave radar, radar signal processing.                                    detection, and gives the analysis and discussion of the results.
                                                                                                                                                                                                                                                                          Finally, we conclude this paper in Section Ⅴ.
                                                                                                                                                                                                              I. INTRODUCTION
                                                                                                                                                                                           According to the 2024 population statistics, the world                                 II. EXPERIMENTAL SETUP AND MEASUREMENT
                                                                                                                                                                                       population aged over 65 is approximately 1.29 times that of the                        The IWR1443 and DCA1000 kit of Texas Instruments (TI)
                                                                                                                                                                                       population aged under 5 years [1]. In the case of limited medical                  are used to collect human gait data. Among them, IWR1443 is a
                                                                                                                                                                                       staff, a monitoring system that can operate independently in the                   76-81GHz millimeter wave sensor with 3 transmit (TX)
                                                                                                                                                                                       elderly's home is becoming more and more important. The                            antennas and 4 receive (RX) antennas. We use 1 TX antenna and
                                                                                                                                                                                       monitoring system is required to achieve low missed detection                      4 RX antennas, and set the starting frequency to 77GHz. The
                                                                                                                                                                                       rate, low false alarm rate, whole-process monitoring, and user                     DCA1000 transmits large amounts of radar data in real time to
                                                                                                                                                                                       friendliness [2].                                                                  the PC for storage and further processing. The detailed radar
                                                                                                                                                                                                                                                                          parameters are shown in Table 1.
                                                                                                                                                                                           Currently, there are three commonly used methods to extract
                                                                                                                                                                                       human gait features: wearable sensors, optical sensors and radar                      The experiment is conducted in a classroom, as shown in
                                                                                                                                                                                       sensors [3]. Regarding the application of millimeter-wave                          Figure 1, where the radar height is 1.5m, the subjects' activity
                                                                                                                                                                                       frequency modulated continuous wave (FMCW) radar to extract                        area is a 10m × 2m rectangle, 1.3m away from the radar. The
                                                                                                                                                                                       human gait features, Yao et al. [4] use multilevel thresholding                    designed motion patterns and corresponding labels are shown in
                                                                                                                                                                                       OTSU method to binarize the velocity-time spectrum, and use                        Table 2. In order to ensure the safety of subjects, subjects are
                                                                                                                                                                                       image mask to remove noise, Then the feature envelopes of the                      required to fall on the cushion. Subjects include 6 males and 2
                                                                                                                                                                                       velocity-time spectrum are extracted according to the energy                       females, ranging in age from 21 to 24, with heights ranging from
                                                                                                                                                                                       percentage. Yao et al. [5] use short time Fourier transform                        1.63m to 1.83m, and weights ranging from 51kg to 93kg. Each
                                                                                                                                                                                       (STFT) to obtain range-velocity gait features from radar data,                     motion pattern is repeated 10 times, and 960 samples of radar
                                                                                                                                                                                       and propose to detect motion events of human gait features with                    data are collected.
                                                                                                                                                                                       a sliding window method.
                                                                                                                                                                                                                                                                             III. DATA PREPROCESSING AND FEATURE EXTRACTION
                                                                                                                                                                                           For the recognition of human behavior, machine learning is
                                                                                                                                                                                       used in the past. Liu et al. [6] use support vector machine (SVM)                  A. Signal Model and Preprocessing
                                                                                                                                                                                       and k-nearest neighbor (KNN) algorithm to classify human                               The signal of RX and the signal of TX are mixed to get the
                                                                                                                                                                                       behavior. Now, a large number of human behavior recognition                        Intermediate frequency (IF) signal. IF signal passes through
                                                                                                                                                                                       methods are implemented by deep learning. Wang et al. [7]                          Analog-to-Digital Converter (ADC) to obtain raw radar data.
                                                                                                                                                                                       propose a line kernel convolutional neural network (LKCNN),                        Average background subtraction is adopted to eliminate the
                                                                                                                                                                                       which directly processes baseband data to detect fall events. Hsu                  noise effects generated by other static objects in the experimental
                                                                                                                                                                                       et al. [8] use bidirectional long short-term memory (Bi-LSTM)                      environment [9]. Then, STFT is used to obtain the range-


                                                                                                                                                                                       979-8-3315-1476-1/25/$31.00 ©2025 IEEE                                       465

                                                                                                                                                                                              Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:38:17 UTC from IEEE Xplore. Restrictions apply.
velocity-channel data cube of each frame. Finally, the range-
velocity-time data cube is obtained by incoherent superposition
along the receive channel dimension.

                 TABLE 1. PARAMETERS FOR EXPERIMENTS
## Parameters                             Quantity
          Starting frequency                          77GHz
           Frequency slope                        39.058MHz/µs
              Bandwidth                            1999.77MHz
           Ramp end time                              51.2µs
               Idle time                              61.2µs
                 Frame                                 30ms
            ADC samples                                 256
          Number of frames                              200
       Number of chirps per frame                       200
          Number of TX/RX                               1/4
             Sample rate                            10000Ksps

                  TABLE 2. DESIGNED MOTION PATTERNS
## Motion Patterns                      Labels
   1               Fall while walking toward the radar             Fall                                  Figure 1. Experimental environment.
## 2             Fall while walking away from the radar            Fall
## 3            Fall toward the radar while sitting down           Fall              B. Feature Extraction
## 4           Fall backward the radar while sitting down          Fall
## 5    Fall toward the radar while bending to pick something      Fall                  Figure 2 shows the processing flow of feature extraction. The
## 6        Fall backward the radar while bending to pick          Fall              block diagram begins with data cube obtained from radar signal
                               something                                             preprocessing. Order-statistic constant false alarm rate (OS-
## 7                       Walk toward the radar                  Non fall            CFAR) filter is applied to identify human radar signal, then
## 8                     Walk away from the radar                 Non fall            motion events are detected by PBC. The signals of different parts
## 9             Sit down while walking toward the radar          Non fall
                                                                                     of human body are extracted, and the micro-Doppler frequency
## 10          Sit down while walking away from the radar         Non fall
## 11      Bend to pick something while walking toward the        Non fall
                                                                                     estimations of body parts are fitted at last. Details of the different
                                  radar                                              processing steps are described as follows.
## 12    Bend to pick something while walking away from the       Non fall
                                  radar




                                                       Figure 2 The processing flow of feature extraction.

    OS-CFAR detection: In order to obtain human radar signals                            PBC extraction: It can be seen from Figure 3(a) that the
in a noisy environment, OS-CFAR is applied to the range-                             subject remains stationary after falling. In order to reduce the
velocity spectrum corresponding to each frame of the range-                          amount of subsequent processing computation data, PBC is used
velocity-time data cube obtained above [10]. The reference                           to detect motion event from velocity-time spectrum [12]. The
window cells are centered on the test cell, with training cells                      PBC is obtained by calculating the sum of normalized power
forming a 31 × 31 rectangular window and guard cells                                 within each frame of the velocity-time spectrum, In order to
comprising an inner 15 × 15 rectangular window. For the range-                       obtain the threshold of PBC, a moving average filter with a
velocity spectrum corresponding to each motion pattern, the                          length of 0.3s is used to filter the PBC and obtain the filtered
farthest distance from the radar during the subjects' movement is                    PBC, and the threshold is obtained by the following equation [13]
cut in the distance dimension to eliminate multi-path echo
interference. In the velocity dimension, data are cut from -0.7m/s                                𝑇𝑇 = 𝑆𝑆𝑓𝑓𝑚𝑚𝑚𝑚𝑚𝑚 + 𝛼𝛼 × �𝑆𝑆𝑓𝑓𝑚𝑚𝑚𝑚𝑚𝑚 − 𝑆𝑆𝑓𝑓𝑚𝑚𝑚𝑚𝑚𝑚 �         (1)
to 2.5m/s for movement toward the radar, and from -2.5m/s to
0.7m/s for movement away from the radar to reduce the                                            ()
                                                                                     where S f n is the filtered PBC, S f min and S f max are the
computational load. After OS-CFAR processing, the range-
velocity-time data cube of human gait is obtained. In order to                                                                            ()
                                                                                     minimum and maximum values of S f n respectively, α is
reduce the influence of scattering intensity of velocity-time                        the empirical coefficient, it is set to 0.15 in algorithm
spectrum caused by different distances, the range-velocity                           implementation. The PBC, the filtered PBC and the threshold are
spectrum of each frame is normalized, and the maximum power                          shown in Figure 3(b).
of each frame is selected for dimensionality reduction to obtain
the velocity-time spectrum [11]. The velocity-time spectrum of                           Scatters extraction: In order to reduce the computational
falling while walking away from radar obtained by OS-CFAR is                         load of the subsequent deep learning model, the micro-Doppler
shown in Figure 3(a).                                                                frequency estimations of torso, arms and legs are extracted from

                                                                               466

         Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:38:17 UTC from IEEE Xplore. Restrictions apply.
the two-dimensional velocity-time spectrum. Figure 4(a) shows
the velocity-time spectrum of falling while walking away from
radar after motion event detection. Combined CLEAN and
clustering algorithms, the corresponding scatters of torso, arms
and legs are obtained [14]. The scatters of different parts of
human body are extracted by CLEAN algorithm. The embedded
DBSCAN makes further judgment on the different parts of the
scatters obtained from CLEAN according to the scatter density,
thus improving the accuracy of scatter extraction.
    The micro-Doppler frequency estimations: In order to further
separate the corresponding left and right arm and leg scatters
from the arm and leg scatters, it is necessary to find out the
periodicity of the movement adaptively. One of the
characteristics of human gait is the maximum speed of the
human torso when the feet touch the ground [15]. Using the
velocity-time spectrum obtained after OS-CFAR processing, the
maximum power at each frame is extracted to obtain the
maximum power velocity-time curve, and the peak interval of it
is the motion period. The corresponding left and right arm and
leg scatters can be separated according to the motion period.
Finally, KNN algorithm is used for regression fitting to obtain
the micro-Doppler frequency estimations corresponding to
different human body parts [16]. K value is set to 6 and
Euclidean distance is adopted. Five micro-Doppler frequency
estimations can be obtained for each sample. The scatters and
micro-Doppler frequency estimations obtained from the
velocity-time spectrum of falling while walking away from radar                    Figure 4. Falling during walking away from radar: (a) Motion event detection
through the above processing are shown in Figure 4(b).                              of Figure 3(a), (b) scatters and the micro-Doppler frequency estimations of
                                                                                                                      Figure 4(a).

                                                                                              IV. DEEP LEARNING MODEL AND RESULT
                                                                                   A. Fall Detection Model
                                                                                       Bi-LSTM is more efficient than ordinary recurrent neural
                                                                                   networks (RNN). After signal processing in Section Ⅲ, five
                                                                                   micro-Doppler frequency estimations of different human body
                                                                                   parts and 1 PBC can be obtained from each sample. These curves
                                                                                   are one-dimensional time series and can be used as the input of
                                                                                   Bi-LSTM. We propose a lightweight fall detection model based
                                                                                   on 1D convolutional neural network (1D-CNN) and Bi-LSTM.




                                                                                                Figure 5. The architecture of fall detection model

                                                                                       The architecture of fall detection model proposed is shown
                                                                                   in Figure 5, where input 1 are micro-Doppler frequency
                                                                                   estimations of body parts and input 2 are power burst curves.
                                                                                   The data feature of the micro-Doppler frequency estimations of
  Figure 3. Falling during walking away from radar: (a) the velocity-time          body parts is extracted by 1D-CNN layers, and the maximum
               spectrum, (b) the PBCs and the threshold line.                      pooling layers are used to reduce the dimension of the data
                                                                                   feature. The convolution kernel sizes of the three 1D-CNN
                                                                                   layers are all 1×3, the channel numbers are 32, 64 and 128. The


                                                                             467

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:38:17 UTC from IEEE Xplore. Restrictions apply.
kernel sizes of the three maximum pooling layers are all 1×2,                                                V. CONCLUSION
and the stride of both the convolution layer and the pooling layer                      A lightweight fall detection system based on FMCW radar is
are all 1. Finally, the Bi-LSTM layer is used for fall detection. In                proposed in the paper. Noise is removed by OS-CFAR filter, The
addition, PBC performs fall detection through the Bi-LSTM                           PBC threshold is used to detect motion events, and micro-
layer, and the number of neurons in both Bi-LSTM layers is 50,                      Doppler frequency estimations of human torso, arms and legs
the detection results of the two inputs are fused in time                           are extracted from the velocity-time spectrum of human gait.
dimension, and the final detection results are obtained through                     Finally, a lightweight fall detection model based on 1D-CNN
the full connection layer. Regularization terms with coefficient                    layers and Bi-LSTM layer is constructed, and the classification
0.5 are introduced into the network to prevent overfitting during                   results of micro-Doppler frequency estimations and PBC are
model training.                                                                     fused to realize fall detection. The accuracy of model is 93.75%,
B. Results and Analysis                                                             with precision, recall and F1 score exceeding 92%. In addition,
    The first 6 subjects' micro-Doppler frequency estimations of                    k-fold cross validation is used to investigate the generalization
                                                                                    of the model. The accuracy is 93.23%, with precision, recall and
body parts and PBCs are used to train, and the last 2 subjects'
                                                                                    F1 score all exceeding 90%.
micro-Doppler frequency estimations of body parts and PBCs
are used to test. In order to evaluate the model, accuracy,                                                        REFERENCES
precision, recall and F1 score are used as evaluation indicators
                                                                                    [1]  H. Ritchie and M. Roser. Age Structure. Our World in Data. [Online].
of the model, and the four evaluation indicators of the test result                      Available: https://ourworldindata.org/age-structure.
are shown in Table 3. As can be seen from Table 3, the accuracy                     [2] H. -B. Li, J. le Kernec, A. Mehul et al., "Distributed radar information
of model is 93.75%, with precision, recall and F1 score                                  fusion for gait recognition and fall detection," 2020 IEEE Radar
exceeding 92%. In addition, the model adopts one-dimensional                             Conference (RadarConf20), Florence, Italy, 2020, pp. 1-6.
features for training, which reduces the training time                              [3] X. Zhou, L. -C. Qian, P. -J. You et al., "Fall detection using convolutional
consumption compared with the two-dimensional micro-                                     neural network with multi-sensor fusion," 2018 IEEE International
Doppler signature model.                                                                 Conference on Multimedia & Expo Workshops (ICMEW), San Diego, CA,
                                                                                         USA, 2018, pp. 1-5.
    Considering the gait differences between different subjects,                    [4] Y. -R. Yao, W. -B. Liu, G. Zhang et al., "Radar-based human activity
k-fold cross validation is used to investigate the generalization                        recognition using hyperdimensional computing," in IEEE Transactions on
of the model [17]. Seven subjects for training and 1 subject for                         Microwave Theory and Techniques, vol. 70, no. 3, pp. 1605-1619, March
                                                                                         2022.
testing. The whole process is repeated for 8 times, and the
                                                                                    [5] Y. -C. Yao, C. -Y. Liu, H. Zhang et al., "Fall detection system using
average of evaluation indicators of the 8 test results is taken. The
                                                                                         millimeter-wave radar based on neural network and information fusion,"
corresponding results of k-fold cross validation are shown in                            in IEEE Internet of Things Journal, vol. 9, no. 21, pp. 21038-21050, 1
Table 4. The accuracy of k-fold cross validation is 93.23%, with                         Nov.1, 2022.
precision, recall and F1 score exceeding 90%. This shows the                        [6] L. Liu, M. Popescu, M. Skubic et al., "Automatic fall detection based on
method proposed has good generalization.                                                 doppler radar motion signature," 2011 5th International Conference on
                                                                                         Pervasive Computing Technologies for Healthcare (PervasiveHealth) and
      TABLE 3. FOUR EVALUATION INDICATORS OF THE TEST RESULT                             Workshops, Dublin, Ireland, 2011, pp. 222-225.
                                                                                    [7] B. Wang, L. Guo, H. Zhang et al., "A millimetre-wave radar-based fall
      Accuracy          Precision            Recall          F1 score                    detection method using line kernel convolutional neural network," in
      93.75%             95.18%             92.17%           93.65%                      IEEE Sensors Journal, vol. 20, no. 22, pp. 13364-13370, 15 Nov.15, 2020.
                                                                                    [8] W. -L. Hsu, J. -X. Liu, C. -C. Yang et al., "A fall detection system based
            TABLE 4. RESULTS OF K-FOLD CROSS VALIDATION                                  on FMCW radar range-doppler image and Bi-LSTM deep learning," in
                                                                                         IEEE Sensors Journal, vol. 23, no. 18, pp. 22031-22039, 15 Sept.15, 2023.
      Accuracy          Precision            Recall          F1 score
       93.23%            96.21%             90.21%           92.82%                 [9] M. Piccardi, "Background subtraction techniques: a review," 2004 IEEE
                                                                                         International Conference on Systems, Man and Cybernetics (IEEE Cat.
                                                                                         No.04CH37583), The Hague, Netherlands, 2004, pp. 3099-3104 vol.4.
              TABLE 5. COMPARISON WITH RELATED WORK
                                                                                    [10] H. Rohling, "Radar CFAR thresholding in clutter and multiple target
                 Number of            Number of                                          situations," in IEEE Transactions on Aerospace and Electronic Systems,
    Work           patterns              samples          Evaluation                     vol. AES-19, no. 4, pp. 608-621, July 1983.
              Fall     Non fall     Fall    Non fall                                [11] X. -Z. Zeng; Báruson, H.S.L.; Sundvall, A. "Walking step monitoring with
     [18]      4          3         408       117      Accuracy: 87%                     a millimeter-wave radar in real-life environment for disease and fall
                                                                                         prevention for the elderly," Sensors 2022, 22, 9901.
                                                       Accuracy: 96.6%
     [19]        3        3         600       400                                   [12] B. Erol, M. Amin, F. Ahmad et al., "Radar fall detectors: a comparison,"
                                                       Precision: 95.2%
                                                       Accuracy: 93.23%                  in Radar Sensor Technol. XX, vol. 9829, 2016.
                                                       Precision: 96.21%            [13] Z. -X. Zeng; Amin, M.G.; Shan, T. "Arm motion classification using time-
    Ours         6        6         480       480
                                                       Recall: 90.21%                    series analysis of the spectrogram frequency envelopes," Remote Sensing.
                                                       F1 score: 92.82%                  2020, 12, 454.
    Finally, Table 5 compares the method proposed in this paper                     [14] D. Steinhauser, P. HeId, A. Kamann et al., "Micro-Doppler extraction of
with related work, including number of patterns, number of                               pedestrian limbs for high resolution automotive radar," 2019 IEEE
samples and model evaluation indicators. It can be seen from                             Intelligent Vehicles Symposium (IV), Paris, France, 2019, pp. 764-769.
Table 5, under the premise of reducing the amount of                                [15] H. Abedi, J. Boger, P. P. Morita et al., "Hallway gait monitoring using
                                                                                         novel radar signal processing and unsupervised learning," in IEEE Sensors
computation, the accuracy of the proposed method is not                                  Journal, vol. 22, no. 15, pp. 15133-15145, 1 Aug.1, 2022.
significantly reduced, and the precision is slightly improved.



                                                                              468

        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:38:17 UTC from IEEE Xplore. Restrictions apply.
[16] Y. -P. Ding, Y. -X. Chen, J. -X. Cao et al., "Human micro-Doppler              [18] B. Jokanović and M. Amin, "Fall detection using deep learning in range-
     frequency estimation by clustering and KNN joint algorithm," in IEEE                doppler radars," in IEEE Transactions on Aerospace and Electronic
     Sensors Journal, vol. 24, no. 7, pp. 10824-10831, 1 April1, 2024.                   Systems, vol. 54, no. 1, pp. 180-189, Feb. 2018.
[17] T. -T. Wong and P. -Y. Yeh, "Reliable accuracy estimates from k-fold           [19] T. Imamura, V. G. Moshnyaga and K. Hashimoto, "Automatic fall
     cross validation," in IEEE Transactions on Knowledge and Data                       detection by using doppler-radar and LSTM-based recurrent neural
     Engineering, vol. 32, no. 8, pp. 1586-1594, 1 Aug. 2020.                            network," 2022 IEEE 4th Global Conference on Life Sciences and
                                                                                         Technologies (LifeTech), Osaka, Japan, 2022, pp. 36-37.




                                                                              469

        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:38:17 UTC from IEEE Xplore. Restrictions apply.

