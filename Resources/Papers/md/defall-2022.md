                                                                                                                                              1




         DeFall: Environment-Independent Passive Fall
                     Detection using WiFi
 Yuqian Hu, Graduate Student Member, IEEE, Feng Zhang, Member, IEEE, Chenshu Wu, Senior Member, IEEE,
                    Beibei Wang, Senior Member, IEEE, and K. J. Ray Liu, Fellow, IEEE



   Abstract—Fall is recognized as one of the most frequent                    a real-time indoor fall detection system with timely and
accidents among elderly people. Many solutions, either wear-                  automatic alarms is highly in need, which could potentially
able or non-contact, have been proposed for fall detection                    save lives by requesting external help timely.
recently. Among them, WiFi-based non-contact approaches are
gaining popularity due to the ubiquity and non-invasiveness.                     The great importance of fall detection has driven the de-
The existing works, however, usually rely on labor-intensive                  velopment of various systems, which can be roughly divided
and time-consuming training before it can achieve a reasonable                into two categories: wearable and non-contact systems. The
performance. In addition, the trained models often contain                    wearable techniques require users to wear special devices,
environment-specific information and thus cannot be generalized               including ECG sensors, barometric sensors, accelerometers,
well for new environments. In this paper, we propose DeFall, a
WiFi-based passive fall detection system that is independent of               gyroscopes, and smartphones, etc., to track the motion of
the environment and free of prior training in new environments.               their bodies [2]–[6]. However, in addition to the potential false
Unlike previous works, our key insight is to probe the physio-                alarms of wearable systems, it is cumbersome and sometimes
logical features inherently associated with human falls, i.e., the            impractical to ask users especially the elder people to carry
distinctive patterns of speed and acceleration during a fall. DeFall          specialized sensors [7], which encourages the development of
consists of an offline template-generating stage and an online
decision-making stage, both taking the speed estimates as input.              non-contact systems. The most common non-contact systems
In the offline stage, augmented dynamic time warping (DTW)                    are vision-based [8]–[13]. Typically, an array of cameras,
algorithms are performed to generate a representative template                infrared sensors, or depth cameras like Kinect need to be
of the speed and acceleration patterns for a typical human fall.              deployed to monitor an area of interest. While high accuracy
In the online phase, we compare the patterns of the real-time                 could be achieved under favored settings of good lighting
speed/acceleration estimates against the template to detect falls.
To evaluate the performance of DeFall, we built a prototype                   condition and clear field of view, vision-based systems are
using commercial WiFi devices and conducted experiments under                 limited by the visibility requirement and also bring privacy
different settings. The results demonstrate that DeFall achieves              concerns, especially in some specific environments such as
a detection rate above 95% with a false alarm lower than 1.50%                the bathrooms and bedrooms.
under both line-of-sight (LOS) and non-LOS (NLOS) scenarios                      Inspired by the fact that the radio frequency (RF) signals
with one single pair of transceivers. Extensive comparison study
verifies that DeFall can be generalized well to new environments              can be altered by the propagation environment [14] [15], the
without any new training.                                                     concept of wireless sensing presents the opportunities of sens-
                                                                              ing human activities passively and many wireless technologies,
 Index Terms—Fall detection system, channel state information,
WiFi sensing, speed estimation                                                such as Doppler radar and WiFi signals have been explored
                                                                              [16]–[23] to detect falls. However, the existing RF-based
                                                                              approaches either have limited coverage or require re-training
                         I. I NTRODUCTION                                     in new environments, which is impractical in commercial
   As the population ages worldwide, our society should take                  indoor fall detection systems. We compare different types of
more and more arduous responsibilities to provide medical                     RF-based systems in detail in Section II.
care for the elderly. Among all of the accidents in the elderly,                 To address this issue, in this work we propose DeFall, a
falls represent the most frequent ones. The report from the                   WiFi-based robust and environment-independent fall detection
World Health Organization (WHO) indicates that 20% - 30%                      system. The key insight that sets apart DeFall from prior
of older people who fall suffer moderate to severe injuries [1].              works is the exploitation of the physiological patterns of
Falls can even cause death. In all regions of the world, death                body speed and accelerations, rather than less explainable
rates caused by falls are the highest among adults over the age               data-driven features used previously. Noticing that human
of 60 years [1].                                                              falls experience different speed/acceleration from other daily
   Moreover, the damage caused by the falls is not only                       activities, we propose to utilize the unique patterns of speed
reflected in the immediate injury of the body, but also in                    and acceleration to recognize falls. Recent work [24] has
all subsequent adverse effects caused by the lack of timely                   shown the feasibility to extract speed information passively
assistance, especially for those who live alone. Therefore,                   from WiFi signals even in non-line-of-sight (NLOS) envi-
                                                                              ronments, which allows us to build DeFall upon the WiFi-
  Y. Hu, F. Zhang, C. Wu, B. Wang, and K. J. R. Liu are with the Department   based speed estimation. Since a fall involves a unique pattern
of Electrical and Computer Engineering, University of Maryland, College
Park, MD, 20742, and the Origin Wireless Inc., Greenbelt, MD, 20770           of speed transition and lasts a certain duration, DeFall uses
  E-mail: {yhu1109, fzhang15, cswu, bebewang, kjrliu}@umd.edu.                the time series of speed/acceleration captured continuously
                                                                                                                                      2



instead of the instantaneous values for identifying fall events.     of wireless IoT applications emerging, including fall detection
This can tremendously reduce the unwanted false alarm in a           systems. In this section, we review the literature on indoor
real environment. However, as we deal with time series, the          activity recognition, with particular interests in fall detection.
temporal variability in time series brings up another challenge.     Existing works on passive wireless sensing can be categorized
To adapt to the non-linear compression or stretching over time,      into different groups based on the features extracted from the
we apply the augmented dynamic time warping (DTW) based              wireless channel as Table I shows: radar-based, RSSI-based
algorithms for the time series processing.                           and CSI-based systems.
   DeFall consists of two key components: the offline template-         Radar-based systems detect events relying on specialized
generating stage and the online decision-making stage. In the        devices that are not readily available in homes. Many of them
offline stage, a representative template for speed and accelera-     infer the motion of the reflector by evaluating the Doppler
tion series is generated. After that, the similarity between real-   frequency shift and extract micro-Doppler signatures for rec-
time speed/acceleration series and the template is evaluated in      ognizing finer body movements, such as activity monitoring
the online stage to detect a fall.                                   [25], [26], gesture recognition [37], and fall detectors [16],
   Since the speed and acceleration are inherent properties of       [17]. Millimeter-wave (mmWave) radars, operating at higher
the human motion that are independent of the static back-            transmit frequencies than commercial WiFi, provide better
ground environment, DeFall needs only one-time light training        velocity resolution and capture more details on motion of
and is robust against different environments in an unsupervised      different body parts [27], [38], [39]. Also, Ultra-wideband
manner. Also, thanks to the rich-scattering model used in speed      (UWB) radar, which has a high resolution due to the wide
estimation, the system can work very well under both line-of-        bandwidth, has also been proposed to classify indoor ac-
sight (LOS) and NLOS scenarios.                                      tivities and detect falls [18], [19]. [18] proposes a time of
   To evaluate the performance of DeFall, extensive experi-          arrival (TOA)-based feature extraction approach based on the
ments have been conducted in a typical indoor environment            received UWB signals. [19] approaches UWB-radar-based
in various settings. We first use a human-like dummy with a          fall detection by applying a convolutional long short term
similar size and weight to a real human to carry out more            memory (ConvLSTM) structure. [40] combines CNN and state
than 800 fall experiments under LOS and NLOS to verify the           machine and adopts a large-scale dataset to detect falls in
feasibility and calculate the detection rate (DR). We also test      various environments. However, although radars may have
the false alarm rate (FAR) while the real human performs daily       higher ranges or frequency resolutions, they usually require
indoor activities including walking and sitting. Furthermore,        LOS for reliable operation. Therefore they can only detect
more real human fall samples are applied to validate the             falls in a very limited coverage and are also limited by the
effectiveness of the proposed system. The experimental results       requirement of extra specialized dedicated devices. Further, the
show that DeFall can achieve a DR larger than 95% on real            speed estimation derived from Doppler shift by radars varies
falls with an FAR of 1.47%, outperforming existing solutions         for different moving directions and the heading direction of
in terms of both accuracy and robustness. The contributions          the subject is usually predefined [41].
of this work are summarized as follows:                                 Some other works on activity recognition and fall detection
   • To the best of our knowledge, the proposed system is the        use commodity devices. Commercial wireless devices, such
      first device-free fall detector that leverages the accurate    as WiFi infrastructures, are available in most indoor spaces
      time series of speed and acceleration estimated from WiFi      and allow more flexible low-cost deployment. Chetty et al.
      channel state information (CSI).                               apply passive WiFi radar (PWR) to realize the through-the-
   • The proposed system works well in both LOS and NLOS             wall human sensing [35] and overcome the coverage limitation
      scenarios, getting rid of the limitation of coverage while     of traditional radars. However, PWR, which also relies on the
      also protecting privacy.                                       principle of radars, collects Doppler information and therefore
   • Through long-term testing, the system is verified to be         is also direction/location dependent and requires directional
      robust against other daily activities as well as the falling   antennas [36].
      of objects while keeping a high detection rate on real            Another widely-used method is using the received signal
      falls.                                                         strength indicator (RSSI) to characterize indoor activities,
   • Based on the performance comparison with other existing         either on WiFi or other wireless devices. For example, [28]
      methods, our system can work independently without any         explores WiFi ambient signals for RSSI fingerprints of dif-
      re-training in a changing environment.                         ferent activities. However, since RSSI measures the overall
   The rest of the paper is organized as follows. Section II         amplitude response of multiple superposed subcarriers, it loses
reviews related works. Section III presents the basic principles     the phase information as well as the detailed information of
of DeFall. Section IV depicts the system design and imple-           each frequency component. Therefore it suffers from dramatic
mentation. The performance of the proposed system is studied         performance degradation in complex situations due to multi-
and evaluated in Section V and Section VI. Lastly, concluding        path fading and temporal dynamics [42], limiting its stability
remarks are given in Section VII.                                    and reliability in practical applications.
                                                                        CSI, which measures both amplitude and phase information
                     II. R ELATED W ORK                              on different frequency components, provides finer-grained in-
   Thanks to the rapid development of Internet of Things (IoT)       formation for a propagation environment and becomes popular
technologies and wireless sensing research, there are plenty         in the field of wireless sensing recently. Different from the
                                                                                                                                        3




Methodology                  Existing works                                       Limitations
                                                                                  Limited detection range
                             Indoor activity recognition [25]–[27]                Cannot be integrated with commercial WiFi
Radar-based
                             Fall detection [16]–[19]                             Specialized device required
                                                                                  Doppler signature affected by moving direction
                                                                                  Coarse granularity
                             Indoor activity recognition [28], [29]
RSSI-based                                                                        High sensitivity to environmental changes
                             Fall detection [30]
                                                                                  Multiple devices required
                             Indoor activity recognition [31]–[33]                Re-training required in new environments
CSI-based
                             Fall detection [20]–[23]                             Performance degrades with LOS path blocked
                                                                                  Extra peripherals and directional antennas required
                             Indoor activity recognition [34]
PWR                                                                               Doppler signature affected by moving direction
                             Human sensing [35], [36]
                                                                                  Stable reference channel required

                                                 TABLE I: Summary on related works.


                                    Claimed   Claimed   Environment-   and reduce the training workload, while light re-training is still
## Reference       Features
                                    DR        FAR       independent    needed in new environments and consecutive activities cannot
 WiFall [20]     Variance           87%       18%       7              be handled as activity segmentation is required before signal
 RT-Fall [21]    Phase difference   91%       11%       7              processing. In addition, an earlier version of this work has
 FallDeFi [22]   Spectrogram        94.33%    14.92%    7              been published in [44] with a fixed sampling rate which may
 TL-Fall [23]    Frequency          86.83%    15.29%    7              not be energy-efficient as the proposed fall down detection
 DeFall          Speed              95.80%    1.47%     3              system requires a high sampling rate.
TABLE II: A brief summary of different CSI-based approaches              To address these challenges, in this work we propose DeFall
to fall detection and the claimed performance.                         that explores the inherent features of a fall and works well
                                                                       with only light training overhead and adaptive sampling rate
                                                                       based on a novel motion detector that is independent of the
                                                                       environment and can be put into use once deployed in any
mechanism of PWR, CSI is the standard information that                 new environment without any re-training or calibration.
can be extracted from commodity WiFi devices. By analyzing
CSI accessible on mainstream devices nowadays, one could                                    III. P RELIMINARIES
monitor indoor activities and detect indoor events, such as               In this section, the distinct speed pattern of a fall event
Wi-chase [31], CRAM [32] and TRIEDS [33]. In [20], Wang                is first presented. Then the definition of physical layer CSI
and Han et al. design WiFall, a WiFi-based unobtrusive fall            is reviewed, and further, the principles of CSI-based motion
detection system that extracts features from the CSI amplitude         detection and speed estimation are illustrated.
information to detect falls, while RT-Fall [21] exploits the
efficacy of phase difference for activity segmentation and
fall detection. FallDeFi [22] uses conventional short-time             A. Distinct Characteristics of Fall Events
Fourier transform (STFT) to extract time-frequency features               Different types of falls might happen in our daily life.
to sense the environmental changes and detect falls. Sensing-          Some are assisted falls occurring where the subject is assisted
Fi [43] detects falls based on WiFi signals together with              by another person or other supporting objects during the
ground-mounted accelerometer measurements to capture floor             falling process. Unassisted falls occur unexpectedly without
vibrations. Unfortunately, as illustrated in Table. II, since the      any support due to extrinsic environmental factors such as
features extracted in the existing WiFi-based fall detection           spills on the floor or intrinsic risk factors such as impaired
systems above are environment-dependent, the trained clas-             gait. Compared to assisted falls, unassisted falls are closer to
sifiers in these works suffer from the impact of environmental         free falls and have larger speeds at the moment of hitting the
changes and cannot be generalized well to new environments             ground, leading to a higher risk of causing severe injuries
without performance degradation. Re-training is required in            or even death [45]. Therefore the system we propose focuses
these systems when the environmental settings change, which            mainly on detecting unassisted falls and especially those when
makes them impractical as it is not suitable to ask users to fall      the subjects fall from a standing position which produces the
and collect training data every time the placements of furniture       largest speed.
or the deployments of the devices get changed. TL-Fall [23]               Speed and acceleration are two characteristics that are
applies transfer learning to mitigate environmental influence          usually used to describe motion. Intuitively, fall can be viewed
                                                                                                                                                                         4




                                                                               1                                     2

                                              𝑣𝑣⃗
     Static scatterers                                        Rx              0.5                                    0
                                         Dynamic scatterers

                                                                               0                                    -2

                                                                                                                                 first valley
                                                                             -0.5                                   -4
                                                                                    0   0.5   1   1.5   2   2.5          0       0.5        1      1.5    2      2.5


                                                                              (a) Theoretical spatial ACFs.        (b) Theoretical differential of
       Tx                                                                                                          spatial ACFs.
                                          Static scatterers

                                                                                                                    0.02
                 Fig. 1: Indoor rich-scattering model.
                                                                                                                         0


as a type of abnormal indoor event with abnormal speed and                                                          -0.02

acceleration and therefore they are both considered as the
                                                                                                                    -0.04
                                                                                                                                    first valley
unique characteristics that help distinguish falls from other
                                                                                                                             0         0.03        0.06       0.09
daily activities. The uniqueness resides not only in the absolute
values of speed and acceleration during a fall but also in how              (c) Differential ACF of response       (d) Instance of differential spa-
they change over time. More specifically, as a human falls to               power and the valley location.         tial ACF of response power.
the ground, his/her body will experience a rapid acceleration            Fig. 2: Spatial ACF and its differential for EM wave compo-
first. Once the body hits the floor, the body speed reduces              nents.
to nearly zero sharply. In fact, most of the unexpected falls
exhibit a similar pattern and this implies the feasibility of
developing an environment-independent system by monitoring
the speed and acceleration variation, which is the foundation            be “seen” by both Tx and Rx. Third, as indicated by [46],
of DeFall.                                                               DFS induced by human motion is not only related to the
                                                                         motion speed but also depends on the relative location and
B. Speed Estimation from WiFi CSI                                        direction with respect to the link. In addition, DFS-based speed
   In wireless communication, CSI, which also refers to chan-            estimators take CSI phase into account, while the phase of CSI
nel frequency response (CFR), describes the propagation of               on commercial WiFi devices cannot be measured accurately
the signals from the transmitter (Tx) to the receiver (Rx). The          due to the phase synchronization errors between the WiFi Tx
estimate of the CSI over a subcarrier with frequency f at time           and Rx [49].
t can be represented as                                                     Inspired by WiSpeed [24], in this work we assume a
                                      Y (t, f )                          practical rich-scattering environment, as shown in Fig. 1,
                         H(t, f ) =             ,                  (1)   and estimate the speed based on a statistical model of EM
                                      X(t, f )
                                                                         wave theory, which only makes use of the CSI magnitude
where X(t, f ) and Y (t, f ) are transmitted and received sig-           information.
nals. The transmitted WiFi signals experience multiple re-
flections in their propagation in indoor environments, and                 Specifically, the CSI magnitude can be measured through
therefore CSI contains a lot of useful information on the                CSI power response G(t, f ) defined as
channel conditions, which implies that we could capture the                             G(t, f ) ,| H(t, f ) |2 = ξ(t, f ) + (t, f ),                                 (2)
changes of the surrounding environment through CSI.
   Since the unique pattern of the series of speed is utilized,          where ξ(t, f ) = kE     ~ Rx (t, f )k2 , and E
                                                                                                                      ~ Rx (t, f ) denotes the
it is critical to have an accurate and reliable estimate of the          propagated signals. (t, f ) denotes the additive noise, and
speed based on WiFi CSI, which is not trivial due to the multi-          ξ(t, f ) and (t, f ) are assumed to be independent of each other.
path effects of the indoor propagation. Some device-free CSI-              It has been shown in [24] that the speed of a moving object
based speed estimators [46]–[48] have been proposed and most             can be reliably estimated by evaluating the autocorrelation
of them make use of the Doppler frequency shift (DFS) to                 function (ACF) of G(t, f ). The theoretical ACF of G(t, f ),
calculate the speed of the human body, which have several                ρG (τ, f ), can be derived as
limitations. First, DFS-based methods utilize the reflection
model, assuming that the human body is simplified as a single                                  σξ2 (f )                         σ2 (f )
                                                                         ρG (τ, f ) =      2                 ρ ξ (τ, f ) +  2                 δ(τ ),
reflector and produces only one dominant reflection path,                                 σξ (f ) + σ2 (f )               σξ (f ) + σ2 (f )
which usually does not hold in a practical indoor environment                                                                              (3)
with rich multi-path propagation. Second, to make sure the               where τ is the time lag of the ACF. σξ2 (f ) and σ2 (f ) are
direct reflection path from human body has strong enough                 the variances of ξ(t, f ) and (t, f ), respectively. ρξ (τ, f ) and
energy to be perceived, the existing works are limited to                Dirac delta function δ(τ ) are the ACFs of ξ(t, f ) and (t, f ).
the LOS coverage since the moving body should be able to                 When τ 6= 0, we have δ(τ ) = 0 and ρG (τ, f ) can be further
                                                                                                                                             5




                               Template-Generating Stage

             CSI Template             Speed                Band relaxed                                   Acceleration
               Dataset                                                              DBA
                                    Estimation              SLN-DTW                                        Estimation


                                                                                                              2D
                                                                                                         Representation

                                                                                                      2D
                               Decision-Making Stage                                               Template

              CSI Testing                          Y         Speed                 2D
               Stream              MD Detector                                                             SLN-DTW
                                                           Estimation         Representation     2D
                                          N                                                    testing
                                                                                                series
                                                           Acceleration                                                   Y      Fall
                                                            Estimation                                    FD Detector
                                                                                                                              Detected!

                                                                                                                 N


                                                       Fig. 3: An overview of DeFall.


derived based on the statistical theory of EM waves [50] as                     axis and get the ρG (τ, f ) as Eqn. (4) with its components
              X                                                                 expressed in Eqn. (5) and (6). Each component and
 ρG (τ, f ) =        (C1 (f )ρEu (τ, f ) + C2 (f )ρ2Eu (τ, f )),                its differential can be visualized in Fig. 2a and Fig.
             u∈{x,y,z}
                                                                                2b, respectively. Observing that the first local valley of
                                                                 (4)
                                                                                4ρ2Eu (τ, f ) , ∀u ∈ {x, y}, happens to be the first local
where C1 (f ) and C2 (f ) are scaling factors determined by
                                                                                valley of 4ρG (τ ) as well, we can extract the speed
the power reflected by all scatterers. ρEu (τ, f ) is the ACF of
 ~ Rx (t, f ) in u-axis direction where u ∈ {x, y, z}.                          information of the moving scatterers by locating the first
E
                                                                                local valley of 4ρG (τ, f ). Fig. 2c shows an example of
   For the i-th dynamic scatterer that moves at speed vi
                                                        ~ iu (t, f ).           4ρG (τ ) over time for a “walking” event, in which the
along z-axis, the scattered signal is denoted as E
                                                                                the first valley locations are marked by the black dots.
Then the components of its ACF ρEiu (τ, f ) in {x, y, z}-
                                                                                Fig. 2d shows a snapshot of the 4ρG (τ ) in Fig. 2c.
axes can be expressed as the following closed-form equations,
respectively:                                                              In the case where a single subject, e.g., a human, moves within
                                                                           the coverage of the pair of Rx and Tx, the dynamic signals
 ρEix (τ, f ) = ρEiy (τ, f )                                               are dominated by the parts that are reflected by the human
                3 sin(kvi τ )       1  3 cos(kvi τ ) (5)                  torso. Therefore it is reasonable to assume that in this case,
              =               1−           +             ,
                2 kvi τ          (kvi τ )2   2 (kvi τ )2                   all dynamic scatterers are moving at the same speed as well
                          3      sin(kvi τ )                              as in the same direction, and we can estimate the speed of the
      ρEiz (τ, f ) =           2
                                             − cos(kvi τ ) ,         (6)   human using the proposed method to further detect a fall.
                       (kvi τ )     kvi τ
where k denotes the wave number. Intuitively, the equa-                                         IV. D E FALL D ESIGN
tions above have established a relationship between the ACF
ρG (τ, f ) and the presence of motion and also the moving                     In this section, we depict the major modules in the DeFall
speed.                                                                     system in detail. The system mainly consists of two stages as
   • The relationship between ρG (τ, f ) and the presence
                                                                           illustrated in Fig. 3. In the offline stage, the speed of a fall is
     of motion From Eqn. (3), if motion is present in the                  estimated from the WiFi CSI by applying a statistical model on
     propagation environment of WiFi signals, as τ → 0                     the radio propagation in an indoor rich-scattering environment.
     we have δ(τ ) = 0 and ρξ (τ, f ) → 1 due to the                       After that, DTW-based algorithms are performed to generate
     property of white noise and the continuity of motion [51].            a representative template for a typical human fall. Then a fall
                                      σξ2 (f )                             event is detected in the online stage by evaluating the similarity
     Consequently, ρG (τ, f ) → σ2 (f )+σ    2      > 0 as τ → 0.          between the patterns of real-time speed/acceleration estimates
                                    ξ         (f )
     If there is no motion, the environment is static and the              and the representative template. In addition, an online motion
     variance σξ2 (τ, f ) = 0 and thus ρG (τ, f ) = 0 as τ → 0.            detection module is added before the fall detection module as
     Therefore the value of limτ →0 ρG (τ, f ) can indicate the            a pre-judgment procedure.
     presence of motion in the surrounding environment.
   • The relationship between ρG (τ, f ) and the moving
     speed For the simple case of all dynamic scatterers                   A. Template-Generating Stage
     moving in the same speed and direction, without loss of                 In the offline template-generating stage, M CSI sequences
     generality we can assume the moving direction is in the z-            of fall events are picked randomly and a “template database”
                                                                                                                                                                                        6



S = {S1 , S2 , ..., SM } is built based on the corresponding
estimated speed series.
   1) Challenges in building a general template: To construct
                                                                                                                           Template
a single representative template, we perform an “average” on
the database. Since the collected data are all time sequences,
the result by direct point-to-point matching and averaging
will be easily affected by sequence shift and misalignment.                                                                           6   4   2   06
                                                                                             6   4   2   06
Therefore, the operation of distance measurement, as well as                                              4                                        4
                                                                                                          2                                        2
series alignment, will be performed in the DTW space [52].                                                0                                        0
                                                                                                                                                       Series inside sliding window
   However, there may exist redundant speed segments of
other activities before or after the fall event, and the classic                         (a) Result of band-relaxed SLN-       (b) Result of a real-time detec-
                                                                                         DTW to extract template.              tion by SLN-DTW.
DTW algorithm is sensitive to the endpoints of the sequences.
Therefore, the endpoints of the series should be carefully                           Fig. 4: Applying the principle of SLN-DTW in series saniti-
defined and the template database cleaning is required.                              zation and fall detection.
   2) Template database cleaning: To remove the redundancy
while adapting to the possible variability in event instances,
we resort to the band-relaxed segmental locally normalized                           of the corresponding D and L are
DTW (SLN-DTW) [53].                                                                                      (
   The basic idea of SLN-DTW is to detect low-distortion local                                             d(i, j), if (u, v) = (i, j)
                                                                                              D(i, j) =                                                                               (8)
alignments between the objective series Sx and a series Sy                                                 D(u, v) + d(i, j), otherwise,
from the rest sequences {S1 , S2 , ..., Sx−1 , Sx+1 , ..., SM } by                                         (
dynamic programming [53]. The original SLN-DTW aims at                                                       1, if (u, v) = (i, j)
                                                                                                 L(i, j) =                                                                            (9)
matching objective series Sx in the testing stream Sy with the                                               L(u, v) + 1, otherwise.
assumption that Sx coincides exactly with the target event,
which is not suitable since any of the collected series in S                          For ∀(i, j) where Bs < i ≤ L1 , minimize C(i, j) =
may contain redundancy. Therefore band-relaxed SLN-DTW                               min d(i,j)+D(u,v)
                                                                                           L(u,v)+1    where (u, v) ∈ {(i − 1, j), (i, j − 1), (i −
                                                                                     (u,v)
in [53] is applied. It relaxes the boundary constraints of SLN-                      1, j − 1)}. For each iteration, update the corresponding D and
DTW so that the starting and ending points of Sx can be                              L as           (
aligned adaptively and the common parts can be retrieved                                                D(i, j) = D(u, v) + d(i, j)
                                                                                                                                      .        (10)
reliably.                                                                                               L(i, j) = L(u, v) + 1
   To be specific, let i and j represent the indices of the ob-
jective sequence Sx and the testing sequence Sy , respectively.                         Step 3 Trace back:
We can construct a grid [1, . . . , i, . . . , L1 ] × [1, . . . , j, . . . , L2 ],      Find the minimum C(k, j) for k ∈ [Be , L1 ] and trace back
where L1 and L2 denote the lengths of Sx and Sy . With                               along path (i, j) until i = Bs to extract the optimum path
relaxed boundaries, the starting point of the optimal warping                        across the central band {(i, j)|i ∈ [Bs , Be ]}. After that, if
path is allowed to be located in the starting band {(i, j)|i ∈                       the cost to the next point is smaller than the current cost,
[1, Bs ]} while the ending point is selected in the ending band                      i.e., C(inext , jnext ) < C(inow , jnow ), continue tracing back.
{(i, j)|i ∈ [Be , L1 ]). Then the accumulative distance matrix D                     Otherwise, stop and produce the optimum path.
and the length matrix L can be generated, where the elements                            Band-relaxed SLN-DTW is applied between every two
of the two matrices, D(i, j) and L(i, j), represent the total                        speed sequences to extract their common parts. Therefore, for
cumulative distance and path length from a starting point                            each objective series Sx ∈ {S1 , S2 , ..., SM }, there are M -
(is , js ) to (i, j). And the cost function is defined as the                        1 possible truncations with M -1 start indices Px,s and M -
ratio C(i, j) = D(i,j)
                     L(i,j) . The procedure of the band-relaxed                      1 end indices Px,e . And the part of Sx with indices lying
SLN-DTW applied for template database cleaning can be                                in [med(Px,s ), med(Px,e )] is regarded as the sanitized speed
summarized as:                                                                       sequence of the fall event in sample Sx , where med(Px,s ) and
   Step 1 Initializing distance matrix D and length matrix L:                        med(Px,e ) are medians of the start indices and end indices,
   For ∀(i, j) where 1 ≤ i ≤ Bs , 1 ≤ j ≤ L2 , we have                               respectively. In this way, the template database is refined to
                        (                                                            Ŝ = {Ŝ1 , Ŝ2 , . . . , ŜM }. Fig. 4a illustrates an instance of the
                            D(i, j) = d(i, j)                                        sanitized speed series by applying SLN-DTW.
                                                                              (7)
                            L(i, j) = 1,                                               3) Averaging in the DTW measure space: The M cleaned
where d(i, j) is the Euclidean distance between the i-th point                       speed series in the refined database Ŝ are then scaled to the
in Sx and the j-th point in Sy .                                                     same length and averaged in the DTW measure space to
                                                                                     construct a single representative profile. The problem to find an
   Step 2 Iteration:
                                                                                     optimal average can be formulated as an optimization problem
   For ∀(i, j) where 1 ≤ i ≤ Bs and 1 ≤ j ≤ L2 , minimize
                                                                                     that given a set of template time series Ŝ = {Ŝ1 , Ŝ2 , ..., ŜM },
C(i, j) = min d(i,j)+D(u,v)      where (u, v) ∈ {(i, j), (i −
                (u,v)L(u,v)+1                                                        the averaged series S̄ is the series that minimizes the sum of
1, j), (i, j − 1), (i − 1, j − 1)}. For each iteration, the updates                  squared DTW distances between S̄ and all of sequences in Ŝ
                                                                                                                                     7



as
                              M
                                                                      Tx
                              X
               S̄ = arg min         DT W 2 (S, Sx ).        (11)
                       S      x=1

   The DTW distance of two sequences DT W (A, B) is de-
fined as the Euclidean distance between series A and series B
                                                                      Rx
along the optimal warping path as follows:
                          v
                          u |P ∗ |
                          uX
         DT W (A, B) = t           kA[ap∗ ] − B[bp∗ ]k2 , (12)
                                                                       (a) Devices.                  (b) Fall examples.
                              p∗ =1

where P ∗ is the optimal warping path that minimizes the            Fig. 5: Illustrations for (a) devices for data collection and (b)
normalized distance as                                              examples for real falls including forward, lateral and backward
                            |P |
                                                                    falls.
                        1 X
           P ∗ = min             kA[ap ] − B[bp ]k2 ,       (13)
                   P   |P | p=1
                                                                    similarity of the two series is evaluated in DTW space to adapt
where ap and bp are indices of A and B associated with the          to misalignment of the two sequences in the time domain.
p-th point on path P .                                                 Since the fall events involving different people may expe-
   To solve the minimization problem (11) and get the optimal       rience different duration, the series segmented by a length-
average series, DTW barycenter averaging (DBA) algorithm            fixed sliding window may also include other activities before
[54] is implemented. DBA is an iterative algorithm that             or after the target event, which cannot be handled by the
refines an average sequence S̄ on each iteration following          traditional DTW, and thus we adopt the SLN-DTW [53] again
an expectation-maximization scheme, whose convergence has           to localize the start and end instances of an event, as Fig. 4b
been proved in [55]. The optimal speed time series S̄, pro-         illustrates. Regarding the template S̄2D as the objective series
duced by DBA, is then considered as the speed template.             and T2D as the testing series, we set the lengths of starting
   Besides speed, acceleration depicts the motion during a          and ending bands of S̄2D to be 1 since the template S̄2D is
fall from another different point of view. To get a more            already sanitized.
comprehensive description of the fall events, we derive an             By implementing SLN-DTW, the similarity of the testing
acceleration series S̄ 0 from the speed template S̄ and combine     stream T2D and S̄2D is evaluated. When the DTW distance
them by point-to-point stitching to generate a 2-D template         between the testing series and the reference template is less
S̄2D . The efficacy of utilizing the 2-D combined template S̄2D     than a preset empirical threshold γ, the testing sequence T2D
rather than a single 1-D template S̄ or S̄ 0 will be discussed in   has a similar pattern to the reference fall template S̄2D and
Section VI.                                                         the detector will alert that a fall occurs, where γ is empirically
                                                                    decided by experiments as well as the requirement of FAR and
B. Decision-making Stage                                            DR.
   As mentioned in Section III-A, fall events experience dis-          In the real-time monitoring, MD module keeps running with
tinct speed and acceleration patterns which could be used           a lower sampling rate and as long as the motion is detected,
for distinguishing falls from other indoor daily activities.        the FD module starts working with a high sampling rate to
However, a high sampling rate is needed for speed estimation        estimate the speed and detect fall events. When the similarity
[24]. To save energy and computation cost, in the decision-         between T2D and S̄2D stays low, i.e., the DTW distance larger
making stage, a low-rate motion detection (MD) module is            than γ, for a long enough time, it switches back to MD module
included in addition to the fall detection (FD) module.             to save power consumption and computation cost.
   1) Motion Detection Module: As indicated in Section III-B,
limτ →0 ρG (τ, f ) could be utilized as a criterion for MD. In
                                                                                      V. E XPERIMENTAL R ESULTS
practice, due to the limitation of the sampling rate, we could
only use ρG (τ = F1s , f ) to approximate τ → 0.                       To build our DeFall system, we employ two laptops
   For the purpose of efficient energy-saving, the MD module        (Thinkpad T420) equipped with off-the-shelf WiFi network
with a low sampling rate is added as a pre-detection of human       interface cards (Intel 5300) as the Tx and Rx, as shown in
motion prior to the FD module, and the FD module is triggered       Fig. 5a. We use the Linux 802.11n CSI tool [56] to collect
only in the presence of motion.                                     CSI measurements. Each of them is equipped with three
   2) Fall Detection Module: In the FD module, we apply a           omnidirectional antennas and the CSI stream over each pair of
sliding window W on the incoming CSI stream. The testing            antennas has a total of 30 subcarriers. By default, the system
speed sequence T is estimated from the CSI series in window         works on WLAN channel 153 with a carrier frequency of
W. The acceleration sequence T 0 is further derived from T ,        5.805 GHz and bandwidth of 40 MHz. In the MD module, the
followed by a combination operation to form a 2-D pattern           sampling rate is set to be 30 Hz. For FD module, to achieve
T2D .                                                               a better speed estimation resolution to capture the high-speed
   Then fall events can be detected by comparing the testing        motion, the Tx sends sounding frames with a channel sampling
time series T2D with the template S̄2D . The corresponding          rate of 1500 Hz.
                                                                                                                                                                                                                                                                                                                                                                                                                8




                                                       14.8 m                                                                                                     14.8 m                                                                                                                             3m                                           4.3 m                  4.2 m

                                                                                                                 Walking                                                                                                                              Walking                                                                               living room              room1           Rx      3.7 m
                                       room3                room4                                                                               room3                      room4
                                                                                                                 area                                                                                                                                 area                     3.7 m          room2
 4.0 m                                                                                                                        4.0 m                                                                                                                                                                                                                   Loc2                  Loc1                           Walking
                                                                                                                 Door                                                                                       Rx5                                       Door                                                                             Walking area                                                        area
                                                                                                                                                                                                                                  Rx4                                                                                                  Door                      Tx1
                                                                                                                 Tx                                                                                                                                   Tx                                                                                                                                                   Door
                                                                Tx1 foyer                                        Rx                                                  Rx2                                              foyer                           Rx                                                                               Tx                                   bathroom                       Tx
                                                                                                                                                        Rx1
 5.0 m                                                Tx2                                                                                        room1          room2                                                                                                                                        kitchenRx                                                                                     Rx
                                                                    Loc                                                      5.0 m                                                                                                                                             4.6 m                                                                            Loc3
                                                                                               closet                                                                                                                                        closet
                                                                                                                                                                                                                  Loc3                                                                                                                 Tx2
                                                                                                                                                      Loc1         Loc2
                                                                                                                                                                                                                                                                                           closet
                                                                                   Rx                                                           Tx                                                                                     Rx3
                                        room1                                                                                                                                                                                                                                                                                                         dining room                             4.6 m
                                                  room2

                                                                                                                                                                                                                                                                                                                                              11.5 m
                                               6.7 m                       6.3 m                                                                        6.7 m                                                             6.3 m
          (a) Environment 1: typical office environment.                                                                         (b) Environment 2: different rooms and place-                                                                                                 (c) Environment 3: typical apartment environ-
                                                                                                                                 ments in the typical office.                                                                                                                  ment.

                                                                                                                                 Fig. 6: Experimental environments.


                               6                                                                         6                                                                                   6                                                                                                                           6
## Walking                   Fall




                 Speed (m/s)                                                           Speed (m/s)                                                                       Speed (m/s)                                                                                                           Speed (m/s)
                               4                                                                         4                                                                                   4                                                                                                                           4
                                                                                                                        Walking                      Fall                                                                 Walking                      Sitting                                                                               Walking                         Sitting

                               2                                                                         2                                                                                   2                                                                                                                           2


                               0                                                                         0                                                                                   0                                                                                                                           0
                                   0     1            2         3            4                               0               1             2                3                                               0                 1              2              3                4                                               0                    1             2               3                 4
                                                Time (s)                                                                         Time (s)                                                                                               Time (s)                                                                                                          Time (s)
                                                 (a)                                                                                 (b)                                                                                                 (c)                                                                                                                   (d)




  Accleration (m/s2 )                                                              Accleration (m/s2 )                                                                  Accleration (m/s2 )                                                                                                    Accleration (m/s2 )
                         10                                                                              10                                                                                                 10                                                                                                               10
                                          Walking               Fall                                                       Walking                   Fall                                                                     Walking                       Sitting                                                                                Walking                       Sitting
                               0                                                                             0                                                                                               0                                                                                                                     0


                        -10                                                                              -10                                                                                        -10                                                                                                                   -10

                                   0     1            2         3           4                                    0               1          2                3                                                        0           1              2              3                4                                                     0              1              2               3                 4
                                                Time (s)                                                                             Time (s)                                                                                                Time (s)                                                                                                           Time (s)
                                                (e)                                                                                  (f)                                                                                                 (g)                                                                                                                    (h)

Fig. 7: Instances of speed and acceleration patterns for “walk-then-fall” and “walk-then-sit”. (a)(e): Speed and acceleration for
“walk-then-fall” under LOS; (b)(f): Speed and acceleration for “walk-then-fall” under NLOS; (c)(g): Speed and acceleration
for “walk-then-sit” under LOS; (d)(h): Speed and acceleration for “walk-then-sit” under NLOS.


A. Experimental Environments
                                                                                                                                                                                                             7                                                                                                            5




                                                                                                                                                                                     Average DTW Distance                                                                                         Average DTW Distance
                                                                                                                                                                                                                                                                     iteration = 1                                                                                       Number of Samples = 20
                                                                                                                                                                                                                                                                     iteration = 4                                                                                       Number of Samples = 25

   We evaluate DeFall with extensive experiments under vari-                                                                                                                                                6.5                                                      iteration = 7
                                                                                                                                                                                                                                                                     iteration = 10
                                                                                                                                                                                                                                                                                                                         4.9
                                                                                                                                                                                                                                                                                                                                                                         Number of Samples = 30
                                                                                                                                                                                                                                                                                                                                                                         Number of Samples = 35
                                                                                                                                                                                                                                                                     iteration = 13                                                                                      Number of Samples = 40

ous conditions (e.g., LOS and NLOS) at different locations in                                                                                                                                                6
                                                                                                                                                                                                                                                                     iteration = 16
                                                                                                                                                                                                                                                                     iteration = 19
                                                                                                                                                                                                                                                                                                                         4.8

                                                                                                                                                                                                            5.5                                                      iteration = 22

both office and home environments, with multiple volunteers                                                                                                                                                                                                          iteration = 25
                                                                                                                                                                                                                                                                     iteration = 28                                      4.7
                                                                                                                                                                                                             5
involved. The detailed settings are shown in Fig. 6 with the                                                                                                                                                4.5
                                                                                                                                                                                                                                                                                                                         4.6

locations of the Tx, the Rx, and the falling person marked.                                                                                                                                                  4                                                                                                           4.5
                                                                                                                                                                                                                  0       5       10    15       20    25       30        35          40                                       0             10           20          30            40            50
The data by a human-like dummy in environment 1 (Fig. 6a)                                                                                                                                                                     Number of Samples                                                                                                           Iteration
is used for template-generating as well as detection algorithm                                                                                                                                (a) Average DTW distance ver-                                                                                (b) Average DTW distance ver-
verification. Then real fall/non-fall activities are performed by                                                                                                                             sus sample size in DBA algo-                                                                                 sus number of iterations in DBA
                                                                                                                                                                                              rithm.                                                                                                       algorithm.
volunteers in all environments to further evaluate the impacts
of environment diversity, user diversity and also types of falls.                                                                                                                                                                       Fig. 8: Investigation of DBA factors.
The ground truth is recorded by video.
   In each environment, we change one of the Tx/Rx and
conduct experiments with different placements under both the
LOS and NLOS scenarios. Under the LOS scenario, Tx and
Rx could both “see” the subject, while in the NLOS case,                                                                                                                environment 3 (Fig. 6c), the Tx is deployed on positions
there does not exist any direct link between the subject and                                                                                                            Tx1 /Tx2 under LOS/NLOS conditions. In environment 2 (Fig.
one or more devices, which is very common for an indoor                                                                                                                 6b), only Rx1 is under the LOS scenario, while the other
environment. Specifically, in environment 1 (Fig. 6a) and                                                                                                               placements correspond to the NLOS cases.
                                                                                                                                                                                                                                                           9




                6                                                              15
                                                Overall                                                                                  Overall
                5                               NLOS                           10                                                        NLOS




                                                          Accleration (m/s2)
                                                LOS                                                                                      LOS
                                                                                5



  Speed (m/s)
                4
                                                                                0
                3
                                                                                -5
                2
                                                                               -10
                1
                                                                               -15
                0                                                              -20
                    0   0.2    0.4        0.6   0.8                                  0     0.2     0.4                        0.6          0.8
                               Time (s)                                                            Time (s)
                         (a) Speed templates.                                            (b) Acceleration templates.                                                                                     (c) 2D templates.

                                                                                         Fig. 9: Templates.


B. Data Collection
                                                                                                                               1                                                                         1
   The data collection is carried out on different days lasting                                                                                                   Overall                                                            DTW-based




                                                                                                         True positive rate
                                                                                                                                                                  LOS
for more than three months, during which the surround-                                                                        0.8                                                                       0.8                          Threshold-based




                                                                                                                                                                                       Detection rate
                                                                                                                                                                  NLOS
                                                                                                                                                                                                                    1
ing propagation environment keeps changing, including the                                                                     0.6
                                                                                                                                          1
                                                                                                                                                                                                        0.6
changes of the placements of furniture, the opening or closing                                                                0.4
                                                                                                                                        0.95
                                                                                                                                                                                                        0.4
                                                                                                                                                                                                                0.9


of doors and windows, etc. To verify the feasibility of DeFall,                                                                          0.9
                                                                                                                                                                                                                0.8
                                                                                                                              0.2                                                                       0.2
we first use a human-like dummy to collect both the template                                                                            0.85
                                                                                                                                            0      0.01         0.02        0.03                                        0         0.02     0.04    0.06
                                                                                                                               0                                                                         0
data and testing data. After that, the samples from real human                                                                      0   0.2      0.4      0.6      0.8             1                          0.2           0.4      0.6     0.8       1
falls, as illustrated by Fig. 5b, are further studied to evaluate                                                                        False positive rate                                                    False alarm rate

the effectiveness of the system.                                                                                  (a) ROC curves for overall, LOS                                               (b) ROC curve of DeFall
                                                                                                                  and NLOS cases.                                                               compared with threshold-based
   In the verification experiments, we consider both separate                                                                                                                                   method in WiSpeed.
fall events and continuous motion followed by falls. “Stand-
then-fall”, which represents falling from a stationary standing                                       Fig. 10: ROC curves for (a) different scenarios and (b)
posture, is realized by first letting the dummy stand straight                                        comparison with the threshold-based method in WiSpeed.
and then making it fall freely; while “walk-then-fall”, indi-
cating the falls happen after the continuous walking motion,
requires the experimenter to walk around the standing dummy                                           size of template database increases to 25, while in Fig. 8b it
at a normal speed and then make it fall. Instances of the                                             converges after around 15 iterations. Therefore the number of
speed/acceleration patterns for “walk-then-fall” and “walk-                                           iterations and the size of the template database are reasonably
then-sit” under both LOS and NLOS scenarios are presented                                             set to be 20 and 40, respectively.
in Fig. 7, where we can observe the distinct patterns between                                            The generated template after refinement and averaging is
falls and other activities such as sitting and walking. After the                                     presented in Fig. 9. As we can observe, the template has the
long-term data collection, there are 846 fall samples from the                                        same tendency as expected. The speed rises to a peak value
dummy and 814 non-fall samples for verification in total as                                           first and then drops, while the acceleration is positive first and
Table III illustrates.                                                                                then becomes negative. Also, it can be found that the templates
   In order to prove that our system can work well in real                                            of LOS and NLOS are highly consistent with each other.
world, we further evaluate its performance based on real                                              Since the speed estimation in DeFall is based on the rich-
human falls. We first involve three volunteers (1 female, 2                                           scattering model, as long as the target is within the coverage
males) for multiple long-term experiments to study the impact                                         of the radios, the system can capture the speed accurately using
of environment diversity, the presence of ambient motion, and                                         either the LOS or NLOS link, preserving not only the average
the types of falls (forward, backward and lateral falls). To                                          speed but also the precise speed changes. Due to the high
investigate the impact of user heterogeneity, we involve 7 more                                       consistency between the LOS and NLOS scenarios, we use
volunteers at different ages to perform different falls.                                              both LOS and NLOS data for template-generating and apply
                                                                                                      the overall template in the detecting phase.
C. Generated Templates
   In the offline template-generating stage, we build the tem-
plate dataset on the fall samples from the dummy. There are                                           D. Performance Evaluation
two factors to be selected in the DBA algorithm, i.e., the
size of template database and the number of iterations. The                                             1) Evaluation metrics: The evaluation metrics of the sys-
investigation of these two factors can be seen in Fig. 8. In                                          tem performance are detection rate and false alarm rate.
Fig. 8a, the average DTW distance gets more stable as the                                             Detection rate, shorted as DR, is defined as the percentage
                                                                                                                                                          10



  Scenario                Events                 Number        DR/FAR (DeFall)                       DR/FAR (WiFall)               DR/FAR (FallDeFi)
                             Stand-then-Fall       424        97.40%                                 75.71%                        91.04%
                  Fall                                                           97.10%                           74.32%                         89.58%
                             Walk-then-Fall         94        95.74%                                 68.09%                        82.98%
    LOS
                                Walking            167         0.00%                                 16.77%                        10.18%
               non-Fall                                                              1.45%                        18.90%                         12.79%
                              Sitting down         177         2.82%                                 22.03%                        15.25%
                             Stand-then-Fall       270        98.15%                                 70.37%                        85.19%
                  Fall                                                           97.56%                           69.82%                         84.45%
                             Walk-then-Fall         58        94.83%                                 67.24%                        81.03%
   NLOS
                                Walking            212         0.47%                                 15.09%                         8.96%
               non-Fall                                                              1.49%                        17.23%                         10.43%
                              Sitting down         258         2.33%                                 18.99%                        11.63%
  Overall                           -                            97.28%/1.47%                         72.58%/17.45%                 87.59%/11.43%
                                    TABLE III: Comparison results with WiFall and FallDeFi.


of correctly detected falls among all falls:                                                 Day 1        Day 2            Day 3         Day 4
                                                                                      1
                     # of detected f alls
                                                                         Detection
                DR =                      ,                  (14)                                                  Living room
                      # of total f alls                                              0.5

while false alarm rate, simplified as FAR, is the percentage of                        0
                                                                                      22:00 10:00 22:00 10:00 22:00 10:00 22:00 10:00 22:00
non-falls that are mistaken as falls among all non-falls:                              1


                                                                         Detection
                # of wrongly detected nonf alls                                                                   Dining room
      F AR =                                    .            (15)                    0.5
                     # of total nonf alls
                                                                                       0
   2) Receiver operating characteristic (ROC) curve: The                              22:00 10:00 22:00 10:00 22:00 10:00 22:00 10:00 22:00
                                                                                                                   Time
threshold γ in the decision-making stage plays an important
role in determining the boundary between fall and non-fall             Fig. 11: Long-term testing in an apartment environment.
events, and therefore it has to be selected carefully. To evaluate
the performance of DeFall, instead of proposing the specific
threshold directly, we first calculate the DR and FAR with           E. Robustness to Indoor Activities
various thresholds and generate the overall ROC curve as                For a fall detection system, DR is very crucial due to the
illustrated by Fig. 10a. We also investigate the ROC curves in       high risk of miss detection. On the other hand, FAR is also
LOS and NLOS scenarios, respectively. As seen, there exists          essential since other daily activities are performed most of
a trade-off between DR and FAR. If the γ is small, then there        the time in practice. Thus a system that yields a low FAR
tends to be fewer speed sequences to reach the standard, i.e.,       while keeping a reasonable DR is preferred. In this work,
the smaller γ is, the lower the DR is, while also getting a lower    the threshold yielding an overall FAR 1.47% is selected for
FAR. Note that the ROC curves of LOS and NLOS overlap                further system evaluation and the corresponding overall DR is
with each other. Also, both of them are highly similar to the        97.28%.
overall ROC trend, verifying the consistency of the proposed            The results of DR and FAR for all types of events are
system in LOS/NLOS scenarios.                                        summarized in Table III. According to the results, DeFall
   3) Effectiveness of the DTW-based pattern matching: In            succeeds in performing a high DR and low FAR under both
the previous work WiSpeed [24], a simple threshold-based             LOS and NLOS scenarios. Comparing the results of different
method is applied to detect falls and two features are pro-          fall events, we can notice a higher DR on “stand-then-fall”
posed: (i) the maximum speed; (ii) the maximum change in             events than “walk-then-fall” events since “walk-then-fall” may
acceleration within 0.5 s. In DeFall, we use the same CSI-           introduce interference to the speed estimation at the beginning
based speed estimator as Wispeed but improve the detection           of falls. Also, among the non-fall events, as “sitting-down”
performance by adding the DTW-based pattern matching for             experiences an acceleration followed by a deceleration, which
making a decision. To show the effectiveness of the DTW-             is more similar to the fall pattern than “walking”, it is can be
based detection module, we also get the ROC curve of                 observed that FAR of “sitting-down” is slightly higher than
WiSpeed by simultaneously adjusting the boundaries for the           that of “walking”.
two aforementioned features and compare it with DeFall as               We implement WiFall [20] and FallDeFi [22] for the
shown in Fig. 10b. As Fig. 10b illustrates, at the same level        comparative study. WiFall extracts seven different features
of FAR, the DR of DeFall is higher than WiSpeed. The area            for classification based on the variation of CSI amplitude
under the curve (AUC) of the ROC of DeFall is larger as well,        over time, while FallDeFi selects features from the STFT
proving a better performance. In particular, when the FAR is         spectrogram and the power burst curve (PBC). To make a fair
less than 1.5%, DeFall can still achieve a high DR over 95%          comparison, we optimize the parameters in these two works to
while the corresponding DR of WiSpeed drops to a level less          adapt to our dataset. We apply 40 fall samples to generate the
than 75%.                                                            template in DeFall, while we use 80 samples (40 falls and 40
                                                                                                                                                      11



       Objects   Material         Size/Weight        FAR                                 Forward        Backward         Lateral         Average
       Bottle    Plastic, water   0.5kg              0.0%                User 1          96.67%          95.56%          94.44%          95.56%
       Bag       Nylon            1kg                0.0%
                                                                         User 2          94.44%          96.67%          93.33%          94.81%
       Plate     Plastic          Radius = 12cm      0.0%
       Plate     Metal            Radius = 10cm      0.0%                User 3          95.56%          97.78%          97.78%          97.04%
       Book      Paper            22cm × 18cm        0.0%                Average         95.56%          96.67%          95.19%          95.80%
                                  17cm × 17cm
       Box       Paper                               0.0%                      TABLE V: Detection rates on different fall types.
                                  ×25cm, 0.8kg
                                  50cm × 40cm                                        Env. 1                      Env. 2                       Env. 3
       Chair     Wood                                0.0%                       LOS      NLOS   LOS                  NLOS                LOS      NLOS
                                  ×58cm, 3kg
                                                                                Tx1      Tx2    Rx1    Rx2      Rx3     Rx4     Rx5      Tx1      Tx2
                                                                     Loc 1      97.78% 95.56%   100%   97.78%   91.11% 95.56%   93.33%   97.78% 95.56%
             TABLE IV: Impact of falling objects.                    Loc 2      -        -      -      100%     93.33% 93.33%   91.11%   -        95.56%
                                                                     Loc 3      -        -      -      -        97.78% 97.78%   93.33%   -        97.78%
                                                                     Average    97.78% 95.56%   100%   98.89%   94.07% 95.56%   92.59%   97.78% 96.30%

                                                                          TABLE VI: Detection rates in various environments.
non-falls) to train the classifiers in WiFall and FallDeFi. The
results in Table III demonstrate that DeFall outperforms both        F. Robustness to Falling Objects
WiFall and FallDeFi with a higher overall DR (24.7% higher
                                                                        There are fall-like events that may cause false alarms, such
than WiFall and 9.69% higher than FallDeFi) and a lower FAR
                                                                     as falls of chairs and dropping a small object to the ground.
(15.98% lower than WiFall and 9.96% lower than FallDeFi).
                                                                     To test the robustness of the system against the interference
In addition, under both LOS and NLOS scenarios, DeFall
                                                                     from these events, extensive fall experiments are conducted on
also performs better in terms of the corresponding DR and
                                                                     objects with different sizes and different materials. For small
FAR. The reasons for this performance enhancement can be
                                                                     objects, each of them is lifted up and then dropped from a
attributed to the environment-independent speed information
                                                                     height of 1m, which is repeated 50 times at various locations
extracted by DeFall and the DTW-based pattern matching
                                                                     to evaluate a reliable FAR. We also repeat testing a falling
which adapts to the consecutive activities. More specifically,
                                                                     wooden chair. The corresponding result listed in Table IV
the features extracted in WiFall are based on the signal
                                                                     presents that all the FARs are 0.0%, verifying the robustness
variation and could be different in different settings, while
                                                                     of DeFall. This is because common objects which can be
the speed estimated in DeFall is an inherent property of falls.
                                                                     lifted up are usually much smaller than a human body and
Although compared with WiFall, FallDeFi devises more robust
                                                                     therefore, even if dropped from a high position, they produce
features using time-frequency analysis, its spectral features are
                                                                     fewer dynamic scatterers and cause less disturbance to the
partly dependent on the signal strength and do not take the
                                                                     environment. In such a case, the speed or acceleration values
detailed change pattern of falls into consideration. We also
                                                                     cannot be detected or the values are not continuous. For falling
observe that the performance of WiFall and FallDeFi degrades
                                                                     chairs, they always fall with lower centers of gravity and have
especially for consecutive events such as “walk-then-fall”.
                                                                     smaller speeds than human falls.
This is because WiFall and FallDeFi either assume segmented
activities or apply the “event duration” as a feature, which
can easily lead to misclassifications if falls and other normal      G. Types of Falls
activities cannot be separated reliably, while DeFall employs a         Three volunteers are involved in the experiments of real
sliding window combined with the pattern matching approach           falls. In this subsection, we study the impact of the orientation
which is more flexible to handle consecutive activities.             of a fall, i.e., forward, backward and lateral. Each of the three
                                                                     volunteers performs 5 forward falls, 5 backward falls and 5
   To take all possible daily activities into consideration and
                                                                     lateral falls in all settings. To better mimic real-world falls,
test the robustness of the system in practical, we further run
                                                                     the subjects first perform normal activities, either walking
the system in the same apartment (Fig. 6c) for four days.
                                                                     or standing still, and then fall in different directions under
Specially, we deploy two pairs of transceivers to cover the
                                                                     each setting. The overall results are summarized in Table.
main motion areas - living room and dining room, respectively.
                                                                     V. Taking the experiments in all environments into account,
The participant stays in the apartment every day and may
                                                                     we find that the falls in all the considered directions can
perform any daily activities in the monitored areas. No fall
                                                                     achieve a detection rate above 95.00%. The results are as
happens during the testing. We apply the same template
                                                                     expected because the proposed approach is independent of the
and detection algorithm to the collected speed series. The
                                                                     moving/falling directions.
experiment results for the long-term continuous test can be
found in Fig. 11. The decision is output every second and the
corresponding false alarms are counted. We have only 12 and          H. Environment Diversity
19 false alarms in total during the four-day testing in the living      To validate the robustness of DeFall to diverse environ-
room and dining room. On average, we have 3 and 6.3 false            ments, extensive experiments are carried out in both office
alarms per day, which is acceptable considering the involved         and home environments. Also, the locations of Tx and Rx
complicated daily activities.                                        are changed. During the experiments, each subject performs
                                                                                                                                                             3.5 m                                            Tx
                                                                                                                                                                                                              Rx
                                                                                                                                                                         C                         D     12




                                                                                                                                                                                              Sample
                                                                                                                                                                                          x   location
                               6.2 m
                                                                                                                   x                                                             x
                                           6.2 m                                                        x                                                                                     Tx
                                                                                                                              x                         x
                A                             B               Test area                                            x                  x
                                                                                                                                          Sample                                     x        Rx
                               A                              B                                                                           location Sample
                                                              Door          Test area
                                                                                                  x                                             x location     x                         x
    3.5 m                                                     Tx            Door                                                  x       Tx
                                                                                                               x                                  Tx
                3.5 m
                                                              Rx            Tx                                                            Rx                         x
                C                             D                             Rx                         x                  x
                                                                                                                                                   Rx
                                                                                                                                                                             x
                               C                              D                                                  xx                   x
                               (a) Setting 1: NLOS scenario.                                                            x scenario.
                                                                                                       (b) Setting 2: LOS                                      (c) Setting 3: LOS scenario.

                                                                                    Fig. 12: Settings for analyzing coverage.
                                           Sample
                                       x   location Sample
                     x
              Training/Template             Testingx location
                                                         DR (DeFall)             DR (WiFall)     DR (FallDeFi)
                                    x      Tx                                                                                                 w/ other moving person
x                     Env. 1                Env. 1
                                                         Tx
                                                                   96.67%          72.22%             90.00%                                                                             w/o other
            x LOS in Env.x1               Rx in Env. 1
                                        NLOS                       95.56%          53.33%             82.22%                               light motion    heavy motion
      x                                    xEnv. 2       Rx
                                                                                                                                                                                         motion
                                    x
                      Env. 1                                       95.37%          56.11%             81.30%                              3-5 m > 5m 3-5 m > 5m
                    x Env. 1                Env. 3
                                                  x
                                                                   96.67%          52.78%             76.11%
            x                                                                                                             LOS             12/15 15/15      8/15    15/15                 15/15
                         x
                        TABLE VII: Impact of environmental changes.                                                       NLOS            13/15 15/15      6/15    14/15                 15/15
                    x
                                   x User 1           User 2          User 3            User 4        User 5                  TABLE IX: Detection results with ambient motion.
             DR                        95.56%         94.81%          97.04%            91.67%        97.22%
             weight (kg)               77             50              84                70            62
                                                                                                                       studying the impact of user diversity and summarize the results
             height (cm)               174            166             168               172           175              in Table VIII. For Users 1-3, we have 270 samples each, while
                                       User 6         User 7          User 8            User 9        User 10          for Users 4-10, 36 samples are collected by each user. The
             DR                        94.44%         97.22%          100%              94.44%        97.22%           users have weights varying from 50 kg to 91 kg and heights
             weight (kg)               60             90              70                91            53               varying from 160 cm to 178 cm. Among all the ten subjects,
             height (cm)               169            178             171               170           160              User 7 is the tallest and User 9 is the heaviest while both User
                                                                                                                       7 and User 9 experience miss detection. Therefore, although a
                        TABLE VIII: Detection rates of different users.                                                greater height and weight indicate more dynamic scatterers on
                                                                                                                       the torso for signal propagation, we cannot conclude that there
                                                                                                                       is an obvious monotonic relationship between users’ heights or
            15 falls in different directions on different positions marked                                             weights and the detection performance based on the samples
            in the floorplan shown in Fig. 6. As reported in Table VI, a                                               from ten subjects.
            minimum detection rate of 91.11% can be achieved in different
            environments. The high detection rates are as expected because                                             J. Impact of Ambient Motion
            the proposed approach is environment-independent.
                                                                                                                          In this part, we investigate the robustness of the DeFall
               We also highlight such independence by comparing it with
                                                                                                                       system when a second subject is moving in the vicinity of
            WiFall and FallDeFi. As Table VII indicates, when we classify
                                                                                                                       the first falling subject, with both LOS and NLOS cases con-
            the data collected in a different environment from the training
                                                                                                                       sidered. Intuitively, two factors may affect the performance,
            dataset, DeFall outperforms both of WiFall and FallDeFi with
                                                                                                                       the distance between the two subjects (“distance”) and the
            a higher detection rate.
                                                                                                                       motion strength of the second subject. To study their impacts,
                                                                                                                       we conduct experiments with a distance of 3-5 m and >5
            I. User Diversity                                                                                          m between the two subjects while for the motion strength, we
               As different users have different heights, body shapes and                                              consider heavy motion (walking) and light motion (reading and
            gait styles, and a reliable fall detector should not be affected                                           typing). Under each setting, 15 fall events occur with different
            by the diversity of users, it is non-trivial to investigate the                                            fall orientations, and the results are presented as the ratio of
            impact of the user heterogeneity on the performance. To do                                                 the number of detected falls to a total of 15 falls in Table
            this, during a two-week experiment, 7 more volunteers with                                                 IX. As we can see, when the second person is walking, the
            ages ranging from 23 to 59 are asked to perform falls at various                                           detection rate degrades as the distance decreases due to the
            locations in environment 2. Similar to the previous experimen-                                             interference from the other person. Nevertheless, some falls
            tal procedure, the volunteers perform random activities before                                             can still be detected even when the walking person is close.
            falling. Each volunteer falls three times (1 forward, 1 backward                                           This is because the system estimates speed by localizing the
            and 1 lateral) under each setting. Combining the experiments                                               first valley as Fig. 2d shows, which always corresponds to
            of different displacements and different locations, we focus on                                            the highest speed of the massive scatterers. Therefore, the
                                                                                                                                                                                                                                                             13



                                                1                                          0.025
      DR         FAR                          0.95
                                                                     DR (Setting 2)
                                                                     DR (Setting 3)




                                                                                                   False alarm rate
                                                                                           0.02                                           1                                                                  1



                             Detection rate
                                                                     FAR (Setting 2)
 A    95.45%     1.28%                         0.9
                                                                     FAR (Setting 3)                                                                           2-D template
                                                                                                                                                               Acceleration template
                                                                                                                                                                                                                                         Rate 1500Hz
                                                                                                                                                                                                                                         Rate 750Hz
                                              0.85                                         0.015                                         0.8                                                                0.8




                                                                                                                        Detection rate
                                                                                                                                                                                           Detection rate
                                                                                                                                                               Speed template                                                            Rate 500Hz
 B    91.30%     1.33%                         0.8                                         0.01                                                      1                                                                      1
                                                                                                                                         0.6                                                                0.6
 C    95.45%     2.56%                        0.75
                                                                                           0.005                                                    0.9
                                                                                                                                         0.4                                                                0.4         0.9
                                               0.7
 D    90.91%     0.0%                         0.65                                         0                                             0.2        0.8                                                     0.2         0.8
                                                     1   2     3     4       5         6
                                                                                                                                                         0         0.02    0.04                                             0          0.1         0.2
                                                             Distance (m)                                                                 0                                                                  0
                                                                                                                                               0   0.2       0.4     0.6   0.8         1                          0   0.2       0.4   0.6    0.8         1
TABLE X: DR and FAR          Fig. 13: DR and FAR under set-                                                                                          False alarm rate                                                   False alarm rate
under setting 1.             ting 2 and setting 3.                                                                             (a) ROC curves for 2-D template                                      (b) ROC curves for different
                                                                                                                               and 1-D separate templates.                                          sampling rates.

                                                                                                                      Fig. 14: ROC curves for (a) comparison on 2-D template and
high speed associated with a fall can still be captured. Also,                                                        1-D separate templates and (b) different sampling rates.
the motion strength of the interfering person has a significant
impact on the performance, and a light motion by the second
person has much less interference than a strong motion.                                                               A. Necessity of 2-D Space
    In fact, fall detection mainly aims at protecting the elderly                                                        The 2-D combining step integrates the information con-
people who live alone by sending alarms to remote caregivers                                                          tributed by speed and acceleration. The combination is based
when the subject being monitored falls. If there is another                                                           on different weights α and realized by S̄2D = (1−α)S̄, αS̄ 0 .
                                                                                                                                                                                   
person nearby, timely assistance is available and the harm                                                            By setting α = 0, we can get the single speed template
to the subject experiencing a fall will be greatly reduced.                                                           while the single acceleration template can be obtained through
Therefore, the slight degradation in the multi-user case has                                                          setting α = 1. For 2-D space, we set α to be 0.5. The
little impact on the applicability of DeFall as it ensures great                                                      performance of the separate 1-D templates and combined
performance for a single-user case and the cases when another                                                         2-D template can be found in Fig. 14a. As shown, the 2-
user is relatively still or far away.                                                                                 D combined template outperforms any single template as it
                                                                                                                      provides a more comprehensive description of the events.
K. Coverage
   It is important to provide a large coverage for a real-                                                            B. Impact of Sampling Rate
world fall detection system. For this purpose, we conduct                                                                As described in Section IV, the sampling rate is a critical
experiments in a large empty hall to evaluate if falls that                                                           factor affecting the performance of our system. We now
are far away from the devices can be detected. As shown in                                                            revisit the experimental results in Section V and evaluate the
Fig. 12a, for the NLOS setting, the Tx is deployed at the                                                             performance with different sampling rate Fs . The DR and FAR
center of a room with size 6.2 m × 3.5 m, the Rx is in the                                                            are studied under different sampling rates 1500 Hz, 750 Hz and
hall and 10 m away from the Tx, and falls are performed at                                                            500 Hz, and their corresponding ROC curves are plotted in
four corners with the corresponding DR and FAR shown in                                                               Fig. 14b. As illustrated, the overall trends for all the cases are
Table X given the pre-selected threshold in Section V-E. For                                                          the same, in which FAR increases as DR increases. However,
the LOS setting, in order to find the impact of the distance                                                          the decrease of the sampling rate leads to a degradation in
between the subject and devices, we first sample uniformly on                                                         the performance of DeFall. This is because as the sampling
positions marked with “X” along the circle centered around                                                            rate gets reduced, the resolution of the ACF-based speed
Tx with a changing radius as shown in Fig. 12b. In the second                                                         estimator degrades correspondingly, which will introduce more
LOS setting shown in Fig. 12c, falls occur along lines parallel                                                       estimation errors and harm the detection accuracy.
to the direct link. Massive fall samples are collected using
the human-like dummy and a real human performs non-fall
                                                                                                                      C. Speed Distribution of Activities
activities. Illustrated by Table X, the system under setting 1
can cover an area as large as a normal office. Also, revealed by                                                         Although the maximum speed of the template can be up to
Fig. 13, DR and FAR both decrease as the distance between                                                             around 5 m/s, it does not mean the system can only detect
the subject and devices increases.                                                                                    falls with speeds reaching as high as 5 m/s. This is because
                                                                                                                      the proposed template-based method not only depends on the
                                                                                                                      single maximum speed value but also relies on the trend of
                       VI. D ISCUSSION
                                                                                                                      speed, which relaxes the decision boundary compared with a
   In this section, we will discuss the result of applying 2-                                                         hard-thresholding method.
D template comparing with that of using only 1-D speed                                                                   To understand the system capability better, we divide our
template and 1-D acceleration template, which demonstrates                                                            real fall/non-fall samples into different intervals (0 1m/s],
the necessity of combining the features into 2-D space. Also,                                                         (1m/s 2m/s], · · · , (5m/s 6m/s] based on their maximum
we will study the impact of the sampling rate and investigate                                                         speeds. The corresponding distribution is shown in Fig. 15a.
the speed distribution of activities. In addition, we evaluate the                                                    Then we apply the same overall template and decision bound-
computation cost.                                                                                                     ary and evaluate the corresponding DR/FAR in each individual
                                                                                                                                                               14



                                                                                   In the online stage, to produce a decision output, it costs only
                                                                                   0.0227 s with a speed estimation module and a simple DTW-
                                                                                   based similarity calculation, which is short enough for real-
                                                                                   time applications.


                                                                                   E. Limitation
                    (a) Distribution based on the maximum speed.
                                                                                      Since we only focus on the hard falls which may cause
           1                                                           1           serious injuries, our approach only deals with unexpected falls
                        Fall                                                       such as stumbles or slips due to weak gait. Other types of
                        Nonfall
                                                                             FAR
     DR   0.5                                                          0.5         falls such as falls slowly from a lower height, may result
                                                                                   in a different speed pattern from what is described in this
           0                                                           0           paper. To solve this problem, we need more analysis on the
                0        1           2       3       4     5       6               action decomposition to get a better understanding of the entire
                                   Maximum speed (m/s)
                                                                                   process of various falls. In this case, multiple templates and
                    (b) DR/FAR in each maximum speed interval.
                                                                                   deep learning techniques may be required.
Fig. 15: Maximum speed distribution and DR/FAR for each                               Another limitation is that since the algorithm can only
maximum speed interval.                                                            estimate the approximate average speed of the moving objects
                                                                                   in the environment, our system works well when there is a
                                                              CPU time             single person or no strong ambient motion close to the subject.
## Stage                            Module
                                                          (s)        (%)           However, this is fully compliant with the goal of our system
                                  Speed estimation        8.571322 96.23           to protect the elderly who live alone.
 Offline template                 Database sanitization   0.168743 1.895
 generating (dataset              DBA for average         0.165920 1.863                                     VII. C ONCLUSION
 size: 40)                        2D representation       0.001251 0.014
                                  Total                   8.9072                      In this paper, we propose DeFall, a novel environment-
                                                                                   independent indoor fall detection system using commercial
                                  Motion detection        0.000535         2.355
                                                                                   WiFi devices. The system extracts speed information to detect
 Online computation               Speed estimation        0.004661         20.52
                                                                                   falls even through the walls with a single pair of transceivers.
 for each output                  SLN-DTW & Detection     0.017519         77.13
                                                                                   A real prototype is built to validate the feasibility and evaluate
                                  Total                   0.0227                   the performance in various environments. The results show
                    TABLE XI: Processing time of DeFall.                           that DeFall achieves a detection rate higher than 95% on real
                                                                                   falls while maintaining a false alarm rate lower than 1.50%
                                                                                   under both LOS and NLOS scenarios, without any scenario-
interval, where the DR/FAR is the ratio of detection to the                        tailored prior training.
total falls/non-falls in that specific interval. As we can see,
the maximum speeds of fall and non-fall series samples are                                                       R EFERENCES
distinct with a small overlapped part. The FAR and DR both
increase with the speed, as illustrated by Fig. 15b. However,                       [1] “Falls.” [Online]. Available: https://www.who.int/news-room/fact-
                                                                                        sheets/detail/falls. Accessed: April 2021.
even if the falls and non-falls have the maximum speeds in the
                                                                                    [2] P. Melillo, R. Castaldo, G. Sannino, A. Orrico, G. de Pietro, and L. Pec-
same interval, our system can still distinguish most of them                            chia, “Wearable technology and ecg processing for fall risk assessment,
with reasonable DR/FAR because of their distinct patterns over                          prevention and detection,” in 2015 37th Annual International Conference
time.                                                                                   of the IEEE Engineering in Medicine and Biology Society (EMBC),
                                                                                        pp. 7740–7743, 2015.
                                                                                    [3] P. Pierleoni, A. Belli, L. Maurizi, L. Palma, L. Pernini, M. Paniccia,
                                                                                        and S. Valenti, “A wearable fall detector for elderly people based on
D. Computation Cost and Realtime Realization                                            ahrs and barometric sensor,” IEEE Sensors Journal, vol. 16, no. 17,
   In the real-time scenario, as the extracted speed feature                            pp. 6733–6744, 2016.
                                                                                    [4] J. Wang, Z. Zhang, B. Li, S. Lee, and R. S. Sherratt, “An enhanced fall
is independent of the environments, the offline stage can be                            detection system for elderly person monitoring using consumer home
completed ahead of time. Then the pre-trained template can                              networks,” IEEE Transactions on Consumer Electronics, vol. 60, no. 1,
be applied directly in the decision-making stage.                                       pp. 23–29, 2014.
                                                                                    [5] J. Dai, X. Bai, Z. Yang, Z. Shen, and D. Xuan, “Perfalld: A pervasive fall
   To evaluate the system computation effort, we repeat the                             detection system using mobile phones,” in 2010 8th IEEE International
process using MATLAB on a desktop with Intel Core i7-                                   Conference on Pervasive Computing and Communications Workshops
9700K processor and 32 GB memory. We record the average                                 (PERCOM Workshops), pp. 292–297, IEEE, 2010.
                                                                                    [6] S. Abbate, M. Avvenuti, F. Bonatesta, G. Cola, P. Corsini, and A. Vec-
processing time. Table XI illustrates the CPU time for each                             chio, “A smartphone-based fall detection system,” Pervasive and Mobile
module in the offline and online stages. Note that we do not                            Computing, vol. 8, no. 6, pp. 883–899, 2012.
require a massive amount of data for template generating,                           [7] C.-C. Lin, P.-Y. Lin, P.-K. Lu, G.-Y. Hsieh, W.-L. Lee, and R.-G.
                                                                                        Lee, “A healthcare integration system for disease assessment and safety
which significantly reduces the computation cost. The total                             monitoring of dementia patients,” IEEE Transactions on information
pre-training process only takes an average CPU time of 8.9 s.                           Technology in Biomedicine, vol. 12, no. 5, pp. 579–586, 2008.
                                                                                                                                                              15



 [8] E. Auvinet, F. Multon, A. Saint-Arnaud, J. Rousseau, and J. Meunier,         [30] S. Kianoush, S. Savazzi, F. Vicentini, V. Rampa, and M. Giussani,
     “Fall detection with multiple cameras: An occlusion-resistant method              “Device-free rf human body fall detection and localization in industrial
     based on 3-d silhouette vertical distribution,” IEEE Transactions on              workplaces,” IEEE Internet of Things Journal, vol. 4, no. 2, pp. 351–
     Information Technology in Biomedicine, vol. 15, no. 2, pp. 290–300,               362, 2017.
     2011.                                                                        [31] S. Arshad, C. Feng, Y. Liu, Y. Hu, R. Yu, S. Zhou, and H. Li, “Wi-
 [9] C. Rougier, J. Meunier, A. St-Arnaud, and J. Rousseau, “3d head                   chase: A wifi based human activity recognition system for sensorless
     tracking for fall detection using a single calibrated camera,” Image and          environments,” in 2017 IEEE 18th International Symposium on A World
     Vision Computing, vol. 31, no. 3, pp. 246–254, 2013.                              of Wireless, Mobile and Multimedia Networks (WoWMoM), pp. 1–6,
[10] E. E. Stone and M. Skubic, “Fall detection in homes of older adults               IEEE, 2017.
     using the microsoft kinect,” IEEE Journal of Biomedical and Health           [32] W. Wang, A. X. Liu, M. Shahzad, K. Ling, and S. Lu, “Device-
     Informatics, vol. 19, no. 1, pp. 290–301, 2015.                                   free human activity recognition using commercial wifi devices,” IEEE
[11] G. Mastorakis and D. Makris, “Fall detection system using kinect’s                Journal on Selected Areas in Communications, vol. 35, no. 5, pp. 1118–
     infrared sensor,” Journal of Real-Time Image Processing, vol. 9, no. 4,           1131, 2017.
     pp. 635–646, 2014.                                                           [33] Q. Xu, Y. Chen, B. Wang, and K. J. R. Liu, “Trieds: Wireless events
[12] S. Gasparrini, E. Cippitelli, S. Spinsante, and E. Gambi, “A depth-based          detection through the wall,” IEEE Internet of Things Journal, vol. 4,
     fall detection system using a kinect® sensor,” Sensors, vol. 14, no. 2,           no. 3, pp. 723–735, 2017.
     pp. 2756–2775, 2014.                                                         [34] Q. Chen, B. Tan, K. Chetty, and K. Woodbridge, “Activity recognition
[13] X. Ma, H. Wang, B. Xue, M. Zhou, B. Ji, and Y. Li, “Depth-based                   based on micro-doppler signature with in-home wi-fi,” in 2016 IEEE
     human fall detection via shape features and improved extreme learning             18th International Conference on e-Health Networking, Applications and
     machine,” IEEE Journal of Biomedical and Health Informatics, vol. 18,             Services (Healthcom), pp. 1–6, 2016.
     no. 6, pp. 1915–1922, 2014.                                                  [35] K. Chetty, G. E. Smith, and K. Woodbridge, “Through-the-wall sensing
[14] B. Wang, Q. Xu, C. Chen, F. Zhang, and K. R. Liu, “The promise of                 of personnel using passive bistatic wifi radar at standoff distances,”
     radio analytics: A future paradigm of wireless positioning, tracking, and         IEEE Transactions on Geoscience and Remote Sensing, vol. 50, no. 4,
     sensing,” IEEE Signal Processing Magazine, vol. 35, no. 3, pp. 59–80,             pp. 1218–1226, 2012.
     2018.                                                                        [36] W. Li, R. J. Piechocki, K. Woodbridge, C. Tang, and K. Chetty, “Passive
[15] K. J. R. Liu and B. Wang, Wireless AI: Wireless Sensing, Positioning,             wifi radar for human sensing using a stand-alone access point,” IEEE
     IoT, and Communications. Cambridge University Press, 2019.                        Transactions on Geoscience and Remote Sensing, pp. 1–13, 2020.
[16] B. Y. Su, K. C. Ho, M. J. Rantz, and M. Skubic, “Doppler radar fall          [37] Y. Kim and B. Toomajian, “Hand gesture recognition using micro-
     activity detection using the wavelet transform,” IEEE Transactions on             doppler signatures with convolutional neural network,” IEEE Access,
     Biomedical Engineering, vol. 62, no. 3, pp. 865–875, 2015.                        vol. 4, pp. 7125–7130, 2016.
[17] M. G. Amin, Y. D. Zhang, F. Ahmad, and K. D. Ho, “Radar signal               [38] S. Björklund, H. Petersson, A. Nezirovic, M. B. Guldogan, and
     processing for elderly fall detection: The future for in-home monitoring,”        F. Gustafsson, “Millimeter-wave radar micro-doppler signatures of hu-
     IEEE Signal Processing Magazine, vol. 33, no. 2, pp. 71–80, 2016.                 man motion,” in 2011 12th International Radar Symposium (IRS),
[18] G. Mokhtari, Q. Zhang, and A. Fazlollahi, “Non-wearable uwb sensor                pp. 167–174, 2011.
     to detect falls in smart home environment,” in 2017 IEEE International
                                                                                  [39] M. Raja, Z. Vali, S. Palipana, D. G. Michelson, and S. Sigg, “3d head
     Conference on Pervasive Computing and Communications Workshops
                                                                                       motion detection using millimeter-wave doppler radar,” IEEE Access,
     (PerCom Workshops), pp. 274–278, 2017.
                                                                                       vol. 8, pp. 32321–32331, 2020.
[19] L. Ma, M. Liu, N. Wang, L. Wang, Y. Yang, and H. Wang, “Room-
                                                                                  [40] Y. Tian, G.-H. Lee, H. He, C.-Y. Hsu, and D. Katabi, “Rf-based fall
     level fall detection based on ultra-wideband (uwb) monostatic radar and
                                                                                       monitoring using convolutional neural networks,” Proceedings of the
     convolutional long short-term memory (lstm),” Sensors, vol. 20, no. 4,
                                                                                       ACM on Interactive, Mobile, Wearable and Ubiquitous Technologies,
     p. 1105, 2020.
                                                                                       vol. 2, no. 3, pp. 1–24, 2018.
[20] Y. Wang, K. Wu, and L. M. Ni, “Wifall: Device-free fall detection by
     wireless networks,” IEEE Transactions on Mobile Computing, vol. 16,          [41] C. Wu, F. Zhang, and Y. H. K. J. R. Liu, “Gaitway: Monitoring and
     no. 2, pp. 581–594, 2016.                                                         recognizing gait speed through the walls,” IEEE Transactions on Mobile
[21] H. Wang, D. Zhang, Y. Wang, J. Ma, Y. Wang, and S. Li, “Rt-fall: A real-          Computing, 2020.
     time and contactless fall detection system with commodity wifi devices,”     [42] Z. Yang, Z. Zhou, and Y. Liu, “From rssi to csi: Indoor localization
     IEEE Transactions on Mobile Computing, vol. 16, no. 2, pp. 511–526,               via channel response,” ACM Computing Surveys (CSUR), vol. 46, no. 2,
     2017.                                                                             pp. 1–32, 2013.
[22] S. Palipana, D. Rojas, P. Agrawal, and D. Pesch, “Falldefi: Ubiquitous       [43] R. Ramezani, Y. Xiao, and A. Naeim, “Sensing-fi: Wi-fi csi and
     fall detection using commodity wi-fi devices,” Proceedings of the ACM             accelerometer fusion system for fall detection,” in 2018 IEEE EMBS
     on Interactive, Mobile, Wearable and Ubiquitous Technologies, vol. 1,             International Conference on Biomedical Health Informatics (BHI),
     no. 4, p. 155, 2018.                                                              pp. 402–405, 2018.
[23] L. Zhang, Z. Wang, and L. Yang, “Commercial wi-fi based fall detection       [44] Y. Hu, F. Zhang, C. Wu, B. Wang, and K. J. R. Liu, “A wifi-based
     with environment influence mitigation,” in 2019 16th Annual IEEE                  passive fall detection system,” in ICASSP 2020-2020 IEEE International
     International Conference on Sensing, Communication, and Networking                Conference on Acoustics, Speech and Signal Processing (ICASSP),
     (SECON), pp. 1–9, 2019.                                                           pp. 1723–1727, IEEE, 2020.
[24] F. Zhang, C. Chen, B. Wang, and K. J. R. Liu, “Wispeed: A statistical        [45] V. S. Staggs, L. C. Mion, and R. I. Shorr, “Assisted and unassisted falls:
     electromagnetic approach for device-free indoor speed estimation,” IEEE           Different events, different outcomes, different implications for quality
     Internet of Things Journal, vol. 5, no. 3, pp. 2163–2177, 2018.                   of hospital care,” The Joint Commission Journal on Quality and Patient
[25] M. A. Al Hafiz Khan, R. Kukkapalli, P. Waradpande, S. Kulandaivel,                Safety, vol. 40, no. 8, pp. 358–364, 2014.
     N. Banerjee, N. Roy, and R. Robucci, “Ram: Radar-based activity mon-         [46] K. Qian, C. Wu, Z. Yang, Y. Liu, and K. Jamieson, “Widar: Decimeter-
     itor,” in IEEE INFOCOM 2016 - The 35th Annual IEEE International                  level passive tracking via velocity monitoring with commodity wi-fi,” in
     Conference on Computer Communications, pp. 1–9, 2016.                             Proceedings of the 18th ACM International Symposium on Mobile Ad
[26] M. S. Seyfioğlu, A. M. Özbayoğlu, and S. Z. Gürbüz, “Deep con-               Hoc Networking and Computing, p. 6, ACM, 2017.
     volutional autoencoder for radar-based classification of similar aided       [47] X. Li, D. Zhang, Q. Lv, J. Xiong, S. Li, Y. Zhang, and H. Mei,
     and unaided human activities,” IEEE Transactions on Aerospace and                 “Indotrack: Device-free indoor human tracking with commodity wi-fi,”
     Electronic Systems, vol. 54, no. 4, pp. 1709–1723, 2018.                          Proc. ACM Interact. Mob. Wearable Ubiquitous Technol., vol. 1, Sept.
[27] S. D. Regani, C. Wu, B. Wang, M. Wu, and K. J. R. Liu, “mmwrite:                  2017.
     Passive handwriting tracking using a single millimeter-wave radio,”          [48] K. Qian, C. Wu, Y. Zhang, G. Zhang, Z. Yang, and Y. Liu, “Widar2.0:
     IEEE Internet of Things Journal, vol. 8, no. 17, pp. 13291–13305, 2021.           Passive human tracking with a single wi-fi link,” in Proceedings of the
[28] Y. Gu, F. Ren, and J. Li, “Paws: Passive human activity recognition               16th Annual International Conference on Mobile Systems, Applications,
     based on wifi ambient signals,” IEEE Internet of Things Journal, vol. 3,          and Services, MobiSys ’18, (New York, NY, USA), p. 350–361, Asso-
     no. 5, pp. 796–805, 2015.                                                         ciation for Computing Machinery, 2018.
[29] S. Sigg, U. Blanke, and G. Tröster, “The telepathic phone: Frictionless     [49] C. Chen, Y. Chen, Y. Han, H.-Q. Lai, F. Zhang, and K. J. R. Liu,
     activity recognition from wifi-rssi,” in 2014 IEEE International Confer-          “Achieving centimeter-accuracy indoor localization on wifi platforms:
     ence on Pervasive Computing and Communications (PerCom), pp. 148–                 A multi-antenna approach,” IEEE Internet of Things Journal, vol. 4,
     155, 2014.                                                                        no. 1, pp. 122–134, 2017.
                                                                                   16



[50] D. A. Hill, Electromagnetic fields in cavities: deterministic and statisti-
     cal theories, vol. 35. John Wiley & Sons, 2009.
[51] F. Zhang, C. Wu, B. Wang, H.-Q. Lai, Y. Han, and K. J. R. Liu,
     “Widetect: Robust motion detection with a statistical electromagnetic
     model,” Proceedings of the ACM on Interactive, Mobile, Wearable and
     Ubiquitous Technologies, vol. 3, no. 3, pp. 1–24, 2019.
[52] H. Sakoe and S. Chiba, “Dynamic programming algorithm optimization
     for spoken word recognition,” IEEE transactions on acoustics, speech,
     and signal processing, vol. 26, no. 1, pp. 43–49, 1978.
[53] A. Muscariello, G. Gravier, and F. Bimbot, “Variability tolerant audio
     motif discovery,” in International Conference on Multimedia Modeling,
     pp. 275–286, Springer, 2009.
[54] F. Petitjean, A. Ketterlin, and P. Gançarski, “A global averaging method
     for dynamic time warping, with applications to clustering,” Pattern
     Recognition, vol. 44, no. 3, pp. 678–693, 2011.
[55] F. Petitjean, G. Forestier, G. I. Webb, A. E. Nicholson, Y. Chen, and
     E. Keogh, “Dynamic time warping averaging of time series allows
     faster and more accurate classification,” in 2014 IEEE International
     Conference on Data Mining, pp. 470–479, 2014.
[56] D. Halperin, W. Hu, A. Sheth, and D. Wetherall, “Tool release: Gathering
     802.11n traces with channel state information,” SIGCOMM Comput.
     Commun. Rev., vol. 41, p. 53, Jan. 2011.

