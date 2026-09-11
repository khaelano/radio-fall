IEEE TRANSACTIONS ON MOBILE COMPUTING,                VOL. 16,     NO. 2,    FEBRUARY 2017                                                                581




                        WiFall: Device-Free Fall Detection
                              by Wireless Networks
        Yuxi Wang, Student Member, IEEE, Kaishun Wu, Member, IEEE, and Lionel M. Ni, Fellow, IEEE

       Abstract—Injuries that are caused by falls have been regarded as one of the major health threats to the independent living for the
       elderly. Conventional fall detection systems have various limitations. In this work, we first look for the correlations between different
       radio signal variations and activities by analyzing radio propagation model. Based on our observation, we propose WiFall, a truly
       unobtrusive fall detection system. WiFall employs physical layer Channel State Information (CSI) as the indicator of activities. It can
       detect fall of the human without hardware modification, extra environmental setup, or any wearable device. We implement WiFall on
       desktops equipped with commodity 802.11n NIC, and evaluate the performance in three typical indoor scenarios with several layouts of
       transmitter-receiver (Tx-Rx) links. In our area of interest, WiFall can achieve fall detection for a single person with high accuracy. As
       demonstrated by the experimental results, WiFall yields 90 percent detection precision with a false alarm rate of 15 percent on average
       using a one-class SVM classifier in all testing scenarios. It can also achieve average 94 percent fall detection precisions with 13 percent
       false alarm using Random Forest algorithm.

       Index Terms—Wireless, channel state information, fall detection, device-free, machine learning

                                                                                       Ç

1    INTRODUCTION

F    ALLS, which can be depicted as the abrupt change of
    human body from an upright position to a lying-down
position without control [1], are prevalent among the
                                                                                           sensors or smartphones is cumbersome for the user, and dif-
                                                                                           ferent positions (e.g., placed at chest, waist, thigh, arms,
                                                                                           legs, etc.) of the sensors will show different detection perfor-
elderly. According to the data from the Center for Disease                                 mance. For example, the user of system in [7] needs to carry
Control and Prevention [2], one out of three adults aged 65                                a custom-made device which comprises of accelerometer,
or older falls at least once each year. A large number of fatal                            micro-controller and other sensors during fall detection.
injuries are caused by falls. Since reducing the rescue time                               Using PerFallD in [8], the user only needs a smartphone on
after fall detection can extremely increase the overall sur-                               him, but the position where the smartphone placed will
vival of the elderly, it is necessary to deploy automatic fall                             affect the detection accuracy.
detection system in home environment.                                                         To achieve effective automatic fall detection, we require
   Based on monitoring instruments, existing fall detection                                the system to be accurate, inexpensive, and user friendly.
(FD) systems can be categorized into four classes: ambient                                 Few of the FD systems using techniques above have been
device, camera, wearable sensor and smartphone. FD sys-                                    widely deployed into home settings due to the fact that they
tems using ambient devices [3], [4] leverage floor vibration                               suffer terrible performance when considering one or more
caused by a fall to detect a risky situation. Specific devices                             of the above three conditions. We want to employ a new
must be implanted beforehand. System in [3] need a Piezo                                   technique to conduct fall detection in order to balance the
Transducer to build a floor vibration based fall detector,                                 three conditions. The widespread dissemination of the
and the system in [4] needs to deploy floor sensors. FD sys-                               wireless local area networks (WLAN) has enabled the possi-
tems using cameras [5], [6] employ activity classification                                 bility of WLAN-based fall detection in indoor environment
algorithms on a series of images recorded by high resolution                               for the elderly. WLAN infrastructures can support high-
cameras, and can effectively detect a fall. However, cameras                               accuracy-low-cost fall detection with simple infrastructure
are expensive and violate personal privacy sometimes. Both                                 deployment, engaging user experience and limited privacy
wearable sensor based [7] and smartphone based [8] FD                                      concerns. Thus, we aim to investigate whether automatic
techniques employ sensors to sense the changes in accelera-                                fall detection can be achieved without any special wearable
tion or velocity on three coordinate axes. However, carrying                               device by leveraging current commercial wireless products
                                                                                           by exploiting the properties of WiFi signal during propaga-
                                                                                           tion. In the last decade, WiFi facilities and techniques have
   Y. Wang and K. Wu are with the College of Computer Science and Soft-                   motivated a variety of research interests in localization [9],
    ware Engineering, Shenzhen University, P.R. China, and the CSE Depart-                 motion detection [10] and object tracking [11]. Currently,
    ment, Hong Kong University of Science and Technology (HKUST),
    Kowloon, Hong Kong. E-mail: ywangav@cse.ust.hk, wu@szu.edu.cn.
                                                                                           more research works have addressed the relationship
   L. M. Ni is with the Department of Computer and Information Science,                   between wireless signals and human activities.
    University of Macau, Taipa, Macau, China. E-mail: ni@umac.mo.                             In order to implement unobtrusive fall detection by
Manuscript received 13 July 2015; revised 14 Mar. 2016; accepted 13 Apr.                   wireless networks, we need to find a good representation of
2016. Date of publication 22 Apr. 2016; date of current version 5 Jan. 2017.               the wireless signal. It should be robust to environmental
For information on obtaining reprints of this article, please send e-mail to:              changes but sensitive to human disturbances. However, we
reprints@ieee.org, and reference the Digital Object Identifier below.
Digital Object Identifier no. 10.1109/TMC.2016.2557792                                     observe that current radio propagation model cannot be
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
                                   1536-1233 ß 2016 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission.
                                       See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
582                                                                        IEEE TRANSACTIONS ON MOBILE COMPUTING,             VOL. 16,   NO. 2,   FEBRUARY 2017


applied directly when considering complex human activi-                             [15], the authors introduce WiTrack which can track the 3D
ties. Therefore, it is difficult to observe the relationship                        motion of a target person. The updated version of this work
between human activities and wireless signal properties                             called WiTrack2.0 [16] achieves 3D motion tracking of mul-
based on existing radio propagation models.                                         tiple targets. Both WiTrack and WiTrack2.0 can detect fall-
   In this paper, we first address the wireless radio propaga-                      ing of a person with wireless signals. However, these two
tion model in indoor environments under the disturbances of                         approaches are implemented using USRP/GNURadio with
human activities. We analyze the radio propagation model                            daughter boards, and cannot be implemented by commercial
during falling from theoretical perspective, and present a                          products. With advanced wireless devices, more subtle
refined model when the user is at the NLOS location. Based                          movements can be detected. Authors in [17] propose a
on our theoretical case study, we propose WiFall, a passive                         method named WiSee to conduct gesture recognition. WiSee
device-free fall detection system leveraging Channel State                          can classify nine whole-body gestures by analyzing the
Information (CSI) as the indicator. We define the area which                        Doppler shifts of wireless signals extracted during transmis-
can be covered by the signal communication links of WiFall                          sion. RSS obtained from commercial wireless product can
for fall detection as the effective range area for performance                      also be applied for activity detection such as gesture recogni-
evaluation, and it is our area of interest. WiFall can detect var-                  tion [18]. Yet, RSS is consider to be not reliable in a cluttered
ious activities for a single person inside the effective range                      environment due to multipath. Therefore, a fine-grained
area, and can achieve fall detection with high accuracy. In                         indicator Channel State Information attracts researcher’s
summary, the main contributions of this paper are as follows:                       attentions. CSI has also been utilized for wireless motion
                                                                                    detection. FIMD [10] is a system which can monitor the
       We exploit the feasibility of using fine-grained Chan-
                                                                                    motion behavior of the target using CSI extracted from com-
        nel State Information for device-free fall detection
                                                                                    modity WiFi NIC. In our work, we not only focus on motion
        for a single person. We take temporal stability and
                                                                                    detection, but identify specific human activities. We only
        frequency diversity of CSI to design WiFall, a pas-
                                                                                    leverage commodity WiFi products to detect the motion of
        sive device-free fall detection system. Compared
                                                                                    the target using CSI. Compared with systems using specific-
        with other FD systems, WiFall leverages existing
                                                                                    designed wireless devices and RSS, WiFall can achieve satis-
        prevalent wireless infrastructures, and can be widely
                                                                                    factory detection accuracy and can be more widely deployed
        deployed into real life with low cost.
                                                                                    in real indoor environment with low cost.
    To realize truly unobtrusive fall detection, we pres-
                                                                                       CSI-based activity identification. Since CSI has been verified
        ent a case study from theoretical perspective by tak-
                                                                                    to be a reliable indicator for device-free wireless motion
        ing human activities into consideration. On the basis
                                                                                    detection, more researchers seek for the opportunity to
        of motion detection by anomaly detection algorithm,
                                                                                    identify various activities using CSI-based feature. Our sys-
        we apply a one-class Support Vector Machine classi-
                                                                                    tem WiFall [19] is prior work among these systems. It learns
        fier and Random Forest algorithm to classify differ-
                                                                                    specific CSI signal amplitude patterns using machine learn-
        ent human activities and achieve fall detection.
                                                                                    ing algorithms, and distinguishes falling from other move-
    Extensive evaluations of WiFall with commodity
                                                                                    ments. Instead of using CSI amplitude directly for activity
        802.11n NICs equipped on laptops are conducted in
                                                                                    recognition, E-eyes [20] utilizes the distribution of CSI
        three typical indoor scenarios with different Tx-Rx
                                                                                    amplitude to classify the activities in whole home environ-
        layout schemes. The measurements show that
                                                                                    ment. The activities identified by the system have high cor-
        WiFall can achieve an average detection accuracy of
                                                                                    relations with the locations. The authors in [21] observe that
        94 percent with Random Forest-based classification
                                                                                    radio frequency interference (RFI) has a significant impact
        in all testing scenarios. Furthermore, WiFall can be
                                                                                    on CSI vectors, and introduce a device-free location-ori-
        extended for identification of other human activities.
                                                                                    ented activity system based on their observation. In [22], the
   The rest of this paper is organized as follows. We will
                                                                                    authors propose another CSI-based human activity monitor-
present the related work of WiFall in Section 2, and we will
                                                                                    ing system called CARM. CARM contains a CSI-speed
introduce the background knowledge in Section 3. Then in
                                                                                    model which transfer CSI amplitude variation caused by
Section 4, we will introduce the detailed design of our
                                                                                    human movements into speed information. Based on the
WiFall system. Section 5 will describe the methods to evalu-
                                                                                    fact that different human movements will cause different
ate the WiFall system, followed by the evaluation results in
                                                                                    speed changes, CARM quantifies the correlation between
Section 6. Finally, we will give our conclusions and discus-
                                                                                    speed and movement, and recognizes a given activity with
sions on WiFall in Section 7.
                                                                                    Hidden Markov Model. It is a remarkable work in CSI-
                                                                                    based activity recognition. CSI from commercial off-the-
2         RELATED WORK                                                              shelf (COTS) WiFi devices can also be leveraged for subtle
WiFall is closely related to the following three research                           movement recognition, such as gesture recognition [23],
categories:                                                                         keystroke tracking [24] and in-air drawing [25]. In this
   Wireless motion detection. Motion detection is the detection                     paper, we improve our WiFall system in [19]. Different
of the movement of entities in an area of interest. Noury                           from other activity identification systems, we mainly focus
et al. [1], Yu [12] and Mubashir et al. [13] review the princi-                     on activity recognition of the elderly, who belong to a rela-
ples and approaches used in existing fall detection (FD) sys-                       tively special social group with obvious common behaviors.
tems. In [14], the authors propose an innovative approach                           It is designed for healthcare scenarios. We revise our
called Wi-Vi. It can track the moving path of a human but                           method to improve the detection accuracy and implement
cannot detect specific activities using wireless signals. In                        the complete WiFall system.
          Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
WANG ET AL.: WIFALL: DEVICE-FREE FALL DETECTION BY WIRELESS NETWORKS                                                                                     583


    Device-free indoor localization. Another important tech-
nique related to WiFall is device-free indoor localization.
Authors in [26] first describe device-free passive (DfP) local-
ization, which does not require the entities to carry any
device during positioning. Mainstream systems leverage
fingerprinting method to locate the tracked entity, and RSS
is the most widely used fingerprint. Nuzzer [27] is a repre-
sentative work, which estimates the location of the target by
comparing RSS to the fingerprint stored in a beforehand
passive radio map. The system ACE [28] solves the problem
of positioning multiple entities using a probabilistic energy-
minimization framework. After CSI has been leveraged for
device-based indoor localization such as FILA [9], [29] and
MODLoc [30], more efforts have been paid in device-free                         Fig. 1. Signal propagation model in indoor environment.
scenarios. Different from RSS-based system, the passive
radio map in CSI-based system is constructed using CSI
                                                                                                               h ¼ jhjejsinu ;
matrices. Pilot [31] is known to be a prior work using CSI
for device-free indoor localization. It first examines whether                  where jhj is the amplitude and u is the phase of each
a target is present in the area of interest, and then estimates                 subcarrier.
the location by mapping the abnormal CSI caused by the                             CSI provides a finer-grained representation of the wire-
target to fingerprint in radio map. MonoPHY [32] is a DfP                       less link compared with Received Signal Strength (RSS).
localization system which only utilizes one single stream of                    Thus, recent wireless applications tend to employ CSI rather
CSI for positioning. Authors in [33] find that receivers at dif-                than RSS. We will give experimental analysis about how to
ferent locations possess diverse sensitivity to environment                     leverage CSI to indicate human activities.
changes, and they utilize this observation to improve locali-
zation accuracy. Similar to DfP indoor localization which                       3.2 Propagation Model for Falling: A Case Study
leverages the fact that RSS or CSI will change when the hori-                   The idea of device-free fall detection using CSI is based on
zontal position of the object changes, we track and analyze                     the fact that human presence and movement will affect the
the effects of vertical position variations of the object person                propagation paths of wireless signals. In this section, we
on CSI to achieve device-free fall detection.                                   provide a case study when falling happens at a NLOS loca-
                                                                                tion with theoretical analysis. We only consider activities
3   PRELIMINARIES                                                               happen at a fixed location and name these activities as in-
                                                                                place activities (falling, sitting down, and standing up). The
In this section, we will present the background knowledge
                                                                                model in this section proves that falling can be distin-
of WiFall system, and give a case study on the signal varia-
                                                                                guished using wireless signals from theoretical perspective.
tion during falling from theoretical perspective.
                                                                                   In a typical indoor environment, there is one main path
                                                                                (Line-Of-Sight, LOS) and several reflected paths (None-
## 3.1 Channel State Information
                                                                                Line-Of-Sight, NLOS) due to the surroundings such as ceil-
Channel State Information or Channel Status Information                         ing, floor and walls, as shown in Fig. 1. The LOS path suffers
(CSI) is information that estimates the channel properties of                   from free space path loss. According to the free space
a communication link [34]. In wireless communication, a                         model, the received power by a receiver antenna which is
transmitted radio signal is affected by the physical environ-                   separated from a radiating transmitter antenna by a dis-
ment (e.g., reflection, diffraction and scattering). CSI                        tance d, is given by the Friis free space equation [34]:
describes how a signal propagates in the channel by com-
bining the effects of time delay, amplitude attenuation and                                                            Pt Gt Gr 2
                                                                                                          Plos ðdÞ ¼                  ;                  (2)
phase shift. In frequency domain, the narrowband flat-fad-                                                              ð4pÞ2 d2
ing channel with multiple transmission and receiving anten-
nas (multi-input-multi-output, MIMO) is modeled as:                             where Pt is the transmitted power, Plos ðdÞ is the received
                                                                                power which is a function of the distance d, Gr is the receiv-
                             y ¼ Hx þ n;                                 (1)    ing antenna gain, Gt is the transmitter antenna gain,  is the
                                                                                wavelength in meters and d is the distance from transmitter
where y is the received vector, x is the transmitted vector, n
                                                                                to receiver in meters.
is the noise vector, and H is the channel matrix. As noise is
                                                                                   Consider the scenario that paths deflected off the walls
often modeled as circular symmetric complex normal with
                                                                                are ignored, when the transmitter and receiver are placed
n  cNð0; SÞ, H in the above formula can be estimated as:
                                                                                near the ground, the power received by the receiver through
                                ^ ¼ y:                                          ceiling and ground paths can be represented as [11]:
                                H
                                    x                                                                                  Pt Gt Gr 2
                                                                                                      Pceil ðdÞ ¼                         ;              (3)
CSI is an estimation of H. In Orthogonal Frequency Division                                                         ð4pÞ2 ðd2 þ 4h1 2 Þ
Multiplexing (OFDM) system, CSI is represented at subcar-
                                                                                                                        Pt Gt Gr 2
rier level. CSI of a single subcarrier is in the following math-                                    Pfloor ðdÞ ¼                          ;              (4)
ematical format:                                                                                                    ð4pÞ2 ðd2 þ 4h2 2 Þ
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
584                                                                         IEEE TRANSACTIONS ON MOBILE COMPUTING,          VOL. 16,   NO. 2,   FEBRUARY 2017


where h1 and h2 are the distance from ceiling or floor to the
transmitter-receiver (Tx-Rx) link, respectively.
   When the target presents in this static environment, there
will several scattered paths caused by the human body.
According to the radar equation [35], the received power
influenced by the target is computed as:
                        X               Pt Gt Gr 2 s
    Psca ðr1 ; r2 Þ ¼               3
                                                             hi 2 ð0; h;    (5)
                        hi   ð4pÞ ðr21 þ h2i Þðr22 þ h2i Þ

where r1 is the distance from the transmitter to the target,
and r2 is the distance from the receiver to the target in hori-
zontal plane. hi represents the height of the scattered points,
and h is the height of the target.
                                                                                   Fig. 2. Overview of system architecture.
   Suppose the intensity magnitudes of LOS, ceiling,
ground and scattered paths are Elos , Eceil , Efloor and Esca ,
                                                                                   MP) in the same area of interest collects the wireless physi-
respectively. The total received power by the receiver can
                                                                                   cal information CSIs, and sends them to the next phase.
be computed as:
                                                                                      Learning phase contains three important modules: data
                  P / jElos þ Eceil þ Efloor þ Esca j2 :                     (6)   processing, profile construction, activity decision module.
                                                                                   We obtain CSI profiles from the CSI data which have been
   When the target falls, Elos , Eceil and Efloor remain                           denoised and reconstructed. The profiles collected during
unchanged, the changes in the received scattered power at                          training process are stored in the profile database, and the
the receiver can be represented as:                                                profiles gathered during testing process are utilized for
                                                                                   activity decision by applying two machine algorithms.
                X                Pt Gt Gr 2 s                                        In the final phase alerting, an emergency alarm is trig-
      DPsca ¼                3
                                                        hi 2 ðh  d; h;     (7)
                 hi   ð4pÞ ðr21 þ h2i Þðr22 þ h2i Þ                                gered when falling is detected. The application will pop up
                                                                                   an alarm and send message for help if the alarm has not
where d is the reduced height of human body due to the fall.                       been stopped in time. The false alarm data can be used to
Therefore, there will be significant change in Esca and the                        give feedback to the learning phase in order to update the
total received power P . Other in-place activities will also                       profile database.
cause the change of P . We analyze the energy changes
when conducting falling and sitting down at the location                           4.2 Data Processing
1m away from the AP-MP link in the lab. Our experimental                           CSIs are extracted from received packages in MPs. Using
data show that the maximum energy change during falling                            the CSI tool introduced in [36], the CSI packet received is a
is 21:3dB and the time duration of variation is around 1s.                         Ntx  Nrx  30 matrix, where Ntx is the antenna number for
The energy vibrates for more than 4s when the person sits                          AP, Nrx is the antenna number for MP, and the third dimen-
down, and the maximum energy change is 9:31dB. Consider                            sion is across 30 subcarriers in the OFDM channel. Let
energy change and time duration, the energy variation dur-                         Ntx ¼ 3 and Nrx ¼ 3, a CSI packet contains 9 streams with
ing falling is more obvious than that when other in-place                          30 subcarriers in each stream, which can be represented in
activities (e.g., sitting down) occur. The energy change is                        the following format:
closely related to the environment, the setting of AP-MP
link, and the location to perform activities. Therefore, the                                     CSI 1 ¼ fCSI 1;1 ; CSI 1;2 ; . . . ; CSI 1;30 g
energy change of each activity is not a fixed value. We do                                       CSI 2 ¼ fCSI 2;1 ; CSI 2;2 ; . . . ; CSI 2;30 g
not simply quantify the energy change but analyze the                                                                               
energy variation based on the model with learning method
when we design the WiFall system.                                                                CSI 9 ¼ fCSI 9;1 ; CSI 9;2 ; . . . ; CSI 9;30 g;

                                                                                   where in CSI i;j , i is the stream number and j is the subcar-
4      WIFALL SYSTEM                                                               rier number.
In this section, we first introduce the architecture of WiFall.                        In WiFall, we take the amplitude of CSI for activity classi-
Then we depict the major modules in WiFall system in                               fication, and leave phase information for our future work.
details.                                                                           The CSI mentioned in the rest of paper means the CSI
                                                                                   amplitude. Previously, we discover that human movements
## 4.1 System Overview                                                                affect the nine streams differently whereas the 30 subcar-
WiFall leverages CSI to indicate human activities in an                            riers similarly, as shown in Figs. 3 and 4. By computing
indoor environment, and then learns the specific patterns                          the correlation matrix of CSI subcarriers, we observe that
related to fall and other focused activities. Fig. 2 presents an                   all the subcarriers have positive correlation and the correla-
overview of the system. The WiFall system consists of three                        tion ratios between successive subcarriers are high. We
main phases: sensing, learning, and alerting.                                      present the correlation matrix of Subcarrier 1 to Subcarrier
   In the sensing phase, the transmitter (Access Point, AP)                        30, shown in Fig. 5. Based on the observations, we try to
propagates wireless signals. The receiver (Monitoring Point,                       aggregate CSI of 30 subcarriers into one single value CSI i .
        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
WANG ET AL.: WIFALL: DEVICE-FREE FALL DETECTION BY WIRELESS NETWORKS                                                                                      585




                                                                                       Fig. 5. Correlation matrix of CSI subcarriers in one stream.

                                                                                       which is an array with 270 columns. We apply the new con-
Fig. 3. CSI variances of 1st subcarrier in different streams.                          structed 270-column arrays for fall identification. The 9-col-
The CSI for each stream is aggregated using the following                              umn arrays CSISt s are only used in anomaly detection.
equation in [9]:                                                                          Environmental factors such as temperature and room set-
                                                                                       tings may also cause a fluctuation in the received CSI. WiFall
                                  1X N
                                        fj                                             reduces environmental noise by employing a weighted mov-
                       CSI i ¼              jCSI i;j j;                        (8)
                                  N j¼1 f0                                             ing average filter. For example, the 270-column CSI value at
                                                                                       time t is averaged by the equation:
where f0 is the central frequency. Therefore, the previous
CSI data for each time slot t we use is a 9-column array as                                dt ¼              1
                                                                                           CSI                               ðm  CSI t
follows:                                                                                            m þ ðm  1Þ þ    þ 1                               (9)
                                                                                                  þ ðm  1Þ  CSI t1 þ    þ 1  CSI tmþ1 Þ:
              CSISt ¼ CSIt1 ; CSIt2 ; . . . ; CSIt9 :

However, we observe that the aggregation partially loses                               The value of m decides to what degree the current value is
the frequency diversity of CSI subcarriers especially in envi-                         related with the historical records. The reconstructed CSI
ronment with rich multipath. Therefore, we reconstruct the                             matrix is processed for profile construction. Similarly, the
CSI packet at time t into:                                                             9-column CSI arrays are denoised using the weighted mov-
        h                                                                         i    ing average filter before anomaly detection.
CSIt ¼ CSIt1;1 ; CSIt2;1 ; . . . ; CSIt9;1 ; CSIt1;2 ; . . . ; CSIt8;30 ; CSIt9;30 ;
## 4.3 Profile Construction
                                                                                       In this part, we introduce the techniques we used to build
                                                                                       our CSI profile for fall detection.

## 4.3.1 Anomaly Detection
                                                                                       Anomaly detection aims to detect the anomaly change in
                                                                                       wireless signal. The activities that WiFall system focuses are
                                                                                       walking, sitting down, standing up and falling. Although
                                                                                       various immobile human postures result in different signal
                                                                                       power at MPs, they have similar signal changing patterns in
                                                                                       time domain, which are steady over the time. Using a Local
                                                                                       Outlier Factor based anomaly detection algorithm, WiFall
                                                                                       picks out human activities and isolates the corresponding
                                                                                       anomaly patterns.
                                                                                          In this step, the system learns a model of stable situation.
                                                                                       For a given series of CSI data, we compute LOF of the
                                                                                       data compared with the stable model in order to detect
                                                                                       anomaly patterns. We define a situation is stable when
                                                                                       the person present in the area of interest is resting. The
                                                                                       stable profile is extracted before WiFall system conducts
                                                                                       detection work, and it evaluates the stable wireless
Fig. 4. CSI variances of different subcarriers in one stream.                          signal propagation features without any human activities.
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
586                                                                      IEEE TRANSACTIONS ON MOBILE COMPUTING,             VOL. 16,    NO. 2,   FEBRUARY 2017


                                                                                                                 TABLE 1
                                                                                                   Proportion of Top Three Eigenvalues
                                                                                                              in SVD Matrix

                                                                                                                                    Proportion
                                                                                                 resting                               99.92%
                                                                                                 falling                               99.83%
                                                                                                 sitting down                          99.86%
                                                                                                 walking                               99.65%
                                                                                                 standing up                           99.91%


                                                                                  4.3.2 SVD Matrix Factorization
                                                                                  After detected anomaly activities, WiFall applies classifica-
                                                                                  tion algorithm on CSI matrix to identify activity. To
                                                                                  decrease the processing time during classification, we lever-
                                                                                  age a Singular Value Decomposition (SVD) matrix to per-
                                                                                  form a selection on the eigenvalue of the CSI data selected
Fig. 6. Eigenvalues of SVD matrix.                                                by anomaly detection. SVD is a method to transform corre-
                                                                                  lated variables into a set of uncorrelated variable which bet-
Given CSIi ¼ fCSI1i ; CSI2i ; . . . ; CSIni g which is a series of                ter exposes the various relationships among the original
CSI of stream i, the approximated density function p^ðxÞ is                       data. It is also a method for best approximation of the origi-
computed as:                                                                      nal data points using fewer dimensions. SVD can be used to
                           X
                         1 n                                                      make the processing time of WiFall short to achieve auto-
                 p^ðxÞ ¼          dn ðx  CSIti Þ;            (10)                matically fall detection.
                         n t¼1
                                                                                     SVD is a factorization of a real or complex matrix in lin-
where n is the number of CSI and dn ðÞ is a kernel function.                     ear algebra, and is applied to statistic and signal processing.
According to [37], the local density is estimated by a specific                   The basic idea behind SVD is to take a high dimensional,
distance at which a sample point can be reached from its                          highly variable set of data and then reduce it to a lower
neighbors. Concretely, the local density of a point p, which                      dimensional space which exposes the substructure of the
is lrdðpÞ, is defined as:                                                         original data clearly. The SVD of an m  n real or complex
                          P                                                       matrix M is formalized as:
                            o2kðpÞ reach  distk ðp; oÞ
              lrdðpÞ ¼ 1=                               ; (11)                                                   M ¼ USV T ;                               (14)
                                       k
where kðpÞ is the set of k-nearest neighbor of p, o is any                        where U is an m  m real or complex unitary matrix, S is an
selected point in kðpÞ, k is the number of chosen nearest                         m  n rectangular diagonal matrix with nonnegative real
neighbors, reach  distk ðp; oÞ is called reachability distance.                  numbers on the diagonal, and V T is an n  n real or com-
Let k  distanceðpÞ be the distance of object p to the k nearest                  plex unitary matrix. We record 100 CSI packages per sec-
neighbors and dðp; oÞ be the distance from p to o,                                ond, and each package consists of nine stream with each
reach  distk ðp; oÞ can be calculated as                                         stream having 30 subcarriers. To cover the duration of a
                                                                                  whole action (e.g., falling, sitting down), we stack the CSI of
      reach  distk ðp; oÞ ¼ maxðk  distanceðpÞ; dðp; oÞÞ:              (12)     two successive seconds together, then obtain a matrix
                                                                                  X 2 R200270 for training and testing. Intuitively, all signal
Local Outlier Factor is defined as the ratio of average local
                                                                                  channels are stable in an ideal environment, and will be
densities of one object’s neighbors to the local density of the
                                                                                  affected simultaneously by changes in the environment.
object. LOF of point p is computed as follows:
                                                                                  Consequently, each sample X should be a low-ranking
                                    1
                                        P                                         matrix. Fig. 6 plots the eigenvalues of typical samples of dif-
                                    k    o2kðpÞ lrdðoÞ
                      LOF ðpÞ ¼                          :               (13)     ferent activity classes. As shown, the eigenvalues in all cases
                                            lrdðpÞ                                decrease rapidly as expected. Moreover, Table 1 shows
                                                                                  the proportion of top three eigenvalues in different classes.
    We consider each stream of CSI one input of the LOF                           Interestingly, we discover that the first three sample of
function, and compute the LOF values of the CSI samples.                          the SVD matrix can capture the characteristics of the whole
Therefore, we will obtain 9 LOF lists as the result of a CSI                      matrix. Therefore, we leverage SVD to select the best three
dataset. LOF denotes the probability of whether a point is                        eigenvalues in this matrix to apply classification. Even con-
an outlier or not. An LOF value of approximately 1 indicates                      sidering resting as a type of activity, the first 3 eigenvalues
that the point is located in a region of homogeneous density,                     from SVD can still provide the features obviously.
and is not an outlier. In each stream, if there is an outlier
occurs, we believe the stream is anomaly. For all the nine                        4.4 Activity Decision
streams, if majority of the streams show anomaly features,                        Two classification algorithms have been applied in WiFall
we believe that the activity corresponding to the CSI dataset                     for fall detection. To distinguish falling from the other
is anomaly.                                                                       movements, we first adopt a one-class Support Vector
        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
WANG ET AL.: WIFALL: DEVICE-FREE FALL DETECTION BY WIRELESS NETWORKS                                                                                      587


Machine (SVM) based on the features extracted from profile
construction module. To further improve the detection
accuracy and to decrease the false alarm, Random Forest
(RF) is then applied in WiFall system.

## 4.4.1 Classification Using a One-Class SVM
To distinguish falling from other movements, a one-class
Support Vector Machine is applied. A SVM is a supervised
learning model with associated machine learning algo-
rithms which are used to analyze data and recognize pat-
terns. It is one of the most commonly used machine
learning tools with strong open-source software supports.
A one-class SVM is an extended algorithm of SVM [38]. In a
one-class SVM, all the samples are divided into either the
objective class or the non-objective class. To solve the non-
linear classification problem, it maps input samples into a
high dimensional feature space by using a kernel function
and finds the maximum margin hyperplane in the trans-
formed feature space. The hyperplane includes all the objec-
tive samples inside and non-objective samples outside.
   To figure out the most useful features for classification,
we first choose the most frequently used features to charac-
terize the activities, which are normalized standard devia-
tion of CSI, offset of signal strength, period of motion,
median absolute deviation, interquartile range, signal
entropy, and velocity of signal change. The meaning of the
seven features we selected are as follows:

  1)    Normalized STD: It is related to the dynamic range
                                                                                 Fig. 7. Random forest flow chart.
        of the motion.
   2) Offset of Signal Strength: It corresponds to the stron-
## 4.4.2 Detection Using Random Forests
        gest power that is received by MPs.
   3) Period of Motion: It shows the time that the activity                      A one-class SVM classifier is reliable enough to distinguish
        lasts.                                                                   falling from the other movements, but the fall detection
   4) Median Absolute Deviation (MAD): MAD is a robust                           accuracy is not desirable in some environments with rich
        measure of the variability of a univariate sample of                     multipath effects. Meanwhile, we want to extend WiFall
        quantitative data. The sum of squared MAD can                            to detect more activities rather than falling, one-class
        express the concentration of data.                                       SVM is not the optimal solution in this case. Significant
   5) Interquartile Range (IR): It corresponds to the disper-                    improvements in classification accuracy have resulted
        sion of CSI.                                                             from growing an ensemble of trees and letting them vote
   6) Signal Entropy: It is a generic measure of system                          for the classes. As one of the most typical ensemble learn-
        disorganization.                                                         ing method for classification, Random Forests first con-
   7) Velocity of Signal Change: Velocity is computed as                         struct decision trees at training time and then output the
        the first order derivative here, which is an indicator                   class that is the mode of the classes output by individual
        showing how fast the signal is changed by an                             trees, and are more likely to improve the detection accu-
        activity.                                                                racy. Therefore, we select Random Forests (RF) as the sec-
    Based on the observations in Section 4.2, different                          ond learning method to build the classification model and
streams present different changing patterns when CSI prop-                       improve the accuracy of WiFall.
agation is affected by human activities. To explore the spa-                        Fig. 7 is the flow chart of Random Forest algorithm. This
tial diversity, each stream generates the above seven                            classification is used to rank the importance of variables in a
features respectively and the features together constitute                       classification problem. To measure the variable importance
the input of the classification algorithm. The combined fea-                     in a dataset Dn ¼ fðXi ; Yi Þgni¼1 , we first fit a random forest
ture can represent a comprehensive characteristic of CSI sig-                    to the data. The out-of-bag error for each data point is
nal variations caused by the activity.                                           recorded and averaged over the forest during this process.
    In our application, falling belongs to the objective class,                  To measure the importance of the jth feature after training,
denoted as F . Other human movements belong to the non-                          the values of the jth feature are permuted among the train-
objective class. We use LOF to extract the anomaly series                        ing data and the out-of-bag error is computed on the per-
and build the classification model by utilizing LibSVM [39].                     turbed dataset. Then we compute an importance score for
Then, we apply one-class SVM to assign a label to each                           this feature by averaging the difference in out-of-bag error
group of the test data and recognize human falling from the                      before and after the permutation over all trees, and the score
other activities.                                                                is normalized by the standard deviation of the difference.
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
588                                                                    IEEE TRANSACTIONS ON MOBILE COMPUTING,             VOL. 16,   NO. 2,   FEBRUARY 2017




Fig. 8. Scenario 1: Chamber.                                                    Fig. 9. Scenario 2: Laboratory.

We rank the features with large values for this score as more                           Chamber. Chamber in Fig. 8 is an RF shielding sys-
important than the other features. By leveraging the Ran-                                tem, where wireless signals are absorbed instead of
dom Forest algorithm, we can distinguish fall activity from                              being reflected. Typically, chamber is a free space
the other activities by comparing the feature importance                                 indoor environment where there is no multipath. It
scores using our selected features, which could improve the                              is an ideal environment to test the influence of
fall detection accuracy.                                                                 human activities on CSI. In the chamber, there is
                                                                                         only one AP-MP link. AP is settled next to the wall
                                                                                         on one side of the chamber, and MP is settled at the
5     EXPERIMENTAL SETUP
                                                                                         opposite side, as shown in Fig. 11.
This section will illustrate the experimental setup and eval-                           Laboratory. Experiments are also conducted in an 8m
uation methods for WiFall. We will present the implementa-                                9m laboratory as shown in Fig. 9. Since the labora-
tion firstly, followed by the experimental scenarios and                                 tory is big and spacious, we can test the effective
evaluation metrics. Then, we analyze the signal properties                               range of one wireless link. In the laboratory, we eval-
of different activities and the examination of the effective                             uate the performance of WiFall with two different
detection range of a single wireless link. Finally, we will                              AP-MP deployments. Figs. 13 and 14 show the AP-
present the performance evaluation method and the user                                   MP link(s) deployments.
interface of WiFall.                                                                    Dormitory. Finally, we deploy WiFall in a student’s
                                                                                         dormitory, which is 4m  5m as shown in Fig. 10.
## 5.1 Implementation                                                                       The dormitory scenario is aimed to estimate the
We implement the proposed WiFall system with two                                         indoor environment of a typical living room. We
TP-LINK TL-WDR7500 wireless routers as the access points                                 deploy one AP-MP link in the dormitory as shown
(APs), and two 3.20GHz Intel(R) Pentium 4 CPU 2 GB RAM                                   in Fig. 12.
desktops equipped with Intel 5,300 NIC as the monitoring
points (MPs). The APs possess 3 detectable antennas, and
the MPs have three working antennas and the firmware is
modified as in [36] to report CSI to the upper layers. Two
APs and MPs form two 3  3 MIMO wireless links and
operate on IEEE 802.11n AP mode at 5GHz in order to get
free from crowded 2.4GHz interference in the experimental
environment. During the experiment, an MP collects CSIs
packets from its corresponding AP at the rate of 100 packets
per second. CSI packets are collected and sent to one of the
two MPs. The MP installed with MATLAB also works as
the server to conduct data processing, profile construction,
and activity decision.

## 5.2 Experimental Scenarios
We conduct experiments in three typical indoor environ-
ments in the campus of Hong Kong University of Science
and Technology, and test different layout schemes. The
detailed experimental scenarios are as follows:                                 Fig. 10. Scenario 3: Dormitory.
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
WANG ET AL.: WIFALL: DEVICE-FREE FALL DETECTION BY WIRELESS NETWORKS                                                                                      589




                                                                                 Fig. 13. Link layout and testing locations in the laboratory with one
                                                                                 AP-MP link.
Fig. 11. Link layout and testing locations in the chamber.
                                                                                 conducted in chamber is aimed to figure out whether we
## 5.3 Evaluation Metrics                                                           can leverage CSI variations caused by different movements
Two metrics are introduced to analyze the performance of                         to recognize human falling. During experiment, only one
WiFall: detection rate (DRfall ) and false alarm (FAfall ).                      male person performs each of the selected activities in the
DRfall is the probability that WiFall system can detect fall-                    middle of the chamber for 50 times.
ing movement, which is computed as:                                                  In the laboratory, the activities tested in the laboratory are
                                                                                 walking, standing up, sitting down, and falling. We both con-
                        number of truly detected fall                            sider long-time walking and short-time walking in our experi-
             DRfall ¼                                 :                 (15)
                           number of total fall                                  ment. The long-time walking means that the person walks for
                                                                                 1 minute and longer. The short-time walking means that the
FAfall refers to the proportion that the system generates an
                                                                                 person walks for several seconds (e.g., 10s, 15s, etc.) and then
alarm when there is no fall happens, which is computed as:
                                                                                 stops. Ten students (eight male and two female) with different
                      number of wrongly detected fall                            heights and weights participate in data collection. Each of
           FAfall ¼                                   :                 (16)     them performs each activity at eight different locations shown
                          number of total fall
                                                                                 in Fig. 13 for 200 times (25 times at each location).
                                                                                     We also test the prediction accuracies of all activity clas-
## 5.4 Evaluation Schemes                                                           sifications in the dormitory environment. The activities
We design different evaluation schemes in the three experi-                      tested in dormitory are the same with those in laboratory.
mental scenarios. During the experiment, one person per-                         We only consider short-time walking in dormitory, and we
forms as the user of WiFall and conducts the specific                            require that the person is resting before and after perform-
activities in the area of interest. We involve another person                    ing other three activities. We randomly select five locations
as the handler to monitor the action of the WiFall user. The                     as the testing location, shown in Fig. 12. To collect training
handler should stay outside the area of interest. The handler                    data, eight people conduct all the activities in the dormitory,
labels the received CSI data manually every second during                        and each of them performs each of the activity for 100 times
monitoring. When hearing the instructions from the han-                          (20 times at each location).
dler, the user of WiFall performs action promptly.
   In the chamber, we test sitting down, standing up and                         5.5 User Interface
falling. These three kinds of activities are similar, so it is                   We implement the user interface of WiFall and conduct real
hard to distinguish falling from the others. The experiment                      scenario experiments in the dormitory. The server side of




                                                                                 Fig. 14. Link layout and testing locations in the laboratory with two
Fig. 12. Link layout and testing locations in the dormitory.                     AP-MP links
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
590                                                                     IEEE TRANSACTIONS ON MOBILE COMPUTING,             VOL. 16,   NO. 2,   FEBRUARY 2017




Fig. 15. User interface of WiFall with falling probability.

WiFall is implemented using MATLAB showing the proba-
                                                                                 Fig. 16. LOF values of different activities.
bility of falling at the time unit, as shown in the bottom right
of Fig. 15. We also implement a client user interface under                      easier to be detected than the other in-place activities as
IOS operating system, as shown in the upper right of                             anomaly by WiFall.
Fig. 15. When a fall of the object person is detected, WiFall                       Two metrics are introduced to evaluate the anomaly
server will send alarm signal to the client. WiFall client pro-                  detection accuracy. The Detection Rate (DRanomaly ) is com-
vides the users with the current activity information and                        puted as:
alarms the users if a the fall alarm signal is received.
                                                                                                             number of detected anomaly
                                                                                            DRanomaly ¼                                 :                 (17)
6     PERFORMANCE EVALUATION                                                                                  number of total anomaly
In this section, we present the evaluation results of WiFall                     The false alarm of anomaly detection is defined as:
systems. We first show evaluation results of anomaly detec-
tion using LOF, and analyze the effective range of an AP-                                           number of wrongly detected anomaly
MP link. Then, we present how the height of an AP-MP link                            FAanomaly ¼                                       :                  (18)
                                                                                                        number of normal activity
will impact on fall detection accuracy. Finally, we present
the overall evaluation result of WiFall.
                                                                                    Fig. 17 shows the anomaly detection rate using LOF.
                                                                                 When the activities happen within 1.5m from the line
6.1 Anomaly Detection with LOF                                                   of sight path, 100 percent of DRanomaly can be achieved.
Anomaly activities are detected using LOF. Since multipath                       When the distance increases to 2.5m, DRanomaly decreases to
will cause differences in time delay, amplitude attenuation                      87 percent. When the distance is increased to 3m, the
and phase shifts, MP will receive several different signal                       DRanomaly is 84 percent. Consider the detection rate along
strengths from the same AP through multiple paths. The                           LOS at distance 3m, the rate of the middle two locations at
signal strength with the longest time delay and weakest                          one side is 89 percent, the rate of the other two locations is
power will usually be ignored. If a falling movement occurs
far from APs and MPs, the changes of the partially received
signal power may not be able to detect the movement. In
this part, we evaluate anomaly detection using LOF, and
define the effective range of an AP-MP link for activity
detection based on our observation.
   We conduct experiments in the laboratory to evaluate
anomaly detection. We examine whether an anomaly can
be detected using LOF effectively when the distance from
LOS is increased and determine the effective range. The
distances from the person and the LOS path are selected
as 1:5m, 2m, 2:5m and 3m. For each distance, we uni-
formly select eight locations (total 32 NLOS locations) for
testing. The distance between two successive locations at
one side is 1:5m. When the person performs an activity,
LOF will change significantly as shown in Fig. 16. Com-
pared with the other two in-place activities, walking leads
to a more obvious change in LOF values, since the loca-
tion of the person keeps changing. Thus walking is much                          Fig. 17. Anomaly DR when distance to LOS increases.
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
WANG ET AL.: WIFALL: DEVICE-FREE FALL DETECTION BY WIRELESS NETWORKS                                                                                      591


                                                                                                             TABLE 2
                                                                                               Experiment Results with One-Class SVM

## Precision         False Alarm
                                                                                        chamber                           96%                18%
                                                                                        laboratory-one link               88%                16%
                                                                                        laboratory-two links              94%                11%
                                                                                        dormitory                         83%                14%

Fig. 18. AP-MP link placement with different heights.
## 6.3 Performance of WiFall
78 percent. Meanwhile, we also observe that when a person                        In this section, we evaluate WiFall using RF and SVD, and
is resting at one of the selected 32 locations, anomaly is                       compare the result with the performance in [19].
detected only twice among the 128 tests, which means the                            Table 2 shows the fall detection results using a one-class
false alarm of LOF is less than 2 percent. From the evalua-                      SVM classifier with seven selected features from [19]. Table 3
tion results we can determine the effective range of WiFall.                     shows the evaluation results using an RF classifier with SVD
Since the coverage of wireless signal will be wider when the                     matrix factorization. Compared the results using RF and
transmission power of the AP increases, we can leverage                          SVD with the results of previous WiFall version, we observe
power control method to increase the signal transmission                         that new version of WiFall can achieve better performance
power of WiFall AP, thus increase the effective range. Due                       in all the experimental scenarios. This is one of the most
to the fact that the elderly always stay in a specific room                      important reasons that we choose this Random Forest as the
and the size of the rooms are limited, the effective range of                    algorithm for WiFall systems.
WiFall can cover the range of activities for the elderly.                           Meanwhile, we also observe that the false alarm of new
                                                                                 WiFall system is still above 10 percent. The major reason
## 6.2 Height of AP-MP Link                                                         of the high false alarm is that our dataset for falling is lim-
During falling, the position of the person will change signifi-                  ited currently. By using a larger training dataset, we can
cantly in the vertical plane. Therefore, the height of an AP-                    improve the performance of WiFall and decrease the false
MP link may affect the fall detection accuracy. To find the                      alarm. The feedback data from alerting phase can be uti-
link height which can provide most precise detection accu-                       lized to gradually enrich the training database.
racy, we test WiFall with AP-MP placements at different                             Another reason of high false alarm is that we mark the
heights. As shown in Fig. 18, we set the AP-MP link at three                     label of different activities manually, and the labeling rate is
heights: 0.15m, 0.55m, and 0.95m. We ask three people to                         much lower than the CSI sampling rate. From our experi-
conduct the experiment. During the experiment, one of the                        mental setting, we receive one CSI packet every 0.01s. How-
three people performs the activities (e.g., falling, standing                    ever, the handler person cannot label the data every 0.01s.
up, etc.) on LOS and NLOS path. The farthest distance from                       So, we ask the person to label the data of every 1s. It is rea-
the person’s location and LOS path is 1m. We evaluate the                        sonable that the label we give should represent the corre-
activity classification accuracy using RF learning algorithm                     sponding activity of the majority of data. By strictly control
after SVD matrix factorization. Fig. 19 shows the evaluation                     the experiment process, only a small number of errors will
results at different heights. When AP-MP is set at 0.55m,                        occur when the label represents the corresponding activity
WiFall can achieve best detection accuracy for all the activi-                   of the minority of data. This is because that different WiFall
ties. Therefore, we select 0.55m as the height for our AP-MP                     user will show different response time. We cannot thor-
placement, and use this height in our following experiments.                     oughly eliminate this uncontrollable factor, but we can
                                                                                 reduce the error probability caused by this reason with
                                                                                 automatic labeling. If we can automatically label the data at
                                                                                 the CSI sampling rate, we can apply a simple algorithm to
                                                                                 elect the label of the majority data, and then consider it to be
                                                                                 the label of the data in 1 second. It will help to decrease the
                                                                                 false alarm rate. We are now searching for an automatic
                                                                                 labeling method to decrease the false alarm.
                                                                                    We also observe that the location of the target person will
                                                                                 slightly affect the performance of WiFall. We divide the eight
                                                                                 locations in Fig. 13 into two groups (Group 1: 1/2/3/4,
                                                                                 Group 2: 5/6/7/8) and test the activity detection ratio with

                                                                                                             TABLE 3
                                                                                               Experiment Results with Random Forest

## Precision         False Alarm
                                                                                        chamber                           98%                15%
                                                                                        laboratory-one link               93%                13%
                                                                                        laboratory-two links              96%                10%
                                                                                        dormitory                         89%                12%
Fig. 19. Detection rates at different heights.
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
592                                                                    IEEE TRANSACTIONS ON MOBILE COMPUTING,             VOL. 16,   NO. 2,     FEBRUARY 2017




Fig. 20. Confusion matrix when user does actions at location 1, 2, 3, 4.


one AP-MP link in the laboratory. Since the location of the
person keeps changing during walking, we only consider
the three in-place activities (falling, sitting down, and stand-
ing up) and test the performance using RF. Figs. 20 and 21                      Fig. 22. Detection rates of activities from different status.
show the evaluation results at the locations 1/2/3/4 and at
5/6/7/8. We observe that when the action locations are                          and NLOS locations. The detection rate of other activities
closer to the AP-MP link, the performance of WiFall is better.                  also decrease. However, we still believe that WiFall can be
During standing up, the body of the user changes from a                         widely deployed since furniture is always placed at the cor-
lower position to an upper position, which is obviously dif-                    ner of a room where AP-MP link may not be blocked.
ferent from the other two activities. Therefore, we discover
that standing up can be distinguished easily.                                   6.4 Efficiency of SVD Matrix Factorization
   Falling after resting or walking may have different                          We also evaluate the time efficiency using SVD matrix fac-
impact on signal propagation, thus influence the fall                           torization. We select a 166 MB CSI dataset and use RF to
detection rate. We want to ensure that WiFall can keep a sat-                   classify the activities with or without using SVD. The data-
isfactory detection accuracy throughout. From previous                          set contains 48 test cases of three different activities at four
experiment, we observe that long-time walking and short-                        locations. As shown in Fig. 24, the average time to process
time walking will not affect the fall detection rate. Since the                 the data for activity classification without or with SVD are
size of the room is limited, the walking considered in this                     211.4s and 35.9s, respectively. The speedup using SVD is
evaluation is short-time walking. Fig. 22 shows the                             5.89. Using SVD matrix factorization, it takes less than 0.75s
evaluation result considering more specific activities (rest-                   to identify the activity of a test case, which proves that
ing-falling, resting-sitting, resting-walking, walking-falling,                 WiFall is able to support online activity monitoring. From
walking-sitting and walking-resting) at LOS path. When we                       this, we can conclude that SVD can highly reduce the proc-
only consider the activities starting from resting, the aver-                   essing time, thus achieve automatic fall detection.
age activity classification rate is 98 percent. When we con-
sider activities starting from resting (e.g., resting-falling)
and those starting from walking (e.g., walking-falling)                         7     CONCLUSIONS AND DISCUSSIONS
together, the rate decrease to 86 percent.                                      In this paper, we propose WiFall, a device-free fall detection
   We also evaluate the performance of WiFall when the                          system leveraging Channel State Information as the
AP-MP link in the lab is blocked. We use a desk to block the
LOS path of the AP-MP link, and asks volunteers to conduct
activities at both LOS and NLOS locations. Fig. 23 shows
that when the AP-MP link is blocked by the desk, the fall
detection rate decreases to around 60 percent both at LOS




Fig. 21. Confusion matrix when user does actions at location 5, 6, 7, 8.        Fig. 23. Performance of WiFall when AP-MP link is blocked.
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
WANG ET AL.: WIFALL: DEVICE-FREE FALL DETECTION BY WIRELESS NETWORKS                                                                                      593


                                                                                and Hong Kong RGC Grant HKUST16207714 and the Uni-
                                                                                versity of Macau Grant SRG2015-00050-FST. Kaishun Wu is
                                                                                the corresponding author.

## REFERENCES
                                                                                [1]    N. Noury, A. Fleury, P. Rumeau, A. Bourke, G. Laighin, V. Rialle,
                                                                                       and J. Lundy, “Fall detection-principles and methods,” in Proc.
                                                                                       29th Annu. Int. Conf. Eng. Med. Biolo. Soc., 2007, pp. 1663–1666.
                                                                                [2]    CDC, “Falls among older adults: An overview,” 2013, (Apr.).
                                                                                       [Online]. Available: http://www.cdc.gov/HomeandRecreatio-
                                                                                       nalSafety/Falls/adultfalls.html
                                                                                [3]    M. Alwan, P. J. Rajendran, S. Kell, D. Mack, S. Dalal, M. Wolfe,
                                                                                       and R. Felder, “A smart and passive floor-vibration based fall
                                                                                       detector for elderly,” in Proc. 2nd Int. Conf. Inform. Commun. Tech-
                                                                                       nol., vol. 1, pp. 1003–1007, 2006.
                                                                                [4]    H. Rimminen, J. Lindstrom, M. Linnavuo, and R. Sepponen,
                                                                                       “Detection of falls among the elderly by a floor sensor using the
                                                                                       electric near field,” IEEE Trans. Inform. Technol. Biomed., vol. 14,
                                                                                       no. 6, pp. 1475–1476, Nov. 2010.
                                                                                [5]    H. Foroughi, A. Naseri, A. Saberi, and H. S. Yazdi, “An eigen-
                                                                                       space-based approach for human fall detection using integrated
Fig. 24. Processing time with or without SVD.                                          time motion image and neural network,” in Proc. 9th Int. Conf. Sig-
                                                                                       nal Process., 2008, pp. 1499–1503.
indicator. WiFall aims to detect the fall of the elderly, and                   [6]    H. Foroughi, B. S. Aski, and H. Pourreza, “Intelligent video sur-
can also identify some other activities. WiFall takes advan-                           veillance for monitoring fall detection of elderly in home environ-
                                                                                       ments,” in Proc. 11th Int. Conf. Comput. Inform. Technol., 2008,
tages of the physical layer Channel State Information in                               pp. 219–224.
widely deployed off-the-shelf WiFi infrastructure. To dem-                      [7]    F. Bianchi, S. J. Redmond, M. R. Narayanan, S. Cerutti, and N. H.
onstrate the feasibility and effectiveness, we implement the                           Lovell, “Barometric pressure and triaxial accelerometry-based
WiFall servers on laptops with commodity 802.11n NICs                                  falls event detection,” IEEE Trans. Neural Syst. Rehabil. Eng.,
                                                                                       vol. 18, no. 6, pp. 619–627, Dec. 2010.
and conduct comprehensive experiment in three different                         [8]    J. Dai, X. Bai, Z. Yang, Z. Shen, and D. Xuan, “Perfalld: A pervasive
scenarios with various Tx-Rx layouts. Experimental results                             fall detection system using mobile phones,” in Proc. 8th IEEE Int.
show that WiFall can achieve an satisfactory fall detection                            Conf. Pervasive Comput. Commun. Workshops, 2010, pp. 292–297.
accuracy with acceptable false alarm rate.                                      [9]    K. Wu, J. Xiao, Y. Yi, M. Gao, and L. M. Ni, “Fila: Fine-grained
                                                                                       indoor localization,” in Proc. INFOCOM, 2012, pp. 2210–2218.
    At the present stage, WiFall can effectively identify                       [10]   J. Xiao, K. Wu, Y. Yi, L. Wang, and L. M. Ni, “Fimd: Fine-grained
the most common daily activities such as walking, sitting                              device-free motion detection,” in Proc. IEEE 18th Int. Conf. Parallel
down, standing up, and falling. More specific activities                               Distrib. Syst., 2012, pp. 229–235.
                                                                                [11]   D. Zhang, J. Ma, Q. Chen, and L. M. Ni, “An rf-based system for
will be considered in our future work. Same with other                                 tracking transceiver-free objects,” in Proc. 5th Annu. IEEE Int.
device-free activity recognition systems using wireless                                Conf. Pervasive Comput. Commun., 2007, pp. 135–144.
signals, WiFall is currently designed for and tested with                       [12]   X. Yu, “Approaches and principles of fall detection for elderly and
only one single person in the area of interest. Currently,                             patient,” in Proc. 10th Int. Conf. e-health Netw., Appl. Serv., Health-
                                                                                       Com, 2008, pp. 42–47.
it is difficult to identify the activity of a person among                      [13]   M. Mubashir, L. Shao, and L. Seed, “A survey on fall detection:
multiple users. When multiple people are conducting                                    Principles and approaches,” Neurocomputing, vol. 100, pp. 144–
different activities, their movements will cause mutual                                152, Jan. 2013.
                                                                                [14]   F. Adib and D. Katabi, “See through walls with wifi!” in Proc.
influence to the signal propagation. Considering an eas-                               ACM SIGCOMM Conf. SIGCOMM, 2013, pp. 75–86.
ier case, when only one person is conducting activities,                        [15]   F. Adib, Z. Kabelac, D. Katabi, and R. C. Miller, “3d tracking via
the locations of other objects will also influence the sig-                            body radio reflections,” in Proc. 11th USENIX Conf. Netw. Syst.
nal propagation paths. Therefore, it is nontrivial to pro-                             Des. Implementation, 2014, vol. 14, pp. 317–329.
                                                                                [16]   F. Adib, Z. Kabelac, and D. Katabi, “Multi-person localization via
pose a thorough propagation model considering the                                      RF body reflections,” in Proc. 12th USENIX Conf. Netw. Syst. Des.
relationship between signal variation and multiple                                     Implementation, 2015, pp. 279–292.
human activities. Meanwhile, it is too costly to build the                      [17]   Q. Pu, S. Gupta, S. Gollakota, and S. Patel, “Whole-home gesture
training database using learning methods since there are                               recognition using wireless signals,” in Proc. 19th Annu. Int. Conf.
                                                                                       Mobile Comput. Netw., 2013, pp. 27–38.
various combinations when considering different num-                            [18]   H. Abdelnasser, M. Youssef, and K. A. Harras, “Wigest: A ubiqui-
bers, activities and locations of objects. Nevertheless, we                            tous wifi-based gesture recognition system,” arXiv:1501.04301, 2015.
still believe that WiFall can be applied to important use                       [19]   C. Han, K. Wu, Y. Wang, and L. M. Ni, “Wifall: Device-free fall
                                                                                       detection by wireless networks,” in Proc. INFOCOM, 2014,
cases, and will greatly contribute to the human health-                                pp. 271–279.
care industry with wireless techniques.                                         [20]   Y. Wang, J. Liu, Y. Chen, M. Gruteser, J. Yang, and H. Liu,
                                                                                       “E-eyes: Device-free location-oriented activity identification using
                                                                                       fine-grained wifi signatures,” in Proc. 20th Annu. Int. Conf. Mobile
ACKNOWLEDGMENTS                                                                        Comput. Netw., 2014, pp. 617–628.
This research is supported in part by Guangdong Natural                         [21]   B. Wei, W. Hu, M. Yang, and C. T. Chou, “Radio-based device-free
                                                                                       activity recognition with radio frequency interference,” in Proc.
Science Funds for Distinguished Young Scholar (No.                                     14th Int. Conf. Inform. Process. Sens. Netw., 2015, pp. 154–165.
S20120011468), the Shenzhen Science and Technology Foun-                        [22]   W. Wang, A. X. Liu, M. Shahzad, K. Ling, and S. Lu,
dation (No. JCYJ20140509172719309, KQCX20150324160                                     “Understanding and modeling of wifi signal based human activ-
                                                                                       ity recognition,” in Proc. 21st Annu. Int. Conf. Mobile Comput.
536457), China NSFC Grant 61472259, 61370185, GDUPS                                    Netw., 2015, pp. 65–76.
(2015), Guangdong Young Talent Project 2014TQ01X238,
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.
594                                                                    IEEE TRANSACTIONS ON MOBILE COMPUTING,             VOL. 16,   NO. 2,   FEBRUARY 2017

[23] W. He, K. Wu, Y. Zou, and Z. Ming, “Wig: Wifi-based gesture rec-                                    Yuxi Wang received the BEng degree in com-
     ognition system,” in Proc. 24th Int. Conf. Comput. Commun. Netw.,                                   pute engineering from the Hong Kong University
     2015, pp. 1–7.                                                                                      of Science and Technology (HKUST) in 2013,
[24] K. Ali, A. X. Liu, W. Wang, and M. Shahzad, “Keystroke recogni-                                     and is currently working toward the PhD degree
     tion using wifi signals,” in Proc. 21st Annu. Int. Conf. Mobile Com-                                in computer science and engineering at HKUST.
     put. Netw., 2015, pp. 90–102.                                                                       Her research interests include wireless communi-
[25] L. Sun, S. Sen, D. Koutsonikolas, and K.-H. Kim, “Widraw:                                           cation, mobile computing, and wireless sensor
     Enabling hands-free drawing in the air on commodity wifi                                            networks. She is a student member of the IEEE.
     devices,” in Proc. 21st Annu. Int. Conf. Mobile Comput. Netw., 2015,
     pp. 77–89.
[26] M. Youssef, M. Mah, and A. Agrawala, “Challenges: Device-free
     passive localization for wireless environments,” in Proc. 13th
     Annu. ACM Int. Conf. Mobile Comput. Netw., 2007, pp. 222–229.                                     Kaishun Wu received the PhD degree in com-
[27] M. Seifeldin, A. Saeed, A. E. Kosba, A. El-Keyi, and M. Youssef,                                  puter science and engineering from the Hong
     “Nuzzer: A large-scale device-free passive localization system for                                Kong University of Science and Technology, in
     wireless environments,” IEEE Trans. Mobile Comput., vol. 12, no. 7,                               2011. After that, he worked as a research assis-
     pp. 1321–1334, Jul. 2013.                                                                         tant professor at the Hong Kong University of
[28] I. Sabek, M. Youssef, and A. V. Vasilakos, “Ace: An accurate and                                  Science and Technology. In 2013, he joined
     efficient multi-entity device-free wlan localization system,” IEEE                                Shenzhen University as a distinguished profes-
     Trans. Mobile Comput., vol. 14, no. 2, pp. 261–273, Feb. 2015.                                    sor. He has co-authored two books and published
[29] K. Wu, J. Xiao, Y. Yi, D. Chen, X. Luo, and L. M. Ni, “Csi-based                                  more than 80 refereed papers in international
     indoor localization,” IEEE Trans. Parallel Distrib. Syst., vol. 24,                               leading journals and premiere conferences. He is
     no. 7, pp. 1300–1309, Jul. 2013.                                                                  the inventor of 6 US and 43 Chinese pending pat-
[30] X. Guo, D. Zhang, K. Wu, and L. M. Ni, “Modloc: Localizing mul-            ents (13 are issued). He won the best paper awards at IEEE Globecom
     tiple objects in dynamic indoor environment,” IEEE Trans. Parallel         2012, IEEE ICPADS 2012, and IEEE MASS 2014. He received the 2014
     Distrib. Syst., vol. 25, no. 11, pp. 2969–2980, Nov. 2014.                 IEEE ComSoc Asia-Pacific Outstanding Young Researcher Award and
[31] J. Xiao, K. Wu, Y. Yi, L. Wang, and L. M. Ni, “Pilot: Passive device-      was selected as 1,000 Talent Plan for Young Researchers. He is a mem-
     free indoor localization using channel state information,” in Proc.        ber of the IEEE.
     IEEE 33rd Int. Conf. Distrib. Comput. Syst., 2013, pp. 236–245.
[32] H. Abdel-Nasser, R. Samir, I. Sabek, and M. Youssef, “Monophy:                                    Lionel M. Ni received the PhD degree in electri-
     Mono-stream-based device-free wlan localization via physical                                      cal and computer engineering from Purdue Uni-
     layer information,” in Proc. Wireless Commun. Netw. Conf., 2013,                                  versity in 1980. He is a chair professor in the
     pp. 4546–4551.                                                                                    Department of Computer and Information Sci-
[33] W. Yang, L. Gong, D. Man, J. Lv, H. Cai, X. Zhou, and Z. Yang,                                    ence and Vice Rector of Academic Affairs at the
     “Enhancing the performance of indoor device-free passive local-                                   University of Macau. Previously, he was a chair
     ization,” Int. J. Distrib. Sens. Netw., vol. 501, p. 256162, 2015.                                professor of computer science and engineering
[34] Z. Yang, Z. Zhou, and Y. Liu, “From RSSI to CSI: Indoor localiza-                                 at the Hong Kong University of Science and Tech-
     tion via channel response,” ACM Comput. Surveys, vol. 46, no. 2,                                  nology. As a fellow of the IEEE and Hong Kong
     p. 25, 2013.                                                                                      Academy of Engineering Science, he has chaired
[35] D. M. Pozar, Microwave Engineering. New York, NY, USA: Wiley,                                     more than 30 professional conferences and has
     2009.                                                                      received eight awards for authoring outstanding papers.
[36] D. Halperin, W. Hu, A. Sheth, and D. Wetherall, “Tool release:
     Gathering 802.11 n traces with channel state information,” ACM             " For more information on this or any other computing topic,
     SIGCOMM Comput. Commun. Review, vol. 41, no. 1, pp. 53–53,
                                                                                please visit our Digital Library at www.computer.org/publications/dlib.
     2011.
[37] M. M. Breunig, H.-P. Kriegel, R. T. Ng, and J. Sander, “Lof: Identi-
     fying density-based local outliers,” in ACM Sigmod Rec., vol. 29,
     no. 2, 2000, pp. 93–104.
[38] B. Sch€olkopf, J. C. Platt, J. Shawe-Taylor, A. J. Smola, and R. C.
     Williamson, “Estimating the support of a high-dimensional distri-
     bution,” Neural Comput., vol. 13, no. 7, pp. 1443–1471, 2001.
[39] C.-C. Chang and C.-J. Lin, “Libsvm: A library for support vector
     machines,” ACM Trans. Intell. Syst. Technol., vol. 2, no. 3, p. 27,
     2011.




      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:09:57 UTC from IEEE Xplore. Restrictions apply.

