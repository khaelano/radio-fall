IEEE TRANSACTIONS ON MOBILE COMPUTING,                VOL. 16,     NO. 2,    FEBRUARY 2017                                                              511




      RT-Fall: A Real-Time and Contactless Fall
    Detection System with Commodity WiFi Devices
                            Hao Wang, Student Member, IEEE, Daqing Zhang, Member, IEEE,
                          Yasha Wang, Member, IEEE, Junyi Ma, Yuxiang Wang, and Shengjie Li

       Abstract—This paper presents the design and implementation of RT-Fall, a real-time, contactless, low-cost yet accurate indoor fall
       detection system using the commodity WiFi devices. RT-Fall exploits the phase and amplitude of the fine-grained Channel State
       Information (CSI) accessible in commodity WiFi devices, and for the first time fulfills the goal of segmenting and detecting the falls
       automatically in real-time, which allows users to perform daily activities naturally and continuously without wearing any devices on the
       body. This work makes two key technical contributions. First, we find that the CSI phase difference over two antennas is a more
       sensitive base signal than amplitude for activity recognition, which can enable very reliable segmentation of fall and fall-like activities.
       Second, we discover the sharp power profile decline pattern of the fall in the time-frequency domain and further exploit the insight for
       new feature extraction and accurate fall segmentation/detection. Experimental results in four indoor scenarios demonstrate that RT-fall
       consistently outperforms the state-of-the-art approach WiFall with 14 percent higher sensitivity and 10 percent higher specificity on
       average.

       Index Terms—Fall detection, activity recognition, channel state information (CSI), WiFi, phase difference

                                                                                       Ç

1    INTRODUCTION

F    ALLS are the leading cause of fatal and nonfatal injuries
     to elders in the modern society [1]. According to the
Centers for Disease Control and Prevention, one out of three
                                                                                           increased depression. This fear cycle then increases the risk
                                                                                           of another fall [5].
                                                                                              For elders who live alone and independently, about 50 per-
adults aged 65 and over falls each year [2]. Falls not only                                cent of the falls occur within their own homes [1], thus timely
bring a main threat to elders’ health, they account for a large                            and automatic detection of falls has long been the research
part of medical cost as well. For example, in 2,000 falls                                  goal in the assistive living community. Various techniques
among older adults cost the U.S. health care system over                                   ranging from wearable sensor-based, ambient device-based
$19 billion dollars and the number increased to $30 billion                                to computer vision based solutions have been proposed and
dollars in 2010 [2]. Most elderly people are unable to get up                              studied [3], [6], [7], [8], [9], [10]. Wearable sensor-based
by themselves after a fall, studies have shown that the medi-                              approaches were among the first techniques developed for fall
cal outcome of a fall is largely dependent on the response                                 detection [11]. Since Lord and Colvin [12] proposed an accel-
and rescue time [3]. The delay of medical treatment after a                                erometer-based approach in 1991, numerous kinds of sensors
fall can increase the mortality risk in some clinical condi-                               have been explored for fall detection in the past decades,
tions, half of those who experienced an extended period of                                 ranging from gyroscopers [13], barometric pressure sensors
lying on the floor ( > 1h) died within six months after the                                [14], RFID [15], to the sensor-rich smart phones [16]. These
incident [4]. In addition to physical injuries and high medi-                              systems can only work when sensors are worn by the user.
cal cost, falls also cause psychological damage to elders,                                 However, the always-on-body requirement makes the subject
which is termed as the fear of falling cycle by the fall                                   difficult to comply with, especially for the elders at home.
researchers [5]. The fear cycle refers to the fact that after a                            Ambient device-based approaches try to make use of ambient
fall, even without injury, elders become so afraid of falling                              information caused by falls to detect the risky activity. The
again that they reduce physical activities. This in turn                                   ambient information being used includes audio noise [7],
decreases their fitness, mobility and balance, leads to                                    floor vibration [3], [6] and infrared sensing data [17]. In these
decreased social interactions, reduced life satisfaction and                               systems, dedicated devices need to be implanted in the envi-
                                                                                           ronment. However, the other sources of pressure or sound
                                                                                           around the subject in the environment account for a large pro-
   H. Wang, D. Zhang, J. Ma, Y. Wang, and S. Li are with the Key Laboratory               portion of false alarms. Computer vision-based approaches use
    of High Confidence Software Technologies, Ministry of Education, and                   cameras installed in the monitoring environment to either
    School of Electronics Engineering and Computer Science, Peking Univer-
    sity, Beijing 100871, China. E-mail: {wanghao, dqzhang}@sei.pku.edu.cn,
                                                                                           capture images or video sequences for scene recognition.
    {majunyi, wyxpku, lishengjie}@pku.edu.cn.                                              Although the recent advances in infra-red LED and depth
   Y. Wang is with the National Engineering Research Center of Software                   camera like Microsoft Kinect [18], [19], have enlarged its
    Engineering, Peking University, China. E-mail: wangys@sei.pku.edu.cn.                  application scope (e.g., independent of illumination of lights
Manuscript received 1 Sept. 2015; revised 10 Apr. 2016; accepted 12 Apr.                   and can work even in a dark room), the privacy intrusion,
2016. Date of publication 22 Apr. 2016; date of current version 5 Jan. 2017.               inherent requirement for line of sight and intensive computa-
For information on obtaining reprints of this article, please send e-mail to:
reprints@ieee.org, and reference the Digital Object Identifier below.                      tion for real-time processing are still open issues that need to
Digital Object Identifier no. 10.1109/TMC.2016.2557795                                     be addressed in the future [8], [10].
                                   1536-1233 ß 2016 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission.
                                       See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
512                                                            IEEE TRANSACTIONS ON MOBILE COMPUTING,      VOL. 16,   NO. 2,   FEBRUARY 2017


   Due to the limitations of the above-mentioned fall detec-           fall from the fall-like activities. Leveraging the previous
tion solutions, very few fall detection systems have been              work, we conduct intensive experiments using commodity
widely deployed in real home settings so far [20]. In recent           WiFi devices to empirically study how the amplitude and
years, the rapid development in wireless techniques has                phase difference of CSI change in both time and frequency
stimulated the research in studying the relationship                   domain in the presence of various human activities. In addi-
between the wireless signal and human activities. In partic-           tion to verifying that the phase difference is a more sensitive
ular, the recently exposed physical layer Channel State                base signal than the amplitude of CSI, we also observed that
Information (CSI) on commercial WiFi devices reveals mul-              the fall and fall-like activities are ended with a sharp power
tipath channel features at the granularity of OFDM subcar-             profile decline in the time-frequency domain. Based on
riers [21], which is much finer-grained than the traditional           these two insights, we design and implement our real-time
MAC layer RSS (Received Signal Strength). By exploiting                and non-intrusive fall detector, called RT-Fall. The fall
the amplitude and phase information of CSI across the                  detection process performed by RT-Fall mainly contains
OFDM subcarriers and the diversity of CSI information                  two-phases: First, we use the variance of phase difference as
across multi-antennas in MIMO systems, significant prog-               a base signal and design a set of filtering and signal process-
ress has been made in applications in motion detection [22],           ing techniques to robustly segment the fall and fall-like
[23], lip language [24] and gesture recognition [25], [26],            activities in the continuously captured WiFi wireless signal
vital sign monitoring [27], [28], and activity recognition [29],       streams. After singling out the fall and fall-like human
[30]. The rationale behind all these research efforts is that          activities in the wireless signal stream, we extract a set of
different human activities can cause different signal change           new features in both the time and frequency domain based
patterns, and activities can be recognized in real-time by             on the two insights to differentiate the real fall from the fall-
mapping the observed signal change patterns to different               like activities using Support Vector Machine (SVM).
human activities. With this motivation, in this paper, we                 In summary, the main contributions of this work are as
aim to investigate if real-time and automatic fall detection           follows:
can be achieved using cheap and widely deployed WiFi
devices at home, without requiring the subjects to wear or               1)    To the best of our knowledge, this is the first work to
carry any objects.                                                             deal with fall detection problem with commodity
   As far as we know, Wifall [29] is the first work using WiFi                 WiFi devices in the real settings, i.e., detect the fall in
commodity devices to detect fall. However, it makes two                        the condition that numerous daily activities are per-
assumptions: (1) the subject can only perform four kinds of                    formed naturally and continuously.
predefined activities (i.e., walk, sit, stand up, fall). (2) Activi-     2) We are the first to identify the phase difference of
ties can not be performed continuously. Obviously, both                        CSI as a better base signal than amplitude for activity
assumptions are not realistic in real home settings. There-                    segmentation and fall detection. By studying the
fore, in this work, we intend to remove these two assump-                      relationship between different human activities and
tions to detect the fall in the real settings, i.e., various daily             the variance of phase difference, we demonstrate its
activities are performed naturally and continuously.                           effectiveness as a base signal to segment the fall and
   In order to automatically detect falls in real-time with                    fall-like activities in the continuously captured signal
WiFi signals in the real settings, there are several challenges                streams.
that must be addressed. First, how the fall and other human              3) We found the sharp power profile decline pattern of
activities affect the amplitude and phase information of                       the fall in the time-frequency domain and further
CSI? Are there any specific features in the CSI of WiFi signal                 exploited the complementary characteristics of falls
streams which can characterize the fall and other human                        in the time and frequency domain for accurate fall
activities? Second, as activities are performed continuously,                  segmentation/detection.
the boundary of the WiFi signal of subsequent activities is              4) We design and implement the real-time activity seg-
not given. How to automatically and accurately segment                         mentation and fall detection system, RT-Fall on com-
the corresponding fall and other activities in the continu-                    modity WiFi devices, with only one antenna at the
ously captured WiFi wireless signal streams? Third, as there                   transmitter side, and two antennas at the receiver
are numerous daily activities, from the perspective of activ-                  side. Experiment results demonstrate that RT-Fall
ity recognition, the problem space is large. Even if the activi-               can segment the falls in the WiFi wireless signal
ties are segmented out, differentiating the fall from all the                  streams with an accuracy of 100 percent and consis-
other daily activities is also challenging.                                    tently outperform the state-of-the-art fall detector
   In our previous work [31], we observe that the phase dif-                   WiFall [29], with 14 percent higher sensitivity and
ference over two antennas exhibits interesting characteris-                    10 percent higher specificity on average.
tics in the presence of fall and other human activities, while            The rest of the paper is organized as follows. We first
the raw amplitude and phase information themselves are                 review the related work in Section 2 and then introduce pre-
not directly usable. Based on this observation, we proposed            liminaries in Section 3. In Section 4 we report the empirical
a transition-based segmentation method leveraging the var-             study results about the relationship between the WiFi CSI
iance of phase difference over a pair of receiver antennas as          information and the human activities, followed by the RT-
a salient feature to automatically segment all the fall and            Fall framework design. Section 6 presents the system perfor-
fall-like activities in the continuously captured WiFi wire-           mance evaluation results and then we discuss some unad-
less signal streams. Then we extracted features from both              dressed research issues in Section 7. Finally, we conclude
the amplitude and phase information of CSI to separate the             our work in Section 8.
WANG ET AL.: RT-FALL: A REAL-TIME AND CONTACTLESS FALL DETECTION SYSTEM WITH COMMODITY WIFI DEVICES                               513


2   RELATED WORK                                                    2.2 Related Work on WiFi-Based Activity
                                                                           Recognition
In this section, we review the related work from two per-
                                                                    The WiFi signal strength RSS has been exploited for indoor
spectives: research on fall detection and research on WiFi
                                                                    localization for more than a decade [32]. However, only
CSI-based activity recognition.
                                                                    recently research attempts have been made to use WiFi RF
                                                                    signal for gesture and activity recognition [25], [29]. While
## 2.1 Related Work on Fall Detection                                  [25], [33] first explore and use WiFi RF signal to recognize
Fall detection has attracted a lot of attention in assistive liv-   different body or hand gestures, they use dedicated instru-
ing and healthcare community for two decades. A great               ments to collect special RF signals, which are not accessible
number of fall detection techniques have been proposed              with commodity WiFi devices. With the CSI tractable on
since the early 1990s. Noury et al. [9], Yu [10], Natthapon         commodity WiFi devices [21], FCC [34] studies the relation-
et al. [20] and Spasova et al. [11] reviewed the principles         ship between the number of moving people and the varia-
and approaches used in existing fall detection systems.             tion of CSI and thus achieves device-free crowd counting.
Roughly, the fall detection systems can be classified into          Liu et al. [27] and Liu et al. [28] exploit the CSI from com-
three broad categories: wearable sensor based systems,              modity NICs to extract the human respiration and heart
ambient device based systems and computer vision based              beat rates in a controlled setting. Kosba et al. [22], Qian et al.
systems.                                                            [23], Liu et al. [35] and Wunon et al. [36] employ RSS and
   Wearable sensor based fall detection systems were                CSI information respectively to detect the human motion in
among the first efforts about fall detection. They attempt          indoor environment. Sigg et al. [37] use software radio to
to detect falls leveraging sensors embedded in wearable             improve the granularity of RSSI values and consequently
objects such as coat, belt and watch. Since Lord and                improve the accuracy of activity recognition. E-eyes [30]
Colvin [12] proposed an accelerometer based approach in             uses CSI amplitude histograms as fingerprints to recognize
1991, various kinds of sensors have been explored to                nine different daily human activities. Moreover, Wang et al.
detect fall in the past decades. The widely used sensors            [24] and Melgarejo et al. [26] leverage WiFi devices
include gyroscopes [13], barometric pressure sensors [14],          equipped with directional antennas to recognize lip and
RFID [15]. These detection systems can only work on the             gesture language respectively. However, all the above WiFi
premise that all the devices are worn or carried by the             based activity recognition work only deals with problems to
subject during fall. Smart phone based fall detector is one         recognize activities from a predefined activity set. Unfortu-
of the promising fall detection systems with great poten-           nately, the fall detection problem is far more complex. Spe-
tial due to the popularity of sensor-rich smartphones [16].         cifically, first, the fall should be singled out from various
While these solutions are appropriate for fall detection in         daily activities which can not be predefined or collected for
outdoor environment, the always-on-the-body require-                training and testing one by one. In other word, the countless
ments make the subjects difficult to comply with, espe-             human activities make the fall detection problem space very
cially for the elders at home.                                      large. Second, when various daily activities are performed
   The ambient device based fall detection systems intend           continuously, the boundary of the WiFi signal of subsequent
to detect falls in a non-intrusive way by exploiting the ambi-      activities is not marked. Identifying the starting and finish-
ent information including audio noise [7], floor vibration          ing point of interested activities for further training and
[3], [6], infrared sensing data [17] produced by a fall. The        classification is challenging.
rational behind these ambient device based fall detection               The first work using WiFi commodity devices to detect
systems is that different human activities will cause differ-       fall is presented in [29], where it exploits the WiFi CSI infor-
ent changes in acoustic noise or floor vibration. These solu-       mation for fall detection. But the work only makes use of
tions do not require the subject to carry or wear anything,         the amplitude information of CSI and simplifies the prob-
they are non-intrusive and more privacy-preserving than             lem, i.e., the subject can only perform four kinds of prede-
computer vision-based systems. However, dedicated devi-             fined activities. When the elders live normally in the home
ces need to be installed in the dwelling environment. More-         environment with various activities naturally and continu-
over, false alarms are often incurred by other sources              ously performed, the solution will fail. In our earlier work
causing the same effect. For example, an object fall might          [31], we attempted to leverage both the amplitude and
also cause similar effect in vibration or sound as an elder’s       phase information of CSI from commodity WiFi devices to
fall.                                                               detect fall in real-time. In particular, we proposed to use the
   Computer vision based fall detection systems use cam-            phase difference over two antennas as the salient feature for
eras installed in the monitoring environment to either cap-         both activity segmentation and fall detection. Different from
ture images or video sequences for scene recognition. By            our previous work, in this paper, we intensively study the
using activity classification algorithm, the fall activity is       relationship between the amplitude, phase, and phase dif-
distinguished from other events [8] ,[9] ,[10]. Recent advan-       ference of the CSI information and the human activities,
ces in infra-red LED and depth camera like Microsoft                respectively, and find that the phase difference is a more
Kinect [18], [19], have enlarged its application scope (e.g.,       sensitive base signal than amplitude or phase for activity
independent of illumination of lights and can work even in          recognition. Further more, we discover the sharp power
a dark room). However, there are still a set of open issues         profile decline pattern of the fall in the time-frequency
to be resolved, such as privacy concern, requirement for            domain. By leveraging the findings about the phase differ-
line of sight and intensive computation for real-time proc-         ence and the power profile decline pattern, we design a set
essing [8] ,[10].                                                   of signal processing techniques to robustly segment the fall
514                                                        IEEE TRANSACTIONS ON MOBILE COMPUTING,     VOL. 16,   NO. 2,   FEBRUARY 2017


## 3.2 Fall Activity Types Targeted
                                                                   There are many ways in which an elder can fall, and in this
                                                                   work we aim to detect falls occurred in situations with
                                                                   respect to two transition activities: 1): standing-fall refers to
                                                                   the situation that the fall occurs when an elder transfers out
                                                                   of a bed or chair, e.g., the elder may just stand up from the
                                                                   chair and falls down; 2): walking-fall refers to situation that
                                                                   the fall occurs while an elder is walking. According to a
                                                                   study by SignalQuest on falls for the elderly, 24 percent of
Fig. 1. WiFi signal propagation in indoor environment.             falls occurred in the first case and 39 percent occurred in the
                                                                   second [38]. Hence, we aim for 63 percent of the fall situa-
and a few fall-like activities from the other activities. Then     tions in this work and plan to address the other fall types
with only the fall and fall-like activities separated, we fur-     which occur while ascending or descending stairs or engag-
ther extract effective features from the amplitude and phase       ing in outdoor activities, in future work.
difference of CSI, to distinguish the real fall from other fall-
like activities, making the real-time fall detection leveraging    4   EMPIRICAL STUDY
the WiFi RF signal streams feasible in real home setting.
                                                                   In this Section, we conduct intensive experiments using
                                                                   commodity WiFi devices to empirically study how the
3     PRELIMINARIES                                                amplitude and phase information of CSI across the OFDM
                                                                   subcarriers and multi-antennas change in the presence of
In this section, we first introduce the concept of Channel
                                                                   different human activities at indoor environment.
State Information (CSI) in commodity WiFi devices, then we
specify the fall activity types targeted in this work.
## 4.1 Human Activities and Amplitude of CSI
                                                                   In this part, we explore the relationship between human
## 3.1 Channel State Information in IEEE 802.11n/ac                   activities and the amplitude information of CSI. We first
In a typical indoor environment, as illustrated in Fig. 1, WiFi    present how the amplitude varies across different subcar-
signals propagate through the physical space via multiple          riers and different streams respectively, and then we show
paths such as ceiling, floor, wall and furniture. As the physi-    how the amplitude changes in the presence of different
cal space constrains the propagation of wireless signals, the      human activities in Line-Of-Sight (LOS) and Non-Line-Of-
received signals in turn contain information that character-       Sight (NLOS) conditions.
izes the environment they pass through. If a person presents
in the environment, additional signal paths are introduced         4.1.1    Amplitude Across Different Subcarriers
by the scattering of human body. Then, the received signals                 and Streams
also convey information that characterizes the effects of
                                                                   As we only use one transmitter antenna and two receiver
human presence in the environment. If we consider the
                                                                   antennas, CSI information we collected is further divided
physical space (including ambient objects and human) as a
                                                                   into two wireless streams and thirty subcarriers in each
wireless Channel, the Channel State Information depicts the
                                                                   stream. In this study, we conduct experiments to see how
effects when the wireless signals pass through this wireless
                                                                   the amplitude varies across different subcarriers and differ-
Channel. In frequency domain, the channel can be modeled
                                                                   ent streams respectively. We have the same observation as
as Y ¼ HX þ N, where Y and X are the received and the
                                                                   [29] that human activities affect different streams indepen-
transmitted signal vectors respectively, N denotes the chan-
                                                                   dently whereas affect different subcarriers in a similar way.
nel noise vector and H is the channel matrix. The channel
                                                                   Furthermore, subcarriers among adjacent frequencies share
matrix H is presented in the format of Channel State Infor-
                                                                   more similarities than those with larger frequency gap.
mation. Specifically, current WiFi standards (e.g., IEEE
                                                                   Based on these observations, we can average CSI samples of
802.11n/ac) use orthogonal frequency division modulation
                                                                   adjacent successive subcarriers into one signal value to
(OFDM) in their physical layer. OFDM splits its spectrum
                                                                   achieve trade-off between computational complexity and
band (20 MHz) into multiple (56) frequency sub-bands,
                                                                   functionality. In the rest of this work, we will only show fig-
called subcarriers, and sends the digital bits through these
                                                                   ures with one subcarrier in one stream.
subcarriers in parallel. CSI reveals a set of channel measure-
ments depicting the amplitude and phase of every OFDM
subcarrier. CSI of a single subcarrier is in the following         4.1.2 Impact of Different Human Activities
mathematical format: h ¼ jhjejﬀu , where jhj and u are the         We roughly divide human daily activities into two catego-
amplitude and phase, respectively.                                 ries: immobile and motion activities.
   If there is no one or no motion in the environment, the            Impact of immobile human activities. Immobile activities,
channel is relative stable. However, as shown in red lines in      such as sitting, lying, and standing, intuitively result in rela-
Fig. 1, along with the motion of a person, the scattered sig-      tively stable signal change patterns as they only involve
nals are changing, which results in obvious channel distor-        tiny changes in human bodies (e.g., chest movement caused
tion, involving both amplitude attenuation and phase shift.        by respiration, tiny body movement unconsciously).
Human activity can be recognized by mapping different channel      Through extensive experiments, the results roughly fit the
distortion patterns to corresponding human activities.             intuition. Figs. 2a, 2c show the amplitude variance of three
WANG ET AL.: RT-FALL: A REAL-TIME AND CONTACTLESS FALL DETECTION SYSTEM WITH COMMODITY WIFI DEVICES                                                515




Fig. 2. CSI amplitude of human motion activities: (a) Sitting, (b) Lying, (c) Standing, (d) Lie down, (e) Upper body activities, (f) Pickup, (g) Squat,
(h) Walking, (i) Stand up, (j) Sit down, (k) Standing-Fall, and (l) Walking-Fall.


immobile activities, respectively. Interestingly, we have an                 weaker from LOS to NLOS conditions. This is expected
observation which was not mentioned in previous work                         because the signal propagation suffers from path loss [39].
that the signal variance of the standing posture seems more                  For example, as shown in red lines in Fig. 1, along with the
notable than that of other immobile activities like sitting                  motion of human body, the scattered paths from human
and lying. We also note that the amplitude variance of                       body keep changing. With the distance between human
standing reduces when the subject stands farther away                        body and LOS path increasing, those scattered power
from LOS path. Hence, we doubt whether the amplitude                         decreases rapidly until they become too weak to be distin-
can reliably distinguish between the standing posture and                    guished from the environment noise. Then we come up
other immobile activities. This inspires us to conduct a com-                with the following questions: how far away will the CSI ampli-
prehensive analysis on the impact of LOS/NLOS condition                      tude of the standing posture become indistinguishable from that of
before we can give the answer to this question.                              other immobile activities? And how far away will this base signal
   Impact of human motion activities. Compared to immobile                   of motion activities become indistinguishable from that of immo-
activities which result in relatively stable signal changes,                 bile activities?
motion activities, such as walking, lying down, sitting                          We conduct extensive experiments in different rooms of
down and fall, exhibit obvious signal variance as illustrated                different sizes, finding that the exact results vary slightly
in Figs. 2d, 2l. To differentiate the fall from other activities,            with respect to room settings and layouts. Using the settings
we tried to find some unique features of the fall at first.                  we adopt, the answer to the first question is around 2 m in a
Unfortunately, neither the variance of the amplitude nor the                 clear environment, and it drops to less than 1.5 m with a
profile of the amplitude shows clear patterns to make                        1 m high wooden desk and an LCD desktop screen on it as
the fall distinguishable from other activities. Therefore, the               an obstacle between the LOS and human. Considering the
amplitude can only tell whether the human subject is con-                    symmetry of both sides from LOS path, we find that the cov-
ducting motion activities or not.                                            erage area is not enough for common rooms. Hence, we con-
                                                                             clude that the ability of the CSI amplitude to distinguish the
## 4.1.3 Activities in LOS and NLOS Conditions                                  standing posture from other immobile activities is quite limited
                                                                             and unreliable in ordinary indoor living environments. The
As daily activities can occur in different locations in the
                                                                             answer to the second question is 5 m without obstacles from
indoor environment, we conduct activities in both LOS and
                                                                             LOS path and it drops to 4 m with the same wooden obsta-
NLOS conditions to see their impact. As illustrated in Fig. 3,
                                                                             cle. Considering the symmetry of both sides from LOS path,
the amplitude variance caused by human activities becomes
                                                                             the coverage area, even with 4 m, is big enough for a com-
                                                                             mon living room. Hence, the ability of the CSI amplitude to dis-
                                                                             tinguish the motion activities from immobile ones is enough and
                                                                             reliable in common living rooms.

## 4.1.4 Fall in Different Scenarios
                                                                             We then focus on falls, i.e., standing-fall and walking-fall,
                                                                             occurred in different scenarios, including LOS and NLOS.
                                                                             As illustrated in Fig. 4, the amplitude variance shows a clear
                                                                             transition from a fluctuated state to a stable one among all
                                                                             falls. This is expected because the fall often ends up with an
                                                                             immobile posture (e.g., lying on the floor/sofa) which
                                                                             results in a relatively stable signal change pattern. It seems
                                                                             that we could use the transition as a feature for real time
Fig. 3. CSI amplitude of activities in LOS and NLOS conditions: (a) LOS
Walking-Fall, (b) NLOS Walking-Fall, (c) LOS Sit down, (d) NLOS Sit          activity segmentation. Unfortunately, as numerous human
down, (e) LOS Standing, and (f) NLOS Standing.                               daily activities can end up with certain kind of immobile activities,
516                                                                  IEEE TRANSACTIONS ON MOBILE COMPUTING,        VOL. 16,   NO. 2,   FEBRUARY 2017




                                                                              Fig. 5. Raw Phase versus Phase Difference without human presence.
Fig. 4. Fall in different Scenarios: (a) Standing-Fall in LOS, (b) Walking-
Fall in LOS, (c) Standing-Fall in NLOS, and (d) Walking-Fall in NLOS.
                                                                              propagation time of the distance difference Dd (which is
singling out the real fall from all of these activity combinations is         around 12  sin u) between two antennas. Then " can be
very difficult, or even impossible.                                           roughly estimated as follows: [42]
    Previous work [29] did make use of the above feature
for real time activity segmentation, which was termed                                                    1=2 sin u    1
as Anomaly Detection. However, we argue that it over-                                               "                   ;
                                                                                                            cT        2Tf
simplifies the problem in two aspects, which limit its appli-
cability: First, the subject was assumed to stay in a controlled              where  is the wavelength, f is the central frequency, c is the
environment where only a few predefined activities were per-                  speed of light, T is the sample interval which is 50 ns in
formed. Hence when various undefined human activities are                     WiFi and u is the direction of arrival. As we select the WiFi
performed, the system will fail. Second, two predefined activi-               setting running on 5 GHz frequency, " is thus approxi-
ties should be separated by an immobile activity in between. In               mately equal to zero. Thus, we get the measured phase dif-
other words, the subject cannot perform activities in a natu-                 ference Dff as
ral and continuous manner, e.g., one cannot stand up from
                                                                                                    ^ ¼ Df þ Db þ DZf :
                                                                                                   Df
the chair and walk, instead, he should stand up first, stand                                          f   f
there for a while, and then walk. The limitations of the CSI
amplitude motivate us to explore if we can find a better                      Fig. 5 shows the raw randomly distributed phase and the
base signal for activity segmentation and fall detection.                     phase difference in a no human presence environment
                                                                              respectively. We can see that the randomly distributed raw
## 4.2 Human Activities and Phase of CSI                                         phase can be calibrated by conducting phase difference
As human activities can cause channel distortion which also                   over a pair of antennas. In the following sections, we con-
leads to signal phase shift, so we follow the same logic of                   duct experiments to see the relationship between human
the last section to study the relationship between human                      activities and the phase difference of CSI as we did for the
activities and the phase information of CSI.                                  amplitude.

## 4.2.1 Phase Calibration                                                       4.2.2    Phase Difference Across Different Subcarriers
As mentioned in [40], the measured phase f^f of CSI of sub-                            and Streams
carrier f can be computed as follows:                                         We have the similar observation for the phase difference as
                                                                              for the amplitude that human activities affect different sub-
                    f^f ¼ ff þ 2pff Dt þ b þ Zf ;                             carriers in a similar way and adjacent subcarriers behave
where ff is the true phase, Dt is the time lag at the antenna,                similarly. From the CSI stream perspective, as the variances
b is an unknown constant phase offset, Zf is some measure-                    of the phase difference across two antennas is the sum of
ment noise, ff is the carrier frequency offset at the receiver.               individual variance on each antenna,1 which implies that
   We find that the raw phases provided by commodity                          the phase difference is more sensitive to the environment
Intel 5300 NICs are randomly distributed and not usable,                      changes than the amplitude, thus the CSI phase difference
the reason lies in the term 2pff Dt, since Dt is different across             seems to be a better base signal compared to the CSI ampli-
subsequent packets. Recent work [41] shows that on a single                   tude for characterizing human activities.
commodity wireless NIC, the RF oscillators are frequency
locked at startup. So the ff across different antennas on the                 4.2.3 Impact of Different Human Activities
same NIC is actually the same value. This inspires us to                      Now we observe the phase difference caused by immobile
compute the phase difference Dff between two antennas as:                     and motion activities, respectively.
                                                                                 Impact of immobile human activities. As illustrated in
                  ^ ¼ Df þ 2pff " þ Db þ DZf ;
                 Df                                                           Figs. 6a and 6c, immobile activities such as sitting and lying,
                   f    f
                                                                              result in relatively stable signal change patterns in time
where Dff is the true phase difference, " ¼ Dt1  Dt2 (Dt1                    domain. One new observation is that the CSI phase differ-
and Dt2 are time lags at the antenna 1 and 2 respectively).                   ence signal fluctuates with the tiny human body movement.
Db is the unknown constant phase difference offset, DZf is
still the measurement noise. If we put two receiver antennas                      1. PhaseU [42] gives detail proofs about this conclusion, we refer
at the distance around 12  from each other, " indicates the                  interested readers to that work for further information.
WANG ET AL.: RT-FALL: A REAL-TIME AND CONTACTLESS FALL DETECTION SYSTEM WITH COMMODITY WIFI DEVICES                                                       517




Fig. 6. Phase difference of human motion activities: (a) Sitting, (b) Lying, (c) Standing, (d) Lie down, (e) Upper body activities, (f) Pickup, (g) Squat, (h)
Walking, (i) Stand up, (j) Sit down, (k) Standing-Fall, and (l) Walking-Fall.


Specifically, the CSI phase difference during standing shows an                 coverage area is enough for rooms with standard sizes, we
obvious fluctuation compared to that caused by sitting and lying,               argue that the phase difference over two antennas proves to be a
and we can see a clear difference between their patterns. As we                 robust base signal to distinguish between lying (sitting) and
also note that the boundary blurs as a subject is standing far                  standing. The answer to the second question is 6 m without
away from LOS path. Hence, we cannot jump to a conclu-                          obstacles from LOS path but it drops to 5 m with the same
sion that the phase can reliably distinguish between the                        desk as an obstacle. Considering the symmetry of both sides
standing activity and other immobile activities.                                from LOS path, we conclude that the phase difference is also a
   Impact of human motion activities. Compared to immobile                      better base signal than the amplitude to distinguish the motion
activities, motion activities lead to obvious CSI signal fluctu-                activities from immobile ones in common living rooms.
ation in the time domain as illustrated in Figs. 6d and 6l.
Again, there is still no obvious pattern to differentiate the                   4.2.5 Fall in Different Scenarios
real fall from other non-fall daily activities.
                                                                                As illustrated in Fig. 8, while most of the human activities,
                                                                                such as walking, running, standing and falling, all lead to
## 4.2.4 Activities in LOS and NLOS Conditions                                     obvious CSI phase difference fluctuation over time. Only
Not surprisingly, as illustrated in Fig. 7, the phase variance                  several immobile activities, such as sitting still and lying,
caused by human activities becomes weaker from LOS to                           result in very steady and stable signal pattern over the time.
NLOS conditions. Now we answer the previous two ques-                           In our previous work [31], it was found that only when peo-
tions with respect to phase difference.                                         ple fall down, lie down and sit down, the variance of the
   With the setting we adopt, the answer to the first ques-                     phase difference exhibits an obvious transition from the
tion is around 3.5 m in a clear environment and it drops to 3                   fluctuation state to the stable one, and then the state transi-
m with a 1 m high wooden desk and an LCD desktop screen                         tion of the CSI phase difference was used for real-time activ-
on it as an obstacle between the LOS and the human object                       ity segmentation.
as we did in Section 4.1.3. Compared to the amplitude, it                          Through extensive experiments, the state transition of the
seems that the CSI phase difference variance for the stand-                     CSI phase difference variance proves to be a robust feature
ing posture in both LOS and NLOS scenarios is amplified                         in time domain to segment all the fall activities from the
and the difference between the signal pattern of the stand-                     continuously received CSI streams. However, many “in-
ing and that of immobile activities becomes clearer. As the                     place” activities besides falling down, lying down and sit-
                                                                                ting down might also cause the state transition of the CSI
                                                                                phase difference, which leads to a lot of activities segmented
                                                                                out. Here “in-place” means the subject is conducting certain
                                                                                limb motions while lying or sitting. The transition happens




Fig. 7. Phase difference of activities in LOS and NLOS conditions: (a)
LOS Walking-Fall, (b) NLOS Walking-Fall, (c) LOS Sit down, (d) NLOS             Fig. 8. Fall in different Scenarios: (a) Standing-Fall in LOS, (b) Walking-
Sit down, (e) LOS Standing, and (f) NLOS Standing.                              Fall in LOS, (c) Standing-Fall in NLOS, and (d) Walking-Fall in NLOS.
518                                                             IEEE TRANSACTIONS ON MOBILE COMPUTING,      VOL. 16,   NO. 2,   FEBRUARY 2017




Fig. 9. Spectrogram for a series of different activities.


when the subject finishes certain in-place activities (such as          (at 68 s), and that of the sit down activity (at 25 s), we can see
eating, writing or making a phone call) and returns to the              that the fall shows an obvious sudden power decline from
immobile postures. As there are different kinds of in-place             high frequency to low frequency components, whereas the sit
activities, collecting all these activities for training and test-      down activity only shows a mild one. This unique characteris-
ing one by one for classification is difficult.                         tic of fall is probably caused by the uncontrollable state of the
                                                                        subject, because when a person falls, she would lose control of
## 4.2.6 Power Profile versus Daily Activities                             the body and experiences an accelerated moving stage before
In order to reveal more effective features for fall segmenta-           hitting the floor. As the subject hits the floor, the moving
tion and detection, we further use the Short-Time Fourier               speed of the body would change from high to zero, without a
Transform to profile the spectrogram of the CSI phase dif-              controlled de-accelerating stage like other fall-like activities
ference signal corresponding to various daily activities. As            such as sitting down.
shown in Fig. 9, it is interesting to see that different activities         However, we also notice that this gap becomes closer
have different power profiles and the frequency range con-              with the speed of the fall-like activity increasing, i.e., the
tributing to the power profile exhibits certain patterns. Spe-          power profile decline pattern of some quick fall-like activi-
cifically, we notice that:                                              ties looks similar to that of the fall. In particular, when the
                                                                        speed of the fall-like activities increases to a comparable one
  1)      The immobile postures such as sitting still (0-4 s, 11-       with that of the falls, we can no longer tell the difference
          14 s, 27-30 s) and lying still (68-72 s) have a weak          only by comparing the power profile decline pattern.
          power profile, as there is no any obvious body
          movement.                                                     4.3 Summary
   2) The “in-place” activities such as making a phone call             In this section, we conduct extensive experiments to study
          while sitting (4-10s) and standing (36-41 s) have a           how the amplitude and phase difference of the CSI change
          mild power profile contributed mainly by the low              in the presence of different human activities at indoor envi-
          frequency components (<5Hz), which are generated              ronment. As previous work only exploits the amplitude
          mainly the limb movement.                                     information, we start from that and find that the CSI ampli-
   3) All the motion activities such as walking (17-21 s, 33-           tude can only tell whether a subject is performing motion
          36 s, 41-46 s, 61-65 s), standing up (14-17 s), jumping       activities or not. This can be useful for activity segmentation
          (53-61 s), turning around and sit down (21-26 s), and         with simplified assumptions made in previous work [29].
          falling (66-68 s) have a strong power profile with            However, it can not work well when various daily activities
          both low frequency [0, 5 Hz] and high frequency               are performed naturally and continuously. The limitations
          components (>5 Hz), which are generated by both               of the CSI amplitude motivate us to explore the phase infor-
          limb and torso movement.                                      mation in human activity recognition. Unfortunately, we
   4) While the falls and sitting/lying down activities                 observe that the raw phases provided by commodity WiFi
          show a sharp power profile decline from high fre-             devices are randomly distributed and thus not usable. After
          quency to low frequency components (68 s, 25 s), the          analyzing the reason, we take the phase difference across a
          “in-place” activities won’t cause such a sudden               pair of receiver antennas for phase calibration. Interestingly,
          power profile decline as the power profile of ”in-            we observe that the phase difference is more sensitive than
          place” activities mainly lies in the low frequency            the amplitude, further more, it can distinguish standing
          range (<5 Hz).                                                from other immobile activities such as sitting and lying.
    Hence, by detecting the state transition of the CSI phase           Based on this observation, our previous work proposed a
difference variance along with the sharp power profile                  simple transition based segmentation method, expecting to
decline pattern, we can robustly rule out the “in-place”                single out only the fall and a few fall-like activities (i.e., sit-
activities but segment only the fall and a few other non-fall           ting and lying) in the continuously captured CSI streams.
activities (i.e., lying down and sitting down). We refer those          However, we found that some “in-place” activities may also
few other non-fall activities as fall-like activities.                  be segmented out as fall-like activities, which lead to diffi-
    Zooming in the power profile of the fall and fall-like activi-      culties in accurate fall detection. Fortunately, we find the
ties, it is noticed that while the fall and fall-like activities both   sharp power profile decline pattern, which is always associ-
end up with a sharp power profile decline, the falls often              ated with fall and fall-like activities, but not with “in-place”
exhibit even a sharper power profile decline pattern than the           activities. Furthermore, we also see that the power profile
fall-like activities. For example, as shown in Fig. 9, comparing        decline patterns of the fall and fall-like activities often look
the power profile before and after the ending point of the fall         quite different. Thus, by combining the state transition of
WANG ET AL.: RT-FALL: A REAL-TIME AND CONTACTLESS FALL DETECTION SYSTEM WITH COMMODITY WIFI DEVICES                                 519


                                                                    within [0, 4 Hz]. Furthermore, these body motions are
                                                                    embedded in all the human activities. Hence, it is reason-
                                                                    able to conduct a band-pass filter to filter out the signal com-
                                                                    ponents which are below the frequency of 4 Hz. Through
                                                                    experiments, we find the frequency range that can filter-out
                                                                    the non-relevant activities yet well characterize the fall and
Fig. 10. The RT-Fall system framework.                              fall-like activities lies in [5, 10 Hz].

the CSI phase difference variance with the sharp power pro-         5.2 Activity Segmentation
file decline pattern, we not only resolve the “in-place” activ-     The main function of the activity segmentation module is to
ity issue for segmentation, but also provide new clues for          single out the fall and fall-like activities from the continu-
fall detection.                                                     ously received CSI streams. It consists of two steps: in step
                                                                    one, the finishing point of the fall or fall-like activities is
5    FRAMEWORK & METHODOLOGY                                        identified automatically by processing the variance of CSI
Our proposed real-time and contactless fall detector, RT-           phase difference; then in step two, the starting point of the
Fall, consists of three functional modules: signal preprocess-      fall or fall-like activities is determined by selecting a proper
ing, fall-like activity segmentation and fall detection. As shown   trace back window size from the finishing point.
in Fig. 10, the system takes the CSI signal streams as input,
which can be collected at the receiver side using two               5.2.1     Identify the Finishing Point of Fall or Fall-Like
receiver antennas of a commodity WiFi device (e.g., Intel                     Activities
5300 NIC). Each CSI signal stream contains CSI readings             In the empirical study section, it was found that the state
from 30 subcarriers on a wireless stream and totally two CSI        transition of the CSI phase difference variance is a robust
streams are collected in the experiment between one trans-          base signal to detect the fall and fall-like activities (i.e., lying
mitter antenna and two receiver antennas. The CSI sam-              down, sitting down). Based on the two observations
pling rate is set to 100 pkts=s as [29]. The system can take        described previously, we propose a two-phase segmentation
advantage of CSI measurements from existing traffic across          approach to separate the fall and fall-like activities from
these links, or if insufficient network traffic is available, the   other activities in the continuously received CSI streams.
system might also generate periodic traffic for measurement            In phase one, we use a threshold-based sliding window
purposes.                                                           method to determine if the raw phase difference signal and
                                                                    the band-pass filtered phase difference signal are in the fluc-
## 5.1 Signal Preprocessing                                            tuation state or stable state. This process consists of three
The goal of signal preprocessing is two-fold: 1) dealing with       steps: First, we collect the two signal streams in stable state
the uneven arrival of packets caused by the bursty Wi-Fi            (e.g., lying/sitting in LOS path) across multiple sliding win-
transmissions to make the signal stream continuous for fur-         dows off-line and calculate their mean m and the normal-
ther signal processing; 2) filtering out signal noises which        ized standard deviation s, respectively; Then, we determine
won’t contribute to fall segmentation and detection. The            the threshold value d for both signal streams as: m þ 6s  d.
above two goals are achieved by applying the following              In the last step of phase one, we acquire the two signal
two techniques: interpolation and band-pass filtering.              streams in a sliding window on-line as shown in Fig. 11b
                                                                    and see if they are in the fluctuation state or stable state, by
## 5.1.1 Interpolation                                                 comparing the mean value in the sliding window with the
                                                                    threshold d. If the mean value is smaller than d, the signal is
Wi-Fi is a shared channel, where multiple devices use ran-
                                                                    said to be in the stable state, otherwise it is in the fluctuation
dom access to share the medium. This results in the
                                                                    state.
received packets that are not evenly spaced in time domain.
                                                                       In phase two, we detect the transition from the fluctua-
Two problems may occur if the arrival of packets is not
                                                                    tion state to stable state for both the raw phase difference
evenly spaced: 1) the sampled CSI readings during the fall
                                                                    signal and the band-pass filtered phase difference signal,
may not be continuous, which makes it difficult for feature
                                                                    and determine the finishing point of the fall and fall-like
extraction; 2) unevenly spaced samples in time domain pre-
                                                                    activities by checking if both signals enter the stable state.
vent Time-Frequency analysis to obtain the spectrogram. To
                                                                    The process contains two steps: In step one, we keep track-
get evenly spaced samples, we adopt the 1-D linear interpo-
                                                                    ing of the state of two signals and checking if there is a
lation algorithm as suggested in [43] to process the raw CSI
                                                                    transition occurring from the fluctuation state to stable
readings.
                                                                    state. When such a transition happens, we mark the time
                                                                    t1 as shown in Fig. 11b and start monitoring the state of
## 5.1.2 Band-Pass Filter                                              the other signal. If the other signal also enters the stable
The interpolated CSI signal stream is then fed into a band-         state within a timelag Dt from t1, we mark the instant
pass filter to further rule out irrelevant signal frequency         t2 ¼ t1 þ Dt as the finishing point of the fall and fall-like
components. As the speed of chest movement caused by                activities.
respiration or slight body movement are relatively low com-            The rationale behind detecting the two signal state transi-
pared to that of the fall, the signal changes caused by these       tions for the fall and fall-like activity segmentation is that
motions mainly lie in the lower frequency range, often              we detect the CSI phase difference transition as the first
520                                                                   IEEE TRANSACTIONS ON MOBILE COMPUTING,            VOL. 16,   NO. 2,   FEBRUARY 2017




Fig. 11. Fall and fall-like activity finishing point identification: (a) Phase difference across a continuously performed activities. (b) The corresponding
sliding standard deviation of (a). d1 and d2 are the thresholds for the raw and band-pass filtered phase difference, respectively.

criteria and then filter out the “in-place” activities by check-               decide the proper trace back window size to collect training
ing the band-pass CSI phase difference variance. If we only                    data samples for accurate fall detection. The window sizes
track the state transition of the raw phase difference vari-                   tested in previous fall detection work were ranging from
ance as we did in our previous work [31], the “in-place”                       0.32 s [44], 1 s [45], to 10 s [46] according to the adopted sen-
activities may also be segmented out as fall-like activities.                  sors and fall detection methods. Considering the duration
As shown in the grey-dashed line of Fig. 11b, when the sub-                    and characteristics of the fall and other fall-like activities in
ject stops making a phone call, the raw phase difference                       time domain, we perform intensive experiments to choose
shows a state transition (at 9 s), which meets our previous                    the best window size with trial-and-error method. It was
segmentation criteria. If we only track the state transition of                found that the best window size is three seconds, compos-
the band-pass filtered CSI phase difference variance, we                       ing a two-second signal segment before the finishing point
will no longer distinguish the lying (sitting) from standing,                  and a one-second signal segment after, representing the
as the energy-band caused by standing activity lies in the                     whole segmented activity stream.
same frequency range as for the in-place activities. As
shown in the solid-blue line of Fig. 11b, when the subject                     5.3 Fall Detection
finishes walking and then stands still, the band-pass filtered                 After determining the starting and finishing point of the fall
phase difference shows a transition (at 36 s) from the fluctu-                 and fall-like activities, only the CSI phase difference and
ation state to stable state. As the fall is always accompanied                 amplitude of those activities are singled out. The goal of the
by a CSI phase difference state transition and a sharp power                   Fall Detection module is to separate the fall from fall-like
profile decline where the energy from the high frequency to                    activities.
low frequency components all drops within a very short
period of time, which inspires us to track the state transi-                   5.3.1 Feature Extraction
tions of both signals as well as the time lag. In particular,                  Through extensive study, we extracted the following eight
the shorter the Dt is, the sharper the power profile decline is.               features from the real time captured CSI streams for activity
    As shown in Fig. 11a, we depict the CSI phase difference                   classification: (1) the normalized standard deviation (STD)
of a series of activities performed continuously and label                     of CSI, (2) the median absolute deviation (MAD), (3) the off-
the corresponding activities. While Fig. 11b shows the fall                    set of signal strength, (4) interquartile range (IR), (5) signal
and fall-like human activity finishing point identification                    entropy, (6) the velocity of signal change, (7) the TimeLag,
results based on our two-phase segmentation approach. It                       (8) the power decline ratio (PDR). As the first six features
can be seen that only the fall and fall-like activities are iden-              are used and explained in [29] for activity classification,
tified, while other activities such as making a phone call,                    here we only elaborate the two new features.
standing up and walking are left out.                                             Both TimeLag and PDR are proposed based on the obser-
                                                                               vation that the fall and fall-like activities are different from
## 5.2.2    Determine the Proper Trace Back Window Size                           the signal power profile perspective. TimeLag characterizes
         for Fall-Detection                                                    the time delay of the state transition point between the
Based on the CSI phase difference state transition detection,                  band-pass filtered and the raw phase difference as shown in
we can identify the finishing point of fall and fall-like activi-              Fig. 11b, we can see that the time lag for the fall is usually
ties in the continuously captured WiFi signal streams. To                      much shorter than that of the sit down activity. If we com-
differentiate the fall from fall-like activities, we need to                   pute the one-second accumulated power before and after
WANG ET AL.: RT-FALL: A REAL-TIME AND CONTACTLESS FALL DETECTION SYSTEM WITH COMMODITY WIFI DEVICES                                      521




                                                                           Fig. 13. User interface.


                                                                           indicates the upper bound on the fraction of training errors
                                                                           and the lower bound of the fraction of support vectors, leav-
Fig. 12. Four test environments: office (a), Apartment (b), Meeting Room
(c), and Hall (d).                                                         ing other parameters as default.

the finishing point, then the PDR is defined as the power                  6    EVALUATION
decline ratio which is the one-second power loss divided by
the one-second accumulated power before the finishing                      In this section, we present the implementation and evalua-
point. PDR is computed with the following mathematical                     tion results of our RT-Fall system using commercial off-the-
formula:                                                                   shelf WiFi devices.
               Pt^      Pfh             Pt^þ1 Pfh
                         f¼fl et;f vf 
                 t¼t^1                     t¼t^   f¼fl et;f vf
## 6.1 Experimental Setups
       PDR ¼              Pt^      Pfh                          ;          We evaluate our RT-Fall system using an 802.11n WiFi net-
                            t¼t^1    f¼fl et;f vf                         work consisting of one or more off-the-shelf WiFi devices
                                                                           (laptop or mini-pc) and a commodity wireless access point
where t^ is the finishing point, t^1 is the instant of one second         (i.e., TP-Link WDR5300 Router with one antenna running
before t^ and the t^þ1 is that of one second after t^. fl and fh           on 5 GHz). The laptop/mini-pc is equipped with an Intel
refer to the frequency range from [0, 50 Hz]. et;f is the power            WiFi Link 5,300 card for measuring CSI [21] and with two
strength of a specific frequency f at a specific time t. vf is             internal antennas. The packet transmission rate is set to
the weight vector for each frequency f.                                    100pkts=s.
   Different from WiFall [29] that only extracts features                      We conduct experiments in four different environments
from the CSI amplitude information, we extract the first six               to show the generality of our system. The experimental
features from both CSI amplitude and phase difference, and                 setup and settings in these environments are shown in
extract the two new features from phase difference only. They              Fig. 12. The first test environment (i.e., office) has the size of
together constitute the input of the SVM Classifier.                       about 3 m  4 m with one sofa, two tables and one bookcase
                                                                           (see the photo inside Fig. 13); the second test environment is
5.3.2 SVM Classifier                                                       an apartment with two bedrooms and one living room,
To detect the fall among the segmented activities, the n-SVM               equipped with a group of sofas, two tables and two beds;
classifier [47] is applied using the features extracted above.             the third test environment (i.e, meeting room) is about
All the samples are divided into objective class (i.e., the fall)          6 m  6 m with a long meeting table and dozens of chairs
and non-objective class (i.e., fall-like activities). To solve the         around, the fourth one is a big hall with the size of
non-linear classification problem, it maps input samples                   12 m  6 m.
into a high dimensional feature space by using a kernel
function and finds the maximum margin hyperplane in the                    6.2 Dataset
transformed feature space. The SVM classifier requires a                   We recruit 6 volunteers (five male and one female; age: 21-
training dataset and test dataset. In the process of classifica-           32 years; height: 1.6-1.83m; weight: 61-82 kg) to perform var-
tion model construction, fall and fall-like activities are seg-            ious daily activities in the four test environments over two
mented and labeled in the continuously captured WiFi                       months. Each data record consists of a continuous stream of
wireless signal streams in the activity segmentation phase.                activities, mixing the fall, fall-like and other daily activities.
Then the extracted features along with the corresponding                   These activities include the specified Activities of Daily Liv-
labels are fed into the SVM classifier to build the classifica-            ing(ADL) summarized in [20] (e.g., standing, walking, run-
tion model. In the process of real-time fall detection, the                ning/jogging, jumping, sitting down, getting up from
classification results along with the data samples will be                 chair/bed, lying down, picking up object, ...) and other com-
recorded. With the user feedback, the wrong classification                 mon activity types (e.g., answering phone, eating, perform-
results will be re-labeled correctly and the model updating                ing exercise like push-up). We let the subjects to fall
process will be triggered in time to update the classification             naturally but provide a mattress to protect the subjects from
model. We create the n-SVM classification model by utiliz-                 being injured. Specifically, the subjects performed the fall
ing LibSVM [48] with the Gaussian Radial Basis Function                    according to their experiences to simulate the sudden loss
(RBF) kernel chosen and set the parameter n to be 0.5, which               of balance, including forward, backward, sideward and
522                                                               IEEE TRANSACTIONS ON MOBILE COMPUTING,          VOL. 16,   NO. 2,   FEBRUARY 2017




Fig. 14. Confusion matrix.


backward fall while walking or standing.2 We install a cam-
era in each room to record the activities conducted as the
ground truth. The web-based user interface of our system is
shown in Fig. 13, where the recorded video, the amplitude
and phase difference of CSI, the segmented activity from
CSI stream, and the detection results are updated on-line in
real-time. When the system is started, a subject can perform
any activities naturally and continuously,2 and the system
will automatically segment CSI streams and report the seg-
mentation/detection results in real-time on the user inter-
face. Based on the recorded activity video and detected
results, it is very easy for the user to report the test results,
ranging from the number of falls performed and detected,                   Fig. 15. System performance and Number of Participants: (a) Experiment
to the fall-like activities performed and detected. In all the             design. (b) Performance evaluation with different number of people.
following sections, we let subjects to perform activities, and             MfSg > x means building the model MfSg from the training data of
                                                                           the people set S to evaluate the performance with the dataset of user x.
ask a separate student to record the full experiment results
for performance evaluation purposes.
                                                                           and the system uses the training data from the subject set S to
## 6.3 Baseline Method and Performance Metrics                                build the model MfSg. In the testing phase, each subject x
In the experiments, we use the state-of-art fall detector                  conducts 40 falls and 80 fall-like activities respectively to eval-
WiFall proposed in [29] as the baseline. Since WiFall cannot               uate the performance using the model built from the training
segment the fall and other daily activities reliably, we thus lever-       data of the subject set S, and the evaluation results of each
age our proposed method to segment the fall and fall-like activities,      experiment group are shown in Fig. 15b, where the classifica-
subsequently we compare its activity classification perfor-                tion model M is built with the training dataset and the tests
mance with that of our approach using our dataset. We use                  are done using those models for different number of partici-
the following two standard metrics for performance evalua-                 pants. For example, at the beginning, as the training data set is
tion—sensitivity and specificity. The confusion matrix is                  empty, we collect training data from the first subject a to build
shown in Fig. 14 to define sensitivity and specificity.                    a model Mfag (see first row in Fig. 15a), which refers to the
   Sensitivity is defined as the percentage of correctly                   model built with one participant’s dataset (user a performed
detected falls: sensitivity ¼ TP =ðTP þ FNÞ                                100 falls and 100 fall-like activities, spending 6 hours in 2
   Specificity is defined as the percentage of correctly                   days’ time), and then test the performance on subject a using
detected non-fall activities: specificity ¼ TN=ðTN þ FP Þ.                 model Mfag from the training data of himself (see second
                                                                           row: Mfag ! a ). Then the second subject participates in the
                                                                           experiments to evaluate the performance using the model
## 6.4    System Performance and Number of                                    Mfag (see third row: Mfag ! b) to see if we can get consis-
       Participants                                                        tent performance as the first subject. If not, we go on collecting
As different people perform activities in different ways, for              training data from the second subject (see fourth row) to
example, some sit down faster, while some fall slower, thus                increase the training data set and build the model Mfa; bg,
we design a set of experiments in the office room to see how               and so on so forth, until we get roughly consistent perfor-
many subjects’ training data is sufficient for obtaining stable            mance with the smaller training dataset.
and satisfactory test results, through testing the system per-                 According to Fig. 15b, Mfag ! a has the best result, but
formance with increasing the number of participants                        it lacks generality to detect falls of other people accurately;
involved. Considering that the activities can occur in differ-             with the number of participants increasing to three, the per-
ent places and from different directions as shown in                       formance obtained with the model built from three subjects’
Fig. 12a, we ask the participants to evenly cover all the situa-           training data tends to converge, which is a little lower than
tions when they perform experiments.                                       that of Mfag ! a. This is expected because Mfag ! a cor-
   As shown in Fig. 15a, the experiments consist of two                    responds to a personalized model, whereas Mfa; b; cg corre-
phases: training data collection phase and testing phase. In               sponds to a generalized one that is trained for more people.
the training data collection phase, we collect the training data-          Furthermore, according to the videos recorded, in the train-
set by increasing the number of participants involved, each                ing and testing phases, all the 620 falls are 100 percent seg-
subject conducts 100 falls and fall-like activities respectively,          mented out. Averaging the performance of the last three
                                                                           experiment groups, i.e., Mfa; b; cg ! d; e; f, we achieve
    2. A demonstration video has been recorded and uploaded to You-        93 percent of sensitivity and 89 percent of specificity in the
Tube (please see: https://youtu.be/WgTnKjr5xow) and Youku (see:            office room. In the rest of this section, we use the generalized
http://v.youku.com/v_show/id_XMTQ1NDg1ODIyOA==.html?
from= s1.8-1-1.2) to show how various activities and falls are conducted   model built from three subjects’ training data for further
in the natural setting.                                                    evaluation.
WANG ET AL.: RT-FALL: A REAL-TIME AND CONTACTLESS FALL DETECTION SYSTEM WITH COMMODITY WIFI DEVICES                               523




                                                                     Fig. 17. Robustness to furniture location change.


                                                                     of the other WiFi device. Knowing this information is tanta-
                                                                     mount to knowing which area the subject is in. In the testing
                                                                     phase, three different students (d, e, f) were invited to per-
                                                                     form daily activities and evaluate the performance of these
                                                                     models built from the training data set with the subject set
                                                                     (a, b, c). Averaging the evaluation results with the three stu-
Fig. 16. Performance comparison in different rooms: (a) Experiment   dents for each room, we get the performance comparison
design. (b) Performance results.                                     results in Fig. 16b. In general, RT-Fall achieves 91 percent of
                                                                     sensitivity and 92 percent of specificity. Compared to the
## 6.5 System Evaluation and Comparison                                 baseline method WiFall, RT-Fall gets 14 percent higher sen-
In this part, we first compare the performance of RT-Fall            sitivity and 10 percent higher specificity.
with that of the baseline method WiFall [29] in four different
test environments, in terms of sensitivity and specificity.          6.5.2 Robustness
Then, we evaluate the system robustness of RT-Fall system            As wireless signal is said to be very sensitive to environ-
with respect to various environment changes.                         ment, we thus evaluate the robustness of our approach
                                                                     against setting changes, including opening the door and
## 6.5.1 Performance Comparison                                         window, switching on/off the light, moving the furniture
We design experiments in four test environments as shown             around, and testing in different rooms. While the RT-Fall
in Fig. 16a to compare the performance of RT-Fall with that          system performance is not affected much by the opening of
of the baseline method WiFall [29]. As we have already col-          windows/door or the light on/off in the four test environ-
lected training and testing data in Section 6.4 in the office        ments, its performance deteriorates when the big furniture
room, we spent two weeks in an apartment, meeting room               is moved or test is done in a new environment with the old
and the hall again with the three students (a,b,c) in the train-     model built for the old environment. We will detail the
ing data collection phase. In the office room and the meeting        results in the following subsections.
room, as we only need one AP and one WiFi device to cover               Impact of moving the furniture location. We move the sofa to
the whole area, two classification models were built for             different places in the office room to evaluate the impact on
each room, one is based on our approach, the other is based          the fall detection performance. The experiment was done
on WiFall. However, in the apartment and the big hall, we need       under four different conditions: Fall detection is conducted
one AP and two WiFi devices to cover the whole area as shown         while the sofa is put in the original place (baseline), perform
in Fig. 12. Specifically, in the apartment, we train three clas-     the same experiment when the sofa is moved to the door
sification models from the training dataset, each model cor-         side, do the same test after moving the sofa to the LOS path,
responding to one room. To make the three models work                and re-train the model and repeat the test as in last case. We
together, the CSI captured in two WiFi devices were syn-             arrange three students to conduct 20 falls and 40 fall-like
chronized to a central sever. As each room has its own               activities in each of the first three scenarios to evaluate the
model, the system needs to track which room the subject is           impact on the system performance, and each student com-
in to select the proper model to use. Actually it is quite sim-      pletes all the tests in one day. For the last test, we ask each
ple for RT-Fall to detect this. For example, if the subject is in    student to conduct 100 falls and 100 fall-like activities in one
the living room, the CSI phase difference signals in both            week and use the collected training data to rebuild the
WiFi devices are in unstable state. However, if the subject is       model. Then we evaluate the new model in the same way as
in one of the two bedrooms, only the WiFi device closer to           we did in the first three scenarios to get the averaged results
the subject has unstable CSI phase difference signal while           as shown in Fig. 17. When the sofa is moved from the origi-
the other one has stable signal. In the hall, as the area is too     nal place to the door side, the sensitivity drops a little bit
large for only one AP and one WiFi device to cover, we               from 89 to 86 percent and the specificity drops from 92 to
deploy two WiFi receiving devices. Again, two classification         77 percent. However, when the sofa is moved to the room
models were built for two separate areas and the CSI cap-            center which blocks the LOS path, the sensitivity suffers
tured in two WiFi devices were synchronized to make the              from a severe deterioration from 89 to 57 percent and the
final decision. As each area has its own model, the system           specificity drops from 92 to 59 percent. So it seems that the
also needs to track which area the subject is in. RT-Fall lev-       bulky furniture movement has quite a big impact on the fall
erages the fact that when the subject is close to one WiFi           detection results, the reason is probably due to the signifi-
device, the standard deviation of the CSI phase difference           cant CSI change caused by the variations in RF propagation
in this WiFi device will show severer fluctuation than that          multi-paths. When the model was reconstructed using the
524                                                          IEEE TRANSACTIONS ON MOBILE COMPUTING,      VOL. 16,   NO. 2,   FEBRUARY 2017


                                                                     signal path between human body and the transceivers in c,
                                                                     d, e, f, but the direct signal path is blocked for the locations
                                                                     a and b. Hence a promising research direction is to intro-
                                                                     duce context such as location information in the fall detec-
                                                                     tion algorithm to improve the system performance. For
                                                                     instance, we might roughly locate the elder in the room first,
                                                                     and then select a location-based classification model for
                                                                     accurate fall detection.
Fig. 18. Robustness to different rooms.

## 7.2 Extend the Solution to Multi-Room Settings
training data collected in the new setting, the test results         This work focuses mainly on the use case of applying the fall
restore to a comparable level, with 87 percent of sensitivity        detection system in a single room setting. Even though we
and 90 percent of specificity respectively.                          also test the RT-fall in an apartment with three rooms and
   System evaluation in different environments. Finally, we          obtain quite satisfactory results, we find that it’s not trivial to
conduct experiments to test the performance of a model               find the best places to install the WiFi access point and device
built for one environment in other environments. Specifi-            to ensure good RF coverage and consistent detection perfor-
cally, we use the model M1 built for the office room and             mance in a multi-room setting. In fact, it’s rather a big chal-
apply it to the apartment and meeting room settings. We              lenge to find the optimal setting given a certain multi-room
ask three students to conduct 40 falls and 80 fall-like activi-      layout. In the future we plan to investigate the optimal
ties in each place in three days. Then we get the averaged           device placement issue for RF coverage and fall detection.
results of system performance in each environment as
shown in Fig. 18. The sensitivity changes from 89 to 65 per-         7.3 Extend the Solution to Multi-Person Settings
cent, 70 and 90 percent in the apartment, meeting room and           Although RT-fall is designed for a single elder living alone
hall setting, respectively; and the specificity drops from 93        and independently at home, we did perform experiments to
to 70 percent, 72 and 75 percent in the apartment, meeting           see its applicability in multi-person settings. We find that
room and hall setting, respectively. Finally, averaging the          RT-fall can work only when there is only one person moving
results in the apartment, meeting room and hall, the sensi-          while the others are still. Specifically, we find that if two sub-
tivity drops from 89 to 71 percent while the specificity drops       jects are in the room, one is sleeping or sitting on the chair,
from 93 to 72 percent. If we recall the RT-Fall system perfor-       when the other subject falls, RT-fall can still detect it reliably.
mance in each place with the model constructed for that              This corresponds to the situation that when one elder is
environment as shown in Fig. 16b, it is obvious that all the         sleeping during night, the system can still detect the fall
system models are environment dependent and optimal                  when the other elder gets up and falls in the same apartment.
performance can be achieved only by fine-tuning the per-             While both elders are active, one should be able to help when
sonalized model in a specific environment. In summary, the           the partner happens to fall in the same apartment.
system is quite robust to small environment changes. For
the significant environment changes, the system perfor-
mance can be ensured by applying the new model learned               8   CONCLUSION
from the changed settings.                                           In this paper, we design and implement a real-time, contact-
                                                                     less, low-cost yet accurate indoor fall detection system, RT-
                                                                     fall, using one commercial off-the-shelf WiFi router and
7     DISCUSSION                                                     WiFi receiving devices. To the best of our knowledge, this is
## 7.1 Major Reasons Causing Detection Errors                           the first work to identify the CSI phase difference as a better
As the sensitivity and specificity are not 100 percent, we           base signal than amplitude for fall activity segmentation
would like to analyze what causes the classification errors          and detection, it also discovers the sharp power profile
in fall detection. After careful analysis about the classifica-      decline pattern of the fall in the time-frequency domain and
tion algorithms and results, we find two major reasons that          leverages the insight for accurate fall segmentation/detec-
prevent perfect fall detection. The first reason is that the fea-    tion. Experimental results conducted in four indoor envi-
tures extracted for fall-like activities are very close to those     ronments demonstrate that RT-fall has great potential to
of falls under certain context, which lead to wrong classifi-        become a practical and non-intrusive fall detection solution.
cation results in terms of both sensitivity and specificity. For        Fall detection has long been a research challenge in the
example, when the subject quickly sits down onto the chair           public healthcare domain for the elders. Although we
and leans against the back of the chair, it is sometimes clas-       implemented quite an effective fall detector using off-the-
sified as a fall. For this type of mis-classification, we plan to    shelf WiFi devices, there are still many interesting problems
introduce more salient features as the input to help distin-         that deserve further study. For example, can we develop a
guish the fall and fall-like activities. The second reason is        very accurate personalized fall detector for each individual
that the extracted features for fall and fall-like activities are    elder? How can we develop a fall detector which can adapt
context-dependent, the same type of activities may show              and evolve according to the environment change? While in
different features for different places. Taking the office           this work we exploit the power of phase difference for activ-
room (see Fig. 12a) as example, we notice that the locations         ity segmentation and fall detection, we believe that it could
behind the desk (a, b) have lower detection rate than loca-          be an effective enabler for activity recognition in general,
tions in c, d, e, f. One possible reason is that there is a direct   especially for those with tiny body movement. We are
WANG ET AL.: RT-FALL: A REAL-TIME AND CONTACTLESS FALL DETECTION SYSTEM WITH COMMODITY WIFI DEVICES                                                        525


working on these questions and expect to obtain promising                         [21] D. Halperin, W. Hu, A. Sheth, and D. Wetherall, “Tool release:
                                                                                       Gathering 802.11 n traces with channel state information,” ACM
results soon.                                                                          SIGCOMM Comput. Commun. Rev., vol. 41, no. 1, pp. 53–53, 2011.
                                                                                  [22] A. E. Kosba, A. Saeed, and M. Youssef, “Rasid: A robust WLAN
ACKNOWLEDGMENTS                                                                        device-free passive motion detection system,” in Proc. IEEE Int.
                                                                                       Conf. Pervasive Comput. Commun. (PerCom)., 2012, pp. 180–189.
This work is funded by the National 1000-plan Research                            [23] K. Qian, C. Wu, Z. Yang, Y. Liu, and Z. Zhou, “Passive detection
Grant and the NSFC Grant No. 61572048. The authors                                     of moving targets with dynamic speed using PHY layer
                                                                                       information,” in Proc. 20th IEEE Int. Conf. Parallel Distrib. Syst.,
would like to thank Wang Yibo, Li Xiang, and Wu Dan for                                2015, pp. 1–8.
their help with experiments. D. Zhang is the corresponding                        [24] G. Wang, Y. Zou, Z. Zhou, K. Wu, and L. M. Ni, “We can hear you
author.                                                                                with wi-fi!” in Proc. 20th Annu. Int. Conf. Mobile Comput. Netw.,
                                                                                       2014, pp. 593–604.
                                                                                  [25] Q. Pu, S. Gupta, S. Gollakota, and S. Patel, “Whole-home gesture
REFERENCES                                                                             recognition using wireless signals,” in Proc. 19th Annu. Int. Conf.
                                                                                       Mobile Comput. Netw., 2013, pp. 27–38.
[1]    S. R. Lord, C. Sherrington, H. B. Menz, and J. C. Close, Falls Older
                                                                                  [26] P. Melgarejo, X. Zhang, P. Ramanathan, and D. Chu, “Leveraging
       People: Risk Factors Strategies Prevention. Cambridge, U.K.: Cam-
                                                                                       directional antenna capabilities for fine-grained gesture recog-
       bridge Univ. Press, 2007.
                                                                                       nition,” in Proc. ACM Int. Joint Conf. Pervasive Ubiquitous Comput.,
[2]    O. A. FALLS. (2013). Falls among older adults: An overview
                                                                                       2014, pp. 541–551.
       [online]. Available: http://www.cdc.gov/HomeandRecreational-
                                                                                  [27] X. Liu, J. Cao, S. Tang, and J. Wen, “Wi-sleep: Contactless sleep
       Safety/Falls/adultfalls.html/
                                                                                       monitoring via wifi signals,” in Proc. IEEE Real-Time Syst. Symp.,
[3]    P. J. Rajendran, “A smart and passive floor-vibration based fall
                                                                                       2014, pp. 346–355.
       detector,” Ph.D. dissertation, Univ. Virginia, Charlottesville, VA,
                                                                                  [28] J. Liu, Y. Wang, Y. Chen, J. Yang, X. Chen, and J. Cheng, “Tracking
       USA, 2007.
                                                                                       vital signs during sleep leveraging off-the-shelf wifi,” in Proc. 16th
[4]    D. Wild, U. Nayak, and B. Isaacs, “How dangerous are falls in old
                                                                                       ACM Int. Symp. Mobile Ad Hoc Netw. Comput., 2015, pp. 267–276.
       people at home?” B. Med. J., vol. 282, no. 6260, pp. 266–268, 1981.
                                                                                  [29] C. Han, K. Wu, Y. Wang, and L. M. Ni, “Wifall: Device-free fall
[5]    S. M. Friedman, B. Munoz, S. K. West, G. S. Rubin, and L. P. Fried,
                                                                                       detection by wireless networks,” in Proc. IEEE INFOCOM, 2014,
       “Falls and fear of falling: Which comes first? a longitudinal pre-
                                                                                       pp. 271–279.
       diction model suggests strategies for primary and secondary pre-
                                                                                  [30] Y. Wang, J. Liu, Y. Chen, M. Gruteser, J. Yang, and H. Liu,
       vention,” J. Amer. Geriatrics Soc., vol. 50, no. 8, pp. 1329–1335, 2002.
                                                                                       “E-eyes: Device-free location-oriented activity identification using
[6]    H. Rimminen, J. Lindstr€     om, M. Linnavuo, and R. Sepponen,
                                                                                       fine-grained wifi signatures,” in Proc. 20th Annu. Int. Conf. Mobile
       “Detection of falls among the elderly by a floor sensor using the
                                                                                       Comput. Netw., 2014, pp. 617–628.
       electric near field,” IEEE Trans. Inform. Technol. Biomed., vol. 14,
                                                                                  [31] D. Zhang, H. Wang, Y. Wang, and J. Ma, “Anti-fall: A non-intru-
       no. 6, pp. 1475–1476, Nov. 2010.
                                                                                       sive and real-time fall detector leveraging CSI from commodity
[7]    Y. Li, K. Ho, and M. Popescu, “A microphone array system for
                                                                                       WiFi devices,” in Proc. 13th Int. Conf. Inclusive Smart Cities e-Health,
       automatic fall detection,” IEEE Trans. Bio. Eng., vol. 59, no. 5,
                                                                                       2015, pp. 181–193.
       pp. 1291–1301, May 2012.
                                                                                  [32] P. Bahl and V. N. Padmanabhan, “Radar: An in-building RF-based
[8]    H. Foroughi, B. S. Aski, and H. Pourreza, “Intelligent video sur-
                                                                                       user location and tracking system,” in Proc. INFOCOM 19th Annu.
       veillance for monitoring fall detection of elderly in home environ-
                                                                                       Joint Conf. IEEE Comput. Commun. Societies., 2000, pp. 775–784.
       ments,” in Proc. 11th IEEE Int. Conf. Comput. Inform. Technol., 2008,
                                                                                  [33] B. Kellogg, V. Talla, and S. Gollakota, “Bringing gesture recogni-
       pp. 219–224.
                                                                                       tion to all devices,” in Proc. 11th USENIX Conf. Netw. Syst. Des.
[9]    N. Noury, A. Fleury, P. Rumeau, A. Bourke, G. Laighin, V. Rialle,
                                                                                       Implementation, 2014, pp. 303–316.
       and J. Lundy, “Fall detection-principles and methods,” in Proc.
                                                                                  [34] W. Xi, J. Zhao, X.-Y. Li, K. Zhao, S. Tang, X. Liu, and Z. Jiang,
       29th IEEE Annu. Int. Conf. Eng. Med. Biol. Soc., 2007, pp. 1663–1666.
                                                                                       “Electronic frog eye: Counting crowd using WiFi,” in Proc. IEEE
[10]   X. Yu, “Approaches and principles of fall detection for elderly and
                                                                                       INFOCOM, 2014, pp. 361–369.
       patient,” in Proc. 10th Int. Conf. e-health Netw., Appl. Serv., 2008,
                                                                                  [35] W. Liu, X. Gao, L. Wang, and D. Wang, “BFP: Behavior-free pas-
       pp. 42–47.
                                                                                       sive motion detection using PHY information,” Wireless Personal
[11]   V. Spasova and I. Iliev, “A survey on automatic fall detection in
                                                                                       Commun., vol. 83, no. 2, pp. 1–21, 2015.
       the context of ambient assisted living systems,” Int. J. Adv. Com-
                                                                                  [36] C. Wu, Z. Yang, Z. Zhou, X. Liu, Y. Liu, and J. Cao, “Non-invasive
       put. Res., vol. 4, pp. 94–109, 2014.
                                                                                       detection of moving and stationary human with wifi,’ IEEE J.
[12]   C. D. Lord C.J., “Falls in the elderly: Detection and assessment,” in
                                                                                       Selected Areas Commun., vol. 33, no. 11, pp. 2329–2342, 2015.
       Proc. Annu. Int. Conf. IEEE Eng. Med. Biol. Soc., 1991, pp. 1938–1939.
                                                                                  [37] S. Sigg, M. Scholz, S. Shi, Y. Ji, and M. Beigl, “Rf-sensing of activi-
[13]   Q. T. Huynh, U. D. Nguyen, L. B. Irazabal, N. Ghassemian, and
                                                                                       ties from non-cooperative subjects in device-free recognition sys-
       B. Q. Tran, “Optimization of an accelerometer and gyroscope-
                                                                                       tems using ambient and local signals,” IEEE Trans. Mobile
       based fall detection algorithm,” J. Sens., vol. 2015, pp. 1–8, 2015.
                                                                                       Comput., vol. 13, no. 4, pp. 907–920, Apr. 2014.
[14]   F. Bianchi, S. J. Redmond, M. R. Narayanan, S. Cerutti, and
                                                                                  [38] J. Shea. (2005). An investigation of falls in the elderly [Online].
       N. H. Lovell, “Barometric pressure and triaxial accelerometry-
                                                                                       Available: http://www.signalquest.com/master
       based falls event detection,” IEEE Trans. Neural Syst. Rehabil.,
                                                                                  [39] D. Tse and P. Viswanath, Fundamentals of Wireless Communication.
       vol. 18, no. 6, pp. 619–627, Dec. 2010.
                                                                                       Cambridge, U.K.: Cambridge Univ. press, 2005.
[15]   Y.-C. Chen and Y.-W. Lin, “Indoor RFID gait monitoring system
                                                                                  [40] S. Sen, B. Radunovic, R. R. Choudhury, and T. Minka, “You are
       for fall detection,” in Proc. IEEE 2nd Int. Symp. Aware Comput.,
                                                                                       facing the Mona Lisa: Spot localization using PHY layer
       2010, pp. 207–212.
                                                                                       information,” in Proc. 10th Int. Conf. Mobile Systems, Appl., Serv.,
[16]   J. Dai, X. Bai, Z. Yang, Z. Shen, and D. Xuan, “Perfalld: A perva-
                                                                                       2012, pp. 183–196.
       sive fall detection system using mobile phones,” in Proc. 8th IEEE
                                                                                  [41] J. Gjengset, J. Xiong, G. McPhillips, and K. Jamieson, “Phaser:
       Int. Conf. Pervasive Comput. Commun. Workshops, 2010, pp. 292–297.
                                                                                       Enabling phased array signal processing on commodity wifi
[17]   S. Tao, M. Kudo, and H. Nonaka, “Privacy-preserved behavior
                                                                                       access points,” in Proc. 20th Annu. Int. Conf. Mobile Comput. Netw.,
       analysis and fall detection by an infrared ceiling sensor network,”
                                                                                       2014, pp. 153–164.
       Sensors, vol. 12, no. 12, pp. 16920–16936, 2012.
                                                                                  [42] C. Wu, Z. Yang, Z. Zhou, K. Qian, Y. Liu, and M. Liu, “Phaseu:
[18]   Z.-P. Bian, J. Hou, L.-P. Chau, and N. Magnenat-Thalmann, “Fall
                                                                                       Real-time los identification with WiFi,” in Proc. IEEE 33rd Annu.
       detection based on body part tracking using a depth camera,” IEEE
                                                                                       Int. Conf. Comput. Commun., 2015, pp. 2688–2696.
       J. Biomed. Health Informat., vol. 19, no. 2, pp. 430–439, Mar. 2015.
                                                                                  [43] R. Nandakumar, B. Kellogg, and S. Gollakota, “Wi-fi gesture rec-
[19]   E. E. Stone and M. Skubic, “Fall detection in homes of older adults
                                                                                       ognition on existing devices,” arXiv preprint arXiv:1411.5394, 2014.
       using the microsoft kinect,” IEEE J. Biomed. Health Informat.,
                                                                                  [44] C. W. Han, S. J. Kang, and N. S. Kim, “Implementation of HMM-
       vol. 19, no. 1, pp. 290–301, Jan. 2015.
                                                                                       based human activity recognition using single triaxial acceler-
[20]   N. Pannurat, S. Thiemjarus, and E. Nantajeewarawat, “Automatic
                                                                                       ometer,” IEICE Trans. Fundam. Electron., Commun. Comput. Sci.,
       fall monitoring: A review,” Sensors, vol. 14, no. 7, pp. 12900–
                                                                                       vol. 93, no. 7, pp. 1379–1383, Jul. 2010.
       12936, 2014.
526                                                                     IEEE TRANSACTIONS ON MOBILE COMPUTING,         VOL. 16,   NO. 2,   FEBRUARY 2017

[45] H. Kerdegari, K. Samsudin, A. R. Ramli, and S. Mokaram,                                           Junyi Ma received the BE degree in network
     “Evaluation of fall detection classification approaches,” in Proc.                                engineering from the School of Computer Sci-
     4th Int. Conf. Intell. Adv. Syst., 2012, pp. 131–136.                                             ence, Beijing University of Posts and Telecommu-
[46] C. S. Hemalatha and V. Vaidehi, “Frequent bit pattern mining                                      nications, Beijing, China, in 2015. He is currently
     over tri-axial accelerometer data streams for recognizing human                                   working toward the PhD degree in computer sci-
     activities and detecting fall,” Procedia Comput. Sci., vol. 19, pp. 56–                           ence in the School of Electronics Engineering
     63, 2013.                                                                                         and Computer Science, Peking University. His
[47] B. Sch€olkopf, A. J. Smola, R. C. Williamson, and P. L. Bartlett,                                 research interests include ubiquitous computing
     “New support vector algorithms,” Neural Comput., vol. 12, no. 5,                                  and mobile computing.
     pp. 1207–1245, 2000.
[48] C.-C. Chang and C.-J. Lin, “Libsvm: A library for support vector
     machines,” ACM Trans. Intell. Syst. Technol., vol. 2, no. 3, p. 27, 2011.
                                                                                                       Yuxiang Wang is a senior at Peking University,
                        Hao Wang received the MS degree in software                                    studying computer science and technology. He is
                        engineering from the School of Software and                                    going to work toward the master’s degree in the
                        Microelectronics, Peking University, in 2013. He                               School of Electronics Engineering and Computer
                        is currently working toward the PhD degree in                                  Science, Peking University. His main research
                        computer science with the School of Electronics                                interest is ubiquitous computing.
                        Engineering and Computer Science, Peking
                        University. His research interests include mobile
                        crowdsensing and ubiquitous computing. He is a
                        student member of the IEEE.

                                                                                                       Shengjie Li received the BE degree in software
                        Daqing Zhang received the PhD degree from the                                  engineering from Jilin University, Changchun,
                        University of Rome La Sapienza in 1996. He is a                                China, in 2015. She is currently working toward
                        chair professor in the School of EECS, Peking Uni-                             the PhD degree in computer science in the
                        versity, China. He has published more than 200                                 School of Electronics Engineering and Computer
                        technical papers in leading conferences and jour-                              Science, Peking University. Her research inter-
                        nals. He served as the general or program chair                                ests include mobile crowd-sensing and ubiqui-
                        for more than 10 international conferences, giving                             tous computing.
                        keynote talks at more than 16 international confer-
                        ences. He is the associate editor for the ACM
                        Transactions on Intelligent Systems and Technol-
                        ogy, IEEE Transactions on Big Data, etc. He is the
                                                                                 " For more information on this or any other computing topic,
winner of the 10-years CoMoRea Impact Paper Award at the IEEE Per-
Com 2013, the Honorable Mention Award at the ACM UbiComp 2015, the               please visit our Digital Library at www.computer.org/publications/dlib.
Best Paper Award at the IEEE UIC 2015 and 2012, and the Best Paper
Runner Up Award at Mobiquitous 2011. His research interests include
context-aware computing, urban computing, mobile computing, big data
analytics, pervasive elderly care, etc. He is a member of the IEEE.

                       Yasha Wang received the PhD degree in the
                       Northeastern University, Shenyang, China, in
                       2003. He is currently a professor and associate
                       director of the National Research & Engineering
                       Center of Software Engineering, Peking Univer-
                       sity, China. He has published more than 50 papers
                       in prestigious conferences and journals, such as
                       ICWS, UbiComp, ICSP, etc. As a technical leader
                       and manager, he has accomplished several key
                       national projects on software engineering and
                       smart cities. Cooperating with major smart-city
solution providing companies, his research work has been adopted in
more than 20 cities in China. His research interest includes urban data
analytics, ubiquitous computing, software reuse, and online software
development environment. He is a member of the IEEE.

