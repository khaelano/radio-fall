34th Annual International Conference of the IEEE EMBS
San Diego, California USA, 28 August - 1 September, 2012


             Doppler Radar Sensor Positioning in a Fall Detection System
                                Liang Liu, Mihail Popescu, K. C. Ho, Marjorie Skubic, Marilyn Rantz





   Abstract— Falling is a common health problem for more                        Doppler radar can detect moving objects and, consequently,
than a third of the United States population over 65. We are                    can detect falls by producing specific signatures for various
currently developing a Doppler radar based fall detection                       part of a falling human body. Radar sensor has been widely
system that already has showed promising results. In this                       employed for target tracking, target recognition and
paper, we study the sensor positioning in the environment with
respect to the subject. We investigate three sensor positions,                  surveillance of human activity. In a room environment, it has
floor, wall and ceiling of the room, in two experimental                        been successfully used for measuring gait parameters such
configurations. Within each system configuration, subjects                      as velocity and stride length [15-16].
performed falls towards or across the radar sensors. We                            Our previous work shows the possibility of using Doppler
collected 90 falls and 341 non falls for the first configuration                radars to estimate fall risk in a daily living environment
and 126 falls and 817 non falls for the second one. Radar
                                                                                based on gait velocity and stride length [17]. We also
signature classification was performed using a SVM classifier.
Fall detection performance was evaluated using the area under                   proposed an automatic fall detection system based on
the ROC curves (AUCs) for each sensor deployment. We found                      Doppler radar signatures and some preliminary results were
that a fall is more likely to be detected if the subject is falling             shown in [18]. Considering that different classifiers
toward or away from the sensor and a ceiling Doppler radar is                   preferentially detect certain falls, in [19] we developed a
more reliable for fall detection than a wall mounted one.                       fusion framework for fall detection. From our previous work
                                                                                [18, 19], two questions surfaced. First, is the fall direction
                           I.   INTRODUCTION                                    influencing the detection performance? What is the best
                                                                                sensor position for fall detection? In this paper we are trying
   In the USA, falling is an important cause of death for
                                                                                to answer the above questions by performing two
elders above the age of 65. Over the past decade, the rate of
                                                                                experiments. In one experiment we compare the fall
fall triggered falls in seniors is rapidly increasing [1-3]. A
                                                                                detection performance for two floor installed radar and
fast response and medical intervention after the occurrence
                                                                                various fall directions. In the second experiment, we
of a fall is positively correlated to the outcomes. The prompt
                                                                                compare a wall mounted radar with a ceiling installed one.
assistance after a fall of the informed nursing personnel
                                                                                   This paper is organized as follows. In section II, we
improves the chances for survival after fall [4].
                                                                                describe the experimental setup. In section III, we present
   Aside of the traditional wearable sensors for fall detection,
                                                                                the study methodology and algorithm. In section IV, we
such as push buttons and accelerometers, non-wearable
                                                                                present and analyze the experimental results. We provide
sensors such as floor vibration sensors, video cameras,
                                                                                conclusions in section V.
infrared cameras, smart carpets and microphone arrays [5-
13] are also developed. In a non-wearable sensors based                                               II. EXPERIMENTAL SETUP
environment, seniors do not have to push buttons, pull cords                       The radar fall detection system uses the GE of range
or wear any devices even when they lost consciousness after                     control radar (RCR), which has a center frequency of
a fall. The fall will be detected automatically regardless of                   5.8GHz. The radar was set to have a coverage range up to
the elder state of mind and an alert will be sent to the nursing
                                                                                6.1 meters. The room size is 9m  8m  3.5m.
personnel for timely help. The fall detection peace of mind
                                                                                   Two configurations will be examined in this study to
allow elderly to live longer independently and reduce the
                                                                                provide some insights about the radar positions on all
healthcare costs [14]. At the University of Missouri,
                                                                                detection performance. Each configuration has two radars.
Columbia, we are currently developing another non-
                                                                                Configuration I (Fig. 1.a) has two RCRs placed on the floor
wearable fall detection system based on Doppler radar. A
                                                                                while configuration II (Fig. 1.b) has a sensor on the wall and
                                                                                the other one on the ceiling. The first configuration is similar
   This project was supported by grant R01HS018477 from the Agency for
Healthcare Research and Quality (AHRQ). The content is solely the               to the one used in [18, 19]. In Fig.1 (a, right), the two floor
responsibility of the authors and does not necessarily represent the official   sensors are oriented toward the center of the room. The
views of the AHRQ.                                                              distance from RCR1 to the room center is about 3.7 m,
   Liang Liu, K. C. Ho and Marjorie Skubic are with is with the Electrical
and Computer Engineering Department, University of Missouri, Columbia,          denoted by L1. The distance from RCR2 to room center is
MO 65211 USA (e-mail: llpfd@mail.missouri.edu, Hod@missouri.edu,                1.85, denoted by L2. In the image Fig.1 (a, left), the subject
SkubicM@missouri.edu).                                                          is performing a forward fall towards RCR1 and crossways
   Mihail Popescu is with the Health Management and informatics
Department, University of Missouri, Columbia, MO 65211 USA (e-mail:             RCR2. We note that RCR2 is closer to the fall than RCR1.
PopescuM@missouri.edu).                                                         In the second experimental configuration, one RCR is placed
   Marilyn Rantz is with the Sinclair School of Nursing, University of          in the center of the ceiling and the other one is attached to
Missouri,        Columbia,       MO        65211         USA        (e-mail:
RantzM@health.missouri.edu).                                                    the north wall at a height of 1.27 meters as shown in Fig. 1
978-1-4577-1787-1/12/$26.00 ©2012 IEEE                                      256
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:29:53 UTC from IEEE Xplore. Restrictions apply.
(b). The ceiling RCR is vertically pointing down to the                                                                                                                  TABLE I.                   DATASET AND SUBJECT INFORMATION
center of the room. The wall RCR is pointing horizontally                                                                                       System                    subject          Height          Weight        Fall       Fall direction
towards the center of the room. In Fig. 1 (b, right) falls were                                                                                 #                         #                (cm)            (kg)           #
                                                                                                                                                System                    1                188             88            20         Forward to RCR1
performed in a radial pattern, where radius R1 is 1 m, R2 is                                                                                                                                                             20         Forward to RCR2
                                                                                                                                                I
2 m and R3 is 3 m. In the image of in Fig. 1 (b, left), the                                                                                                                                                              5          Forward to RCR1&2
subject is standing in the room center and facing the north                                                                                                               2                162             53            20         Forward to RCR1&2
wall.                                                                                                                                                                                                                    20         Away from RCR1
## 5          Forward to RCR2
   In configuration I, we collected 90 falls from 2 subjects                                                                                    System                    3                183             83            21         Forward
who were falling in the center of the room to perform (see                                                                                      II                                                                       21         Left side
Fig. 2) 20 forward falls towards RCR1, 25 falls towards                                                                                                                                                                  21         Right side
                                                                                                                                                                          4                171             61            21         Forward
RCR2, 25 falls between RCR1 and RCR2, and 20 falls away                                                                                                                                                                  21         Left side
from RCR1. In configuration II, we collected 126 falls from                                                                                                                                                              21         Right side
2 subjects at 21 positions shown in Fig.1 (b, right). At each
position, each of the subjects performs 3 types of falls (see                                                                                                                 III. METHODOLOGY AND ALGORITHM
Fig. 3): forward fall, left side fall, right side fall.
   In configuration I, 341 non fall activities are selected from                                                                                   The sampling frequency of the radar signal is 960Hz. We
walking, body sway, cylinder sway, squat, pick up a book                                                                                        divided the whole fall detection procedure into three parts:
from the floor, etc. In configuration II, 817 non fall activities                                                                               data preprocessing; feature extraction; classification and
such as walking and bending down are selected from the                                                                                          result evaluation.
recorded radar signal at locations that show high energy                                                                                          A. Data preprocessing
density in the related spectrogram. Details about both
                                                                                                                                                  The fall signal segment, shown by the red block in Fig. 4,
datasets can be seen in TABLE I.
                                                                                                                                                can be located using the timestamp provided by a
                                                                                                                            N
                                                                                                                                                synchronized web camera. If the fall timestamp is
                                                                                                                   W                E           unavailable, we take the short time Fourier transform
                                                                                                                            S
                                                                                                                                                (STFT) to the given fall signal segment r ( n ) as shown in
                                                                                  1
                                                                                                                                                                                               ,
                                                                                                                                        8m

                                                                                                    L1
                                                                                                                                                Fig. 4, to obtain:
                                                                                                                                                                                                      

                                                                                                                                                                  ST F T ( m , f )   r ( n ) w ( n  m ) e
                                                                             L2

                                                           RCR 2                                                           RCR 1
                                                                                                                                                                                                                                  jw n
                                                                                                                                                                                                                                          .               (1)
                                                                                                                                                                                                 n  
                                                        Fall position
                                                                                                                                                                                                           Ceiling RCR
                                                                                                                                                                  0.3
                                                                         9m


(a) two floor radars system. (left) real view; (right) position diagram.                                                                                          0.2

                                                                                                                                                                  0.1

                                                                                                                             N                                      0
                                                    18                                                       19



                                                                                                                                                    Voltage (V)
                                                                                  10               R3                  W            E

                                                            17                                                                  S                                 -0.1
                                                                                                        11
                                                                                  2
                                                                         9
                                                                                               3                                                                  -0.2
                                                   16            8            1                                                          8m
                                                                                               4             12
                                                                                      R1            R2                                                            -0.3
                                                                     7
                                                                                           5
                                                                              6
                                                         15                                                                                                       -0.4
                                                                                                   13
                                              21                             14
                                                                                                                  20
                                                                                                                                                                  -0.5
                                                                                                                                                                      0             5                 10        15          20                25     30
                                                    Fall position                                                                                                                                           Second (s)


                                                                         9m
                                                                                                                                                Fig. 4. A fall signal.
(b) wall and ceiling radars system. (left) real view; (right) position diagram.
Fig. 1. sensor deployment setups in motion lab.                                                                                                 The spectrogram is formed by taking the magnitude square
                                                                                                                                                of the STFT,
                                                                                                                                                                                              2
                                                                                                                                                      spectrogram{r ( n )} | STFT ( m , w ) | .     (2)
                                                                                                                                                which is shown in Fig. 5. We, next, generate the energy
                                                                                                                                                burst curve, Fig. 6.up, as
                                                                                                                                                                                      50 /( 2  )
Fig. 2. Four types of fall for configuration I. (a) forward fall toward RCR1;
(b)forward fall toward RCR2; (c) forward fall between RCR1 & RCR2.                                                                                                EB ( m )                          STFT ( m , w ) ,                                    (3)
                                                                                                                                                                                    w  25 /( 2  )

                                                                                                                                                and apply smoothing over K bursts to reduce noise:
                                                                                                                                                                    ^               K 1

                                                                                                                                                                  EB (m )   EB (m  i) .                                                                (4)
                                                                                                                                                                                    i0
Fig. 3. Three types of fall for configuration II. (a) forward fall; (b)left side                                                                The peaks in this curve are marked in Fig. 6(up) by a red
fall; (c)right side fall.
                                                                                                                                                marker.


                                                                                                                                              257
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:29:53 UTC from IEEE Xplore. Restrictions apply.
   An example of using the energy burst curve to find energy                                             at various values. Since the classifier and the extracted
peaks as non fall activities is shown on the top of Fig. 6. The                                          features are fixed in this paper, we can compare the
located non fall activities, four 2 s windows marked by                                                  performance the ROC curve to find the best sensor position.
rectangles in the raw signal, are shown in Fig. 6. The
                                                                                                                                        IV. EXPERIMENTAL RESULTS
corresponding non-falls spectrograms can be seen in Fig. 5.
                                                                                                           A. Experiment1: influence of fall direction on RCR
                         200
                                                         Spectrogram                                       performance
                         180
                                                                                                 -30
                                                                                                            We employed configuration I to explore the influence of
                         160                                                                             fall direction on detector performance. In Fig. 7 and 8 we
                         140
                                                                                                 -40
                                                                                                         show the fall detection performance for different fall
                                                                                                         directions: towards, away, oblique and perpendicular the two

   Frequency (Hz)
                         120                                                                     -50

                         100                                                                             sensors RCR1 and RCR2, respectively. From Fig. 7, we see
                                                                                                 -60
                                  80                                                                     that RCR1 has the best performance (AUC=0.996) when the
                                  60                                                             -70     fall is away from the sensor and the worst one (AUC=0.889)
                                  40
                                                                                                 -80
                                                                                                         when the fall is perpendicular to it. In Fig. 8, the best
                                  20                                                                     detection of RCR2 was when the fall was towards the sensor
                                   0
                                    0       5       10          15         20   25
                                                                                                 -90
                                                                                                         (AUC=0.998) and the worst when the fall was perpendicular
                                                           Time (s)
                                                                                                         to the sensor (AUC=0.966). We note that RCR2 detection
Fig. 5. The spectrogram of a fall signal (marked by rectangle).                                          was, in general, better than RCR1’s since the fall mat was
                                                          Energyburst curve                              closer to RCR2. From this experiment we can conclude that
                                  300
                                                                                                         the fall direction has an important impact on detection


                    EnergyBurst
                                  200                                                                    performance, introducing about 10% variability in detection
                                  100
                                                                                                         results. Best detection is obtained when the fall is along the
                                                                                                         sensor axis. Consequently, placing the radar on the floor
                                       0
                                        0      5            10          15            20    25           might not be the best solution for fall detection. Instead,
                                            Largest nonfall energy window for Ceiling RCR
                                  0.5                                                                    positioning the sensor higher up on the wall or on the ceiling
                                                                                                         of the room might improve the detection performance.

                    Voltage (V)
                                       0
                                                                                                                                   1


                                  -0.5                                                                                            0.8
                                      0         5          10              15        20     25
                                                                Time (s)




                                                                                                             true positive rate
Fig. 6. Raw signal (down) and energy peaks (up) of non-fall activities.
                                                                                                                                  0.6
   If the timestamp from a synchronized web camera is
available, the fall signal segment can be located directly and                                                                    0.4
is indicated by the red rectangle in Fig. 4.                                                                                                  Fall towards RCR1 (AUC = 0.959)
                                                                                                                                              Fall perpedicular to RCR1 (AUC = 0.889)

  B. Feature extraction                                                                                                           0.2         Fall oblique to RCR1 (AUC = 0.934)
                                                                                                                                              Fall away from RCR1 (AUC = 0.996)
   For a selected 2-second window containing possible fall
activities, we first segment the 2-second window into 166                                                                          0
                                                                                                                                    0   0.2
                                                                                                                                        0.4        0.6                             0.8   1
sub-frames with an overlap rate of 0.5. Seven coefficients                                                                           false positive rate
are extracted for each sub-frame. By discarding the                                                      Fig. 7. Detection results for RCR1
dominant coefficient, we have 6166=966 MFCC features to                                                                           1
represent this motion instance.
  C. Classification and result evaluation                                                                                         0.8

   In this paper we use support vector machine (SVM) to


                                                                                                             true positive rate
classify the radar signature in two classes: fall and non falls.                                                                  0.6
We employed MATLAB to perform computational
experiments and LibSVM [20] to implement SVM. For                                                                                 0.4
computational efficiency, we used only a linear kernel for                                                                               Fall away from RCR2 (AUC = 0.974)
SVM in all our experiment together with a leave-one-out                                                                           0.2    Fall toward RCR2 (AUC = 0.998)

cross validation framework (i.e. for N samples, each                                                                                     Fall oblique to RCR2 (AUC = 0.976)
                                                                                                                                         Fall perpendicular to RCR2 (AUC = 0.966)
experiment uses N-1 samples for training and the remaining
                                                                                                                                   0
sample for testing). In order to evaluate the performance of                                                                        0   0.2
                                                                                                                                        0.4        0.6                             0.8   1
                                                                                                                                     false positive rate
our fall detection algorithms we produce a receiver operating
                                                                                                         Fig. 8. Detection results for RCR2.
characteristic (ROC) curve by thresholding the SVM scores

                                                                                                       258
                         Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:29:53 UTC from IEEE Xplore. Restrictions apply.
  A. Experiment2: comparison between ceiling and wall                                                                          REFERENCES
  mounted RCRs                                                                                   [1]  Murhy SL, “Deaths: Final Data for 1998,” National Vital Statistics
   We used configuration II to compare two sensor locations:                                          Reports, vol. 48, no. 11. Hyattsville, Maryland: National Center for
                                                                                                      Health Statistics, 2000.
wall and ceiling. In this configuration, two subjects
                                                                                                 [2] Centers for Disease Control and Prevention, National Center for
performed three types of falls at each of the 21 positions                                            Injury Prevention and Control. Web–based Injury Statistics Query
shown in Fig. 1.b.right. The fall recognition results obtained                                        and Reporting System (WISQARS) [online]. Accessed November
                                                                                                      30, 2010
for configuration II are given in Fig. 9. From Fig. 9, we can
                                                                                                      Stevens JA. Fatalities and injuries from falls among older adults –
conclude that the ceiling mounted RCR has better                                                      United States, 1993–2003 and 2001–2005. MMWR 2006a;55(45).
performance than the wall mounted one.                                                                C. G. Moran, R.T. Wenn, M. Sikand, A.M. Taylor, Early mortality
                                                                                                      after hip fracture: is delay before surgery important", J. of Bone and
                                                                                                      Joint Surgery, pp. 483-9, 2005.
                        1                                                                        [5] Giansanti D, Maccioni G and Macellari V, “The development and test
                                                                                                      of a device for the reconstruction of 3D position and orientation by
                                                                                                      means of a kinematic sensor assembly with rate gyroscopes and
                       0.8                                                                            accelerometers,” IEEE Trans. Biomed. Eng. 52 1271–7, 2005
                                                                                                 [6] N. Noury, A. Fleury, P. Rumeau, et al., "Fall detection-principles and




  true positive rate
                       0.6                                                                            methods", Proc. of the 29th IEEE EMBS, Lyon, France, Aug. 23-26,
                                                                                                 [7] M. Alwan, P. J. Rajendran, S. Kell, D. Mack, S. Dalal, M. Wolfe,
                                                                                                      R.Felder, " A smart and passive floor-vibration based fall detector for
                       0.4                                                                            elderly", 2nd IEEE Int. Conf. on Inf. & Comm. Tech.: from Theory to
                                                                                                      Applications - ICTTA’06, April 24 - 28, 2006, Damascus, Syria.
                                                                                                 [8] D. Anderson, R.H. Luke, J. Keller, M. Skubic, M. Rantz, Aud M,
                       0.2                      ceiling RCR (AUC=0.949)                               "Linguistic summarization of activities from video for fall detection
                                                wall RCR (AUC=0.858)                                  using voxel person and fuzzy logic. Computer Vision and Image
                                                                                                      Understanding, Vol. 113 (1), January 2009, pp. 80-89
                        0                                                                        [9] A. Sixsmith, N. Johnson, R. Whatmore, "Pyrolitic IR sensor arrays for
                         0     0.4 0.2    0.6                      0.8        1
                            false positive rate                                                       fall detection in the older population", J. Phys. IV France, vol. 128.
Fig. 9. Detection results for forward fall.                                                      [10] M. Addlesee, A. Jones, F. Livesey, and F. Samaria, “Orl active floor,”
                                                                                                      in IEEE Personal Communications, vol. 4.5, 1997, pp. 35 – 41.
                                                                                                 [11] M. Popescu, S. Coupland, "A fuzzy logic system for fall detection",
   Moreover, although the ceiling RCR has some variability                                            AAAI Fall Symposium, Washington DC, Nov 7-9 2008, pp. 78-83.
in detection due to fall direction, this is only about 30% from                                  [12] M. Popescu, A. Mahnot, "Acoustic fall detection using one-class
that of the wall and floor mounted sensors. However,                                                  classifier", 31th Int. IEEE EMBS Conf., Vancouver, BC, 2009
comparing Fig. 7, 8 and 9 we see that the ceiling RCR has a                                      [13] M. Popescu, Y. Li, M. Skubic, M. Rantz, "An acoustic fall detector
                                                                                                      system that uses sound height information to reduce the false alarm
slightly lower performance (3-4%) than the floor RCRs                                                 rate", 30th Int. IEEE EMBS Conf., Vancouver, BC, Aug. 20-24, 2008,
when falls are close to the sensor.                                                                   pp. 4628-4631.
                                                                                                 [14] Demiris G, Rantz MJ, Aud MA, Marek KD, Tyrer HW, Skubic M &
                                           V. CONCLUSIONS                                             Hussam AA, "Older Adults' Attitudes Towards and Perceptions of
                                                                                                      'Smarthome' Technologies: a Pilot Study," Medical Informatics and
   Based on the results, we have the following observations.                                          The Internet in Medicine, June, 2004, vol. 29, no. 2, pp. 87-94.
For configuration I, better result is achieved when the fall is                                  [15] D. Tahmoush, J. Silvious, “Radar stride rate extraction,” 13th
straightly towards or away from the RCR. The detection                                                International Machine Vision and Image Processing Conference, pp.
                                                                                                      128-133, 2009
performance also improves as the falling subject and the
                                                                                                 [16] M. Otero, “Application of a continous wave radar for human gait
RCR sensor is closer to each other. For configuration II,                                             recognition,” The MITRE Corporation, 2005.
ceiling mounted RCR can always generate more stable fall                                         [17] Yardibi, T.; Cuddihy, P.; Genc, S.; Bufi, C.; Skubic, M.; Rantz, M.;
detection results than wall mounted RCR and is less                                                   Liang Liu; Phillips, C.; , "Gait characterization via pulse-Doppler
sensitive to the fall direction. The wall mounted RCR has                                             radar," Pervasive Computing and Communications Workshops
                                                                                                      (PERCOM Workshops), 2011 IEEE International Conference on ,
stronger dependency on fall direction.                                                                vol., no., pp.662-667, 21-25 March 2011
   In conclusion, in further experiments, we consider to                                         [18] Liu L, Popescu M, Skubic M, Rantz M, Yardibi T & Cuddihy P,
install a ceiling mounted RCR for the entire apartment and                                            "Automatic Fall Detection Based on Doppler Radar Motion,"
deploy a floor RCR in the most probable falling location                                              Proceedings, 5th International Conference on Pervasive Computing
                                                                                                      Technologies for Healthcare, Dublin, Ireland, May 23-26, 2011.
(living room or bedroom).                                                                        [19] Liu L, Popescu M, Rantz M, Skubic, "Fall Detection using Doppler
                                                                                                      Radar and Classifier Fusion," Proceedings of EMBS on BHI,
                                         ACKNOWLEDGMENTS                                              Shenzhen, Jan 2-7, 2012.
                                                                                                 [20] http://www.csie.ntu.edu.tw/~cjlin/libsvm/
  The authors would like to thank Mr. Xiang Wang, Xin Du,
Calvin Phillips for help with data collection.
  We also thank Dr. Tarik Yardibi and Paul Cuddihy from
GE Global research for sensor support.




                                                                                            259
                       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:29:53 UTC from IEEE Xplore. Restrictions apply.

