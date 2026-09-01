                   Received 17 May 2024; accepted 5 June 2024. Date of publication 7 June 2024; date of current version 1 July 2024.
                                                        Digital Object Identifier 10.1109/OJCOMS.2024.3411529




     WiFi-Based Human Sensing With Deep Learning:
     Recent Advances, Challenges, and Opportunities
                  IFTIKHAR AHMAD                 (Student Member, IEEE), ARIF ULLAH                                    (Member, IEEE),
                                                AND WOOYEOL CHOI (Member, IEEE)
                 Department of Computer Engineering, College of IT Convergence, Chosun University, Gwangju 61452, Republic of Korea
                                           CORRESPONDING AUTHOR: W. CHOI (e-mail: wyc@chosun.ac.kr)
                                     This work was supported by the research fund from Chosun University in 2024.




          ABSTRACT The rapid advancements in wireless technologies have led to numerous research studies that
          provide evidence of the successful utilization of wireless signals, particularly, WiFi signals for human
          activity sensing in the indoor environment. As a promising technology, WiFi-based human sensing can
          be utilized for a variety of applications such as smart healthcare, smart homes, security, industry, office
          indoor environments etc., due to the availability of rich infrastructure. Furthermore, compared to other
          radio frequency (RF) based systems such as radio detection and ranging (RADAR) and radio frequency
          identification (RFID), WiFi is non-invasive, has low-cost, and provides ubiquitous coverage in the indoor
          setup. However, due to the limited accuracy and high complexity of the model-based approaches for
          human sensing, the systems empowered by the deep learning (DL) techniques have achieved remarkable
          performance gains and showed more robustness in dealing with complicated human sensing tasks. The
          article explores the physical layer parameters used in WiFi sensing such as received signal strength indicator
          (RSSI) and channel state information (CSI), the estimated parameters such as angle-of-arrival (AoA)
          and Doppler shift (DS) along with frequency modulated continuous wave (FMCW) RADAR technology.
          Moreover, the preliminary signal processing stages that are applied to the received WiFi signals in the
          DL assisted systems are discussed. This article provides a comprehensive literature survey on the recent
          advances in DL-empowered WiFi sensing focusing on human activity recognition and movement tracking
          followed by fall detection, single task-multi task classification, crowd monitoring and sensing, indoor
          localization, gaits recognition, and pose estimation. Furthermore, the paper highlight the challenges in
          the existing literature and discusses the possible future research directions in WiFi-based human sensing
          assisted by DL techniques.

          INDEX TERMS Deep learning, device-based sensing, device-free sensing, human activity recognition,
          human pose estimation, indoor localization, machine learning, RF-sensing.




I. INTRODUCTION                                                                     and smart home systems [1], [2]. RF systems use radio waves

T    HE WIDE range of emerging wireless technologies
     has triggered significant advancement in the fields of
wireless communication, networking, and sensing. Within
                                                                                    to transmit and receive signals, and can be used for sensing
                                                                                    by capturing significant information about the presence and
                                                                                    movements of people within a defined space. This data
this dynamic landscape, emerging radio frequency (RF)                               is obtained by analyzing how the radio waves change as
sensing stands as a notable and innovative stride that has                          they interact with the humans in the surrounding. Unlike
the potential to redefine our perception and interaction with                       traditional methods that rely on cameras or physical sensors,
the world around us. By utilizing the basic principles of                           RF-based sensing remains unaffected by visual obstructions,
RF signals, RF-based human sensing systems are capable of                           illumination, or external disruptions [3]. This characteristic
identifying humans, detecting falls, monitoring humans, and                         offers benefit in scenarios where ensuring privacy, safety,
more especially in the development of security, healthcare,                         and avoiding the necessity of a direct line of sight (LoS) is
                       2024 The Authors. This work is licensed under a Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 License.
                      c
                                            For more information, see https://creativecommons.org/licenses/by-nc-nd/4.0/
VOLUME 5, 2024                                                                                                                                  3595
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




of utmost significance [4]. Human sensing technology can be      breakthroughs in training algorithms as well as growing
either device-based and device-free. Device-based approach       interest across diverse domains [16]. The integration of RF-
utilize dedicated hardware or wearable devices such as           based sensing with DL has brought a transformative impact
smartphones and motion capture systems to track movements        in contactless sensing and provide solutions to numerous
while device-free sensing relies on existing infrastructure or   challenges [17], [18]. A sophisticated artificial neural
ambient signals for human monitoring. One such technique         networks (ANN) characterized by multiple layers, commonly
utilizes RF signals for human activities recognition to enable   referred to as deep neural networks (DNN), is employed
non-intrusive monitoring in both LoS and non-line-of-sight       to extract vital information from extensive RF signals.
(NLoS) scenarios. However, these sensing methods present         Generally, the DNN comprise multiple hidden layers and
unique advantages and challenges, which drive ongoing            follow iterative weight adjustments during data processing,
research for integration into healthcare, security, smart        thereby improve their learning ability and identify complex
environments, and human-computer interaction.                    patterns to enhance their proficiency in extracting valuable
                                                                 information from RF data. DL models are adaptable to
A. DEVICE-BASED AND DEVICE-FREE SENSING                          dynamic environments and improving the accuracy and
Within the realm of human-computer interaction and envi-         robustness of real-time sensing applications by continuously
ronmental monitoring, two primary paradigms emerge such          updating their knowledge through learning from the RF
as device-based human sensing and device-free sensing. The       data [19]. Additionally, DL enables the fusion of RF
former involves the deliberate deployment of specialized         sensing with other sensing modalities such as cameras to
sensors or devices designed to monitor and interpret human       improve the accuracy and insights in complex scenarios [20].
actions and behaviors such as wearable fitness trackers [5],     Furthermore, RF signal has inherent non-linear characteris-
motion sensors [6], pyroelectric infrared (PIR) sensors [7],     tics and DL models perform exceptionally in capturing these
stretch sensors [8], acoustic-based sensors [9], [10], smart-    non-linear relationships between input features and target
watches [11], [12], cameras [13], and medical monitoring         variables [21]. This nonlinearity is particularly crucial in RF
sensors [14] that track different parameters like heart rate,    sensing where basic linear models may find it challenging
steps taken, sleep patterns, and even skin temperature. On       to comprehend the underlying patterns effectively.
the other hand, Device-free human sensing uses RF signals           Within the realm of RF sensing, sensing is done using
to enables the observation and analysis of human behaviors,      radio detection and ranging (RADAR), radio frequency
movements, and presence without relying on specialized           identification (RFID), and WiFi-based systems [22], [23].
sensors or wearable devices. This methodology takes advan-       RADAR utilizes radio waves to detect human movements
tage of existing infrastructure such as ambient signals, WiFi    and gestures and is applicable in domains like security and
routers, and radio waves to detect alterations caused by         healthcare while RFID employs RF signals to recognize and
human activities and motions within the vicinity [3]. To sum     oversee individuals via tags or cards and its application spans
up, device-based sensing is remarkable for its accuracy in       from access control to healthcare oversight. Meanwhile,
measuring specific data points but it can be invasive and        WiFi-based sensing utilizes WiFi signals to detect and
expensive. On the other hand, device-free sensing though is      monitor human presence and collectively underscores the
not as detailed in data collection but it provides solutions     potential to enable a thorough comprehension of human
that are respectful to privacy, is less intrusive, and could     behaviors and interactions. Expanding the discussion on RF-
be scale up more easily by using the infrastructure already      based human sensing methods, we provided brief overviews
in place [15]. Choosing between these approaches depends         of RADAR, RFID, and WiFi-based sensing in the next
on the particular situation and finding the right balance        sections.
between accurate information and practical considerations.
Device-free sensing is advantageous in a situation where the     1) RADAR-BASED SENSING
installation of physical sensors is challenging and to avoid     A typical RADAR system involves a transmitter and receiver,
expensive system expansion for effective monitoring.             where an electromagnetic signal is transmitted by the
                                                                 transmitter and collected by the receiver with a processing
B. RF-SENSING TECHNOLOGIES                                       capabilities to perform further data analysis. The RADAR
RF-based human sensing constitutes a dynamic field that          systems can be classified into active and passive system.
employs RF signals to comprehend and assess human                Both differs from each other in a sense, that active RADAR
presence and behaviors. Development in RF hardware,              uses the bounce signal off the objects while passive RADAR
signal processing methods, and machine learning (ML)             analyzes disruptions in existing signals for detection. When
algorithms have collectively contributed the advancement         objects intercept the transmitted radio signal results in
to enhance accuracy, reliability, and real-time capabilities     scattering which propagates the information regarding the
along with seamless integration of RF-based human sensing        range, velocity, trajectory, and identity. The well known
technologies. The deep learning (DL) has experienced             Doppler effect is utilized to measure the velocity by assessing
notable progress in recent years driven by the accessi-          frequency shifts in the RADAR signal. Object identification
bility of powerful computing resources such as GPUs,             relies on micro-Doppler signatures, tiny modulations induced

3596                                                                                                                VOLUME 5, 2024
by slight movements in an object’s oscillating or rotating
parts. In human monitoring, these signatures reflect specific
patterns in torso, limb, and head movements during motion
unique to individuals and activities and serve automated clas-
sification and monitoring objectives effectively [24], [25].
   Considerable research has been carried out in the area
of RADAR-based human activity recognition (HAR) by
utilizing DL approaches [26], [27], [28]. The authors in [29]
present a novel method for hand gesture recognition using
feature cubes encoded by three dimensional fast Fourier
transform (3D-FFT) using convolutional neural network
(CNN) architecture with specialized spatiotemporal convo-
lution blocks. The approach achieves recognition rates of         FIGURE 1. WiFi-based human sensing [3].

99.53% and 97.22% on the dataset validation and testing
stage, respectively, and surpasses the existing approaches.
FallWatch is an learning model that detect real-time falls        and classifying phase values. The authors in [41] consider
despite visual obstructions [30]. It employs trained CNN,         an ambient framework for HAR using multivariate Gaussian
attention mechanism, recurrent neural network (RNN), and          modeling and employs maximum likelihood estimation for
long short-term memory (LSTM) fall detection from signal          feature learning. Comprehensive experiments shows accurate
collected through antenna array. FallWatch excels in detect-      predictions, making it suitable for single as well as multi-
ing falls across multiple individuals and settings, surpassing    dwelling settings.
the alternative approaches, and offering a unique solution           DL for RFID-based human sensing is explored in the liter-
for elderly fall monitoring. Frequency-modulated continuous       ature such as the authors in [42] propose TagFree which is a
wave (FMCW) RADAR provides exceptional benefits with              pioneer device-free RFID-based HAR system considering the
superior range and velocity resolution and is well-suited         impact of multipath signal reception, correlations between
for tasks like precise distance measurements, gesture recog-      signal power, angles, and activities, and capturing angle data
nition, and effective object tracking [31], [32], [33], [34].     while analyzing it through DL. TagFree is demonstrated by
The authors in [35] employ FMCW RADAR for falls                   an Impinj reader prototype and show superior performance
detection achieving 95.5% accuracy in identifying six fall-       in multipath-rich environments. A passive RFID sensor tag
like movements using the dynamic range-Doppler trajectory         system employing RFMicron’s Magnus S chip is presented
(DRDT) and a subspace K-nearest neighbor (KNN) classifier.        in [43]. It measures RSSI and pressure changes in indoor
Similarly, a new preprocessing method is introduced in [36]       footwear during activities. Extracted features are used for
to tackle static interference and estimate range, velocity, and   ML-based activity classification and achieve high accuracy
angle features for gesture recognition using CNN.                 for different subjects. The authors in [44] introduce DeepTag
                                                                  which is an advanced DL-based RFID framework which
2) RFID-BASED SENSING                                             extracts key features from phase data and uses a hybrid
Different from the traditional RFID applications concentrated     architecture for signal analysis, adapting well to various
on object identification, RFID-based human sensing employs        scenarios and demonstrating superiority in multipath-rich
RFID technology to monitor human presence and movements           settings. The back scatter RFID tag can be read by WiFi
within the vicinity. This method prioritizes human interac-       device for sensing. However, tag needs to be deployed in the
tions with the environment through strategically positioned       close proximity of WiFi device to work robustly in NLoS
RFID tags or sensors. The system recognize the entry of indi-     scenarios which limit their operating range.
viduals with RFID tags, enabling presence detection, location
tracking, motion analysis, and interactions with tagged           3) WIFI-BASED SENSING
objects. Its applicability spans smart homes, healthcare, and     WiFi sensing is an emerging technology that uses WiFi
retail, fostering context-aware systems, occupancy moni-          signal to perceive and interpret the surrounding environment
toring, and personalized experiences derived from human           and offer numerous applications such as indoor localization,
behavior. The RFID technology is utilised for automatic           HAR, environmental monitoring, pose estimation, and even
identification in the context of the Internet-of-Things (IoT)     gesture identification. Fig. 1 illustrates the general frame-
technology [37], [38], [39]. Recent advancements in wireless      work for WiFi based human sensing and its applications..
sensing for tracking human activities have encountered            Nevertheless, striving to interpret WiFi signals and derive
challenges such as direct contact or specialized hardware         substantive insights from them poses a major challenge.
requirements of RFID-based systems. The authors in [40]           Compared to RADAR and RFID-based sensing, WiFi-based
introduce TACT, a contact-free approach utilizing common          human sensing offers distinct advantages such as utilizing
RFID systems to detect and classify human activities and          existing infrastructure and reducing deployment complexity
achieves 93.5% precision in diverse scenarios by segmenting       and costs. Moreover, it provides higher resolution data

VOLUME 5, 2024                                                                                                              3597
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




due to higher frequency signals, enabling finer movement            the other hand, the learning approaches perform well as it
tracking. Unlike RADAR technology, which is unable to               enables processing of high dimensional data. Although a
see through walls, WiFi-based sensing provides extensive            substantial amount of work has been conducted in this field,
coverage with no blind spots. Additionally, WiFi affordability      there is still significant room for further enhancement. This
and widespread availability enable WiFi sensing to detect           article deeply explores the existing works in the domain
presence in the WiFi range. Similarly, as RFID deployments          of WiFi-based human sensing employing sophisticated DL
are constrained by infrastructure limitations, WiFi sensing         approaches.
utilizes the existing WiFi infrastructure with minor firmware
updates. Another advantage of WiFi over RFID is its superior        C. DEEP LEARNING FORWIFI-BASED SENSING
accuracy, attributed to its wider bandwidth and more sophis-        DL takes on a crucial role, granting significant benefits to
ticated signal processing capabilities, facilitating precise        WiFi sensing [18]. DL-based WiFi sensing stands out from
sensing [45]. The widespread WiFi adoption enhances scala-          other RF technologies such as RADAR and RFID due to its
bility for smart environments, making it a versatile approach       use of the extensive and continuous signal data provided by
for applications like smart homes and healthcare. WiFi-based        existing WiFi networks. This rich data stream enables more
sensing capitalizes disruptions within the wireless channels        precise detection of subtle human behaviors and enhances
caused by human activities and movement within the vicinity         the granularity of movement tracking. In comparison, other
changes the signal propagation, manifesting as variations           RF methods are typically more specialized, and tailored
in channel state information (CSI) [46]. This dynamic CSI           for specific applications that may not demand such com-
holds valuable insights into human motion and interactions.         prehensive data collection. WiFi-based sensing with DL
Leveraging the WiFi signals from WiFi routers, Intel 5300           enables accurate classification of specific body movements,
network interface cards (NIC) [47], and Atheros [48]                relying on unique WiFi signal changes linked to human
stands out for its cost-effectiveness and easy deployment.          presence and activities [57]. The authors in [58] designed
These devices integrated into WiFi infrastructure utilizes          WiFi CSI-based framework with CP factorization, graph
orthogonal frequency division multiplexing (OFDM) by                learning based optimized features, and used RNN for daily
dividing the signals into subcarriers with independent data         activity detection that work well without requiring human
transmissions [49]. Human presence disrupts subcarriers and         intervention. Different ML algorithms are applied on CSI
alters signal attributes captured by the CSI.                       datasets for motion detection in [59] and the results show
   WiFi devices operating in 2.4GHz or 5GHz bands provides          that RNN provide superior performance in case of larger
balanced coverage and data rates for indoor and extended-           datasets. The existing literature extensively employed DL
range user. Extracting patterns from OFDM subcarriers,              techniques for the HAR using WiFi signals for a diverse set
WiFi sensing identifies and categorizes human activities            of tasks such as fall detection, classifying different activities,
for context-aware applications. Different from conventional         monitoring human behavior, and identifying walking patterns
methods relying on received signal strength indicator (RSSI)        (gaits), etc., [60], [61], [62], [63], [64], [65]. SenseFi [57],
which struggles with noise and subtle movements, the                is an open-source benchmark and DL library for WiFi-based
CSI approach exploits signal amplitude and phase details            human sensing evaluated for different datasets. Furthermore,
to detect minute motions at sub-cm levels across various            the authors in [66] presents the detailed investigation of DL
frequency channels. This sophisticated technique encom-             techniques on WiFi-based HAR using CSI.
passes data collection, signal processing, and classification
stages reminiscent of detection processes. The WiFi based           D. LITERATURE SELECTION FOR THE SURVEY
sensing methods includes model-based and learning based             For the comprehensive survey, an organized approach was
approaches. Both approaches differs from each other in a            used to search for related research publications on WiFi
sense that the former methods rely on physical model based          sensing. A range of reputable databases were meticulously
signal propagation such as Fresnel Zone while the later             accessed, including Google Scholar, IEEE Xplore, ACM
uses trained model to approximate function and classify the         Digital Library, Science Direct, Springer, and Archive. A
input WiFi signal. The model-based approaches withstand             range of keywords including “RF human sensing,” “WiFi
environmental changes, however, they often fail to achieve          sensing”, “DL”, “CSI”, “fall detection”, “pose estimation”,
significant performance improvements in case of the com-            “localization”, and “HAR” were employed to identify rel-
plicated human activities in coarse-grained applications [46].      evant literature. The primary focus is to review the recent
Furthermore, it is extremely challenging to determine               research works on WiFi sensing with a specific temporal
accurate mathematical to approximate correlations between           constraint ensuring the inclusion of papers published in the
complex human actions and variations in WiFi signals.               last five years to capture the most current developments in
Moreover, the model-based approaches suffers performance            the field. The source diversity was a key aspect, including
degradation in NLoS scenarios. In this regard, WiseFi system        survey papers, high-impact journal articles from esteemed
is proposed in [50], where the authors illustrate this limitation   journals like the IEEE IoT Journal, IEEE Transactions on
and achieve a median recognition accuracy of just 74.3%             Mobile Computing, IEEE Transactions on Aerospace and
in case of the signal transmission through single wall. On          Electronic Systems, and conference papers from prestigious

3598                                                                                                                     VOLUME 5, 2024
TABLE 1. How does this survey vary from other surveys on RF-sensing. LC, MC, and HC denotes low, medium, and high coverage, respectively, while C and LR
denotes the DL coverage and the number of literature surveyed on the topic.




events such as CVF, ICCV, ICML, ICASSP, and CVPR. We                            community to advance research, innovation, development,
closely examined the literature to make sure it matches our                     and recent insights into WiFi-based HAR. To the best of our
research goals and keywords. By continuously Web searching                      knowledge, this is the first survey that presents DL-aided
over the databases, we ensured to identify the most up-to-                      WiFi-based HAR, particularly concentrating on whole-body
date literature which led to a compilation of this work.                        activities. Table 1 provides a comparison of this work with
                                                                                other related surveys published on the topics.
E. CONTRIBUTIONS AND PAPER ORGANIZATION                                            The main contributions of this survey are as follows.
Numerous recent surveys have addressed RF-based human                              • This survey offers an extensive review of WiFi-based
sensing, encompassing RADAR-based sensing [67], [68],                                human behavior recognition through DL, highlighting
RFID-based sensing [69], [70], and WiFi-based sensing [52],                          contributions from a wide range of recent research
[53], [56], [71], [72]. However, these surveys provide                               works.
extensive insights into diverse techniques and applications.                       • This survey illustrates how DL effectively tracks
This paper provides a literature review on WiFi-based                                human movements via WiFi signals, showcasing diverse
HAR, emphasizing the integration of DL approaches with                               methodologies and results.
more comprehension and detailed analysis. Furthermore,                             • This survey presents studies that merge WiFi signals
WiFi-based HAR using DL techniques is deeply analysis                                and DL for human pose estimation (HPE), illuminating
with a specific emphasis on full-body-involved activities. It                        the realm of contactless pose inference.
addresses a pivotal aspect of human behavior analysis, cat-                        • This survey paper explores the existing challenges and
egorizing existing research, methodologies, and applications                         possible future research directions in the realm of WiFi-
to enhance the understanding of leveraging WiFi signals for                          based sensing.
complex human activity detection. Moreover, a systematic                        As depicted graphically in Fig. 2, the rest of the paper
presentation on the recent advancements, challenges, and                        is organized as follows. Section II explores the RF-based
opportunities is highlighted to shed light on employing DL                      human sensing including the technical background, key
techniques to improve accuracy, robustness, and real-world                      concepts of RF sensing including WiFi, and the employment
applicability. This work provides a guideline for the research                  of DL for WiFi sensing followed by signal processing

VOLUME 5, 2024                                                                                                                                             3599
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




FIGURE 2. Paper structure and organization.



preliminaries. Section III provides a detailed overview of      wireless signals propagating across varying distances. It
existing works on DL for different WiFi based sensing tasks.    finds extensive application in tasks such as localization
Section IV presents the challenges and the possible future      of individuals [73]. Within the domain of human sensing,
directions related to WiFi sensing. Finally, the paper is       the proximity of an individual introduces signal attenuation
summarized and concluded in Section V.                          which leads to dynamic fluctuations in the RSSI values in
                                                                the sensing area. While readily accessible across numerous
II. FROM RAW DATA TO LEARNING INPUT:                            WiFi devices, RSSI’s granularity remains limited, providing
PARAMETERS AND PREPROCESSING FOR DEEP                           a singular numerical representation of signal loss [74].
LEARNING
                                                                This constrained information content hampers its capacity
For human activity detection, RF-based human sensing
                                                                to discern a comprehensive spectrum of human activities.
devices utilize technical aspects of received RF signals. The
                                                                Nonetheless, the RSSI remains a valuable tool in the realm of
commonly used metric used for measuring signal properties
                                                                RF human sensing, enabling insights into human movement
in RF sensing includes RSSI, CSI, FMCW, angle of arrival
                                                                through RF signal analysis [75]. Moreover, the RSSI values
(AoA), and Doppler shift (DS). This received raw signal
                                                                can exhibit variability even in the absence of movement
is preprocessed, transformed, and significant features are
                                                                which poses challenges to their reliability in real-world
extracted to decipher human actions accurately. These steps
                                                                scenarios especially in fine-grained HAR.
enable the subsequent analysis and recognition of diverse
behaviors and play essential role in the initial stage of
                                                                2) CHANNEL STATE INFORMATION
translating RF signals into valuable insights about human
presence and motion. Generally, RSSI and CSI is utilized        The information regarding channel condition is a pivotal
in commodity devices like WiFi while FMCW is used by            factor in RF human sensing, providing a valuable avenue to
RADAR and AoA and DS are estimated parameters.                  discern intricate human behaviors and motions by analyzing
                                                                shifts within the wireless channel caused by these actions.
A. KEY CONCEPTS FOR RF SENSING                                  Compared to metrics like RSSI, CSI offers a more detailed
In this section, we briefly discusses the physical layer        view of the wireless signal. CSI is composed of complex
parameters such as RSSI and CSI followed by FMCW                values that include both amplitude and phase information
RADAR technology, and other estimated parameters such as        across multiple OFDM subcarriers. These subcarriers capture
AoA and DS used in RF-based human sensing.                      distinct multi-path fading effects and collectively create
                                                                a detailed picture of the wireless channel. The IEEE
1) RECEIVED SIGNAL STRENGTH INDICATOR (RSSI)                    802.11n standard provides CSI measurements for 52 and
The RSSI serves as a fundamental metric akin to a measuring     128 subcarriers, each with bandwidths of 20MHz and
instrument in RF sensing. It quantifies the amplitude of        40MHz, respectively, while the emerging 802.11ac standard

3600                                                                                                             VOLUME 5, 2024
supports even wider bandwidths [52]. As individuals move          algorithms are required in such systems because the envi-
within WiFi or RF device coverage, their motion change            ronmental factors such as signal reflection and interference
to the wireless channel condition which leads to variations       effect the AoA of the received signal. Essentially, AoA
in the signal amplitude and phase across distinct subcar-         enriches human sensing techniques and enables interpreting
riers. Devices equipped with multiple-input-multiple-output       movement patterns in real-world scenarios using specialized
(MIMO) transmission capabilities can capture these varia-         hardware setups such as Texas Instruments FMCW RADAR
tions to construct the CSI matrix. The CSI matrix captures        sensors [17].
temporal and spatial changes due to human actions, enabling
recognition of subtle gestures, actions, and even breathing       5) DOPPLER SHIFT
patterns. DL techniques and pattern recognition algorithms        DS also known as Doppler effect refers to the change in
learn the intricate patterns within CSI data and enable the       frequency or wavelength of a wave due to the relative
identification and classification of specific human activities.   motion between the source and the observer. The DS has a
Similar to RSSI, CSI measurements can be acquired using           significant role in RF sensing, offering a unique perspective
readily accessible WiFi devices such as Intel 5300 NIC [47],      to observe human activities and movements. Emerging from
and Atheros [48] with customized drivers. The applicability       the changes in frequency caused by human motion in the
of CSI-based human sensing spans security, healthcare,            vicinity, the DS helps identify and track scenario-dependent
and smart homes, offering notable accuracy and versatility.       dynamics and imparts essential insights into movement
Nevertheless, challenges exist such as advanced hardware,         speed and direction. Analogous to signals emitted by a
complex signal processing, environmental influences, and          transmitter and reflecting off the human body, any bodily
calibration requirements. In essence, CSI emerges as a robust     motion triggers DS. Importantly, moving towards the receiver
asset in WiFi-based human sensing providing huge data that        induces a positive frequency shift, while moving away causes
empowers precise and comprehensive HAR in diverse real-           a negative frequency change which facilitates the tracking
world scenarios through accurate analysis based on DL and         the inference of motion patterns, covering activities like
advanced signal processing techniques.                            walking, running, and even vital signs [79], [80], [81]. The
                                                                  application of Doppler-based human sensing is especially
3) FREQUENCY MODULATED CONTINUOUS WAVE                            crucial in domains requiring accurate real-time motion
The FMCW is a vital technique in RF especially RADAR              tracking, including security and healthcare applications.
based human sensing which involves the emission of                Despite its significance, effectively utilizing DS demands
a continuous wave signal with a frequency sweep or                customized hardware setups and advanced signal processing
chirp that gradually increases or decreases. This signal          to precisely extract and interpret frequency alterations [82].
interacts with the environment and produces a frequency
beat arises from the difference between the transmitted           B. PRELIMINARY PROCESSING AND EMPLOYMENT
and received frequencies. This beat frequency carries cru-        OFDEEP LEARNING IN WIFI-BASED HUMAN SENSING
cial distance-related information about objects, facilitating     Proceeding with attention directed toward the utilization
accurate distance measurement [2]. FMCW excels in RF              of WiFi signals for human sensing, this section primarily
sensing because changes in the beat frequency due to human        focuses on CSI and RSSI. As a pivotal part of WiFi-based
movements enable the detection and tracking of individuals’       human sensing, signal processing techniques convert the raw
positions [30], [31], [76], [77]. FMCW’s capacity to distin-      signal data into valuable insights defining human activities.
guish between various targets based on motion characteristics     These methods encompass denoising for cleaner CSI data,
allows simultaneous identification of multiple individuals.       signal transformation like Fourier and wavelet transforms
Despite specialized hardware requirements, FMCW can               to unveil temporal and frequency patterns, and feature
generate and analyze the modulated signal at both the             extraction to distill these patterns for behavior recognition as
transmitter and receiver.                                         shown in Fig. 3. Together, these strategies enable a precise
                                                                  understanding of human presence and motion in the WiFi
4) ANGLE OF ARRIVAL                                               coverage area.
The concept of AoA in RF-based provide a distinct approach
to understanding human movements which determine the              1) PREPROCESSING AND DENOISING
direction from which wireless signals reaches at the receiv-      In WiFi-based human sensing, preprocessing of CSI data
ing antenna, offering insights into spatial orientation and       is an essential phase that refines raw signal which involves
movement patterns. Analyzing signal angles from different         a sequence of operations intending to improve the quality
antennas make it possible to track activities such as walking,    and reliability of collected CSI data. Initially the data
gestures, and posture changes [78]. Commonly, an antenna          calibration is performed to rectify systematic errors and
array captures signals from various directions where varia-       ensure precise measurements. Subsequently, techniques like
tions in the signal phase and intensity reveal arrival angles.    filtering and smoothing are applied to counteract unwanted
TAoA data for human activity insights is derived through          interference, environmental fluctuations, and noise reduc-
DL and signal processing. Advanced signal processing              tion [83], [84], [85]. The preprocessing phase also identifies

VOLUME 5, 2024                                                                                                                3601
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




                                                                   shows the characteristics of data distribution [89]. Temporal
                                                                   features analyze patterns within specific time intervals and
                                                                   uncover rhythms and periodicity. Frequency-domain fea-
                                                                   tures expose spectral components such as peak frequencies
                                                                   and spectral bandwidth, aiding in distinguishing activities
                                                                   with distinct frequency attributes. Time-frequency features
                                                                   such as mel-frequency cepstral coefficients (MFCCs) com-
                                                                   bine time and frequency information to capture nuanced
FIGURE 3. An overview of the signal processing sequence.
                                                                   variations [90]. Principal component analysis (PCA) and
                                                                   independent component analysis (ICA) are utilized for data
and eliminates outliers and anomalies in the data to fur-          analysis and dimensionality reduction [91]. They are com-
ther enhance the quality of the utilized dataset [86], [87].       monly applied in ML to preprocess data before employing
Ultimately, preprocessing establishes a solid foundation for       classification. The careful selection of relevant features
subsequent signal processing and DL techniques.                    is pivotal for ensuring the precision and effectiveness of
                                                                   subsequent analyses.
2) SIGNAL TRANSFORMATION
After preprocessing of WiFi signals, the collected CSI data        4) EMPLOYMENT OF DL MODELS FOR HUMAN SENSING
requires signal transformation which is pivotal in reveal-         After applying the aforementioned signal processing steps on
ing underlying patterns, temporal dynamics, and frequency          the collected dataset for a particular environment and sensing
characteristics within the data to enable more profound            scenario, the DL model is trained to associate specific
understanding of human activities and movements. One               signal patterns with corresponding human activities such as
notable technique is the Fourier transform (FT) which              walking, sitting, falling, pose estimation, localization etc.
translates the CSI data from the time domain to the frequency      Once properly trained on large data, the model is tested
domain, unveiling the distinct frequency components embed-         on unseen data to evaluate the accuracy performance of the
ded in the signal. This translation aids in identifying patterns   model. The trained model is then deployed to accurately
and periodicity tied to specific human actions like walking        predict and classify human activities by leveraging the
and breathing. An additional powerful method is the wavelet        learned parameters from WiFi signal data. Additionally, the
transform which differs from the FT and allows both                DL models continuously learn and adapt to new patterns
frequency and time localization [56], [88]. This capability is     over time through techniques such as transfer learning to
particularly useful for capturing rapid changes and transient      enhance the accuracy and robustness.
events in the signal. Wavelet analysis furnishes a multi-
resolution representation of the CSI data and facilitates the      III. SURVEY OF WIFI-ENABLED HUMAN SENSING
detection of both high- and low-frequency changes across           LEVERAGING DEEP LEARNING
varying time intervals to enable the recognition of a diverse      In the recent years, DL has emerged as a powerful tool
array of human activities. Visual depictions like spectrograms     in various revolutionizing fields by replacing the traditional
or heatmaps assist in discerning frequency patterns correlated     model based approaches with learnable model for data
with human actions. However, in spite of the robust tech-          analysis and processing. Different DL architectures have
niques, proper parameter adjustment and function selection         been utilized in the literature for WiFi-based human sensing
are imperative to unveil pertinent information in the CSI          including multilayer Perceptron (MLP), CNN, simple RNN
data.                                                              (SRNN), LSTM, BiLSTM, GRU, residual network (ResNet),
                                                                   autoencoder, transformer, and hybrid models. The hybrid
3) FEATURE EXTRACTION                                              model are the combination of multiple standalone DL models
After noise removal, certain systems directly derive features      to enable efficient learning.
from the time-domain data, while others transform it into the         MLP: MLP comprises multiple interconnected layers of
frequency domain using techniques like short-time Fourier          neurons with weighted connections. The MLP layers includes
transform (STFT) or discrete wavelet transform (DWT)               input layer, several hidden layers, and an output layer. Input
to create spectrograms. After preprocessing and signal             data is fed in to the input layer and passed through the hidden
transformation step, the features are extracted from the actual    layer employing nonlinear activation functions to process
data in the next phase. The transformed data is translated into    input data. Each hidden layers follow the data weighting
the representative features that encapsulate crucial insights      and biasing before passing it to the output layer. This MLP
about human activities and movements, forming the basis            architecture is trained via back-propagation and can be used
for subsequent analysis and classification. Feature extraction     for classification, regression, and feature learning.
methods aim to capture pertinent aspects of the data while            CNN: CNN is feed forward neural network and process
reducing noise and redundancy. Common techniques used              2D grid data such images and matrix with correlated row
for feature extraction include statistical features such as        and columns to learn spatial features in the input data
mean, standard deviation, skewness, and kurtosis which             by utilizing set of kernels for convolution [162]. CNNs

3602                                                                                                                  VOLUME 5, 2024
TABLE 2. Deep learning techniques for WiFi based sensing.




                                             [31]




uses supervised learning to extract features from the input        and integrating new input, thereby simplifying the model
data autonomously without human assistance, making them            while still effectively handling short-term memory challenges
useful for applications like object identification and image       in sequences.
classification.                                                       BiLSTM: BiLSTM is a modified version of LSTM which
   ResNet: ResNet is a type of CNN having skip connec-             utilises two LSTM layer in a bidirectional way. In BiLSTM,
tions or shortcuts allowing to bypass certain convolutional        the forward data flow is handled by one LSTM while the
layers. These connections empower ResNet to maintain high          additional LSTM enable backward data propagation to model
efficiency and effectiveness in training utilizing hundreds of     the two way sequential dependencies in the input data.
layers. The core idea behind ResNet is to enable the training      The output of the two LSTM is then combined either by
of the networks by allowing gradients to flow through the          averaging, summing, or concatenating to generate the final
network without vanishing or exploding. ResNet utilizes            output.
identity mappings as skip connections and perform element-            Autoencoder: Autoencoders is a specific type of DNN
wise addition operations between these connections. ResNet         commonly used for unsupervised learning tasks involving
is effective in tasks such as image classification, object         dimensionality reduction [165]. Autoencoders comprise two
detection, and segmentation.                                       main functions, i.e., encoder and decoder. The encoder
   SRNN: RNN models are exceptional at processing sequen-          compress the input data and the decoder reconstruct the
tial data by utilizing their unique architecture to recall         original data from the compressed representation of the input
previous inputs, thereby influencing output decisions. RNN         data. Notably, the hidden layers of autoencoders typically
can do tasks that depend on the timing and sequence of data        have fewer nodes compared to the input layers, resulting in a
points because of their intrinsic ability to update their states   bottleneck phenomenon that encourages the network to learn
continuously. Unlike other neural networks, which usually          a concise representation of the input data. The autoencoder
interpret input data independently, RNNs dynamically handle        applies to data compression, enhancement, sophisticated data
temporal dependencies [163]. The conventional simple RNN           analysis, image processing, and noise reduction.
(SRNN) exhibit vanishing gradient problem which are dealt             Transformer: The transformer is a powerful architecture
by other variants of RNN such as LSTM, BiLSTM, and                 based on the attention mechanism, famous for its ability
GRU.                                                               to capture long-range dependencies in sequential data with
   LSTM: LSTM model comprises multiple cells and gates.            remarkable efficiency and reduced training time [151]. A
The cell remember the previous values and the three                transformer comprises an encoder-decoder structure, where
gates such as input gate, output gate and a forget gate            both components have multiple identical layers. In the
regulate the data into and out of the cell. LSTM retain the        encoder, each layer consists of two sub-layers: a multi-head
information across long sequences and effectively deal with        self-attention mechanism and a fully connected feed-forward
the tasks demanding comprehensive long-term contextual             network, each followed by residual connection and layer
learning [128].                                                    normalization. The decoder includes an additional sub-layer
   GRU: Gated Recurrent Units (GRUs) is another variant            for multi-head attention over the encoder output.
of RNNs which resemble LSTMs in operation but having a                The brief discussion of these model is provided in the
simpler architecture which comprises two gates instead of          following paras while the application to different sensing
three, i.e., reset and update gate [164]. These gates empower      scenario is listed in Table 2. In the next sections, we present
GRUs to strike a balance between retaining past information        the detailed survey of the aforementioned DL technique

VOLUME 5, 2024                                                                                                                3603
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




applied to WiFi based human sensing in the state-of-the-art         capability to accurately distinguish falls and ensure the
literature.                                                         safety of individuals, especially in challenging scenarios
                                                                    where traditional methods have limited performance. Authors
A. HUMAN ACTIVITY RECOGNITION                                       in [155] proposed a DL method based on EfficientNet [156]
WiFi-based HAR is an emerging and increasingly popular              for fall detection utilizing CSI data collected from WiFi
approach in recent years which non-intrusively monitor              signal and achieve over 96% accuracy. FallCNN is proposed
and analyze human behaviors across diverse environments.            in [126] which is a CNN based learning framework for fall
With continuous advancements in signal processing, neu-             detection utilizing CSI from WiFi signals. The proposed
ral network models, and deployment of wireless device,              scheme is capable of achieving an average accuracy of
WiFi HAR shows great promise in applications such as                95% in seven different indoor environments. Similarly, the
healthcare, smart environments, security, etc. It provides          authors in [106] investigate fall detection in construction site
robust healthcare monitoring through gait recognition and           using different variants of LSTM and reported 99% accuracy
improves eldercare safety by detecting fall. The domain of          on the study case involving six workers and 360 activity
indoor environments has advanced to incorporate motion              sets. The authors in [166] proposed WiFall which utilizes
sensing and population monitoring, along with precise               WiFi CSI to detect human falls without requiring addi-
indoor localization that is essential in huge complexes such        tional hardware, environmental setup, and wearable devices.
as airports and malls. Pose estimation assists treatment,           Extensive simulations shows that WiFall can accurately
increases worker safety in factories or workplaces through          detect falls for a single person in the coverage area. Using
monitoring, and enhances online shopping experiences with           a single class support vector machine (SVM) classifier, the
virtual try-on elements. These developments contribute to a         system achieves an accuracy of 90% with an average FAR
deeper understanding of human interactions and ultimately           of 15% across all testing scenarios while employing the
enhance the overall quality of life. This section provides          random forest algorithm, WiFall achieves an average fall
a discussion on the advancements and comparison of the              detection precision of 94% with FAR of 13%. RT-Fall is
state-of-the-art related to WiFi-based HAR including fall           presented in [130] is a cost-effective indoor fall detection
detection, multi-activity classification, movement tracking,        system that utilizes fine-grained CSI including phase and
indoor localization, gaits recognition, and HPE. Table 3            amplitude from commodity WiFi device and achieves real-
provides a comprehensive performance assessment of various          time contactless fall detection. The authors demonstrate that
learning models for activity recognition in terms of activity       the phase difference of CSI between two antennas is a
types, data collection sources and metrics, antenna systems,        reliable signal for activity recognition which enable accurate
and key performance indicators such as precision, false             fall segmentation. Moreover, a sharp power profile decline
alarm rate (FAR), accuracy, specificity, sensitivity, recall, and   pattern in the time-frequency domain for falls is identified
F1-score.                                                           which extracts new features to improve fall segmentation
                                                                    and detection. Experimental results demonstrate that RT-Fall
1) FALL DETECTION                                                   outperforms the state-of-the-art approaches for four indoor
Human fall is a major problem among elderly citizens                scenarios with an average increase of 14% in sensitivity and
worldwide which results in a considerable number of fatal-          10% in specificity.
ities, particularly for people aged 60 and above. According            Researchers strive to develop a fall detection system
to the World Health Organization (WHO), approximately               with minimal environment dependency and do not requires
646,000 fall-related deaths occur globally and there are            retraining with new data while operating in the new
around 37.3 million falls that are treated medically each           environment. In this regard, the authors in [105] proposes
year [172]. It is projected that by 2030 the number of aged         an adversarial data augmentation (ADA) for WiFi-based
people (60 years or above) will comprise one-sixth of the           domain-independent fall detection system. The CNN-ADA
global population. It became imperative to ensure timely            and LSTM-ADA models are utilized and compared on
rescue for elderly individuals living alone which presents          the FallDeFi dataset including five environments data. The
a pressing public health challenge [173]. To address this           dataset is divided into 10 domains and the semantic distance
issue, traditional methods have been utilized in the literature     between the target and the source is measured using
such as cameras, wearable sensors, and specialized RADAR            Wasserstein distance parameter (p). It is reported that the
hardware to detect falls. However, WiFi-based solution have         accuracy of CNN-ADA drop from 64.12% to 41.51% while
gained popularity due to the widespread availability and            LSTM-ADA exhibits an opposite trend with performance
non-intrusive nature. Utilizing advanced technology such            improvement from 40.20% to 66.03% with an increase
ad MIMO-OFDM-based WiFi systems offers a promising                  in p. However, both models shows poor performance for
approach to detect falls without human intervention and             real-world applications indicating further room for improve-
dependence on lighting condition requirements.                      ment in accuracy and reliability. Similarly, the authors
   Extensive researchers has been carried out to improve            in [174], [175] propose DeFall which utilizes speed and
fall detection in real-world environments using DL algo-            acceleration patterns for fall detection and is capable of
rithms and WiFi based system. These efforts enhance the             working in different environments. The system estimates fall

3604                                                                                                                   VOLUME 5, 2024
TABLE 3. WiFi-based human activities recognition.




   [166]


   [130]


   [105]



   [127]



   [92]


   [167]



   [111]




   [121]




   [108]



   [129]


   [107]


   [110]



   [168]


                                                                                                                 (Continued)


speed using WiFi signals in the offline stage and generates   to detect falls in online stage. DeFall achieve a detection rate
representative templates using dynamic time warping (DTW)     of 96% and a false alarms less than 1.5% through a single
algorithms and compare the real-time motion with templates    pair of WiFi transceiver tested in various scenarios. The

VOLUME 5, 2024                                                                                                            3605
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




TABLE 3. (Continued.) WiFi-based human activities recognition.



   [169]




   [170]



   [171]



   [124]



   [150]



   [151]



   [152]




FallWatch system presented in [30], detects falls in open-air    in five indoor environments and achieves an average accuracy
and through the wall using autoencoder with CNN based            of 84.31% and an average F1 score of 84.56%. Despite
encoder and LSTM models based decoder. The FallWatch             these advancements, the WiFi-based fall detection system is
detect falls effectively in a cross-person and cross-people      still immature and requires further improvement in terms of
scenario by achieving precision, recall, and F1-score of         effectiveness and reliability.
0.923, 0.917, and 0.920, respectively. The authors in [92] by
propose FallDar for fall detection which outperformed the        2) FROM SINGLE-TASK TO MULTI-ACTIVITY
state-of-the-art approaches by simultaneously tackling the       CLASSIFICATION
environmental diversity, motion diversity, and user diversity    Professionals are developing WiFi-based multi-activity clas-
challenges. FallDar utilizes the body’s speed to handle          sification to enable natural human behavior recognition,
environmental diversity and ensure resilience to changing        a promising technology with the potential to enhance
conditions. FallDar uses DNN-based generative model for          applications across these diverse domains such as healthcare,
efficient detection of different types of falls. For user        industry, and smart homes. The authors in [76] utilize a
diversity, fall detection network is augmented with a user       CNN with a rectified linear unit (ReLU) activation function
identification network to extract independent user features      to estimate six different human activities. The experiment
without requiring new user fall data. FallDar is implemented     involved generating signals in compliance with the IEEE
on commercial WiFi devices and tested for over six months        802.11ad standards using a 60 GHz channel and utilize the
in home and office environment trials, achieving FAR and         DS information extracted from pilot subcarriers at the input
missed alarm rate (MAR) of 3.4% and 5.7%, respectively.          of CNN. The CNN performed impressively by achieving a
Similarly, the authors in [167] propose AFall which is a         validation accuracy of 96%, demonstrating its proficiency in
model-based robust fall detection system that utilizes WiFi      accurate recognition of human activities and the substantial
CSI without requiring prior training for individuals. AFall      reduction in the loss function value up to 0.1599 indicates
employs the MUSIC algorithm to model the relationship            the network’s effectiveness in terms of error minimization
between human falls and changes in AoA of the reflected          during training. The authors in [111] present a comparison
WiFi signal from the human body. By using two receivers          between ultra-wideband (UWB) and commodity WiFi setups
in orthogonal spatial layouts, AFall captures diverse AoA        for passive LoS based HAR and evaluated the estimation
information and maintains stable performance even with           performance for five different human activities, i.e., sitting,
slight environmental changes due to the independence of          standing, lying down, standing from the floor, and walking
AoA with the surroundings and subjects. AFall is evaluated       using a range of classifiers including CNN, DNN, Gaussian

3606                                                                                                                VOLUME 5, 2024
naive Bayes (GNB), KNN, and random forest. The channel               The existing research exhibits domain dependence sensing,
impulse response (CIR) samples is used as input to the            where a system performing well in one environment and
classifiers for UWB system while CSI data is utilized for         exhibits performance degradation when tested in another
commodity WiFi system. Simulation results show that CIR-          environment. To overcome this, a robust system is needed to
aided UWB system gives an outstanding F1-score of 95.53%          accurately identify human activities in diverse environments.
and the WiFi CSI amplitude-based input data achieves              Utilizing DL algorithms, the researchers aim to extract
lower F1-score of 92.24% while the WiFi spectrogram-              activity-specific features from the signal while avoiding
based input data yields an F1-score of 80.89%. Additionally,      environment-specific characteristics and ultimately design
irrespective of whether the UWB or WiFi systems are               a versatile scheme independent of the sensing domain.
employed, the random forest classifier consistently out-          In this regard, the authors in [129] investigate WiFi CSI
performs the other classifiers. However, UWB technology           based framework to recognize 13 indoor human activities
presents increased complexity and diminished resilience in        using a single transmitter point (TP) and access point (AP).
NLoS scenarios compared to commodity WiFi systems. A              Online filtering is used for smoother CSI curves, preserving
one-class support vector machine (OSVM) is used in [121]          patterns, and a segmentation technique is utilized to isolates
which highlights the potential of WiFi-based CSI data for         primitive action patterns from MIMO signal. SVM-based
precise multi-activity recognition in complex scenarios. The      multi-classification with selected features enables activity
system distinguishes between a range of human activities          recognition regardless of location, orientation, and speed.
including walking, running, sitting, standing, and greeting       The results show that the SVM with feature selection per-
as well as strenuous motions such as fighting and kicking.        forms better than linear discriminant analysis. A WiFi-based
The system achieves notable accuracy rates of 90.89% for          activity recognition system called WiSDAR is presented
strenuous human motions and 84.43% for normal human               in [107] which incorporates spatial diversity awareness and
body movements. Similarly, the authors in [122] present a         achieves an accuracy rate of approximately 96% in detecting
CNN-attention bidirectional long short-term memory (CNN-          various human activities including walking, falling, sitting,
ABLSTM) based WiFi CSI passive sensing technique,                 running, picking, pushing, waving, and boxing. The proposed
which outperforms the existing learning models in terms           WiSDAR addresses the accuracy degradation challenges that
of accuracy for multiple actions and multiple individuals.        arises when individuals pass through dead zones with ineffec-
In [112] seven distinct human activities are classified           tive signal coverage within the monitored environment. This
using InceptionTime and LSTM-based classification models          is accomplished by integrating spatial diversity techniques.
applied to WiFI CSI data. Similarly, a hybrid DL network          WiSDAR uses a DL model that combines CNNs and LSTM
CNN-gated recurrent unit-attention network (CNN-GRU-              to achieve enhanced HAR performance. The authors in [95]
AttNet) is tested on CSI-HAR and StanWiFi datasets. The           use CNN and hybrid model of RNN and LSTM for HAR
proposed scheme outperforms the traditional DL models with        and achieve an average testing accuracy of 97%. Similarly,
an accuracy improvement of 4.62% compared to GRU, bidi-           two DL models including attention-based bidirectional long
rectional GRU (BiGRU), CNN, LSTM and BiLSTM [114].                short term memory (ABiLSTM) and CNN-ABiLSTM are
The WiFi CSI data is translated into images and processed         utilized in [110] to recognize different human activi-
by CNN based ImgFi in [131], showing 99.5% accuracy               ties across diverse spatial environments. The experimental
for human gestures recognition. WiAReS is an innovative           results demonstrate that by employing a transfer learning
device-free that accurately identify various activities [108]     technique, these models deliver acceptable results when
by utilizing CNN to extract spatiotemporal features from CSI      applied to new environments with varying configurations.
measurements by capturing the spatial and temporal patterns       The performance of WiSDAR for passive HAR is further
of human activities. For enhanced recognition accuracy,           improved in [168] through the utilization of ABLSTM.
WiAReS introduces a unique ensemble architecture that             The ABLSTM utilizes a BiLSTM architecture to extract
combines multiple models including a multi-layer MLP, a           meaningful features from sequential CSI measurements in
random forest, and an SVM. The CSI data is collected using        both forward and backward directions. To capture the varying
standard WiFi devices equipped with Atheros-CSI-Tool on           importance of these learned features, an attention mechanism
AR9590-based WiFi NICs for activities such as sitting down,       is incorporated that assigns different weights to each feature.
jumping, wave, pick up, walk, and run. Extensive experi-          The experimental results demonstrate that the ABLSTM
ments were conducted in activity rooms and laboratories to        achieves superior recognition performance compared to
demonstrate the exceptional performance of WiAReS with an         benchmark schemes. Moreover, its robustness and general-
overall accuracy of 98.1% and 99%, respectively. Similarly,       izability capable them to maintain high performance even
the authors in [31] use predictive approach with trajectory-      when trained in one environment and tested in a different
guided unsupervised learning (TGUL) for the recognition of        one. Another environment-independent (EI) approach is
multiple human actions and demonstrate that the proposed          presented in [169] which extract activity features independent
scheme achieves a mean average precision (mAP) of 91.7            of the environment and subject. The proposed approach
in the fine-tuning setting for the intersection union threshold   employs a feature extractor, an activity recognizer, and
of θ =0.1.                                                        a domain discriminator, where the domain discriminator

VOLUME 5, 2024                                                                                                               3607
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




predicts the environment and encourages the feature extrac-       the state-of-the-art techniques in both cross-user and cross-
tor to generate environment/subject-independent features.         scene scenarios. The authors in [124] integrate bi-directional
Experimental results on six testbeds validate the effectiveness   and attention mechanisms into the gated loop unit (BI-AT-
of the approach in transferable learning features. Similarly,     GRU) network to recognize diverse human actions. This
CSI-based Parallel convolutional networks-based location-         approach achieves recognition accuracy of 97.4% and 93.3%
independent HAR system (CSI-PCNH) is proposed in [113]            across two distinct environments. Similarly, deep gated
which uses 3DCNN with channel attention mechanism                 recurrent unit (DGRU) model is introduced for non-intrusive
(CAM) and 2DCNN along with LSTM to recognize six dif-             HAR in [123] which achieve 95% to 99% accuracy for
ferent activities across various indoor locations and achieve     various daily human activities. Similarly, a novel dual-stream
an accuracy of 91.7%. Eight different location-independent        convolution augmented human activity transformer (THAT)
human activities are recognized in [109] using CSI data           is used in [150] to effectively captures spatial and temporal
and Raspberry Pi 4 with an LSTM DL model, achieving               features for various human activities and outperform existing
an overall accuracy of 97%. The authors in [170] proposed         state-of-the-art models in both effectiveness and efficiency.
a new approach called activity-related feature extraction,
enhancement, and matching network (AFEE-MatNet) which             B. MOVEMENT TRACKING
combines activity-related feature extraction and enhancement      Movement tracking is the process of monitoring and record-
(AFEE) with a matching network (MatNet). AFEE focuses             ing the paths that objects or individuals follow over a
on improving CSI quality by eliminating non-activity-related      period of time. This technology has diverse applications,
features while preserving behavior-related information and        such as sports analytic tracking, healthcare monitoring,
reducing feature signal size for faster training. MatNet learn    and security surveillance. Movement tracking may includes
transferable features that can be applied across different        crowd monitoring and motion sensing, localization, and gait
environments and effectively handle domain shift challenges.      recognition.
Furthermore, the approach also incorporate a prediction
checking and correction mechanism to rectify classification       1) CROWD MONITORING AND MOTION SENSING
errors that arise from the expected human behavior transi-        Crowd analysis is a prominent research area and is applicable
tions. Experimental results demonstrate that AFEE-MatNet          in urban planning, crowd management, surveillance, health-
outperform the existing HAR methods in terms of accuracy          care, and prevention of accidents and casualties. Vision-based
and training time. Similarly, the authors in [171] propose        methods for crowd analysis suffer from blind spots, high
matching network with enhanced channel state information          deployment costs, computational complexity, poor lighting
(MatNet-eCSI) which uses one-shot learning approach for           issues, and privacy concerns. In contrast, WiFi-based crowd
HAR that is operable and can identify various activities in       monitoring offers low-cost, extensive coverage without blind
different environments. It combines the correlation feature       spots, low computation, and preserves public privacy. This
matrix (CFM) and MatNet architecture comprising CNN               section provides a thorough literature review on WiFi-
with ReLU activation and Max pooling. The CFM is                  based crowd counting and motion sensing. A novel idea is
obtained by extracting activity-related information using         presented in [176], which accurately calculates the time-up
a linear recursive operation and subtracting it from the          and go (TUG) time for a subject rising from the rest. The
received signal using an exponentially weighted moving            precise determination of TUG time depends on both the
average (EWMA) approach to reduces the dimensions of              aligned movements of the subject and the continuous analysis
the original CSI matrix. MatNet utilizes the CFM and              of the reflected RF signals from the individual. TUG time is
employs the CNN along with the Bidirectional LSTM                 a crucial parameter widely used in the healthcare domain. It
model to produce the final output. Experimental results           helps healthcare professionals to diagnose disease and find
demonstrate the exceptional performance of MatNet-eCSI            its severity in an individual. The authors in [177] present
which surpasses the existing sensing methods with an aver-        an in-depth review of AI-based crowd-counting methods in
age accuracy of 0.868 for one-shot learning. Additionally,        healthcare, biotechnology, and in IoT. By using RNNs with
it offers the advantage of reduced training complexity            spatial-temporal matrices and grid partitioning, the paper [96]
making it highly effective solution for HAR. Similarly,           addresses the scalability of WiFi crowd counting while
the authors in [127] propose DeepSeg which employs a              lowering error rates in campus tests. The study in [115]
CNN framework that transforms activity segmentation tasks         aims to enhance real-time monitoring using bi-convolutional
into classification task, showing a significant performance       LSTM, attention-based autoencoders, and semi-synthetic
improvement. The authors in [151] use vision transformers         datasets for improved WiFi-based crowd analysis.
such as vanilla ViT, SimpleViT, DeepViT, SwinTransformer,            The work in [157] demonstrates the simultaneous tasks
and CaiT for CSI-based HAR on UT-HAR and NTU-Fi                   of crowd counting and localization estimation through ML
HAR datasets. Similarly, cross-domain action recognition          and WiFi CSI without necessitating user-device interaction.
using WiFi (CDFi) is introduced in [152] that utilizes            In three different span of time, the experimental results
transformers for activity recognition with minimal CSI            achieved a counting accuracy of up to 94% and local-
samples and achieve enhanced performance compared to              ization accuracy of 95% for k-fold cross-validation. This

3608                                                                                                                 VOLUME 5, 2024
work is further explored in [158] and proposed Wi-CaL              with over 99% accuracy within medium crowds and 100%
which addresses the feasibility of a simultaneous crowd            accuracy within small crowds. This level of precision
estimation system capable of predicting crowd numbers and          satisfies the requirements of most crowd-aware applications,
locations using WiFi IoT CSI technology and ML techniques.         accommodating varying crowd sizes within WiFi-covered
Instead of a conventional WiFi system, the author employed         areas. The paper [179] introduces FreeCount, a device-
Espressif system platform 32 (ESP32) nodes and their CSI           free crowd-counting method using WiFi routers. A novel
toolkit for medium-scale crowd counting and localization           OpenWrt firmware is used to capture router CSI data and
to establish a novel CSI platform. The experimental results        enable accurate estimation of occupants using two routers.
show that the Wi-CaL achieved promising results. Using             Wavelet denoising, diverse feature calculation, and info-
ML evaluation, the proposed method achieves 0.35 median            theory selection enhance counting while transfer kernel
absolute error (MAE) and 91.4% accuracy for 5 individuals          learning ensures temporal robustness. FreeCount achieves
in a small room and 0.41 MAE and 98.1% accuracy                    96% accuracy with a promising practical implementation.
for 10 individuals in a medium-sized room. Compared to             The paper [116] employs WiFi sensing and LSTM models to
the percentage of non-zero elements metric (PEM), Wi-              predict event crowd counting. The study involves monitoring
CaL outperformed with 0.41 MAE and 81.8% while PEM                 an event in Brussels using privacy-preserving WiFi sensors
scored 0.62 MAE and 66.5% accuracy in single-person                to gather crowd counts. These counts are transformed into
scenarios. The authors in [117] introduced CROSSCOUNT,             time series data which is then used for forecasting. The
a precise human counting system, that uses recurrent neural        research evaluates five LSTM models for crowd forecasting
networks while addressing challenges like weak signals, data       and compares their performance to a random walk model.
collection complexity, and the absence of CSI data. The            The convolutional LSTM model stands out as the most
system processes WiFi link intervals, surpassing received          effective and concludes the effectiveness of this system for
signal strength (RSS)-based methods. Utilizing LSTM to             accurate crowd monitoring.
classify blockage patterns, CROSSCOUNT outperforms RF-                IMep is proposed in [180], a system that operates without
based systems in counting accuracy. Across diverse test            devices and utilizes WiFi signals to count the steps of
setups, it achieves 59% precise human count accuracy,              multiple people. By utilizing CSI data, the authors developed
improving to 100% within a two-person difference case.             the multiplayer amplitude decomposition algorithm (MADA)
Similarly, the authors in [178] aim to count people within         using block term decomposition (BTD). They also con-
buildings using external WiFi transceivers, relying solely         structed the multiplayer stepping amplitude relation model
on WiFi RSSI measurements. It observes the inter-event             (MSARM). In contrast to traditional single-step measurement
times that are related to signal dip events and remain             methods, the study proposed a new moving energy method
stable even behind walls. A method is introduced to derive         (MEM) technique to enhance step counting accuracy, leading
people count from these inter-event times, treating wireless       to heightened precision in IMep’s results. Experimental
power measurements as a blend of renewal-type processes.           results demonstrated IMep’s capacity to accurately count
By leveraging concepts of the renewal process from the             the steps of up to seven individuals simultaneously in real-
literature, the probability mass function of inter-event times     world scenarios. Remarkably, IMep achieved step counting
is calculated to predict crucial people count information. The     accuracy of 95.57%, 94.66%, and 89.94% in three different
results demonstrate the accurate estimation of people behind       environments while also displaying adaptability to envi-
walls without extensive prior calibrations. In [94], the authors   ronmental changes. The authors in [181] propose WiStep,
introduce WiCount, an innovative system, that utilizes DL          a WiFi-based step-counting method, leveraging multipath
techniques to address complex multi-human environmental            propagation. WiFi signals are modulated by the differential
sensing tasks using WiFi CSI (amplitude and phase).                movement speeds of limbs and torso during walking and
WiCount employs a DNN model based on back-propagation              introduce distinct frequency components into received CSI.
(BP) which comprises an input layer, two hidden layers, and        The approach employs time-frequency analysis to segment
a softmax layer. WiCount is capable of accurately counting         walking patterns, selecting sensitive subcarriers based on
up to five individuals. The system incorporates both offline       amplitude variance, and applying wavelet decomposition for
training and online testing phases. Initial findings indicate      faster processing. Step counting uses short-time energy of
that WiCount achieves an impressive average recognition            coefficients with combined results from chosen subcarriers
accuracy of 82.3% for scenarios involving up to five people        for accuracy. WiStep accommodates in-place walking and
and outperforms traditional methods like SVM that operate          exhibits resilience across diverse scenarios, achieving step
on conventional features.                                          counting accuracies of around 90% in experiments using
   The authors in [159] introduce a device-free crowd-             commodity WiFi devices. The authors in [182] introduce
counting technique utilizing WiFi signals. By analyzing            Widar, a unique tracking system that utilizes WiFi signals
the phase and energy of subcarriers in real-time CSI,              for accurately estimating movement speed, direction, and
a DNN model is established to correlate these features             locations of individuals at a precision of a few decimeters.
with crowd density to enable accurate crowd counting.              Unlike conventional statistical learning methods, Widar
The method achieves a mean counting error of 0.11-0.14             establishes a geometric theoretical model to quantitatively

VOLUME 5, 2024                                                                                                              3609
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




TABLE 4. Whole body movement tracking.




   [157], [158]


   [117]


   [94]

   [159]



   [179]


   [183]


   [184]


   [99]


   [118]




understand the connections between the dynamics of CSI             peak-finding algorithm for counting consecutive actions. Two
and the person’s motion characteristics. The results show a        actions, walking and squats, are identified and distinguished.
remarkable performance, achieving accuracy at the decimeter        It integrates DWT-based waveform feature extraction and
level, with median location errors of approximately 24 cm          applies DTW and KNN for action recognition. Experimental
(with initial positions) and 36 cm (without initial positions)     results demonstrate that Wi-CR achieves 95% accuracy in
along with an average relative velocity error of 11%.              action counting and 90% in action recognition. The authors
   The authors in [185] introduce WiTraj, an innovative            in [186] developed a cost-effective and device-free approach
device-less WiFi-based system for accurate indoor motion           that intelligently monitors human dynamics by estimating
tracking. It enhances Doppler-frequency-shift (DFS) esti-          the number of participants, human density, and walking
mation by employing multiple angles to capture trajectory          speed in a particular direction. The proposed technique
accurately, distinguish between walking and stationary             employs the statistical distribution of CSI measurements
actions, and improve tracking accuracy compared to existing        to estimate the number of participants and density. At the
methods. Experimental results show a median tracking               same time, walking speed and direction are determined using
error of less than 2.5% for room-sized trajectories. The           a frequency-based mechanism. The experimental results
study in [183] introduces DeMan, an innovative method for          demonstrate that the proposed system achieves over 90%
non-invasively detecting stationary and moving individuals         accuracy in fine-grained human dynamics tracking – includ-
using standard WiFi devices. DeMan employs amplitude               ing participant count, density, walking speed, and direction
and phase information from CSI for motion detection and            across different indoor environments. Table 4 presents an
utilizes subtle chest movements due to human respiration to        overview of the existing works on tracking activities as a
identify stationary presence. DeMan achieves a remarkable          function of data sources, antenna systems, learning models,
detection rate of around 95% for both stationary and moving        and key performance indicators (KPIs).
individuals with a 96% accuracy in identifying human-
free scenarios and outperforms the existing benchmarks             2) INDOOR LOCALIZATION
by approximately 30%. Similarly, the authors in [184]              The performance of global positioning system (GPS) is not
introduce Wi-CR which is a CSI-based technique for                 satisfactory in the indoor environment and WiFi fingerprint-
continuous action counting and recognition without requiring       ing can be utilized due to the widespread availability of
specialized hardware. Wi-CR improves action detection              WLAN in the indoor setup. However, the precision of indoor
accuracy by identifying action start and end points, utilizing a   positioning is hampered by issues of uncertain and unstable

3610                                                                                                                 VOLUME 5, 2024
fingerprints for the WiFi signals. To this end, the authors        with clustering scores. In the online phase, user locations are
in [132] introduces FSTNet which is a DL framework to              estimated via classifiers using dynamic signal strength data.
enhance indoor positioning accuracy by understanding the           The system achieves high accuracy on the three benchmark
spatial-temporal relationship in the fingerprint data. The         datasets, i.e., 94%-99% for JUIndoorLoc, 96%-99%, and
framework introduces the concept of path fingerprints to           95%-98% for the second and third datasets, respectively.
address uncertainty and instability in the fingerprint. It            ViFi is introduced in [190] which is an indoor positioning
employs a CNN to effectively capture local attributes within       system that merges the multi-wall multi-floor (MWMF)
path fingerprints and a fingerprint attention mechanism to         model for virtual reference points with a deterministic
efficiently capture spatial characteristics for stable position-   weighted k-Nearest Neighbors (WkNN) algorithm. ViFi
ing data. The on-site experiments on FSTNet demonstrates its       outperforms prior virtual fingerprinting methods by main-
ability to effectively capture temporal and spatial correlations   taining high accuracy while reducing measurement time.
within RSS measurements and achieves 44% enhancement in            Guidelines for parameter selection are provided and future
mean positioning error where 99.2% of errors being confined        research potential are discussed. The study in [98] presents a
within the range of 2m. The indoor localization mainly relies      robust approach for tracking and locating moving objects in
on RSS and time of arrival (ToA) for fingerprinting. The           indoor the environments by using different classifier along
study in [187] compared the three localization methods,            with Kalman filtering and smoothing. The Feko channel-
i.e., multilateration, KNN, and minimum mean square error          propagation emulator is used to simulate the RSSI maps in
(MMSE) using RSS in the indoor WiFi systems. The aim is            the indoor setting divided into multiple zones to enable multi-
to assess their accuracy through simulations by correlating        classification. A gradient-boosting decision-tree classifier
the estimated positions with actual data, and revealing the        is trained on RSSIs while Kalman filter enables online
strengths and limitations of each approach via the network         tracking and Kalman smoother facilitates offline localization.
simulator (NS-2). The authors in [133] introduce a WiFi-           Results demonstrate 73.1% highest localization accuracy and
based indoor localization system that leverages CNN for            the smallest average Euclidean-distance error of 1.33 m.
classification tasks. Three distinct approaches are explored       Similarly, FedPos is presented in [134] which utilizes a
such a custom architecture called WiFiNet, tailored for            federated transfer learning for WiFi CSI-based indoor local-
the task, and the use of popular pre-trained networks with         ization. The overall improvement of 5.22% in the average
transfer learning and feature extraction. Results shows that       accuracy is observed while the training time is reduced by
effectiveness of WiFiNet in indoor localization for medium-        about 34.78% compared to traditional learning methods. The
sized environments (30 positions, 113 access points) and           authors in [149] evaluated the stacked autoencoder (SAE)
reduce the localization error by 33% with less processing          for for three RSSI based indoor localization datasets and
time compared to existing methods such as SVM.                     achieved an accuracy of 100% for building, 99.66% for
   The authors in [188] assess different learning models for       the floor, and 83.47% for zone location. The RS-DeepNet
indoor positioning within an office setting by utilizing an        is proposed in [125] for indoor localization with MAE of
open source wireless infrastructure. The accuracy of esti-         4.81 m and 1.68m for two different indoor scenarios. A deep
mated two-dimensional (2D) positions is evaluated in terms         supervised autoencoder (SAE) based DeepPos is presented
of root-mean-square error (RMSE) and R-squared metrics.            in [148] which achieve 1.9m improvement in MAE compared
The methods include distance estimation via an RSSI-based          to DeepFi proposed in [191]. Similarly, a transformer-based
ML model, coupled with the Min-Max positioning algorithm,          indoor positioning system (TIPS) is presented in [153] that
independent RSSI-based models for individual coordinates,          utilizes self-attention on WiFi CSI and direction of arrival
and RSSI-based sequential prediction of the varying coordi-        (DoA) information to achieve distance error of up to 20cm,
nates. A comparative analysis is conducted and the results         outperforming state-of-the-art methods. Table 5 presents the
reveal the superior performance of the distance prediction         state-of-the-art on DL based indoor localization activities
model and Min-Max algorithm for fixed positions and sug-           with an emphasis on the experimental setups, type of learning
gest the need for more precise sub-0.5 m measurements in           models, and the used KPIs such as positioning error, MMSE,
2D coordinate prediction. In [97], the authors proposed two        localization accuracy, median error, and Euclidean distance
DL models, i.e., a convolutional mixture density recurrent         error.
neural network and a variational autoencoder-based semi-
supervised model for accurate user location estimation using       3) GAITS RECOGNITION
limited labeled WiFi data. Validation experiments on real-         Human gait recognition identifies individuals from a distance
world datasets confirm their superior performance compared         and has gained popularity with time. With increasing data
to existing methods. The work in [189] presents a two-phase        volume, the focus has shifted from traditional ML to
semi-supervised localization method applicable to indoor           advanced DL based gate recognition. In this regard, a
localization datasets. In the offline phase, the rank-based        brief review of DL techniques on gait identification using
iterative clustering (RBIC) algorithm is used to form clusters     CNNs, capsule networks, RNNs, autoencoders, deep belief
with minimal distant points. RBIC acts as a clustering             networks, and generative adversarial networks (GANs) is
ensemble generated based on ranked baseline algorithms             presented in [192]. AutoFi is proposed in [93], which utilizes

VOLUME 5, 2024                                                                                                                3611
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




TABLE 5. WiFi-based indoor localization.




   [132]
   [187]


   [133]

   [188]



   [97]



   [189]


   [98]


   [190]

   [134]


   [125]




low-quality CSI samples and employ MLP model for human           authors in [99] introduces Wihi, a new approach that
gait recognition. In [136], the CSI data is preprocessed         employs DWT for noise removal, extracting human walking
and then passed through the CNN model to detect walking          patterns via statistical features, and utilizing an RNN-LSTM
direction, achieving an accuracy of 92.9%, 95.1%, and 89%        model for accurate identification. Wihi’s prototype on WiFi
in three indoor environments and across different people.        devices shows superior performance over existing methods
The authors in [100] present Vi-WiFi-Gate which using            showcasing its potential for robust human identity identifi-
RNN along with an attention mechanism and provides               cation in noisy indoor environments. Human gait, a crucial
a gait recognition accuracy of 94.6% on over 1000 CSI            identifier, can now be captured from a distance using passive
samples. The authors in [193] introduce GAITWAY, an              sensors and applications in security and identification. While
innovative system that identifies an individual’s gait through   conventional research relies on cameras and computer vision
walls using wireless radios. GAITWAY passively tracks            for gait recognition, these methods struggle in low-light
gait speed with standard WiFi transceivers and eliminates        conditions. The article [118] presents GaitFi which is a multi-
the need for devices or restricted walkways. It detects          modal technique that combines WiFi signals and videos.
stable walking periods, extracts relevant speed features, and    GaitFi employs CSI from WiFi along with camera-recorded
identifies a person’s gait. Using a rich-scattering multipath    videos and employs a lightweight residual convolution
model, GAITWAY captures gait speed from over 10 m                network (LRCN) to enhance gait information. By integrating
behind the walls. Experiments with 5,000 gait instances          WiFi and visual features in a two-stream model while
and various subjects demonstrate its accuracy and achieve        training with triplet and classification loss, GaitFi achieves
a median speed error of 0.12 m/s, stride length error of         impressive real-world results with an accuracy of 94.2% in
3.36 cm, and strong recognition rates of up to 81.2%. This       identifying 12 subjects and outperforming the WiFi only or
establishes GAITWAY as both reliable and practical for use.      camera-based methods. The paper [194] presents WiFiU, an
The use of commercial WiFi devices for human identification      approach that utilizes commercial WiFi devices to capture
has gained attention in applications such as smart homes         intricate gait patterns for human recognition. By exploiting
and intrusion detection. However, the existing methods are       the unique gait signatures in WiFi’s CSI, the method
prone to indoor noise and hence limited accuracy. The            generates spectrograms akin to Doppler RADARs through

3612                                                                                                                VOLUME 5, 2024
signal processing. Auto-correlation on the torso reflection          The paper [102] investigates the performance of WiFi-
further refines the pattern characterization. Evaluated on a      based HPE for single-person scenarios. An experiment is
dataset of 2,800 gait instances from 50 individuals in a 50m2     conducted using a setup comprising a 3-antenna WiFi
room, WiFiU achieves recognition accuracy of 79.28% (top-         transceiver to collect WiFi data. Simultaneously, a synchro-
1), 89.52% (top-2), and 93.05% (top-3). WiWho is presented        nized camera records videos of individuals with annotated
in [195] which is a WiFi-based framework for device-              key points are used for reference and a WiFi single-
free person identification in small groups. Utilizing WiFi        person pose network (WiSPPN) is proposed which is a
CSI, WiWho captures unique gait patterns to distinguish           fully connected CNN, designed to estimate single-person
individuals. Analyzing step and walk data within CSI,             pose based on the collected CSI data and its corresponding
WiWho achieves accurate identification without personal           annotations. The results demonstrate that WiSPPN achieves
devices while requiring a short walk. Evaluated with 20           comparable accuracy to camera-based methods for single
volunteers across different locations, WiWho achieves 92%         HPE. Similarly, the authors in [77] introduce a novel
and 80% identification accuracy for 2 and 6-people groups,        approach using the teacher-student network model for 2D
respectively. The study underscores that a 2-3m walk is           human poses estimation in challenging scenarios involving
sufficient for successful identification to enable a person’s     walls and occlusion. The method utilizes synchronized visual
recognition in smart spaces using WiFi.                           data and signal reflections to address these difficulties. The
                                                                  teacher network [138] plays a vital role in the proposed
C. POSE ESTIMATION                                                approach with the employment of CNN with the ReLu acti-
HPE plays a vital role in human-computer interaction and          vation function. Notably, despite not being explicitly trained
can be applied to applications such as virtual reality and        for wall-related scenarios, the proposed model demonstrates
exercise monitoring in a smart environment. The traditional       impressive capabilities in estimating 2D human poses in
approaches rely on vision-based techniques which is not           such conditions. It achieves an acceptable average precision
applicable in NLoS scenarios. Therefore, RF-based methods         (AP) of 85.0%, which comparable with the teacher network
become an appealing alternative for pose estimation in            having AP of 93.3%. The work in [103] proposes WiSPE,
scenarios with no wearable sensors and LoS requirements.          a 2D static HPE system based on commercial of-the-shelf
Table 6 provides a comprehensive review of DL based               (COTS) WiFi and utilizes 2D AoA imaging, resembling
HPE shedding light on considered dimensions, experimental         a camera, to estimate human pose accurately. The system
setups, utilized learning models, and KPIs such as the            incorporates the environment background filter (Env-Filter)
percentage of correct key points (PCK@α) with distance            algorithm to mitigate static environmental factors in the
threshold α, AP, prediction accuracy, and average joint           images and employs a teacher-student network (RNN and
localization error. The PCK@5 in Table 6 measures the             openpose) to correlate 2D AoA images with human skeleton
proportion of key points where the distance between the           joints. The results showed an average prediction accuracy of
predicted key point and the true joint falls within 5% of         95.2% in PCK@50 for each skeleton joint, surpassing other
the subject’s size. In other words, it refers to the percentage   benchmarks and achieve a prediction accuracy of 73.1% in
of keypoints where the predicted location is within 5%            PCK@10.
of the subject’s size from the ground truth keypoints.               The evolving attentive spatial-frequency network
The authors in [138] introduced a real-time approach for          (EASFN) is introduced in [140], which combines static
estimating the 2D poses of multiple people in an image.           spatial and dynamic frequency information from dilated
The method employs part affinity fields (PAFs) to effectively     CSI sequences and utilize it for 2D HPE. The model
encode the limbs and orientations of humans, facilitating         includes an evolving attention module to focus on specific
precise key point association. Feature extraction is accom-       features and leads to a significant performance improvement
plished using the first ten layers of visual geometry group       of 16% in PCK @20 over the state-of-the-art method
(VGG-19) architecture which ensure favorable outcomes             and proved to be effective for accurate HPE. The [160]
compared to the prior research by efficiently detecting           study presents a multimodal HPE network (MHPEN) which
the joints and associating connections among various body         is a unified network for 2D HPE, combining a teacher
parts. Similarly, the authors in [135] introduce a novel          network (Alphapose) using visual data and a student network
approach for generating human pose images using wireless          (PerUnet) utilizing WiFi CSI data. The WiFi-based HPE
signals rather than optical cameras. The proposed framework       is focused by PerUnet which leverages the power of a
combines data from multiple wireless devices capturing            multi-head attention mechanism and Unet-like architecture
WiFi signals with an initial optical image from a camera.         is used to effectively combine fine-grained pose features and
The wireless and vision data are then preprocessed before         contextual information from WiFi CSI. This integration leads
being fed into a CNN plus Residual network for generating         to highly accurate HPE results. Additionally, the authors
human pose images. Experimental results indicate that this        propose the attention-based denoising (ABD) method which
approach outperforms existing WiFi-based methods in terms         effectively overcomes the limitations of traditional filters and
of pose estimation accuracy and produces higher-quality           facilitates the extraction of pose features from the CSI data.
visuals.                                                          Extensive experiments are conducted, demonstrating that

VOLUME 5, 2024                                                                                                                3613
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




TABLE 6. Pose estimation literature.




PerUnet achieves competitive performance in WiFi-based       method more promising over other HPE approaches.
HPE evaluated on the Wi-Pose dataset. A novel architecture   Experimental results on the Wi-Pose dataset demonstrate
named CSI-former is introduced in [139] which integrates     that CSI-former significantly enhances HPE performance
multi-head attention into a WiFi-based pose estimation       with a PCK@5 accuracy of 0.5505 and surpasses the
network (PEN). The attention-based performer feature         existing ResNet with PCK@5 accuracy of 0.5231. Similarly,
extraction (PAFE) and CNN-based encoder/decoder focus        a domain adaption algorithm called AdaPose is proposed
on information-rich CSI inputs which make the proposed       in [196] for weakly supervised WiFi-based HPE which


3614                                                                                                       VOLUME 5, 2024
emphasizes consistent human poses to address environmental        a static position. GoPose is a 3D HPE system that utilizes
dynamics. in this regard, the CNN model and mapping               WiFi signals from household devices [120]. By leveraging
consistency loss are utilized. The article [141] estimates head   the 2D AoA spectrum of WiFi signals reflected off the human
pose using CNN model WiFi CSI information including               body and employing DL techniques such as CNN and LSTM
phase, amplitude, and frequency domain information such           models, the system achieves accurate pose estimation and
as phase, amplitude, and frequency domain information. The        tracking. Notably, it enables environment-independent pose
authors in [101] proposed an approach for reconstructing          estimation and exhibits an impressive accuracy of 4.7 cm
human skeletal motion through WiFi micro-Doppler                  across diverse scenarios including NLoS conditions and
signatures which enable practical human activity tracking         tracking unseen activities. This innovative technology holds
with a 17-key point skeleton model. The method employs a          significant potential for various applications requiring precise
CNN-RNN architecture to effectively learn temporal-spatial        HPE. Wi-Mose utilizes the fusion of amplitude and phase of
dependencies from clean micro-Doppler signatures. A pose          CSI data to create CSI images and enable the reconstruction
optimization mechanism is applied to estimate the initial         of 3D poses of moving individuals while providing both
skeleton state and control error growth. Extensive testing        pose and position information [104]. The system employs a
in diverse environments with multiple subjects is performed       residual network to extract pose-related features from these
using a single-receiver RADAR system. Furthermore, it is          CSI images and a key-point regression network then converts
observed that the mean absolute error of 29.4mm is achieved       these features into key-point coordinates. During training,
for all key point positions. Similarly, MetaFi is presented for   synchronized visual data is used to supervise the WiFi
HPE in metaverse avatars simulation [197] which employs           data. The experimental results demonstrate Wi-Mose’s effec-
a customized DNN that is capable of achieving 95.23%              tiveness in accurately localizing key points and achieving
accuracy at PCK@50 which is further improved to 97.30%            mean-per-joint position error (P-MPJPE) values of 29.7 mm
in MetaFi++ [154].                                                and 37.8 mm in LoS and NLoS scenarios, respectively.
   A TGUL approach for 3D HPE is presented in [31]                The authors in [147] introduce “Winect”, which estimates
which employs a DNN with 9-residual block encoder for             3D human poses from environment-independent free-form
spatio-temporal convolutional features and a 3-residual block     activities through the ResNet-18 model. The authors in [142]
decoder for spatial de-convolution. Based on comparative          developed a correlated knowledge distillation (CKD) system
analysis, predictive learning outperforms contrastive learning    using WiFi and USRP to detect human postures and
due to its ability to capture and utilize relevant information,   movements while preserving privacy. CKD combined RF sig-
resulting in consistent performance improvements over             nals and camera images for a hybrid framework and used two
supervised baselines during fine-tuning. The authors in [161]     parallel approaches (image and radio signal classification) for
introduce fast RFPose, a mmWave RADAR-based 3D HPE                knowledge distillation. By leveraging correlated multimodal
model which utilizes the human localization network (HLN)         information between teacher and student networks, the
and the PEN network. HLN is responsible for predicting            CKD model achieved accurate inference without relying
human positions in the RF heatmap and cropping the relevant       on images or video data. Experiments on the SDR-based
regions while PEN estimates the 3D human poses based on           testbed confirmed the feasibility and potential impact of this
these cropped areas. Extensive quantitative and qualitative       framework including the leverage of pre-trained networks
analysis confirm the efficacy of Fast RFPose, demonstrating       with limited data. Similarly, the authors in [143] introduce
its ability to achieve accurate 3D HPE with remarkable            Winect, an innovative 3D human pose tracking system that
processing speed. Furthermore, the trained Fast RFPose            utilizes commodity WiFi devices to monitor 3D free-form
model is successfully deployed on a laptop with a central         activities. The method estimates a 3D skeleton pose with
processing unit (CPU) underscoring its practical applicability    essential body joints to effectively track varied movements
in real-world settings. WiPose is an innovative 3D human          by integrating signal separation techniques and modeling
pose construction framework that utilizes commercial WiFi         joint motions. The system identifies moving limbs through
devices to reconstruct accurate human skeletons in a chal-        the 2D AoA from human body reflections, untangles these
lenging real-world scenario [119]. The DL model (CNN              signals for each limb, and constructs a comprehensive 3D
with LSTM) encodes prior knowledge of the human skeleton          skeleton by capturing the inherent correlation between limb
to ensure estimated joints adhere to the body’s skeletal          motions and joint movements. The proposed system achieves
structure. Additionally, WiPose achieves cross-environment        an overall localization error of 4.6 cm, with joint localization
generalization by using a 3D velocity profile as input and        errors ranging from 4.1 cm to 5.1 cm, showcasing Winect’s
effectively distinguishing posture-related features from static   ability to achieve cm-level precision in tracking diverse
objects in the environment. Experimental results from real-       activities even in challenging scenarios, including non-line-
world WiFi sensing testbed shows that WiPose achieves an          of-sight situations. Similarly, [144], [145] propose Wi-Mesh
average joint localization error of 2.83 cm and outperforms       which utilizes WiFi signals for creating a 3D human mesh.
the state-of-the-art posture construction model designed for      By capitalizing on the advancements in WiFi technology,
dedicated RADAR sensors by 35% accuracy. However, this            the proposed system visualizes human body shapes and
method can only estimate the pose of a single human in            movements to construct a detailed 3D mesh. This is achieved

VOLUME 5, 2024                                                                                                                3615
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




by estimating the 2D AoA of WiFi signal reflections and          result, these changes can lead to misunderstandings about
essentially enables WiFi devices to perceive their surround-     human behavior and affect the overall performance of the
ings. The process involves isolating human body images           sensing system [198]. To tackle this challenge, there is
from the WiFi signal reflections and utilizing DL models         a need to create adaptive algorithms and DL techniques
to transform these images into a 3D mesh representation.         that can quickly adapt to these environmental shifts to
Through rigorous experimentation across various indoor           ensure the reliability and robustness in real world dynamic
settings, Wi-Mesh demonstrates encouraging performance           situations.
with an average error of 2.58 cm for vertices locations
and 2.24 cm in joint positioning. WiLink is another WiFi-
                                                                 B. MULTI-USER SENSING IN MULTI-MODAL SCENARIO
based 3D indoor HPE system that intelligently utilizes
                                                                 Most of the literature on WiFi sensing considers single-
existing WiFi links for accurate HPE [146]. By classifying
                                                                 user scenarios. However, detecting and distinguishing the
links as noise-dominated, most-effective, and redundant, the
                                                                 activities of multiple users simultaneously using commodity
dynamic link selection (DLS) mechanism is introduced to
                                                                 WiFi presents a significant challenge. This is particularly
adaptively choose the most-effective links by maximizing
                                                                 evident when trying to differentiate users based solely on
importance and minimizing redundancy. The selected CSI
                                                                 the WiFi signal data since standard WiFi systems do not
samples are fed into a DNN with residual blocks and fully
                                                                 inherently provide user identification features. This challenge
connected layers for precise HPE. The P-MPJPE results
                                                                 is further complicated by issues like signal interference and
(32.31 mm for training subjects and 40.30 mm for untrained
                                                                 the blending of signals when several users are active at
subjects) demonstrate WiLink’s cross-subject generalization.
                                                                 once. Additionally, it is crucial to prioritize data privacy as
Similarly, the authors in [137] introduce a novel approach
                                                                 handling data collected from the activities of multiple users
that utilizes WiFi signals and DL to estimate dense human
                                                                 requires careful consideration to avoid violating their privacy
pose correspondence. The DNN converts WiFi CSI into
                                                                 rights. To advance this technology, sophisticated algorithms
UV coordinates and is capable of achieving accurate pose
                                                                 and signal processing techniques must be developed to
estimations for 24 human regions. The proposed method
                                                                 accurately identify individual user activities while also
incorporates a modality translation network and WiFi-
                                                                 preserving their privacy. This challenge remains complex
DEnsePose RCNN to transform CSI into UV maps. Transfer
                                                                 and ongoing in the field of multi-user activity sensing using
Learning with a teacher network is used to further enhance
                                                                 standard WiFi technology [199], [200]. On the other hand,
the model performance. The results demonstrate that the
                                                                 the existence and availability of multiple technologies with
WiFi-based model is more effective in estimating multiple
                                                                 different standards, principles, and operating frequencies is
subjects than the image-based methods. However, limitations
                                                                 more ambitious in the era of future IoT. Most of the literature
exist, such as potential biases with rare body poses in the
                                                                 on sensing focuses on a single RF mode while the WiFi
training data and challenges in handling multiple subjects
                                                                 signals can be jointly utilized with other RF modes such
in one capture. Nonetheless, the approach shows promising
                                                                 as FMCW radar operating in higher frequency bands such
applications in HPE using readily available WiFi signals.
                                                                 as mm wave and terahertz, or even the sub-GHz LoRa
IV. CHALLENGES AND FUTURE DIRECTION                              signals [67]. It is an exciting future research direction to
WiFi-based human sensing has received comprehensive              utilize and train DL on multi-stream data to enable multi-user
attention in the existing literature and has demonstrated        sensing in multi-modal setups.
impressive accomplishments. On the other hand, DL is an
effective tool that enhances the performance of WiFi sensing     C. EFFICIENT DEEP LEARNING MODEL OR EDGE
but still there exist enduring challenges that need to be        INTELLIGENCE FOR WIFI-BASED SENSING
addressed to fully exploit DL in future research. In this        Despite its strong sides, DL algorithms used in WiFi
section, we present the challenges related to DL-based WiFi      sensing face significant challenges. Firstly, the computational
sensing and the potential strategic foresight.                   demands of complex DL models can hinder their real-time
                                                                 implementation on resource-constrained embedded devices,
A. PHYSICAL ENVIRONMENT VARIABILITY                              limiting their practicality in diverse scenarios. Secondly,
In WiFi-based human sensing, there is a frequently under-        gathering the extensive labeled datasets needed for training
estimated but significant challenge related to environmental     can be arduous and expensive, especially in situations where
changes such as rearranging furniture, adding obstructions,      data collection is difficult. Additionally, DL algorithms
human presence, closing doors, etc. Despite their seemingly      often require substantial memory and storage resources,
common nature, these environmental alterations disrupt the       posing issues for devices with limited memory capacity.
consistency between the received data, like human activities,    Furthermore, these models may lack transparency and
gestures, and locations, and the established reference data is   interpretability, which is crucial in handling sensitive WiFi
used for sensing. For example, moving furniture or closing a     data. Addressing these limitations is vital for the widespread
door can unexpectedly change the behavior of WiFi signals        adoption of DL-based WiFi sensing systems, making the
and may cause unexpected reflections and distortion. As a        exploration of memory-efficient techniques and optimization

3616                                                                                                                VOLUME 5, 2024
methods a compelling avenue for research and progress in          Considering the joint use of DL and RIS in the smart indoor
HAR [201].                                                        environment, we highlight the potential future research
                                                                  direction stated as follows.
D. HYBRID RF-VLC-BASED SENSING
                                                                  1) DATASET GENERATION AND AVAILABILITY FOR
Despite the advantage, there exist some challenges in
                                                                  RIS-ENABLED WIFI SENSING
RF-based systems such as spectrum congestion and
interference issues. Therefore, high-frequency bands such as      In the context of WiFi-based sensing, creating standardized
mmWaves are used for WiFi-based indoor localization and           open datasets specifically designed for WiFi-based human
showed improved localization performance through spatial          sensing can make it easier and more cost-effective for
beam signal-to-noise ratios for RSSI fingerprinting [202].        researchers and developers to obtain labeled training data.
Considering the energy consumption of RF-based systems,           Based on experimental data the performance of RIS-enabled
visible light offers several advantages such as spectrum avail-   WiFi sensing is an interesting future research direction.
ability, enhanced security, cost-effective implementation, and    Keeping in view the importance of reproducible research,
high energy efficiency [203]. Visible light communication         the dataset should be openly available so that new concepts
(VLC) and localization have been extensively explored             and models in the area of ML are tested and compared with
in literature [204], [205], [206]. However, despite these         the existing ones.
advantages, the visible light-based system requires LoS and       2) AUTOMATED DATA LABELING IN RIS-ENABLED WIFI
results in limited performance in NLoS scenario [207].            SENSING
Therefore, the heterogeneous deployment of WiFi technology        Exploring automatic labeling methods using non-RF tech-
and visible light can be a promising solution in the              nologies, such as video or infrared sensors, offers a novel
indoor environment as both are capable of improving the           way to improve the efficiency and accuracy of data collection
system performance by complementing each other [208].             which is crucial in overcoming a key obstacle in developing
Utilizing DL in such heterogeneous deployment for HAR,            robust WiFi sensing systems. Additionally, the concept of
fall detection, HPE, motion sensing etc., can be one of the       sensing with information fusion, which involves combining
promising future research directions.                             data from various sensors and sources, shows great potential
                                                                  for enhancing the reliability and precision of WiFi-based
E. RECONFIGURABILITY AND MULTIPATH EFFECT FOR                     HAR. This approach can help address some of the challenges
SMART INDOOR ENVIRONMENT
                                                                  related to noisy signal data. While considering sensing with
The multipath effect is a significant factor in WiFi-based
                                                                  information fusion, using RIS as a sensing element is one of
human sensing that deserves close attention from researchers
                                                                  the promising future aspects of WiFi-based sensing. The DL
in the field. Multipaths occur when WiFi signals take
                                                                  model utilized in RIS-enabled WiFi sensing usually requires
multiple paths to reach a receiver influenced by reflections,
                                                                  huge labeled data for training to learn and classify different
diffraction, and scattering in indoor environments. In human
                                                                  features. However, automated data along with an efficient
sensing applications, this phenomenon presents notable
                                                                  DL model needs to be designed to learn the unlabelled data
challenges. As people move in a space, they can affect
                                                                  to avoid the significant overhead in the data acquisition.
WiFi signal propagation by acting as signal reflectors. This
can lead to unpredictable variations in signal strength and       3) MULTIPLE RIS FOR MULTI-MODEL SENSING IN
phase, potentially causing inaccuracies in detecting human        INDOOR WIFI SENSING
presence and activities. Additionally, multipath interference     Utilizing RIS in the indoor system can improve the sensing
can make it difficult to distinguish between multiple indi-       capability of the RF system by utilizing improved CSI
viduals nearby, affecting the system’s ability to accurately      through the LoS link. As demonstrated in [212] RIS can
track and identify users. To address the multipath effect         play a vital role and its presence leads to achieving high
in WiFi-based human sensing, innovative signal process-           accuracy in the recognition of human postures while in [213]
ing techniques, and advanced algorithms mitigate signal           a single RIS is proposed to enable a favorable propagation
interference and improve system reliability. To enable a          environment for RADAR sensing in the indoor environment.
smart indoor environment, the reconfigurable intelligent          However, considering multiple path signals from multiple
surface (RIS) is considered a promising solution to improve       RIS in a multi-modal scenario can be interesting to explore
the quality of the received signal by avoiding blockages,         in the future. Similarly, instead of single-user multi-user
capacity, coverage, and energy efficiency [209]. However,         sensing capabilities while considering the impact of passive
RIS is mostly analyzed in the literature to improve the           and active RIS needs to be analyzed. The location of RIS
performance of wireless networks while there exist some           plays a vital role, therefore, optimal deployment of RIS can
works that consider the deployment of RIS for integrated          be explored for performance enhancement.
sensing and communication through RF networks [210].
However, as mentioned in [211], the quality of received           F. HITL BASED LEARNING MODEL FOR SENSING
CSI is affected by RIS and can be considered to extend            A range of DL models are used for WiFi based human
the capability of WiFi-based sensing in the indoor setup.         activity prediction. However, achieving optimal accuracy

VOLUME 5, 2024                                                                                                              3617
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




remains a primary goal for these models. One promising            REFERENCES
future research direction for WiFi-based human sensing is          [1] F. Adib, Z. E. Kabelac, and D. Katabi, “Object tracking via radio
to improve the learning capabilities of DL models through              reflections,” U.S. Patent 15 120 864, Mar. 16, 2017.
Human-in-the-Loop” (HITL) methodologies. By integrating            [2] D. Katabi, “1.3 working at the intersection of machine learning,
                                                                       signal processing, sensors, and circuits,” in Proc. IEEE Int. Solid-
human feedback and interaction directly into the DL models             State Circuits Conf. (ISSCC), San Francisco, CA, USA, 2021,
enable them to adjust to various environments and user                 pp. 26–29.
behaviors dynamically [214]. This approach capitalizes on          [3] Y. He, Y. Chen, Y. Hu, and B. Zeng, “Wi-Fi vision: Sensing,
                                                                       recognition, and detection with commodity MIMO-OFDM Wi-Fi,”
real-time human inputs to correct and refine sensing outputs,          IEEE Internet Things J., vol. 7, no. 9, pp. 8296–8317, Sep. 2020.
thereby boosting system performance in complex real-world          [4] L. Lubna et al., “Radio frequency sensing and its innovative
scenarios [215], [216]. For instance, users might validate             applications in diverse sectors: A comprehensive study,” Front.
or correct identified activities using a mobile application,           Commun. Netw., vol. 3, Sep. 2022, Art. no. 1010228.
                                                                   [5] M. S. Mopas and E. Huybregts, “Training by feel: Wearable fitness-
allowing the system to learn from these interactions and               trackers, endurance athletes, and the sensing of data,” The Senses
update its models accordingly. This iterative process not              Soc., vol. 15, no. 1, pp. 25–40, 2020.
only enhances model accuracy but also customizes the               [6] S. C. Mukhopadhyay, “Wearable sensors for human activity moni-
                                                                       toring: A review,” IEEE Sensors J., vol. 15, no. 3, pp. 1321–1330,
sensing experience to better fit individual user patterns              Mar. 2015.
and preferences. Moreover, the concept of HITL can be              [7] K. C. Sahoo and U. C. Pati, “IoT based intrusion detection system
applied to various challenges in WiFi-based human sensing              using PIR sensor,” in Proc. IEEE 2nd Int. Conf. Recent Trends
such as variability encountered in physical environments               Electron., Inf. Commun. Technol. (RTEICT), 2017, pp. 1641–1645.
                                                                   [8] Q. Lin et al., “E-Jacket: Posture detection with loose-fitting garment
by empowering systems to adapt to changing conditions                  using a novel strain sensor,” in Proc. 19th ACM/IEEE Int. Conf.
based on user feedback. In scenarios involving multiple                Inf. Process. Sensor Netw. (IPSN), Sydney, NSW, Australia, 2020,
users and modes, HITL can play a crucial role in managing              pp. 49–60.
                                                                   [9] C. Zieger, A. Brutti, and P. Svaizer, “Acoustic based surveillance
and distinguishing signals from different users, enhancing             system for intrusion detection,” in Proc. IEEE 6th Int. Conf. Adv.
the system’s capability to handle complex environments.                Video Signal Based Surveillance, Genova, Italy, 2009, pp. 314–319.
Additionally, the integration of HITL with DL or edge             [10] Z. Shi, X. Chang, C. Yang, Z. Wu, and J. Wu, “An acoustic-based
intelligence can optimize processing and reduce latency,               surveillance system for amateur drones detection and localization,”
                                                                       IEEE Trans. Veh. Technol., vol. 69, no. 3, pp. 2731–2739, Mar. 2020.
making real-time adjustments more feasible. HITL also             [11] G. M. Weiss, J. L. Timko, C. M. Gallagher, K. Yoneda, and
stands to improve reconfigurability and mitigate multipath             A. J. Schreiber, “Smartwatch-based activity recognition: A machine
effects in smart environments by leveraging user inputs to             learning approach,” in Proc. IEEE-EMBS Int. Conf. Biomed. Health
                                                                       Informat. (BHI), Las Vegas, NV, USA, 2016, pp. 426–429.
fine-tune system responses.
                                                                  [12] F. Shahmohammadi, A. Hosseini, C. E. King, and M. Sarrafzadeh,
                                                                       “Smartwatch based activity recognition using active learning,” in
                                                                       Proc. IEEE/ACM Int. Conf. Connect. Health, Appl., Syst. Eng.
V. CONCLUSION                                                          Technol. (CHASE), Philadelphia, PA, USA, 2017, pp. 321–329.
                                                                  [13] Q. Lei, J.-X. Du, H.-B. Zhang, S. Ye, and D.-S. Chen, “A survey
This study presents a comprehensive survey of recent                   of vision-based human action evaluation methods,” Sensors, vol. 19,
research on human activity sensing via WiFi, leveraging                no. 19, p. 4129, 2019.
DL algorithms. This study reveals the emerging trend of           [14] G. Li and D. Wen, “Wearable biochemical sensors for human health
                                                                       monitoring: Sensing materials and manufacturing technologies,” J.
integrating DL with RF sensing has led to substantial                  Mater. Chem. B, vol. 8, no. 16, pp. 3423–3436, 2020.
progress. DL is a valuable technique to enhance the precision     [15] A. Shastri et al., “A review of millimeter wave device-based
and range of device-free RF sensing. Researchers have                  localization and device-free sensing technologies and applications,”
effectively utilized DL to detect new phenomena that were              IEEE Commun. Surveys Tuts., vol. 24, no. 3, pp. 1708–1749, 3rd
                                                                       Quart., 2022.
previously not observed in the literature through traditional     [16] Y. LeCun, Y. Bengio, and G. Hinton, “Deep learning,” Nature,
approaches. This survey briefly highlights the fundamental             vol. 521, no. 7553, pp. 436–444, 2015.
physical layer parameters used in RF sensing including RSSI,      [17] I. Nirmal, A. Khamis, M. Hassan, W. Hu, and X. Zhu, “Deep
                                                                       learning for radio-based human sensing: Recent advances and
and CSI. Furthermore, the estimated parameters such as AoA             future directions,” IEEE Commun. Surveys Tuts., vol. 23, no. 2,
and DS as well as FMCW technology followed by signal                   pp. 995–1019, 2nd Quart., 2021.
processing techniques is explored. Furthermore, we provided       [18] J. Yang, H. Zou, L. Xie, and C. J. Spanos, Deep Learning
a detailed review on WiFi based human activity sensing                 and Unsupervised Domain Adaptation for Wi-Fi-Based Sensing.
                                                                       Singapore: World Sci., 2021, ch. 4, pp. 79–100.
such as motion detection, fall detection, crowd sensing,          [19] C. Shi, J. Liu, N. Borodinov, B. Leao, and Y. Chen, “Towards
multi-activity classification, step sensing, HPE, localization,        environment-independent behavior-based user authentication using
and gaits calculation assisted by DL techniques. Finally,              Wi-Fi,” in Proc. IEEE 17th Int. Conf. Mobile Ad Hoc Sensor Syst.
                                                                       (MASS), 2020, pp. 666–674.
the paper highlights the current limitations in WiFi-based        [20] S. Fang, T. Islam, S. Munir, and S. Nirjon, “EyeFi: Fast human
sensing methods and presents the challenges that need to be            identification through vision and Wi-Fi-based trajectory matching,”
addressed in the future. Based on the identified challenges,           in Proc. 16th Int. Conf. Distrib. Comput. Sensor Syst. (DCOSS),
                                                                       Marina del Rey, CA, USA, 2020, pp. 59–68.
future research directions are suggested related to WiFi
                                                                  [21] Y. Zhang, C. Wu, and Y. Chen, “A low-overhead indoor positioning
sensing to facilitate the reader’s extending the research in           system using CSI fingerprint based on transfer learning,” IEEE
the field.                                                             Sensors J., vol. 21, no. 16, pp. 18156–18165, Aug. 2021.



3618                                                                                                                          VOLUME 5, 2024
 [22] S. A. Shah and F. Fioranelli, “RF sensing technologies for assisted         [43] K. Toda and N. Shinomiya, “Machine learning-based fall detection
      daily living in healthcare: A comprehensive review,” IEEE Aerosp.                system for the elderly using passive RFID sensor tags,” in Proc.
      Electron. Syst. Mag., vol. 34, no. 11, pp. 26–44, Nov. 2019.                     IEEE 13th Int. Conf. Sens. Technol. (ICST), Sydney, NSW, Australia,
 [23] X. Wang, X. Wang, and S. Mao, “RF sensing in the Internet of                     2019, pp. 1–6.
      Things: A general deep learning framework,” IEEE Commun. Mag.,              [44] X. Fan, F. Wang, F. Wang, W. Gong, and J. Liu, “When RFID
      vol. 56, no. 9, pp. 62–67, Sep. 2018.                                            meets deep learning: Exploring cognitive intelligence for activity
 [24] B. Fu, N. Damer, F. Kirchbuchner, and A. Kuijper, “Sensing                       identification,” IEEE Wireless Commun., vol. 26, no. 3, pp. 19–25,
      technology for human activity recognition: A comprehensive survey,”              Jun. 2019.
      IEEE Access, vol. 8, pp. 83791–83820, 2020.                                 [45] Z. Liu, X. Liu, J. Zhang, and K. Li, “Opportunities and challenges
 [25] Z. Hussain, M. Sheng, and W. E. Zhang, “Different approaches for                 of wireless human sensing for the smart IoT world: A survey,” IEEE
      human activity recognition: A survey,” 2019, arXiv:1906.05074.                   Netw., vol. 33, no. 5, pp. 104–110, Oct. 2019.
 [26] Y. Yao et al., “Fall detection system using millimeter-wave radar           [46] Z. Wang, Z. Huang, C. Zhang, W. Dou, Y. Guo, and D. Chen, “CSI-
      based on neural network and information fusion,” IEEE Internet                   based human sensing using model-based approaches: A survey,” J.
      Things J., vol. 9, no. 21, pp. 21038–21050, Nov. 2022.                           Comput. Design Eng., vol. 8, no. 2, pp. 510–523, 2021.
 [27] Y. Kim, I. Alnujaim, and D. Oh, “Human activity classification based        [47] D. Halperin, W. Hu, A. Sheth, and D. Wetherall, “Tool release:
      on point clouds measured by millimeter wave MIMO radar with                      Gathering 802.11n traces with channel state information,” ACM
      deep recurrent neural networks,” IEEE Sensors J., vol. 21, no. 12,               SIGCOMM Comput. Commun. Rev., vol. 41, no. 1, p. 53,
      pp. 13522–13529, Jun. 2021.                                                      2011.
 [28] S. Z. Gurbuz and M. G. Amin, “Radar-based human-motion                      [48] Y. Xie, Z. Li, and M. Li, “Precise power delay profiling with
      recognition with deep learning: Promising applications for indoor                commodity W-Fi,” in Proc. 21st Annu. Int. Conf. Mobile Comput.
      monitoring,” IEEE Signal Process. Mag., vol. 36, no. 4, pp. 16–28,               Network., Paris, France, 2015, pp. 53–64.
      Jul. 2019.                                                                  [49] H. Li, W. Yang, J. Wang, Y. Xu, and L. Huang, “WiFinger: Talk
 [29] X. Dong, Z. Zhao, Y. Wang, T. Zeng, J. Wang, and Y. Sui,                         to your smart devices with finger-grained gesture,” in Proc. ACM
      “FMCW radar-based hand gesture recognition using spatiotemporal                  Int. Joint Conf. Pervas. Ubiquitous Comput., Heldelberg, Germany,
      deformable and context-aware convolutional 5-D feature represen-                 2016, pp. 250–261.
      tation,” IEEE Trans. Geosci. Remote Sens., vol. 60, Oct. 2021,              [50] D. Zhu, N. Pang, G. Li, and S. Liu, “WiseFi: Activity localization
      Art. no. 5107011.                                                                and recognition on commodity off-the-shelf Wi-Fi devices,” in Proc.
 [30] A. Chebrolu, “FallWatch: A novel approach for through-wall fall                  IEEE 18th Int. Conf. High Perform. Comput. Commun., Sydney,
      detection in real-time for the elderly using artificial intelligence,” in        NSW, Australia, 2016, pp. 562–569.
      Proc. IEEE 3rd Int. Conf. Transdiscipl. AI (TransAI), Laguna Hills,         [51] S. Yousefi, H. Narui, S. Dayal, S. Ermon, and S. Valaee,
      CA, USA, 2021, pp. 57–63.                                                        “A survey on behavior recognition using Wi-Fi channel state
 [31] T. Li, L. Fan, Y. Yuan, and D. Katabi, “Unsupervised learning for                information,” IEEE Commun. Mag., vol. 55, no. 10, pp. 98–104,
      human sensing using radio signals,” in Proc. IEEE/CVF Winter Conf.               Oct. 2017.
      Appl. Comput. Vis., Waikoloa, HI, USA, 2022, pp. 3288–3297.                 [52] Z. Wang et al., “A survey on CSI-based human behavior recognition
 [32] L. Fan, T. Li, Y. Yuan, and D. Katabi, “In-home daily-life captioning            in through-the-wall scenario,” IEEE Access, vol. 7, pp. 78772–78793,
      using radio signals,” in Proc. 16th Eur. Conf. Comput. Vis., Glasgow,            2019.
      U.K., 2020, pp. 105–123.                                                    [53] H. F. T. Ahmed, H. Ahmad, and C. Aravind, “Device free human
 [33] L. Fan, T. Li, R. Fang, R. Hristov, Y. Yuan, and D. Katabi, “Learning            gesture recognition using Wi-Fi CSI: A survey,” Eng. Appl. Artif.
      long-term representations for person re-identification using radio               Intell., vol. 87, Jan. 2020, Art. no. 103281.
      signals,” in Proc. IEEE/CVF Conf. Comput. Vis. Pattern Recognit.,           [54] J. Liu, H. Liu, Y. Chen, Y. Wang, and C. Wang, “Wireless sensing
      Seattle, WA, USA, 2020, pp. 10699–10709.                                         for human activity: A survey,” IEEE Commun. Surveys Tuts., vol. 22,
 [34] C.-Y. Hsu, R. Hristov, G.-H. Lee, M. Zhao, and D. Katabi,                        no. 3, pp. 1629–1645, 3rd Quart., 2019.
      “Enabling identification and behavioral sensing in homes using              [55] J. Xiao, H. Li, M. Wu, H. Jin, M. J. Deen, and J. Cao, “A survey on
      radio reflections,” in Proc. CHI Conf. Human Factors Comput. Syst.,              wireless device-free human sensing: Application scenarios, current
      Glasgow, U.K., 2019, pp. 1–13.                                                   solutions, and open issues,” ACM Comput. Surveys, vol. 55, no. 5,
 [35] C. Ding, Y. Zou, L. Sun, H. Hong, X. Zhu, and C. Li, “Fall detection             pp. 1–35, 2022.
      with multi-domain features by a portable FMCW radar,” in Proc.              [56] Y. Ge et al., “Contactless Wi-Fi sensing and monitoring for future
      IEEE MTT-S Int. Wireless Symp. (IWS), Guangzhou, China, 2019,                    healthcare-emerging trends, challenges, and opportunities,” IEEE Rev.
      pp. 1–3.                                                                         Biomed. Eng., vol. 16, pp. 171–191, 2022.
 [36] Y. Zhao, V. Sark, M. Krstic, and E. Grass, “Novel approach for              [57] J. Yang et al., “SenseFi: A library and benchmark on deep-learning-
      gesture recognition using mmwave FMCW radar,” in Proc. IEEE                      empowered Wi-Fi human sensing,” Patterns, vol. 4, no. 3, 2023,
      95th Veh. Technol. Conf. (VTC), Helsinki, Finland, 2022, pp. 1–6.                Art. no. 100703.
 [37] C. Wang et al., “Multi-touch in the Air: Device-free finger                 [58] J. Ding, Y. Wang, J. Zhang, H. Chen, H. Si, and J. Liu, “Multi-AP
      tracking and gesture recognition via COTS RFID,” in Proc. IEEE                   CSI fusion and features optimization-based behavioral sensing on
      Conf. Comput. Commun. (INFOCOM), Honolulu, HI, USA, 2018,                        Wi-Fi platform,” IEEE Sensors J., vol. 23, no. 22, pp. 27601–27612,
      pp. 1691–1699.                                                                   Nov. 2023.
 [38] Y. Zou, J. Xiao, J. Han, K. Wu, Y. Li, and L. M. Ni, “GRfid: A              [59] M. Ali, P. Hendriks, N. Popping, S. Levi, and A. Naveed, “A
      device-free RFID-based gesture recognition system,” IEEE Trans.                  comparison of machine learning algorithms for Wi-Fi sensing using
      Mobile Comput., vol. 16, no. 2, pp. 381–393, Feb. 2017.                          CSI data,” Electronics, vol. 12, no. 18, p. 3935, 2023.
 [39] H. Ding et al., “Femo: A platform for free-weight exercise monitoring       [60] P. F. Moshiri, R. Shahbazian, M. Nabati, and S. A. Ghorashi, “A
      with RFIDs,” in Proc. 13th ACM Conf. Embed. Netw. Sensor Syst.,                  CSI-based human activity recognition using deep learning,” Sensors,
      Seoul, South Korea, 2015, pp. 141–154.                                           vol. 21, no. 21, p. 7225, 2021.
 [40] Y. Wang and Y. Zheng, “Modeling RFID signal reflec-                         [61] F. Succetti et al., “A fast deep learning technique for Wi-Fi-based
      tion for contact-free activity recognition,” Proc. ACM Interact.,                human activity recognition,” Electrom. Waves, vol. 174, pp. 127–141,
      Mobile, Wearable Ubiquitous Technol., vol. 2, no. 4, pp. 1–22,                   Jul. 2022.
      2018.                                                                       [62] A. Poulose, J. H. Kim, and D. S. Han, “HIT HAR: Human
 [41] G. A. Oguntala et al., “Smartwall: Novel RFID-enabled ambient                    image threshing machine for human activity recognition using deep
      human activity recognition using machine learning for unobtru-                   learning models,” Comput. Intell. Neurosci., vol. 2022, Oct. 2022,
      sive health monitoring,” IEEE Access, vol. 7, pp. 68022–68033,                   Art. no. 1808990.
      2019.                                                                       [63] M. Keaton et al., “Wi-Fi-based in-home fall-detection utility:
 [42] X. Fan, W. Gong, and J. Liu, “Tagfree activity identification with               Application of Wi-Fi channel state information as a fall detection ser-
      RFIDs,” Proc. ACM Interact., Mobile, Wearable Ubiquitous Technol.,               vice,” in Proc. IEEE Int. Conf. Eng., Technol. Innovat. (ICE/ITMC),
      vol. 2, no. 1, pp. 1–23, 2018.                                                   Cardiff, U.K., 2020, pp. 1–6.

VOLUME 5, 2024                                                                                                                                           3619
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




 [64] T. Nakamura, M. Bouazizi, K. Yamamoto, and T. Ohtsuki,                    [85] S. Li, Z. Liu, Y. Zhang, Q. Lv, X. Niu, L. Wang, and D. Zhang,
      “Wi-Fi-based fall detection using spectrogram image of chan-                   “WiBorder: Precise Wi-Fi based boundary sensing via through-wall
      nel state information,” IEEE Internet Things J., vol. 9, no. 18,               discrimination,” Proc. ACM Interact., Mobile, Wearable Ubiquitous
      pp. 17220–17234, Sep. 2022.                                                    Technol., vol. 4, no. 3, pp. 1–30, 2020.
 [65] U. M. Khan, Z. Kabir, S. A. Hassan, and S. H. Ahmed, “A deep              [86] Y. Ma, G. Zhou, and S. Wang, “Wi-Fi sensing with channel state
      learning framework using passive Wi-Fi sensing for respiration                 information: A survey,” ACM Comput. Surveys, vol. 52, no. 3,
      monitoring,” in Proc. IEEE Global Commun. Conf. (GLOBCOM),                     pp. 1–36, 2019.
      Singapore, 2017, pp. 1–6.                                                 [87] J. Shang and J. Wu, “Fine-grained vital signs estimation using
 [66] R. Zhang, X. Jing, S. Wu, C. Jiang, J. Mu, and F. R. Yu, “Device-free          commercial Wi-Fi devices,” in Proc. 8th Wireless Students, Workshop,
      wireless sensing for human detection: The deep learning perspective,”          New York, NY, USA, 2016, pp. 30–32.
      IEEE Internet Things J., vol. 8, no. 4, pp. 2517–2539, Feb. 2021.         [88] H. Abdelnasser, M. Youssef, and K. A. Harras, “Wigest: A
 [67] J. Zhang et al., “A survey of mmwave-based human sensing:                      ubiquitous Wi-Fi-based gesture recognition system,” in Proc. IEEE
      Technology, platforms and applications,” IEEE Commun. Surveys                  Conf. Comput. Commun. (INFOCOM), Hong Kong, China, 2015,
      Tuts., vol. 25, no. 4, pp. 2052–2087, 4th Quart., 2023.                        pp. 1472–1480.
 [68] S. Pisa, E. Pittella, and E. Piuzzi, “A survey of radar systems for       [89] N. Xiao, P. Yang, Y. Yan, H. Zhou, and X.-Y. Li, “Motion-
      medical applications,” IEEE Aerosp. Electron. Syst. Mag., vol. 31,             Fi: Recognizing and counting repetitive motions with passive
      no. 11, pp. 64–81, Nov. 2016.                                                  wireless backscattering,” in Proc. IEEE Conf. Comput. Commun.
 [69] E. Elbasani, P. Siriporn, and J. S. Choi, A Survey on RFID in Industry         (INFOCOM), Honolulu, HI, USA, 2018, pp. 2024–2032.
      4.0. Cham, Switzerland: Springer, 2020, pp. 1–16.                         [90] T. Yu, H. Jin, and K. Nahrstedt, “Writinghacker: Audio-based
 [70] Y. Duroc, “From identification to sensing: RFID is one of the key              eavesdropping of handwriting via mobile devices,” in Proc. ACM
      technologies in the IoT field,” Sensors, vol. 22, no. 19, p. 7523,             Int. Joint Conf. Pervas. Ubiquitous Comput., Heidelberg, Germany,
      2022.                                                                          2016, pp. 463–473.
 [71] H. Jiang, C. Cai, X. Ma, Y. Yang, and J. Liu, “Smart home based           [91] M. N. Patil, B. Iyer, and R. Arya, “Performance evaluation of PCA
      on Wi-Fi sensing: A survey,” IEEE Access, vol. 6, pp. 13317–13325,             and ICA algorithm for facial expression recognition application,” in
      2018.                                                                          Proc. 5th Int. Conf. Soft Comput. Problem Solving, Singapore, 2016,
 [72] D. Wu, D. Zhang, C. Xu, H. Wang, and X. Li, “Device-free Wi-                   pp. 965–976.
      Fi human sensing: From pattern-based to model-based approaches,”          [92] Z. Yang, Y. Zhang, and Q. Zhang, “Rethinking fall detection with
      IEEE Commun. Mag., vol. 55, no. 10, pp. 91–97, Oct. 2017.                      Wi-Fi,” IEEE Trans. Mobile Comput., vol. 22, no. 10, pp. 6126–6143,
 [73] P. Bahl and V. Padmanabhan, “RADAR: An in-building RF-based                    Oct. 2023.
      user location and tracking system,” in Proc. 19th Annu. Joint Conf.       [93] J. Yang, X. Chen, H. Zou, D. Wang, and L. Xie, “AutoFi:
      IEEE Comput. Commun. Soc. (INFOCOM), Tel Aviv, Israel, 2000,                   Toward automatic Wi-Fi human sensing via geometric self-supervised
      pp. 775–784.                                                                   learning,” IEEE Internet Things J., vol. 10, no. 8, pp. 7416–7425,
 [74] Y. Wang, M. Li, and M. Li, “The statistical analysis of IEEE 802.11            Apr. 2023.
      wireless local area network–based received signal strength indicator      [94] S. Liu, Y. Zhao, and B. Chen, “WiCount: A deep learning approach
      in indoor location sensing systems,” Int. J. Distrib. Sensor Netw.,            for crowd counting using Wi-Fi signals,” in Proc. IEEE Int. Symp.
      vol. 13, no. 12, 2017, Art. no. 1550147717747858.                              Parallel Distrib. Process. Appl. IEEE Int. Conf. Ubiquitous Comput.
 [75] A. T. Parameswaran, M. I. Husain, and S. Upadhyaya, “Is RSSI                   Commun. (ISPA/IUCC), Guangzhou, China, 2017, pp. 967–974.
      a reliable parameter in sensor localization algorithms: An experi-        [95] Y. Ma et al., “Location-and person-independent activity recognition
      mental study,” in Proc. IEEE Field Failure Data Analysis Workshop              with Wi-Fi, deep neural networks, and reinforcement learning,” ACM
      (F2DA09), Niagara Falls, NY, USA, 2009, pp. 1–5.                               Trans. Internet Things, vol. 2, no. 1, pp. 1–25, 2021.
 [76] R. Zavorka, R. Marsalek, J. Vychodil, E. Zöchmann, G. Ghiaasi, and        [96] L. Hao, B. Huang, B. Jia, G. Xu, and G. Mao, “Toward accurate
      J. Blumenstein, “Deep neural network-based human activity classifier           crowd counting in large surveillance areas based on passive Wi-Fi
      in 60 GHz WLAN channels,” in Proc. IEEE Globecom Workshops                     sensing,” IEEE Trans. Intell. Transp. Syst., vol. 24, no. 12, pp. 14086–
      (GC Wkshps), Rio de Janeiro, Brazil, 2022, pp. 1304–1309.                      14096, Dec. 2023.
 [77] M. Zhao et al., “Through-wall human pose estimation using radio           [97] W. Qian, F. Lauri, and F. Gechter, “Supervised and semi-supervised
      signals,” in Proc. IEEE Conf. Comput. Vis. Pattern Recognit.,                  deep probabilistic models for indoor positioning problems,”
      Salt Lake City, UT, USA, 2018, pp. 7356–7365.                                  Neurocomputing, vol. 435, pp. 228–238, May 2021.
 [78] Y. Xie, J. Xiong, M. Li, and K. Jamieson, “mD-Track: Leveraging           [98] G. Liu, P. Neupane, H.-C. Wu, W. Xiang, L. Pu, and S. Y. Chang,
      multi-dimensionality for passive indoor Wi-Fi tracking,” in Proc.              “Novel robust indoor device-free moving-object localization and
      25th Annu. Int. Conf. Mobile Comput. Network., Los Cabos, Mexico,              tracking using machine learning with Kalman filter and smoother,”
      2019, pp. 1–16.                                                                IEEE Syst. J., vol. 16, no. 4, pp. 6253–6264, Dec. 2022.
 [79] K. Chetty, G. E. Smith, and K. Woodbridge, “Through-the-wall              [99] J. Ding, Y. Wang, and X. Fu, “Wihi: Wi-Fi based human identity
      sensing of personnel using passive bistatic Wi-Fi radar at standoff            identification using deep learning,” IEEE Access, vol. 8, pp. 129246–
      distances,” IEEE Trans. Geosci. Remote Sens., vol. 50, no. 4,                  129262, 2020.
      pp. 1218–1226, Apr. 2012.                                                [100] T. Li, T. Chen, K. Li, and R. Ao, “Vi-Wi-Fi-Gate: A Wi-Fi sensing
 [80] B. Tan, K. Woodbridge, and K. Chetty, “Awireless passive radar                 gait recognition method inspired by the image vision field,” in Proc.
      system for real-time through-wall movement detection,” IEEE Trans.             Int. Conf. Internet Things Mach. Learn. (IoTML), Singapore, 2023,
      Aerosp. Electron. Syst., vol. 52, no. 5, pp. 2596–2603, Oct. 2016.             pp. 376–381.
 [81] B. Tan, K. Woodbridge, and K. Chetty, “A real-time high resolution       [101] C. Tang, W. Li, S. Vishwakarma, F. Shi, S. Julier, and K. Chetty,
      passive Wi-Fi doppler-radar and its applications,” in Proc. Int. Radar         “MDPose: Human skeletal motion reconstruction using Wi-Fi micro-
      Conf., Lille, France, 2014, pp. 1–6.                                           doppler signatures,” IEEE Trans. Aerosp. Electron. Syst., vol. 60,
 [82] M. AlHamaydeh and N. Ghazal Aswad, “Structural health monitoring               no. 1, pp. 157–167, Feb. 2024.
      techniques and technologies for large-scale structures: Challenges,      [102] F. Wang, S. Panev, Z. Dai, J. Han, and D. Huang, “Can Wi-Fi
      limitations, and recommendations,” Pract. Periodical Struct. Design            estimate person pose?” 2019, arXiv:1904.00277.
      Constr., vol. 27, no. 3, 2022, Art. no. 3122004.                         [103] M. Xu, Z. Guo, L. Gui, B. Sheng, and F. Xiao, “WiSPE: A COTS
 [83] P. S. Santhalingam, A. A. Hosain, D. Zhang, P. Pathak, H. Rangwala,            Wi-Fi-based 2D static human pose estimation,” IEEE Syst. J., vol. 17,
      and R. Kushalnagar, “mmASL: Environment-independent ASl ges-                   no. 3, pp. 3560–3571, Sep. 2023.
      ture recognition using 60 GHz millimeter-wave signals,” Proc.            [104] Y. Wang, L. Guo, Z. Lu, X. Wen, S. Zhou, and W. Meng, “From point
      ACM Interact., Mobile, Wearable Ubiquitous Technol., vol. 4, no. 1,            to space: 3D moving human pose estimation using commodity Wi-
      pp. 1–30, 2020.                                                                Fi,” IEEE Commun. Lett., vol. 25, no. 7, pp. 2235–2239, Jul. 2021.
 [84] W. Wang, A. X. Liu, M. Shahzad, K. Ling, and S. Lu, “Understanding       [105] T.-D. H. Nguyen and H.-N. H. Nguyen, “Towards a robust Wi-Fi-
      and modeling of Wi-Fi signal based human activity recognition,”                based fall detection with adversarial data augmentation,” in Proc.
      in Proc. 21st Annu. Int. Conf. Mobile Comput. Netw., Paris, France,            IEEE 54th Annu. Conf. Inf. Sci. Syst. (CISS), Princeton, NJ, USA,
      2015, pp. 65–76.                                                               2020, pp. 1–6.

3620                                                                                                                                          VOLUME 5, 2024
[106] R. Guo, H. Li, D. Han, and R. Liu, “Feasibility analysis of using       [127] C. Xiao, Y. Lei, Y. Ma, F. Zhou, and Z. Qin, “DeepSeg:
      channel state information (CSI) acquired from Wi-Fi routers for               Deep-learning-based activity segmentation framework for activity
      construction worker fall detection,” Int. J. Environ. Res. Public             recognition using Wi-Fi,” IEEE Internet Things J., vol. 8, no. 7,
      Health, vol. 20, no. 6, p. 4998, 2023.                                        pp. 5669–5681, Apr. 2021.
[107] F. Wang, W. Gong, and J. Liu, “On spatial diversity in Wi-Fi-based      [128] Y. Yu, X. Si, C. Hu, and J. Zhang, “A review of recurrent neural
      human activity recognition: A deep learning-based approach,” IEEE             networks: LSTM cells and network architectures,” Neural Comput.,
      Internet Things J., vol. 6, no. 2, pp. 2035–2047, Apr. 2019.                  vol. 31, no. 7, pp. 1235–1270, 2019.
[108] W. Cui, B. Li, L. Zhang, and Z. Chen, “Device-free single-user          [129] Y. Wang, X. Jiang, R. Cao, and X. Wang, “Robust indoor human
      activity recognition using diversified deep ensemble learning,” Appl.         activity recognition using wireless signals,” Sensors, vol. 15, no. 7,
      Soft Comput., vol. 102, Apr. 2021, Art. no. 107066.                           pp. 17195–17208, 2015.
[109] F. Abuhoureyah, Y. C. Wong, A. S. B. M. Isira, and M. N. Al-Andoli,     [130] H. Wang, D. Zhang, Y. Wang, J. Ma, Y. Wang, and S. Li, “Rt-fall: A
      “CSI-based location independent human activity recognition using              real-time and contactless fall detection system with commodity Wi-Fi
      deep learning,” Human-Centric Intell. Syst., vol. 3, pp. 1–21,                devices,” IEEE Trans. Mobile Comput., vol. 16, no. 2, pp. 511–526,
      Dec. 2023.                                                                    Feb. 2017.
[110] A. Elkelany, R. Ross, and S. Mckeever, “Wi-Fi-based human activity      [131] C. Zhang and W. Jiao, “Imgfi: A high accuracy and lightweight
      recognition using attention-based BiLSTM,” in Proc. Irish Conf.               human activity recognition framework using CSI image,” IEEE
      Artif. Intell. Cogn. Sci., Munster, Ireland, 2022, pp. 121–133.               Sensors J., vol. 23, no. 18, pp. 21966–21977, Sep. 2023.
[111] M. J. Bocus, K. Chetty, and R. J. Piechocki, “UWB and Wi-Fi             [132] Q. Ren, Y. Wang, S. Liu, and X. Lv, “FSTNet: Learning spatial-
      systems as passive opportunistic activity sensing radars,” in Proc.           temporal correlations from fingerprints for indoor positioning,” Ad
      IEEE Radar Conf. (RadarConf21), Atlanta, GA, USA, 2021, pp. 1–6.              Hoc Netw., vol. 149, Oct. 2023, Art. no. 103244.
[112] A. Zhuravchak, O. Kapshii, and E. Pournaras, “Human activity recog-     [133] N. Hernández et al., “Wi-FiNet: Wi-Fi-based indoor localisa-
      nition based on Wi-Fi CSI data-a deep neural network approach,”               tion using CNNs,” Expert Syst. Appl., vol. 177, Sep. 2021,
      Procedia Comput. Sci., vol. 198, pp. 59–66, Jan. 2022.                        Art. no. 114906.
[113] Y. Zhang, Y. Yin, Y. Wang, J. Ai, and D. Wu, “CSI-based                 [134] J. Guo, I. W.-H. Ho, Y. Hou, and Z. Li, “FedPos: A federated transfer
      location-independent human activity recognition with parallel con-            learning framework for CSI-based Wi-Fi indoor positioning,” IEEE
      volutional networks,” Comput. Commun., vol. 197, pp. 87–95,                   Syst. J., vol. 17, no. 3, pp. 4579–4590, Sep. 2023.
      Jan. 2023.                                                              [135] C. Yu et al., “Wi-Fi-based human pose image generation,” in
[114] S. Mekruksavanich, W. Phaphan, N. Hnoohom, and A. Jitpattanakul,              Proc. IEEE 24th Int. Workshop Multimedia Signal Process. (MMSP),
      “Attention-based hybrid deep learning network for human activity              Shanghai, China, 2022, pp. 1–6.
      recognition using Wi-Fi channel state information,” Appl. Sci.,         [136] H. A. H. Ali and S. Seytnazarov, “Human walking direction detection
      vol. 13, no. 15, p. 8884, 2023.                                               using wireless signals, machine and deep learning algorithms,”
                                                                                    Sensors, vol. 23, no. 24, p. 9726, 2023.
[115] L. Hao, B. Huang, B. Jia, and G. Mao, “On the fine-grained crowd
                                                                              [137] J. Geng, D. Huang, and F. De la Torre, “DensePose from Wi-Fi,”
      analysis via passive Wi-Fi sensing,” IEEE Trans. Mobile Comput.,
                                                                                    2022, arXiv:2301.00250.
      vol. 23, no. 6, pp. 6697–6711, Jun. 2024.
                                                                              [138] Z. Cao, T. Simon, S.-E. Wei, and Y. Sheikh, “Realtime multi-
[116] U. Singh, J.-F. Determe, F. Horlin, and P. De Doncker, “Crowd
                                                                                    person 2D pose estimation using part affinity fields,” in Proc. IEEE
      forecasting based on Wi-Fi sensors and LSTM neural networks,”
                                                                                    Conf. Comput. Vis. Pattern Recognit., Honolulu, HI, USA, 2017,
      IEEE Trans. Instrum. Meas., vol. 69, no. 9, pp. 6121–6131,
                                                                                    pp. 7291–7299.
      Sep. 2020.
                                                                              [139] Y. Zhou, C. Xu, L. Zhao, A. Zhu, F. Hu, and Y. Li, “Wi-Fi-Former:
[117] O. T. Ibrahim, W. Gomaa, and M. Youssef, “CrossCount: A deep                  Pay more attention to pose estimation with Wi-Fi,” Entropy, vol. 25,
      learning system for device-free human counting using Wi-Fi,” IEEE             no. 1, p. 20, 2022.
      Sensors J., vol. 19, no. 21, pp. 9921–9928, Nov. 2019.
                                                                              [140] Y.-C. Chen et al., “Seeing the unseen: Wi-Fi-based 2D human
[118] L. Deng, J. Yang, S. Yuan, H. Zou, C. X. Lu, and L. Xie,                      pose estimation via an evolving attentive spatial-frequency network,”
      “GaitFi: Robust device-free human identification via Wi-Fi and                Pattern Recognit. Lett., vol. 171, pp. 21–27, Jul. 2023.
      vision multimodal learning,” IEEE Internet Things J., vol. 10, no. 1,   [141] Y. Liu and S. Konomi, “Wihead: Wi-Fi-based head-pose estimation,”
      pp. 625–636, Jan. 2023.                                                       in Proc. Int. Conf. Human-Comput. Interact., Cham, Switzerland,
[119] W. Jiang et al., “Towards 3D human pose construction using Wi-Fi,”            2022, pp. 69–86.
      in Proc. 26th Annu. Int. Conf. Mobile Comput. Netw., London, U.K.,      [142] S. R. Pokhrel et al., “On correlated knowledge distillation for
      2020, pp. 1–14.                                                               monitoring human pose with radios,” 2023, arXiv:2305.14829.
[120] Y. Ren, Z. Wang, Y. Wang, S. Tan, Y. Chen, and J. Yang, “GoPose: 3D     [143] Y. Ren, Z. Wang, S. Tan, Y. Chen, and J. Yang, “Winect: 3D human
      human pose estimation using Wi-Fi,” Proc. ACM Interact., Mobile,              pose tracking for free-form activity using commodity Wi-Fi,” Proc.
      Wearable Ubiquitous Technol., vol. 6, no. 2, pp. 1–25, 2022.                  ACM Interact., Mobile, Wearable Ubiquitous Technol., vol. 5, no. 4,
[121] J. Liu, L. Wang, L. Guo, J. Fang, B. Lu, and W. Zhou, “A research on          pp. 1–29, 2021.
      CSI-based human motion detection in complex scenarios,” in Proc.        [144] Y. Wang, Y. Ren, Y. Chen, and J. Yang, “A Wi-Fi vision-based 3D
      IEEE 19th Int. Conf. e-Health Netw., Appl. Services (Healthcom),              human mesh reconstruction,” in Proc. 28th Annu. Int. Conf. Mobile
      Dalian, China, 2017, pp. 1–6.                                                 Comput. Netw., Sydney, NSW, Australia, 2022, pp. 814–816.
[122] Z. He, X. Zhang, Y. Wang, Y. Lin, G. Gui, and H. Gacanin, “A robust     [145] Y. Wang and J. Yang, “3D human mesh construction leveraging
      CSI-based Wi-Fi passive sensing method using attention mechanism              Wi-Fi,” 2022, arXiv:2210.10957.
      deep learning,” IEEE Internet Things J., vol. 10, no. 19, pp. 17490–    [146] L. Wang, L. Guo, Z. Lu, X. Wen, and S. Zhou, “WiLink: Link
      17499, Oct. 2023.                                                             selection-based 3D human pose estimation using commodity Wi-Fi,”
[123] S. M. Bokhari, S. Sohaib, A. R. Khan, and M. Shafi, “DGRU                     in Proc. IEEE Wireless Commun. Netw. Conf. (WCNC), Glasgow,
      based human activity recognition using channel state information,”            U.K., 2023, pp. 1–7.
      Measurement, vol. 167, Jan. 2021, Art. no. 108245.                      [147] Y. Ren and J. Yang, “3D human pose estimation for free-form activity
[124] L. Zhang, Y. Zhang, R. Bao, Y. Zhu, and X. Shi, “A novel                      using Wi-Fi signals,” 2021, arXiv:2110.08314.
      Wi-Fi-based personnel behavior sensing with a deep learning             [148] P. Yazdanian and V. Pourahmadi, “DeepPos: Deep supervised
      method,” IEEE Access, vol. 10, pp. 120136–120145, 2022.                       autoencoder network for CSI-based indoor localization,” 2018,
[125] F. Khan, A. U. Khan, I. Ahmad, and W. Choi, “RS-DeepNet:                      arXiv:1811.12182.
      A machine learning aided RSSI fingerprinting for precise indoor         [149] S. BelMannoubi, H. Touati, and H. Snoussi, “Stacked auto-encoder
      localization,” in Proc. 2nd Int. Conf. Maritime IT Converg. (ICMIC),          for scalable indoor localization in wireless sensor networks,” in
      Jeju, South Korea, 2023, pp. 1–6.                                             Proc. 15th Int. Wireless Commun. Mobile Comput. Conf. (IWCMC),
[126] H. El Zein, F. Mourad-Chehade, and H. Amoud, “Leveraging Wi-Fi                Tangier, Morocco, 2019, pp. 1245–1250.
      CSI data for fall detection: A deep learning approach,” in Proc. IEEE   [150] B. Li, W. Cui, W. Wang, L. Zhang, Z. Chen, and M. Wu, “Two-stream
      5th Int. Conf. Bio-Eng. Smart Technol. (BioSMART), Paris, France,             convolution augmented transformer for human activity recognition,”
      2023, pp. 1–4.                                                                in Proc. AAAI Conf. Artif. Intell., 2021, pp. 286–293.

VOLUME 5, 2024                                                                                                                                       3621
AHMAD et al.: WiFi-BASED HUMAN SENSING WITH DL




[151] F. Luo, S. Khan, B. Jiang, and K. Wu, “Vision transform-               [172] “Falls.” WHO. 2021. [Online]. Available: https://www.who.int/en/
      ers for human activity recognition using Wi-Fi channel state                 news-room/fact-sheets/detail/falls
      information,” IEEE Internet Things J., early access, Mar. 21, 2024,    [173] “Ageing and health.” WHO. 2022. [Online]. Available: https://www.
      doi: 10.1109/JIOT.2024.3375337.                                              who.int/ageing/about/facts/en/.
[152] B. Sheng, R. Han, H. Cai, F. Xiao, L. Gui, and Z. Guo,                 [174] Y. Hu, F. Zhang, C. Wu, B. Wang, and K. R. Liu, “A Wi-Fi-based pas-
      “CDFi: Cross-domain action recognition using Wi-Fi signals,”                 sive fall detection system,” in Proc. IEEE Int. Conf. Acoust., Speech
      IEEE Trans. Mobile Comput., early access, Jan. 2, 2024,                      Signal Process. (ICASSP), Barcelona, Spain, 2020, pp. 1723–1727.
      doi: 10.1109/TMC.2023.3348939.                                         [175] Y. Hu, F. Zhang, C. Wu, B. Wang, and K. J. R. Liu, “DeFall:
[153] Z. Zhang, H. Du, S. Choi, and S. H. Cho, “TIPS: Transformer based            Environment-independent passive fall detection using Wi-Fi,” IEEE
      indoor positioning system using both CSI and DoA of Wi-Fi signal,”           Internet Things J., vol. 9, no. 11, pp. 8515–8530, Jun. 2022.
      IEEE Access, vol. 10, pp. 111363–111376, 2022.                         [176] R. Hristov, Z. Kabelac, H. Rahul, and D. Katabi, “System and method
[154] Y. Zhou, H. Huang, S. Yuan, H. Zou, L. Xie, and J. Yang,                     for wireless detection and measurement of a subject rising from rest,”
      “MetaFi++: Wi-Fi-enabled transformer-based human pose estima-                U.S. Patent 17 235 447, Oct. 21, 2021.
      tion for metaverse avatar simulation,” IEEE Internet Things J.,        [177] M. Gao, A. Souri, M. Zaker, W. Zhai, X. Guo, and Q. Li, “A compre-
      vol. 10, no. 16, pp. 14128–14136, Aug. 2023.                                 hensive analysis for crowd counting methodologies and algorithms in
[155] Y. Chu, K. Cumanan, S. K. Sankarpandi, S. Smith, and O. A. Dobre,            Internet of Things,” Clust. Comput., vol. 27, pp. 859–873, Feb. 2024.
      “Deep learning-based fall detection using Wi-Fi channel state          [178] S. Depatla and Y. Mostofi, “Crowd counting through walls using Wi-
      information,” IEEE Access, vol. 11, pp. 83763–83780, 2023.                   Fi,” in Proc. IEEE Int. Conf. Pervas. Comput. Commun. (PerCom),
[156] M. Tan and Q. Le, “EfficientNet: Rethinking model scaling for                Athens, Greece, 2018, pp. 1–10.
      convolutional neural networks,” in Proc. Int. Conf. Mach. Learn.,
                                                                             [179] H. Zou, Y. Zhou, J. Yang, W. Gu, L. Xie, and C. Spanos,
      Long Beach, California, USA, 2019, pp. 6105–6114.
                                                                                   “Freecount: Device-free crowd counting with commodity Wi-Fi,” in
[157] H. Choi, T. Matsui, S. Misaki, A. Miyaji, M. Fujimoto, and                   Proc. GLOBECOM, IEEE Global Commun. Conf., Singapore, 2017,
      K. Yasumoto, “Simultaneous crowd estimation in counting and                  pp. 1–6.
      localization using Wi-Fi CSI,” in Proc. IEEE Int. Conf. Indoor
                                                                             [180] J. He and W. Yang, “IMep: Device-free multiplayer step counting
      Position. Indoor Navig. (IPIN), Lloret de Mar, Spain, 2021, pp. 1–8.
                                                                                   with Wi-Fi signals,” IEEE Trans. Mobile Comput., vol. 22, no. 10,
[158] H. Choi, M. Fujimoto, T. Matsui, S. Misaki, and K. Yasumoto, “Wi-            pp. 5887–5899, Oct. 2023.
      Cal: Wi-Fi sensing and machine learning based device-free crowd
                                                                             [181] Y. Xu, W. Yang, J. Wang, X. Zhou, H. Li, and L. Huang, “WiStep:
      counting and localization,” IEEE Access, vol. 10, pp. 24395–24410,
                                                                                   Device-free step counting with Wi-Fi signals,” Proc. ACM Interact.,
      2022.
                                                                                   Mobile, Wearable Ubiquitous Technol., vol. 1, no. 4, pp. 1–23, 2018.
[159] R. Zhou, X. Lu, Y. Fu, and M. Tang, “Device-free crowd counting
      with Wi-Fi channel state information and deep neural networks,”        [182] K. Qian, C. Wu, Z. Yang, C. Yang, and Y. Liu, “Decimeter level
      Wireless Netw., vol. 26, pp. 3495–3506, Jul. 2020.                           passive tracking with Wi-Fi,” in Proc. 3rd Workshop Hot Topics
                                                                                   Wireless, New York, NY, USA, 2016, pp. 44–48.
[160] Y. Zhou, A. Zhu, C. Xu, F. Hu, and Y. Li, “PerUnet: Deep signal
      channel attention in Unet for Wi-Fi-based human pose estimation,”      [183] C. Wu, Z. Yang, Z. Zhou, X. Liu, Y. Liu, and J. Cao, “Non-invasive
      IEEE Sensors J., vol. 22, no. 20, pp. 19750–19760, Oct. 2022.                detection of moving and stationary human with Wi-Fi,” IEEE J. Sel.
                                                                                   Areas Commun., vol. 33, no. 11, pp. 2329–2342, Nov. 2015.
[161] C. Yu et al., “Fast 3D human pose estimation using RF signals,”
      in Proc. IEEE Int. Conf. Acoust., Speech Signal Process. (ICASSP),     [184] X. Liu, H. Chen, X. Jiang, J. Qian, G. Aceto, and A. Pescape,
      Rhodes Island, Greece, 2023, pp. 1–5.                                        “Wi-CR: Human action counting and recognition with Wi-Fi signals,”
[162] S. Pouyanfar et al., “A survey on deep learning: Algorithms,                 in Proc. IEEE 4th Int. Conf. Comput., Commun. Security (ICCCS),
      techniques, and applications,” ACM Comput. Surveys, vol. 51, no. 5,          Rome, Italy, 2019, pp. 1–8.
      pp. 1–36, 2018.                                                        [185] D. Wu et al., “WiTraj: Robust indoor motion tracking with Wi-Fi
[163] J. Ding and Y. Wang, “A Wi-Fi-based smart home fall detection                signals,” IEEE Trans. Mobile Comput., vol. 22, no. 5, pp. 3062–3078,
      system using recurrent neural network,” IEEE Trans. Consum.                  May 2023.
      Electron., vol. 66, no. 4, pp. 308–317, Nov. 2020.                     [186] X. Guo, B. Liu, C. Shi, H. Liu, Y. Chen, and M. C. Chuah, “Wi-
[164] R. Dey and F. M. Salem, “Gate-variants of gated recurrent unit (GRU)         Fi-enabled smart human dynamics monitoring,” in Proc. 15th ACM
      neural networks,” in Proc. IEEE 60th Int. Midwest Symp. Circuits             Conf. Embed. Netw. Sensor Syst., Delft, The Netherlands, 2017,
      Syst. (MWSCAS), Boston, MA, USA, 2017, pp. 1597–1600.                        pp. 1–13.
[165] W. Wang, Y. Huang, Y. Wang, and L. Wang, “Generalized autoen-          [187] R. Arthi, D. S. Rawat, A. Pillai, Y. Nair, and S. Kausik, “Analysis
      coder: A neural network framework for dimensionality reduction,”             of indoor localization algorithm for Wi-Fi using received signal
      in Proc. IEEE Conf. Comput. Vis. Pattern Recognit. Workshops,                strength,” in Proc. Int. Conf. Emerg. Trends Adv. Elect. Eng. Renew.
      Columbus, OH, USA, 2014, pp. 490–497.                                        Energy (ETAEERE), 2021, pp. 423–431.
[166] Y. Wang, K. Wu, and L. M. Ni, “Wifall: Device-free fall detection      [188] R. Estrada, N. Vera, and X. Aizaga, “Evaluation of machine learning
      by wireless networks,” IEEE Trans. Mobile Comput., vol. 16, no. 2,           prediction models for Wi-Fi based indoor positioning system,” in
      pp. 581–594, Feb. 2017.                                                      Proc. IEEE Int. Conf. Comput., Inf. Telecommun. Syst. (CITS), Genoa,
[167] S. Chen, W. Yang, Y. Xu, Y. Geng, B. Xin, and L. Huang, “AFall:              Italy, 2023, pp. 01–07.
      Wi-Fi-based device-free fall detection system using spatial angle of   [189] M. Mallik, S. Das, and C. Chowdhury, “Rank based iterative
      arrival,” IEEE Trans. Mobile Comput., vol. 22, no. 8, pp. 4471–4484,         clustering (RBIC) for indoor localization,” Eng. Appl. Artif. Intell.,
      Aug. 2023.                                                                   vol. 121, May 2023, Art. no. 106061.
[168] Z. Chen, L. Zhang, C. Jiang, Z. Cao, and W. Cui, “Wi-Fi CSI based      [190] G. Caso, L. De Nardis, F. Lemic, V. Handziski, A. Wolisz,
      passive human activity recognition using attention based BLSTM,”             and M.-G. Di Benedetto, “ViFi: Virtual fingerprinting Wi-Fi-based
      IEEE Trans. Mobile Comput., vol. 18, no. 11, pp. 2714–2724,                  indoor positioning via multi-wall multi-floor propagation model,”
      Nov. 2019.                                                                   IEEE Trans. Mobile Comput., vol. 19, no. 6, pp. 1478–1491,
[169] W. Jiang et al., “Towards environment independent device free human          Jun. 2020.
      activity recognition,” in Proc. 24th Annu. Int. Conf. Mobile Comput.   [191] X. Wang, L. Gao, S. Mao, and S. Pandey, “CSI-based fingerprinting
      Netw., 2018, pp. 289–304.                                                    for indoor localization: A deep learning approach,” IEEE Trans. Veh.
[170] Z. Shi, Q. Cheng, J. A. Zhang, and R. Y. Da Xu, “Environment-robust          Technol., vol. 66, no. 1, pp. 763–776, Jan. 2017.
      Wi-Fi-based human activity recognition using enhanced CSI and deep     [192] V. Narayan, S. Awasthi, N. Fatima, M. Faiz, and S. Srivastava,
      learning,” IEEE Internet Things J., vol. 9, no. 24, pp. 24643–24654,         “Deep learning approaches for human gait recognition: A review,”
      Dec. 2022.                                                                   in Proc. IEEE Int. Conf. Artif. Intell. Smart Commun. (AISC), 2023,
[171] Z. Shi, J. A. Zhang, R. Y. Xu, and Q. Cheng, “Environment-robust             pp. 763–768.
      device-free human activity recognition with channel-state-             [193] C. Wu, F. Zhang, Y. Hu, and K. R. Liu, “GaitWay: Monitoring
      information enhancement and one-shot learning,” IEEE Trans.                  and recognizing gait speed through the walls,” IEEE Trans. Mobile
      Mobile Comput., vol. 21, no. 2, pp. 540–554, Feb. 2022.                      Comput., vol. 20, no. 6, pp. 2186–2199, Jun. 2021.

3622                                                                                                                                      VOLUME 5, 2024
[194] W. Wang, A. X. Liu, and M. Shahzad, “Gait recognition using Wi-Fi        [215] L. Duan, L. Huang, C. Langbort, A. Pozdnukhov, J. Walrand, and
      signals,” in Proc. ACM Int. Joint Conf. Pervas. Ubiquitous Comput.,            L. Zhang, “Human-in-the-loop mobile networks: A survey of recent
      Heidelberg, Germany, 2016, pp. 363–373.                                        advancements,” J. Sel. Areas Commun., vol. 35, no. 4, pp. 813–831,
[195] Y. Zeng, P. H. Pathak, and P. Mohapatra, “WiWho: Wi-Fi-based                   2017.
      person identification in smart spaces,” in Proc. 15th ACM/IEEE           [216] A. T. Z. Kasgari, W. Saad, and M. Debbah, “Human-in-the-
      Int. Conf. Inf. Process. Sensor Netw. (IPSN), Vienna, Austria, 2016,           loop wireless communications: Machine learning and brain-aware
      pp. 1–12.                                                                      resource management,” IEEE Trans. Commun., vol. 67, no. 11,
[196] Y. Zhou, J. Yang, H. Huang, and L. Xie, “AdaPose: Towards cross-               pp. 7727–7743, Nov. 2019.
      site device-free human pose estimation with commodity Wi-Fi,”
      2023, arXiv:2309.16964.
[197] J. Yang, Y. Zhou, H. Huang, H. Zou, and L. Xie, “MetaFi:
      Device-free pose estimation via commodity Wi-Fi for metaverse
      avatar simulation,” in Proc. IEEE 8th World Forum Internet Things
      (WF-IoT), Yokohama, Japan, 2022, pp. 1–6.                                                         IFTIKHAR AHMAD (Student        Member, IEEE)
[198] Y. Zhang, X. Wang, J. Wen, and X. Zhu, “Wi-Fi-based non-contact                                   received the bachelor’s and master’s degrees
      human presence detection technology,” Sci. Rep., vol. 14, no. 1,                                  in telecommunication engineering from the
      p. 3605, 2024.                                                                                    University of Engineering and Technology
[199] C. Li, Z. Cao, and Y. Liu, “Deep AI enabled ubiquitous wireless                                   (UET) Peshawar and UET Taxila, Pakistan, in
      sensing: A survey,” ACM Comput. Surveys, vol. 54, no. 2, pp. 1–35,                                2015 and 2018, respectively. He is currently
      2021.                                                                                             pursuing the Ph.D. degree with the Smart
[200] Q. Li, R. Gravina, Y. Li, S. H. Alsamhi, F. Sun, and G. Fortino,                                  Networking Laboratory, Department of Computer
      “Multi-user activity recognition: Challenges and opportunities,” Inf.                             Engineering, College of IT Convergence, Chosun
      Fusion, vol. 63, pp. 121–135, Nov. 2020.                                                          University, Republic of South Korea. His research
[201] F. Gu, M.-H. Chung, M. Chignell, S. Valaee, B. Zhou, and X. Liu,                                  interest    includes    machine-learning-assisted
      “A survey on deep learning for human activity recognition,” ACM                                   RF-based HAR.
      Comput. Surveys, vol. 54, no. 8, pp. 1–34, 2021.
[202] T. Koike-Akino, P. Wang, M. Pajovic, H. Sun, and P. V.
      Orlik, “Fingerprinting-based indoor localization with commercial
      mmWave Wi-Fi: A deep learning approach,” IEEE Access, vol. 8,
      pp. 84879–84892, 2020.                                                                            ARIF ULLAH (Member, IEEE) received the M.S.
[203] R. F. Miranda et al., “A review of cognitive hybrid radio                                         degree in electrical engineering from COMSATS
      frequency/visible light communication systems for wireless sensor                                 University, Islamabad, Pakistan, and the Ph.D.
      networks,” Sensors, vol. 23, no. 18, p. 7815, 2023.                                               degree in electronic and communication engineer-
[204] C. Liang et al., “Integrated sensing, lighting and communication                                  ing from Ghulam Ishaq Khan (GIK) Institute
      based on visible light communication: A review,” Digit. Signal                                    of Engineering Sciences and Technology, Topi,
      Process., vol. 145, Feb. 2024, Art. no. 104340.                                                   Pakistan. He was a Graduate Research Assistant
[205] T. Li, C. An, Z. Tian, A. T. Campbell, and X. Zhou, “Human sensing                                with GIK Institute and also worked as a Research
      using visible light communication,” in Proc. 21st Annu. Int. Conf.                                Fellow with the Smart Networking Laboratory,
      Mobile Comput. Netw., Paris, France, 2015, pp. 331–344.                                           Chosun University, South Korea, from November
[206] K. Gligorić, M. Ajmani, D. Vukobratović, and S. Sinanović, “Visible                            2021 to April 2022. He is currently working as an
      light communications-based indoor positioning via compressed sens-       Assistant Professor with the Department of Computer Engineering, College
      ing,” IEEE Commun. Lett., vol. 22, no. 7, pp. 1410–1413, Jul. 2018.      of IT Convergence, Chosun University. His research interests include
[207] H. Yang, W.-D. Zhong, C. Chen, and A. Alphones, “Integration             modeling and performance analysis of cellular networks using stochas-
      of visible light communication and positioning within 5G networks        tic geometry, millimeter wave, and terahertz communication, vehicular
      for Internet of Things,” IEEE Netw., vol. 34, no. 5, pp. 134–140,        networks, Internet of Things, 5G and beyond 5G networks, and machine-
      Oct. 2020.                                                               learning-aided wireless communication.
[208] A. Ullah, W. Choi, and S. Coleri, “Path loss estimation and jamming
      detection in hybrid RF-VLC vehicular networks: A machine-learning
      framework,” IEEE Sensors J., vol. 23, no. 24, pp. 31325–31336,
      Dec. 2023.
[209] X. Yuan, Y.-J. A. Zhang, Y. Shi, W. Yan, and H. Liu,
      “Reconfigurable-intelligent-surface empowered wireless communi-                                   WOOYEOL CHOI (Member,              IEEE) received
      cations: Challenges and opportunities,” IEEE Wireless Commun.,                                    the B.S. degree from the Department of
      vol. 28, no. 2, pp. 136–143, Apr. 2021.                                                           Computer Science and Engineering, Pusan
[210] A. Kaushik et al., “Towards integrated sensing and communications                                 National University, Busan, Republic of Korea,
      for 6G: A standardization perspective,” 2023, arXiv:2308.01227.                                   in 2008, and the M.S. and Ph.D. degrees from
[211] Y. Han, W. Tang, X. Li, M. Matthaiou, and S. Jin, “CSI acquisition in                             the School of Information and Communications,
      RIS-assisted mobile communication systems,” Nat. Sci. Rev., vol. 10,                              Gwangju Institute of Science and Technology,
      no. 8, 2023, Art. no. nwad127.                                                                    Gwangju, Republic of Korea, in 2010 and 2015,
[212] J. Hu et al., “Reconfigurable intelligent surface based RF sensing:                               respectively. He is currently an Associate Professor
      Design, optimization, and implementation,” IEEE J. Sel. Areas                                     with the Department of Computer Engineering,
      Commun., vol. 38, no. 11, pp. 2700–2716, Nov. 2020.                                               Chosun University, Gwangju. He was a Senior
[213] A. Aubry, A. De Maio, and M. Rosamilia, “RIS-aided RADAR sens-           Research Scientist with the Korea Institute of Ocean Science and
      ing in N-LOS environment,” in Proc. IEEE 8th Int. Workshop Metrol.       Technology, Ansan, Republic of Korea, from 2015 to 2017, and a Senior
      AeroSpace (MetroAeroSpace), Naples, Italy, 2021, pp. 277–282.            Researcher with Korea Aerospace Research Institute, Daejeon, Republic
[214] L. Li, K. Ota, and M. Dong, “Human in the loop: Distributed deep         of Korea, from 2017 to 2018. His research interests include cross-layer
      model for mobile crowdsensing,” IEEE Internet Things J., vol. 5,         protocol design, learning-based resource optimization, and experiment-
      no. 6, pp. 4957–4964, Dec. 2018.                                         driven evaluation of wireless networks.




VOLUME 5, 2024                                                                                                                                         3623

