This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials

                                                                                                                                                                                                                                 1




                  Wireless Sensing for Human Activity: A Survey
                                                      Jian Liu, Hongbo Liu, Yingying Chen, Yan Wang, Chen Wang


                                                                                                                 Measurements and   Derived Metrics Associated with
             Abstract—With the advancement of wireless technologies and                                          Techniques         Human Movements                     Signal Pre-processing   Applications
          sensing methodologies, many studies have shown the success of                                                RSSI            Signal strength variations                               Intrusion detection
          re-using wireless signals (e.g., WiFi) to sense human activities                                                                                                                      Room occupancy monitoring
          and thereby realize a set of emerging applications, ranging from                                             CSI           Channel condition variations
                                                                                                                                                                         Feature Extraction     Daily activity recognition
          intrusion detection, daily activity recognition, gesture recognition                                                        Frequency shift associated                                Gesture recognition
                                                                                                                     FMCW              with human body depth                                    Vital signs monitoring
          to vital signs monitoring and user identification involving even                                                                                                                      User identification
                                                                                                                                      Frequency shift associated       Prediction via Machine
          finer-grained motion sensing. These applications arguably can                                            Doppler shift      with human body moving          Learning or Model-based   Indoor localization & tracking
          brace various domains for smart home and office environments,                                                                        speed                          Methods

          including safety protection, well-being monitoring/management,
          smart healthcare and smart-appliance interaction. The move-                                           Fig. 1.       Typical workflow of human activity sensing via wireless signal.
          ments of the human body impact the wireless signal propaga-
          tion (e.g., reflection, diffraction and scattering), which provide
          great opportunities to capture human motions by analyzing
          the received wireless signals. Researchers take the advantage                                         infrared (PIR) sensors [4], are deployed to inspect different
          of the existing wireless links among mobile/smart devices (e.g.,                                      human activities and gestures. Motion sensor based approaches
          laptops, smartphones, smart thermostats, smart refrigerators and                                      usually require individuals to wear a specialized device to track
          virtual assistance systems) by either extracting the ready-to-use                                     body motions, which are not always convenient in practice.
          signal measurements or adopting frequency modulated signals to                                        The approaches relying on camera or visible light sensors
          detect the frequency shift. Due to the low-cost and non-intrusive                                     can only work well in the environments under certain light
          sensing nature, wireless-based human activity sensing has drawn                                       conditions, which could be easily interfered by low illumination
          considerable attention and become a prominent research field                                          condition, smoke, or opaque obstructions. Furthermore, the
          over the past decade. In this paper, we survey the existing wireless
          sensing systems in terms of their basic principles, techniques and
                                                                                                                stability of acoustic-based approaches is vulnerable to ambient
          system structures. Particularly, we describe how the wireless                                         noise and surrounding sound interferences, and the sensing
          signals could be utilized to facilitate an array of applications                                      range is also limited due to the fast attenuation of acoustic
          including intrusion detection, room occupancy monitoring, daily                                       signals. Overall, the aforementioned techniques involve extra
          activity recognition, gesture recognition, vital signs monitoring,                                    overhead in terms of complicated hardware installation and
          user identification and indoor localization. The future research                                      diverse maintenance needs. To overcome the aforementioned
          directions and limitations of using wireless signals for human                                        limitations, a low-cost and non-intrusive solution is desirable
          activity sensing are also discussed.                                                                  to capture human body movements involved in their daily
                                                                                                                activities. Recently more and more research work focus on radio
                                                                                                                frequency (RF) (e.g., WiFi) based techniques to perform human
                                          I.    I NTRODUCTION                                                   activity sensing. The prevalence of WiFi technology enables
             With the rapid development of sensing technology over                                              almost every electronics in home/office environments such as
          the past decade, considerable attention has been drawn on                                             smart speakers (e.g., Amazon Echo, Apple HomePod), smart
          human activity recognition to brace a broad range of compelling                                       TV, smart thermostat, and home security system interconnected
          applications, such as human-computer interactions on smart-                                           wirelessly. WiFi signals can usually reach tens of meters of
          home appliances, elder care, well-being management and safety                                         coverage in indoor environments, and the wireless links among
          surveillance. To facilitate these applications, active research                                       these smart devices provides rich web of reflected rays that
          has been conducted to examine human activities through                                                spread every indoor corner. The presence of people and related
          sensing from different perspectives, including pinpointing target                                     body motion will have considerable impact on wireless signals
          person’s positions in an indoor environment, recognizing the                                          and result in significant changes in both amplitude and phase
          regular activities or specific body gestures that the person                                          of the received signals, which can be utilized to capture human
          performed and monitoring his or her vital signs (e.g., breathing                                      body movements involved in their daily activities.
          rate).
                                                                                                                   To quantify the changes of the received WiFi signal,
             To effectively perform human activity recognition, various                                         researchers could measure the physical layer properties over
          sensing technologies, including motion sensors [1], vision-                                           wireless channel such as the received signal strength Indicator
          based sensors [2], acoustic-based sensors [3] and pyroelectric                                        (RSSI) and channel state information (CSI), which are readily
            Jian Liu, Yingying Chen and Chen Wang are with WINLAB, Department
                                                                                                                available on many commercial network interface cards (e.g.,
          of Electrical and Computer Engineering, Rutgers University, Piscataway, NJ                            Intel 5300 NIC [96] and Atheors 9580 NIC [97]) with
          08854. E-mail: {jianliu@winlab.rutgers.edu, yingche@scarletmail.rutgers.edu,                          modified driver software. To pursue more precise sensing,
          chenwang@winlab.rutgers.edu}                                                                          some researchers manipulate the transmitting wireless signals
            Hongbo Liu is with Department of Computer, Information and Technology,                              on universal software radio peripheral (USRP) defined radio
          Indiana University-Purdue University Indianapolis (IUPUI), Indianapolis, IN
          46202. Email:hl45@iupui.edu
                                                                                                                platform, such as Frequency Modulated Carrier Wave (FMCW),
            Yan Wang is with Computer Science Department, Binghamton University,                                to detect the signal’s frequency shift caused by the human
          Binghamton, NY, 13902. E-mail: yanwang@binghamton.edu                                                 motions [28]. Moreover, the Doppler effect is exploited to




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




                                                              TABLE I.           A PPLICATIONS OF W I F I S ENSING FOR H UMAN ACTIVITY.
## Main Techniques
                                          Section #                Applications
                                                                                                       RSSI                      CSI         FMCW               Doppler shift
                                                          Intrusion detection                  [5], [5]–[7]               [7]–[9], [9]–[11] —                  —
                                          Section III
                                                          Room occupancy monitoring            [12]–[14]                  [15], [16]        —                  —
                                                          Daily activity recognition           [17], [17]–[20]            [21]–[27]         [28]               [29], [30]
                                          Section IV
                                                          Gesture recognition                  [31]–[33]                  [34]–[41]         [42]–[44]          [45]
                                          Section V       Vital signs monitoring               [46]–[48]                  [49]–[54]         [55]–[57]          [58]–[66]
                                                          User identification                  —                          [67]–[71]         —                  —
                                          Section VI
                                                          Indoor localization & tracking       [72]–[74], [74]–[83]       [84]–[91]         [55]–[57]          [28], [92]–[95]



          measure the signal’s frequency shift associated with body                                                              II.     T ECHNIQUES FOR W I F I S ENSING
          motions [45], which also needs the support of USRP platforms
          to control the transmission and receiving of wireless signals.                                           For both commodity devices and customized hardware, there
          We will elaborate these techniques in details in Section II.                                          are many physical layer properties that can be extracted over
                                                                                                                wireless channel to facilitate human activity sensing. In this
             Given the WiFi sensing techniques, a broad range of                                                section, we identify four common WiFi sensing techniques
          emerging applications could be supported to improve the                                               based on different physical layer properties, including Received
          quality of people’s lives. In this paper, we investigate the                                          signal strength indicator (RSSI), channel state information
          state-of-the-art WiFi sensing studies on human activity and                                           (CSI), frequency shift for frequency modulated carrier wave
          related applications. We broadly divide these applications into                                       (FMCW), and Doppler shift, as summarized in Table II.
          four categories: intrusion detection & occupancy monitoring,
          activity & gesture recognition, vital signs monitoring and user
                                                                                                                A. Techniques Using Commodity Hardware
          identification & localization. Specifically, intrusion detection &
          occupancy involves the detecting any abnormality (i.e., human                                            Received Signal Strength Indicator (RSSI). Received
          intrusion of a room) and room occupancy monitoring (i.e.,                                             signals are available in most WiFi devices, which indicate
          crowd estimation). Activity & gesture recognition ranges from                                         the path loss of wireless signals with respect to a certain
          daily in-home activity (e.g., walking, cooking and washing                                            distance, and can be derived following Log-normal Distance
          dishes) recognition to relatively smaller body gestures (e.g.,                                        Path Loss (LDPL) model [100]:
          arm/hand/finger/head motions) recognition. Vital signs moni-
          toring refers to detecting breathing and heart rates associated                                                                                                  d
                                                                                                                                       P(d) = P(d0 ) + 10γ log                + Xδ ,                      (1)
          with minute human body vibrations, and user identification                                                                                                       d0
          & localization is using the WiFi-based location fingerprints                                          where P(d) denotes RSSI measurement indicating the path
          for indoor localization and the unique user-specific activity                                         loss at distance d measured in Decibel (dB), P(d0 ) is the path
          behavior for further identity verification. The related work                                          loss at the reference distance d0 , γ is the path loss exponent,
          for each application category will be introduced together                                             and Xδ is a zero-mean normal noise caused by flat fading.
          with their main techniques, which are summarized in Table I.
          Figure 1 shows the typical workflow of the existing human                                                As one of the most representative RSS-based applications,
          activity sensing systems using wireless signals. Specifically,                                        the success of utilizing RSSI to estimate the positions of
          the sensing systems first extract signal changes associated                                           target users with carry-on WiFi devices has been demonstrated
          with human activities based on different sensing methods (e.g.,                                       for a long time [72]. It has also been noticed that the
          RSSI, CSI, FMCW and Doppler shift). Next a series signal pre-                                         existence of human body within the wireless sensing area
          processing procedures (e.g., filtering, denoising and calibration)                                    would cause signal attenuation, leading to the variation of
          are adopted to mitigate the impact of interference, ambient noise                                     RSSI measurements. Thus, RSSI has been widely deployed for
          and system offset. Finally the unique features are extracted and                                      human activity sensing in recent years, for example, device-
          fed into machine learning models to perform human activity                                            free indoor localization [82], [83], [101], room crowd density
          detection and recognition.                                                                            estimation [12], [14], and breathing rate monitoring [46]–[48].
                                                                                                                Although RSSI is easily obtained in any commodity WiFi
             The remainder of this paper is organized as follows. We                                            devices without additional hardware, it can only detect limited
          first review the four key techniques to perform WiFi sensing                                          types of human activities due to the coarse-grained channel state
          in Section II. Next the four categories of WiFi-based human                                           information (i.e, single path loss value per packet). Furthermore,
          activity sensing applications are introduced. Specifically, the                                       It has been shown that the stability of the RSSI is not guaranteed
          studies on intrusion detection and room occupancy monitoring                                          even in a static indoor environment [102], making it unreliable
          is presented in Section III; in Section IV, we review the work                                        in many application scenarios.
          on regular activity and gesture recognition; we study the work                                           Channel State Information (CSI). To achieve accurate and
          on human vital signs monitoring in Section V; and the work                                            reliable human activity sensing, it is essential to capture more
          on user identification and indoor localization and tracking will                                      fine-grained CSI, which represents the combined effect of, for
          be discussed in Section VI. In Section VII, we discuss the                                            example, scattering, fading, and power decay with distance.
          limitations of existing work and the prospects of future WiFi-                                        Since wireless signals could travel through almost any corner
          based human activity sensing. Finally, we conclude the survey                                         in an indoor environment, the presence or movement of a
          of current human activity sensing work leveraging WiFi in                                             human body would alter the propagation of wireless signals,
          Section VIII.                                                                                         resulting in the small changes in multiple reflected rays as




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
                                                                TABLE II.      M AIN TECHNIQUE COMPARISON .
              Techniques                Derived Metric               Granularity           Additional Hardware         Existing Sensing Work
              RSSI-based             Wireless signal strength       Coarse-grained                  No                  [5], [5]–[7], [12]–[14], [17], [17]–[20], [31]–[33], [46]–[48],
                                                                                                                       [72]–[74], [74]–[83]
                                   Channel conditions/properties
              CSI-based                                              Fine-grained                   No                  [7]–[9], [9]–[11], [15], [16], [21]–[27], [34]–[41], [49]–[54],
                                        of wireless links
                                                                                                                       [67]–[71], [84]–[91]
                                    Frequency shift associated
            FMCW-based                                               Fine-grained                  Yes                  [28], [42]–[44], [55]–[57] [29], [30], [45], [98], [99]
                                     with human body depth
                                  Frequency shift associated with
          Doppler Shift-based                                        Fine-grained                  Yes                  [28]–[30], [45], [58]–[66], [92]–[95]
                                    human body moving speed



                                Reflected by ceiling/wall
                                                                                                                                           !" ($) !& ($)
                                                Reflected by                                                  !(
                                                human body


                                                                                                  Frequency
                                                                                                                                       ∆!
                                                                     Router                                                   ∆$
           WiFi device
                                                                                                              !'
                                                                                                                        Sweep 1                               Sweep 2
                                  Reflected by floor
                                                                                                                                               Time
Fig. 2.     Illustration of the multipath effect of wireless signals.
                                                                                                Fig. 3.        Illustration of FMCW operation.


shown in Figure 2. All these multi-path rays contribute to
the measurable CSI values and could be used to detect and                                       wireless signal to travel from the transmitter to the reflecting
track the human body movements. In contrast to RSSI, CSI                                        human body and back to the receiver. However, it would
consists of a set of a complex values, including both amplitude                                 be hard to measure the time of flight (ToF) directly since
and phase information, for multiple orthogonal frequency-                                       wireless signals travel very fast, specifically at the speed of
division multiplexing (OFDM) subcarriers.Each subcarrier with                                   light. Thus, FMCW which maps differences in time to the
slightly different center frequency experiences different multi-                                shifts of carrier frequency is deployed to measure ToF of radio
path fading effects, and all the subcarriers together depict                                    signals. As shown in Figure 3, the carrier frequency of the
the wireless channel in a fine-grained manner. For instance,                                    transmitting wireless signal fx (t) is repeatedly swept across
IEEE 802.11n standard can render the CSI measurements for                                       a specific bandwidth. After reflected from the human body,
52 and 128 subcarriers with 20MHz and 40MHz bandwidth                                           it will introduce a frequency shift ∆ f with the slope k (i.e.,
for each subcarrier, respectively, and the emerging 802.11ac                                    swept bandwidth divided by the sweep time) to the received
standard supports even wider bandwidth. CSI essentially allows                                  signal fy (t), and the time-shift (i.e., ∆t) with respect to the
fine-grained channel estimation, and is expressed as:                                           transmitting signal can be derived based on such frequency
                                                                                                shift as follows:
                  H = [H1 , H2 , ..., Hi , ..., HN ]T , i ∈ [1, N],                  (2)                                          ∆f
                                                                                                                            ∆t =     .                       (4)
                                                                                                                                   k
where N is the number of subcarriers, and Hi can be represented
as:                                                                                             Compared to measuring the ToF directly, it is much easier
                     Hi = |Hi |e j sin(∠Hi ) ,              (3)                                 to measure the frequency shift ∆ f to obtain the ∆t. Then the
                                                                                                round-trip distance of wireless signals (i.e., d = c · ∆ f , and c
where |Hi | is the CSI amplitude at the ith subcarrier, and ∠Hi                                 is the speed of light) can be obtained to describe the distance
denotes its phase. Similar to RSSI, CSI measurements can                                        of the human body relative to the transmitter and receiver. It
be obtained at any devices with off-the-shelf WiFi interfaces                                   is important to note that, in contrast to off-the-shelf WiFi that
(e.g., Intel 5300 NIC [96] and Atheors 9580 NIC [97]) with                                      uses OFDM, FMCW technique relies on specialized device
modified driver. Now it has been widely adopted by more and                                     (e.g., USRP) to generate the signal that sweeps the frequency
more researchers to perform human activity sensing, such as                                     across time.
human intrusion detection, walking speed/direction estimation
                                                                                                   A number of wireless sensing systems leveraging FMCW
and human activity recognition [21], [22].
                                                                                                technique have been developed to track different human
                                                                                                activities. For instance, the researchers utilize FMCW signals
B. Techniques Using Customized Hardware                                                         generated by USRP software radio with directional antennas
                                                                                                to capture human figure through a wall [103], track user’s 3D
   Frequency Modulated Carrier Wave (FMCW). The hu-                                             motion [28], estimate gait velocity and stride length [104],
man activities can also be captured based on radio reflections                                  detect vital signs [56], monitor sleep and insomnia [105], and
off her body, specifically by estimating the time it takes the                                  recognize people emotions [106].
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




                                                                                                               The RSSI-based and CSI-based intrusion detection methods
                                                                                                               are investigated.
                                                                                                                  RSSI-based Detection. RSSI-based methods primarily infer
                                                                       Speed v                                 intruders through detecting human disturbances to RSSI
                                                                                                               measurements in WiFi networks. When an intruder enters the
                                                                      !                                        sensing area, WiFi links would be disrupted due to the presence
                                                                                                               or body motions of the intruder, resulting in the RSSI changes
                                                                                                               of radio signals. Inspired by such phenomenon, the concept
                                                                   Reflected by hand                           of device-free passive detection using WiFi was first proposed
                                                                                                               in [5], which facilitates intrusion detection leveraging time-
          Fig. 4. Illustration of Doppler shift when a hand is moving towards a WiFi                           series analysis on the RSSI readings like the moving average
          device.                                                                                              and moving variance techniques. Following the work [5], Ikeda
                                                                                                               et al. [110], [111] leverage a threshold of RSSI fluctuation
                                                                                                               width, the difference between the RSSI when event occurs
             Doppler Shift. Doppler shift effects is another physical layer                                    and the average of RSSI observed in advance in static state,
          property of wireless signals that can be used to perform human                                       to identify intrusion. Other than the work [110], Moussa and
          activity sensing. Specifically, it measures the frequency change                                     Youssef [6] later present an alternative algorithm, based on the
          of the received wireless signal as the transmitter and the receiver                                  maximum likelihood estimator (MLE), to achieve better detec-
          move to each other. If we consider the received wireless signal                                      tion performance in real environments. RASID [7] develops
          reflected from the human body as the signal emitted from                                             a non-parametric statistical anomaly detection technique with
          the wireless transmitter, any movements of the human body                                            adaptive environment-dependent profile updating to achieve
          would result in a Doppler shift. Specifically, positive frequency                                    accurate and robust intrusion detection. In contrast to the
          change (i.e., Doppler shift) is produced if the person moves                                         aforementioned techniques, RASID has significantly lower
          towards the receiver, while negative frequency change occurs                                         overhead than MLE technique while maintaining comparable
          if the person departs from the receiver. As shown in Figure 4,                                       detection performance. In addition, RASID is more robust to
          when an object (e.g., hand) moves at the speed v along the                                           temporal changes of training profiles as compared to other
          direction θ with respect to the receiver, it will result in a                                        existing intrusion detection systems.
          Doppler shift [107] as:
                                                                                                                  CSI-based Detection. Due to the fine-grained wireless
                                     2v cos(θ )                                                                channel measurement, CSI recently becomes a popular and
                                            ∆f =f,                  (5)                                        powerful tool for intrusion detection system design. Nishi-
                                         c
                                                                                                               mori et al. [112] measure the influences of antenna arrangement
          where c is the speed of light and f is the center frequency
                                                                                                               on radio signal propagation in indoor environments, and then
          of wireless signal. Leveraging Doppler shift effects, some
                                                                                                               utilize the channel matrix in MIMO channels to detect intrusion.
          WiFi sensing systems are developed based on software defined
                                                                                                               Hong et al. [113] further extract eigenvectors to achieve
          radio device (e.g., USRP N210) to detect walking [30], [98],
                                                                                                               intrusion detection with higher accuracy. Moreover, Honma et
          running [29] and human body/hand gestures [45], [99].
                                                                                                               al. [114] propose the antenna arrangements for the MIMO
                                                                                                               interference to provide better intrusion detection performance.
               III.      I NTRUSION D ETECTION & ROOM O CCUPANCY                                               FIMD [115] realizes device-free motion detection by leveraging
                                     M ONITORING                                                               the eigenvalues of a CSI-based correlation matrix in a given
                                                                                                               time period. Pilot [8] leverages the correlation of CSI over
             In this section, we introduce the existing studies on the                                         time to monitor abnormal appearance and further locate the
          room-level human activity sensing with WiFi signals, including                                       entity. Moreover, PADS [9] and DeMan [116] further extract the
          human intrusion detection and room occupancy monitoring.                                             maximum eigenvalues of the covariance matrix from successive
          We particularly focus on RSSI-based and CSI-based methods                                            full CSI information, including both amplitude and phase,
          leveraging the commodity devices.                                                                    to enhance detection performance. Ding et al. [10] explore
                                                                                                               phase difference between adjacent antenna pairs for passive
                                                                                                               device-free motion detection. Additionally, OmniPHD [11]
          A. Human Intrusion Detection
                                                                                                               achieves the omnidirectional sensing coverage for passive
             As an important security issue, human intrusion detection                                         human detection in typical multipath-rich indoor scenarios. The
          has drawn considerable attention in recent years. Traditional                                        aforementioned studies mainly rely on the characteristic from
          methods mainly rely on cameras (e.g., closed-circuit television                                      matrix of CSI amplitude, phase or phase difference to detect
          (CCTV) or Internet protocol (IP) cameras [108], [109]) or                                            the sudden changes associated with human intrusion. Compare
          dedicated sensors (e.g., acoustic sensor [3] or infrared (IR)                                        to RSSI-based methods, CSI-based method can achieve more
          sensor [4]) to perform intrusion detection. However, camera-                                         accurate and reliable intrusion detection performance.
          based approaches are difficult to detect an intrusion event
          under low illumination condition or without LoS view, while                                           B. Room Occupancy Monitoring
          the sensor-based approaches usually require complex hardware
          installation and diverse maintenance needs. To reduce the im-                                           Room occupancy monitoring plays a critical role in serving
          plementation/maintenance overhead, researchers take advantage                                         various purposes including public area surveillance, energy
          of existing WiFi infrastructure to perform intrusion detection.                                       saving (e.g., controlling lights and air-flow rate) and hotspot




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




                                                    TABLE III.          A COMPARISON OF EXISTING ROOM OCCUPANCY MONITORING STUDIES .
                        Work                                 Technique                 Frequency Band                      Number of People           Accuracy
                        Nakatsuka et al. [12]                RSSI                      2.4GHz                              23-29                      N/A
                        Yuan et al. [13]                     RSSI                      2.4GHz                              10                         94%
                        Xu et al. [14]                       RSSI                      2.13GHz                             4                          86%
                        Xi et al. [16]                       CSI                       2.4GHz, 5GHz                        4                          83%
                        Guo et al. [15]                      CSI                       2.4GHz                              6                          98% estimation errors are less than 2
                                                                                                                                                      persons in indoor environment




          Fig. 5. RSSI readings when there are different number of people in a room                             Fig. 6. CSI amplitude difference between two antennas under different
          when people are not moving around [13].                                                               number of subjects in a room [15].


                                                                                                                (i.e., 0, 3 and 12) in a room, indicating the aforementioned
          tracking in multi-functional room management, etc. Existing                                           relationship between people density and RSSI readings. A set of
          studies [117], [118] mainly rely on surveillance camera to                                            studies [12]–[14] conduct a large scale deployment of wireless
          inspect human flow, but the high deployment costs and privacy                                         sensors in indoor environments and infer the number of moving
          concerns prevent them to be deployed in large-scale. Moreover,                                        people leveraging RSSI from multiple wireless links. However,
          some other studies infer people density based on the number                                           these approaches need a large number of wireless nodes or
          of detected devices. For instance, the number of connected                                            devices to create dense RF links, resulting in extremely high
          mobile devices via Bluetooth [119] and microphone/speaker                                             cost and complex maintenance efforts.
          pair [120] are estimated to derive the people density. However,
          the aforementioned approaches require the users to carry the                                             CSI-based Approaches. Similar to RSSI-based solutions,
          mobile devices running with specific applications, making                                             the variation of CSI measurements can also be extracted to
          them not always applicable in practice. Differently, device-free                                      infer the number of walking people in an indoor environment.
          approaches rely on existing WiFi infrastructure to perform                                            As mentioned before, CSI provides more fine-grained channel
          room occupancy monitoring without requiring people to carry                                           information (i.e., both amplitude and phase information) with
          additional devices. Specifically, we will investigate both RSSI-                                      multiple subcarriers. Figure 6 shows the impact of different
          based and CSI-based methods as follows. A comparison of                                               number of subjects (i.e., no person, 1 person, 3 persons
          these solutions for room occupancy monitoring is summarized                                           and 5 persons) on CSI amplitude differences across 30
          in Table III.                                                                                         subcarriers [15]. It is obvious to find that more people could
                                                                                                                induce a higher CSI variance over WiFi links. Inspired by this
             RSSI-based Approaches. It is well known that RSSI                                                  observation, Xi et al. [16] theoretically studied the relationship
          changes when a subject approaches the LoS of a wireless                                               between the number of moving people and the variation of
          link [5], [19]. Existing studies [12]–[14] also verified more                                         wireless CSI. A stable monotonic function is formulated to
          subjects in a room will make an even greater impact on the                                            characterize the relationship between the crowd number and
          surrounding wireless environment. To facilitate room occupancy                                        various features of CSI (i.e., Percentage of nonzero Elements
          monitoring, the researchers empirically conclude that: (1) When                                       (PEM) in the dilated CSI matrix). In addition, Guo et al. [15]
          no subject in the area of interest, the RSSI values stay at a                                         propose a comprehensive human flow management system
          stable level; (2) When some subjects enter the sensing zone, the                                      leveraging existing WiFi traffic to estimate crowd counting,
          RSSI reading of some RF links would decrease dramatically;                                            people density, walking speed and direction. Different from
          and (3) The more the number of subjects, the more the radio                                           the previous studies [16], [69], the proposed system adopts
          links are affected, resulting in significant drops on RSSI                                            a robust semi-supervised learning approach for estimation of
          readings. Figure 5 shows the collected RSSI readings from a                                           the number of participants, which can be easily extended to a
          specific wireless link when there are different number of people                                      new environment. They also propose to utilize CSI variance




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




          Fig. 7. Histogram of CSI amplitudes on a particular subcarrier when a person                          Fig. 8.     Similar CSI amplitude time series pattern for same walking
          is cooking and sleeping, respectively [21].                                                           trajectory [21].


          histogram to estimate human density distribution within a                                             fluctuation of RSSI of WiFi signal caused by human movements.
          specific region.                                                                                      Specifically, Sigg et al. [17] extract 17 empirical features (e.g.
                                                                                                                highest signal peak and median signal strength) from RSS
                       IV.     ACTIVITY & G ESTURE R ECOGNITION                                                 signal and utilize k nearest neighborhood (KNN) classifier to
                                                                                                                recognize four regular activities (i.e., lying, standing, walking
             Human activity recognition is the key technology to support                                        and crawling). To further improve the environmental sensing
          a broad array of applications including human-computer                                                generosity of RSSI-based system, Sigg et al. [18] focus on the
          interaction (HCI), elder care, well-being management and                                              detection of static and dynamic activities of single individuals
          security monitoring fields, etc. Traditionally, it mainly relies                                      by using active or passive systems and further recognize four
          on dedicated sensors, such as wearable devices [121] or                                               regular activities (i.e., lying, standing, walking and crawling).
          cameras [122]. However, wearable-based methods require users’                                         Particularly, the active system employs dedicated transmitter
          active participation (e.g., wearing sensor devices) and have                                          hardware as a part of the system while the passive system
          limited sensing capability, while camera-based approaches                                             solely uses ambient FM radio. In addition, radio tomographic
          usually raise privacy concerns, making them inapplicable                                              imaging (RTI) [19] is also an effective way to perform RSS-
          in personal areas. Compared to traditional human activity                                             based device-free motion tracking, which deploys a wireless
          recognition approaches, RF-based solutions are device-free                                            sensor network around the interesting area and uses the raw
          without incurring potential privacy issues (i.e., capturing                                           RSS measurements to image the moving targets. Wilson and
          unnecessary and sensitive information). Generally, human                                              Patwari also proposed vRTI [20], an extension of the RTI
          activity can be divided into two main categories, regular                                             technique, by leveraging the motion-induced variance of RSS
          activities (e.g., daily activity and abnormal body motion) and                                        measurements for better activity recognition.
          gestures (e.g., hand/finger gesture and head motion). We will
          discuss the related research on human activity recognition with                                          CSI-based Recognition. Due to the low-resolution and
          respect to the above two categories.                                                                  limited sensing capability of RSSI measurements, it is difficult
                                                                                                                to achieve fine-grained activity recognition. Therefore, recent
                                                                                                                studies propose to exploit CSI measurements for better recog-
          A. Activity Recognition                                                                               nition performance. Wang et al. [21] propose the first work,
                                                                                                                E-eyes, to explore using fine-grained CSI to recognize daily
             Regular activity refers to the daily in-home activity (e.g.,                                       activities. Particularly, E-eyes seeks to utilize the relationship
          walking, sitting, cooking and watching television). By tracking                                       between location and activity characteristics to develop a
          a sequence of such meaningful activities of a person, it is                                           location-oriented activity identification system to distinguish a
          possible to suggest a healthier daily routine change towards                                          set of in-place (e.g., cooking, washing dishes, bathing, studying,
          health improvement. Additionally, it also benefits many other                                         eating and sleeping) and walking activities (i.e., walking from
          domains such as elder-care, latchkey child safety, etc. Specif-                                       one room to another) with only a single WiFi access point.
          ically, four types of WiFi-based regular activity recognition                                         For instance, the authors showed the similarity levels of the
          approaches are reviewed as follows.                                                                   CSI amplitude distribution for the same and different in-
             RSSI-based Recognition. Wireless signals are easily af-                                            place activity (i.e., cooking in a kitchen and sleeping on a
          fected by surrounding body movement that associated with                                              bed) respectively at a particular subcarrier in Figure 7. When
          human activities, resulting in a special fluctuation pattern                                          cooking, the histogram of CSI amplitude mainly ranges from
          on RSSI. Each specific activity has its particular way to be                                          9 to 12, whereas the histogram while sleeping mainly ranges
          conducted by human, it is thus possible to induce a unique                                            from 11 to 16. Furthermore, regarding the large-scale body
          RSSI fingerprint on the RF-signals, which can be captured                                             movements (i.e., walking), CSI measurements exhibit similar
          by nearby wireless receivers. Sigg et al. [17], [18] propose a                                        changing patterns for the same trajectory, whereas the changes
          device-free human activity recognition system by leveraging the                                       of CSI measurements over time are different for different




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




          trajectories, which is shown in Figure 8. This observation
          validates that the CSI measurement from WiFi signals is
          dominated by the specific in-place activity or unique path of the
          walking activity, and it thus is a good alternative for recognizing
          regular daily activities. However, the aforementioned system
          (i.e., [21]) is based on empirical study, and lacks the theoretical
          support explaining the relationship between CSI measurements
          and human activities. Therefore, Wang et al. [22], [23] propose
          a human activity recognition system, named CARM, which
          builds CSI-speed model and CSI-activity model to quantify the
          correlation between the movement speeds of different human
          body parts and a specific human activity. The proposed system
          can work in both trained and untrained environments, in which                                         Fig. 9. WiTrack automatically detects falls by monitoring the absolute value
          a large set of daily activities (e.g., walking, running, opening                                      and the change in elevation [28].
          refrigerator, falling and boxing) are evaluated.
             In addition to recognizing human daily activities, abnormal                                        which capture the minute changes in the WiFi signals caused
          human motion detection (e.g., falling down) is also important,                                        by human motion such as running [29], walking forward and
          especially for timely elder-care. WiFall [24] is the first CSI-                                       backward [30]. Chetty et al. [29] build a passive WiFi radar
          based fall detection system. In order to achieve reliable fall                                        running on USRP platform to measure the Doppler shifts caused
          detection, WiFall constructs the radio propagation model to                                           by the human activities through the wall. Adib et al. [30]
          analyze the time variability and special diversity of CSI and                                         later improve the through-the-wall system by using MIMO
          trains a support vector machine(SVM) classifier to differentiate                                      interference nulling to eliminate the flash effect of Doppler
          fall from other human motions (i.e., walk, sit and stand up).                                         shifts and render more accurate recognition performance.
          To further enhance the performance of CSI-based fall detection                                        Additionally, Okamoto et al. [123] use the temporal phase
          system, Zhang et al. [25] propose Anti-Fall that uses both the                                        shift obtained from the moving target in addition to MIMO
          phase and amplitude of CSI readings to accurately detect the                                          interference to measure the relative velocity between the target
          fall from other fall-like activities. Moreover, Wang et al. [26]                                      and the antenna. Okamoto et al. [124] further utilize bistatic
          find that the CSI phase difference over two antennas is more                                          radar model based on MIMO scheme to classify various human
          sensitive to fall action. Also, they find the unique sharp decline                                    activities and track multiple targets. Later work [125], [126]
          pattern of fall action in the time-frequency domain and first                                         build antenna array to measure the Doppler Shifts caused by
          propose to utilize the frequency-based features to detect fall                                        the daily movement of elder people (i.e., falling down on the
          accurately. Similarly, Palipana et al. [27] propose FallDeFi that                                     floor after standing, sitting on the chair after standing).
          extracts time-frequency features in CSI using the conventional
          Short-Time Fourier Transform (STFT) to achieve accurate
          fall detection. To ensure the fall detection system resilient to                                      B. Gesture Recognition
          environmental changes, the authors [27] also devise a sequential                                         Human gestures such as arm/hand movements, head motion
          forward selection algorithm to single out the robust features.                                        and even finger motion are important interaction interfaces
             FMCW-based Recognition. In addition to the aforemen-                                               to smart Internet of Things (IoT) and mobile devices. In this
          tioned RSSI and CSI based approaches that can leverage off-                                           section, we review four main WiFi-based gesture recognition
          the-shelf wireless devices, there are also some existing work                                         technologies (i.e., RSSI, CSI, FMCW, and Doppler shift).
          relying on USRP platform to facilitate activity recognition.                                          The existing gesture recognition systems are summarized in
          These methods precisely modulate the transmitting wireless                                            Table IV.
          signals to sweep across a certain frequency band (e.g., FMCW                                             RSSI-based Recognition. Early gesture recognition systems
          radio) and then derive ∆t measurements based on the reflected                                         mainly rely on RSSI extracted from off-the-shelf devices
          signals. Due to the super-heterodyne based architecture of                                            to identify different hand gestures. Sigg [31] examine the
          FMCW radio, the ∆t measurements delivers good sensitivity                                             fluctuation in RSSI from the mobile phone to identify 11
          and stability on activity recognition. WiTrack [28] is one of the                                     different hand gestures, but the recognition accuracy is as
          precursory FMCW-based activity recognition system, which                                              low as 51.0%. To eliminate the environmental effects of RSSI,
          leverages the radio signals reflected off human body to track the                                     Melgarejo et al. [32] take advantage of directional antennas and
          3D motion of the user. By leveraging the T shape directional                                          short-range wireless propagation properties and achieve higher
          antenna array, WiTrack can localize the center of a human                                             recognition accuracy with 25 hand gestures. The proposed
          body in a 3D domain. It can also coarsely track body parts,                                           gesture recognition system has been successfully applied to
          such as identifying the direction of a pointing hand with a                                           gesture-based electronic activation from wheelchair and gesture-
          median of 11.2°. Additionally, WiTrack can distinguish a fall                                         based control of car infotainment system. Abdelnasser et
          action from other activities (e.g., standing, walking, sitting on                                     al. [33] devise WiGest that further improves the recognition
          a chair and sitting on the floor) by monitoring the absolute                                          accuracy of 8 hand gestures to 96%. The wavelet techniques
          Z-axis value and the change in elevation as shown in Figure 9.                                        are adopted to eliminate the environmental interferences and
                                                                                                                ambient noises from the RSSI measurements. Also, WiGest
            Doppler-based Recognition. Human activity recognition                                               requires no training efforts and works well in none-line-of-
          can also be achieved by leveraging Doppler effects [29], [30],                                        sight scenario. However, due to the coarse granularity and the




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




                                                        TABLE IV.            A COMPARISON OF W I F I - BASED GESTURE RECOGNITION WORKS .
                                             Work                          Technique          Gesture                                                            Accuracy
                                             Sigg [31]                     RSSI               11 hand gestures                                                   51%
                                             Melgarejo et al. [32]         RSSI               25 hand gestures                                                   92%
                                             Abdenasser et al. [33]        RSSI               8 hand gestures                                                    96%
                                             Nandakumar et al. [34]        RSSI, CSI          4 arm gestures                                                     91%
                                             WiG [127]                     CSI                4 arm gestures                                                     92%
                                             Virmani et al. [35]           CSI                6 arm gestures                                                     91.4%
                                             WiDraw [128]                  CSI                Hand trajectory for drawing letters, words, and sentences          91%
                                             Li et al. [36]                CSI                9 finger gestures                                                  90.4%
                                             SignFi [37]                   CSI                276 head, arm, hand and finger gestures                            94.81%
                                             WiCatch [38]                  CSI                9 two-hand gestures                                                95%
                                             Ali et al. [39]               CSI                Keystroke recognition                                              93.5%
                                             Fang et al. [41]              CSI                5 hand and mouth gestures                                          86.3%
                                             Wang et al. [40]              CSI                9 mouse movements                                                  91%
                                             Adib [42]                     FMCW               Hand gestures of multiple people simultaneously                    95%
                                             Soli [43]                     FMCW               4 hand gestures                                                    92.1%
                                             WiSee [45]                    Doppler shift      9 arm/leg involved gestures                                        94%




          high sensitivity of RSSI to environmental changes, RSSI-based                                         wearable WiFi system instead of off-the-shelf WiFi device to
          gesture recognition systems have no ability to capture more                                           capture the head gestures. In contrast, Wang et al. [40] leverage
          fine-grained gestures (e.g., finger gestures, keystrokes, mouth                                       off-the-shelf WiFi to recognize the mouth movements by using
          movements).                                                                                           partial multi-path effects derived from the CSI measurements.
             CSI-based Recognition. To further improve the recognition                                             FMCW-based Recognition. In addition to WiFi-based
          accuracy and capture more subtle motion, the fine-grained CSI                                         gesture recognition systems, FMCW radar have also been
          information becomes prevalent for gesture recognition [34]–                                           applied to gesture recognition [42]–[44]. FMCW radar takes
          [41]. Nandakumar et al. [34] propose to leverage both RSSI                                            up to 1.79 GHz bandwidth compared to 20 MHz bandwidth of
          and CSI information to recognize arm movements, and it can                                            WiFi devices, so it can achieve much higher time resolution
          achieve 91.0% accuracy with respect to four arm gestures                                              on gesture recognition. Adib et al. [42] propose the first multi-
          (i.e., right, left, push, pull). In comparison, WiG [127] is                                          person gesture tracking system with FMCW radar, which
          an arm gesture recognition system solely relying on CSI.                                              is able to recognize the hand gestures of multiple people
          The recognition accuracy of WiG is up to 92% in line-of-                                              simultaneously. In addition, due to the high-resolution and great
          sight scenario and 88% average accuracy in none-line-of-sight                                         robustness of FMCW radar, FMCW-based gesture recognition
          scenario. However, both the above two systems [34], [127]                                             systems are on their way to commercialization. In 2016, Google
          work effectively only under consistent setup (i.e., stand at the                                      proposes a public project Soli [43] aiming to develop a robust,
          same position with same orientation) during training and testing                                      high-resolution gesture recognition system for human-computer
          phases. To combat such limitation, Virmani et al. [35] propose                                        interaction based on FMCW radar. NVIDIA also develops
          WiAG to recognize user’s arm gestures with different positions                                        a short-range FMCW radar-based system for sensing hand
          and orientations, which largely improve the practical usability.                                      gestures for intelligent driver assistance systems [44].
          The key idea behind WiAG is to convert the training samples to                                           Doppler-based Recognition. As a Doppler-based gesture
          the virtual samples for all gestures in all possible configurations                                   recognition system, WiSee [45] successfully recognize 9
          through the proposed gesture translation function. In addition                                        arm/leg involved gestures based on the unique Doppler shifts
          to the regular hand gesture recognition, WiDraw [128] can                                             profile extracted from wireless signals as shown in Figure 10.
          continuously track the hand’s trajectory to enable in-air drawing                                     Due to the different relative body movements to the wireless
          by using the Angle-of-Arrival (AoA) estimation with CSI.                                              radar sensor, we can observe unique positive and negative
             Instead of tracking the whole hand, Li et al. [36] proposes                                        Doppler shift pattern of these arm/leg gestures. A proof-of-
          WiFinger to recognize 9 finger gestures of American Sign                                              concept prototype using USRP-N210s is evaluated in both
          Language with the accuracy as high as 90.4%. WiFinger enables                                         office and apartment environment, and the experimental results
          continuously input text in off-the-shelf WiFi environment to                                          indicate WiSee can achieve the average recognition accuracy
          facilitate human-computer interaction. SignFi [37] further ex-                                        as high as 94%.
          ploits CSI measurements to recognize sign language involving
          the head, arm, hand, and finger gestures. The system extends the
          recognizing ability to 276 sign gestures by using Convolutional                                                             V.     V ITAL S IGNS M ONITORING
          Neural Network (CNN). Moreover, WiCatch [38] is developed                                                Vital signs (i.e., breathing and heart rates) and biometric
          to detect two-hand gestures by constructing the virtual antenna                                       statistics are important indicators for evaluating one’s sleep
          array based on CSIM samples in time domain.                                                           quality, stress level and health conditions. Traditional ap-
             To push the limit of more subtle gestures recognition, Ali                                         proaches, such as camera-based (e.g., DistancePPG [129])
          et al. [39] propose a CSI-based keystroke recognition system,                                         and sensor-based (e.g., Geophone [130], [131]) methods, could
          named WiKey, which can capture more fine-grained variations                                           accurately track vital signs. However, these approaches either
          in CSI values to recognize different keystrokes. Moreover, Fang                                       need to work under bright lighting condition or require complex
          et al. [41] propose HeadScan to recognize the head and mouth                                          installation and maintenance efforts. Differently, RF-based
          gestures including eating, drinking, coughing and speaking.                                           approaches become more appealing due to their low-cost,
          However, the usability of HeanScan is restricted by using a                                           contact-free, easy-to-deploy properties. Leveraging the main




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




          Fig. 10. Unique positive and negative Doppler shifts corresponding to each
          gesture [45].

                                                                                                                Fig. 11. Mean-removed RSS signal for the basic and breakpoint methods [47].
          techniques discussed in Section II, four different vital sign
          monitoring system, RSSI-based, CSI-based Dopper-based and
          FMCW-based, are reviewed as follows.
             RSSI-based Recognition. Many existing studies observed
          that even the minute body movements associated with breathing
          and heartbeat would impact the wireless channel, resulting in
          the fluctuated RSSI readings. Inspired by such observation,
          Kaltiokallio, Ossi Johannes et al. [46] measure RSSI from 16
          frequency channels in IEEE 802.15.4 wireless sensor network to
          detect the user’s breathing rate. Consider the interferences from
          other body motions, N. Patwari et al. [47] defined "breakpoints"
          to indicate the sudden changes of RSSI signal caused by the
          user’s motion interference (e.g., a person rolls over in bed or
          moves a foot) and apply appropriate mean removal to ensure
          the breathing rate estimation more robust to motion interference.
          Figure 11 compares the RSSI signals of four links obtained
          from basic method (top) and breakpoint method (bottom). The
          green-dot areas are the estimated breakpoints, showing the
          breathing rate estimation with breakpoint method is more                                              Fig. 12. CSI amplitude measurements of four subcarriers when a person is
          robust to motion interferences. However, the above approaches                                         in asleep [51].
          usually require additional wireless network infrastructure with
          high-density placement of sensor nodes. BreathTaking [132]
          model the breathing signals as sinusoidal waveforms and apply                                         recognize a diverse set of human activities while estimating
          the maximum likelihood estimation (MLE) to estimate the                                               the user’s breathing rate, by analyzing the CSI captured by
          breathing rate based on the RSSI measurements collected on                                            two designed wearable devices on the user’s hip and wrist.
          around 20 wireless links. Additionally, UbiBreath [48] can                                            WiCare [52] utilizes CSI of WiFi signals to monitor breathing
          achieve accurate estimation of user’s breathing rate with the                                         rate with the coexistence of some micro-motions (e.g., reading,
          error less than 1 breaths per minute (bpm) and also detect                                            writing, using the phone). Specifically, WiCare is able to
          apnea with more than 96% accuracy.                                                                    distinguish micro-motions of a specific individual from his/her
             CSI-based Recognition. Due to the low granularity, RSSI-                                           breathing based on the fact that breathing results in the CSI
          based approaches usually rely on redundant dimensions (i.e.,                                          fluctuation with a much narrower frequency band compared to
          multiple wireless links from various devices) to capture minute                                       micro-motions. PhaseBeat [53] leverages CSI phase differences
          movement related to vital signs. Toward accurate vital sign                                           between two receiving antennas on WiFi devices [133] to
          estimation with less complex infrastructure, many studies turn                                        monitor breathing rate and heart rate in real time. Along with
          to CSI signals for detecting subdued actions. Liu el al. [49],                                        this direction, Wang et al. [54] further verify the feasible
          [50] re-use existing WiFi network to track the breathing and                                          condition (e.g., user’s relative location and orientation) to
          heartbeat concurrently without requiring dedicated/wearable                                           perform breathing estimation with extensive experimental
          sensors or additional wireless infrastructure. Figure 12 shows                                        studies. The proposed system employs Fresnel zone model
          the CSI amplitude of four subcarriers extracted from a laptop 3-                                      to explore the feasibility of breathing rate detection based on
          meter-apart away from a sleeping person. The proposed device-                                         one’s breathing depth, location and orientation.
          free approach has the potential to be widely deployed in home                                            FMCW-based Recognition. Doppler-based vital sign recog-
          and many other non-clinical environments. BodyScan [51] can                                           nition approaches present good performance under some




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




                                                                                                                Fig. 14. Received signal when doppler radar beams to human heart location
                                                                                                                without and with occlusion scenario [64].

          Fig. 13.     FMCW phase changes due to breathing and hearbeat [56].



          specific circumstances, however, it does not have a good way to
          eliminate the influence of moving objects in the front or behind
          the target. Since FMCW radar can separate the radio signal
          reflections from different objects, Anitori et al. [55] propose
          to detect breathing and heartbeat leveraging 9.6 GHz FMCW
          radar signal. Vital-Radio [56] uses FMCW radar to separate the
          reflections from different objects as different buckets depending
          on the distance between these objects and the device. The                                             Fig. 15.    CSI Spectrogram with human walking [69].
          system could differentiate multiple users and track their vital
          signs simultaneously. As shown in Figure 13, breathing causes
          the variation on FMCW radar signal phase, where peaks and                                                        VI.     U SER I DENTIFICATION & L OCALIZATION
          valleys correspond to exhale and inhale periods, respectively.
          Moreover, heartbeats are modulated on the top of the breathing                                           Due to the inherent behavioral and physiological differences
          motion. Zhang at al. [57] demonstrate that for the FMCW-based                                         existed among different people, researchers have demonstrated
          approach, the breathing signal’s harmonics may overwhelm                                              the possibility to perform user authentication by characterizing
          the heartbeat signal, making the latter invisible in the spectral                                     the wireless signal affected by human activities. Such device-
          analysis sign. Therefore, they propose to suppress unnecessary                                        free approaches are low-cost and easy-to-deploy leveraging
          periodic fluctuation component with a projection matrix.                                              the prevalent WiFi signals made available by IoT devices (i.e.,
                                                                                                                smart refrigerator, smart TV and thermostat, etc.), and the
             Doppler-based Recognition. Doppler radar is notable on                                             privacy of users are also preserved. Additionally, localizing
          low-power, cost-effective and robust on longer distance, low                                          users or devices in an indoor space, such as an office building
          visibility, and through-wall detections [134]. SleepMinder [58]                                       or a mall, has attracted significant attention in the past decades.
          implements a radio-frequency Doppler radar system to capture                                          In this section, we will review the related work on user
          physiological movements in the form of phase modulation.                                              identification as well as indoor localization using WiFi signals.
          Passive radar system [59] extract breathing rate based on micro
          Doppler derived from cross ambiguity function (CAF) [135].
          Another critical issue of Doppler-based approaches is that                                            A. User Identification
          the noise produced by random body movement influence the
          monitoring accuracy. Figure 14 shows the difference of received                                         WiFi-based user identification approaches primarily rely
          Doppler radar signals with and without occlusion scenario.                                           on CSI to capture the unique physiological and behavioral
          Salmi, Jussi, Olli Luukkonen, and Visa Koivunen. [60] show                                           characteristics inherited from people’s daily activities (e.g.,
          that nonlinear (arctan, or phase) demodulation combined with                                         human gait pattern) to discriminate people. We review the
          proper offset estimation could give good performance only                                            CSI-based approaches as follows. These approaches are also
          if the radar presents close tA set ofo user’s chest. Several                                         summarized in Table V.
          following studies [61]–[63] introduce signal demodulation                                               CSI-based. Existing studies [67]–[69] perform user identifi-
          methods and mutually injection-locked SIL radars to cancel                                           cation by capturing the unique walking gait pattern based on
          the influence of random body movement. WiSpiro [64] exploit                                          the CSI measurements. Specifically, Zhang et al. [67] extract
          2.4 GHz Doppler radar to capture the breath volume based                                             10 representative features from CSI variations caused by human
          on phase-motion demodulation algorithm, which eliminate the                                          walking to uniquely identify each individual among a group of
          impact from body movement. Other than CW Doppler radar,                                              2 to 6 people. Zeng et al. [68] propose to identify a person’s
          Zhao, Heng et al. [65] employ digital-IF Doppler radar [66]                                          steps and walking gait for user identification leveraging the
          to further improve the performance on vital sign recognition                                         CSI amplitude features, but it requires the human subject to
          with its high sensitivity and low power design.                                                      walk along a path with a distance of 1 meter parallel to the LoS




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




                                                          TABLE V.           A COMPARISON OF W I F I - BASED USER IDENTIFICATION WORKS .
                Work                   Technique       Frequency Band          Accuracy                                                        Activity                                        Distance
                Zhang et al. [67]      CSI             2.4GHz/5GHz             93% for 2 subject, 77% for 6 subject                            Human walking                                   2m
                Zeng et al. [68]       CSI             2.4GHz                  92% for 2 subject, 80% for 6 subject                            Steps and walking gait                          2-3m
                Wang et al. [69]       CSI             5GHz                    79.28% for top-1, 89.52% for top-2, 93.05% for top-3            Movement speed of different body parts          6m
                WFID [70]              CSI             N/A                     91.9% for 9 subjects, 93.1% for 6 subjects                      Standing, marching and walking                  3.6m
                Shi et al. [71]        CSI             5GHz                    94% for walking, 91% for stationary activities                  Walking and stationary activities               10m




          path between the WiFi transmitter and receiver. Additionally,
          Wang et al. [69] examine the moving speed changes of different
          body parts, e.g., torso and legs, from the spectrogram, as shown
          in Figure 15 and correlates the movement speed of different
          body parts with WiFi spectrogram, which are exploited to
          recognize the gaits from different users at a distance of more
          than 6 meters to the LoS path. However, these approaches
          are limited to walking people either following well-designed
          paths (e.g., clear LoS path between the WiFi devices) or
          moving near the WiFi transceivers. Moreover, WFID [70]
          performs device-free user authentication via characterizing the
          uniqueness of subcarrier-amplitude frequency (SAF) from CSI
          measurements when the users are standing, marching, and
          walking. Different from the aforementioned approaches based
          on walking activities, Shi et al. [71] examine the WiFi signals
                                                                                                                Fig. 16.    Relation between effective CSI readings and distance [84].
          and extracts unique physiological and behavioral characteristics
          inherited from people’s in-home or in-office activities including
          both walking activities (e.g., waking between rooms) and
                                                                                                                anchor method is proposed in [78] to alleviate environmental
          stationary activities (e.g., operating appliances) to differentiate
                                                                                                                effects. The proposed system computes the dynamic correction
          each individual person. The authors exploit the unique variation
                                                                                                                coefficient for each distance reference anchor node based on
          patterns on both amplitude and relative phase of CSI caused
                                                                                                                each RSSI measurement, and a continuous feedback is provided
          by people’s daily activities. A deep learning based model
                                                                                                                to reflect the environmental changes for robust location
          is developed to perform both activity recognition and user
                                                                                                                estimation. Xie et al. [79] present a K-Nearest-Neighbor (KNN)
          authentication, and thereby facilitate many applications in both
                                                                                                                scheme based on spearman distance to eliminate the multi-
          corporate offices and residential areas.
                                                                                                                path attenuation in RSSI-based localization system. Hong et
                                                                                                                al. [136] rely on Support Vector Machine (SVM) to detect
          B. Indoor Localization & Tracking                                                                     eigenvector changes of RSS measurements and further improve
                                                                                                                the localization accuracy. To enhance the efficiency of RSSI-
             Beside human motions, the locations of people also have                                            based system, Barsocchi et al. [80] propose a virtual calibration
          significant impacts on wireless signal propagation in an indoor                                       technique for wireless signal propagation model, which does not
          environment. Therefore, the physical properties of wireless                                           require the human intervention during training phase. Xiong
          signals can be used to infer the locations. There are a large                                         and Jamieson [81] propose ArrayTrack, which requires no
          body of work in the field of indoor localization and tracking.                                        calibration beforehand to achieve high localization accuracy
          In this paper, we described a subset of the work that provide                                         using RSSI. Unlike aforementioned approaches which only
          localization and tracking in term os adopted sensing techniques                                       localize the single person, Bocca et al. [82] and Nannuru et
          (i.e., RSSI-based, CSI-based and FMCW-based).                                                         al. [83] utilize Radio-frequency (RF) tomography of RSSI
             RSSI-based. Banhl and Padmanabhan [72] introduces                                                  measurements to achieve multi-user localization in indoor
          RADAR, a radio-frequency (RF) based system, which uses                                                environments.
          RSSI measurements to model the relationship between signal                                               CSI-based. CSI-based indoor localization, first proposed
          strength and distance and further track the people inside a                                           by Wu et al. [84], [85] and Sen et al. [86], is emerging to
          building. To improve the accuracy, Guvenc et al. [73] and Paul                                        replace RSSI, due to its fine-grained channel information and
          [74] propose to use Kalman filter algorithm to the propagation                                        high robustness. Wu et al. [84], [85] re-defined the indoor
          model of RSSI-based localization system. In addition, some                                            propagation model based on a modified free space path loss
          other approaches (e.g., [74]–[76]) are developed to combine                                           propagation model to capture the relationship between the
          RSS measurements with the measurements of other sensors                                               effective CSI readings (i.e., CSIeff in Figure 16) and distance.
          (e.g., GPS [75], [76], infra-red (IR) motion sensor [74]) to                                          Figure 16 illustrates the approximated relationship between
          enhance the stability of indoor localization. Since RSSI is too                                       CSIeff and distance according to the refined propagation model.
          sensitive to the small environmental changes, it is critical to                                       Through exponential fitting, a CSI-distance model can be built
          ensure the robustness of RSSI-based localization system. A                                            to enable indoor localization. Similarly, Sen et al. [86] model
          differential RSSI-based approach [77] is proposed to model                                            the channel response and demonstrate that the localization
          the shadowed links and utilizes the particle filter to realize                                        accuracy using CSI can achieve the granularity of 1m x 1m
          location estimation robustly. A dynamic distance reference                                            boxes. Furthermore, Sen et al. [87] propose to effectively




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




          reduce the impact of multipath reflections by applying CSI                                            also have critical impact on the performance of WiFi-based
          information to indoor localization system. Different from the                                         sensing systems. For the human involved activities, the differ-
          aforementioned localization systems involving multiple access                                         ences on users’ location and orientation could induce different
          points (APs), SAIL [88] is proposed to capture the user’s                                             variation pattern of RSSI or CSI measurements. Thus, existing
          location accurately with only a single WiFi AP. Additionally,                                         systems usually require the user to keep the same location
          Wang et al. [89], [90] propose to use deep learning techniques                                        and orientation during both the training and testing phases.
          to facilitate indoor localization. Specifically, the weights in the                                   Some research studies attempt to overcome such limitations.
          deep network replace the raw CSI measurements to represent                                            For example, existing work WiAG [35] proposed a translation
          the location fingerprints.                                                                            function that can generate virtual samples of a given gesture in
             FMCW-based. The first FMCW-based localization system,                                              any desired configuration (i.e., location and orientation) based
          proposed by Vossiek et al. [92], uses three FMCW radars to                                            on the real samples of the same gesture under another known
          achieve object tracking in 3-D space. In contrast to the work                                         configuration. Yet WiAG needs additional efforts to derive a
          that relies on a wireless signal channel for localization, Feger                                      few parameters (i.e, gesture shape and speed) by asking the
          et al. [93] and Gierlich et al. [94] propose to apply multiple-                                       user to hold a smartphone while performing gestures, making it
          input multiple-output (MIMO) technique to FWCW system                                                 less practical for some application scenarios. A more efficient
          for high-precision location estimation. Recently, WiTrack [28]                                        and convenient solution is to build a rigorous theoretical model,
          further leverages the MIMO FMCW technique to obtain the ∆t                                            which is independent to the user’s location and orientation,
          measurements to track single moving person and the related                                            to map the relationship between WiFi measurements and the
          motion of different body parts. To enhance the performance of                                         human involved action/activity.
          WiTrack, Adib et al. proposed WiTrack2.0 [95] that not only                                              Multi-user Activity Sensing. Existing FMCW-based solu-
          achieves multiple moving people tracking but also localizes                                           tion WiTrack2.0 [42] can track the hand gestures of multiple
          multiple static people through the TOF measurements of                                                people simultaneously leveraging a directional antenna array.
          FMCW signals. Evaluation of WiTrack2.0 shows that it can                                              Vital-Radio [56] can differentiate multiple users and track their
          localize up to five people simultaneously with a median                                               vital signs simultaneously through differentiating the reflections
          accuracy of 11.7 cm.                                                                                  from different subjects. The CSI-based approach [49], [50]
                                                                                                                could use the frequency difference of multiple users’ breathing
                                                                                                                rates to track them simultaneously. However, most of the RSSI
                          VII.       L IMITATIONS AND D ISCUSSIONS                                              and CSI based sensing approaches can only handle single-
                                                                                                                person case as it is challenging to distinguish the movements of
             Although the aforementioned research studies have demon-                                           multiple people from WiFi signal measurements. A promising
          strated the powerful capability of WiFi-based sensing systems                                         way would be isolating concurrent activities of different people
          on serving a broad array of applications, there still exist                                           in separate spaces and perform activity sensing separately, but
          limitations and open problems that need further exploration in                                        a complex web of WiFi links in an area is required.
          the future.
                                                                                                                   Re-using Real WiFi Traffic. The sensing capability of
             Impact of Environmental Changes. For many RSSI or                                                  many existing RSSI or CSI-based sensing systems is usually
          CSI-based sensing systems that need to build training profiles                                        fulfilled with periodic WiFi traffic at a constant rate. Existing
          (e.g., activity recognition [21], gesture recognition [127] and                                       WiFi sensing systems relying on RSSI or CSI measurements
          indoor localization [72], [86]), the profiles can be easily altered                                   need to be running with periodic WiFi traffic at a constant
          by environmental changes (e.g., furniture movements, closing a                                        rate to keep continuous and synchronized sensing ability. The
          door), which could lead to the inconsistency between incoming                                         researchers usually use ping command to generate such traffic
          testing instance (e.g., activity, gesture and location) and the                                       to satisfy this requirement. However, real WiFi traffic depends
          profiles. As a result, the system usually needs a huge amount of                                      on the real-time demand of users or IoT devices, which cannot
          extra efforts to re-train the profiles, which requires unacceptable                                   be manageable. Moreover, the commercial routers can only
          labor cost and system downtime. To mitigate the impacts of                                            broadcast beacon packages with a default constant interval
          environmental changes, existing studies [22], [23] build CSI-                                         100ms to help keep the network synchronized. Empirical
          speed model and CSI-activity model to quantify the correlation                                        demonstration of re-using such aforementioned real WiFi traffic
          between the movement speeds of different body parts and a                                             in various sensing application domains would be necessary.
          specific activity, but it may affect the sensitivity of the proposed                                  Additionally, FMCW and Doppler-based solutions require well-
          system on detecting human activities. Furthermore, AutoFi [91]                                        defined transmitting signals, which might be hard to use on
          develops a novel contaminant removal module and applies                                               the top of the existing WiFi signals. Further exploration needs
          feature-preserving autoencoder [137] to intelligently calibrate                                       to be made along with this direction.
          the Wi-Fi profiles. It estimates the CSI changes caused by the                                           Security & Privacy Considerations. With the rapid ad-
          environment changes and then eliminates these contaminants                                            vancement of WiFi sensing techniques, it also raises serious
          with a linear regression module with the autoencoder, making                                          security and privacy breaches. Existing work has demonstrated
          the profile features adaptive to the new environment. More                                            that WiFi signals can be used to snoop keystrokes [39] and
          efforts, such as intelligent profile calibration with multiple WiFi                                   infer mobile phone password [138]. Adversaries could also
          links and advanced data filtering/machine learning techniques,                                        use existing activity sensing systems to spy on the position
          would be helpful in future work.                                                                      and activities of others (e.g., neighbors). Thus, when we enjoy
             Impact of User’s Location and Orientation. In addition to                                          the convenience brought by the WiFi sensing technologies, we
          the environmental changes, the user’s location and orientation                                        need to pay more attention to the accompanying security and




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




          privacy concerns. There is an urgent need to derive security                                           [11]    Z. Zhou, Z. Yang, C. Wu, L. Shangguan, and Y. Liu, “Towards omni-
          solutions during the new sensing system design.                                                                directional passive human detection,” in INFOCOM, 2013 Proceedings
                                                                                                                         IEEE. IEEE, 2013, pp. 3057–3065.
                                                                                                                 [12]    M. Nakatsuka, H. Iwatani, and J. Katto, “A study on passive crowd
                                        VIII.        C ONCLUSION                                                         density estimation using wireless sensors,” in The 4th International
                                                                                                                         Conference on Mobile Computing and Ubiquitous Networking (Citeseer
             In this work, a survey of recent studies on human activity                                                  ICMU), 2008.
          sensing systems using RF signals (e.g., WiFi) has been provided.                                       [13]    Y. Yuan, J. Zhao, C. Qiu, and W. Xi, “Estimating crowd density in an
          We review a broad array of emerging applications associated                                                    rf-based dynamic environment,” IEEE Sensors Journal, vol. 13, no. 10,
          with human body movements using wireless signals, including                                                    pp. 3837–3845, 2013.
          intrusion detection, room occupancy monitoring, activity and                                           [14]    C. Xu, B. Firner, R. S. Moore, Y. Zhang, W. Trappe, R. Howard,
          gesture recognition, vital signs monitoring, identity identifica-                                              F. Zhang, and N. An, “Scpl: indoor device-free multi-subject counting
                                                                                                                         and localization using radio signal strength,” in The 12th ACM/IEEE In-
          tion and indoor localization. According to the sensing technique                                               ternational Conference on Information Processing in Sensor Networks
          introduced in these studies, we categorize the literature into four                                            (IEEE IPSN), 2013, pp. 79–90.
          major categories: RSSI-based, CSI-based, FMCW-based and                                                [15]    X. Guo, B. Liu, C. Shi, H. Liu, Y. Chen, and M. C. Chuah, “Wifi-
          Doppler-shift-based. These compelling wireless sensing studies                                                 enabled smart human dynamics monitoring,” in Proceedings of the
          have shown promising performance in various application                                                        15th ACM Conference on Embedded Network Sensor Systems (ACM
          domains. In addition, we also point out the limitations of                                                     SenSys), 2017.
          the current WiFi-based sensing approaches and show a few                                               [16]    W. Xi, J. Zhao, X.-Y. Li, K. Zhao, S. Tang, X. Liu, and Z. Jiang,
          challenges that need to be addressed in the future.                                                            “Electronic frog eye: Counting crowd using wifi,” in Proceedings of
                                                                                                                         the International Conference on Computer Communications (IEEE
                                                                                                                         INFOCOM), 2014, pp. 361–369.
                                    IX.       ACKNOWLEDGMENT                                                     [17]    S. Sigg, S. Shi, F. Buesching, Y. Ji, and L. Wolf, “Leveraging
                                                                                                                         rf-channel fluctuation for activity recognition: Active and passive
            This work was partially supported by the National Sci-                                                       systems, continuous and rssi-based signal features,” in Proceedings
          ence Foundation Grants CNS-1820624, CNS-1826647, CNS-                                                          of International Conference on Advances in Mobile Computing &
          1815908, CNS-1717356 and Army Research Office W911NF-                                                          Multimedia. ACM, 2013, p. 43.
          18-1-0221.                                                                                             [18]    S. Sigg, M. Scholz, S. Shi, Y. Ji, and M. Beigl, “Rf-sensing of activities
                                                                                                                         from non-cooperative subjects in device-free recognition systems using
                                                                                                                         ambient and local signals,” IEEE Transactions on Mobile Computing,
                                               R EFERENCES                                                               vol. 13, no. 4, pp. 907–920, 2014.
                                                                                                                 [19]    J. Wilson and N. Patwari, “Radio tomographic imaging with wireless
            [1] S. C. Mukhopadhyay, “Wearable sensors for human activity monitoring:                                     networks,” IEEE Trans. on Mobile Computing, vol. 9, no. 5, 2010.
                A review,” IEEE sensors journal, vol. 15, no. 3, pp. 1321–1330, 2015.
                                                                                                                 [20]    ——, “See-through walls: Motion tracking using variance-based radio
            [2] T. B. Moeslund, A. Hilton, and V. Krüger, “A survey of advances in                                       tomography networks,” IEEE Trans. on Mobile Computing, vol. 10,
                vision-based human motion capture and analysis,” Computer vision                                         no. 5, pp. 612–621, 2011.
                and image understanding, vol. 104, no. 2-3, pp. 90–126, 2006.
                                                                                                                 [21]    Y. Wang, J. Liu, Y. Chen, M. Gruteser, J. Yang, and H. Liu, “E-
            [3] C. Zieger, A. Brutti, and P. Svaizer, “Acoustic based surveillance
                                                                                                                         eyes: device-free location-oriented activity identification using fine-
                system for intrusion detection,” in IEEE International Conference on
                                                                                                                         grained wifi signatures,” in Proceedings of the 20th annual international
                Advanced Video and Signal Based Surveillance (AVSS). IEEE, 2009,
                                                                                                                         conference on Mobile computing and networking (ACM MobiCom),
                pp. 314–319.
                                                                                                                         2014, pp. 617–628.
            [4] K. C. Sahoo and U. C. Pati, “Iot based intrusion detection system
                                                                                                                 [22]    W. Wang, A. X. Liu, M. Shahzad, K. Ling, and S. Lu, “Understanding
                using pir sensor,” in IEEE International Conference on Recent Trends
                                                                                                                         and modeling of wifi signal based human activity recognition,” in
                in Electronics, Information & Communication Technology (RTEICT).
                                                                                                                         Proceedings of the 21st Annual International Conference on Mobile
                IEEE, 2017, pp. 1641–1645.
                                                                                                                         Computing and Networking (ACM MobiCom), 2015, pp. 65–76.
            [5] M. Youssef, M. Mah, and A. Agrawala, “Challenges: device-free
                passive localization for wireless environments,” in Proceedings of the                           [23]    ——, “Device-free human activity recognition using commercial wifi
                13th annual ACM international conference on Mobile computing and                                         devices,” IEEE Journal on Selected Areas in Communications, vol. 35,
                networking (ACM MobiCom), 2007.                                                                          no. 5, pp. 1118–1131, 2017.
            [6] M. Moussa and M. Youssef, “Smart devices for smart environments:                                 [24]    C. Han, K. Wu, Y. Wang, and L. M. Ni, “Wifall: Device-free fall
                Device-free passive detection in real environments,” in IEEE Inter-                                      detection by wireless networks,” in The 33rd Annual IEEE International
                national Conference on Pervasive Computing and Communications                                            Conference on Computer Communications (IEEE INFOCOM), 2014,
                (PerCom). IEEE, 2009, pp. 1–6.                                                                           pp. 271–279.
            [7] A. E. Kosba, A. Saeed, and M. Youssef, “Rasid: A robust wlan                                     [25]    D. Zhang, H. Wang, Y. Wang, and J. Ma, “Anti-fall: A non-intrusive
                device-free passive motion detection system,” in Proceedings of the                                      and real-time fall detector leveraging csi from commodity wifi devices,”
                International Conference on Pervasive Computing and Communications                                       in International Conference on Smart Homes and Health Telematics.
                (IEEE PerCom), 2012.                                                                                     Springer, 2015, pp. 181–193.
            [8] J. Xiao, K. Wu, Y. Yi, L. Wang, and L. M. Ni, “Pilot: Passive device-                            [26]    H. Wang, D. Zhang, Y. Wang, J. Ma, Y. Wang, and S. Li, “Rt-fall: A
                free indoor localization using csi,” in Proceedings of the 2013 IEEE                                     real-time and contactless fall detection system with commodity wifi
                33rd International Conference on Distributed Computing Systems                                           devices.” IEEE Trans. Mob. Comput., vol. 16, no. 2, pp. 511–526,
                (IEEE ICDCS), 2013.                                                                                      2017.
            [9] K. Qian, C. Wu, Z. Yang, Y. Liu, and Z. Zhou, “Pads: Passive detection                           [27]    S. Palipana, D. Rojas, P. Agrawal, and D. Pesch, “Falldefi: Ubiquitous
                of moving targets with dynamic speed using phy layer information,”                                       fall detection using commodity wi-fi devices,” Proceedings of the ACM
                in 20th IEEE International Conference on Parallel and Distributed                                        on Interactive, Mobile, Wearable and Ubiquitous Technologies, vol. 1,
                Systems (ICPADS). IEEE, 2014, pp. 1–8.                                                                   no. 4, p. 155, 2018.
           [10] E. Ding, X. Li, T. Zhao, L. Zhang, and Y. Hu, “A robust passive                                  [28]    F. Adib, Z. Kabelac, D. Katabi, and R. C. Miller, “3d tracking via body
                intrusion detection system with commodity wifi devices,” Journal of                                      radio reflections,” in Proceedings of the 11th USENIX Conference on
                Sensors, vol. 2018, 2018.                                                                                Networked Systems Design and Implementation (NSDI), 2014.




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




           [29] K. Chetty, G. E. Smith, and K. Woodbridge, “Through-the-wall sensing                                     of the 16th ACM International Symposium on Mobile Ad Hoc
                of personnel using passive bistatic wifi radar at standoff distances,”                                   Networking and Computing. ACM, 2015, pp. 277–286.
                IEEE Transactions on Geoscience and Remote Sensing, vol. 50, no. 4,                              [49]    J. Liu, Y. Wang, Y. Chen, J. Yang, X. Chen, and J. Cheng, “Tracking
                pp. 1218–1226, 2012.                                                                                     vital signs during sleep leveraging off-the-shelf wifi,” in Proceedings of
           [30] F. Adib and D. Katabi, “See through walls with wifi!” in Proceedings                                     the 16th ACM International Symposium on Mobile Ad Hoc Networking
                of the ACM SIGCOMM 2013 conference on SIGCOMM, 2013.                                                     and Computing (ACM Mobihoc), 2015, pp. 267–276.
           [31] S. Sigg, U. Blanke, and G. Troster, “The telepathic phone: Frictionless                          [50]    J. Liu, W. Y. Chen, Yingying, X. Chen, J. Cheng, and J. Yang,
                activity recognition from wifi-rssi,” in Pervasive Computing and                                         “Monitoring vital signs and postures during sleep using wifi signals,”
                Communications (PerCom), 2014 IEEE International Conference on.                                          IEEE Internet of Things Journal (IEEE IoT), vol. 5, pp. 2071–2084,
                IEEE, 2014, pp. 148–155.                                                                                 2018.
           [32] P. Melgarejo, X. Zhang, P. Ramanathan, and D. Chu, “Leveraging                                   [51]    B. Fang, N. D. Lane, M. Zhang, A. Boran, and F. Kawsar, “Bodyscan:
                directional antenna capabilities for fine-grained gesture recognition,”                                  Enabling radio-based sensing on wearable devices for contactless
                in Proceedings of the 2014 ACM International Joint Conference on                                         activity and vital sign monitoring,” in Proceedings of the 14th Annual
                Pervasive and Ubiquitous Computing. ACM, 2014, pp. 541–551.                                              International Conference on Mobile Systems, Applications, and Services
           [33] H. Abdelnasser, M. Youssef, and K. A. Harras, “Wigest: A ubiqui-                                         (ACM Mobisys), 2016, pp. 97–110.
                tous wifi-based gesture recognition system,” in Proceedings of the                               [52]    J. Zhang, W. Xu, W. Hu, and S. S. Kanhere, “Wicare: Towards in-
                IEEE International Conference on Computer Communications (IEEE                                           situ breath monitoring,” in Proceedings of the 14th EAI International
                INFOCOM), 2015, pp. 1472–1480.                                                                           Conference on Mobile and Ubiquitous Systems: Computing, Networking
                                                                                                                         and Services. ACM, 2017, pp. 126–135.
           [34] R. Nandakumar, B. Kellogg, and S. Gollakota, “Wi-fi gesture recogni-
                tion on existing devices,” arXiv preprint arXiv:1411.5394, 2014.                                 [53]    X. Wang, C. Yang, and S. Mao, “Phasebeat: Exploiting csi phase data
                                                                                                                         for vital sign monitoring with commodity wifi devices,” in Distributed
           [35] A. Virmani and M. Shahzad, “Position and orientation agnostic gesture
                                                                                                                         Computing Systems (ICDCS), 2017 IEEE 37th International Conference
                recognition using wifi,” in Proceedings of the 15th Annual International
                                                                                                                         on. IEEE, 2017, pp. 1230–1239.
                Conference on Mobile Systems, Applications, and Services. ACM,
                2017, pp. 252–264.                                                                               [54]    H. Wang, D. Zhang, J. Ma, Y. Wang, Y. Wang, D. Wu, T. Gu, and
                                                                                                                         B. Xie, “Human respiration detection with commodity wifi devices:
           [36] H. Li, W. Yang, J. Wang, Y. Xu, and L. Huang, “Wifinger: talk to
                                                                                                                         do user location and body orientation matter?” in Proceedings of the
                your smart devices with finger-grained gesture,” in Proceedings of the
                                                                                                                         2016 ACM International Joint Conference on Pervasive and Ubiquitous
                2016 ACM International Joint Conference on Pervasive and Ubiquitous
                                                                                                                         Computing. ACM, 2016, pp. 25–36.
                Computing. ACM, 2016, pp. 250–261.
                                                                                                                 [55]    L. Anitori, A. de Jong, and F. Nennie, “Fmcw radar for life-sign
           [37] Y. Ma, G. Zhou, S. Wang, H. Zhao, and W. Jung, “Signfi: Sign language                                    detection,” in IEEE radar conference, 2009, pp. 1–6.
                recognition using wifi,” Proceedings of the ACM on Interactive, Mobile,
                Wearable and Ubiquitous Technologies, vol. 2, no. 1, p. 23, 2018.                                [56]    F. Adib, H. Mao, Z. Kabelac, D. Katabi, and R. C. Miller, “Smart
                                                                                                                         homes that monitor breathing and heart rate,” in Proceedings of the
           [38] Z. Tian, J. Wang, X. Yang, and M. Zhou, “Wicatch: A wi-fi based hand                                     33rd annual ACM conference on human factors in computing systems.
                gesture recognition system,” IEEE Access, vol. 6, pp. 16 911–16 923,                                     ACM, 2015, pp. 837–846.
                2018.
                                                                                                                 [57]    D. Zhang, M. Kurata, and T. Inaba, “Fmcw radar for small displacement
           [39] K. Ali, A. X. Liu, W. Wang, and M. Shahzad, “Keystroke recognition                                       detection of vital signal using projection matrix method,” International
                using wifi signals,” in Proceedings of the 21st Annual International                                     Journal of Antennas and Propagation, vol. 2013, 2013.
                Conference on Mobile Computing and Networking. ACM, 2015, pp.
                90–102.                                                                                          [58]    T. Ballal, R. B. Shouldice, C. Heneghan, and A. Zhu, “Breathing
                                                                                                                         rate estimation from a non-contact biosensor using an adaptive iir
           [40] G. Wang, Y. Zou, Z. Zhou, K. Wu, and L. M. Ni, “We can hear you                                          notch filter,” in 2012 IEEE Topical Conference on Biomedical Wireless
                with wi-fi!” IEEE Transactions on Mobile Computing, vol. 15, no. 11,                                     Technologies, Networks, and Sensing Systems, 2012, pp. 5–8.
                pp. 2907–2920, 2016.
                                                                                                                 [59]    W. Li, B. Tan, and R. J. Piechocki, “Non-contact breathing detection us-
           [41] B. Fang, N. D. Lane, M. Zhang, and F. Kawsar, “Headscan: A wearable                                      ing passive radar,” in Communications (ICC), 2016 IEEE International
                system for radio-based sensing of head and mouth-related activities,”                                    Conference on. IEEE, 2016, pp. 1–6.
                in Information Processing in Sensor Networks (IPSN), 2016 15th
                                                                                                                 [60]    J. Salmi, O. Luukkonen, and V. Koivunen, “Continuous wave radar
                ACM/IEEE International Conference on. IEEE, 2016, pp. 1–12.
                                                                                                                         based vital sign estimation: Modeling and experiments,” in Radar
           [42] F. Adib, Z. Kabelac, and D. Katabi, “Multi-person motion tracking                                        Conference (RADAR), 2012 IEEE. IEEE, 2012, pp. 0564–0569.
                via rf body reflections,” MIT technical report, 2014.
                                                                                                                 [61]    C. Li and J. Lin, “Random body movement cancellation in doppler
           [43] J. Lien, N. Gillian, M. E. Karagozler, P. Amihood, C. Schwesig,                                          radar vital sign detection,” IEEE Transactions on Microwave Theory
                E. Olson, H. Raja, and I. Poupyrev, “Soli: Ubiquitous gesture sensing                                    and Techniques, vol. 56, no. 12, pp. 3143–3152, 2008.
                with millimeter wave radar,” ACM Transactions on Graphics (TOG),
                                                                                                                 [62]    F.-K. Wang, T.-S. Horng, K.-C. Peng, J.-K. Jau, J.-Y. Li, and C.-
                vol. 35, no. 4, p. 142, 2016.
                                                                                                                         C. Chen, “Single-antenna doppler radars using self and mutual
           [44] P. Molchanov, S. Gupta, K. Kim, and K. Pulli, “Short-range fmcw                                          injection locking for vital sign detection with random body movement
                monopulse radar for hand-gesture sensing,” in Radar Conference                                           cancellation,” IEEE Transactions on Microwave Theory and Techniques,
                (RadarCon), 2015 IEEE. IEEE, 2015, pp. 1491–1496.                                                        vol. 59, no. 12, p. 3577, 2011.
           [45] Q. Pu, S. Gupta, S. Gollakota, and S. Patel, “Whole-home gesture                                 [63]    C. Li and J. Lin, “Complex signal demodulation and random body
                recognition using wireless signals,” in Proceedings of the 19th annual                                   movement cancellation techniques for non-contact vital sign detection,”
                international conference on Mobile computing & networking (ACM                                           in Microwave Symposium Digest, 2008 IEEE MTT-S International.
                MobiCom), 2013.                                                                                          IEEE, 2008, pp. 567–570.
           [46] O. Kaltiokallio, H. Yigitler, R. Jantti, and N. Patwari, “Non-invasive                           [64]    P. Nguyen, X. Zhang, A. Halbower, and T. Vu, “Continuous and fine-
                respiration rate monitoring using a single cots tx-rx pair,” in Proceed-                                 grained breathing volume monitoring from afar using wireless signals,”
                ings of the 13th international symposium on Information processing                                       in The 35th Annual IEEE International Conference on Computer
                in sensor networks (ACM IPSN). IEEE Press, 2014, pp. 59–70.                                              Communications (IEEE INFOCOM). IEEE, 2016, pp. 1–9.
           [47] N. Patwari, L. Brewer, Q. Tate, O. Kaltiokallio, and M. Bocca,                                   [65]    H. Zhao, H. Hong, L. Sun, Y. Li, C. Li, and X. Zhu, “Noncontact
                “Breathfinding: A wireless network that monitors andlocates breathing                                    physiological dynamics detection using low-power digital-if doppler
                in a home,” IEEE Journal of Selected Topics in Signal Processing,                                        radar,” IEEE Transactions on Instrumentation and Measurement,
                vol. 8, no. 1, pp. 30–42, 2014.                                                                          vol. 66, no. 7, pp. 1780–1788, 2017.
           [48] H. Abdelnasser, K. A. Harras, and M. Youssef, “Ubibreathe: A                                     [66]    C. Gu, C. Li, J. Lin, J. Long, J. Huangfu, and L. Ran, “Instrument-based
                ubiquitous non-invasive wifi-based breathing estimator,” in Proceedings                                  noncontact doppler radar vital sign detection system using heterodyne




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




                   digital quadrature demodulation architecture,” IEEE Transactions on                                   localization,” IEEE Transactions on Parallel and Distributed Systems,
                   Instrumentation and Measurement, vol. 59, no. 6, pp. 1580–1588,                                       vol. 24, no. 7, pp. 1300–1309, 2013.
                   2010.                                                                                         [86]    S. Sen, B. Radunovic, R. R. Choudhury, and T. Minka, “You are
           [67]    J. Zhang, B. Wei, W. Hu, and S. Kenhere, “Wifi-id: Human identifica-                                  facing the mona lisa: Spot localization using phy layer information,” in
                   tion using wifi signal,” in Proceedings of International Conference on                                Proceedings of the 10th International Conference on Mobile Systems,
                   Distributed Computing in Sensor Systems (IEEE DCOSS), 2016, pp.                                       Applications, and Services (MobiSys), 2012, pp. 183–196.
                   75–82.                                                                                        [87]    S. Sen, J. Lee, K.-H. Kim, and P. Congdon, “Avoiding multipath to
           [68]    Y. Zeng, P. H. Pathak, and P. Mohapatra, “Wiwho: Wifi-based person                                    revive inbuilding wifi localization,” in Proceeding of the 11th annual
                   identification in smart spaces,” in 15th ACM/IEEE International                                       international conference on Mobile systems, applications, and services.
                   Conference on Information Processing in Sensor Networks (IEEE                                         ACM, 2013, pp. 249–262.
                   IPSN), 2016, pp. 1–12.                                                                        [88]    A. T. Mariakakis, S. Sen, J. Lee, and K.-H. Kim, “Sail: Single access
           [69]    W. Wang, A. X. Liu, and M. Shahzad, “Gait recognition using wifi                                      point-based indoor localization,” in Proceedings of the 12th annual
                   signals,” in Proceedings of ACM International Joint Conference on                                     international conference on Mobile systems, applications, and services.
                   Pervasive and Ubiquitous Computing (ACM Ubicomp), 2016, pp. 363–                                      ACM, 2014, pp. 315–328.
                   373.                                                                                          [89]    X. Wang, L. Gao, S. Mao, and S. Pandey, “Deepfi: Deep learning
           [70]    F. Hong, X. Wang, Y. Yang, Y. Zong, Y. Zhang, and Z. Guo,                                             for indoor fingerprinting using channel state information,” in Wireless
                   “Wfid: Passive device-free human identification using wifi signal,” in                                Communications and Networking Conference (WCNC), 2015 IEEE.
                   Proceedings of the 13th International Conference on Mobile and                                        IEEE, 2015, pp. 1666–1671.
                   Ubiquitous Systems: Computing, Networking and Services (ACM                                   [90]    ——, “Csi-based fingerprinting for indoor localization: A deep learning
                   MobiQuitous), 2016, pp. 47–56.                                                                        approach,” IEEE Transactions on Vehicular Technology, vol. 66, no. 1,
           [71]    C. Shi, J. Liu, H. Liu, and Y. Chen, “Smart user authentication                                       pp. 763–776, 2017.
                   through actuation of daily activities leveraging wifi-enabled iot,” in                        [91]    X. Chen, C. Ma, M. Allegue, and X. Liu, “Taming the inconsistency
                   Proceedings of the 18th ACM International Symposium on Mobile Ad                                      of wi-fi fingerprints for device-free passive indoor localization,” in
                   Hoc Networking and Computing (MobiHoc). ACM, 2017, p. 5.                                              IEEE Conference on Computer Communications (INFOCOM), 2017,
           [72]    P. Bahl and V. N. Padmanabhan, “Radar: An in-building RF-based user                                   pp. 1–9.
                   location and tracking system,” in Proceedings of the IEEE International                       [92]    M. Vossiek, R. Roskosch, and P. Heide, “Precise 3-d object position
                   Conference on Computer Communications (IEEE INFOCOM), March                                           tracking using fmcw radar,” in Microwave Conference, 1999. 29th
                   2000, pp. 775–784.                                                                                    European, vol. 1. IEEE, 1999, pp. 234–237.
           [73]    İ. GüvencÌč, “Enhancements to rss based indoor tracking systems using                       [93]    R. Feger, C. Wagner, S. Schuster, S. Scheiblhofer, H. Jager, and
                   kalman filters,” Ph.D. dissertation, University of New Mexico, 2003.                                  A. Stelzer, “A 77-ghz fmcw mimo radar based on an sige single-chip
           [74]    A. S. Paul and E. A. Wan, “Rssi-based indoor localization and tracking                                transceiver,” IEEE Transactions on Microwave Theory and Techniques,
                   using sigma-point kalman smoothers,” IEEE Journal of Selected Topics                                  vol. 57, no. 5, pp. 1020–1035, 2009.
                   in Signal Processing, vol. 3, no. 5, pp. 860–873, 2009.                                       [94]    R. Gierlich, J. Huettner, A. Ziroff, R. Weigel, and M. Huemer, “A
           [75]    K. Chintalapudi, A. Padmanabha Iyer, and V. N. Padmanabhan, “Indoor                                   reconfigurable mimo system for high-precision fmcw local positioning,”
                   localization without the pain,” in Proceedings of the sixteenth annual                                IEEE Transactions on Microwave Theory and Techniques, vol. 59,
                   international conference on Mobile computing and networking. ACM,                                     no. 12, pp. 3228–3238, 2011.
                   2010, pp. 173–184.                                                                            [95]    F. Adib, Z. Kabelac, and D. Katabi, “Multi-person localization via rf
           [76]    H. Li, X. Chen, G. Jing, Y. Wang, Y. Cao, F. Li, X. Zhang, and                                        body reflections.” in NSDI, 2015, pp. 279–292.
                   H. Xiao, “An indoor continuous positioning algorithm on the move                              [96]    D. Halperin, W. Hu, A. Sheth, and D. Wetherall, “Tool release:
                   by fusing sensors and wi-fi on smartphones,” Sensors, vol. 15, no. 12,                                gathering 802.11 n traces with channel state information,” ACM
                   pp. 31 244–31 267, 2015.                                                                              SIGCOMM Computer Communication Review, vol. 41, no. 1, pp.
           [77]    J. Wang, Q. Gao, Y. Yu, P. Cheng, L. Wu, and H. Wang, “Robust device-                                 53–53, 2011.
                   free wireless localization based on differential rss measurements,” IEEE                      [97]    Y. Xie, Z. Li, and M. Li, “Precise power delay profiling with commodity
                   transactions on industrial electronics, vol. 60, no. 12, pp. 5943–5952,                               wifi,” in Proceedings of the 21st ACM Annual International Conference
                   2013.                                                                                                 on Mobile Computing and Networking (MobiCom), 2015, pp. 53–64.
           [78]    U. Bekcibasi and M. Tenruh, “Increasing rssi localization accuracy                            [98]    B. Tan, K. Woodbridge, and K. Chetty, “A wireless passive radar system
                   with distance reference anchor in wireless sensor networks,” Acta                                     for real-time through-wall movement detection,” IEEE Transactions
                   Polytechnica Hungarica, vol. 11, no. 8, 2014.                                                         on Aerospace and Electronic Systems, vol. 52, no. 5, pp. 2596–2603,
           [79]    Y. Xie, Y. Wang, A. Nallanathan, and L. Wang, “An improved k-nearest-                                 2016.
                   neighbor indoor localization method based on spearman distance,”                              [99]    ——, “A real-time high resolution passive wifi doppler-radar and its
                   IEEE Signal Processing Letters, vol. 23, no. 3, pp. 351–355, 2016.                                    applications,” in Radar Conference (Radar), 2014 International. IEEE,
           [80]    P. Barsocchi, S. Lenzi, S. Chessa, and G. Giunta, “A novel approach                                   2014, pp. 1–6.
                   to indoor rssi localization by automatic calibration of the wireless                         [100]    S. Y. Seidel and T. S. Rappaport, “914 mhz path loss prediction models
                   propagation model,” in Vehicular Technology Conference, 2009. VTC                                     for indoor wireless communications in multifloored buildings,” IEEE
                   Spring 2009. IEEE 69th. IEEE, 2009, pp. 1–5.                                                          transactions on Antennas and Propagation, vol. 40, no. 2, pp. 207–217,
           [81]    J. Xiong and K. Jamieson, “Arraytrack: a fine-grained indoor location                                 1992.
                   system,” in Proceedings of the 10th USENIX conference on Networked                           [101]    D. Zhang, Y. Liu, X. Guo, and L. M. Ni, “Rass: A real-time,
                   Systems Design and Implementation (NSDI), 2013.                                                       accurate, and scalable system for tracking transceiver-free objects,”
           [82]    M. Bocca, O. Kaltiokallio, N. Patwari, and S. Venkatasubramanian,                                     IEEE Transactions on Parallel and Distributed Systems, vol. 24, no. 5,
                   “Multiple target tracking with rf sensor networks,” IEEE Transactions                                 pp. 996–1008, 2013.
                   on Mobile Computing, vol. 13, no. 8, pp. 1787–1800, 2014.                                    [102]    A. T. Parameswaran, M. I. Husain, S. Upadhyaya et al., “Is rssi a
           [83]    S. Nannuru, Y. Li, Y. Zeng, M. Coates, and B. Yang, “Radio-frequency                                  reliable parameter in sensor localization algorithms: An experimental
                   tomography for passive indoor multitarget tracking,” IEEE Transactions                                study,” in Field failure data analysis workshop (F2DA09), vol. 5.
                   on Mobile Computing, vol. 12, no. 12, pp. 2322–2333, 2013.                                            IEEE, 2009.
           [84]    K. Wu, J. Xiao, Y. Yi, M. Gao, and L. M. Ni, “Fila: Fine-grained                             [103]    F. Adib, C.-Y. Hsu, H. Mao, D. Katabi, and F. Durand, “Capturing the
                   indoor localization,” in INFOCOM, 2012 Proceedings IEEE. IEEE,                                        human figure through a wall,” ACM Transactions on Graphics (TOG),
                   2012, pp. 2210–2218.                                                                                  vol. 34, no. 6, p. 219, 2015.
           [85]    K. Wu, J. Xiao, Y. Yi, D. Chen, X. Luo, and L. Ni, “Csi-based indoor                         [104]    C.-Y. Hsu, Y. Liu, Z. Kabelac, R. Hristov, D. Katabi, and C. Liu,




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




                   “Extracting gait velocity and stride length from surrounding radio                                    IEEE International Conference on Communications (ICC). IEEE,
                   signals,” in Proceedings of the CHI Conference on Human Factors in                                    2013, pp. 1512–1516.
                   Computing Systems. ACM, 2017, pp. 2116–2126.                                                 [124]    Y. Okamoto and O. Tomoaki, “Human activity classification and
          [105]    C.-Y. Hsu, A. Ahuja, S. Yue, R. Hristov, Z. Kabelac, and D. Katabi,                                   localization using bistatic three frequency cw radar,” in 2013 IEEE
                   “Zero-effort in-home sleep and insomnia monitoring using radio                                        International Conference on Communications (ICC). IEEE, 2013, pp.
                   signals,” Proceedings of the ACM on Interactive, Mobile, Wearable                                     4808–4812.
                   and Ubiquitous Technologies, vol. 1, no. 3, p. 59, 2017.                                     [125]    Y. Agata, T. Ohtsuki, and K. Toyoda, “Doppler analysis based fall
          [106]    M. Zhao, F. Adib, and D. Katabi, “Emotion recognition using wireless                                  detection using array antenna,” in 2018 IEEE International Conference
                   signals,” in Proceedings of the 22nd Annual International Conference                                  on Communications (ICC). IEEE, 2018, pp. 1–6.
                   on Mobile Computing and Networking. ACM, 2016, pp. 95–108.                                   [126]    S. Tomii and T. Ohtsuki, “Falling detection using multiple doppler
          [107]    W. Majewski, R. Carrara, and R. Goodman, “Spotlight synthetic                                         sensors,” in 2012 IEEE 14th International Conference on e-Health
                   aperture radar: Signal processing algorithms,” Norwood, MA: Artech                                    Networking, Applications and Services (Healthcom). IEEE, 2012, pp.
                   House, 1995.                                                                                          196–201.
          [108]    C. Hassapis and H. K. Nishihara, “Stereo camera intrusion detection                          [127]    W. He, K. Wu, Y. Zou, and Z. Ming, “Wig: Wifi-based gesture
                   system,” Apr. 30 2013, uS Patent 8,432,448.                                                           recognition system,” in Computer Communication and Networks
                                                                                                                         (ICCCN), 2015 24th International Conference on. IEEE, 2015, pp.
          [109]    J.-x. Wang, “Research and implementation of intrusion detection
                                                                                                                         1–7.
                   algorithm in video surveillance,” in International Conference on Audio,
                   Language and Image Processing (ICALIP). IEEE, 2016, pp. 345–348.                             [128]    L. Sun, S. Sen, D. Koutsonikolas, and K.-H. Kim, “Widraw: Enabling
                                                                                                                         hands-free drawing in the air on commodity wifi devices,” in Proceed-
          [110]    S. Ikeda, H. Tsuji, and T. Ohtsuki, “Indoor event detection with
                                                                                                                         ings of the 21st Annual International Conference on Mobile Computing
                   eigenvector spanning signal subspace for home or office security,”
                                                                                                                         and Networking. ACM, 2015, pp. 77–89.
                   IEICE transactions on communications, vol. 92, no. 7, pp. 2406–2412,
                   2009.                                                                                        [129]    M. Kumar, A. Veeraraghavan, and A. Sabharwal, “Distanceppg: Robust
                                                                                                                         non-contact vital signs monitoring using a camera,” Biomedical optics
          [111]    S. Ikeda, “Indoor event detection with signal subspace spanned by                                     express, vol. 6, no. 5, pp. 1565–1588, 2015.
                   eigenvector for home or office security,” IEICE Transactions on
                   Communications, vol. 92, no. 7, pp. 2406–2412, 2009.                                         [130]    Z. Jia, A. Bonde, S. Li, C. Xu, J. Wang, Y. Zhang, R. E. Howard,
                                                                                                                         and P. Zhang, “Monitoring a person’s heart rate and respiratory rate
          [112]    K. Nishimori, Y. Koide, D. Kuwahara, N. Honmay, H. Yamada,                                            on a shared bed using geophones,” in Proceedings of the 15th ACM
                   and M. Hideo, “Mimo sensor-evaluation on antenna arrangement,”                                        Conference on Embedded Network Sensor Systems. ACM, 2017, p. 6.
                   in Proceedings of the 5th European Conference on Antennas and
                   Propagation (EUCAP). IEEE, 2011, pp. 2771–2775.                                              [131]    Z. Jia, M. Alaziz, X. Chi, R. E. Howard, Y. Zhang, P. Zhang,
                                                                                                                         W. Trappe, A. Sivasubramaniam, and N. An, “Hb-phone: a bed-
          [113]    J. Hong and T. Ohtsuki, “State classification with array sensor using                                 mounted geophone-based heartbeat monitoring system,” in Proceedings
                   support vector machine for wireless monitoring systems,” IEICE                                        of the 15th International Conference on Information Processing in
                   transactions on communications, vol. 95, no. 10, pp. 3088–3095,                                       Sensor Networks. IEEE Press, 2016, p. 22.
                   2012.
                                                                                                                [132]    N. Patwari, J. Wilson, S. Ananthanarayanan, S. K. Kasera, and D. R.
          [114]    N. Honma, K. Nishimori, H. Sato, and Y. Tsunekawa, “Compact                                           Westenskow, “Monitoring breathing via signal strength in wireless
                   antenna arrangement for mimo sensor in indoor environment,” IEICE                                     networks,” IEEE Transactions on Mobile Computing, vol. 13, no. 8,
                   transactions on communications, vol. 96, no. 10, pp. 2491–2498, 2013.                                 pp. 1774–1786, 2014.
          [115]    J. Xiao, K. Wu, Y. Yi, L. Wang, and L. M. Ni, “Fimd: Fine-grained                            [133]    C. A. Johnston, “Network interface card for wireless asynchronous
                   device-free motion detection,” in IEEE 18th International Conference                                  transfer mode networks,” May 16 2000, uS Patent 6,064,649.
                   on Parallel and Distributed Systems (ICPADS). IEEE, 2012, pp.
                                                                                                                [134]    C. Li, V. M. Lubecke, O. Boric-Lubecke, and J. Lin, “A review on
                   229–235.
                                                                                                                         recent advances in doppler radar sensors for noncontact healthcare
          [116]    C. Wu, Z. Yang, Z. Zhou, X. Liu, Y. Liu, and J. Cao, “Non-invasive                                    monitoring,” IEEE Transactions on microwave theory and techniques,
                   detection of moving and stationary human with wifi,” IEEE Journal                                     vol. 61, no. 5, pp. 2046–2060, 2013.
                   on Selected Areas in Communications, vol. 33, no. 11, pp. 2329–2342,
                                                                                                                [135]    R. Tolimieri and M. An, “Cross-ambiguity function,” in Time-Frequency
                   2015.
                                                                                                                         Representations. Springer, 1998, pp. 141–150.
          [117]    S.-Y. Cho, T. W. Chow, and C.-T. Leung, “A neural-based crowd
                                                                                                                [136]    J. Hong and T. Ohtsuki, “Signal eigenvector-based device-free passive
                   estimation by hybrid global learning algorithm,” IEEE Transactions on
                                                                                                                         localization using array sensor,” IEEE Transactions on Vehicular
                   Systems, Man, and Cybernetics, Part B (Cybernetics), vol. 29, no. 4,
                                                                                                                         Technology, vol. 64, no. 4, pp. 1354–1363, 2015.
                   pp. 535–541, 1999.
                                                                                                                [137]    G. E. Hinton and R. R. Salakhutdinov, “Reducing the dimensionality of
          [118]    R. Ma, L. Li, W. Huang, and Q. Tian, “On pixel count based crowd                                      data with neural networks,” science, vol. 313, no. 5786, pp. 504–507,
                   density estimation for visual surveillance,” in IEEE Conference on                                    2006.
                   Cybernetics and Intelligent Systems (IEEE CIS), vol. 1, 2004, pp.
                   170–173.                                                                                     [138]    M. Li, Y. Meng, J. Liu, H. Zhu, X. Liang, Y. Liu, and N. Ruan, “When
                                                                                                                         csi meets public wifi: Inferring your mobile phone password via wifi
          [119]    J. Weppner and P. Lukowicz, “Collaborative crowd density estimation                                   signals,” in Proceedings of the 2016 ACM SIGSAC Conference on
                   with mobile phones,” in Proceedings of of ACM PhoneSense (Citeseer),                                  Computer and Communications Security. ACM, 2016, pp. 1068–1079.
                   2011.
          [120]    P. G. Kannan, S. P. Venkatagiri, M. C. Chan, A. L. Ananda, and L.-S.
                   Peh, “Low cost crowd counting using audio tones,” in Proceedings
                   of the 10th ACM Conference on Embedded Network Sensor Systems
                   (ACM Sensys), 2012, pp. 155–168.
          [121]    O. D. Lara, M. A. Labrador et al., “A survey on human activity
                   recognition using wearable sensors.” IEEE Communications Surveys
                   and Tutorials, vol. 15, no. 3, pp. 1192–1209, 2013.
          [122]    L. Xia and J. Aggarwal, “Spatio-temporal depth cuboid similarity
                   feature for activity recognition using depth camera,” in Proceedings
                   of the IEEE Conference on Computer Vision and Pattern Recognition,
                   2013, pp. 2834–2841.
          [123]    Y. Okamoto and T. Ohtsuki, “Human activity classification and
                   localization algorithm based on temporal-spatial virtual array,” in 2013




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.
This article has been accepted for publication in a future issue of this journal, but has not been fully edited. Content may change prior to final publication. Citation information: DOI 10.1109/COMST.2019.2934489, IEEE
                                                                                               Communications Surveys & Tutorials




                                         Jian Liu received his Ph.D. degree in Wireless                                               Chen Wang received his PhD degree in WINLAB
                                         Information Network Laboratory (WINLAB) in 2019                                              at Rutgers University in 2019 under the supervision
                                         at Rutgers University, under the supervision of Prof.                                        of Prof. Yingying Chen. He received his BS and MS
                                         Yingying Chen. His current research interests include                                        degrees from the University of Electronic Science and
                                         mobile sensing and computing, cybersecurity and                                             Technology of China, in 2009 and 2012. His research
                                         privacy, intelligent systems and smart healthcare.                                           interests include mobile computing, cyber security
                                         He is the recipient of the Best Paper Awards from                                            and privacy, and smart healthcare. He received
                                         IEEE SECON 2017 and IEEE CNS 2018. He also                                                   the Best Paper Award from IEEE Conference on
                                         received Best-in-session Presentation Award from                                             Communications and Network Security (CNS) 2018,
                                         IEEE INFOCOM 2017, and two Best Poster Award                                                 the Best Paper Award from ACM Conference on
                                         Runner-up from ACM MobiCom 2016 and ACM                                                      Information, Computer and Communications Security
          MobiCom 2018.                                                                                         (ASIACCS) 2016 and the Best Paper Award from IEEE Conference on
                                                                                                                Communications and Network Security (CNS) 2014.



                                         Hongbo Liu is an Assistant Professor of Computer
                                         Information and Graphics Technology Department
                                         at Indiana University Purdue University Indianapolis
                                         (IUPUI) since Aug. 2013. He received the Ph.D.
                                         degree in Electrical Engineering from the Stevens
                                         Institute of Technology in 2013. His research interests
                                         include mobile and pervasive computing, cyber
                                         security and privacy, and visible light communication.
                                         He is the recipient of the Best Paper Award from
                                         ACM MobiCom 2011, Best Paper Runner-up Award
                                         from IEEE CNS 2013 and Best Paper Award from
          IEEE CNS 2018.




                                   Yingying (Jennifer) Chen is a Professor of Electri-
                                   cal and Computer Engineering at Rutgers University
                                   and associate director of the Wireless Information
                                   Network Laboratory (WINLAB). She also leads the
                                   Data Analysis and Information Security (DAISY)
                                   Lab. Her research interests include smart healthcare,
                                   cyber security and privacy, Internet of Things, and
                                   mobile computing and sensing. She has published
                                   over 150 journals and referred conference papers
                                   in these areas. Her background is a combination
                                   of Physics, Computer Science and Computer Engi-
          neering. Prior to joining Rutgers, she was a tenured professor at Stevens
          Institute of Technology and had extensive industry experiences at Nokia
          (previously Alcatel-Lucent). She is the recipient of the NSF CAREER Award
          and Google Faculty Research Award. She also received NJ Inventors Hall
          of Fame Innovator Award. She is the recipient of the Best Paper Awards
          from IEEE CNS 2018, IEEE SECON 2017, ACM AsiaCCS 2016, IEEE
          CNS 2014 and ACM MobiCom 2011. She is the recipient of IEEE Region
## 1 Technological Innovation in Academic Award 2017; she also received the
          IEEE Outstanding Contribution Award from IEEE New Jersey Coast Section
          each year 2005 - 2009. Her research has been reported in numerous media
          outlets including MIT Technology Review, CNN, Fox News Channel, Wall
          Street Journal, National Public Radio and IEEE Spectrum. She has been
          serving on the editorial boards of IEEE/ACM Transactions on Networking
          (IEEE/ACM ToN), IEEE Transactions on Mobile Computing (IEEE TMC),
          IEEE Transactions on Wireless Communications (IEEE TWireless) and ACM
          Transactions on Privacy and Security.




                                         Yan Wang joins SUNY Binghamton University as
                                         an Assistant Professor in Department of Computer
                                         Science since Aug. 2015. He received his Ph.D. de-
                                         gree in Electrical Engineering from Stevens Institute
                                         of Technology. His research interests include Mobile
                                         and Pervasive Computing, Cybersecurity and Privacy,
                                         and Smart Healthcare. He is the recipient of the Best
                                         Paper Awards from IEEE CNS 2018, IEEE SECON
                                         2017 and ACM AsiaCCS 2016. He is the Winner
                                         of ACM MobiCom Student Research Competition,
                                         2013.




  1553-877X (c) 2019 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission. See http://www.ieee.org/publications_standards/publications/rights/index.html for more information.

