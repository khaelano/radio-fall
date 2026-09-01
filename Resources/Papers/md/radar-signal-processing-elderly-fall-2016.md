                                                                                                      Signal Processing for Assisted Living


       Moeness G. Amin, Yimin D. Zhang,
       Fauzia Ahmad, and K.C. (Dominic) Ho




                                                   Radar Signal Processing for Elderly Fall Detection
                                                                                                           The future for in-home monitoring




                                                            R
                                                               adar is considered an important technology for health monitoring and fall detection
                                                               in elderly assisted living due to a number of attributes not shared by other sensing
                                                               modalities. In this article, we describe the signal processing algorithms and tech-
                                                               niques involved in elderly fall detection using radar. A human’s radar signal returns
                                                                              differ in their Doppler characteristics, depending on the nature of the
                                                                                     human gross motor activities. These signals are nonstationary in
                                                                                          nature, inviting time-frequency analysis in both its linear
                                                                                              and bilinear aspects, to play a fundamental role in
                                                                                                 motion identification, including fall features deter-
                                                                                                    mination and classification. This article employs
                                                                                                      real fall data to demonstrate the success of
                                                                                                        existing detection algorithms as well as to
                                                                                                         report on some of the challenges facing tech-
                                                                                                          nology developments for fall detection.



 image licensed by ingram publishing,
## Introduction
                                                                                                                The elderly population aged 65 years or
                                                                                                                older is growing, and their ratio to the
                                                                                                                population aged 20–64 will reach 35% in

woman—© istockphoto.com/silviajansen
                                                                                                                2030 [1]. The worldwide population over
                                                                                                                65 is projected to increase to one billion in
                                                                                                               2030. An overwhelming majority of elder-
                                                                                                              lies exercise self-care within their own
                                                                                                            homes most of the time. One out of three
                                                                                                           elderly people over the age of 65 will fall every
                                                                                                        year, and the percentage rises for the elderly liv-
                                                                                                      ing in long-term care institutions. The fall can
                                                                                                    result in injuries and reduced quality of life and,
                                                                                                 unfortunately, it represents one of the leading causes of
                                                                                             death in the elderly population. Eventually, the elderly who
                                                                                        are at high risk of falling will have to move to institutionalized
                                                                                 care, which can cost approximately US$3,500 per month. Most seniors
                                                                    are unable to get up by themselves after a fall, and it was reported that, even with-
                                                            out direct injuries, half of those who experienced an extended period of lying on the floor
                                                            (more than an hour) died within six months after the incident. Therefore, prompt fall
                                                            detection saves lives, leads to timely interventions and most effective treatments, and
       Digital Object Identifier 10.1109/MSP.2015.2502784
                                                            reduces medical expenses. Furthermore, it avoids placing major burdens on the elderly’s
       Date of publication: 7 March 2016                    family. Driven by a pressing need to detect and attend to a fall, elderly fall detection has


     1053-5888/16©2016IEEE                                    IEEE Signal
        Authorized licensed use limited to: Universitas Brawijaya.        Processing
                                                                     Downloaded   onMagazine | 01,2026
                                                                                     September March 2016at |11:25:40 UTC from IEEE Xplore. Restrictions apply.   71
 become an active area of research and development and is iden-                    2) Human Factors and Behavior Science: via the understand-
 tified as a major innovation opportunity to allow seniors to live                     ing of human normal gross motor activities and those
 independently [2]. There are competing technologies for fall                          affected by medications and physically impairing illnesses.
 detection, of which wearable devices, like accelerometers and                     3) System Engineering and Engineering Design: via efficient
 “push buttons,” are most common. The shortcomings of these                            integrations of hardware and software modules to produce
 devices are that they are intrusive, easily broken, and must be                       a cost-effective, reliable, and smart system that realizes the
 worn or carried. In addition, push-button devices are less suited                     full potential of fall detection algorithms.
 for cognitively impaired users.                                                       In this article, we discuss only the first foundation, though
     Although in-home radar monitoring of the elderly for fall detec-              the other two foundations are essential for the development of
 tion is still in its early stage of development, it carries great potential       an overall system for fall monitoring. The main challenges in
 to be one of the leading technologies in the near future. The attrac-             fall detection using radar are:
 tive attributes of radar, related to its proven technology, nonobstruc-           ■■ High false-alarm rates stemming from confusion of falls
 tive illumination, nonintrusive sensing, insensitivity to lighting                    with similar motions, like sitting and kneeling
 conditions, privacy preservation, and safety, have brought electro-               ■■ Presence of scatterers caused by interior walls that create
 magnetic waves to the forefront of indoor monitoring modalities in                    clutter and ghost targets
 competition with cameras and wearable devices [3]. Radar back-                    ■■ Occlusion of the fall due to large stationary items, e.g., fil-
 scatters from humans in motion generate changes in the radar fre-                     ing cabinets
 quencies referred to as Doppler effects. The Doppler signatures                   ■■ Weak Doppler signatures stemming from orthogonality of
 determine the prominent features that underlie different human                        motion direction to the radar line-of-sight
 motions and gross motor activities. Recently, enhanced detection                  ■■ Reliability of fall detection irrespective of the immediate
 and classification techniques of radar signals associated with                        preceding motion articulations
 micro- and macromotions have been developed to identify falls                     ■■ Similar Doppler signatures of pets jumping off tables and
 from standing, sitting, kneeling, and other motion articulations [4]–                 chairs to those of a human falling
 [10]. Reference [4] explored the dynamic nature of a fall signal and              ■■ The presence of multiple persons in the radar field of view.
 used the Mel-frequency cepstral coefficients (MFCCs) in conjunc-                      Although it is important to develop superior fall detec-
 tion with machine-learning approaches to differentiate radar echo                 tion algorithms, some of the aforementioned challenges can
 behaviors between falls and nonfalls. This differentiation was                    be addressed through logistics and increased system
 achieved in [4], [6], [7], and [9] using features extracted from time-            resources. In [5], multiple Doppler sensors are exploited to
 frequency signal representations. Radar fall signals were analyzed                raise the precision of fall detection by covering the target
 using wavelet transform (WT) in [8] and [10] and features extract-                movement from multiple directions and to combat occlu-
 ed in the joint time-scale domain were used for fall classification.              sions. The fusion of data is performed by feature combina-
## A Doppler radar obtains target Doppler information by                         tion or selection. Although more complex to implement, the
 observing the phase variation of the return signal from the targets               combination method is shown to outperform the selection
 corresponding to repetitively transmitted signals. An important                   method for different fall and nonfall motion classifications.
 property of Doppler radar is its ability to effectively suppress clut-            When using multiple radars, a change in the carrier frequen-
 ter, represented by strong scatterings of the electromagnetic                     cy is recommended to avoid mutual interference. The radar
 waves from a room’s furniture, floors, ceiling, or from interior                  operational frequencies should not, in general, intervene
 walls. Radars also have the capability to separate motions of ani-                with other services, such as terrestrial TV, cellular phones,
 mate and inanimate targets, like fans and pendulums [11]. Radar                   global positioning system, and Wi-Fi, and should adhere to
 units in homes can be low cost, low power, small in size, and can                 the frequency allocations guidelines.
 be mounted on walls and ceilings in different rooms, depending                        In [4]–[6], [8], and [9], a fall is isolated from a preceding
 on operational requirements and logistic needs as well as the                     motion by prescreening that involves identifying the begin-
 required signal strength.                                                         ning and the end of a possible fall event. The fall micro-Dop-
     The role of radars in assisted living predicates on its ability to            pler features are then extracted within the identified time
 perform detection, classification, and localization. Successful                   interval. An ultrawideband range-Doppler radar with 2.5-
 detection of a fall as well as locating its occurrence to at least room           GHz bandwidth is used in [13] to provide range information
 accuracy, and classifying its type (see Figure 1) with low false                  for target localization. Range-Doppler radars are also used in
 alarm and high classification rates would provide key information                 [14] to detect physiological (heartbeat, respiration) and motion
 to first responders on the scene. On the other hand, distinguishing               parameters to identify a fallen person. Characteristics corre-
 between a fall due to a heart attack and one due to tripping can                  sponding to the detected heartbeat, respiration, and motion, or
 certainly aid in mobilizing the necessary care and treatment.                     combinations thereof, are proposed to differentiate between
     The emerging area of fall detection using radar builds on                     an animal present in the room and the fallen person. A range-
 three foundations:                                                                Doppler radar can also resolve targets and thereby permits the
 1) Information Technology: via the development of signal                          radar to handle more than one person in the field of view (e.g.,
     processing algorithms and the corresponding software for                      [15]). In this case, both the intended elderly and other
     elderly fall detection, localization, and classification.                     person(s) in the room will be monitored. When used in a


72                                                         IEEE Signal
     Authorized licensed use limited to: Universitas Brawijaya.        Processing
                                                                 Downloaded    onMagazine | 01,2026
                                                                                  September March 2016at |11:25:40 UTC from IEEE Xplore. Restrictions apply.
                                                                             (a)




                                                                              (b)


figure 1. Types of falls from (a) a heart attack and (b) tripping. (Figure used with permission of [12].)


­multiunit system, the range information localizes the target,                      In this case, the Doppler signature is the superposition of all
 through trilateration, and as such, can eliminate ghosts [5].                      component Doppler frequencies. Torso and limb motions gen-
                                                                                    erally generate time-varying Doppler frequencies, and the
Signal model                                                                        nature of this variation defines the Doppler signature associ-
Consider a monostatic continuous-wave (CW) radar that trans-                        ated with each human gross motor activity, including a fall.
mits a sinusoidal signal with frequency fc over the sensing peri-                   The exact Doppler signatures depend on the target shape and
od. The transmitted signal is expressed as s (t) = exp (j2rfc t) .                  motion patterns.
Consider a point target located at a distance of R 0 from the
radar at time t = 0, and that moves with a velocity v (t) in a                      Appropriate signal analysis domains
direction forming an angle i with the radar line-of-sight. As                       A human fall has a quick acceleration motion of short duration
such, the distance between the radar and the target at time                         at the beginning until reaching the ground and a slow decelera-
instant t is given by                                                               tion motion of long duration toward the end upon lying on the
                                                                                    floor. Such a dynamic creates a Doppler radar return that is
                   R (t) = R 0 + # v (u) cos (i) du.(1)
                                        t                                           nonstationary, as in (3). This type of nonstationary signal can
                                    0                                               be well described and analyzed by joint time-frequency repre-
                                                                                    sentations that reveal the local behavior of the signal and depict
The radar return scattered from the target can be expressed as                      its time-varying Doppler frequency signatures, thereby sup-
                                                                                    porting the radar primary tasks of detection and classification.
                                                 2R (t)                                 A number of methods are available to perform time-fre-
                 x a (t) = t exp c j2rfc c t -          mm,(2)
                                                   c                                quency analysis of the Doppler signatures [4], [6], [7], [9].
                                                                                    These methods can be generally divided into the linear time-
where t is the target reflection coefficient and c is the veloc-                    frequency analysis and quadratic time-frequency analysis
ity of the electromagnetic wave propagation in free space. The                      methods. Short-time Fourier transform (STFT) is a commonly
Doppler frequency corresponding to x a (t) is given by                              used technique to perform linear time-frequency analysis [16].
 fD (t) = 2v (t) cos (i) /m c, where m c = c/fc is the wavelength. A                Time-scale analysis using WT [17] is also considered an effec-
spatially extended target, such as a human, can be considered                       tive linear method to analyze and extract the characteristics of
as a collection of point scatterers. Therefore, the correspond-                     radar fall signals that exhibit nonstationary behaviors [8], [10].
ing radar return is the integration over the target region X                            Quadratic time-frequency distributions (QTFDs) involve
and is expressed as                                                                 the data bilinear products and are defined within Cohen’s class
                                                                                    [18]. QTFDs have been shown to be most suitable in analyzing
                           x (t) = # x a (t) da.(3)
                                    X                                               wideband signals that are instantaneously narrowband. The


                                                        IEEE Signal
  Authorized licensed use limited to: Universitas Brawijaya.        Processing
                                                               Downloaded   onMagazine | 01,2026
                                                                               September March 2016at |11:25:40 UTC from IEEE Xplore. Restrictions apply.   73
                          250                                                       250                                                                 250
                          200                                                       200                                                                 200
                          150                                                       150                                                                 150




        Frequency (Hz)                                            Frequency (Hz)                                     Frequency (Hz)   Frequency (Hz)
                          100                                                       100                                                                 100
                           50                                                        50                                                                  50
                            0                                                         0                                                                   0
                          −50                                                       −50                                                                 −50
                         −100                                                      −100                                                                −100
                         −150                                                      −150                                                                −150
                         −200                                                      −200                                                                −200
                         −250                                                      −250                                                                −250
                                0       2      4     6     8    10                        0   2      4     6     8          10                                0   2      4     6     8   10
                                            Time (seconds)                                        Time (seconds)                                                      Time (seconds)
                                                 (a)                                                   (b)                                                                 (c)


     figure 2. Time-frequency distributions of a fall motion: (a) spectrogram, (b) WVD, and (c) EMBD.


 spectrogram S (t, f) is a key member of Cohen’s class and is                                          z (i, x) exhibit low-pass filter characteristics to suppress
 obtained at time index t and frequency f by computing the                                             cross terms and preserve autoterms. For example, the Choi–
 squared magnitude of STFT of the data x (t) with a window                                             Williams distribution uses a Gaussian kernel in both frequen-
 h (t) . Other members of Cohen’s class are obtained by the                                            cy shift and time lag axes, which is expressed as
                                                                                                                               2
 two-dimensional (2-D) Fourier transform of its kerneled                                               z (i, x) = exp (- n (ix) ), where n is a constant [19]. Anoth-
 ambiguity function, expressed as                                                                      er alternative is the extended modified B-distribution
                                                                                                       (EMBD), which is a product of a Doppler-domain filter and a
                                    3       3                                                          lag-domain filter, expressed as [20]
       D (t, f) =                   / / z (i, x) A (i, x) exp ( j4rfx - j2rit),(4)
                                i =-3 x =-3                                                                                                            C (b + jri) 2 C (a + jrx) 2
                                                                                                                 z (i, x) =                                                        ,(6)
                                                                                                                                                          C 2 (b)       C 2 (a)
     where
                                                                     where - 0.5 # i # 0.5, - 0.5 # x # 0.5, 0 # a # 1, and
                       3                                              0 # b # 1. The lengths of the Doppler and lag windows are
         A (i, x) = / x (u + x) x * (u - x) exp (- j2riu)(5)       controlled by separate parameters a and b, respectively. The
                    u =-3
                                                                     extra degree of freedom in the formulation of the EMBD
                                                                     allows to independently adjust the lengths of the windows
  is the ambiguity function, z (i, x) is the time-frequency          along both lag and Doppler axes.
 ­kernel, and ($) * denotes the complex conju-                                                Figure 2 compares different time-fre-
  gate. Here, i and x, respectively, denote                                               quency representations of the Doppler signa-
  the frequency shift (also referred to as           Driven by a pressing                 ture of a human fall from standing in the
  Doppler frequency) and time lag. The               need to detect and attend form of the spectrogram, WVD, and
  properties of a QTFD are heavily depen-            to a fall, elderly fall              EMBD. A 255-point Hamming window is
  dent on the applied kernel.                        detection has become an              used for the computation of the spectrogram.
      The Wigner–Ville distribution (WVD)            active area of research              All results are depicted on a logarithm scale
  is often regarded as the basic or prototype                                             with a 25 dB dynamic range. It is clear that
                                                     and development and
  QTFD, since its filtered versions describe                                              the spectrogram provides a clean distribution
  Cohen’s class. WVD is known to provide             is identified as a major             without cross terms, but with a coarse reso-
  the best time-frequency resolution for sin-        innovation opportunity               lution. Due to signal containing multiple
  gle-component linear frequency modulat-            to allow seniors to live             irregular components as well as a strong
  ed signals, but it yields undesirable              independently.                       residual clutter, the WVD exhibits a high
  cross-terms when the signal frequency                                                   level of cross-term and sidelobe contamina-
  law is nonlinear or when a multicompo-                                                  tion, thereby rendering QTFD-based motion
  nent signal is analyzed. The kernel function of the WVD is         classification challenging. The EMBD, on the other hand, pro-
  unity across the entire ambiguity function. Various                vides better contrast and connectivity and reveals a higher level
  reduced-interference distributions (RIDs) have been devel-         of detail as compared to the spectrogram.
  oped to reduce the cross-term interference. The majority of            Similar to the STFT, the WT uses the inner products to mea-
  signals have autoterms located near the origin in the ambi-        sure the similarity between a signal and an analyzing function. In
  guity domain, while the signal cross terms are distant from        STFT, the analyzing functions are windowed complex exponen-
  the time-lag and frequency-shift axes. As such, RID kernels        tials, and the STFT coefficients represent the projection of the


74                                                           IEEE Signal
       Authorized licensed use limited to: Universitas Brawijaya.        Processing
                                                                   Downloaded    onMagazine | 01,2026
                                                                                    September March 2016at |11:25:40 UTC from IEEE Xplore. Restrictions apply.
signal over a sinusoid in an interval of a
specified length. According to the uncer-            Raw Radar           TF/Wavelet                Feature           Motion
tainty principle [18], the product of the                Data             Transform               Extraction        Classifier Fall/Nonfall
time resolution and the frequency resolu-
tion is lower bounded, i.e., we cannot
                                                                                        Event
achieve a high resolution in both the time                                            Detection
domain and the frequency domain at the
same time. Therefore, although STFT can
                                                 figure 3. Data processing blocks for fall detection.
observe the time-varying frequency signa-
tures, the question always arises as the
optimum window length for the given data for the best tradeoff             low-frequency band that excludes the clutter-dominated zero-fre-
between spectral and temporal resolutions. In the WT, the ana-             quency region but effectively captures human activities. An event
lyzing function is a wavelet. The WT implements the multireso-             is triggered for classification when the signal power in the speci-
lution concept by changing the position and scaling of the mother          fied frequency band exceeds a certain level. The coefficients of
wavelet function and thereby captures both short-duration, high-           wavelet decomposition at a given scale have also been used in
frequency components and long-duration, low-frequency compo-               the prescreening stage to identify the time locations where fall
nents [21]. There are many choices of the wavelet functions,               activities may have occurred [10].
depending on the properties imposed on the wavelets. When the
data is in discrete form, the WT can be computed very efficiently          Feature definitions
by restricting the scales to be dyadic and the positions to be inte-       For fall detection based on STFT, pertinent features include
ger. Such a fast computation uses a high-pass filter and a low-pass        extreme frequency magnitude, extreme frequency ratio, and
filter to represent the wavelet function, and successive filtering         the time span of event [9].
generates the discrete stationary WT (SWT) [22]. SWT is redun-             1) Extreme Frequency Magnitude: The extreme frequency
dant and it produces the same number of samples as the data at                 magnitude is defined as F = max ( f+ max, - f- min), where
each scale. However, it avoids the shift variant behavior that                  f+ max and f- min, respectively, denote the maximum fre-
appears in the nonredundant discrete WT.                                       quency in the positive frequency range and the minimum
     It is noted that Mel-frequency cepstrum is another repre-                 frequency in the negative frequency range. Critical falls
sentation of the short-term power spectrum for nonstationary                   often exhibit a high extreme frequency magnitude when
signals and has been used in [4] to represent the Doppler sig-                 compared to other types of observed motions.
natures. Empirical mode decomposition (EMD) has also been                  2) Extreme Frequency Ratio: The extreme frequency ratio is
used to examine human Doppler signatures [23], [24]. EMD                       defined as R = max ( f+ max /f- min , f- min /f+ max ) . For falls,
is an adaptive technique that decomposes a signal into time-                   due to the translational motion of the entire body, a high
frequency components called intrinsic mode functions                           energy spectrogram is concentrated in either the positive or
(IMFs). Each IMF comprises signal components that belong                       negative frequencies, resulting in a high extreme frequency
to a specific oscillatory time scale. The energy as a function                 ratio. On the other hand, other types of motions, such as
of the IMF index provides a unique feature vector with which                   sitting and standing, often demonstrate high energy content
human motion classification can be achieved. Furthermore,                      in both the positive and negative frequency bands because
time-frequency representations based on compressed sensing                     different body parts undergo different motion patterns,
and sparse reconstructions have been successfully employed                     thereby corresponding to a low extreme frequency ratio.
for high-resolution Doppler signature analysis and radar oper-             3) Time Span of Event: This feature describes the length of
ation with nonperiodic sub-Nyquist sampling [25], [26].                        time, in milliseconds, between the start and the end of an
                                                                               event, i.e., L = t extrm - t begin, where t extrm denotes the time
Feature extraction and classification                                          where the extreme frequency occurs and t begin denotes the
Figure 3 shows the data processing blocks for fall detection. The              initiation time of the event. The latter is determined by the
radar data is first transformed to an appropriate domain, fol-                 time when the magnitude of the frequency content of a sig-
lowed by a prescreening step that determines whether an impor-                 nal passes a specific threshold. The different motion pat-
tant event may have occurred and, if so, its time location. Once               terns being compared in this work generally show distinct
an event is detected by the prescreener, a classification process is           time spans.
initiated to detect whether such an event is a fall. More specifi-             The aforementioned three features extracted from the
cally, windowed transformed data around the identified event               spectrogram have been used for fall detection in [9]. Addi-
time location is used to extract pertinent features, which are used        tional features have also been extracted from time-frequen-
by a classifier to perform fall versus nonfall classification. A           cy distributions for classification of human activities (see,
power burst curve (also referred to as the energy burst curve),            e.g., [27], [28] and references therein). These include torso
which represents the signal power within a specific frequency              Doppler frequency, total bandwidth of the Doppler signal,
band as a function of time, can be utilized for prescreening [4],          offset of the total Doppler, normalized standard deviation
[9]. The frequency band chosen for prescreening should be a                of the Doppler signal strength, period of the limb motion,


                                                        IEEE Signal
  Authorized licensed use limited to: Universitas Brawijaya.        Processing
                                                               Downloaded   onMagazine | 01,2026
                                                                               September March 2016at |11:25:40 UTC from IEEE Xplore. Restrictions apply.   75
 shape of the spectrogram envelope, ratio                                                  depicts the ground truth of three aforemen-
 of torso echoes to other echoes in the              For fall detection based              tioned STFT-based features, i.e., the
 spectrogram, and Fourier series coeffi-             on STFT, pertinent features extreme frequency magnitude, the extreme
 cients of spectrogram envelope. Nonpara-            include extreme frequency frequency ratio, and the time span of the
 metric features derived from subspace               magnitude, extreme                    event [9]. Specifically, Figure 5(a) shows
 representations of the time-frequency dis-                                                the three-dimensional view of the three
                                                     frequency ratio, and the
 tributions have also been proposed. Effec-                                                features, whereas their pairwise 2-D plots
 tive and reliable fall detection often
                                                     time span of an event.                are respectively provided in Figure 5(b)–
 requires the combined use of multiple                                                     (d), where these features generally provide
 features. Once a set of features is extracted, a classification     a clear distinction between the fall and nonfall events, except
 algorithm can be applied to determine whether an event is a         one outlier fall event (marked with a circle). Examination of
 fall or nonfall activity.                                           the spectrogram of this outlier fall event shows that the corre-
                                                                     sponding ­signal is very weak, yielding low extreme Doppler
 Classifiers                                                         frequency as well as a short time span of event. The fall
 A variety of classifiers have been employed for fall detection      events exhibit larger extreme frequency magnitudes, higher
 [4], [27], with the support vector machine (SVM) being the          extreme frequency ratios, and longer lengths of event time
 most commonly used classifier. Different classifiers, includ-       than the nonfall counterparts. These features, however, do not
 ing k-nearest neighbor, are used to automatically distinguish       robustly classify the fall and nonfall activities based on a sin-
 falling from activities, such as walking and bending down [4].      gle feature alone.
 The sparse Bayesian learning method based on the relevance              The SVM classifier is applied by using a Gaussian kernel.
 vector machine improves fall detection performance over the         Fivefold cross-validation is used on the motion data. The
 SVM with fewer relevance vectors, and its effectiveness is          entire sample set is randomly partitioned into five equal-size
 demonstrated in [9]. Hidden Markov model-based machine              subsets. Out of the five subsets, a single subset is retained as
 learning is used in [6] to characterize the signal spectrogram      the validation data for testing the classifier, and the remaining
 for fall detection. However, the choice of employed features        four subsets are used as the training data. The cross-validation
 has been determined to have a greater impact on the classifi-       process is repeated five times, with each of the five subsets
 cation performance than the specific classifier applied (see        used exactly once as the validation data. The classifier is suc-
 [28] and references therein).                                       cessfully able to detect fall from nonfall events except for the
                                                                     misclassification of the outlier fall event as described earlier
 Classification results                                              and marked with the circle in Figure 5(a).
 A CW radar was set up in the Radar Imaging Lab at
 Villanova University, Pennsylvania. A vertically polarized          Wavelet-based approach
 horn antenna (BAE Systems, Model H-1479) with an oper-
 ational frequency range of 1–12.4 GHz and 3-dB beam-                Feature Definition
 width of 45° was used as a transceiver for the CW radar.            WT-based features include the smoothed magnitude square of
 The feed point of the antenna was positioned 1 m above              the discrete SWT coefficients of the radar signal at several
 the floor. Agilent’s E5071B RF network analyzer was used            dyadic scales over a moving window (frame) typically of
 for signal generation and measurement of radar returns. A           0.5 seconds with 50% overlap [10]. The collection of features
 carrier frequency of 8 GHz was employed and the network             in 2.5 seconds centered at the event location identified by a
 analyzer was externally triggered at a 1 kHz sampling rate.         prescreener forms the feature vector for classification. The
 Data were collected for eight different motion patterns             smoothed magnitude square of the SWT coefficients is
 using two test subjects, with each experiment motion pat-           defined next. 
 tern repeated ten times (five times each for two test sub-
 jects). Considered motion patterns include 1) forward               Smoothed Magnitude Square of the SWT Coefficients
 falling, 2) backward falling, 3) sitting and standing, and          Let pu i (k) be the sum of the square of the SWT coefficients at
 4) bending over and standing up. Two different variations           dyadic scale 2 i in frame k. There will be nine frames in a
 of each motion pattern were measured, one being a stan-             total of 2.5 seconds that contain a possible fall event. Normal-
 dard type of motion, whereas the other demonstrating a              ization of pu i (k) by the sum of the nine values is often needed,
 high-energy form of the same motion to study the impact             giving p i (k) . The collection of the nine p i (k) s forms the row
 of such variations on the classification performance. The           vector p i . Over the dyadic scales 2 i b to 2 i e, the feature vector
 recording time for each experiment was 20 seconds [9].              for classification is y = [ p i bgp i e ] .
     The typical spectrograms of the eight considered motion             The study in [4] applied cepstral analysis of the radar signal
 patterns are shown in Figure 4. The first four patterns are col-    for fall detection. The MFCCs were extracted over a 4-second
 lectively considered falls, whereas the last four patterns are      data segment that might contain a fall activity and encourag-
 collectively considered nonfall motions. Our objective is to        ing classification results between falls and nonfalls were
 correctly detect fall events from nonfall events. Figure 5          observed.


76                                                         IEEE Signal
     Authorized licensed use limited to: Universitas Brawijaya.        Processing
                                                                 Downloaded    onMagazine | 01,2026
                                                                                  September March 2016at |11:25:40 UTC from IEEE Xplore. Restrictions apply.
                              200                                           –20                       200

                                                                            –30
                              100                                                                     100




            Frequency (Hz)                                                          Frequency (Hz)
                                                                            –40
                                0                                                                      0
                                                                            –50

                             –100                                                                    –100
                                                                            –60

                             –200                                           –70                      –200
                                    0   5        10        15       20                                      0   5         10       15        20
                                            Time (seconds)                                                          Time (seconds)
                                                  (a)                                                                     (b)

                              200                                                                     200


                              100                                                                     100




            Frequency (Hz)                                                          Frequency (Hz)
                                0                                                                      0


                             –100                                                                    –100


                             –200                                                                    –200
                                    0   5        10        15       20                                      0   5         10       15        20
                                            Time (seconds)                                                          Time (seconds)
                                                  (c)                                                                     (d)

                              200                                                                     200


                              100                                                                     100




            Frequency (Hz)                                                          Frequency (Hz)
                                0                                                                      0


                             –100                                                                    –100


                             –200                                                                    –200
                                    0   5        10        15       20                                      0   5         10       15        20
                                            Time (seconds)                                                          Time (seconds)
                                                  (e)                                                                     (f)

                              200                                                                     200


                              100                                                                     100




            Frequency (Hz)                                                          Frequency (Hz)
                                0                                                                      0


                             –100                                                                    –100


                             –200                                                                    –200
                                    0   5        10        15       20                                      0   5         10       15        20
                                            Time (seconds)                                                          Time (seconds)
                                                  (g)                                                                     (h)


figure 4. Spectrograms of typical motion profiles [9]. (a) Fall backward. (b) Fall backward with arm motion. (c) Fall forward. (d) Fall forward with arm
motion. (e) Sit and stand. (f) Fast sit and stand. (g) Bend and stand up. (h) Fast bend and stand up. (Figure reproduced with permission of the Institution
of Engineering and Technology.)


                                                        IEEE Signal
  Authorized licensed use limited to: Universitas Brawijaya.        Processing
                                                               Downloaded   onMagazine | 01,2026
                                                                               September March 2016at |11:25:40 UTC from IEEE Xplore. Restrictions apply.     77
                                                                                                                                                                             12




             Frequency Magnitude (Hz)
                                               250
                                               200                                                                                                                           10




## Frequency Ratio
                                               150                                                                                                                            8
## 100                              Fall    Not Fall                                                                              6
                                                           50
                                                                                                                                                                              4
                                                                    0
                                                                   15                                                                                                         2
                                                                                10                                                   3                                                                Fall    Not Fall
                                                                                                                          2                                                   0
                                                                                         5                      1
               Frequency Ratio                                                                                                                                                    0   0.5      1      1.5     2          2.5
                                                                                               0     0                                                                                  Lasting Time (seconds)
                                                                                                         Lasting Time (seconds)
                                                                                                   (a)                                                                                            (b)
                                                                   250                                                                                                  250




                                        Frequency Magnitude (Hz)                                                                             Frequency Magnitude (Hz)
                                                                   200                                                                                                  200

                                                                   150                                                                                                  150

                                                                   100                                                                                                  100

                                                                    50                                                                                                       50
                                                                                                         Fall       Not Fall                                                                           Fall   Not Fall
                                                                        0                                                                                                     0
                                                                            0          0.5      1      1.5      2              2.5                                                0            5                  10
                                                                                         Lasting Time (seconds)                                                                            Frequency Ratio
                                                                                                   (c)                                                                                           (d)


 figure 5. Ground truth of motions with 3-D vision and three 2-D visions [9]. (Figure reproduced with permission of the Institution of Engineering and Technology.)


 Classification Results                                                                                                                  sification. The data was acquired in a continuous manner as
 Wavelet-based fall detection results are presented using real data                                                                      in practice. A prescreener based on the SWT coefficient val-
 collected in three different bathrooms of senior residence apart-                                                                       ues at scale equal to four gives the potential falls locations for
 ments [29]. A bathroom is where falls of elderly people could                                                                           feature extraction and classification. Figure 6 examines the
 occur often and yet other sensors, such as video cameras or                                                                             classification performance using the SWT and the MFCC fea-
 acoustic sensors, are not suitable due to privacy reasons or strong                                                                     tures, using leave-one-out cross-validation between training
 interferences. The data collection was performed from January                                                                           and testing. The false-alarm rate is the number of false alarms
 to May 2013, where the Doppler radars were mounted above in                                                                             normalized by the total number of events from the prescreen-
 the attic at the middle of the bathrooms. The data set contains                                                                         er. The WT classifier has comparable performance with the
 19 different kinds of falls and 14 various typical nonfalls that                                                                        MFCC classifier for detection rate below 80% and has much
 were performed by a professionally trained female stunt actor                                                                           better results otherwise. At a 100% detection rate, the WT
 [10]. The fall types and their counts are tabulated in Table 1.                                                                         classifier reduces the amount of false alarms by more than a
     The radar used in the experiment is a commercially avail-                                                                           factor of four from the prescreener.
 able pulse-Doppler range control radar with a price close to
 that of a webcam. The pulse repetition rate is 10 MHz, the                                                                              Open issues and problems
 duty cycle is 40%, and the center frequency is 5.8 GHz.                                                                                 There are many challenges still facing the radar-based fall
 The sampling frequency of the radar signal is 960 Hz.                                                                                   detection technology. Classifying a fall, once the corresponding
 Based on the velocity range during a human fall, dyadic                                                                                 event time interval is identified, has been the subject of most
 scales from two to 64 are used to generate the features, giving                                                                         work in this area. However, identifying such an interval is still
 the feature vector length of 6 (scales) # 9 (frames) = 54. The                                                                          an open question, specifically when a fall is preceded by a high-
 wavelet function for SWT is the reverse biorthogonal 3.3                                                                                Doppler gross motor activity. For example, experiments have
 wavelet. The window function is Hamming. The classifier is                                                                              shown that progressive fall from a rapid walk is not easy to
 the k -nearest neighbor with k = 1 for fall versus nonfall clas-                                                                        reveal. Fast sitting and slow falling can also be confused


78                                                         IEEE Signal
     Authorized licensed use limited to: Universitas Brawijaya.        Processing
                                                                 Downloaded    onMagazine | 01,2026
                                                                                  September March 2016at |11:25:40 UTC from IEEE Xplore. Restrictions apply.
without the effective use of range information. Optimal sensor
placement is also an open problem, as the Doppler frequency of                                          1
a radar return is proportional to the target motion along the                                          0.9
radar along the line-of-sight.Placing the radar several feet above                                     0.8
the ground can provide clear signals for gait and fall analysis.                                       0.7




## Detection Rate
On the other hand, the fall detection performance may not be as
                                                                                                       0.6
good as when it is mounted in the ceiling due to weaker relative
                                                                                                       0.5
motion that affects the features characterization [30]. Finally,
radar fall detection would emerge to be elderly specific. In this                                      0.4
respect, it would require 1) tuning the fall detection algorithms                                      0.3
                                                                                                                                   WT Classifier
to the elderly physical impairments and any awareness of the                                           0.2                         MFCC Classifier
use of walking aid devices, and 2) making the system dynamic                                           0.1                         Prescreener
by unsupervised or supervised learning, which can occur by                                              0
observing the elderly over an extended period of time.                                                       0   0.2     0.4      0.6     0.8         1
                                                                                                                       False-Alarm Rate
    There are limitations of using Doppler radar for fall detec-
tion. In fact, it is not straightforward for a Doppler radar to
distinguish between a human fall and a pet jumping. Other                        figure 6. Classification performance of WT features.
normal activities, such as sitting on a chair, could also present
challenges to a Doppler radar fall detection system. On the                      lives, minimize injury, and reduce the anxiety of the elderly
other hand, a pet is smaller in size than a human and sitting                    who live alone. Effective use of radar technology for elderly
down does not exhibit the full dynamics of a fall. It is antici-                 fall detection relies on the signal processing techniques for
pated that, by extracting the reliable features and designing a                  Doppler signature analysis and motion classifications. In this
proper classifier, some of these false alarms could be elimi-                    article, we presented an overview of the the main approaches
nated. The use of Doppler radar for fall detection is still in its               for revealing pertinent features in the joint-variable time-fre-
infancy and there are many open issues that need to be                           quency domain. More specifically, time-frequency analysis in
addressed and further investigated.                                              both its linear and bilinear aspects, including WT, was shown
                                                                                 to play a fundamental role in fall features determination and
Conclusions                                                                      human motion classification. The success of feature-based fall
Automatic real-time detection of falls may enable the first                      detection schemes was demonstrated using real data experi-
responders to provide rapid medical assistance, and, thus, save                  ments and challenges facing technology development for fall
                                                                                 detection were also discussed. Further developments in this
                                                                                 area toward commercialization call for having a large reposi-
 Table 1. A description of fall types.
                                                                                 tory of fall data, both real and kinematically modeled, that will
Fall Type                                                           Count        provide the means for understanding the nominal features of
Loose balance-forward                                               11           fall motions, and also for proper training and performance
Loose balance-backward                                              9            comparison of the different algorithms.
Loose balance-left                                                  8
                                                                                 Authors
Loose balance-right                                                 10
                                                                                 Moeness G. Amin (moeness.amin@villanova.edu) received his
Loss of consciousness-forward                                       3
                                                                                 Ph.D. degree in 1984 from the University of Colorado, Boulder.
Loss of consciousness-backward                                      3            He has been on the faculty of the Department of Electrical and
Loss of consciousness-left                                          2            Computer Engineering at Villanova University, Pennsylvania,
Loss of consciousness-right                                         3            since 1985, where he is now a professor and the director of the
Loss of consciousness-straight down                                 3            Center for Advanced Communications. He is a recipient of the
Trip and fall-forward                                               1            2015 IEEE Warren D. White Award for Excellence in Radar
                                                                                 Engineering, the 2014 IEEE Signal Processing Society
Trip and fall-sideways                                              2
                                                                                 Technical Achievement Award, the 2009 EURASIP Individual
Slip and fall-forward                                               4
                                                                                 Technical Achievement Award, and the IEEE Third Millennium
Slip and fall-sideways                                              5            Medal. He was a Distinguished Lecturer of the IEEE Signal
Slip and fall-backward                                              4            Processing Society during 2003–2004. He has authored more
Reach-fall (chair)-forward                                          2            than 700 journal and conference publications in the broad area
Reach-fall (chair)-left                                             1            of theory and applications of signal and array processing, includ-
Reach-fall (chair)-right                                            2            ing radar. He is a Fellow of the IEEE, EURASIP, SPIE, and IET.
Reach-fall (chair)-sliding forward                                  4
                                                                                     Yimin D. Zhang (ydzhang@temple.edu) received his Ph.D.
Reach-fall (chair)-sliding backward                                 5
                                                                                 degree from the University of Tsukuba, Japan, in 1988. He is cur-
                                                                                 rently an associate professor in the Department of Electrical and


                                                         IEEE Signal
   Authorized licensed use limited to: Universitas Brawijaya.        Processing
                                                                Downloaded   onMagazine | 01,2026
                                                                                September March 2016at |11:25:40 UTC from IEEE Xplore. Restrictions apply.   79
 Computer Engineering, Temple University, Philadelphia,                                                                tures,” in Proc. IEEE Int. Conf. Healthcare Informatics, Philadelphia, PA, Sept.
                                                                                                                       2013, pp. 169 –174.
 Pennsylvania. He has authored more than 270 publications in the
                                                                                                                       [7] F. Wang, M. Skubic, M. Rantz, and P. E. Cuddihy, “Quantitative gait measure-
 area of array signal processing, time-frequency analysis, com-                                                        ment with pulse-Doppler radar for passive in-home gait assessment,” IEEE Trans.
 pressive sensing, and optimization with applications in radar,                                                        Biomed. Eng., vol. 61, no. 9, pp. 2434 –2443, Sept. 2014.

 communications, and navigation. He is an associate editor of                                                          [8] A. Gadde, M. G. Amin, Y. D. Zhang, and F. Ahmad, “Fall detection and clas-
                                                                                                                       sification based on time-scale radar signal characteristics ,” in Proc. SPIE ,
 IEEE Transactions on Signal Processing and serves on the edito-                                                       Baltimore, MD, May 2014, vol. 9077, no. 907712, pp. 1–9.
 rial board of the journal Signal Processing. He was an associate                                                      [9] Q. Wu, Y. D. Zhang, W. Tao, and M. G. Amin, “Radar-based fall detection
                                                                                                                       based on Doppler time-frequency signatures for assisted living,” IET Radar Sonar
 editor of IEEE Signal Processing Letters during 2006–2010. He                                                         Navig., vol. 9, no. 2, pp. 164–172, Feb. 2015.
 is a member of the Sensor Array and Multichannel Technical                                                            [10] B. Y. Su, K. C. Ho, M. J. Rantz, and M. Skubic, “Doppler radar fall activity
 Committee of the IEEE Signal Processing Society. He is a Senior                                                       detection using the wavelet transform,” IEEE Trans. Biomed. Eng., vol. 62, no. 3,
                                                                                                                       pp. 865–875, Mar. 2015.
 Member of the IEEE and SPIE.
                                                                                                                       [11] P. Setlur, M. G. Amin, F. Ahmad, and P. D. Zemany, “Experiments on
     Fauzia Ahmad (fauzia.ahmad@villanova.edu) received her                                                            through-the-wall motion detection and ranging,” in Proc. SPIE, Orlando, FL, Apr.
 Ph.D. degree in electrical engineering from the University of                                                         2007, vol. 6538, no. 653809, pp. 1–10.

 Pennsylvania, Philadelphia, in 1997. Since 2002, she has been                                                         [12] Detecting falling people. [Online]. Available: http://muscle.ercim.eu/content/
                                                                                                                       view/35/43/
 with the Center for Advanced Communications, Villanova                                                                [13] J. Sachs and R. Herrmann, “M-sequence based ultra-wideband sensor network
 University, Pennsylvania, where she is now a research professor                                                       for vitality monitoring of elders at home,” IET Radar Sonar and Navig., vol. 9, no.
                                                                                                                       2, pp. 125–137, Feb. 2015.
 and the director of the Radar Imaging Lab. She has authored
                                                                                                                       [14] P. E. Cuddihy, J, M. Ashe, C.N. Bufi, and S. Genc, “Radar based systems
 more than 170 publications in the areas of radar imaging, radar                                                       and methods for detecting a fallen person,” U.S. Patent 8742935 B2, June 3,
 signal processing, compressive sensing, and array signal process-                                                     2014.
 ing. She serves on the editorial boards of IEEE Transactions on                                                       [15] Z. A. Cammenga, G. E. Smith, and C. J. Baker, “Combined high range resolu-
                                                                                                                       tion and micro-Doppler analysis of human gait,” in Proc. IEEE Int. Radar Conf.,
 Signal Processing, IEEE Geoscience and Remote Sensing                                                                 Arlington, VA, May 2015, pp. 1038–1043.
 Letters, IET Radar, Sonar, & Navigation Journal, and SPIE/IS&T                                                        [16] L. B. Almeida, “The fractional Fourier transform and time-frequency repre-
 Journal of Electronic Imaging. She is a member of the Radar                                                           sentations,” IEEE Trans. Signal Processing, vol. 42, no. 11, pp. 308–3091, 1994.
                                                                                                                       [17] S. Mallat , A Wavelet Tour of Signal Processing, 3rd ed. New York:
 Systems Panel of the IEEE Aerospace and Electronic Systems                                                            Academic, 2009.
 Society and a member of the Sensor Array and Multichannel                                                             [18] L. Cohen, Time-Frequency Analysis. Englewood Cliffs, NJ: Prentice Hall,
 Technical Committee of the IEEE Signal Processing Society. She                                                        1995.
 is a Senior Member of the IEEE and SPIE.                                                                              [19] H. Choi and W. J. Williams, “Improved time-frequency representation of multi-
                                                                                                                       component signals using exponential kernels,” IEEE Trans. Acoustics Speech
     K.C. (Dominic) Ho (hod@missouri.edu) received his                                                                 Signal Processing, vol. 37, no. 6, pp. 862–871, June 1989.
 Ph.D. degree in electronic engineering from the Chinese                                                               [20] B. Boashash and T. Ben-Jabeur, “Design of a high-resolution separable-ker-
 University of Hong Kong, in 1991. Since September 1997, he                                                            nel quadratic TFD for improving newborn health outcomes using fetal movement
                                                                                                                       detection,” in Proc. Int. Conf. Information Science, Signal Processing and Their
 has been with the University of Missouri, Columbia, where he                                                          Applications, Montreal, Canada, 2012, pp. 354–359.
 is currently a professor in the Electrical and Computer                                                               [21] S. Qian, Introduction to Time-Frequency and Wavelet Transforms.
                                                                                                                       Englewood Cliffs, NJ: Prentice Hall, 2001.
 Engineering Department. His research interests include sensor
                                                                                                                       [22] G. P. Nason and B. W. Silverman, “The stationary wavelet transform and some
 array processing; elder care; source localization, detection,                                                         statistical applications,” Lect. Notes Stat., vol. 103, pp. 281–299, 1995. [23] D. P.
 and estimation; wireless communications; and the develop-                                                             Fairchild and R. M. Narayanan, “Classification of human motions using empirical
                                                                                                                       mode decomposition of human micro-Doppler signatures,” IET Radar Sonar
 ment of efficient signal processing algorithms for various                                                            Navig., vol. 8, no. 5, pp. 425–434, 2014.
 applications. He served as the chair of the Sensor Array and                                                          [24] I. Mostafanezhad, O. Boric-Lubecke, V. Lubecke, and D. P. Mandic,
 Multichannel Technical Committee of the IEEE Signal                                                                   “Application of empirical mode decomposition in removing fidgeting interference in
                                                                                                                       Doppler radar life signs monitoring devices,” in Proc. 31st Annu. Int. Conf. IEEE
 Processing Society during 2013–2014. He was an associate                                                              Engineering in Medicine and Biology Society, Minneapolis, MN, Sept. 2009, pp.
 editor of IEEE Transactions on Signal Processing from 2003                                                            340–343.

 to 2006 and from 2009 to 2013 and IEEE Signal Processing                                                              [25] B. Jokanovic, M. G. Amin, Y. D. Zhang, and F. Ahmad, “Multi-window
                                                                                                                       time-frequency signature reconstruction from undersampled continuous wave radar
 Letters from 2004 to 2008. He is a Fellow of the IEEE.                                                                measurements for fall detection,” IET Radar Sonar Navig., vol. 9, no. 2, pp. 173–
                                                                                                                       183, Feb. 2015.
                                                                                                                       [26] M. G. Amin, B. Jakonovic, Y. D. Zhang, and F. Ahmad, “A sparsity-per-
 References                                                                                                            spective to quadratic time-frequency distributions,” Digit. Signal Processing, vol.
                                                                                                                       46, pp. 175–190, Nov. 2015.
 [1] United Nations, Department of Economic and Social Affairs, Population
 Division. (2011). World population prospects: The 2010 revision. [Online].                                            [27] Y. Kim and H. Ling, “Human activity classification based on micro-Doppler sig-
 Available: http://www.esa.un.org/wpp/                                                                                 natures using a support vector machine,” IEEE Trans. Geosci. Remote Sens., vol. 47,
                                                                                                                       no. 5, pp. 1328–1337, 2009.
 [2] AARP. Health Innovation Frontiers: Untapped Market Opportunities for
 t h e 5 0 + . [ O n l i n e ] . Ava i l a b l e : h t t p : / / h e a l t h 5 0 . o rg / fi l e s / 2 0 1 3 / 0 5 /   [28] S. Z. Gurbuz, B. Tekeli, M. Yuksel, C. Karabacak, A. C. Gurbuz, and M. B.
 AARPHealthInnovationFullReportFINAL.pdf                                                                               Guldogan, “Importance ranking of features for human micro-Doppler classification
                                                                                                                       with a radar network,” in Proc. 16th Int. Conf. Information Fusion, Istanbul,
 [3] M. G. Amin, Ed., Through the Wall Radar Imaging. Boca Raton, FL: CRC Press, 2011.                                 Turkey, July 2013, pp. 610 – 616.
 [4] L. Liu, M. Popescu, M. Skubic, M. Rantz, T. Yardibi, and P. Cuddihy, “Automatic                                   [29] TigerPlace: An assisted living facility in Columbia, MO, USA. [Online].
 fall detection based on Doppler radar motion,” in Proc. 5th Int. Conf. Pervasive                                      Available: http://www.eldertech.missouri.edu/
 Computing Technologies for Healthcare, Dublin, Ireland, May 2011, pp. 222–225.
                                                                                                                       [30] L. Liu, M. Popescu, K. C. Ho, M. Skubic, and M. Rantz, “Doppler radar sen-
 [5] S. Tomii and T. Ohtsuki, “Falling detection using multiple Doppler sensors,” in                                   sor positioning in a fall detection system,” in Proc. Int. Conf. IEEE Engineering in
 Proc. IEEE Int. Conf. e-Health Networking, Applications and Services, Beijing,                                        Medicine and Biology Society, San Diego, CA, Aug. 2012, pp. 256–259.
 China, Oct. 2012, pp. 196 –201.
 [6] M. Wu, X. Dai, Y. D. Zhang, B. Davidson, J. Zhang, and M. G. Amin,
                                                                                                                                                                                                       SP
 “Fall detection based on sequential modeling of radar signal time-frequency fea-


80                                                         IEEE Signal
     Authorized licensed use limited to: Universitas Brawijaya.        Processing
                                                                 Downloaded    onMagazine | 01,2026
                                                                                  September March 2016at |11:25:40 UTC from IEEE Xplore. Restrictions apply.

