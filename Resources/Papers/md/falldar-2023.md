6126                                                                                 IEEE TRANSACTIONS ON MOBILE COMPUTING, VOL. 22, NO. 10, OCTOBER 2023




                     Rethinking Fall Detection With Wi-Fi
                                           Zheng Yang , Fellow, IEEE,
                     Yi Zhang , Student Member, IEEE, and Qian Zhang , Student Member, IEEE

       Abstract—The past decades have witnessed a surge in human fall detection with sensors, cameras, and wireless signals.
       Among them, Wi-Fi-based fall detection has been one of the most attractive solutions due to the ubiquitous and pervasive
       deployment of Wi-Fi infrastructures. However, these approaches are still difficult to be put into practical use. To push forward
       Wi-Fi-based fall detection for wide deployment, three major limitations concerning environmental diversity, motion diversity, and
       user diversity are required to be resolved. In this paper, we propose FallDar, a Wi-Fi-based deep learning-assisted fall detection
       system that outperforms state-of-the-art works on the three criteria simultaneously. First, to deal with environmental diversity,
       FallDar characterizes falls with the speed of the body, which is the most relevant and inherent feature of falling activities,
       making the system resilient to environmental changes. Second, to deal with motion diversity, FallDar simulates a large amount
       of fall data of various falling types with a DNN-based generative model. Training with these data, FallDar is endowed the
       capability of detecting more types of falls. Third, to deal with user diversity, FallDar proposes to incorporate the fall detection
       network with a user identification network. The network is designed to extract user-independent features, requiring no fall data
       from new users for system adjustment. We implement FallDar on commercial Wi-Fi devices and conduct experiments in home
       and office environments for six months. The evaluation results show that FallDar achieves a false alarm rate of 5.7% and a
       missed alarm rate of 3.4% across all factors, making a fundamental step towards ubiquitous fall detection with Wi-Fi.

       Index Terms—Fall detection, channel state information (CSI), commodity Wi-Fi

                                                                                       Ç

1      INTRODUCTION                                                                        settings, have three intrinsic limitations that leave them vul-
                                                                                           nerable to practical challenges in deployment scenarios.
       UMAN falls are a major cause of injury and morbidity
H    among senior citizens, which result in more than 2.8
million injuries treated in emergency departments annually,
                                                                                                     Environmental factors are not completely removed from sig-
                                                                                                      nals. The signal features used in existing works are either
including over 800,000 hospitalizations and more than                                                 primitive signal features such as amplitude and phase of
27,000 deaths [1]. To prevent death and injury, extensive                                             CSI [10], [11] or Doppler Frequency Spectrogram
research efforts have been devoted to indoor fall detection.                                          (DFS) [12] converted from CSI. However, due to the
Traditional approaches have exploited the sensing ability of                                          multipath effects of wireless signals, these raw features
cameras [2], [3], [4], wearable sensors [5], [6], [7], or dedi-                                       are prone to environmental changes. The measured CSI
cated radar hardware [8], [9] for fall detection. However,                                            readings portray the combined signal propagation paths
cameras have the risk of privacy leakage, wearable sensors                                            including those from the surrounding environments,
are intrusive to users and radars are expensive for large scale                                       and DFS profiles are highly correlated with the locations
deployment. The demand for a device-free, secure, and ubiq-                                           and orientations of the users. Using these features, a fall
uitous fall detection mechanism has triggered interests in                                            detection system will have low generalizability between
sensing with commodity Wi-Fi.                                                                         environments and should be retrained whenever
   Previous Wi-Fi-based fall detection systems, such as                                               deployment settings change. So, the performance of the
WiFall [10], RTFall [11], FallDeFi [12], and DeFall [13] have                                         existing works suffers from environmental diversity.
demonstrated the feasibility of using Channel State Informa-                                         Human fall movements are not properly modeled. Exist-
tion (CSI) from Wi-Fi devices for fall detection. These sys-                                          ing works typically associate falls with bursts of
tems, although yielding promising performance in specific                                             changes in CSI readings or frequency components of
                                                                                                      DFS. However, the actual falling movements are far
                                                                                                      beyond that perception. Human falls are complex
   The authors are with the School of Software, Tsinghua University, Beijing                         movements that involve the collaborative move-
    100190, China. E-mail: {hmilyyz, zhangyithss}@gmail.com, megan412@126.                            ments of the torso and limbs, each of which has dif-
    com.                                                                                              ferent moving patterns during falling. For example,
Manuscript received 14 April 2021; revised 28 June 2022; accepted 30 June                             some people may hold on to surrounding furniture
2022. Date of publication 6 July 2022; date of current version 31 August 2023.                        or lean against the wall as they fall and some may
This work was supported in part by the National Key Research Plan under Grant
2018AAA0101200 and in part by NSFC under Grant 61832010. The work of
                                                                                                      fall from chairs, all of which induce less significant
Qian Zhang was supported in part by the NSFC under Grant 62002193.                                    signal fluctuations. The diverse falling patterns will
This work involved human subjects or animals in its research. Approval of all                         be misclassified as those normal activities that
ethical and experimental procedures and protocols was granted by Tsinghua                             exhibit fast movements (e.g., running, abrupt sitting-
University.
(Corresponding author: Zheng Yang.)                                                                   down, etc). So, the performance of the existing works
Digital Object Identifier no. 10.1109/TMC.2022.3188779                                                suffers from motion diversity.
                                   1536-1233 © 2022 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission.
                                                 See ht_tps://www.ieee.org/publications/rights/index.html for more information.
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
YANG ET AL.: RETHINKING FALL DETECTION WITH WI-FI                                                                                                         6127


                                                                                 scenarios. To remedy this, we design a statistical approach
                                                                                 for speed estimation under Non-Line-of-Sight (NLOS) and
                                                                                 rich-scattering settings. Specifically, we regard each object in
                                                                                 the indoor environment as a latent scatterer that would dif-
                                                                                 fuse the signal away in all directions. By modeling the signals
                                                                                 emitted by each scatterer as a Gaussian random variable, we
                                                                                 derive the quantitative relationship between the moving
                                                                                 speed of scatterers and the statistical features of the observed
                                                                                 CSI. This method discards the specific signal propagation
                                                                                 path and is resilient to environmental reflections.
                                                                                     The second challenge is to achieve consistent perfor-
                                                                                 mance for different falling motions. The key to solving this
                                                                                 problem is to build a large and representative training data-
Fig. 1. A comparison of the state-of-the-art Wi-Fi-based fall detection          set that encompasses diverse types of fall movements. How-
systems. The three dimensions give a quantitative comparison between
these systems. The Motion Diversity axis reflects the number of fall types       ever, collecting fall data requires tremendous effort and
reported in these systems. The User Diversity axis reflects the number of        even if this dataset is collected, there remain unseen fall
participants reported in these systems. The Environmental Diversity axis         types which the classifier may not be able to generalize to.
reflects the number of rooms evaluated in these systems.
                                                                                 To tackle this problem, we propose to augment the training
                                                                                 dataset by generating synthetic data instances with a gener-
       Human discrepancies are not fully considered. The exist-                 ative model based on Deep Neural Network (DNN). We
        ing works perform fall detection irrespective of                         first analyze the speed transformations of various types of
        human identity. However, as discussed in some                            falls and identify that the diversity of falls comes from the
        works [14], [15] in the biological field, discrepancies                  protective movements of limbs. Thus, we simulate pertur-
        exist in the falling patterns of different people, which                 bations induced by the limbs’ motion with the generative
        are induced by diverse body characters such as                           model and produce other new types of fall instances. With
        weights, heights, and habitual motions. These dis-                       the cooperation of collected and synthetic fall data, FallDar
        crepancies will perturb signals in different manners                     is endowed with the capability of detecting more types of
        and pollute the performance when applying the sys-                       fall activities.
        tems to novel users. So, the performance of the exist-                       The third challenge is to achieve consistent performance
        ing works suffers from user diversity.                                   across different users. Our key insight is to remove user
   As a result, the pursuit of ubiquitous sensing necessitates                   identity from the features used for fall detection. To achieve
an environment-independent, motion-irregular, and user-                          this purpose, FallDar proposes to incorporate a human
irrespective Wi-Fi-based fall detection system.                                  identification task into the fall detection task. Specifically,
   In this paper, we collaborate with a leading smart hard-                      we build a DNN-based network that can output a fall indi-
ware manufacturing company to develop FallDar, an easy-                          cator and human identity simultaneously. Different from
to-deploy Falldetection raDar based on commodity Wi-Fi                           traditional classifiers, we deliberately force the network to
routers. The ultimate goal of FallDar is to provide a low-                       output false human identity, which in turn fraud the latent
cost, sensorless, and contactless fall detection system com-                     features of the network to be user-independent. The classi-
mercially available to the elderly that live on their own.                       fier can be trained with widely available walking data of the
Fig. 1 shows a qualitative comparison between FallDar and                        target people, which imposes a minor burden on model
the state-of-the-art works. FallDar intends to achieve consis-                   adaptation. Therefore, FallDar is immune to user diversity.
tent performance across all three factors simultaneously.                            Putting it all together, FallDar is implemented on several
First, FallDar intends to have prominent generalizability                        commercial Wi-Fi routers and evaluated with a voluntary
between different deployment environments. Second, Fall-                         family across 6 months. The participants consist of two
Dar intends to retain robustness to human motion varia-                          elderly members of the same age of 50 and three young
tions. Third, FallDar intends to be readily scalable between                     members between the ages of 20 and 25. We collect 3,342
users. To support these features, FallDar has to overcome                        data instances after 6 months of continuous monitoring,
three technical challenges.                                                      during which 21 types of normal activities and 24 sub-varia-
   The first challenge is to achieve consistent performance                      tions of fall movements were observed. Evaluation results
across diverse environments. Based on our observations,                          have demonstrated that FallDar can achieve an average
the key to solve this problem is to extract features that are                    false alarm rate of 5.7% and a missed alarm rate of 3.4%
resilient to environmental variations. FallDar proposes to                       across all factors (environments, fall types, and users) in
characterize fall movements with the moving speed of the                         typical home scenarios, outperforming the state-of-the-art
human body, which conveys the most relevant information                          works, making it the most promissing Wi-Fi-based fall
to human activities compared to CSI or DFS. To extract                           detection system for commercial use.
speed from CSI signals, some existing works [16], [17] have                          In a nutshell, we make three main contributions to push
established the quantitative relationship between the speed                      the limit of Wi-Fi-based fall detection:
of moving objects and the DFS profile extracted from CSI.
However, they all assume that the Line-of-Sight (LOS) path                               We resolve the motion diversity and user diversity
between the Wi-Fi devices and the object dominates in the                                 problem in the fall detection system by disentangling
measured signal, which is unrealistic for typical household                               the fall-specific information from the falling speed
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
6128                                                                         IEEE TRANSACTIONS ON MOBILE COMPUTING, VOL. 22, NO. 10, OCTOBER 2023




Fig. 2. Phase difference, DFS, and speed of torso features of falls in different environment settings. (a)(e)(i) Location #1, orientation #1. (b)(f)(j) Loca-
tion #1, orientation #2. (c)(g)(k) Location #2, orientation #1. (d)(h)(l) Transmitter and receiver are placed in different rooms.


       pattern with signal processing and deep learning                              To reveal the correlation between signal features and
       techniques respectively.                                                  environmental factors, we set up four data collection set-
    We build a rigorous fall detection system FallDar on                        tings in a family house. In the first three settings, a pair of
       commodity Wi-Fi devices, which can be easily gener-                       Wi-Fi devices are placed in the sitting room with a dis-
       alized to new users and detect diverse falling pat-                       tance of 3 meters. A user performs fall movements (with
       terns in various environments, making the large                           protective equipment) at different locations and orienta-
       scale deployment of fall detection systems in real                        tions. In the last setting, a pair of devices are put in two
       business scenarios readily available.                                     different rooms with LOS occluded by the wall. After col-
    We conduct extensive experiments in authentic                               lecting CSI measurements, we subtract the CSI phase
       household scenarios, which demonstrate a consistent                       between two adjacent antennas to mitigate the random
       performance of FallDar across diverse factors and                         phase noise [11]. Besides, we perform Short-time Fourier
       confirm its prominent potential for ubiquitous use.                       Transform (STFT) to extract the DFS, which was also used
   The rest of the paper is organized as follows. We intro-                      for fall detection in [12]. We extract human moving speed
duce the observations and motivations of FallDar in Sec-                         with the speed estimation algorithm to be introduced in
tion 2, system overview in Section 3, technical details in                       Section 4.
Sections 4, 5, and 6. We present evaluation in Section 7,                            Figs. 2a, 2b, 2c, 2d, 2e, 2f, 2g, 2h, 2i, 2j, 2k, and 2l demon-
review the literature in Section 8, and conclude this paper in                   strate the phase difference, DFS, and speed during human
Section 10.                                                                      falls. Four observations can be made according to the
                                                                                 results. (1) The CSI phase difference is highly sensitive to
2      OBSERVATIONS AND MOTIVATIONS                                              the environment. For both the dynamic and static period
                                                                                 during falling, the phase difference changes drastically with
To exploit the gap between research and application of Wi-                       no conspicuous pattern, making it an undesirable motion
Fi-based fall detection systems, we conduct extensive field                      indicator for fall detection. (2) When the user falls at the
experiments to study to what extent different factors affect                     same location (location #1) but to different orientations (ori-
fall detection systems. Specifically, we deploy commercial                       entation #1 and #2), the DFS profiles demonstrate different
Wi-Fi routers in a family house to collect CSI measurements.                     frequency shifts (Figs. 2e and 2f even with contrary signs.
Several observations are made based on the results.                              When the user falls to the same orientation (orientation #1)
                                                                                 but at different locations (location #1 and #2), the DFS pro-
## 2.1 Impact of Environmental Diversity                                            files reveal different degrees of frequency shift (Figs. 2e and
In FallDar, environmental diversity includes both the static sur-                2g). (3) When the signal is occluded by walls, frequency
roundings (furniture, walls, ceils, etc) and the relative loca-                  shifts in the DFS profile become weak and faint (Fig. 2h). (4)
tions and orientations of the user to Wi-Fi devices. In                          The speed feature demonstrates a consistent pattern across
practical deployment scenarios, the fall detection system can                    diverse environmental factors.
be deployed in diverse families and houses with different                            From the above observations, we can conclude that tradi-
layouts. More importantly, the moving locations and orienta-                     tional signal features including CSI phase difference and
tions of the users are not fixed, making the robust detection                    DFS are prone to environmental changes, making them sub-
much more challenging. Hence, it is necessary to study the                       optimal for fall motion characterization. To build a fully
impact of environmental diversities on the sensing system.                       environment-independent fall detection system, we try to
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
YANG ET AL.: RETHINKING FALL DETECTION WITH WI-FI                                                                                                         6129




Fig. 3. Speed transformation of different falling types. (a) Trip. (b) Slip. (c)   Fig. 4. Speed transformation of different normal motions. (a) Walk. (b)
Lose Balance. (d) Kneel then fall. (e) Fall from chair. (f) Walk then fall.        Sit. (c) Bend and pick-up. (d) Squat. (e) Dance. (f) Open and close door.

extract human torso speed from raw CSI signals as a motion                         but keep the legs fixed. At last, we ask the volunteer to take
indicator, and Section 4 is designed for this purpose.                             a step forward and move his arms freely when falling. The
                                                                                   falling speeds of the above three patterns are shown in
## 2.2 Impact of Motion Diversity                                                     Fig. 5. Without limbs motion, the falling speed has the larg-
Human falls are complex motions that involve the collabo-                          est peak value and the shortest duration. The acceleration
rative movements of the full body. In practice, the users can                      stage is more steady and smooth than the other patterns.
fall in different manners, making the fall detection task                          When the hands are free during the fall, the volunteer will
much complicated. Existing Wi-Fi-based fall detection sys-                         reach his hands to seek balance, which will cause the falling
tems ([10], [11], [12]) model human falls as sudden torso                          speed to decelerate. The peak value of speed is smaller and
movements that incur bursts of changes in the signal meas-                         the falling duration is longer in this case. When the limbs all
urements. However, in this paper, we ask the following                             move freely, the acceleration becomes more mild, revealing
question: Does the word sudden suffice to portray human                            a smaller peak value and a longer duration. The above eval-
falls?                                                                             uation results reveal that the falling patterns are greatly
   To have a full understanding of human falls, we investi-                        affected by the motion diversity of limbs. In Section 5, we
gate how the torso moves when the human perform differ-                            try to leverage the motion diversity to strengthen the system
ent fall and normal activities. We ask a user to imitate six                       performance.
falling motions including trip, slip, lose balance, kneel then
fall, fall from chair, and walk then fall. During the experi-                      2.3 Impact of User Diversity
ment, we measure CSI with Wi-Fi and extract human mov-                             A commercially valuable fall detection system should
ing speed with the proposed speed estimation algorithm.                            achieve consistent performance for different users. That
As a comparison study, we also ask the user to do some nor-                        makes us think if user diversity is an important factor to
mal activities including walk, sit, bend and pick-up, squat,                       consider when building a fall detection system.
dance, open and close the door.                                                       To validate the impact of user diversity, we compare the
   Figs. 3a, 3b, 3c, 3d, 3e, and 3f demonstrate the speed                          falling patterns of different users. We invite five users to
transformation of the six fall motions, and Figs. 4a, 4b, 4c,                      perform trip falls. Similar to the above experiments, the
4d, 4e, and 4f demonstrate the speed transformation of the                         human moving speed is extracted from the CSI readings
six normal motions. As can be seen, even though fall                               captured by a pair of Wi-Fi devices. Besides, we also use a
motions have larger speeds and accelerations, the discrep-                         dummy to imitate the falling of humans (details can be
ancies between different falling types are non-trivial. This                       found in Section 5.1). We tie a smartphone on the waist of
observation motivates us to believe that by modeling fall                          the dummy to help measure the ground-truth speed.
motion in a fine-grained manner, we can have an in-depth                              Figs. 6a, 6b, 6c, 6d, 6e, and 6f demonstrate the speed
understanding of human motion, which will potentially                              transformation of the dummy and the five users. Several
help us to achieve better performance in fall detection.                           observations can be made. First, compared with the dummy
   To dive deep into the impact of limbs motion, we evalu-                         that has no consciousness, the falling speed of human have
ate the falling speed with regard to different moving pat-                         more fluctuations due to the protective movements during
terns of limbs. We first ask a volunteer to fall from a                            falling. Second, the user with low heights (user #5 and #6)
standing position without moving his legs and arms. Then,                          have smaller peak speeds during falling. Besides, the dura-
we ask the volunteer to move his arms freely when falling                          tion of falls varies between users.
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
6130                                                                         IEEE TRANSACTIONS ON MOBILE COMPUTING, VOL. 22, NO. 10, OCTOBER 2023




Fig. 5. Impact of limbs motion on falling speed.
                                                                                 Fig. 7. Fall detection accuracy across users.

   The above observations reveal that discrepancies exist in
                                                                                 leverages a generative DNN network to synthesize human
the falling pattern of different users. To further evaluate
                                                                                 limbs’ movements, which is aimed to augment fall samples
how would these discrepancies affect fall detection accu-
                                                                                 in training datasets and generates more fall types that are not
racy, we implement a prototype model based on an SVM
                                                                                 included in the collected datasets. With the augmented train-
classifier. The model takes as input the DFS profile of both
                                                                                 ing sets, FallDar is capable of detecting more types of fall
fall and normal instances. We train the model with the data
                                                                                 movements, making it more robust to motion diversity. The
from one user and tested it with the data from one of the
                                                                                 collected fall and normal samples, as well as the synthetic
other four users. The detection accuracy is shown in Fig. 7.
                                                                                 fall samples, are passed to the Fall Detection module. This
As can be seen, without training samples from the testing
                                                                                 module is based on an adversarial DNN network that can
user, the detection accuracy would tumble by a significant
                                                                                 recognize fall movements and users’ identities simulta-
rate. Hence, a fall detection system demands to take the
                                                                                 neously. However, we deliberately encourage the network
diversity of users into account. Section 5 is designed to miti-
                                                                                 to misidentify the users, forcing it to extract user-indepen-
gate the impact of user diversity on the detection system.
                                                                                 dent latent features. By doing so, the fall detection results are
                                                                                 more robust to user diversity.
3      SYSTEM OVERVIEW
FallDar inputs raw CSI streams measured by a pair of Wi-Fi                       4     FALL SPEED ESTIMATION
devices and outputs whether fall movements are detected.                         Existing Wi-Fi based fall detection systems extract features
It is composed of three main modules: Data Collection mod-                       from CSI or DFS as fall representations, which are prone to
ule, Data Generation module, and Fall Detection module.                          environment changes. FallDar proposes to characterize fall
Fig. 8 presents the detailed system workflow.                                    motion with speed of human torso estimated with Channel
    In the Data Collection module, CSI measurements of fall                      State Information (CSI).
and normal movements are processed by a speed estimation                            CSI portrayed by commodity Wi-Fi can be modeled as:
algorithm to extract the actual moving speed of the human
                                                                                                          X
                                                                                                          L                     Rt
body, which is a physically plausible and environmentally                                                                j2p      f ðf;tÞdt
independent motion feature for fall detection, making it                                     Hðf; tÞ ¼          al ðf; tÞe       1 Dl         ;          (1)
                                                                                                          l¼1
more robust to environmental diversity. Upon obtaining the
speed sequence of fall activities, the Data Generation module                    where L is the total number of reflection paths, al is the
                                                                                 amplitude attenuation of path l, fDl is the DFS induced by
                                                                                 object movements on path l.
                                                                                    Some ray-tracing-based works [16], [17] geometrically
                                                                                 trace the signal propagation paths and derive the relation-
                                                                                 ship between DFS and object moving speed. However, they
                                                                                 have limitations in two aspects. First, DFS is correlated with
                                                                                 the relative location and orientation of moving objects




Fig. 6. Speed transformation of falls from the dummy and user #1 to #5.          Fig. 8. Workflow of FallDar.
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
YANG ET AL.: RETHINKING FALL DETECTION WITH WI-FI                                                                                                         6131

                                                                                                Z 2p Z p
                                                                                  Hi ðf; tÞ ¼                hi ða; b; f; tÞexpðjkvi cosðaÞtÞdadb;        (3)
                                                                                                 0       0

                                                                                 where k ¼ 2p= and  is the signal wavelength, vi is the
                                                                                 speed of ith scatterer, a and b are the pitch and yaw angles,
                                                                                 expðjkvi cosðaÞtÞ represents the DFS of the signal on direc-
                                                                                 tion ða; bÞ. hi ða; b; f; tÞ is the portion of observed CSI con-
                                                                                 tributed by ith scatterer on direction ða; bÞ. Inherited from
                                                                                 the physical properties of EM waves [21], hi ða; b; f; tÞ can be
                                                                                 viewed as a circularly-symmetric Gaussian random vari-
                                                                                 able. For 8i; j 2 Vd and ða1 ; b1 Þ 6¼ ða2 ; b2 Þ, hi ða1 ; b1 ; f; tÞ is
                                                                                 independent of hj ða2 ; b2 ; f; tÞ.
Fig. 9. Wi-Fi signals in rich-scattering environment.                               Based on Equations (2) and (3), we are able to derive the
                                                                                 statistical property by analyzing the autocorrelation func-
related to the Wi-Fi link. Specifically, only the radial speed                   tion (ACF) of Hðf; tÞ [21]:
projected on the normal direction of the ellipse with Tx and
Rx as foci could produce DFS. In our previous work                                                     Cov½Hðf; tÞ; Hðf; t þ tÞ
Widar3.0 [18], we have already demonstrated the feasibility                                rH ðf; tÞ ,
                                                                                                        Cov½Hðf; tÞ; Hðf; tÞ
of speed estimation in an environment-independent manner.                                              P        2
                                                                                                         i2Vd s i ðfÞsincðkvi tÞ
However, Widar3.0 is based on the assumption that there is a                                         ¼      P         2
                                                                                                                                  sincðkvtÞ;              (4)
direct path between Wi-Fi devices and the target user, which                                                   i2Vd s i ðfÞ
is reasonable for gesture recognition tasks. The condition can
hardly be met in fall detection tasks because the user can fall                  where Cov½;  is the covariance between two random varia-
at any indoor location. Hence, a novel speed estimation algo-                    bles, s 2i ðfÞ is the variance of hi ða; b; f; tÞ, sincðkvtÞ ¼ sinðkvtÞ
                                                                                                                                                  kvt ,
rithm that can work in NLOS scenarios is necessary. Second,                      and t is the time lag. For human fall activity, we can assume
the signal propagation paths in typical indoor environments                      that the dynamic scaterers are mostly on the torso and have
can hardly be traced due to the complex multipath effect and                     similar speed v. The rationality behind this assumption is
occlusions. As a straightforward example in Fig. 9, a user falls                 that the torso contributes most of the strong scatters, which
behind a wall with no LOS path to the Wi-Fi transceivers. The                    have similar speeds and dominate those from the limbs [20].
received CSI is dominated by the multi-reflection compo-                         Even though we can discard the scatterers on the limbs, the
nents with potentially several times reflections on the sur-                     reciprocal influence on the human torso is non-trivial. In the
rounding objects, which limits the application prospects of                      next section (Section 5), we will discuss how will the protec-
the ray-tracing-based speed estimation methods.                                  tive movements of limbs affect the speed of the torso during
    To enable speed estimation in multipath-rich environ-                        falls. Thus, Equation (4) is approximated with a much sim-
ments, we design a statistical approach inspired by [19],                        pler form: rH ðf; tÞ  sincðkvtÞ. Using this formulation, we
[20]. As is shown in Fig. 9, we treat all the objects in indoor                  have quantitatively established the relationship between the
environments as scatterers that diffuse the signals in all                       speed of human and the ACF of CSI. In practice, the speed v
directions. The CSI observed by the receiver is added up                         is extracted by matching the first peak of the sincðxÞ func-
with the portions contributed by all of the static (like furni-                  tion and the first peak of ACF:
ture, walls, etc) and dynamic (like arms, legs, etc) scatterers.
Intuitively, each scatter is deemed as a ”virtual Tx”. Such                                                       x0    x0 
                                                                                                             v¼       ¼      ;                             (5)
modeling is tenable in typical indoor scenarios, where the                                                        kt 0 2pt0
rooms are crowded with furniture and signals could propa-
gate in all directions. With this model, we dismiss the spe-                     where x0 is the constant value representing the location of
cific signal propagation path and intend to statistically                        the first peak of sincðxÞ function, t 0 is the time lag corre-
investigate the correlation between the observed CSI and                         sponding to the first peak in the ACF.
the moving speed.                                                                   As a straightforward example, we invite a volunteer to
    We decompose the observed CSI into the portions con-                         walk and fall in a heavily furnished room and extract the
tributed by individual scatterers:                                               speed with the CSI collected from a Wi-Fi link located in
                                                                                 another room. As is shown in Fig. 10, even with NLOS
                        X                       X
          Hðf; tÞ ¼              Hi ðf; tÞ þ              Hj ðf; tÞ;      (2)    occlusions and multipath pollution, the walking speed and
                      i2Vs ðtÞ                 j2Vd ðtÞ                          fall speed are estimated consistently, demonstrating its
                                                                                 robustness to environmental diversity.
where Vs ðtÞ and Vd ðtÞ are the sets of static and dynamic                          Comparison Between DFS and Speed. The statistical signal
scatterers, Hi ðf; tÞ is the portion of observed CSI contributed                 model can produce the speed of the target irrespective of its
by ith scatterer. For each scatterer, the diffused components                    moving directions, while the DFS only captures the radial
undergo anonymous propagation processes and eventually                           speed projected on the normal direction of the ellipse with
add up at the receiver. If setting a three-dimensional coordi-                   Tx and Rx as foci. To compare DFS and speed for different
nate with its origin at the ith scatterer and its Z-axis align                   moving directions, we design two experiments. In the first
with the scatterer’s moving direction, the representation of                     experiment, we let a volunteer free fall in the normal and
Hi ðf; tÞ is further decomposed as follows [19]:                                 tangential direction of the Wi-Fi link. The DFS and speed
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
6132                                                                         IEEE TRANSACTIONS ON MOBILE COMPUTING, VOL. 22, NO. 10, OCTOBER 2023




Fig. 10. The estimated speed and the ACF of CSI signals.

extracted from the statistical model are shown in Fig. 11.
Clearly, while falling in the normal direction induces drastic
doppler frequency changes, falling in the tangential direc-
tion only creates minor doppler frequencies, which will be
                                                                                 Fig. 12. Comparison between DFS and speed for walking on a non-linear
mistaken for other activities. On the contrary, the statistical                  track.
model produces consistent speed in both cases. In the sec-
ond experiment, we let a volunteer walk on an L-shaped                           fall from the chair. In such cases, the moving speed of the
track. Specifically, the volunteer first walks in the normal                     torso is not significant, hence diluting the basic foundations
direction and then walks in the tangential direction, and                        of the past works. Worse still, some daily activities such as
returns the same way. The DFS and speed are shown in                             sitting down, run or dance also exhibit fast motion and
Fig. 12. It is observed that when the target moves in the tan-                   would be misclassified as fall.
gential direction, the DFS is less observable than that from                         To deal with the complexity of body motion, FallDar
the normal direction. However, the calculated speed is                           demands a large and representative training dataset with a
more robust to the moving directions. Hence, the fall speed                      variety of fall types. However, the problem of enriching the
estimation algorithm is a better choice to tackle the environ-                   training set is twofold. First, human fall activity is rarely
ment diversity problem.                                                          seen in daily life. Collecting large datasets with an abundant
   In the next sections, we will discuss the methods to detect                   number of falls is time-consuming and labor-intensive. Sec-
fall motion with the estimated speed information.                                ond, there are enormous types of fall motion such as walk-
                                                                                 then-fall, sit-then-fall, trip, slip, etc. Even if we manage to
                                                                                 collect datasets with plentiful fall samples, there would
5      FALL DATA AUGMENTATION                                                    remain unseen fall types to which the classifier may not be
Existing fall detection works are based on the presumption                       able to generalize. The key observation to solve this issue is
that fall motion induces faster torso speed than other daily                     that the falling speed of the torso follows a unique pattern
activities and could be identified by analyzing the abrupt                       with two phases, i.e., acceleration and deceleration, corre-
changes in signals. However, not all falls have to be fast. In                   sponding to the falling and striking period of falls. The
practice, people may hold on to surrounding furniture or                         motion diversity is caused by the random limbs movements
lean against the wall as they fall and some elderly may even                     and their reciprocal influence on the torso. Based on this
                                                                                 observation, it is straightforward to find out this unique pat-
                                                                                 tern and add some perturbations to simulate falls. In this
                                                                                 section, FallDar intends to solve these issues by leveraging a
                                                                                 stochastic generative model based on DNN. This model can
                                                                                 generate a large amount of realistic synthetic data from a
                                                                                 small number of real-world measurements.
                                                                                     Below, we describe how FallDar models human fall
                                                                                 activity and generates diverse fall samples with VAE model.

## 5.1 The Kernel Speed of Fall
                                                                                 Human fall is a complex body motion involving the move-
                                                                                 ments of the torso and limbs. Biomechanics research [14]
                                                                                 reveals that instinctive movements of the limbs exist for pre-
                                                                                 venting injury during a fall. For example, upper extremities
                                                                                 would sway, legs would step towards the falling direction
                                                                                 and even knees would bend to contact the ground to seek
                                                                                 balance when falling. Such protective movements, though
                                                                                 less perceptible, could affect the fall speed and lead to
Fig. 11. Comparison between DFS and speed for different falling                  motion diversity of falls. This is similar to shooting a basket-
directions.                                                                      ball, where a player jumps to throw a ball forwards and his
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
YANG ET AL.: RETHINKING FALL DETECTION WITH WI-FI                                                                                                        6133




Fig. 13. Falling pattern of dummy (Kernel Speed) and human.                     Fig. 14. Kernel speed and residual speed of fall.


torso naturally leans backward. Without the instinctive                         motion during falls and generalize to more complex fall
movements of the limbs, the whole body will be dragged by                       movements.
gravity and fall freely to the ground in an uncontrolled
manner. Without loss of generality, if the initial posture and
## 5.2 The Generative Model
body structure are fixed, we can assume that this uncon-
                                                                                Among various kinds of generative models [22], [23], Fall-
trolled manner of falls has an identical speed pattern. In
                                                                                Dar employs Variational Autoencoder (VAE) [23] because it
another word, the diverse falling patterns are perturbed
                                                                                can generate large amounts of samples from a small input
versions of a fixed pattern. In FallDar, we model human
                                                                                dataset. The core idea underpinning VAE is that the input
falls as two additive components, i.e., the Kernel Pattern and
                                                                                data can be represented with a normal distribution in much
the Residual Pattern. The Kernel Pattern corresponds to the
                                                                                lower-dimensional space. VAE intends to train an Encoder
speed of the human body for uncontrolled falling, and the
                                                                                network that encodes the input data into this latent space
Residual Pattern corresponds to the speed perturbations
                                                                                and reconstruct it from this space with a Decoder network.
induced by limbs. We define the speed of the human body
                                                                                Once trained, VAE can draw random samples from this
as the moving speed of the upper torso. In the following
                                                                                space and generate new data with the Decoder network. In
parts, we discuss the procedures to capture the Kernel Pat-
                                                                                the context of our fall detection task, the fall diversity is
tern and the algorithm to simulate the randomness in the
                                                                                induced by the kinetic movements of limbs, which is charac-
Residual Pattern.
                                                                                terized in the Residual Speed features. VAE takes as input
    Based on the definition of Kernel Pattern, it is a reason-
                                                                                Residual Speed, captures the underlying distribution with
able way to capture this pattern from a dummy that has no
                                                                                network parameters, and generates synthetic data for
active moving capability. The dummy used in FallDar has
                                                                                unseen limbs’ movements. Such movements, when com-
the same height as an ordinary person and is covered with
                                                                                bined with Kernel Speed, would derive novel fall types.
latex rubber, a material that is similar to human skin. Note
                                                                                    The VAE network used in FallDar is illustrated in Fig. 15. It
that the body structure of the dummy has slight differences
                                                                                is composed of two main components: Encoder and Decoder
with humans and we will discuss this phenomenon in Sec-
                                                                                networks. The input x of Encoder is a 1-D vector with a length
tion 6. We let the dummy free fall from standing posture
                                                                                of 1,500, representing 1,500 snapshots of Residual Speed within
and estimate its falling speed with the algorithms in Sec-
                                                                                1.5 seconds. Two Fully-connected (FC) layers activated by
tion 4. Multiple experimental results are averaged to obtain
                                                                                rectified linear unit (ReLU) are cascaded to extract high-level
the Kernel Speed. Fig. 13 demonstrates the Kernel Speed and
                                                                                features from x. Another two FC layers are adopted to extract
fifty samples of human falls. As can be seen, a fall activity is
                                                                                the mean (m) and variance (s) of the latent vector (Z). To
composed of two main stages. The acceleration stage reveals
                                                                                enable backpropagation in the latent space, VAE employs a
an increase of speed from 0 to about 4 m/s, lasting for about
                                                                                trick called reparameterization. Specifically, vectors randomly
1000 milliseconds. The deceleration stage reveals a tumble
of speed towards 0 m/s, lasting for about 300 milliseconds.
The fall patterns from real persons exhibit diversity due to
the protective movements of limbs, but all comply with the
Kernel Speed.
    After representing the core characteristics of fall with Ker-
nel Speed, we intend to simulate the perturbations induced by
the complex motion of the limbs. Specifically, we subtract
the Kernel Speed from the fall speed sampled from real per-
sons and obtain Residual Speed that is independent of the fall
movements. An example of the two speed patterns is shown
in Fig. 14. Residual Speed embodies the relative motion of
limbs to the torso, which contributes to the diversity of vari-
ous fall types With Residual Speed as input, the generative
model is trained to learn the latent representation of limbs’                   Fig. 15. FallDar’s variational autoencoder.
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
6134                                                                         IEEE TRANSACTIONS ON MOBILE COMPUTING, VOL. 22, NO. 10, OCTOBER 2023


sampled from the standard normal distribution are multi-
plied with s and added with m to generate a latent vector Z,
and thus Z is regulated to comply with a normal distribution.
The Decoder network is composed of two FC layers activated
by ReLU and Sigmoid to map Z into synthetic data x^. The
learning objective of VAE is to minimize the reconstruction
loss between x and x^ and regulate Z into a standard normal
distribution (Nð0; 1Þ). Formally, the loss function is defined
as:

         Loss ¼ KL½Nðm; sÞ; Nð0; 1Þ þ Ckx  x^k2 ;                       (6)
                                                                                 Fig. 16. FallDar’s adversarial learning-based fall detection network.

where KLð; Þ is the Kullback-Leibler divergence between                        for fall detection. In FallDar, we leverage the adversarial
two distributions, k  k2 is the euclidean distance between                      learning [26] technique based on DNN to achieve this pur-
two vectors, and C is the constant weight.                                       pose. Fig. 16 provides the DNN architecture. We design a
   After training the VAE with a small dataset of fall sam-                      User Discriminator to recognize the user by whom the activi-
ples collected on-site, FallDar randomly draws samples                           ties are performed. This network and Fall Detector share the
from the standard normal distribution and passes them into                       same input features, which are extracted by a Feature Extrac-
Decoder to generate synthetic data. These data, after incor-
                                                                                 tor network. We confuse the discriminator and force the Fea-
porating with Kernel Speed, can be directly used as the train-
                                                                                 ture Extractor to generate features of activities independent
ing set of the fall detection classifier. Theoretically, we can
                                                                                 of users.
draw an endless number of samples from the model. There-
                                                                                     Let S be the input datasets. During training, each sample
fore, using the augmented datasets in training, FallDar can
                                                                                 s 2 S is a one-dimensional vector with a time length of T .
generalize its classifier to detect unseen fall types and                        The fall samples are generated by the VAE model in Sec-
increase its robustness to motion diversity of humans.                           tion 5.2 and the normal samples are from both the pre-col-
                                                                                 lected dataset and the custom samples of the target users. s
6      FALL DETECTION                                                            is labeled with fall or normal and user identity. During test-
In some of the application scenarios, a practical fall detec-                    ing, FallDar applies sliding windows on the estimated
tion system is supposed to detect fall motion while identify-                    speed stream with a window length of T and a stride length
ing the user’s identity, which can accommodate the post-fall                     of T =2. Each window is evaluated with the detection net-
assistant strategy for individuals. However, based on our                        work. We empirically set T ¼ 1:5 seconds. Feature Extractor
discussions in Section 2, the distributions of fall speed for                    is meant to extract latent features from the input speed
different users have significant discrepancies, which will                       sequences. FallDar employs two FC layers to map the input
potentially create bias in pattern recognition and reduce the                    S into a latent space:
system performance. In FallDar, to maximize the perfor-                                                  F ¼ fðfðS; u1 Þ; u2 Þ;                           (7)
mance, we attempt to mitigate the impact of user diversity
by removing users’ identity information from the wireless                        where u1 ; u2 are the parameters, F is the extracted feature.
signals. Arguably, even though FallDar discards users’                           The FCs are activated by ReLU to introduce non-linearity.
identity, the system will still be valuable in most of the fall                  Dropout mechanism is adopted before each FC to avoid
detection scenarios. This is because FallDar targets the users                   overfitting. By mapping the input into the latent space, we
that live on their own, whose identity is already known                          remove the noise in the speed sequence and capture the
before deployment and there is no need to discriminate                           continuity and the correlation over time. F is further fed
from other users. To enable fully user-independent fall                          into Fall Detector for fall state inference. In the Fall Detector
detection, a challenging yet practical problem should be                         network, two FC layers and a Softmax layer are applied to
resolved: a fall detection pipeline that is trained on a prede-                  obtain the fall indicator:
fined user set can be directly applied to other users without
extra training efforts. This problem is especially challenging                                 Ofall ¼ softmaxðfðfðF; u3 Þ; u4 Þ; u5 Þ;                   (8)
as we need to remove the user identity information from
the signals while preserving the fall features before passing                    where u3 ; u4 ; u5 are the parameters. The Softmax layer has
them into the fall classifier. As far as web know, none of the                   two output units and Ofall is a one-hot encoding vector indi-
existing fall detection works can perform such procedures.                       cating fall or normal. As is discussed earlier, S contains
    To remedy the user identity problem, FallDar intends to                      users’ identity that could deteriorate the detection accuracy,
incorporate a user identification task into the fall detection                   which is also the case for the latent feature F . We pass F
task. Our inspiration is that some state-of-the-art wireless                     into User Discriminator to identify the users’ labels:
sensing works [20], [24], [25] have demonstrated the poten-                                   Ouser ¼ softmaxðfðfðF; u6 Þ; u7 Þ; u8 Þ;                    (9)
tial of human identification based on the gait information
with commodity Wi-Fi devices. In one’s everyday life, his/                       where u6 ; u7 ; u8 are the parameters. For a dataset of N users,
her walking data are widely available, which contains abun-                      the Softmax has N output units, and Ouser is a one-hot
dant identity components. FallDar uses these data to remove                      encoding vector indicating the identities of users. The goal
user-specific features and preserves the sanitized features                      of User Discriminator is to force the latent feature F to be
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
YANG ET AL.: RETHINKING FALL DETECTION WITH WI-FI                                                                                                         6135


independent of the users’ identity to boost the performance
of Fall Detector. Hence we have to maximize the loss in
User Discriminator while minimum the loss in Fall Detector.
The final loss function for the DNN network is:

                      Loss ¼ Lfall  aLuser ;                           (10)

where a is a constant, Lfall is the binary cross-entropy
between Ofall and the label of fall, Luser is the binary cross-
entropy between Ouser and the label of user identity. Note
that the model is trained with the data samples from both
real humans and the VAE model. We annotate the identity
of the samples from the VAE model with a novel label. This                       Fig. 17. Experimental layout in a home.
is because we train the VAE model with mixed fall samples
from multiple users. The identity is already diluted in the
model parameters as well as in the generated samples. As                         home is a typical household environment that is furnished
an intuitive example, if the identity is defined as the height                   with desks, sofa, television, cabinet, etc. Fig. 17 sketches the
of users, the mixed height of two users with heights of 180                      room layout. The size of the monitoring environment is
cm and 170 cm will create a user with a height of 175 cm.                        8:4m  3:6m and two settings of device deployment are
Hence, the generated user can be treated as a novel user. By                     adopted. In setting #2, the LOS path between the transmitter
training the feature extraction, fall detection, and user dis-                   and the receiver is occluded by the door, which is commonly
crimination networks simultaneously, FallDar successfully                        seen in typical home scenarios. The three locations marked
fraud the network to misidentify the users and obtain the                        with A, B, and C are the places where we collect the fall data.
user-independent latent features for robust fall detection in                    We also mark the four falling orientations with numbers 1 to
facing user diversity.                                                           4. If we set up a coordinate system with the Tx as the origin
   In FallDar, the adopted VAE and adversarial learning                          and orientation 1 and 2 as x and y axes, the location of Rx
technique are commonly used in literature. However, the                          and fall are marked in the layout. The Tx is placed at a height
contribution of adapting them in FallDar is non-trivial. For                     of 30 cm, and the Rx in settings #1 and #2 are placed at 2 m
the data augmentation part, we pinpoint the latent structure                     and 1.5 m heights respectively. The transmitter and receiver
(Kernel Speed) that underpin the motion diversity of human                       are both equipped with three omnidirectional antennas. We
falls. Based on this, we exploit the feasibility of capturing                    only use one antenna on the receiver device. The Network
this motion diversity with VAE models and simulate fall                          Interface Cards (NICs) are set to operate on channel 165 with
patterns for system training. Compared with existing fall                        a center frequency of 5.825 GHz and report CSI at a fre-
detection works, we are the first to fully analyze and utilize                   quency of 1,000 Hz. To synchronize between these devices, a
the motion diversity of falls, setting a new stage for human                     router is adopted to connect them with a server to store the
fall detection. For the fall detection part, the key insight is                  captured data. The office room is furnished with a table and
that we can remove human identity from the falling pat-                          several chairs. The room has a size of around 5m  7m.
terns to embrace user diversity. By incorporating a user                         Fig. 18 sketches the office layout. We place the transmitter on
identification network into the fall detection network, we                       the table and the receiver at the 16 different locations marked
can remove user identity from the raw signals and force the                      with green circles in the layout. For each receiver location,
fall detection network to be resilient to user identity. To the                  we let the volunteers fall at the four different locations
best of our knowledge, we are the first to consider and                          marked with blue squares in the layout.
tackle the user diversity problem in fall detection systems.                         Data Collection. For the experiment in the home environ-
                                                                                 ment, the deployed system continuously captures human
                                                                                 activities for six months. Several surveillance cameras are
7    EVALUATION
                                                                                 also deployed to help annotate the data instances. To pre-
## 7.1 Evaluation Setup                                                             serve the privacy of the participants, we only perform
Experimental Settings. We collaborate with a leading smart                       experiments in the living room, dining room, and balcony.
hardware manufacturing company from China to provide                             The voluntary family has five members, including two
fall detection service on their commercial Wi-Fi routers. The                    elderly members (the mother and father) and three young
ultimate goal of FallDar is to provide a low-cost, sensorless,                   members (the son, cousin, and daughter-in-law). Their ages
and contactless fall monitoring system to the elderly that                       range from 20 to 50. Their heights are within 160 cm to 181
live on their own at home. The prototype system is imple-                        cm and weights are within 50 kg to 75 kg. During six
mented by MATLAB and Keras [27] mainly for benchmark                             months of monitoring, we captured massive data instances
analysis1. The experiments are conducted in the home of a                        of various human activities. With careful data sanitization
voluntary family and an office room. For the home environ-                       and annotation, we select data instances corresponding to
ment, we managed to collect a large scale dataset when the                       only a single participants appear in the monitoring area (the
family members stay at home during the COVID-19 pan-                             area with grey color in Fig. 17). However, fall activities are
demic (the members were all in good health condition). The                       rarely seen during data collection. To obtain fall instances,
                                                                                 we require the participants to perform fall motions deliber-
    1. All the code and datasets will be released upon publication.              ately with controlled risk. Specifically, the participants are
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
6136                                                                         IEEE TRANSACTIONS ON MOBILE COMPUTING, VOL. 22, NO. 10, OCTOBER 2023


                                                                                                               TABLE 2
                                                                                                       The Open Dataset From [12]

                                                                                 Room1            A          B         C           D          E           Total2
                                                                                 Fall             70        30         2          30         49           181
                                                                                 Normal           67        87        151         112        34           297
                                                                                 1A: bathroom; B: bedroom; C: corridor; D: kitchen; E: laboratory.
                                                                                 2We only use part of the dataset with clear annotation.

                                                                                 ms to 1,500 ms, in which the falling phase lasts longer than
                                                                                 the striking phase. (2) The peak speed is around 3 m/s to
                                                                                 4.5 m/s for typical fall motions. Therefore, for each fall sam-
                                                                                 ple, we pinpoint the location of the peak speed and adjust
                                                                                 the window to have 1,000 ms on the left and 500 ms on the
                                                                                 right of the peak.
Fig. 18. Experimental layout in an office.                                          Open Dataset. To fully evaluate the system performance
                                                                                 and robustness, we adopt an open dataset released by the
required to wear protective equipment and pretend to fall                        authors of [12]. Due to the lack of descriptions, we only
unconsciously as best as they could. The floor is covered                        adopt the data samples with clear annotations. Table 2
with a sponge to avoid injuries. For the experiment in the                       shows the details of this dataset. A total of 181 fall activities
office environment, we collected both falling and walking                        and 297 normal activities are collected from five rooms
activities from two volunteers. We cover the ground with                         including the bathroom, bedroom, corridor, kitchen, and
several mats and let the volunteers fall forward onto them.                      laboratory.
One volunteer falls at the locations of #1 to #4 and the other                      Metrics. In FallDar, we use two straightforward metrics
one falls at the locations of #1 to #3. We also let one of the                   of fall detection: False Alarm Rate (FAR) and Missed Alarm
volunteers walk freely in the room to collect normal activi-                     Rate (MAR). FAR is the ratio between the number of misi-
ties. After collecting all the normal and fall instances, we                     dentified normal instances and the number of all normal
classify the normal activities into 21 classes and fall activi-                  instances, showing how often the users are bothered when
ties into 6 classes with 24 sub-variations, which are listed in                  no fall event occurs. MAR is the ratio between the number
Table 1. We summarize the overview of our dataset in                             of misidentified fall instances and the number of all fall
Table 3. When collecting normal data, the users are asked to                     instances, showing the sensitivity of FallDar to fall events.
freely perform these movements in the monitoring area. We
have 610 fall instances and 2,000 normal instances collected
## 7.2 Method Comparison
from the home, among which 115 fall instances are from the
participants and the rest are from the dummy. We also have                       In this section, we compare FallDar with the state-of-the-art
228 fall instances and 504 normal instances collected from                       fall detection works based on Wi-Fi signals. We also evalu-
the office room. Besides, we generate 900 instances of syn-                      ate the fall detection capability of FallDar with different
thetic fall instances with our generative model to train the                     input fall features and learning methods.
system. All the experiments are approved by our IRB.                                 Comparison With the State-of-the-Art Works. We compare
   Data Segmentation. To build a real-time fall detection sys-                   FallDar against two state-of-the-art fall detection works,
tem, we design and implement a segmentation algorithm to                         FallDeFi [12] and DeFall [13]. FallDeFi leverages DFS pro-
deal with signal flows. Specifically, we apply a window                          files extracted from CSI streams and select several statistical
with a length of 1,5000 ms on the signal streams and slide                       features of them for detection. Then, it uses an SVM classi-
the window with a step length of 500 ms. In each window,                         fier for binary classification between fall and normal. DeFall
we extract the speed sequence as the input of the detection                      is the first work that proposes to use the speed of body as
network. During system training, we design another seg-                          the features for fall detection. It extracts the speed from the
mentation algorithm to adjust the window position of fall                        raw CSI streams with an algorithm similar to FallDar and
samples. This algorithm is based on two observations we                          constructs a fall template with the speed and acceleration
made in Section 2. (1) The duration of fall is around 1,000                      information. The fall events are identified with a template
                                                                                 matching method. To compare FallDeFi and DeFall with
                                                                                 FallDar, we split the full datasets (containing 610 real fall
                            TABLE 1                                              instances, 900 synthetic fall instances, and 2,000 normal
              The Observed Fall and Normal Activities                            instances) into train and test and extract the corresponding
Movements Types                                Sub-variations                    DFS and speed sequences. We adopt a ten-fold cross-valida-
                                                                                 tion method for evaluation. Fig. 19 shows the results. Intra-
             trip, slip, lose-balance,         forward, backward,
Fall         kneel-then-fall, sit-then-fall,   lateral, on-position
                                                                                 domain represents that the training and testing sets contain
             walk-then-fall                                                      the data samples of the same fall types from the same per-
             walking, jogging, sit-down/stand-up, bend-and-pickup,               son and the same environment. Cross-env, Cross-user, Cross-
             open/close door, open/close fanner, squat, dancing,                 fall represent that the training and testing sets contain the
Normal       eating, reading, watching TV, chatting, answering                   data from different environments, different persons, and
             phone, listening to music, laughing, hanging clothes,               different fall types respectively. For Intra-domain and Cross-
             open/close window
                                                                                 env cases, FallDar and DeFall achieve better performance
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
YANG ET AL.: RETHINKING FALL DETECTION WITH WI-FI                                                                                                        6137


                                                                       TABLE 3
## Dataset Overview

#       Room           Room Size          Duration        People Number                  Samples (fall, normal)                Fall Types     Normal Types
## 1   Living Room       4:2m  3:6m       700 hours                5            1,540 (540, 1000) (495 fall from dummy)            24               21
## 2   Dining Room       2:4m  3:6m       400 hours                5                          870 (70, 800)                        8                10
## 3     Balcony         1:8m  3:6m       200 hours                5                           200 (0, 200)                        0                4
## 4      Office           5m  7m         57 minutes               2                          732 (228, 504)                       1                1



among the three works, which is benefit from the speed fea-                         Comparison of Learning Models. We evaluate the effective-
tures. When testing on different users (Cross-user) and fall                    ness of the proposed DNN-based classifier. With speed
types (Cross-fall), FallDar achieves the best performance,                      sequences as input, we classify fall and normal with Naive
demonstrating its robustness to user diversity and motion                       Bayes, SVM, and the FallDar’s classifier. Both training and
diversity. From the application perspective, we have to                         testing sets contain the instances from all five participants.
admit that even though FallDar achieves better performance                      As is shown in Fig. 21, FallDar’s DNN classifier outperforms
than the existing fall detection systems, the performance is                    the other models with an average decrease of 10.9% and
still to be improved for some application scenarios. We give                    5.9% in terms of FAR+MAR. It is worth noting that even
three suggestions to improve the usability of FallDar. First,                   FAR of the SVM model is lower than FallDar, but its MAR
when FallDar detects fall motions, the system interface can                     is much higher, making it less applicable. The results dem-
seek for user’s confirmation before sounding the alarm for                      onstrate the superiority of the proposed DNN classifier.
the incident. This can ease the false alarm to some extent.                         Performance on Different Datasets. We evaluate the perfor-
Second, deploying more Wi-Fi devices to increase the signal                     mance of FallDar on an external open dataset. We refer to
coverage is another promising method. Last, as we dis-                          our dataset collected in the home environment as #1 and the
cussed in Section 5, human falls are complex motions with                       external dataset as #2. In this experiment, we use four set-
endless types. It will be beneficial to train FallDar with                      tings. In the first setting, we split dataset #1 into train and
more data samples from both the proposed VAE model and                          test with a ratio of 8:2, each of which contains the samples
real-world collection. With the above improvements, we                          from all of the users. In the second setting, we mix datasets
believe FallDar will be taken closer to commercial use.                         #1 and #2 and split them into train and test with the same
    Comparison of Fall Features. We compare three types of                      ratio. In the third setting, we train our system with dataset
different signal features used for fall detection: denoised                     #1 and test it with dataset #2. In the last setting, we only use
CSI phase, DFS profile, and speed sequence. For each type                       dataset #2 for training and testing. Note that users’ identity
of the features, we build a classifier that is similar to the                   is not annotated in dataset #2, and we treat them as from
DNN classifier used in FallDar in Fig. 16. Specifically, we                     the same user in the second and third settings. Ten-fold
adjust the shape of the input layer and keep the other                          cross-validation is used.
layers unmodified. The denoised CSI phase is extracted                              The results can be found in Fig. 22. As is shown, the sys-
from the raw CSI with the denoising algorithms discussed                        tem performance decreases by around 4% for MAR and
in [16], [17] and PCA is applied to refine the 30 subcarriers                   FAR when trained and tested with dataset #2. The system
into one dimension. Each CSI phase instance has a size of                       performance further decrease by around 7% for MAR and
1,500 (samples during 1.5 seconds)1 (one principal com-                        FAR when trained and tested with different datasets. The
ponent). The DFS profile is extracted with the algorithms                       performance decreases are likely caused by the lack of iden-
introduced in [28]. Each DFS instance has a size of 1,500                       tity annotation in dataset #2. Without annotating the users’
(samples during 1.5 seconds)61 (frequency bins). The                           identities, the proposed user discriminator network will not
training and testing sets are both composed of instances                        work, making the system prone to user diversity. This prob-
from the two environment settings. The evaluation results                       lem becomes even worse when the training and testing
are shown in Fig. 20. As can be seen, the speed sequence                        users are different. This reveals that users’ identity is a non-
outperforms both the CSI phase and DFS with an average                          trivial factor for fall detection.
decrease of 35% and 6.6% in terms of FAR+MAR. This                                  Comparison With Outlier Detection Methods. Fall events are
demonstrates that the speed sequence is an ideal feature                        rarely seen during daily lives and fall motions induce stron-
for fall detection.                                                             ger signal fluctuations than normal motions. Given this fact,




Fig. 19. Comparison between state-of-the-art works.                             Fig. 20. Comparison between different fall features.
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
6138                                                                         IEEE TRANSACTIONS ON MOBILE COMPUTING, VOL. 22, NO. 10, OCTOBER 2023




Fig. 21. Comparison between different learning methods.                          Fig. 23. Comparison with outlier detection methods.


                                                                                                                TABLE 4
## Outlier Detection Performance

                                                                                 Methods                    AUROC"             AUPRC"              FPR80#
                                                                                 FallDar                   0.97 (1e-5)        0.94 (1e-4)        0.01 (1e-6)
                                                                                 Softmax                   0.96 (6e-5)        0.93 (4e-4)        0.01 (5e-6)
                                                                                 ODIN                      0.95 (2e-5)        0.93 (3e-4)        0.01 (2e-6)
                                                                                 VAE                       0.78 (9e-5)        0.41 (3e-4)        0.30 (1e-3)
                                                                                 Likelihood-ratio          0.72 (9e-5)        0.30 (5e-4)        0.40 (1e-3)

Fig. 22. Performance on different datasets.
                                                                                 random initialization of network parameters and random
it is straightforward to model fall detection as an outlier                      shuffling of training inputs. As can be seen, the VAE and its
detection problem (while in FallDar we model it as a classifi-                   variant likelihood-ratio method perform worse than the
cation problem). In this experiment, we compare FallDar                          others. This is because the number of NORMAL motions is
with four classical outlier detection methods. Note that Fall-                   tremendous and it is difficult to capture the underlying struc-
Dar is a DNN driven system and we only consider those                            tures with a VAE model. Consequently, the reconstruction
DNN-based outlier detection methods. 1) The Softmax [29]                         loss of the VAE model is large for both the fall and normal
method recognizes the samples that have low prediction con-                      samples. On the contrary, human fall motions have their
fidence on the Softmax layer as outliers. 2) The ODIN [30] is a                  intrinsic structure (i.e., the Kernel Pattern discussed in Sec-
variant of the Softmax method. It uses temperature scaling                       tion 5.1), which makes it possible to model human falls and
and input preprocessing techniques to detect outliers based                      generate synthetic samples with the VAE model. The Softmax
on the prediction confidence of the Softmax layer. 3) The                        and its variant ODIN methods have a decrease in perfor-
VAE method [31] trains a VAE model on resident samples                           mance compared to FallDar. This reveals that it is crucial to
and employs the reconstruction loss during testing as outlier                    encompass the diversity of human motions when building a
indicator. 4) The likelihood-ratio method [32] is a variant of                   fall detection system. Simply treating fall motion as outliers
the VAE method. It contrasts the likelihood of a generative                      without considering their unique patterns will result in sub-
model against a background model and employs the likeli-                         optimal performance. While in FallDar, we dive deeper into
hood ratio between the two models as an outlier indicator.                       the fall patterns by modeling it with the speed transformation
The designed fall detection network in Fig. 16 uses the Soft-                    of the torso. With diverse falling samples as the training data-
max layer to classify fall and normal instances, hence meth-                     set, FallDar demonstrates significantly robustness for practi-
ods 1) and 2) require no modification to the network. We                         cal use.
train the model with normal samples from the users and fall
samples from the dummy. For methods 3) and 4), we build a                        7.3 Robustness Evaluation
VAE model with the same structure as that we use for data                        Performance on the Speed Estimation Algorithm. In FallDar, we
augmentation (Fig. 15). Different from the data augmentation                     characterize human fall motions with the speed of the torso
procedure (Section 5.2) that train the VAE with fall samples,                    to have better modeling of the human motion. One of the
we only use normal samples to train the VAE model in this                        crucial parts of FallDar to achieve this purpose is the speed
experiment and regard the fall samples as outliers. For                          estimation algorithm discussed in Section 4. The accuracy of
method 4), we perturb the training set by flipping the speed                     the speed estimation algorithm is important for the overall
sequence, randomly shifting it along the time axis, and scal-                    performance of FallDar. In this experiment, we evaluate the
ing the value with a random variable within 0 and 1. The per-                    proposed speed estimation algorithm.
turbed dataset is used to train the background model. Three                         We deploy the Wi-Fi transmitter and receiver in both LOS
metrics are used to depict the outlier detection perfor-                         and NLOS settings in the sitting room and the balcony (illus-
mance [32], which are the area under the ROC curve                               trated in Fig. 17). We invite a user to perform some normal
(AUROC), the area under the precision-recall curve                               activities and fall activities in location A in the living room.
(AUPRC), and the false positive rate at 80% true positive rate                   We use a Kinect sensor to capture the motion of the user and
(FPR80). The evaluation results are shown in Fig. 23 and                         log out the speed of the Spine Base joint (defined in Kinect
Table 4. Numbers in front and inside of the brackets are mean                    SDK) as the ground truth. We also extract the speed of the
and variance respectively based on 10 independent runs with                      human torso with the proposed speed estimation algorithm.
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
YANG ET AL.: RETHINKING FALL DETECTION WITH WI-FI                                                                                                        6139




                                                                                Fig. 26. Performance across fall types.
Fig. 24. Performance of the speed estimation algorithm.




                                                                                Fig. 27. Performance across users.
Fig. 25. Performance between different environments.
                                                                                fall types. We consider a total number of 6 fall types and 24
The Wi-Fi devices and the Kinect are synchronized with a                        of its sub-variations in FallDar, including trip, slip, lose-bal-
python script that communicates with socket connection.                         ance, kneel-then-fall, walk-then-fall, and sit-then-fall, which
   Fig. 24 plots the Cumulative Distribution Function (CDF)                     are labeled from #1 to #6. These fall data are from the
of the speed estimation errors. A median error of 0.12 m/s                      dummy and the five participants and the normal data are
and a 90%-tile error of 0.35 m/s in the NLOS case can be                        collected from the five participants. We train the model
observed. The performance decreases slightly for the LOS                        with the data from five out of the six fall types and part of
case, which is because the multipath condition is less obvi-                    the normal types. We compare the performance when the
ous in such a case, and the speed estimation model should                       900 instances of synthetic fall data are used or not used for
be based on a rich-scattering environment.                                      training. The data of the last fall type and the remaining nor-
   Performance Between Environments. In this experiment, we                     mal data are used for testing. The results are shown in
evaluate the performance of FallDar when it is trained and                      Fig. 26. As can be seen, with the synthetic fall data used for
tested with data from different environments. As is illustrated                 training, FallDar can decrease its fall detection accuracy by
in Fig. 17, the Wi-Fi devices are placed in two different set-                  0.78% for FAR and 3.4% for MAR when novel fall types
tings. In Setting #1, both transmitter and receiver are placed in               occur. This result demonstrates that augmenting the train-
the living room and have LOS between them. In Setting #2,                       ing datasets with the generated fall data can enhance the
the transmitter is placed in the living room and the receiver is                system’s robustness to motion diversity.
placed in the balcony and they are occluded by the door. In                         Performance Between Users. Existing fall detection works
this experiment, both the training dataset and the test dataset                 are trained and tested on the same users, while FallDar pro-
are composed of the fall data from the dummy and the normal                     poses a novel classifier based on adversarial learning to
data from the five participants. The training datasets are col-                 enhance the system’s robustness to user diversity. In this
lected in the Dining Room for the LOS setting. The 900 instan-                  experiment, we evaluate the performance when the system
ces of synthetic fall data are also used for training. This                     is tested on new users with no fall data collected from them
experiment contains four settings. In the first setting, we eval-               for training. The training set is composed of the fall data
uate the performance when test data are collected in the same                   from the dummy and the normal data from all the partici-
location and setting as that in the training set. In the second                 pants (including the new users). The 900 instances of syn-
setting, we evaluate the performance when test data are col-                    thetic fall data are also used for training. For testing
lected in the Dining Room in the NLOS setting. In the third                     datasets, we collect 20 fall instances and 100 normal instan-
setting, we evaluate the performance when test data are col-                    ces from each of the five participants. We evaluate the per-
lected in the living room in the LOS setting. In the fourth set-                formance with and without the adversarial part of the
ting, we evaluate the performance with the data collected                       classifier. We also evaluate the performance when removing
from the office environment. The results are shown in Fig. 25.                  the normal data of the test user from the training set. The
As can be seen, FAR and MAR are both consistent when the                        results are shown in Fig. 27. As can be seen, FAR and MAR
location and LOS condition changes. The performance also                        decrease by about 4.5% and 0.8% respectively when the
stays consistent across different rooms. Benefiting from the                    adversarial learning method is adopted. This demonstrates
environment-independent attribute of the extracted speed                        the effectiveness of the adversarial method to deal with user
sequence, FallDar is robust to environmental diversity.                         diversity. Besides, the FAR and MAR decrease by about
   Performance Between Fall Types. In this experiment, we                       6.1% and 3.2% when removing the normal data of the test
evaluate the capability of FallDar when dealing with diverse                    user from the training set. This confirms that by using the
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
6140                                                                         IEEE TRANSACTIONS ON MOBILE COMPUTING, VOL. 22, NO. 10, OCTOBER 2023




Fig. 28. Impact of CSI sampling rate.                                            Fig. 30. Impact of window size.




Fig. 29. Impact of training samples.
                                                                                 Fig. 31. Impact of falling orientations.


normal data samples for adversarial training, system perfor-                     The total datasets are composed of the 610 real fall instan-
mance can be more robust to the user diversity problem.                          ces, the 900 synthetic fall instances, and the 2,000 normal
   Performance Between Fall Orientations. The proposed speed                     samples. In the first case, we gradually decrease the number
feature is theoretically robust to moving orientations. In this                  of synthetic fall samples from the datasets and perform ten-
experiment, we evaluate the performance when the users fall                      fold cross-validation. In the second case, we gradually
at different orientations. The training data are collected from                  decrease the number of real fall samples from the datasets
five participants and the dummy in the home environment.                         and perform ten-fold cross-validation. The results are
The synthetic fall samples are also used for training. We use                    shown in Fig. 29. As can be seen, when decreasing the num-
the data from one of the falling orientations for testing and the                ber of synthetic fall samples from 900 to 10, FAR and MAR
others for training. The performance of DFS and speed fea-                       drop by 1.7% and 1.9%. When decreasing the number of
tures are compared. Fig. 31 shows the evaluation results. As                     real fall samples from 610 to 5, FAR and MAR drop by 7.2%
can be seen, the performances of the speed feature for different                 and 6%. This demonstrates that through the collaborative
orientations are consistent. On the contrary, the performance                    use of real fall data and the synthetic fall data, FallDar can
of DFS is susceptible to orientation changes. This is because                    boost its performance to a significant extent.
DFS only captures the radial velocity, and falling in the tan-                      Impact of Window Size. In the above experiments, each
gential direction will induce minor doppler frequency compo-                     instance in the datasets corresponds to a time window of 1.5
nents. This confirms our observations in Figs. 11 and 12.                        seconds. This is based on our empirical observation that all
                                                                                 fall movements occur within 1.5 seconds. In this experi-
## 7.4 Parameter Study                                                              ment, we evaluate the impact of the window size on the
Impact of CSI Sampling Rate. In the above experiments, we                        detection accuracy. We randomly crop the data into a time
evaluate FallDar with a CSI sampling rate of 1000 Hz. How-                       window of 1; 250ms, 1; 000ms, 750ms, and 500ms. The
ever, this rate is not guaranteed as the Wi-Fi packet trans-                     results are shown in Fig. 30. As can be seen, FAR and MAR
mission might be interfered. In this experiment, we                              slightly drops by 3.2% and 1.7% when the window size
evaluate the impact of CSI sampling rate on system perfor-                       decreases from 1; 500ms to 1; 000ms. But when window size
mance. We collect CSI at a rate of 1000 Hz and downsample                        further decreases from 1; 000ms to 500ms, FAR and MAR
the CSI series to 750 Hz, 500 Hz, 250 Hz, and 200 Hz for fall                    tumble by 30% and 17%. This demonstrates that a time win-
detection. The input shape of the DNN models is adjusted                         dow of 1; 000ms suffices for fall detection. In practice, we
accordingly. The results are shown in Fig. 28. As can be                         employ 1; 500ms for better performance.
seen, FAR and MAR drop by 3.6% and 4.1% respectively
when the sampling rate decreases from 1000 Hz to 200 Hz.
This is because fall movements are featured by the prolifera-                    8     RELATED WORK
tion of speed with a maximum of about 4-5 meters/second,                         RSSI-Based Activity and Fall Recognition. RSSI measurements
which could hardly be captured by a low sampling rate. In                        from commodity Wi-Fi devices have been leveraged to rec-
practice, FallDar employs shorter Wi-Fi packets to mitigate                      ognize gestures [33] and many kinds of human activities
the impact on communication.                                                     (including falls events) [34], [35]. WiGest [33] leverages the
   Impact of Training Samples. In this experiment, we evalu-                     effect of in-air hand motion on RSSI to recognize gestures. It
ate the impact of the training samples on detection accuracy.                    divide the impact signals into three states and uses the
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
YANG ET AL.: RETHINKING FALL DETECTION WITH WI-FI                                                                                                        6141


combinations of the states to perform gesture recognition.                      inclinometers to recognize falls events from signal changes
Harmony [34] transforms RSSI into frequency component                           [5], [6], [7], [50]. Among the IMU-based fall detection works,
vectors and uses machine learning technique to classify                         [51], [52] present some deep learning-based methods to aug-
nine kinds of human activities. [35] uses software radio to                     ment the fall dataset, which could be valuable for Wi-Fi-
improve the granularity of RSSI values and consequently                         based fall data augmentation. In terms of ambient device-
improve the accuracy of activity recognition. However, the                      based methods, G-Fall [53] uses geophones to decompose
above RSSI-based methods have low resolution and have                           falling modes and acoustic-FADE [54] uses a microphone
intrinsic limitations on the improvement of recognition                         array to identify if falls events happen. Different from these
accuracy [36], [37].                                                            works, FallDar enables a secure, device-free, and ubiquitous
   CSI-Based Activity Recognition. CSI is commonly used to                      fall detection system.
recognize activities. E-eyes [38] collects location-oriented
time-domain channel features to distinguish in-place activi-
ties. CARM [28] employs a CSI-speed model to build correla-                     9     LIMITATIONS AND DISCUSSIONS
tions between time-frequency features and specific activities.                  FallDar pushes forward Wi-Fi-based fall detection in three
On the basis of CARM, WiFiU [24] generates limb and torso                       aspects including user diversity, motion diversity, and envi-
velocities in CSI for gait recognition. WiDance [16] extracts                   ronment diversity. Even though FallDar achieves better per-
motion-induced DFS to recognize human motions. In addi-                         formance in the above three aspects, there are still some
tion, DeMan [39] uses amplitude and phase information of                        limitations that demand to be resolved.
CSI to detect the moving and stationary users and WiDir [40]                       The Impact of Body Shapes on Residual Speed. The protective
uses phase change of CSI to estimate user’s walking direc-                      movements of human limbs can perturb the falling pattern,
tion. WiTrack2.0 [41] and Widar2.0 [42] enable human locali-                    which will deteriorate the recognition performance. To alle-
zation with wireless signals. [43], [44], [45] extract Doppler                  viate this effect, FallDar proposes to disentangle the residual
shifts or higher level features from wireless signals to per-                   speed from the falling speed pattern to characterize the
form human gesture recognition. [20], [46] enables human                        motion diversity and use it for motion simulation. The
identification with Wi-Fi signals based on gait patterns.                       residual speed is obtained by subtracting the speed pattern
These systems are pioneers of exploration in CSI analysis                       of a dummy from that of the real users. However, using the
and inspire the idea of Wi-Fi-based fall detection.                             dummy is not the optimal way because the dummy has dif-
   CSI-Based Fall Detection. Among the CSI-based fall detec-                    ferent body shapes from that of the real users. The residual
tion systems, WiFall [10] uses fine-grained CSI and a one-                      speeds contain undesired information corresponding to the
class Support Vector Machine classifier and Random Forest                       body shape discrepancies between the dummy and the real
algorithm to classify different human activities and then                       users. To tackle this problem, one potential solution is to
identify falls events. RT-Fall [11] exploits time-frequency                     build custom dummies that have similar body shapes to
domain patterns of CSI to automatically detect falls events in                  that of the real users. This seems cumbersome but could be
real-time. FallDeFi [12] also applies the time-frequency                        effective. Other solutions are expected in future works.
domain features and design a sequential forward selection                          The Impact of Data Imbalance on User Identification. The dis-
algorithm to selects specific features that are resilient to envi-              crepancies between different users can have an impact on
ronmental changes. TL-Fall [47] further solves the issue that                   fall detection performance. To resolve this problem, FallDar
a fall detection model trained in one specific environment                      incorporates a user identification module into the fall detec-
does not work well in the other. It leverages transfer learning                 tion network. By deliberately forcing the network to mis-
theory to further reduce the environmental impact on fall                       identify users, we train the network to discard the user
detection. FallViewer [48] proposes a series of calibration                     identities. However, the training datasets are imbalanced.
algorithms to calibrate the raw Wi-Fi signals that are influ-                   The datasets collected from the dummy and generated by
enced by the multipath effects and mitigate the influence on                    the simulation module only contain falling samples, and
the environment. Comparing to these works, FallDar aims to                      most of the real users only have normal data samples. The
be resistant to environmental diversity, motion diversity,                      different number of falling and normal data samples from
and user diversity simultaneously, which has prominent                          different sources could be harmful to the user identification
advantages among the state-of-art works and promotes the                        algorithm. To remedy this problem, some potential solu-
commercialization and productization of fall detection in                       tions include collecting the falling samples from all the real
smart Wi-Fi devices. DeFall [13] is a pioneering work to                        users and simulating some normal data samples.
extract environment-independent speed features for fall                            Limitations in Dataset Scale. In the experiments, we collect
detection. Our speed estimation is similar to that in DeFall.                   data from three indoor environments and five volunteers.
However, the recognition algorithm in that paper is based on                    The scale of the dataset is sufficient for benchmark analysis
template matching and is constrained to simple fall motions,                    but still not enough for deployment. In real-world applica-
which necessitates the design of data augmentation and user                     tions, the number of environments and users could be enor-
discrimination algorithms in FallDar.                                           mous. To improve the application prospects, other data
   Other Methods of Fall Detection. There exists other means                    augmentation solutions could be valuable besides the
focusing on fall detection including vision-based, IMUs-                        designed VAE-based method. For example, some works [55],
based, and ambient device-based methods. Vision-based                           [56] have demonstrated the feasibility of simulating RF sig-
methods analyze images recorded by depth cameras, such as                       nal measurements from three-dimensional models. There-
Kinect, to monitor falls events [2], [3], [4], [49]. IMUs-based                 fore, we can build models of more kinds of indoor
methods usually leverage accelerometers, gyroscopes, and                        environments and users, and use them to simulate more
      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
6142                                                                         IEEE TRANSACTIONS ON MOBILE COMPUTING, VOL. 22, NO. 10, OCTOBER 2023


data samples. This simulation process does not require the                       [11] H. Wang, D. Zhang, Y. Wang, J. Ma, Y. Wang, and S. Li, “RT-fall:
                                                                                      A real-time and contactless fall detection system with commodity
users to perform falling movements and can be easily                                  WiFi devices,” IEEE Trans. Mobile Comput., vol. 16, no. 2, pp. 511–526,
adapted to more environments and users.                                               Feb. 2017.
    High False Alarm Rate. FallDar has an overall false alarm                    [12] S. Palipana, D. Rojas, P. Agrawal, and D. Pesch, “FallDeFi: Ubiqui-
rate of 5.7% and a missed alarm rate of 3.4%. The performance                         tous fall detection using commodity Wi-Fi devices,” Proc. ACM
                                                                                      InterAct. Mobile Wearable Ubiquitous Technol., vol. 1, 2019, pp. 1–25.
is better than the state-of-the-art works but still has a gap from               [13] Y. Hu, F. Zhang, C. Wu, B. Wang, and K. J. R. Liu, “A WiFi-based
the real-world applications. To further reduce the false alarm                        passive fall detection system,” in Proc. IEEE Int. Conf. Acoust.
rate, one promising solution is to consider body height. After                        Speech Signal Process., 2020, pp. 1723–1727.
                                                                                 [14] E. T. Hsiao and S. N. Robinovitch, “Common protective move-
falling, the human body will be close to the ground, having a                         ments govern unexpected falls from standing height,” J. Biomech.,
lower height than the other normal activities, which may also                         vol. 31, pp. 1–9, 1998.
induce high speed. By considering the body height, some nor-                     [15] S. N. Robinovitch, L. Inkster, J. Maurer, and B. Warnick,
mal but abrupt motions will be filtered. Another potential                            “Strategies for avoiding hip impact during sideways falls,” J. Bone
                                                                                      Mineral Res., vol. 18, pp. 1267–73, 2003.
solution is to use the body skeletons as features rather than                    [16] K. Qian, C. Wu, Z. Zhou, Y. Zheng, Z. Yang, and Y. Liu, “Inferring
the speed. Some works [57], [58] have demonstrated the feasi-                         motion direction using commodity Wi-Fi for interactive exergames,” in
bility of reconstructing the human skeleton from RF signals.                          Proc. ACM CHI Conf. Hum. Factors Comput. Syst., 2017, pp. 1961–1972.
The human skeleton contains richer information regarding                         [17] X. Li et al., “Indotrack: Device-free indoor human tracking with
                                                                                      commodity Wi-Fi,” Proc. ACM InterAct. Mobile Wearable Ubiquitous
human falling status compared to speed. By exploiting skele-                          Technol., vol. 1, pp. 1–22, 2017.
ton for fall detection, some fall-like movements will be filtered                [18] Y. Zheng et al., “Zero-effort cross-domain gesture recognition with
out, reducing the false alarm rate to some extent.                                    Wi-Fi,” in Proc. ACM 17th Annu. Int. Conf. Mobile Syst. Appl. Serv.,
                                                                                      2019, pp. 313–325.
                                                                                 [19] F. Zhang, C. Chen, B. Wang, and K. J. R. Liu, “WiSpeed: A statistical
10     CONCLUSION                                                                     electromagnetic approach for device-free indoor speed estimation,”
                                                                                      IEEE Internet Things J., vol. 5, no. 3, pp. 2163–2177, Jun. 2018.
In this paper, we propose a Wi-Fi-based passive fall detection                   [20] C. Wu, F. Zhang, Y. Hu, and K. J. R. Liu, “GaitWay: Monitoring
system. To enhance the system’s robustness to environmental                           and recognizing gait speed through the walls,” IEEE Trans. Mobile
diversity, we design a novel speed extraction algorithm to                            Comput., vol. 20, no. 6, pp. 2186–2199, Jun. 2020.
                                                                                 [21] D. A. Hill, Electromagnetic Fields in Cavities: Deterministic and Statis-
extract the body speed as a fall feature. To enable FallDar to                        tical Theories, Hoboken, NJ, USA: Wiley, 2009.
detect more types of fall, we design a novel generative DNN                      [22] D. Kingma and M. Welling, “Auto-encoding variational bayes,”
model, which leverages a small dataset of real data and can                           2013, arXiv:1312.6114.
                                                                                 [23] Y. Pu et al., “Variational autoencoder for deep learning of images,
generate enormous synthetic datasets for training. To enhance                         labels and captions,” in Proc. 30th Int. Conf. Neural Informat. Pro-
the system’s robustness to user diversity, we design a novel                          cess. Syst., 2016, pp. 2360–2368.
adversarial learning-based DNN classifier that can extract                       [24] W. Wang, A. X. Liu, and M. Shahzad, “Gait recognition using
user-independent fall features. Through the collaborative                             WiFi signals,” in Proc. ACM Int. Joint Conf. Pervasive Ubiquitous
                                                                                      Comput., 2016, pp. 363–373.
working of the above methods, FallDar outperforms the state-                     [25] Y. Zeng, P. H. Pathak, and P. Mohapatra, “WiWho: WiFi-based
of-the-art fall detection works.                                                      person identification in smart spaces,” in Proc. 15th ACM/IEEE Int.
                                                                                      Conf. Informat. Process. Sensor Netw., 2016, pp. 1–12.
                                                                                 [26] Y. Ganin and V. Lempitsky, “Unsupervised domain adaptation by
REFERENCES                                                                            backpropagation,” in Proc. ACM Int. Conf. Int. Conf. Mach. Learn.,
[1]  NCOA, “Falls prevention facts,” 2015. [Online]. Available: https://              2015, pp. 1180–1189.
     www.ncoa.org/news/resources-for-reporters/get-the-facts/falls-              [27] F. Chollet et al., “Keras,” 2015. [Online]. Available: https://github.
     prevention-facts/                                                                com/fchollet/keras
[2] Z.-P. Bian, J. Hou, L.-P. Chau, and N. Magnenat-Thalmann, “Fall              [28] W. Wang, A. X. Liu, M. Shahzad, K. Ling, and S. Lu, “Understanding
     detection based on body part tracking using a depth camera,” IEEE                and modeling of WiFi signal based human activity recognition,” in
     J. Biomed. Health Inform., vol. 19, no. 2, pp. 430–439, Mar. 2015.               Proc. Annu. Int. Conf. Mobile Comput. Netw., 2015, pp. 65–76.
[3] E. E. Stone and M. Skubic, “Fall detection in homes of older adults          [29] D. Hendrycks and K. Gimpel, “A baseline for detecting misclassi-
     using the microsoft kinect,” IEEE J. Biomed. Health Inform., vol. 19,            fied and out-of-distribution examples in neural networks,” 2013,
     no. 1, pp. 290–301, Jan. 2015.                                                   arXiv:1312.6114.
[4] G. Mastorakis and D. Makris, “Fall detection system using kinect’s           [30] S. Liang, Y. Li, and R. Srikant, “Enhancing the reliability of out-of-dis-
     infrared sensor,” J. Real-Time Image Process, vol. 9, pp. 635–646,               tribution image detection in neural networks,” 2017, arXiv:1706.02690.
     2014.                                                                       [31] J. An and S. Cho, “Variational autoencoder based anomaly detection
[5] L.-J. Kau and C.-S. Chen, “A smart phone-based pocket fall acci-                  using reconstruction probability,” Special Lecture IE 2.1, pp. 1–18,
     dent detection, positioning, and rescue system,” IEEE J. Biomed.                 2015.
     Health Inform., vol. 19, no. 1, pp. 44–56, Jan. 2015.                       [32] J. Ren et al., “Likelihood ratios for out-of-distribution detection,”
[6] J. Wang, Z. Zhang, B. Li, S. Lee, and R. S. Sherratt, “An enhanced                in Proc. 33rd Int. Conf. Neural Informat. Process. Syst., 2019,
     fall detection system for elderly person monitoring using con-                   pp. 14707–14718.
     sumer home networks,” IEEE Trans. Consum. Electron., vol. 60,               [33] H. Abdelnasser, M. Youssef, and K. A. Harras, “WiGest: A ubiqui-
     no. 1, pp. 23–29, Feb. 2014.                                                     tous WiFi-based gesture recognition system,” in Proc. IEEE Conf.
[7] P. Pierleoni, A. Belli, L. Palma, M. Pellegrini, L. Pernini, and S.               on Comput. Commun., 2015, pp. 1472–1480.
     Valenti, “A high reliability wearable device for elderly fall               [34] Z. Chi, Y. Yao, T. Xie, Z. Huang, M. Hammond, and T. Zhu,
     detection,” IEEE Sensors J., vol. 15, no. 8, pp. 4544–4553, Aug. 2015.           “Harmony: Exploiting coarse-grained received signal strength
[8] Y. Tian, G.-H. Lee, H. He, C.-Y. Hsu, and D. Katabi, “RF-based fall               from IoT devices for human activity recognition,” in Proc. IEEE
     monitoring using convolutional neural networks,” Proc. ACM Inter-                Int. Conf. Netw. Protoc., 2016, pp. 1–10.
     Act. Mobile Wearable Ubiquitous Technol., vol. 2, 2018, Art. no. 137.       [35] S. Sigg, M. Scholz, S. Shi, Y. Ji, and M. Beigl, “RF-sensing of activities
[9] J. Hong, S. Tomii, and T. Ohtsuki, “Cooperative fall detection                    from non-cooperative subjects in device-free recognition systems
     using doppler radar and array sensor,” in Proc. IEEE 24th Annu.                  using ambient and local signals,” IEEE Trans. Mobile Comput.,
     Int. Symp. Pers. Indoor Mobile Radio Commun., 2013, pp. 3492–3496.               vol. 13, no. 4, pp. 907–920, Apr. 2014.
[10] Y. Wang, K. Wu, and L. M. Ni, “WiFall: Device-free fall detection           [36] X. Liu, J. Cao, S. Tang, J. Wen, and P. Guo, “Contactless respira-
     by wireless networks,” IEEE Trans. Mobile Comput., vol. 16, no. 2,               tion monitoring via off-the-shelf WiFi devices,” IEEE Trans. Mobile
     pp. 581–594, Feb. 2017.                                                          Comput., vol. 15, no. 10, pp. 2466–2479, Oct. 2016.

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.
YANG ET AL.: RETHINKING FALL DETECTION WITH WI-FI                                                                                                         6143

[37] A. Luong, A. S. Abrar, T. Schmid, and N. Patwari, “RSS step size:           [54] Y. Li, K. C. Ho, and M. Popescu, “A microphone array system for
     1 dB is not enough!,” in Proc. ACM 3rd Workshop Hot Top. Wirel.,                 automatic fall detection,” IEEE Trans. Biomed. Eng., vol. 59, no. 5,
     2016, pp. 17–21.                                                                 pp. 1291–1301, May 2012.
[38] Y. Wang, J. Liu, Y. Chen, M. Gruteser, J. Yang, and H. Liu, “E-             [55] B. Korany, C. R. Karanam, H. Cai, and Y. Mostofi, “Xmodal-ID:
     eyes: Device-free location-oriented activity identification using                Using WiFi for through-wall person identification from candidate
     fine-grained WiFi signatures,” in Proc. Annu. Int. Conf. Mobile                  video footage,” in Proc. 25th Annu. Int. Conf. Mobile Comput. Netw.,
     Comput. Netw., 2014, pp. 617–628.                                                2019, pp. 1–15.
[39] C. Wu, Z. Yang, Z. Zhou, X. Liu, Y. Liu, and J. Cao, “Non-invasive          [56] H. Cai, B. Korany, C. R. Karanam, and Y. Mostofi, “Teaching RF to
     detection of moving and stationary human with WiFi,” IEEE J.                     sense without RF training measurements,” Proc. ACM Interact. Mobile
     Sel. Areas Commun., vol. 33, no. 11, pp. 2329–2342, Nov. 2015.                   Wearable Ubiquitous Technol., vol. 4, no. 4, Dec. 2020, Art. no. 120.
[40] D. Wu, D. Zhang, C. Xu, Y. Wang, and H. Wang, “WiDir: Walking               [57] M. Zhao et al., “RF-based 3D skeletons,” in Proc. ACM Conf. ACM
     direction estimation using wireless signals,” in Proc. ACM Int.                  Special Int. Group Data Commun., 2018, pp. 267–281.
     Joint Conf. Pervasive Ubiquitous Comput., 2016, pp. 351–362.                [58] W. Jiang et al., “Towards 3D human pose construction using WiFi,”
[41] F. Adib, Z. Kabelac, and D. Katabi, “Multi-person localization via               in Proc. Annu. Int. Conf. Mobile Comput. Netw., 2020, pp. 1–14.
     RF body reflections,” in Proc. 12th USENIX Conf. Networked Syst.
     Des. Implementation, 2015, pp. 279–292.                                                              Zheng Yang (Fellow, IEEE) received the BE
[42] K. Qian, C. Wu, Y. Zhang, G. Zhang, Z. Yang, and Y. Liu, “Widar2.0:                                  degree in computer science from Tsinghua Uni-
     Passive human tracking with a single Wi-Fi link,” in Proc. 16th Annu.                                versity, in 2006, and the PhD degree in computer
     Int. Conf. Mobile Syst. Appl. Serv., 2018, pp. 350–361.                                              science from the Hong Kong University of Sci-
[43] K. Ali, A. X. Liu, W. Wang, and M. Shahzad, “Keystroke recogni-                                      ence and Technology, in 2010. He is currently an
     tion using WiFi signals,” in Proc. 21st Annu. Int. Conf. Mobile Com-                                 associate professor with Tsinghua University. His
     put. Netw., 2015, pp. 90–102.                                                                        main research interests include wireless ad-hoc/
[44] Q. Pu, S. Gupta, S. Gollakota, and S. Patel, “Whole-home gesture                                     sensor networks and mobile computing.
     recognition using wireless signals,” in Proc. ACM Annu. Int. Conf.
     Mobile Comput. Netw., 2013, pp. 27–38.
[45] Y. Zhang, Z. Yang, G. Zhang, C. Wu, and L. Zhang, “XGest:
     Enabling cross-label gesture recognition with RF signals,” ACM
     Trans. Sen. Netw., vol. 17, no. 4, 2021, Art. no. 37.
[46] Y. Zhang, Y. Zheng, G. Zhang, K. Qian, C. Qian, and Z. Yang,                                         Yi Zhang (Student Member, IEEE) received the
     “GaitiD: Robust Wi-Fi based gait recognition,” in Proc. 15th Int.                                    BE degree from the Beijing University of Posts
     Conf. Wirel. Algorithms Syst. Appl., 2020, pp. 730–742.                                              and Telecommunications, in 2017, and the PhD
[47] L. Zhang, Z. Wang, and L. Yang, “Commercial Wi-Fi based fall                                         degree from Tsinghua University, in 2022. His
     detection with environment influence mitigation,” in Proc. 16th                                      research interests include wireless sensing,
     Annu. IEEE Int. Conf. Sens. Commun. Netw., 2019, pp. 1–9.                                            mobile computing, and pattern recognition.
[48] Y. Wang, S. Yang, F. Li, Y. Wu, and Y. Wang, “Fallviewer: A fine-
     grained indoor fall detection system with ubiquitous Wi-Fi devices,”
     IEEE Internet Things J., vol. 8, no. 15, pp. 12 455–12 466, Aug. 2021.
[49] C. Krupitzer, T. Sztyler, J. Edinger, M. Breitbach, H. Stuckensch-
     midt, and C. Becker, “Hips do lie! a position-aware mobile fall
     detection system,” in Proc. IEEE Int. Conf. Pervasive Comput. Com-
     mun., 2018, pp. 1–10.                                                                                Qian Zhang (Student Member, IEEE) received the
[50] Q. T. Huynh, U. D. Nguyen, L. B. Irazabal, G. Nazanin, and B. Q.                                     MS degree in computer science from the Illinois
     Tran, “Optimization of an accelerometer and gyroscope-based fall                                     Institute of Technology, and the PhD degree from
     detection algorithm,” J. Sensors, vol. 2015, 2015, Art. no. 452078.                                  the School of Computer Science, Beijing Institute
[51] O. Steven Eyobu and D. S. Han, “Feature representation and data                                      of Technology, China. She is currently a postdoc
     augmentation for human activity classification based on wearable                                     researcher with the School of Software, Tsinghua
     IMU sensor data using a deep LSTM neural network,” Sensors,                                          University, China. Her research interests include
     vol. 18, no. 9, 2018, Art. no. 2892.                                                                 mobile computing, smart sensing, and mobile
[52] T. Theodoridis, V. Solachidis, N. Vretos, and P. Daras, “Human                                       crowd sensing.
     fall detection from acceleration measurements using a recurrent
     neural network,” in Proc. Int. Conf. Biomed. Health Inform., 2018,
     pp. 145–149.
[53] Y. Huang, W. Chen, H. Chen, L. Wang, and K. Wu, “G-fall:
     Device-free and training-free fall detection with geophones,” in            " For more information on this or any other computing topic,
     Proc. 16th Annu. IEEE Int. Conf. Sens. Commun. Netw., 2019, pp. 1–9.        please visit our Digital Library at www.computer.org/csdl.




       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 16:10:59 UTC from IEEE Xplore. Restrictions apply.

