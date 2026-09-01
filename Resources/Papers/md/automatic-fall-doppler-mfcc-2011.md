     2011 5th International Conference on Pervasive Computing Technologies for Healthcare (PervasiveHealth) and Workshops




              Automatic Fall Detection Based on Doppler
## Radar Motion Signature
   Liang Liu, Mihail Popescu, Marjorie Skubic,                                                 Tarik Yardibi, Paul Cuddihy
                 Marilyn Rantz                                                                       GE Global Research
              ECE Department of Missouri                                                          Schenectady, NY, USA
                 Columbia, MO, USA                                                           e-mail: {yardibi,cuddihy}@ge.com
            e-mail: llpfd@mail.missouri.edu,
          {popescum, skubicm}@missouri.edu,


Abstract—Falling is a common health problem for elderly. It is                   show promising results. The main challenge of a fall
reported that more than one third of adults 65 and older fall                    detection system is to have as few false alarms as possible
each year in the United States. To address the problem, we are                   while detecting all the falls. In order to achieve this goal, we
currently developing a Doppler radar-based fall detection                        believe that it is necessary to develop multiple fall detection
system. Doppler radar sensors provide an inexpensive way to                      modalities together with multiple classification methods for
recognize human activity. In this paper, we employed mel-                        each sensor and then combine them using a sensor fusion
frequency cepstral coefficients (MFCC) to represent the                          framework.
Doppler signatures of various human activities such as                               Various studies have shown that radar sensors can be
walking, bending down, falling, etc. Then we used two different
                                                                                 employed for gait characterization. A Ku-band radar is used
classifiers, SVM and kNN, to automatically detect falls based
on the extracted MFCC features. We obtained encouraging
                                                                                 to estimate the gait velocity from the frequencies with the
classification results on a pilot dataset that contained 109 falls               highest reflection levels. The stride rate can be estimated
and 341 non-fall human activities.                                               from the estimated gait velocities [9]. A continuous wave
                                                                                 radar was used in [10] to estimate the stride rate by taking
    Keywords-fall detection; eldercare; MFCC features; radar                     the Fourier transform at each Doppler frequency bin after
classification; SVM; kNN                                                         computing the spectrogram. Different human body parts can
                                                                                 generate different radar signatures [11]. Continuous wave
                         I.    INTRODUCTION                                      radar can distinguish different persons and other moving
    Falls are the leading causes of accidental death in the US                   objects [12]. A system using an acoustic Doppler radar and a
population over age 65 [1, 2]. In 2007, about three thirds of                    microphone [13] showed that the footstep sounds correlated
all people that died as a result of a fall were above age 65                     with the secondary peaks on the radar spectrogram. Another
[2]. The death rate caused by falls among elders is increasing                   acoustic Doppler radar was used in [14] for human gait
quickly over the past decade [3]. Multiple studies showed                        characterization studies with a training based classification
that delay of the medical intervention after a fall is                           method.
negatively correlated to its outcomes. If the nursing                                Many processing algorithms have been reported for radar
personnel is informed as soon as possible after a fall they can                  data. Kim and Ling [15] extracted six features from a
provide invaluable assistance that may significantly improve                     denoised radar spectrogram and used them to classify seven
the intervention outcomes [4]. One of the possible solutions                     different human activities, such as running, walking, walking
for reducing the intervention time is to automatically detect                    while holding a stick, crawling, boxing while moving
and then promptly report the fall to the related medical                         forward, boxing while standing in place, and sitting still. The
personnel.                                                                       wavelet ridges and higher-order statistics were used in [16]
     In recently years, many fall detection methods have been                    characterize radar signals. A fuzzy support vector machine
described in the literature. There are two main types of fall                    (SVM) was then applied to identify different emitter signals
monitoring devices: wearable and non-wearable. The                               [16]. A successive normalization-based feature extraction
simplest wearable device is a “Push-button”, which can be                        algorithm on the instantaneous frequencies was obtained by
manually activated in case of a fall. Accelerometer-based                        using instantaneous autocorrelation in [17]. An intra-pulse
wearable devices detect falls by measuring the applied                           feature extraction approach based on symbolic time series
acceleration along the vertical axis [5]. The wearable devices                   analysis (STSA) is proposed in [18]. The gait features are
are inexpensive but they have two main drawbacks: they                           extracted to identify subjects in a realistic outdoor clutter
can’t be activated when a loss of conscience occurs after a                      background [19]. It has been shown that human operators
fall and they may be not be worn at all times (for example,                      that listen to the Doppler audio output from the surveillance
during night time) [6]. Among the non-wearable devices, we                       radar are able to detect and identify certain targets [20]. It
mention floor vibration sensors [7] and microphone arrays                        was concluded that the Doppler signature of targets can be
[8]. All these methods are currently under development and                       manipulated by sound signal processing techniques.



                                                                                                                     978-1-936968-15-2 © 2011 ICST
                                                                           222                        DOI 10.4108/icst.pervasivehealth.2011.245993
     Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:28:29 UTC from IEEE Xplore. Restrictions apply.
Consequently, they [20] used mel-frequency cepstral
coefficients (MFCC) features to represent the Doppler
signatures and then they employed and Gaussian Mixture
Model (GMM) to achieve about 88% target recognition rate.
    In our paper, we propose a fall detection technique that
involves two pulse-Doppler range control radars (RCR)
developed by General Electric Co. RCR uses the Doppler
principle to estimate the relative velocities of the targets
within the detection range. RCR transmits the
electromagnetic wave signal at a certain frequency and
measures the various frequency shifts in the reflected wave.
Different body parts generate distinct Doppler signatures for
a certain moving person. Since a human fall comprises a
series of human body parts movements, it is reasonable to try
recognizing a fall based on its Doppler signature.
    This paper is organized as follows. In section II, we                         Figure 2. The Doppler-based sensors fall detector setup in lab.
describe the experimental setup and the available datasets. In
section III, we present the algorithms employed in this work.                         The dataset used in this paper consists in 450 human
In section IV, we present and analyze the experimental                            activity radar signatures (see Table I): 109 falls and 341
results. The conclusion is given in section V.                                    possible false alarms (non falls). The falls were performed by
                                                                                  two students and by a professional stunt actor. The stunt
     II.       EXPERIMENT SETUP AND DATASET DESCRIPTION
                                                                                  actor was trained by our nursing collaborators to fall like
The experimental setup is shown in the diagram from Fig. 1                        older adults. We replicated various types of falls such as
and in the image shown in Fig. 2. RCR sensor A is placed at                       forward fall, backward fall, left-side fall, right-side fall, etc.
the end of a 24 foot long and 3 foot wide carpet. RCR sensor                      Relative to the sensor positions, we included different types
B is placed on the right side of the carpet (when the subject                     of falls such as between the two sensors and towards or away
is facing RCR A) orthogonally to RCR A. During this                               from one of the sensors. Out of 109 falls, 98 fall signatures
experiment, test subjects are asked to perform different                          were recorded when both sensors were on floor and other 11
actions at the center of the carpet or walk toward RCR A.                         were recorded when RCR B was mounted on the ceiling and
           Subject                                                                RCR A was placed on floor. The 341 “non fall” signatures
                                  Carpet
                                                                                  were acquired from various activities performed by 8 human
                                                                                  subjects (our entire team). Among the recorded human
y                                                                                 activities we mention bending over to pick up objects from
                                           12’                                    the floor, kneeling, tying shoes, sitting on a chair, arm/leg
           x                                                    RCR A             swing, walking, etc.
                                 6’
z                                                                                     The radar signals were recorded using a National
                                                                                  Instruments data acquisition card NI 9201 with 8-channel
                                                                                  analog inputs. The signal processing and classification of the
                                 RCR B                                            recorded radar signal were performed using Matlab
                                                                                  (http://www.mathworks.com).
Figure 1.The diagram of the Doppler-based sensors fall detector setup.
                                                                                                  III.    ALGORITHMS AND METHODS
    In Fig. 2, the positions of the two sensors, RCR A and
RCR B, are marked with red circles. Since a Doppler radar is                          The procedure employed to classify an activity as a “fall”
sensitive mainly to movement along its central axis, more                         or “not fall” based on its radar signature has the following
than one sensor might be necessary to ensure that falls in any                    steps:
direction can be detected. However, a sensor placed on the                            1. Compute the spectrogram (STFT(f, t) , see Fig. 3.b)
ceiling might be sufficient for a small room due to the fact                              of the entire radar signature (raw signal, see Fig.
that most falls have an important vertical motion component.                              3.a). The sampling frequency of the radar signal is
There are advantages of this setup: the beam is not                                       1000Hz.
obstructed by objects in the room and there is not                                    2. Compute the energy burst curve (see Fig. 3.c).
interference from the nearby hallway (since there is some                                 Through experimentation, we determined that the
amount of wall penetration of the radar beam). We mention                                 frequencies of interest for fall detection are in the
that our initial setup (two radars placed on the floor) was                               [25-50] Hz range. Consequently the energy burst EB
motivated by our initial gait measurement experiments. We                                 is computed as:                           .
are currently collecting more data in order to investigate the                        3. Find the location of the maximum, tmax, of the energy
fall detection performance of a single RCR sensor placed on                               burst curve, EB(t). We assumed that a fall is a
the ceiling.                                                                              catastrophic event that involves many body parts
                                                                                          (hence many frequencies) that move with speeds




                                                                            223
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:28:29 UTC from IEEE Xplore. Restrictions apply.
     superior (hence produce high intensity Doppler                                                                                                                 computed as (# of falls detected)/109 and the false
     signal) to most indoor activities. For example, in Fig.                                                                                                        alarm rate as (#false alarms/341).
     3.a we can compare the signatures of two events: at
     t~2 s the actor bent and clapped and at t~8 s she fell.                                                                                                                                                                                                                          IV.                              RESULTS
     In Fig. 3.b, we clearly see that the fall spans a                                                                          A. Sample outputs for the two RCR sensors
     frequency range about 4 times larger than the bend-
     and-clap event, with higher energy levels at each                                                                              In Fig. 4, we show the raw Doppler signal, the
     frequency.                                                                                                                 spectrogram and the energy burst for a typical fall compared
4.   Compute the MFCC features in a 4-second window                                                                             to the same measurements for a non-fall.
     centered at the maximum energy location, tmax. We                                                                                                              Raw signal of RCR A                                                                                                                        Spectrogram of RCR A                                                                                      Energy Burst of RCR A


     only use six MFCC coefficients in this paper (index
                                                                                                                                                4                                                                                                                                500

                                                                                                                                                                                                                                                                                 450                                                                                                          2500
                                                                                                                                              3.5

                                                                                                                                                                                                                                                                                 400


     2 to 7). To make the system less dependent on the                                                                                          3
                                                                                                                                                                                                                                                                                                                                                                                              2000




                                                                                                                                                                                                                                                                                                                                                                         accumulated energy
                                                                                                                                                                                                                                                                                 350




                                                                                                                                                                                                                                                                 frequency(Hz)
                                                                                                                                              2.5
                                                                                                                                                                                                                                                                                 300



     distance to the sound source, we did not use the first                                                                      voltage(V)
                                                                                                                                                                                                                                                                                                                                                                                              1500
                                                                                                                                                2                                                                                                                                250

                                                                                                                                                                                                                                                                                 200
                                                                                                                                              1.5


     cepstral coefficient. The features were extracted
                                                                                                                                                                                                                                                                                                                                                                                              1000
                                                                                                                                                                                                                                                                                 150
                                                                                                                                                1
                                                                                                                                                                                                                                                                                 100                                                                                                           500



     using the Matlab function, mfcc [21]. The extracted
                                                                                                                                              0.5
                                                                                                                                                                                                                                                                                     50

                                                                                                                                                0                                                                                                                                    0                                                                                                           0
                                                                                                                                                    0   1   2   3      4    5           6       7       8                    9           10                                                   1       2    3       4    5       6     7       8       9                                              0       1   2   3      4      5    6      7   8   9   10



     features for a 4-second window are represented by a
                                                                                                                                                                       time(second)                                                                                                                                time(second)                                                                                                 time(second)
                                                                                                                                                                Raw signal of RCR A                                                                                                                        Spectrogram of RCR A                                                                                      Energy Burst of RCR A
                                                                                                                                              3.2                                                                                                                     500




     6×174 matrix. We then arrange the feature matrix                                                                                         3.1                                                                                                                     450                                                                                                                     2500

                                                                                                                                               3                                                                                                                      400
                                                                                                                                                                                                                                                                                                                                                                                              2000



     into a vector with 6*174 = 1044 elements that we
                                                                                                                                                                                                                                                                                                                                                                    accumulated energy
                                                                                                                                              2.9                                                                                                                     350




                                                                                                                                                                                                                                                 frequency(Hz)
                                                                                                                                              2.8                                                                                                                     300



                                                                                                                                 voltage(V)
                                                                                                                                                                                                                                                                                                                                                                                              1500
                                                                                                                                              2.7                                                                                                                     250



     further use in the classification algorithm.                                                                                             2.6

                                                                                                                                              2.5
                                                                                                                                                                                                                                                                      200

                                                                                                                                                                                                                                                                      150
                                                                                                                                                                                                                                                                                                                                                                                              1000




5.   We independently classify the feature vectors                                                                                            2.4

                                                                                                                                              2.3
                                                                                                                                                                                                                                                                      100

                                                                                                                                                                                                                                                                           50
                                                                                                                                                                                                                                                                                                                                                                                              500




     extracted from the signatures produced by the two
                                                                                                                                              2.2                                                                                                                                0                                                                                                              0
                                                                                                                                                    0   1   2   3     4     5       6       7       8                    9                                                                1       2        3       4    5       6         7       8       9                                          0       1   2   3      4      5    6      7   8   9   10
                                                                                                                                                                     time(second)                                                                                                                                time(second)                                                                                               time(second)




     radars, A and B. For each feature vector we used                                                                           Figure 4. Doppler signal, spectrogram and energy burst captured by RCR
                                                                                                                                sensor A, for a typical fall (upper row) and for a false alarm (lower row)
     three classifiers: support vector machines (SVM)
     and k-nearest neighbor (kNN). Each classifier                                                                                  The false alarm (lower row in Fig. 4) was acquired when
     outputs a confidence, conf[0,1], that the current                                                                         a student picked up a book from the floor. The first energy
     activity signature represents a fall.                                                                                      burst corresponds to bending down, while the second one
                                                     Raw signal of RCR A
                                                                                                                                represents coming back up. By comparing the pictures in the
                                                                                                                                two rows of Fig. 4, we see that the energy burst of the fall is
                            4


                           3.5


                            3


                           2.5
                                                                                                                                higher than that of false alarms. This is typically the case for
       voltage(V)
                            2                                                                                                   older adults that do not perform very vigorous activities.
                           1.5


                            1
                                                                                                                                Also, the spectral composition of a fall (upper spectrogram)
                           0.5                                                                                                  seems to be different from the one of bending (lower
                            0
                                 0       1   2   3      4       5
                                                        time(second)
                                                                            6           7           8       9        10
                                                                                                                                spectrogram), with higher frequencies up to about 200 Hz for
      a.) Raw Doppler radar signal (a fall occurred at t=8)                                                                     the fall case. This might be explained by the many body parts
                                                     Spectrogram of RCR A
                                                                                                                                involved in a fall, which is rarely the case for regular indoor
                                                                                                                                activities. These observations argue favorably for the
                           500

                           450

                           400

                           350
                                                                                                                                possibility of using a classifier to detect the falls.
           frequency(Hz)
                           300

                           250

                           200

                           150
                                                                                                                                B. Performance of the SVM and kNN Classifiers
                           100

                            50

                             0
                                                                                                                                 In Fig. 5 and 6 we show the ROCs obtained for the two
                                                                                                                                classifiers (Fig. 5 – for RCA A, and Fig. 6 for RCA B) used
                                         1   2   3          4       5           6           7           8       9
                                                            time(second)


      b.) Spectrogram of the raw signal (spectrogram)
                                                     Energy Burst of RCR A                                                      in this paper, SVM and kNN.
                           2500



                           2000




      accumulated energy
                                                                                                                                                                                                                                                                                     ROC curve for all RCR data (RCR A)
                           1500
                                                                                                                                                                                                                                 1
                           1000
                                                                                                                                                                                                                         0.9
                           500

                                                                                                                                                                                                                         0.8
                                 0
                                     0   1   2   3      4       5       6           7           8       9       10
                                                            time(second)                                                                                                                                                 0.7                  AUC SVM = 0.93096

      c.) The energy burst curve of the spectrogram. Peak value is

                                                                                                                                                                                                    true positive rate
                                                                                                                                                                                                                         0.6

      marked by a red cross.                                                                                                                                                                                             0.5

                                                                                                                                                                                                                         0.4
                                                                                                                                                                                                                                         AUC kNN = 0.95788
      Figure 3. First three signal processing steps of a radar signature:                                                                                                                                                0.3

      a) raw signal, b) spectrogram and c) energy burst                                                                                                                                                                  0.2

                                                                                                                                                                                                                         0.1


6.   Use a set of N thresholds, {i}i=1,N to compute the                                                                                                                                                                         0
                                                                                                                                                                                                                                     0                                           0.2                        0.4         0.6
                                                                                                                                                                                                                                                                                                          false positive rate
                                                                                                                                                                                                                                                                                                                                                              0.8                                        1

     receiver operator characteristic (ROC) curve. By                                                                           Figure 5. Performance results for kNN and SVM classifiers on RCR A data
     thresholding the confidence of each classifier with
     each threshold in the set we obtained N {detection
     rate, false alarm rate} pairs that are used to plot the
     ROC. The detection rate for each threshold was




                                                                                                                          224
 Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:28:29 UTC from IEEE Xplore. Restrictions apply.
                                         1
                                                        ROC curve for all RCR data (RCR B)              [4]  C. G. Moran, R.T. Wenn, M. Sikand, A.M. Taylor, Early mortality
                                        0.9
                                                                                                             after hip fracture: is delay before surgery important", J. of Bone and
                                        0.8
                                                                                                             Joint Surgery, pp. 483-9, 2005.
                                        0.7
                                                  AUC SVM = 0.91813
                                                                                                        [5] Giansanti D, Maccioni G and Macellari V, “The development and test
                                                                                                             of a device for the reconstruction of 3D position and orientation by

                   true positive rate
                                        0.6

                                        0.5                                                                  means of a kinematic sensor assembly with rate gyroscopes and
                                        0.4                                                                  accelerometers,” IEEE Trans. Biomed. Eng. 52 1271–7, 2005
                                        0.3                                                             [6] N. Noury, A. Fleury, P. Rumeau, et al., "Fall detection-principles and
                                        0.2                                                                  methods", Proc. of the 29th IEEE EMBS, Lyon, France, Aug. 23-26,
                                              AUC kNN = 0.97401
                                        0.1
                                                                                                        [7] M. Alwan, P. J. Rajendran, S. Kell, D. Mack, S. Dalal, M. Wolfe,
                                         0
                                              0        0.2          0.4         0.6
                                                                  false positive rate
                                                                                        0.8   1              R.Felder, " A smart and passive floor-vibration based fall detector for
                                                                                                             elderly", 2nd IEEE Int. Conf. on Inf. & Comm. Tech.: from Theory to
Figure 6. Performance results for kNN and SVM classifiers on RCA B
                                                                                                             Applications - ICTTA’06, April 24 - 28, 2006, Damascus, Syria.
data.
                                                                                                        [8] Y. Li, Z. Zeng, M. Popescu, D. Ho, "Acoustic Fall Detection Using a
                                                                                                             Circular Microphone Array", Proc. of 32nd Annual International
    From the above results we see that kNN (k=3) produced                                                    Conference of the IEEE EMBS, Buenos Aires, Argentina, Aug. 31 -
the best results for both sensors, with an area under the curve                                              Sept. 4, 2010, pp. 2242-2245.
(AUC) of about 0.96. SMV performance was close, with an                                                 [9] D. Tahmoush, J. Silvious, “Radar stride rate extraction,” 13th
AUC of about 0.92.                                                                                           International Machine Vision and Image Processing Conference, pp.
    By analyzing the false alarms of both classification                                                     128-133, 2009
algorithms we found some examples of squatting and                                                      [10] M. Otero, “Application of a continous wave radar for human gait
kneeling. A possible reason for this situation is that while the                                             recognition,” The MITRE Corporation, 2005.
actor and the students were instructed how to walk and fall                                             [11] J. L. Geisheimer, W. S. Marshall, E. Greneker, “A continuous-wave
                                                                                                             (CW) radar for gait analysis,” Signals, Systems and Computers, vol.
as an older adult, they were not told to bend and kneel in the                                               1, pp. 834-838, 2001.
same fashion. As a result, the speed of these actions was                                               [12] C. Hornsteiner, J. Detlefsen, “Characterisation of human gait using a
possibly close to that of a fall. We intend to address this                                                  continuous-wave radar at 25 GHz,” Adv. Radio Sci., vol. 6, pp. 67-
problem by collecting data in a real living environment, the                                                 70, 2008.
Tiger Place aging in place facility from Columbia, Missouri,                                            [13] Z. Zhang, P. O. Pouliquen, A. Waxman, A. G. Andreou, “Acoustic
where the stunt actor will perform only the falls but not the                                                micro-Doppler radar for human gait imaging,” J Acoust Soc Am., vol.
false alarms.                                                                                                121, no. 3, pp. 110-113, 2007.
                                                                                                        [14] K. Kalgaonkar, R. Bhiksha, “Acoustic Doppler Sonar for gait
                                                     V.           CONCLUSION                                 recognition,”, Mitsubishi Electric Research Laboratories, Inc., 2007.
                                                                                                        [15] Youngwook Kim; Hao Ling; , "Human Activity Classification Based
    In this paper we present an automatic fall detection                                                     on Micro-Doppler Signatures Using a Support Vector Machine,"
system based on two Doppler radar sensors. The radar sensor                                                  Geoscience and Remote Sensing, IEEE Transactions on , vol.47,
measures the relative speed of motion on a direction parallel                                                no.5, pp.1328-1337, May 2009
to its emission axis. Since a human fall comprises a series of                                          [16] Mingqiu, Ren; Jinyan, Cai; Yuanqing, Zhu; Jun, Han; , "Radar signal
                                                                                                             feature extraction based on wavelet ridge and high order spectra
human body parts in motion, it is reasonable to try                                                          analysis," Radar Conference, 2009 IET International , vol., no., pp.1-
recognizing a fall based on its Doppler signature.                                                           5, 20-22 April 2009
    We used MFCC features to represent the activity                                                     [17] Yunwei Pu; Weidong Jin; Ming Zhu; Laizhao Hu; , "Classification of
signature. Then we used two well known classifiers, SVM                                                      Radar Emitter Signals Using Cascade Feature Extractions and
and kNN, to classify the activities from a pilot dataset of                                                  Hierarchical Decision Technique," Signal Processing, 2006 8th
about 450 samples in two classes: falls and non-falls. We                                                    International Conference on , vol.4, no., 16-20 Nov. 2006
consider the classification results obtained (AUC between                                               [18] Tao-Wei Chen; Wei-Dong Jin; , "Feature extraction of radar emitter
                                                                                                             signals based on symbolic time series analysis," Wavelet Analysis and
0.91 and 0.97) as encouraging.                                                                               Pattern Recognition, 2007. ICWAPR '07. International Conference on
    In future work we plan to investigate the placement of a                                                 , vol.3, no., pp.1277-1282, 2-4 Nov. 2007
single sensor on the ceiling, employ classifier fusion to                                               [19] Tahmoush, D.; Silvious, J.; , "Stride rate in radar micro-doppler
reduce the false alarm rate and collect datasets in a real                                                   images," Systems, Man and Cybernetics, 2009. SMC 2009. IEEE
living environment (Tiger Place).                                                                            International Conference on , vol., no., pp.4218-4223, 11-14 Oct.
                                                                                                             2009
                                                   AKNOLEDGEMENTS                                       [20] Hughes, E. J.; Lewis, M.; , "The Application of Speech Recognition
                                                                                                             Techniques to Radar Target Doppler Recognition: A Case Study,"
      This work has been supported in part by an AHRQ grant.                                                 High Resolution Imaging and Target Classification, 2006. The
                                                                                                             Institution of Engineering and Technology Seminar on , vol., no.,
                                                             REFERENCES                                      pp.145-152, 21-21 Nov. 2006
[1]   Murhy SL, “Deaths: Final Data for 1998,” National Vital Statistics                                [21] M. Slaney, "Auditory toolbox 2.0", http://www.slaney.org/malcolm.
      Reports, vol. 48, no. 11. Hyattsville, Maryland: National Center for
      Health Statistics, 2000.
[2]   Centers for Disease Control and Prevention, National Center for
      Injury Prevention and Control. Web–based Injury Statistics Query
      and Reporting System (WISQARS) [online]. Accessed November
      30, 2010
[3]   Stevens JA. Fatalities and injuries from falls among older adults –
      United States, 1993–2003 and 2001–2005. MMWR 2006a;55(45).




                                                                                                  225
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:28:29 UTC from IEEE Xplore. Restrictions apply.

