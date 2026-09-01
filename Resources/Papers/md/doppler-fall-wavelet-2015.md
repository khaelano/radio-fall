IEEE TRANSACTIONS ON BIOMEDICAL ENGINEERING, VOL. 62, NO. 3, MARCH 2015                                                                                         865




## Doppler Radar Fall Activity Detection
                           Using the Wavelet Transform
                 Bo Yu Su, Student Member, IEEE, K. C. Ho, Fellow, IEEE, Marilyn J. Rantz, Member, IEEE,
                                       and Marjorie Skubic, Senior Member, IEEE


   Abstract—We propose in this paper the use of Wavelet trans-                       multipath reflections. Both the visual and audio systems can
form (WT) to detect human falls using a ceiling mounted Doppler                      work and complement with each other for inhome fall detection
range control radar. The radar senses any motions from falls as                      to provide reliable results. Both cannot be used; however, in the
well as nonfalls due to the Doppler effect. The WT is very effective
in distinguishing the falls from other activities, making it a promis-               bathroom area where statistics have shown to be challenging
ing technique for radar fall detection in nonobtrusive inhome elder                  for fall detection [18]. Having video camera in the bathroom is
care applications. The proposed radar fall detector consists of two                  obviously not preferred. Also, the small dimension of a bath-
stages. The prescreen stage uses the coefficients of wavelet decom-                  room would create too many multipath reflections to render the
position at a given scale to identify the time locations in which                    proper performance of an acoustic system, not to mention the
fall activities may have occurred. The classification stage extracts
the time–frequency content from the wavelet coefficients at many                     strong acoustic interferences from water flowing. In this paper,
scales to form a feature vector for fall versus nonfall classification.              we explore a relatively new approach based on motion sensing
The selection of different wavelet functions is examined to achieve                  by a Doppler range control radar (RCR) that would fill the need
better performance. Experimental results using the data from the                     for fall detection, especially in the bathroom.
laboratory and real inhome environments validate the promising                          A human fall generates motion that creates frequency change
and robust performance of the proposed detector.
                                                                                     between the sent and received signals of a Doppler radar. An-
   Index Terms—Classifier, Doppler radar, fall detection, wavelet.                   alyzing the radar signal carefully can detect human falls [19],
                                                                                     [20]. A Doppler radar fall detection system separates itself from
                             I. INTRODUCTION                                         the image-based and the acoustic-based system in that it can op-
                                                                                     erate in low-lighting and highly noisy environments. In addition,
       UMAN falls are a main cause to morbidity among older
H      adults (aged 65 years and older) [1]. Preventing falls and
detecting when they occur are important for elder care. Timely
                                                                                     the radar detection system can address the privacy concerns,
                                                                                     which are particularly crucial in the bathrooms or bedrooms.
                                                                                        One challenge for radar fall detection is that the radar will
detection of falls enables immediate assistance by caregiver and                     generate responses not only from human falls but also from other
minimizes the negative consequences of falls [2].                                    human or nonhuman motions. Signal processing is an indispens-
   Apart from the clinical techniques, less expensive personal                       able component to screen out the nonfall activities for improving
fall detection devices are becoming available in the commer-                         processing efficiency and increasing detection accuracy. Mel-
cial market. These devices can be broadly classified as wearable                     frequency cepstrum coefficients (MFCC) have been proposed
[3]–[7] and nonwearable [8]–[17]. Nonwearable devices are of-                        previously for radar fall detection [19]. MFCC is known to have
ten nonobtrusive and more acceptable to the users with bet-                          excellent features for speech recognition [21]. However, the ra-
ter comfort. A commonly found nonobtrusive fall detection                            tionale of using it in radar is not clear. Extensive evaluations
device is the video camera [8]–[12], where image processing                          under practical inhome environments indicate the performance
techniques can isolate and detect falls. However, visual-based                       of MFCC is not adequate and generates an exceeding number
systems cannot function under low-lighting or occlusion en-                          of false alarms in radar fall detection.
vironments. Another is the microphone array that utilizes                               This paper investigates another signal processing technique
the acoustic signal generated from the impact with the floor                         called Wavelet transform (WT) [22] for radar fall activity de-
for fall detection [13]–[15]. Acoustic devices have the short-                       tection. WT is a very effective method to analyze and extract
coming of requiring relatively quiet environments with little                        the characteristics of a signal that has nonstationary behaviors
                                                                                     [23]–[25] such as the radar fall signal. Indeed, WT has been
   Manuscript received August 5, 2014; revised October 24, 2014; accepted            proposed recently by many researchers to process biomedical
October 27, 2014. Date of publication November 4, 2014; date of current version      signals such as electrocardiographic [26] data and heart sound
February 16, 2015. This work was supported by the Agency for Healthcare              [23], [24] with numerous successes.
Research and Quality under Grant R01HS018477.
   B. Y. Su and M. Skubic are with the ECE Department, University of                    A fundamental question of using WT for radar fall detection
Missouri, Columbia, MO 65211 USA (e-mail: bsdg6@mail.missouri.edu;                   is the choice of the wavelet function. WT uses the dilated and
SkubicM@missouri.edu).                                                               translated versions of a wavelet function to form bases for signal
   K. C. Ho is with the ECE Department, University of Missouri, Columbia,
MO 65211 USA (e-mail: HoD@missouri.edu).                                             decomposition. In this paper, we examine over 100 wavelet
   M. Rantz is with the Sinclair School of Nursing, University of Missouri,          functions and identify the ones that are suitable for fall detection.
Columbia, MO 65211 USA (e-mail: RantzM@missouri.edu).                                   The proposed radar fall detection is a two-stage processing:
   Color versions of one or more of the figures in this paper are available online
at http://ieeexplore.ieee.org.                                                       prescreening and classification. The radar data comes in con-
   Digital Object Identifier 10.1109/TBME.2014.2367038                               tinuously and the first stage applies the WT coefficients at a
                          0018-9294 © 2014 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission.
        Authorized licensed use limited to: Universitas
                              See                       Brawijaya. Downloaded on September
                                   http://www.ieee.org/publications                          01,2026 at 11:32:42
                                                                      standards/publications/rights/index.html forUTC
                                                                                                                   morefrom IEEE  Xplore. Restrictions apply.
                                                                                                                         information.
866                                                                        IEEE TRANSACTIONS ON BIOMEDICAL ENGINEERING, VOL. 62, NO. 3, MARCH 2015



particular scale to locate an instance when potential fall activi-
ties may have occurred. The second stage forms feature vector
using the WT coefficients at many scales over the time region
identified and performs fall versus nonfall classification through
a trained classifier. A detection would trigger an alert to a
caregiver.
   The contributions of this paper includes the introduction of
using the WT for radar fall detection, the developments of the
WT prescreener and classifier that perform significantly bet-
ter than the previous methods, and the performance evalua-
tions of the proposed radar fall activity detector with a wide
variety of fall types and the actual fall data from an elderly
person.
   Closely related to our study, Gadde et al. [27] recently pro-
posed the use of wavelet processing for fall detection as well,
where three features are extracted from the continuous WT of
a radar signal for fall versus sit/stand classification using the
Mahalanobis distance. The investigation here uses the discrete
WT at dyadic scales instead which would reduce the complexity
[28]. Gadde et al. [27] chooses the Morlet wavelet, and we con-
duct a study to determine the wavelet function that yields the
best performance for the fall detection problem. The features
of the proposed classifier are different from those in [27]. We
are able to advance the performance as illustrated in Section
VI, through extensive evaluations on data measurements from
laboratory and inhome environments containing realistic and
actual human falls of many kinds. In addition, we establish the
                                                                                Fig. 1. (a) Waveform of radar output from human fall, the fall is occurred at
use of the wavelet coefficients at a certain scale for prescreening             14 s. (b) Spectrum of (a).
to identify time segments for fall versus nonfall classification.
Gadde et al. [27] focuses on classification only and applies an
energy detector for prescreening, which yields larger amounts
                                                                                   Fig. 1(a) gives a sample waveform of the radar output con-
of false alarms for the classifier to handle.
                                                                                taining a human fall, and Fig. 1(b) is its spectrogram. The fall
   This paper is organized as follows. Section II gives a brief
                                                                                happens at around 14 s. Due to the dynamics of the fall, a
background on Doppler radar. Section III provides the rationale
                                                                                higher frequency response appears at the beginning followed
of using the WT for radar fall activity detection. Section IV
                                                                                by lower frequency content. A human fall typically reaches to
elaborates the details of the proposed fall activity detector using
                                                                                about v = 5 m/s before hitting the ground. Using the Doppler
the WT. Section V describes the data measurements for per-
                                                                                frequency formula [31]
formance evaluations, and Section VI provides the results and
comparisons. Finally, we draw conclusions in Section VII.                                                                  2v
                                                                                                              Δfm ax =        fc                         (1)
                                                                                                                            c
                         II. DOPPLER RADAR                                      where c = 3 × 108 m/s is the light speed. We expect the fall
                                                                                signal covers a frequency range from 0 up to the maximum
   Doppler radar is a device that produces responses resulted
                                                                                Doppler shift of about Δfm ax = 200 Hz. The prediction is con-
from the Doppler effect caused by the motion of an object
                                                                                sistent with the spectrogram shown in Fig. 1(b).
along the radar-object direction [29]. A Doppler radar sends
                                                                                   Although we use this particular radar for investigation, the
out gated sinusoids (modulated rectangular pulses) at radio fre-
                                                                                WT technique for radar fall detection is general and can be
quencies and measures the echo reflected by a moving object.
                                                                                applied to other Doppler radar with straightforward adjustments.
The Doppler effect creates frequency difference between the
sent and received signals and the radar output contains harmon-
                                                                                                      III. WAVELET TRANSFORM
ics at the frequency change.
   The radar used in this study is a commercially available pulse-                 The Fourier transform (FT) is typically used when analyzing
Doppler RCR [30] which has a price comparable to a webcam.                      data in the frequency domain. One fundamental assumption of
The pulse repetition rate is 10 MHz and the duty cycle is 40%.                  the FT is that the data are stationary (or at least wide-sense
The carrier frequency fc is 5.8 GHz. The radar mixes the sent                   stationary) with time invariant statistical properties. It divides
and received signals and applies a low-pass filter to produce                   the frequency range occupied by the data into bins of equal
the output. The radar output is then digitized at a sampling                    size to examine the frequency content within. For biomedical
frequency of 960 Hz.                                                            applications, most of the signals encountered are nonstationary,

      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:32:42 UTC from IEEE Xplore. Restrictions apply.
SU et al.: DOPPLER RADAR FALL ACTIVITY DETECTION USING THE WAVELET TRANSFORM                                                                                 867




Fig. 2.    Data processing blocks for fall activity detection.




and they contain high-frequency components of short bursts and
low frequency content of long durations. The FT is not sufficient
and not suitable to analyze these kinds of signals, and the WT has
been developed to better examine these kinds of nonstationary
signals [22].                                                                      Fig. 3.   Multilevel wavelet decomposition of Doppler radar signal.
   A human fall typically starts with a quick movement of falling
down, followed by a slow motion of lying on the floor. A Doppler
radar captures the entire fall activity and produces similar dy-                   the classification stage to detect the fall behavior are elaborated
namic characteristics of short duration of high frequencies and                    in details below.
long period of low frequencies in the output. This kind of signal
behavior makes the WT a good choice for data analysis and                          A. Prescreening Stage
feature extractions for Doppler radar.
                                                                                      Prescreening should maintain 100% true positives, while
   The continuous WT of a signal x(t) is defined as [22]
                                                                                   seeking to minimize as many false positives as possible. To
                                                                                make a balance between efficiency and complexity, we use only
                          1                t−τ
              X(τ, a) = √        x(t)f ∗            dt         (2)                 a single scale for processing in this stage.
                            a                 a
                                                                                      Through theoretical study and validation by experimental re-
where f ∗ is the wavelet function. a is the scale factor, and                      sults, scale 4 is the best scale for prescreening. At the sampling
it is positive for practical applications. The wavelet is dilated                  rate of 960 Hz, scale 4 corresponds to a frequency range of
                                                                                   about 120 to 240 Hz [22]. Using (1), we get the speed range of
   √ a > 1 and contracted when a < 1. τ is the translation and
when
1/ a is the energy normalization factor. Different choices of                      3 to 6 m/s, which is what we expect at the early stage of a fall
the wavelet function will yield different WT.                                      before hitting the ground.
   The data are in sampled form in practice. By limiting the scale                    Fig. 3 is an example of the wavelet decomposition over a
a to be dyadic, the WT has a very efficient implementation by                      data segment shown at the top, which contains a fall around
using a pair of filters, one high-pass and the other low-pass, to                  10 s and several nonfall activities between 17.5 and 30 s. The
represent the wavelet function [22]. The resulting WT is often                     SWT outputs at scales 2i , denoted by Di (n), i = 1, 2, . . . , 6 are
termed as Discrete Stationary Wavelet Transform (SWT) [32]                         depicted below the data segment, where the wavelet function
in the literature. SWT is an online processing that transforms                     is the reverse biorthogonal 3.3 (rbio3.3) [34]. Note that they
the incoming data sequentially through successive applications                     do not share a common range in the y-axis. Although the WT
of the filters. The SWT is redundant in the sense that it will                     coefficients over the fall are becoming larger as the scale in-
generate the same number of samples in each dyadic scale as in                     creases from 2 to 64, the coefficients D2 (n) (scale 4) has the
the original data.                                                                 largest fall to nonfall distinction. This observation is consistent
   It is imperative to determine which wavelet function can pro-                   with the expectation from theory. We, therefore, use D2 (n) for
vide better performance in extracting the fall information and                     prescreening.
suppressing the nonfall activities. We shall use the area under                       The fall confidence value for prescreening is the short-time
the receiver operating characteristic (ROC) [33] curve to select                   energy of D2 (n) over a moving window to average out varia-
the wavelets. The details will be deferred to Section IV.                          tions. The window is Hamming; the window size is 0.5 s and
                                                                                   the amount of overlap is 50%. Hence, the location resolution of
                                                                                   a fall is 0.25 s. In essence, the prescreener detection value at
                               IV. ALGORITHM
                                                                                   frame j is
   Fig. 2 shows the block diagram of the proposed WT fall ac-
tivity detector. The data first passes through SWT to generate                                              
                                                                                                            N
                                                                                                 C(j) =           (w(l)(D2 (l + j(N/2))))2 .                 (3)
the wavelet coefficients at a number of dyadic scales. The co-
                                                                                                            l=1
efficients at a particular scale, scale 4 in our case, will be used
to identify the possible time location at which fall activity may                  where w(l) represents the Hamming window and, N = 480
have occurred. The SWT coefficients of other scales around the                     corresponds to the number of samples in 0.5 s.
identified time location will form a feature vector, which is used                    A typical fall lasts about 2 s, and a detection is declared
by a classifier to perform fall versus nonfall classification. The                 if several consecutive C(j) values over a 2 s window exceed
details of the prescreening stage to locate the fall occurrence and                the threshold. The frame that has the maximum prescreener

          Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:32:42 UTC from IEEE Xplore. Restrictions apply.
868                                                                        IEEE TRANSACTIONS ON BIOMEDICAL ENGINEERING, VOL. 62, NO. 3, MARCH 2015



value among the neighboring frames will be assigned as the                      typical fall of 2 s long, the extra 0.5 s provides a margin for
potential fall location and it will be denoted by jp . We use                   capturing the fall. This duration, under a frame size of 0.5 s and
a 0.5 s frame instead of 2 s for computing the prescreener value                50% overlap, translates to four frames before and four frames
to provide a more accurate time location of a possible fall event               after the frame jp .
to the classifier. A 0.5 s window size also allows us to reuse the                 The main purpose of the classification stage is to exploit the
prescreener values in the classifier.                                           changes in the time–frequency content during a fall to achieve
   Wavelet Selection: It is essential to determine which wavelet                better detection performance. Rather than using Ei (j), we re-
function is more suitable for fall detection. We shall use the                  move the energy factor in each scale through normalization with
detection performance curve which is the detection rate ver-                    the WT energy at that scale over the fall duration
sus the number of false alarms, and calculate the area under                                                             Ei (j)
the curve as an index to evaluate the detection performance                                         Ẽi (j) = M                                          (5)
from different wavelet functions. When computing the area, the                                                     m =−M Ei (jp + m)
y-axis is the detection rate from 0 to 1 and the x-axis is from 0 to            where j = jp − M, jp − M + 1, . . . , jp + M , and M = 4. The
the largest number of false alarms for reaching 100% detection                  features of frame j are
over the wavelet functions tested. The better wavelet function
for fall detection is the one that gives largest area.                                          v(j) = [ Ẽ1 (j), Ẽ2 (j), . . . , Ẽ6 (j) ] .            (6)
   In generating the detection performance curve, the detec-                    The overall feature vector for classification is
tion rate and the number of false alarms are obtained using                                     
the prescreening detection statistic C(j) after alarm merging                              v = vj p −M , vj p −M +1 , . . . , vj p +M .                   (7)
by stepping down the detection threshold. A typical fall is not                 The feature vector contains six normalized energies per frame
more than 2 s long, and we have one detection value for every                   over nine frames, giving a length of 54.
0.25 s. Contiguous detections up to a maximum of eight frames
are merged together with the largest among them as the merged                   C. Classifier
confidence. Noncontiguous detections are counted as separate
                                                                                  We use the nearest neighbor (NN) classifier with the feature
even if they are within eight frames.
                                                                                vector v. NN is the special case of the k-NN classifier having k
   The ROC is produced using the dataset collected in the lab
                                                                                equal to 1. Given a test sample vtest , we obtain the l1 norm [35]
as will be described in Section V. We defer the details of the
                                                                                between vtest and the nearest training sample of falls vtrain,fall
results for optimum wavelet selection to Section VI.
                                                                                                     distfall = |vtest − vtrain,fall | .                  (8)
B. Time–Frequency Features
                                                                                The l1 norm with respect to the closest nonfall training sample
   The alarms from the prescreening stage detects any motion                    is obtained similarly
at 3 to 6 m/s. This is a characteristic for a fall. Other activities
such as sitting down rapidly on a chair or standing up quickly,                                  distnonfall = |vtest − vtrain,nonfall | .                (9)
however, would create similar motion at the velocity range and                  The statistic for fall detection is
result in strong detection. Most importantly, the dynamic be-
havior of a fall that gives rise to the variations in the frequency                                  conf = distnonfall − distfall .                     (10)
content during a fall has not been explored. The classification                 Varying the detection threshold will trace out a detection per-
stage focuses on extracting the time–frequency features from                    formance curve.
the WT to improve the fall detection performance.                                  Although simple, NN provides reasonably good results due
   The feature vector for classification is the concatenation of                to the effectiveness of the time–frequency features from the WT.
the features from several frames centered at the fall location jp               We have tested other classifiers such as SVM with linear and
identified by the prescreener. For a given frame j, we compute                  Gaussian kernel functions and the results are not as good as NN.
the energy of the WT coefficients within after windowing:
                         
                         N                                                                               V. DATA DESCRIPTION
             Ei (j) =          (w(l) Di ( l + j(N/2) ) )2                (4)       The Doppler radar used in the experimental study is the GE
                         l=1
                                                                                Security PrecisionLine RCR-50 [30] whose characteristics have
where i = 1, 2, . . . , 6, w(l) is the Hamming window, Di (n) is                been described in Section II. The radar data acquisition unit is
the WT coefficients at scale 2i , and N = 480 is the window size                DATAQ DI710 [36] at 960 Hz sampling. The data collections
in samples corresponding to 0.5 s. The values Ei (j) characterize               from human subjects have been approved by the Institutional
the time–frequency content represented by six dyadic scales in                  Review Board at the University of Missouri.
frame j. The window advances 0.25 s. (240 samples) to yield                        The performance evaluation of the proposed fall detection
the time–frequency content for the next frame.                                  system contains three datasets. The first dataset D0 was collected
   The identified fall location from the prescreener is at the early            in 2011, under a laboratory that simulates a home environment.
stage of a fall before hitting the ground. We, therefore, collect               The second dataset D1 was acquired in 2013, in the bathrooms
the time–frequency content over the time range from 1 s before                  of several senior residence apartments at TigerPlace [37]. The
the fall location to 1.5 s after for classification. Considering a              third dataset D2 was taken also in a senior residence apartment

      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:32:42 UTC from IEEE Xplore. Restrictions apply.
SU et al.: DOPPLER RADAR FALL ACTIVITY DETECTION USING THE WAVELET TRANSFORM                                                                                     869



                                   TABLE I                                                                        TABLE III
                               DESCRIPTION OF D0                                                        STUNT ACTOR INFORMATION OF D1


 Fall                                  times        Acted Nonfall       times                                                            Height         Weight
                                                                                   Subject                 Gender         Age             (cm)           (kg)
 Loose balance-Forward                   5               Walk            486
 Loose balance-Backward                  5               Kick            107       Stunt actor A           female            34           160              60.8
 Loose balance-Left                      5         Clapping strongly     107
 Loose balance-Right                     5            Bend over           4
 Loss consciousness-Forward              5
 Loss consciousness-Backward             5                                                                          TABLE IV
 Loss consciousness-Left                 5                                                                  DESCRIPTION OF FALLS IN D1
 Loss consciousness-Right                5
 Loss consciousness-Straight down        5
                                                                                   Fall                                  Jan      Feb    Mar      Apr       May
 Trip and fall-Forward                   5
 Trip and fall-Sideways                  5
                                                                                   Loose balance-Forward                 0         1       2       2         6
 Slip and fall-Forward                   5
                                                                                   Loose balance-Backward                1         0       2       0         6
 Slip and fall-Sideways                  5
                                                                                   Loose balance-Left                    1         1       0       0         6
 Slip and fall-Backward                  5
                                                                                   Loose balance-Right                   1         1       2       0         6
 Reach-fall (chair)-Forward              5
                                                                                   Loss consciousness-Forward            0         1       2       0         0
 Reach-fall (chair)-Left                 5
                                                                                   Loss consciousness-Backward           1         0       2       0         0
 Reach-fall (chair)-Right                5
                                                                                   Loss consciousness-Left               1         1       0       0         0
 Reach-fall (chair)-Sliding forward      5
                                                                                   Loss consciousness-Right              1         0       2       0         0
 Reach-fall (chair)-Sliding backward     5
                                                                                   Loss consciousness-Straight down      0         1       0       2         0
 Couch fall-Upper body first             5
                                                                                   Trip and fall-Forward                 1         0       0       0         0
 Couch fall-Hip first                    5
                                                                                   Trip and fall-Sideways                1         1       0       0         0
                                                                                   Slip and fall-Forward                 1         1       2       0         0
                                                                                   Slip and fall-Sideways                0         1       2       2         0
                                                                                   Slip and fall-Backward                0         0       2       2         0
                                TABLE II                                           Reach-fall (chair)-Forward            0         0       2       0         0
                      STUNT ACTOR INFORMATION OF D0                                Reach-fall (chair)-Left               1         0       0       0         0
                                                                                   Reach-fall (chair)-Right              1         1       0       0         0
                                                                                   Reach-fall (chair)-Sliding forward    1         1       2       0         0
                                                       Height          Weight      Reach-fall (chair)-Sliding backward   0         1       2       2         0
 Subject                 Gender         Age             (cm)            (kg)

 Stunt actor A           female          32             160             61
 Stunt actor B           female          46             163             53
 Stunt actor C            male           30             173             77       the fall protection pad, and pulling the chair will also generate
                                                                                 many nonfall activities.
                                                                                    In dataset D1, the stunt actor A, the same as the
                                                                                 one in D0 with information given in Table III, per-
at TigerPlace in 2013, but in the living room (not the bathroom)                 formed falls and nonfalls at three different bathrooms
with actual falls from an elderly resident. The data were recorded               at TigerPlace apartment over a period of five months.
continuously in time as the detection system operates in clinical                Two bathrooms have dimensions 2.6 m × 2.4 m ×
practice and we did not manually isolate out the fall and nonfall                2.7 m and one has 2.3 m × 2.3 m × 2.7 m. The radar was
segments.                                                                        mounted in the middle of the bathrooms, above in the attic. The
   For D0, the dimension of the simulated living room was 9 m ×                  dataset D1 has 211 min in total from the collections over five
8.2 m × 3 m (L × W × H). The radar was mounted at the ceil-                      different months. The kinds of falls in D1 (see Table IV) are the
ing center pointing downward. The dataset contains 21 kinds                      same as in D0 except the last two. Fourteen types of nonfall ac-
of falls from a combination of various fall types and direc-                     tivities are specifically performed to emulate real-life scenarios
tions as tabulated in Table I. Each was performed five times                     as follows. The counts for them in the five months are listed in
from professional stunt actors, whose statistics are summa-                      Table V.
rized in Table II, to strongly resemble the falls of elders after                     1) Bend at the knees and stoop to a squatting position on
training by nursing staff [38]. The dataset has eight kinds of                            the floor, from a standing position.
acted nonfalls that are typical daily activities. The total num-                      2) Bend down and kneel on the floor, from a standing
ber of falls is 105 and that of acted nonfalls is 704. The total                          position.
length of D0 is 145 min. The data were collected and processed                        3) Bend down and kneel on the floor, wait for 2 s, then lie
continually.                                                                              down on the floor, from a standing position.
   In addition to the intentional nonfalls described in Table I,                      4) Bend down to plug an appliance into an electrical outlet
there are many unintentional nonfall activities during the data                           close to the floor, from a standing position.
collection such as warming up, actively moving right before                           5) Squat to tie a shoe, from a standing position.
or after falls, sitting down on a chair, reclining on a sofa, and                     6) Sit on the floor with the legs tucked under the body, from
standing up after performing each fall. These activities create                           a standing position.
an additional 286 nonfalls. Furthermore, when preparing the                           7) Sit on the floor with the legs extended from the body,
experiment, repositioning the sofa, opening the door, moving                              from a standing position.

        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:32:42 UTC from IEEE Xplore. Restrictions apply.
870                                                                          IEEE TRANSACTIONS ON BIOMEDICAL ENGINEERING, VOL. 62, NO. 3, MARCH 2015



                                 TABLE V
                       DESCRIPTION OF NONFALLS IN D1


 Nonfall Type          Jan        Feb        Mar            Apr        May

 1                      0          0           0             0          2
 2                      1          0           0             0          2
 3                      1          1           0             0          2
 4                      1          1           2             2          0
 5                      0          1           2             2          0
 6                      0          0           2             0          0
 7                      0          0           0             0          0
 8                      1          2           2             2          4
 9                      2          1           4             0          2
 10                     0          1           2             2          2
 11                     1          0           2             0          2
 12                     1          1           0             0          2
 13                     1          1           2             0          0
 14                     3          3           6             2          6


                                                                                 Fig. 4.   Relative detection performance from different wavelet functions.
                                  TABLE VI
                RESIDENT’S (IN TIGERPLACE) INFORMATION OF D2


## Height            Weight
 Subject             Gender            Age          (cm)              (kg)

 1                   female             75           160              63.5




     8) Perform three sit-ups and some stretches of upper
        and lower extremities, from a lying position on the
                                                                                 Fig. 5. Wavelet function rbio3.3 represented by a pair of filters in decompo-
        floor.                                                                   sition. (a) Decomposition low-pass filter coefficients. (b) Decomposition high-
     9) Slowly rise to a half kneeling position, then rise to a                  pass filter coefficients.
        standing position, from a lying position on the floor.
   10) Appear to trip but will regain balance and continue walk-
        ing, from a walking position.                                                                 VI. EXPERIMENTAL RESULTS
   11) Walk forward for 3 s and then stop suddenly, from a
        standing position.                                                       A. Wavelet Selection
   12) Walk forward for 3 s and then stop suddenly and turn                         We shall use the detection performance from the prescreener
        around, from a standing position.                                        on D0 to evaluate the performance of different wavelet functions
   13) Walk to a stationary chair and sit on it, from a standing                 for fall detection.
        position.                                                                   We test 111 commonly used wavelet functions for evaluations
   14) Bend over to pick up a book on the floor, from a sitting                  [28], [34]:
        position in a chair.                                                        1) Daubechies (db) 1 ∼ 45;
   As in D0, D1 also contains those unintentional nonfall activ-                    2) biorthogonal (bior) and reverse biorthogonal (rbio) series
ities, which are not listed in Table V.                                                 (1.1, 1.3, 1.5, 2.2, 2.4, 2.6, 2.8, 3.1, 3.3, 3.5, 3.7, 3.9, 4.4,
   The dataset D2 is real life data acquired during the daily liv-                      5.5, 6.8);
ing of an elderly resident whose statistics are summarized in                       3) coiflets (coif) 1 ∼ 5;
Table VI. The radar was placed above the middle of the living                       4) discrete approximation of Meyer wavelet (dmey);
room (4.4 m × 6.4 m × 2.7 m) at the attic in a TigerPlace                           5) symlets (sym) 1 ∼ 30.
apartment. The dataset is ten days long containing 13 real falls                    The areas under the detection curves from the wavelet func-
from the resident. At least one fall occurred in each day and the                tions are sorted in descending order and the results after normal-
normal daily activities contribute to nonfalls. The subject has a                izing them with the largest area are shown in Fig. 4 using cross
cat that has a weight of 3.8 Kg. The staff of the TigerPlace came                symbols. The best five wavelets are “rbio3.3,” “db3,” “sym3,”
inside the apartment every day to help the subject and other                     “rbio1.3,” and “bior2.2.” Fig. 5 shows the low-pass and the high-
people visited during a day. The data portions with staff or visi-               pass filter representation of “rbio3.3.” The worst one is “rbio3.1”
tors present are removed, for the purpose to assess performance                  with a normalized area of 0.85.
of the radar fall detection system under natural behavior of the                    To support the use of the second level of wavelet decompo-
resident alone. Indeed, automated fall detection is not urgent                   sition (a = 4) for prescreening, Fig. 6 shows the ROC curves
when others are present.                                                         from different scales of the wavelet rbio3.3. It confirms that

      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:32:42 UTC from IEEE Xplore. Restrictions apply.
SU et al.: DOPPLER RADAR FALL ACTIVITY DETECTION USING THE WAVELET TRANSFORM                                                                              871




Fig. 6. Prescreening ROCs of D0 using the wavelet coefficients from rbio3.3     Fig. 7.   Prescreener detection performance for D0.
at different scales.



the wavelet coefficients at scale 4 provide better detection than
those from other scales.
   A better wavelet function for prescreening would yield
smaller number of nonfalls for classification. It would reduce
the effort of a classifier and provide better detection accuracy
after classification as well.
   We next examine the classification performance of different
wavelet functions, at the detection locations identified by the
prescreener using its best wavelet function “rbio3.3.” The areas
under the detection curves relative to the largest are shown
in Fig. 4 using circle symbols. The top five wavelets for the
classification stage are “rbio3.3,” “coif4,” “db10,” “bior2.6,” and
“db11.” It is interesting that “rbio3.3” gives the best performance
for both prescreening and classification.
   For the results presented in the rest of this section, we use the
“rbio3.3” in both the prescreening and classification stages.
                                                                                Fig. 8.   Prescreener detection performance for D1.
B. Performance Evaluation
   1) Prescreening: For reference purpose, we generate the
                                                                                prescreener and the STFT prescreener perform better than the
performance of the energy detector from the input signal as
                                                                                energy detector; the difference is particularly obvious in D1.
follows:
                                                                                The proposed WT prescreener is much more effective than the
                      1 
                           M
                                                                                STFT prescreener. At 95% detection rate, the reduction in the
     Xenergy (j) =           (w(n))((x(n + j(M/2)))2 )                 (11)     number of false alarms is almost by a factor of 3.
                      M n =1
                                                                                   2) Classification: We shall use the proposed prescreener to
where Xenergy (j) represents the signal energy in frame j, and                  locate the possible fall activities and then apply a classifier
x(n) is the radar data samples. The index n denotes the sample                  to improve the performance. We shall compare the proposed
number within the segment, and M corresponds to the number                      wavelet features with the MFCC features developed in [19]. For
of samples with the 2 s window size. w(n) is the Hamming                        a fair comparison, both features are used to train the same kind
window function. We shall use Xenergy (i) to create the energy                  of classifier, which is the NN, for classification. We also im-
detector ROC curve.                                                             plemented the classification method from [27] that is based on
   In addition to the energy detector, we also generated the re-                three time-scale (TS) features and the Mahalanobis distance.
sults from the detector developed in [19], which is based on                    The cross validation uses leave one out in the training and
the short-time Fourier transform (STFT). Figs. 7 and 8 com-                     testing [39].
pare the fall detection performance from the three prescreeners                    Fig. 9 shows the ROC classification performance, in terms
for datasets D0 and D1. As expected, both the proposed WT                       of sensitivity versus 1-specificity, for D0. The results from the

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:32:42 UTC from IEEE Xplore. Restrictions apply.
872                                                                            IEEE TRANSACTIONS ON BIOMEDICAL ENGINEERING, VOL. 62, NO. 3, MARCH 2015




                                                                                    Fig. 11.   ROC curves of the proposed classifier for D1 in five different months.

Fig. 9.     ROC curves of the proposed and MFCC classifiers for D0.

                                                                                       The performance for D1 is shown in Fig. 10. In this dataset,
                                                                                    the MFCC classifier has better accuracy than the prescreeener
                                                                                    for the sensitivity below 90%. The TS classifier follows the
                                                                                    prescreener performance but having a nearly constant decrease
                                                                                    in sensitivity at a given specificity. The proposed WT classifier
                                                                                    remains the best and outperforms the prescreener considerably.
                                                                                    The WT classifier has 58 false alarms to reach 100% detec-
                                                                                    tion. Thirty-three false alarms come from significant prepara-
                                                                                    tion motions before or after the data collections: 19 from stunt
                                                                                    actors standing up after performing falls; 1 from the designed
                                                                                    type 3 nonfall activity; 1 from the designed type 4 nonfall ac-
                                                                                    tivity; 1 from the designed type 13 nonfall activity; and 3 from
                                                                                    the designed type 14 nonfall activity.
                                                                                       Fig. 10 is the aggregated results of the data collected over five
                                                                                    months from January to May, 2013. Fig. 11 gives the separated
                                                                                    performance of the proposed detector for individual months
                                                                                    separately. It is interesting to note that detection performance in
                                                                                    March and May are particularly worse compared to the others. In
                                                                                    the two months, there were extra human activities in preparing
Fig. 10.     ROC curves for D1 using leave one out cross validation.                the experiments, and the stunt actor was standing up faster than
                                                                                    normal after performing the falls. Among the false alarms to
                                                                                    reach 100% sensitivity in Fig. 10, 26 out of 33 from activities
                                                                                    preparing the experiments, and 14 out of 19 from standing up
MFCC classifier are worse than the prescreener at the sensitivity                   after falls are from these two months.
below 90% and comparable above. The performance of the                                 In practice, a classifier must be trained beforehand using avail-
TS classifier is also below the prescreener. The proposed WT                        able data before putting into practical use. The robust perfor-
classifier is able to provide significant performance gain over                     mance of the proposed classifier is illustrated in Fig. 12, where
the prescreener.                                                                    we use the lab dataset D0 for training and apply it to the dataset
   To obtain a better understanding, we analyzed the false alarms                   D1 for testing. The proposed classifier has consistent and com-
of the proposed classifier to reach 100% sensitivity. Among                         parable performance with the cross validation results in Fig. 10,
these 95 false alarms, 59 are caused by significant human activ-                    and this is not the case for the MFCC and TS classifiers.
ities such as moving around for preparing and finishing the data                       The falls in D0 and D1 are from stunt actors. The apparent
collection; 11 from intentional kick actions for time synchro-                      large number of false alarms from the proposed classifier to
nization; 7 from the stunt actors standing up after performing                      reach 100% detection is caused by nonnatural activities of the
falls; 6 from the warm up actions of the stunt actors; 5 from the                   stunt actor. Using D2, we are able to assess the performance of
stunt actor motion activities right before or after falls; 4 from                   the proposed detector for actual falls from an elderly resident
clapping strongly; 2 from stunt actors bending over; and 1 from                     in a typical home environment. The proposed prescreener first
a stunt actor lying down on the sofa.                                               processes the dataset D2, and the proposed WT or the MFCC

          Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:32:42 UTC from IEEE Xplore. Restrictions apply.
SU et al.: DOPPLER RADAR FALL ACTIVITY DETECTION USING THE WAVELET TRANSFORM                                                                                       873



                                                                                                               TABLE VII
                                                                                     AREA UNDER THE ROC (AUC), SENSITIVITY, SPECIFICITY, AND ACCURACY
                                                                                                      AT THE OPERATING THRESHOLD


                                                                                                                                 D0            D1             D2

                                                                                      WT Prescreener             AUC             0.91         0.82         0.71
                                                                                                               Sensitivity      92.3%        86.5%        76.9%
                                                                                                               Specificity      88.9%        80.8%        76.9%
                                                                                                               Accuracy         89.5%        81.9%        77.6%
                                                                                      WT Prescreener and         AUC             0.96         0.92         0.82
                                                                                      WT Classifier            Sensitivity      97.1%        95.1%        92.3%
                                                                                                               Specificity      92.2%        90.7%        81.4%
                                                                                                               Accuracy         93.0%        91.6%        83.5%
                                                                                      WT Prescreener and         AUC             0.91         0.85         0.75
                                                                                      MFCC Classifier          Sensitivity      93.3%        87.8%        92.3%
                                                                                                               Specificity      89.7%        89.1%        62.9%
                                                                                                               Accuracy         90.3%        88.8%        68.6%
                                                                                      WT Prescreener and         AUC             0.76         0.77         0.48
                                                                                      TS Classifier            Sensitivity      85.7%        85.4%        69.2%
                                                                                                               Specificity      71.4%        72.4%        50.0%
                                                                                                               Accuracy         73.8%        75.1%        73.1%

Fig. 12.     ROC curves for D1 using D0 as the training data.

                                                                                       The performance shown in Fig. 13 is for fall detection using
                                                                                    radar in the living room of an elderly resident. We expect it
                                                                                    represents the lower bound performance for fall detection in the
                                                                                    bathroom, since there are more differences between the training
                                                                                    and testing data and the living room has more nonfall activities
                                                                                    that can cause false positives than the bathroom.
                                                                                       In addition to the ROC curves, Table VII tabulates the perfor-
                                                                                    mance metrics of the detectors obtained from the three datasets
                                                                                    at the operating thresholds [33]. The values shown for D1 are
                                                                                    the cross validation results as in Fig. 10. The proposed WT fall
                                                                                    detector (WT-based prescreener and classifier) achieves the best
                                                                                    and consistent performance. The experimental studies corrob-
                                                                                    orate that the time–frequency features extracted from WT are
                                                                                    very effective for fall detection and the proposed fall activity
                                                                                    detector has more robust behavior than the previously proposed
                                                                                    detector using MFCC features.
                                                                                       The TS classifier [27] also uses wavelet processing and its
                                                                                    performance is below expectation. We believe there are two
Fig. 13.     ROC curves for D2 using D1 as the training data.                       main reasons. First, the three features of the TS classifier are
                                                                                    derived from backward falls and sit/stand nonfalls. Datasets D0
                                                                                    and D1 have large varieties of falls and nonfalls performed by
                                                                                    professional stunt actors as tabulated in Tables I, IV, and V, and
classifier operates on the declared locations from a prescreener
                                                                                    they have different characteristics than just backward falls and
to produce the detection performance. Training uses dataset D1,
                                                                                    sit/stand nonfalls. Second, the radar in [27] was placed 40 in
where the data from March and May are excluded due to their
                                                                                    above the floor looking horizontally and our radar was mounted
abnormal behavior.
                                                                                    in the ceiling pointing down. A Doppler radar responds to the
   Fig. 13 illustrates the results. The MFCC classifier produces
                                                                                    relative motion along the radar-object direction. The received
worst results than the prescreener, which is consistent with
                                                                                    signals from a ceiling mounted radar and a ground standing
the previous observations from Fig. 12. The proposed detector
                                                                                    radar behave differently. We believe that the TS classifier from
yields promising results. The number of false alarms is much
                                                                                    [27] would work better when the radar is mounted on a wall
less to reach 100% detection, only 16 over 10 days. The pro-
                                                                                    looking horizontally.
posed WT fall detector is quite resilient to false positives created
by natural daily nonfall activities. Among the 16 false alarms, 11
                                                                                                               VII. CONCLUSION
are from nonhuman activities possibility due to the cat or elec-
tromagnetic interference; 1 from random noise with nobody in                           We have developed a reliable detector using Doppler radar
the living room; 2 from the subject adjusting the height of a                       measurements for the detection of human falls. The detector is
chair; 1 from the subject standing up quickly; and 1 from the                       based on WT that explores the time–frequency characteristics
subject bending over to pick up an object.                                          of a fall caused by its unique dynamics. The detector has two

           Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:32:42 UTC from IEEE Xplore. Restrictions apply.
874                                                                           IEEE TRANSACTIONS ON BIOMEDICAL ENGINEERING, VOL. 62, NO. 3, MARCH 2015



stages; the prescreening stage that uses the WT coefficients at                     [15] O. Gabai and H. Primo, “Acoustic motion capture,” U.S. Patent
a given scale to identify the possible occurrence of a fall, and                         20 110 009 194, Jan. 13, 2011.
                                                                                    [16] D. Anderson, R. H. Luke, J. M. Keller, M. Skubic, M. Rantz, and M. Aud,
the classification stage that uses the WT coefficients at several                        “Linguistic summarization of video for fall detection using voxel per-
scales over many successive frames to form a feature vector                              son and fuzzy logic,” J. Comput. Vision Image Understanding, vol. 113,
for fall versus nonfall classification. The better wavelet func-                         pp. 80–89, Jul. 2008.
                                                                                    [17] E. E. Stone and M. Skubic, “Fall detection in homes of older adults
tions to reach higher detection accuracy are “rbio3.3,” “db3,”                           using the microsoft kinect,” IEEE J. Biomed. Health Informat., to be
“sym3,” “rbio1.3,” and “bior2.2” for prescreening and “rbio3.3,”                         published.
“coif4,” “db10,” “bior2.6,” “db11” for classification. Evalua-                      [18] M. J. Krauss, B. Evanoff, E. Hitcho, K. E. Ngugi, W. C. Dunagan,
                                                                                         I. Fischer, S. Birge, S. Johnson, E. Costantinou, and V. J. Fraser, “A
tions based on the data collected in the lab, in the bathrooms,                          case-control study of patient, medication, and care-related risk fac-
and in the senior residence apartment validate the promis-                               tors for inpatient falls,” J. Gen. Internal Med., vol. 20, pp. 116–122,
ing and robust performance of the proposed WT fall activity                              Feb. 2005.
                                                                                    [19] L. Liu, M. Popescu, M. Rantz, and M. Skubic, “Fall detection
detector.                                                                                using Doppler radar and classifier fusion,” in Proc. IEEE 32th
                                                                                         Annu. Int. Eng. Med. Biol. Soc. Conf. BHI, Hong Kong, Jan. 2012,
                                                                                         pp. 180–183.
                           ACKNOWLEDGMENT                                           [20] L. Liu and M. Popescu, “An automatic in-room fall detection system
                                                                                         using Doppler radar signatures,” submitted for publication J. Ambient
   The authors would like to thank L. Liu for providing the                              Intell. Smart Environ., 2014.
processing codes of STFT prescreening and MFCC feature ex-                          [21] H. Y. Cho and Y. H. Oh, “On the use of channel-attentive MFCC for robust
traction from radar signals used in [19].                                                recognition of partially corrupted speech,” IEEE Signal Process. Lett.,
                                                                                         vol. 11, no. 6, pp. 581–584, Jun. 2004.
                                                                                    [22] O. Rioul and M. Vetterli, “Wavelets and signal processing,” IEEE Signal
                                   REFERENCES                                            Process. Mag., vol. 8, no. 4, pp. 14–38, Oct. 1991.
                                                                                    [23] I. Hossain and Z. Moussavi, “An overview of heart-noise reduction of
 [1] S. B. Vyrostek, J. L. Annest, and G. W. Ryan, “Surveillance for fatal               lung sound using wavelet transform based filter,” in Proc. IEEE 25th
     and nonfatal injuries—United States, 2001,” MMWR Surveill Summaries,                Annu. Int. Eng. Med. Biol. Soc. Conf., Cancun, Mexico, Sep. 2003,
     vol. 53, pp. 1–57, 2004.                                                            pp. 458–461.
 [2] F. Bagala, C. Becker, A. Cappello, L. Chiari, K. Aminian, J. M. Hausdorff,     [24] J. J. Lee, S. M. Lee, I. Y. Kim, H. K. Min, and S. H. Hong, “Comparison
     W. Zijlstra, and J. Klenk, “Evaluation of accelerometer-based fall de-              between short time Fourier and wavelet transform for feature extraction
     tection algorithms on real-world falls,” PLoS ONE, vol. 7, pp. 1–9,                 of heart sound,” in Proc. Int. IEEE TENCON Conf., Cheju Island, Korea,
     May 2012.                                                                           Dec. 1999, pp. 1547–1550.
 [3] T. Tamrat, M. Griffin, S. Rupcic, S. Kachnowski, T. Taylor, and J. Barfield,   [25] M. Yashita and N. Hamada, “Time-frequency masking method using
     “Operationalizing a wireless wearable fall detection sensor for older               wavelet transform for BSS problem,” in Proc. Int. IEEE TENCON Conf.,
     adults,” in Proc. 6th Int. Conf. PervasiveHealth, San Diego, CA, USA,               Hong Kong, China, Nov. 2006, pp. 1–4.
     May 2012, pp. 297–302.                                                         [26] L. Brechet, M. F. Lucas, C. Doncarli, and D. Farina, “Compression
 [4] P. Kumar and P. C. Pandey, “A wearable inertial sensing device for fall             of biomedical signals with mother wavelet optimization and best-basis
     detection and motion tracking,” in Proc. IEEE India Annu. Conf., Mumbai,            wavelet packet selection,” IEEE Trans. Biomed. Eng., vol. 54, no. 12,
     India, Dec. 2013, pp. 1–6.                                                          pp. 2186–2192, Dec. 2007.
 [5] M. Terroso, R. Freitas, J. Gabriel, A. T. Marques, and R. Simoes, “Ac-         [27] A. Gadde, M. G. Amin, Y. D. Zhang, and F. Ahmad, “Fall detection and
     tive assistance for senior healthcare: A wearable system for fall detec-            classification based on time-scale radar signal characteristics,” Proc. SPIE,
     tion,” in Proc. 8th Iberian Conf. Inform. Syst., Technol., Lisboa, Portugal,        vol. 9077, May 2014.
     Jun. 2013, pp. 1–6.                                                            [28] S. Mallat, A Wavelet Tour of Signal Processing. New York, NY, USA:
 [6] W. Bao, Y. Chen, and X. Zeng, “Wearable wireless system with embedded               Academic, 2008.
     real-time fall detection logic for elderly assisted living applications,” in   [29] F. Pfanner, T. Allmendinger, T. Flohr, and M. KachelrieB, “Monitoring
     Proc. IEEE 11th Int. Conf. Solid-State Integr. Circuit Technol., Xi’an,             respiratory motion using continuous wave Doppler radar in a near field
     China, Oct. 2012, pp. 1–3.                                                          multi antenna approach,” in Proc. Int. IEEE Med. Imag. Conf., Anaheim,
 [7] D. Chen, W. Feng, Y. Zhang, X. Li, and T. Wang, “A wearable wireless                CA, USA, Oct. 2012, pp. 3575–3581.
     fall detection system with accelerators,” in Proc. IEEE Int. Conf. Robot.      [30] Available: http://utcfssecurityproducts.com/
     Biomemetics, Phuket, Thailand, Dec. 2011, pp. 2259–2263.                       [31] R. W. Ditchburn, Light. New York, NY, USA: Dover, 1991, pp. 331–333.
 [8] V. Vaidehi, K. Ganapathy, K. Mohan, A. Aldrin, and K. Nirmal, “Video           [32] G. P. Nason and B. W. Silverman, “The stationary wavelet transform and
     based automatic fall detection in indoor environment,” in Proc. IEEE                some statistical applications,” Lect. Notes Statist., vol. 103, pp. 281–299,
     Int. Conf. Recent Trends Inform. Technol., Chennai, India, Jun. 2011,               1995.
     pp. 1016–1020.                                                                 [33] M. H. Zweig and G. Campbell, “Receiver-operating characteristic (ROC)
 [9] A. Edgcomb and F. Vahid, “Automated fall detection on privacy-enhanced              plots: A fundamental evaluation tool in clinical medicine,” Clin. Chem.,
     video,” in Proc. IEEE 34th Annu. Int. Conf. Eng. Med. Biol. Soc., San               vol. 39, pp. 561–577, 1993.
     Diego, CA, USA, Aug. 2012, pp. 252–255.                                        [34] I. Daubechies, Ten Lectures on Wavelets. Philadelphia, PA, USA: SIAM,
[10] V. Vaidehi, K. Ganapathy, K. Mohan, A. Aldrin, and K. Nirmal, “Video                1992.
     based automatic fall detection in indoor environment,” in Proc. IEEE           [35] J. W. Williams and Y. Li, “Comparative study of distance functions
     Int. Conf. Recent Trends Inform. Technol., Chennai, Tamil Nadu, India,              for nearest neighbors,” in Advanced Techniques in Computing Sci-
     Jun. 2011, pp. 1016–1020.                                                           ences and Software Engineering. New York, NY, USA: Springer, 2010,
[11] Y. T. Ngo, H. V. Nguyen, and T. V. Pham, “Study on fall detection based             pp. 79–84.
     on intelligent video analysis,” in Proc. Int. Conf. Adv. Technol. Commun.,     [36] Available: http://www.dataq.com
     Hanoi, Vietnam, Oct. 2012, pp. 114–117.                                        [37] TigerPlace is an assisted living facility in Columbia, Missouri, USA [On-
[12] W. Y. Shieh and J. C. Huang, “Speedup the Multi-camera video-                       line]. Available: http://eldertech.missouri.edu/
     surveillance system for elder falling detection,” in Proc. Int. Conf. Em-      [38] M. J. Rantz, M. A. Aud, G. Alexander, B. J. Wakefield, M. Skubic,
     bedded Softw, Syst., Zhejiang, China, May 2009, pp. 350–355.                        R. H. Luke, D. Anderson, and J. M. Keller, “Falls, technol-
[13] Y. Li, Z. Zeng, M. Popescu, and K. C. Ho, “Acoustic fall detection using            ogy, and stunt actors: New approaches to fall detection and fall
     a circular microphone array,” in Proc. IEEE 32th Annu. Int. Conf. Eng.              risk assessment,” J. Nursing Care Quality, vol. 23, pp. 195–201,
     Med. Biol. Soc., Buenos Aires, Argentina, Sep. 2010, pp. 2242–2245.                 Jul. 2008.
[14] Y. Li, K. C. Ho, and M. Popescu, “A microphone array system for                [39] R. Kohavi, “A study of cross-validation and bootstrap for accuracy estima-
     automatic fall detection,” IEEE Trans. Biomed. Eng., vol. 59, no. 5,                tion and model selection,” in Proc. Int. Joint Conf. Artif. Intell., Montreal,
     pp. 1291–1301, May 2012.                                                            QC, Canada, Aug. 1995, pp. 1137–1143.



       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:32:42 UTC from IEEE Xplore. Restrictions apply.
SU et al.: DOPPLER RADAR FALL ACTIVITY DETECTION USING THE WAVELET TRANSFORM                                                                                     875



                          Bo Yu Su (S’14) was born in Taipei, Taiwan. He re-                                   Marilyn J. Rantz (M’12) received the Ph.D. degree
                          ceived the B.S. degree in electrical engineering from                                in nursing from the University of Wisconsin, Mil-
                          National Sun Yat-Sen University, Kaoshiung, Tai-                                     waukee, WI, USA, in 1992.
                          wan, in 2002, and the M.S. degree in electrooptical                                      She is with the University of Missouri (MU),
                          engineering from Tatung University, Taipei, Taiwan,                                  Columbia, MO, USA, where she is a Faculty Member
                          in 2004. He is currently working toward the Ph.D. de-                                in the Sinclair School of Nursing and the Department
                          gree with the Department of Electrical and Computer                                  of Family and Community Medicine, MU School of
                          Engineering, University of Missouri, Columbia, MO,                                   Medicine, where she is currently a Professor. She
                          USA.                                                                                 is also the University Hospital Professor of nursing.
                              His current research interests include the Doppler                               She has developed and sustained a research program
                          radar and eldercare.                                                                 to improve the quality of care of elderly. Her innova-
                                                                                    tive work in nursing home quality spans nearly 30 years, in practice and as a
                                                                                    Leading Researcher, establishes her as a Premier International Expert in quality
                                                                                    measurement in nursing homes. She and her multidisciplinary research team has
                                                                                    garnered nearly 60 million in funds to support their work measuring effective-
                                                                                    ness of nurse care coordination, conduct cutting edge research in long-term care,
                                                                                    new delivery models of care, and for technology development to enhance aging
                                                                                    in place of community-dwelling elders. Her current research interests include
                                                                                    technology to enhance aging in place, long-term care quality measurement, and
                                                                                    quality improvement.
                                                                                        Prof. Rantz received both the MU Sinclair School of Nursing Faculty Award
                                                                                    for Excellence in Research and the National Gerontological Nursing Associ-
                                                                                    ation Lifetime Achievement Award in 2005. In 2006, she received the MU
                           K. C. Ho (M’91–SM’00–F’09) was born in Hong              Alumni Association Faculty Alumni Award for her outstanding contributions to
                           Kong. He received the B.Sc. degree with first class      her profession, the community, and the University of Missouri. She is a Fellow
                           honors in electronics and the Ph.D. degree in elec-      of the American Academy of Nursing.
                           tronic engineering, both from the Chinese University
                           of Hong Kong, Shatin, Hong Kong, in 1988 and 1991,
                           respectively.
                               He was a Research Associate in the Royal Mili-                                  Marjorie Skubic (S’90–M’91–SM’13) received the
                           tary College of Canada from 1991 to 1994. He joined                                 Ph.D. degree in computer science from Texas A&M
                           the Bell-Northern Research, Montreal, QC, Canada in                                 University, College Station, TX, USA, in 1997, where
                           1995 as a Member of scientific staff. He was a Faculty                              she specialized in distributed telerobotics and robot
                           Member in the Department of Electrical Engineering                                  programming by demonstration.
at the University of Saskatchewan, Saskatoon, Canada, from September 1996                                          In 2006, she established the Center for Eldercare
to August 1997. Since September 1997, he has been with the University of                                       and Rehabilitation Technology at the University of
Missouri, Columbia, MO, USA, and he is currently a Professor in the Elec-                                      Missouri and serves as the Center Director for this
trical and Computer Engineering Department. He was very active in the ITU                                      interdisciplinary team. The focus of the center’s work
standard developments from 1995 to 2012. He is an Inventor of 20 patents in                                    includes monitoring systems for tracking the physi-
the United States, Europe, Asia, and Canada on geolocation and signal process-                                 cal and cognitive health of elderly residents in their
ing for wireless communications. His research interests include sensor array        homes, logging sensor data in an accessible database, extracting activity and
processing, detection and estimation, source localization, wireless communica-      gait patterns, identifying changes in patterns, and generating alerts for health
tions, and the development of efficient signal processing algorithms for various    changes. She is currently a Professor in the Electrical and Computer Engineer-
applications.                                                                       ing Department at the University of Missouri, Columbia, MO, USA, with a
    Dr. Ho received the Junior Faculty Research Award and the Senior Faculty        joint appointment in computer science. In addition to her academic experience,
Research Award from the College of Engineering, University of Missouri. He          she has spent 14 years working in industry on real-time applications such as
was the Chair of the Sensor Array and Multichannel Technical Committee in           data acquisition and automation. Her current research interests include sensory
the IEEE Signal Processing Society from 2013 to 2014. He was an Associate           perception, computational intelligence, spatial referencing interfaces, human–
Editor of the IEEE TRANSACTIONS ON SIGNAL PROCESSING and the IEEE SIG-              robot interaction, and sensor networks for eldercare.
NAL PROCESSING LETTERS.




        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:32:42 UTC from IEEE Xplore. Restrictions apply.

