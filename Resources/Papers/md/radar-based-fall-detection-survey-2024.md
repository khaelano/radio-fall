                                                                                                                                                                                        1




## A Survey on Radar-Based Fall Detection
                                                     Shuting Hu, Siyang Cao, Nima Toosizadeh, Jennifer Barton, Melvin G. Hector, Mindy J. Fain



                                           Abstract—Fall detection, particularly critical for high-risk                 to live independently [6]. The CDC reports the annual medical
                                        demographics like the elderly, is a key public health concern                   costs related to non-fatal fall injuries is about $50 billion and
                                        where timely detection can greatly minimize harm. With the                      $754 million is spent related to fatal falls [7]. The growing
                                        advancements in radio frequency technology, radar has emerged
                                        as a powerful tool for human detection and tracking. Traditional                elderly population and subsequent increase in falls could strain
                                        machine learning algorithms, such as Support Vector Machines                    healthcare systems due to resource scarcity. The need for
                                        (SVM) and k-Nearest Neighbors (kNN), have shown promising                       efficient fall detection systems is evident, as prompt detection
                                        outcomes. However, deep learning approaches, notably Convolu-                   and reporting of falls can significantly reduce associated risks.




arXiv:2312.04037v1 [cs.RO] 7 Dec 2023
                                        tional Neural Networks (CNN) and Recurrent Neural Networks                         Over the years, various methodologies have been de-
                                        (RNN), have outperformed in learning intricate features and
                                        managing large, unstructured datasets. This survey offers an                    vised to address this concern, including (i) Sound-based ap-
                                        in-depth analysis of radar-based fall detection, with emphasis                  proaches [8] [9] [10] [11] [12] make use of acoustic signals or
                                        on Micro-Doppler, Range-Doppler, and Range-Doppler-Angles                       noises generated during a fall event. Microphones or wearable
                                        techniques. We discuss the intricacies and challenges in fall                   sound sensors detect these unique sound patterns, differen-
                                        detection and emphasize the necessity for a clear definition of                 tiating between regular noises and those produced by falls.
                                        falls and appropriate detection criteria, informed by diverse
                                        influencing factors. We present an overview of radar signal                     (ii) Motion-based methods [13] [14] [15] [16] primarily use
                                        processing principles and the underlying technology of radar-                   wearable devices equipped with accelerometers or gyroscopes.
                                        based fall detection, providing an accessible insight into machine              These sensors measure changes in velocities and orientations,
                                        learning and deep learning algorithms. After examining 74                       identifying patterns consistent with falls. (iii) Vision-based
                                        research articles on radar-based fall detection published since                 systems [17] [18] [19] [20] [21] utilize cameras to moni-
                                        2000, we aim to bridge current research gaps and underscore
                                        the potential future research strategies, emphasizing the real-                 tor individuals continuously. Through image processing and
                                        world applications possibility and the unexplored potential of                  machine learning, these systems can discern between regular
                                        deep learning in improving radar-based fall detection.                          movements and falls.
                                          Index Terms—Gesture, Posture and Facial Expressions, Hu-                         Non-radar sensors, including sound, motion, and vision-
                                        man Detection and Tracking, Machine Learning for Robot                          based solutions, offer innovative ways to detect falls. Sound
                                        Control                                                                         sensors are ubiquitous and non-intrusive but can generate
                                                                                                                        false alarms due to ambient noise [8] and may raise privacy
                                                                I. INTRODUCTION                                         concerns. Motion sensors are compact and respect privacy, but
                                                                                                                        they require frequent charging [22] and may cause discom-

                                        T     HE global rise in life expectancy, as reported by the
                                              World Health Organization (WHO) [1], has led to an
                                        aging population and increased risk of falls among the el-
                                                                                                                        fort [23]. Vision sensors are non-contact, and benefit from
                                                                                                                        advanced computer vision techniques, but they may intrude
                                                                                                                        on privacy [24] and could fail to detect falls in case of
                                        derly. The U.S. Centers for Disease Control and Prevention                      occlusions [17]. Despite their advantages, each sensor type has
                                        (CDC) [2] estimates that annually, one in four older adults                     inherent limitations, often making hybrid systems or combined
                                        in the United States experiences a fall. These falls, as the                    sensors an optimal choice for effective fall detection [25].
                                        leading cause of injury among older adults [3] [4], contribute                     Prior surveys on fall detection have been explored. Stud-
                                        significantly to unintentional injuries and deaths.                             ies [26] [27] [28] focused on motion-based fall detection
                                           Three decades ago, the National Institutes of Health                         using sensors. Meanwhile, authors [29] [30] [31] [32] [33]
                                        (NIH) [5] identified fractures as the most common serious                       observed the rise of vision-based detectors and machine
                                        injuries from falls in older persons, making them more sus-                     learning while noting performance and privacy issues. Zhang
                                        ceptible to falls. The fear of falling can also reduce the                      Zhong, et al [34] discussed the limitations of vision-based
                                        confidence of older adults in outdoor activities and their ability              techniques and the benefits of depth sensors. Xu Tao, et
                                           S. Hu and S. Cao are with the Department of Electrical and Computer          al. [35] identified a transition towards Radio Frequency (RF)
                                        Engineering, The University of Arizona, Tucson, AZ, 85721 USA. e-mail:          sensor-based methods. Recent reviews [36] [37] [38] [39]
                                        (shutinghu@arizona.edu, caos@arizona.edu).                                      underscored the need for real-time detection, real fall datasets,
                                           N. Toosizadeh is with the Department of Rehabilitation and Move-
                                        ment Sciences, Rutgers School of Health, Rutgers University. e-mail:            and privacy preservation, noting the rising use of radar for fall
                                        (nima.toosizadeh@rutgers.edu).                                                  detection. These articles provide vital insights into the state
                                           J. Barton is with the Department of Biomedical Engineering, The University   and challenges of current fall detection technologies.
                                        of Arizona, Tucson, AZ, 85721 USA. e-mail: (barton@arizona.edu).
                                           M.G. Hector and M.J. Fain are with the Department of Medicine,                  RF sensor-based methods for fall detection primar-
                                        The University of Arizona, Tucson, AZ, 85724 USA. e-mail:                       ily encompass Wi-Fi and radar technologies. While Wi-
                                        (Melvin.hector@banner.health.com, MFain@aging.arizona.edu).                     Fi has achieved considerable milestones in this domain
                                           This work was supported by National Institute of Biomedical Imaging
                                        and Bioengineering (NIBIB), National Institute of Health (NIH), Grant No.       [40] [41] [42] [43] [44] [45], it falls beyond the scope of this
                                        R21EB033454.                                                                    paper. Radar carries great potential to be one of the leading
                                                                                                                                       2



technologies in the near future [46] [47]. They are non-invasive    follows: Section II provides an understanding of falls. Section
and ensure privacy since they don’t capture visual images [48].     III discusses radar detection system fundamentals with associ-
They can detect through obstructions like walls [49], are           ated techniques. Section IV reviews radar-based fall detection
unaffected by environmental conditions such as lighting [48],       in Micro-Doppler, Range-Doppler, and Range-Doppler-Angle
and can operate efficiently in low power [50] [51]. Addition-       approaches. Section V discusses existing limitations and sug-
ally, they provide broad coverage while ensuring continuous         gests directions for future research. Section VI concludes the
monitoring [52] [53].                                               paper.
   Despite significant advancements in radar sensor technol-
ogy, no prior surveys specifically delve into the evolution and                      II. U NDERSTANDING FALLS
potential of radar-based fall detection. While the developments     A. The Challenges of Fall Detection
in radar-based fall detection over the past two decades are vast,
                                                                       Detecting a fall precisely is challenging due to its unpre-
there remains a void in consolidating this information into a
                                                                    dictable and sudden nature. A fall can be defined as uninten-
comprehensive survey. This paper aims to fill that gap. To
                                                                    tionally coming to the ground or a lower level without a violent
provide a clearer understanding, Figure 1 depicts a conceptual
                                                                    blow, loss of consciousness, or sudden paralysis [54] [55] [26].
representation of a radar-based fall detection robotic system,
                                                                       1) Factors and Variables Related to Falls: Extensive re-
showcasing how changes in a person’s movements, such as
                                                                    search has been conducted into the factors and variables
falls, can be detected and processed using radar technology.
                                                                    causing falls, revealing numerous demographic, psychological,
                                                                    functional, medical, and physical characteristics associated
                                                                    with falls. Intrinsic risk factors relate to an individual’s func-
                                                                    tional and health status including muscle strength, balance,
                                                                    motion, and sleep disorders [56] [57] [58] [59]. Extrinsic risk
                                                                    factors include environmental hazards such as slippery floors,
                                                                    poor lighting, improper use of assistive devices, and inap-
                                                                    propriate footwear [60]. Most researchers conclude that falls
                                                                    and recurrent falls result from a combination of intrinsic and
                                                                    extrinsic factors. The interrelation of these variables and the
                                                                    diversity of causes pose significant challenges to addressing
                                                                    the problem of falls.
                                                                       2) Challenges of Public Datasets: Capturing the moment of
                                                                    a fall is difficult due to the non-periodic nature of falls, leading
                                                                    to a scarcity of public datasets for fall incidents, especially
                                                                    real-life datasets. A few studies ventured into collecting and
                                                                    analyzing real fall events [61] [62] [63], while others choose
                                                                    to simulate the behavior of an elderly person [64] [65] [66].
                                                                    Notable datasets in the radar domain, such as studies by Su, Bo
Fig. 1: A radar-based fall detection robotic system. The radar
                                                                    Yu, et al. [67], Li, Haobo, et al. [68], Yao, Yicheng, et al. [69],
device emits waves that interact with the environment. As a
                                                                    Wang, Bo, et al. [70], revealed temporal and scene diversity
person moves or falls, the returning wave patterns change.
                                                                    in falls, which complicates the process of data collection and
These changes are captured and processed by the radar device,
                                                                    annotation.
and sent to a computer or screen. The computer processes and
visualizes the signal data, highlighting the point of a detected
fall and trigger an alarm.                                          B. Fall Categories and Scenarios
                                                                       Falls can occur in various settings, including living spaces,
   When selecting papers for our review, we established spe-        sleeping quarters, hallways, bathrooms, etc. Activities preced-
cific criteria to ensure the relevance and quality of the studies   ing a fall can range from transitioning on/off the bed, sofa,
chosen: (i) Our primary focus was on papers that directly           or wheelchair, walking, bending, dressing, bathing, to sitting
tackled themes related to “radar fall” in conjunction with terms    and standing. Capturing genuine fall incidents is a lengthy
such as “detection” and “detector”. (ii) We concentrated on         process that’s both time-consuming and labor-intensive. Given
publications from the past two decades. (iii) Emphasis was          the unpredictable nature of falls, especially among the elderly,
placed on studies that showcased clear methodologies and            gathering a sufficient amount of authentic fall data for research
thorough data analyses. We excluded articles that primarily         requires extended periods of observation. This prolonged data
delved into hardware or antenna design. (iv) Furthermore, to        collection process not only demands significant time but
recognize influential work, we filtered out articles with fewer     also incurs high human resource costs. Moreover, the ethical
than 10 citations before 2010 and those with under 5 citations      implications surrounding the collection of real fall data from
prior to 2015.                                                      vulnerable individuals, particularly the elderly, further com-
   To the best of our knowledge, this is the first survey paper     plicates the process. It is this combination of ethical concerns
specifically focused on the two-decade evolution of radar-          and the logistical challenges of long-term data collection that
based fall detection. The rest of the paper is organized as         underscores the reliance on simulated fall data in most existing
                                                                                                                                     3



research. Hence, most of the existing radar-based fall detection    the same concept. For the sake of clarity and consistency, we
research relies on simulated actions with data collection based     will use the term “recall” throughout the remainder of this
on the researchers’ definitions. Upon reviewing established         paper.
radar-based fall detection research, a recurring issue becomes         Specificity is another important measure and stands for the
evident: the absence of a standardized measure.                     proportion of actual negatives that are correctly identified.
   With the inherent challenges in designing and covering           It is defined as Spec = T NT+F    N
                                                                                                         P . While sensitivity/recall
all potential real-life scenarios due to the limited range of       focuses on the correct identification of positive cases (falls
activities, there’s a pressing call for researchers to aim for      in this context), Specificity ensures the correct identification
realism in the collected data, ensuring it accurately mirrors       of negative cases (non-fall activities).
actual fall situations. A possible approach includes setting           The F1 score, defined as F 1 = 2 × P       rec×Rec
                                                                                                                P rec+Rec , represents
up lab environments that closely mimic real-life settings           the harmonic mean of precision and recall. A perfect F1 score
with similar room sizes, furniture, and other elements. We          of 1.0 denotes perfect precision and recall. This score drops
recommend including diverse scenarios - dining room, living         to 0 if either precision or recall is zero.
room, bedroom, and restroom - with specific activities defined
within each. Participants should be encouraged to perform                 III. R ADAR FALL D ETECTION F UNDAMENTALS
their daily movements naturally, and the age distribution
of participants should be broad and not limited to younger          A. Radar Signal Processing
individuals. Lastly, including individuals who require assistive       In this section, we aim to provide a succinct overview of
devices like canes, walkers, or wheelchairs can enhance the         the fundamentals of radar signal processing. Our intention is
realism and applicability of the study.                             to offer non-specialists in the radar domain a foundational
                                                                    understanding, even if it might be cursory in nature. For
C. Quality Metrics for Fall Detection                               readers interested in a more comprehensive and in-depth ex-
                                                                    ploration of radar signal processing, we recommend consulting
   To develop a fall detection system applicable to real-life       the seminal book of Richards, Mark A. [71]. Radar, originally
scenarios, it is crucial to minimize the false alarm. Evaluation    an acronym for “Radio Detection and Ranging”, has become a
metrics for this system can be derived from the realm of binary     commonly used noun. Its applications can be broadly classified
classification statistics, which includes accuracy, precision,      into detection, tracking, and imaging.
recall, and the F1 score. In this context, “items of interest”
                                                                       1) Pulsed Radar: In a pulsed radar system, a transmitter
correspond to falls, with “positive” indicating fall events and
                                                                    dispatches a pulse that is then reflected back to the receiver
“negative” non-fall events. A correct prediction is labeled
                                                                    by an object. If the target is at distance R, the pulse traverses
“true”, whereas an incorrect prediction is “false”.
                                                                    a total distance of 2R. The required propagation time delay
   To simplify, we can define:
                                                                    is denoted as t0 , and the distance to the target can thus be
   1) True Positive (TP): A fall event is correctly identified as   expressed as R = ct20 . Here, c is the speed of electromagnetic
       a fall by the device.                                        wave propagation in free space. The maximum detectable
   2) False Positive (FP): A non-fall event is incorrectly          distance by the radar, termed as the maximum unambiguous
       identified as a fall by the device.                          range Rmax , corresponds to the furthest distance that a pulse
   3) True Negative (TN): A non-fall event is correctly iden-       can travel back and forth within the continuous transmission
       tified as non-fall by the device.                            pulse interval T , also known as the pulse repetition interval
   4) False Negative (FN): A fall event is incorrectly identified   (PRI). The pulse repetition frequency (PRF) is the reciprocal
       as non-fall by the device.                                   of T . Consequently, the maximum unambiguous range can be
Thus, items predicted correctly include TP and TN; items of         represented as Rmax = c·P2RI = 2·PcRF .
interest predicted encompass TP and FP; and items of interest          Pulsed radars offer several advantages, including long-range
comprise TP and FN.                                                 applications and the capacity to measure both range and
   Given the likely imbalance between Activities of Daily           velocity with ease. However, a significant downside is their
Living (ADL) and fall samples in fall detection tasks, accuracy     requirement for high peak powers to ensure a satisfactory
(Acc = T P +FT PP +T+T N
                       N +F N ) may not be the most suitable        average power.
performance measure. Precision (P rec = T PT+F   P
                                                   P ) and recall      2) Continuous Wave (CW) Radar: Unlike pulsed radar,
             TP
(Rec = T P +F N ), however, offer more meaningful evaluation        CW radar transmits signals uninterruptedly, equating average
metrics.                                                            power with peak power. CW radar listens for signal reflections
   Precision quantifies the proportion of identified falls that     from a target while transmitting, necessitating separate anten-
are actual falls, emphasizing the reduction of false alarms. A      nas for transmission and reception. A fixed frequency signal
score of 100.0% in precision signifies that all system alerts       is transmitted, and the reflections from objects are received
correspond to actual fall events. Recall, on the other hand,        and mixed with the transmitted carrier. Like pulsed radar, CW
measures the detection rate of all fall events; a score of          radar detects the radial velocity of a moving object, which
100.0% in recall implies perfect detection. It is worth noting      changes the frequency of the reflected signal. If the waveform
that in the machine learning community, “recall” is more            is reflected from a target at distance R0 , moving at a constant
commonly used, while in medical testing and some other              velocity v with a radial angle θ, an arbitrarily time-varying
fields, “Sensitivity” might be the preferred term to describe       range R(t) can be defined as R(t) = R0 + vcos(θ)t. The
                                                                                                                                    4



second component introduces a Doppler frequency shift in the        to produce an Intermediate Frequency (IF) signal. This fre-
radar return, which might consist of only a few Hz shifts on top    quency difference, fIF , is known as the “beat frequency”. Its
of a multi-GHz carrier signal. In addition to overall movement,     maximum value, the IF bandwidth, is dependent on the chip
different parts of the target may also exhibit additional micro-    hardware performance. For example, the AWR2243 radar de-
scale movements, causing further Doppler shifts. These are          vice from Texas Instruments (TI) offers a 20MHz bandwidth.
known as micro-Doppler effects and can provide valuable             Assuming the chirp’s slope is S = 20M Hz/us, the ideal
information for identifying target characteristics. For instance,   maximum range is: Rmax = c·P2RI = 2c · fIF  S = 150m. Given
Figure 2a, the natural arm swing of a walking person generates      a target at distance d from the radar, the IF signal will be a
a distinctive micro-Doppler effect. The stronger reflection from    sinusoidal wave x(t) = Asin(2πf0 t + ϕ0 ).
the human body, compared to the limbs, coupled with time-              The IF signal is valid from the moment the Receiver (RX)
frequency representation of micro-Doppler effects, offers a         chirp arrives, so its initial phase ϕ0 is ϕ0 = 2πfc τ . Where
wealth of information.                                              τ is the time difference between when the Transmitter (TX)
                                                                    chirp is transmitted and RX chirp arrives, and f0 = Sτ . From
                                                                    τ = 2dc and λ = c/fc , we can further deduce:

                                                                                                      S2d    4πd
                                                                                    x(t) = Asin(2π        t+     )               (1)
                                                                                                       c      λ
                                                                       Once the frequency f0 = S2d      c  of the sine wave at the
                                                                    moment of RX reception is known, we can calculate the
                                                                    distance d to the target. This is applicable for a single
  (a) Micro-Doppler. [52]               (b) Range-Doppler. [72]
                                                                    target. For multiple targets, there will be multiple IF signals,
                                                                    which can be distinguished using the Fast Fourier Transform
                                                                    (FFT), referred to as range-FFT. However, FFT theory suggests
                                                                    that the smallest frequency component resolvable within an
                                                                    observation window Tc is T1c . Given the bandwidth of FMCW
                                                                    radar is B = fstop − fstart = STc , we can determine the
                                                                    minimum resolvable distance between two targets, or range
                                                                                          c
                                                                    resolution Rres = 2B    .
                                                                       In Equation 1, the second component ϕ0 = 4πd    λ shows the
  (c) Range-Angles. [73]                   (d) Point-Cloud.         change in phase. We can discover the velocity information of
 Fig. 2: Different radar data types of a human movements.           the target by sending two chirp signals with time interval Tc .
                                                                    The target moves a distance of d = vTc within Tc time, and
   3) Frequency Modulated Continuous Wave (FMCW) Radar:             the phase change is ∆ϕ = 4πvT    λ . Once we know the phase
                                                                                                        c



While unmodulated CW radar can gauge velocity, it cannot            information, we can calculate the velocity of the target v =
                                                                     λ∆ϕ
measure target distance. To overcome this, FMCW radar trans-        4πTc . But since the measurement of velocity is based on the
mits a frequency-modulated sinusoidal signal continuously to        phase difference, the maximum unambiguous phase difference
measure both range and velocity. In this case, the frequency        is π, so our maximum unambiguous velocity vmax = 4Tλc .
                                                                       To differentiate multiple targets moving at the same distance
increases linearly with time, generating a signal also known as
                                                                    simultaneously, we need to execute another FFT across mul-
a chirp. Figure 3 provides an example of a transmitted chirp
                                                                    tiple consecutive chirps, known as velocity-FFT. We define
signal and the reflection from a single detected object.
                                                                    the spatial frequency ω = ∆ϕ = 4πvT        λ . The term spatial
                                                                                                                 c


                                                                    frequency refers to the phase-shift across consecutive chirps.
                                                                    Suppose we have two targets and the velocity difference is ∆v.
                                                                    The difference in the spatial frequency corresponding to these
                                                                    two objects is ∆ω = 4πT   λ ∆v. The theory of discrete Fourier
                                                                                                c


                                                                    transforms tells us that within N consecutive chirps cycles, the
                                                                    smallest spatial frequency component that can be resolved is
                                                                    2π                                                           λ
                                                                     N . We can get the minimum velocity resolution vres = 2N Tc .
                                                                    N consecutive chirps is called a frame, we define frame time
                                                                    Tf = N Tc , then vres = 2Tλf .
                                                                       In order to get the angle of the target relative to the radar,
                                                                    which is also called the angle of arrival (AoA), we need at least
                                                                    two RX antennas. We define the distance between two adjacent
                                                                    RX antennas as d, and the incident signal reflected from
          Fig. 3: FMCW radar IF frequency signal.                   the target reaches each antenna with a distance difference of
                                                                    dsinθ. We can do an angle-FFT along the antenna dimension
   Similar to CW radar, FMCW radar requires a “mixer”               {1, 2, ..., N }, and the differential distance result in a phase
that combines the signals from the transmitter and receiver         change in the FFT peak. The phase change from the target
                                                                                                                                    5



to the RX antenna can be expressed as ϕ = 2πfc t =                  (AAEs) [88], have marked a transformative shift in fall de-
2π λc dc = 2πd
            λ . The phase difference due to ∆d = dsinθ              tection. Their unique ability to automatically learn hierarchi-
is ∆ϕ = 2πdsinθ
              λ   . We can get θ = sin−1 ( λ∆ϕ2πd ). Similarly,
                                                                    cal features from raw data, coupled with their proficiency
the maximum unambiguous phase difference is π, so our               in handling large volumes of unstructured data, make them
maximum unambiguous angle θmax = sin−1 ( 2d    λ
                                                  ). We usually     particularly suited for complex tasks like analyzing radar sig-
choose d = λ/2 when designing antennas, because then we             nals. These deep architectures have been pivotal in bypassing
can get the largest field of view (FoV) θmax ∈ (−90◦ , 90◦ ).       manual feature engineering, often a cumbersome step in tradi-
   The angle resolution θres depends on the number of receiver      tional machine learning. As such, they present a more holistic
antennas available. The larger the number of antennas, the          approach, learning both low-level and high-level features that
better the resolution. Again, we let the spatial frequency          are essential for tasks. The choice of a specific DL architecture
ω = ∆ϕ = 2πdsinθλ   . The term spatial frequency here refers to     is primarily influenced by the dataset’s complexity, the nature
the phase shift across consecutive antennas in the RX array.        of the task, and the available computational power. Their
Suppose we have two targets and the AoA difference is ∆θ.           adaptability, scalability, and proficiency in capturing intricate
The difference in the spatial frequency corresponding to these      patterns are instrumental in pushing the boundaries of what’s
two objects ∆ω = 2πd                             2πd
                      λ (sin(θ + ∆θ) − sinθ) ≈ λ (cosθ∆θ).
                                                                    achievable in fall detection. Figure 4 shows us the difference
                             2π
Similarly, we need ∆ω ≥ N and can get the the minimum               between Machine Learning and Deep Learning.
angle resolution θres = dN λcosθ = N2 , when d = λ/2.

B. Machine Learning for Fall Detection
   In recent years, machine learning (ML) has gained promi-
nence as an instrumental technique in healthcare, especially
in fall detection and prediction among the elderly popula-
tion [33]. While traditional fall detection mechanisms pre-
dominantly utilize threshold-based strategies, they exhibit con-
straints concerning adaptability and precision [74]. In contrast,
the data-driven nature of ML models makes them adapt better
to various scenarios and individual fall patterns. Deep Learning
(DL), outside of ML, is another subset of Artificial Intelligence
(AI) and forms the computational foundation for fall detection.
ML empowers computers to acquire knowledge and execute
tasks without being explicitly programmed [75] [76]. DL,            Fig. 4: Distinguishing Machine Learning and Deep Learning.
a more specialized category within ML, builds on this by
leveraging layered architectures that emulate neural structures        CNNs exploit local data dependencies to minimize learnable
in the human brain, enabling non-linear data transforma-            weights, facilitating the construction of deeper networks that
tions [77] [78].                                                    recognize intricate features. 1D-CNNs are suitable for time-
   1) Machine Learning for Fall Detection: Traditional ML           series data, with kernels sliding along one dimension, treating
techniques, such as Naive Bayes (NB) Classifier [79], Support       different time-series as distinct filter channels. 2D-CNNs, on
Vector Machine (SVM) [80], Decision Trees (DT) [81], K-             the other hand, are optimal for data with multiple features
means & k-Nearest Neighbors (kNN) [82], and Principal               like image, making them apt for processing radar-derived data
Component Analysis (PCA) [83], have served as foundational          such as Micro-Doppler and Range-Doppler maps. Lastly, 3D-
methodologies in fall detection research. These algorithms,         CNNs are best suited for multidimensional data like radar
widely recognized for their interpretability and efficiency, have   point clouds, where features such as Doppler and/or Signal-
provided reliable results when applied to structured datasets.      to-noise ratio (SNR) serve as unique filter channels.
Additionally, they often require manual feature extraction,            Human activities are performed continuously over time,
where domain knowledge plays a crucial role in achieving            making the temporal dimension crucial for understanding be-
optimal performance. The choice of a specific ML technique          havior. While RNNs excel at processing sequential data, they
often stems from the nature of the data at hand, the desired fea-   suffer from short-term memory limitations. Advanced variants
ture representation, and the underlying problem’s complexity.       like Long Short-Term Memory (LSTM) and Gated Recurrent
Furthermore, the ease of implementation and interpretability        Units (GRU) address this by learning long-term dependencies
of traditional ML techniques have made them popular in              through additional gates. While RNNs handle hierarchical tree
scenarios where understanding the decision-making process is        structures, the sequence-to-sequence (Seq2Seq) model, using
pivotal.                                                            encoders and decoders, struggles with longer sequences. The
   2) Deep Learning for Fall Detection: Emerging as the             attention mechanism addresses this by weighting input signifi-
vanguard of modern computational approaches, deep learn-            cance, and transformers eschew RNNs altogether, focusing on
ing architectures, such as Convolutional Neural Networks            multi-head attention. Moreover, combining RNNs with CNNs
(CNNs) [84], Recurrent Neural Networks (RNNs) [85],                 facilitates spatio-temporal processing of data.
Variational Autoencoders (VAEs) [86], Generative Adversar-             Autoencoders, including VAEs, compress data into a latent
ial Networks (GANs) [87], and Adversarial Autoencoders              space to uncover underlying features, and can reconstruct
                                                                                                                                                                         6



                  TABLE I: Categorization of reviewed publications based on radar data formats and the classifiers
 Category                          Threshold     SVM       Bayes1     kNN2      LDA3      SVDD4      PCA       BPNN5       CNN6      RNN7      AE8      GAN     Other9
                                                  [92]                                                                      [113]
                                                  [93]                                                                      [114]
                                                  [94]                                                                      [115]
                                                  [95]                                                                      [116]
                                                                       [106]
                                                  [96]                                                                      [117]
                                                                       [107]
                                                  [97]                                                                      [118]     [125]
                                                                       [67]                                                                     [128]           [132]
                                                  [46]                                                                      [119]     [126]
 Micro-Doppler                      [91]                    [105]      [46]                [111]      [112]                                     [129]   [131]   [133]
                                                  [98]                                                                      [68]      [127]
                                                                       [108]                                                                    [130]           [111]
                                                  [99]                                                                      [120]     [121]
                                                                       [109]
                                                  [100]                                                                     [121]
                                                                       [110]
                                                  [101]                                                                     [122]
                                                  [102]                                                                     [123]
                                                  [103]                                                                     [70]
                                                  [104]                                                                     [124]
                                                  [72]
                                                                       [89]                                                 [141]
                                                  [134]
                                                                       [137]                                    [140]       [142]     [145]
 Range-Doppler                                    [135]                          [90]                 [90]                                      [146]
                                                                       [138]                                    [90]        [143]     [143]
                                                  [89]
                                                                       [139]                                                [144]
                                                  [136]
                                                                                                                            [73]
 Range-Doppler-Angles                                                  [147]                                    [148]                 [149]     [150]
                                                                                                                            [69]
 1
   Naive Bayes, or Sparse Bayesian classifier.
 2
   K-means, or k-Nearest Neighbors.
 3
   Linear discriminant analysis (LDA).
 4
   Support Vector Data Description (SVDD).
 5
   Back Propagation Neural Network (BPNN), Shallow Neural Networks.
 6
   Deep CNNs, and variants including ResNet, AlexNet, VGG, Inception, DenseNet, etc.
 7
   Deep RNNs, and variants including LSTM, GRU, Seq2Seq, Attention, Transformer, etc.
 8
   Including AE, VAE, AAE.
 9
   Quadratic Discriminant Analysis (QDA), Adaptive Boosting (AdaBoost), Decision Tree, Logistic Regression (LR), Mahalanobis Distance classifier.



or even generate new data samples. VAEs particularly use                                emerging around 2016. While Micro-Doppler remains a lead-
Bayesian statistics to learn data distributions. On the other                           ing method in fall detection, advancements in Printed Circuit
hand, GANs employ a generator and discriminator to pro-                                 Board (PCB) onboard antennas and the evolution of Multiple-
duce data samples without assuming a specific distribution,                             Input Multiple-Output (MIMO) technology have steered a
improving through iterative training until the generated sam-                           rising number of studies towards using Range-Doppler-Angles
ples are indistinguishable from real ones. AAEs merge VAE                               data since 2018. The progression of radar data types employed
and GAN concepts, leveraging adversarial loss for flexible                              in fall detection over the years can be visualized in Figure 5.
distribution choices in the latent space, thus comprising an
encoder-generator, decoder, and discriminator setup. For fall
detection applications, especially when labeling data is time-
consuming, one can consider employing unsupervised/semi-
supervised methods using VAEs, GANs, or AAEs.

     IV. R EVIEW OF R ADAR -BASED FALL D ETECTION
   This section presents a comprehensive review of 74 studies
focused on radar-based fall detection, which utilizes different
radar data formats such as Micro-Doppler, Range-Doppler,
and Range-Doppler-Angles, exemplified in Figure 2. The
reviewed researches are systematically classified into three
distinct groups based on their unique characteristics. Table I
offers a clear categorization of these studies, organizing them
according to the specific classifiers employed within each                              Fig. 5: Temporal Evolution of Radar Data Types Utilized in
category. It is important to note that for studies that utilized                        Fall Detection Research.
multiple classifiers or algorithms, only the one that reported
the best performance is showcased, unless the authors explic-                              While there is extensive research on radar-based human-
itly indicate a combination of methods, e.g., [46] [89] [90].                           related applications, such as human activity classifica-
   Early studies in fall detection primarily leveraged Micro-                           tion [151] [52] [53], and pose estimation [48] [152], this
Doppler data. However, with the introduction of FMCW radar                              review does not encompass those studies. Our focus is specif-
technology, research incorporating range information began                              ically on research that addresses fall detection as the primary
                                                                                                                                   7



problem, hence, the reviewed papers must either contain the           Please note that, in our discussion in Section II-C, we
keyword “fall” or primarily tackle the issue of fall detection.    emphasize the importance of precision, recall, and the F1 score
                                                                   as performance metrics for fall detection systems. However,
A. Fall Detection with Micro-Doppler                               the metrics reported in the reviewed papers varied. To make
   Micro-Doppler-based fall detection has seen significant ad-     the performance metrics consistent (i) For papers with a
vancements over the years, all centered around the correlation     provided confusion matrix, we computed the precision, recall,
between Doppler frequency and motion velocity.                     and F1 score directly; (ii) In cases where sensitivity was
   Liu, Liang, et al. laid the groundwork, using Mel-Frequency     mentioned, we treated it synonymously with recall while
Cepstral Coefficients (MFCC) to represent Doppler signatures       opting to overlook the specificity; (iii) When precision and
of human activities, employing SVM and kNN classifiers for         false alarm rate were present, we deduced the recall and
fall detection [106] [107] [92]. Karsmakers, Peter, et al. [93]    subsequently calculated the F1 score; (iv) For instances where
improved accuracy with a CW Doppler radar and the Global           only accuracy (most frequently in classification tasks where
Alignment (GA) kernel. Hong, Jihoon, et al. [94] addressed         a fall is one among multiple classes) or the Area Under the
non-line-of-sight (NLOS) effects, while Liu, Liang, et al. [104]   Receiver Operating Characteristics Curve (AUC) was reported,
developed practical applications for senior apartments.            we maintained the results as presented in the original stud-
   Later studies focused on feature extraction techniques and      ies. Even though we make these efforts, inconsistencies in
classifiers. Gadde, Ajay, et al. [132] used Time-Scale-based       Table II III IV are still inevitable. We believe that with the
signal analysis and the Mahalanobis Distance (MD) classi-          broader adoption of standardized metrics in the field, such
fier, while Su, Bo Yu, et al. [67] [108] combined Wavelet          inconsistencies will be reduced in future research.
Transform (WT) and a nearest neighbor classifier for improved
results.
                                                                   B. Fall Detection with Range-Doppler
   Deep learning entered the scene with Jokanovic, Branka,
et al. [112] [128] employing PCA and stacked Autoen-                  Radar signals in the Time-Frequency (TF) domain reveal
coders. Amin, Moeness G. et al. [46] [47] advocated for            velocities, accelerations, and Doppler terms of human body
elderly-specific radar monitoring algorithms and a larger          parts in motion [154]. These signals, combined with range
fall data repository. The use of CNNs gained traction with         information, allow for accurate positioning and movement
Zhou et al. [113] and Yoshino et al. [118] achieving high          tracking.
accuracies. Seyfioğlu, Mehmet Saygın, et al. [129] imple-            Stepped-Frequency Continuous Wave (SFCW) radar, fixed
mented a deep Convolutional Autoencoder (CAE) for clas-            both on the wall and on the ceiling, measures position and
sifying micro-Doppler signatures. Sadreazami, Hamidreza, et        speed and has been deemed suitable for fall detection and vital
al. [125] [114] [115] [116] [117] [110] [122] experimented         signs detection [154]. Studies have found characteristic signal
with various network architectures, while Anishchenko et           changes when falls occur, distinct from regular walking [72],
al. [119] improved reliability with two radars at a 90° angle.     [154], [155].
   Recent work by Lu et al. [131] and Chen et al. [111]               The integration of textural-based feature extraction methods,
explored three-stage fall detection approaches, reducing power     wideband radars, and SVM have been shown to optimize
consumption and improving detection. Studies by Wang et            false alarm problems in radar fall detection systems, achieving
al. [123] [70] focused on signal processing and soft-fall detec-   95.0% accuracy [72]. Utilizing Range-Doppler radars and deep
tion. Shah et al. [130] achieved an accuracy of 88.0% using        learning, researchers have achieved a success rate of 97.1%
an autoencoder. The latest research by Saho et al. [124] used      in minimizing false alarms [146]. Notably, this is the first
two Doppler radars installed in a restroom, highlighting the       paper to use Radar Cross-Section (RCS) information for fall
continuous evolution of Micro-Doppler-based fall detection,        detection [155].
moving from foundational exploration towards practical, real-         Researchers have shown that data fusion of two Ultraw-
world applications with improved accuracy.                         ide Band (UWB) radars using different fusion architectures
   Micro-Doppler-based fall detection has progressed from          improves performance and reduces false alarms, with Multi-
using basic classifiers to advanced deep learning models, en-      Sensor feature-level fusion yielding the best results [89]. Other
hancing accuracy and practicality. The work began with SVM         methods include using a TeraHertz (THz) FMCW radar to
and kNN classifiers, and has evolved to include the use of         extract features and analyze with different classifiers [140],
CNNs and GANs. Sensor configurations and fusion techniques         and using deformable deep CNN with a 1-class contrastive
have improved system performance, with multiple radars and         loss function achieving an accuracy of 99.5% [141]. Lastly,
sensor types reducing false alarms. Emphasizing real-world         the use of RadarNet, a structure of CNN followed by Inception
applications, like systems for senior apartments, demonstrates     modules, has shown an accuracy rate of 98.0% in target
the field’s maturity and readiness for deployment. Despite         classification for people or dogs [144].
challenges, like NLOS effects and data distortion, the advance-       In conclusion, the application of Range-Doppler in fall
ments in this field are promising for creating robust, efficient   detection has made significant progress, utilizing diverse radar
fall detection systems. Future research should focus on these      technologies and advanced machine learning techniques. Inte-
issues while exploring new deep learning techniques and            gration of machine learning methods has improved accuracy
sensor configurations. The summary table for Fall Detection        and reliability, while innovative approaches like RCS infor-
with Micro-Doppler is Table II.                                    mation and sensor data fusion have reduced false alarms.
                                                                                                                                                                         8



                                                            TABLE II: Fall Detection with Micro-Doppler
 Paper                                Radar             Classifier        Subjects       Motions                                    Performance
 Liu, Liang, et al. [106]             Doppler           kNN               3              109 falls, 341 non-falls                   AUC=0.974
 Liu, Liang, et al. [107]             Doppler           kNN               3              109 falls, 341 non-falls                   AUC=0.979
 Liu, Liang, et al. [92]              Doppler           SVM               2              216 falls, 1158 non-falls                  AUC=0.996
 Karsmakers, Peter, et al. [93]       Doppler           SVM               2              4 activities, 60 examples                  Acc=95.0%
 Hong, Jihoon, et al. [94]            Doppler           SVM               -              4 activities, 80 examples                  AUC=0.964
 Wu, Meng, et al. [95]                Doppler           SVM               -              3 activities, 30 examples                  Acc=100.0%
 Liu, Liang, et al. [104]             Doppler           SVM               1              72 falls, 98 non-falls                     AUC=0.980
 Gadde, Ajay, et al. [132]            Doppler           MD                2              10 falls, 10 non-falls                     Prec=100.0%, Rec=100.0%, F1=100.0%
 Rivera, Luis      Ramirez,      et   Doppler           MD                2              8 activities, 80 examples                  Prec=100.0%, Rec=97.5%, F1=98.7%
 al. [133]
 Garripoli, Carmine, et al. [96]      Doppler           SVM               16             4 activities, 65 falls                     Prec=100.0%, Rec=100.0%, F1=100.0%
 Su, Bo Yu, et al. [67]               Doppler           kNN               2              105 falls, 990 non-falls                   AUC=0.960, Rec=97.1%
 Wu, Qisong, et al. [105]             Doppler           Bayes             2              8 activities, 80 examples                  -
 Jokanovic, Branka, et al. [97]       Doppler           SVM               2              5 activities, 32 falls and 32 non-falls    AUC=0.938
 Amin, Moeness, et al. [153]          Doppler           -                 -              20,000 samples                             -
 Amin, Moeness, et al. [91]           Doppler           Threshold         5              20,000 samples                             Rec=87.5%
 Jokanovic,       Branka,        et   Doppler           PCA               -              4 activities, 60 examples                  Acc=90.0%
 al. [112]
 Jokanovic,       Branka,        et   Doppler           AE                -              4 activities, 120 examples                 Acc=87.0%
 al. [128]
 Amin, Moeness, et al. [46]           Doppler           SVM, kNN          1              19 types of falls, 14 types of non-falls   Prec=100.0%, Rec=82.0%
 Liu, Liang, et al. [98]              Doppler           SVM               6              real-life senior resident activities       2.0/week false alarms, Rec=100.0%
 Shrestha, A., et al. [99]            FMCW              SVM               6              7 activities                               Acc=94.0%
 Li, Haobo, et al. [100]              FMCW              SVM               16             10 activities                              Acc=91.3%
 Su, Bo Yu, et al. [108]              Doppler           kNN               1              real-life senior resident activities       8.6/day false alarms, Rec=100.0%
 Seyfioğlu, Mehmet Saygın, et        Doppler           CAE               11             12 activities                              Acc=94.2%
 al. [129]
 Sadreazami, Hamidreza, et            UWB               LSTM              5              121 falls, 85 non-falls                    Prec=95.0%, Rec=88.5%, F1=91.6%
 al. [125]
 Erol, Baris, et al. [109]            Doppler           PCA               14             6 activities                               Rec=97.0%
 Zhou, Xu, et al. [113]               Doppler           CNN               3              4 activities                               Acc=99.85%
 Sadreazami, Hamidreza, et            UWB               CNN               5              121 falls, 85 non-falls                    Prec=94.2%, Rec=93.4%, F1=93.8%
 al. [114]
 Sadreazami, Hamidreza, et            UWB               CNN               5              121 falls, 85 non-falls                    Prec=96.1%, Rec=96.7%, F1=96.4%
 al. [115]
 Sadreazami, Hamidreza, et            UWB               CNN               10             187 falls, 149 non-falls                   Prec=96.2%, Rec=90.9%, F1=93.5%
 al. [116]
 Sadreazami, Hamidreza, et            UWB               CNN               10             1870 falls, 1490 non-falls                 Prec=93.6%, Rec=90.4%, F1=92.0%
 al. [117]
 Yoshino, Haruka, et al. [118]        Doppler           CNN               10             2 types of falls, 2 types of non-falls     Prec=95.0%
 Li, Haobo, et al. [101]              FMCW              SVM               16             6 activities                               Acc=87.3%
 Anishchenko,       Lesya,       et   Doppler           CNN               5              175 falls, 175 non-falls                   Prec=100.0%, Rec=98.6%, F1=99.3%
 al. [119]
 Alnaeb, Ali, et al. [102]            Doppler           SVM               5              50 falls, 50 non-falls                     Acc=100.0%
 Li, Haobo, et al. [126]              FMCW              LSTM              16             6 activities                               Acc=96.0%
 Li, Haobo, et al. [68]               FMCW              CNN               14             12 activities                              Acc=84.0%
 Sadreazami, Hamidreza, et            UWB               kNN               5              6 activities                               Prec=94.3%, Rec=100.0%, F1=97.1%
 al. [110]
 Chuma, Euclides Lourenço, et        Doppler           CNN               6              5 activities                               Acc=99.9%
 al. [120]
 Maitre, Julien, et al. [121]         UWB               CNN-LSTM          10             60 falls, 600 non-falls                    Acc=90.0%
 Lu, Jincheng, et al. [131]           Doppler           GAN               3              14 activities                              Prec=91.8%, Rec=93.3%, F1=92.6%
 Sadreazami, Hamidreza, et            UWB               CNN               10             187 falls, 149 non-falls                   Prec=98.4%, Rec=94.4%, F1=96.28%
 al. [122]
 Hanifi, Khadija, et al. [103]        Doppler           SVM               10             543 falls and 675 non-falls                Prec=88.0%, Rec=87.0%, F1=88.0%
 Chen, Mengxia, et al. [111]          UWB               SVDD, MD          11             9 activities                               Prec=99.6%, Rec=97.6%, F1=98.6%
 Wang, Ping, et al. [123]             UWB               CNN               9              3 activities                               Prec=91.7%, Rec=95.7%, F1=91.9%
 Shah, Syed Aziz, et al. [130]        FMCW              AE                99             6 activities                               Acc=88.0%
 Wang, Bo, et al. [70]                FMCW              CNN               12             29 activities                              Rec=95.8%
 Imamura,        Takayuki,       et   Doppler           LSTM              2              6 activities                               Prec=95.2%, Rec=96.6%, F1=95.9%
 al. [127]
 Saho, Kenshi, et al. [124]           Doppler           CNN               21             8 activities                               Acc=95.6%

Note:
   •    Acc (Accuracy): Represents the proportion of samples that are correctly predicted out of all the samples.
   •    Prec (Precision or Positive Predictive Value): Out of the samples predicted as positive, the proportion that are actually positive.
   •    Rec (Recall or Sensitivity or True Positive Rate): The proportion of actual positive samples that are correctly predicted as positive by the model.
   •    AUC: Represents the Area Under the receiver operating characteristics (ROC) Curve.
                                                                                                                                                         9



                                               TABLE III: Fall Detection with Range-Doppler
 Paper                              Radar      Classifier      Subjects   Motions                                     Performance
 Mercuri, M., et al. [154]          SFCW       -               1          3 activities                                -
 Erol, Baris, et al. [72]           UWB        SVM             4          4 activities, 106 samples                   Prec=97.7%, Rec=94.7%, F1=96.2%
 Peng, Zhengyu, et al. [155]        FMCW       -               1          3 activities                                -
 Erol, Baris, et al. [134]          UWB        SVM             4          4 activities, 106 samples                   Prec=99.6%, Rec=99.6%, F1=100.0%
 Wang, Haofei, et al. [156]         SFCW       -               1          2 activities                                -
 Erol, Baris, et al. [135]          UWB        SVM             4          25 falls, 47 non-falls                      Prec=100.0%, Rec=95.0%, F1=97.5%
 Erol, Baris, et al. [89]           UWB        kNN, SVM        3          4 activities                                Prec=97.0%, Rec=95.0%, F1=95.9%
 Jokanovic,      Branka,       et   FMCW       AE              3          4 activities, 117 falls and 291 non-falls   Prec=88.2%, Rec=78.9%, F1=83.4%
 al. [146]
 Erol, Baris, et al. [137]          UWB        kNN             6          4 activities                                Prec=99.1%, Rec=96.6%, F1=97.9%
 Ding, Chuanwei, et al. [138]       FMCW       kNN             3          6 activities                                Acc=95.5%
 Ding, Chuanwei, et al. [139]       FMCW       kNN             8          6 activities                                Acc=91.9%
 He, Mi, et al. [140]               FMCW       BPNN            10         300 falls, 300 non-falls                    Prec=84.3%, AUC=0.932
 Erol, Baris, et al. [90]           FMCW       PCA,     LDA,   14         5 activities                                Acc=97.2%
                                               BPNN
 Shankar, Yogesh, et al. [141]      FMCW       CNN             8          302 falls, 942 non-falls                    Acc=99.5%
 Bhattacharya,     Abhijit,    et   FMCW       CNN             2          3 activities                                -
 al. [144]
 Wang, Bo, et al. [142]             FMCW       CNN             11         4 types of falls, 3 types of non-falls      Rec=99.6%, Acc=98.7%
 Ma, Liang, et al. [143]            UWB        CNN-LSTM        5          6 activities                                Rec=98.0%, Acc=95.8%
 Liang, Tingxuan, et al. [145]      FMCW       LSTM            -          100 falls, 300 non-falls                    Prec=98.9%, Rec=99.0%, F1=99.0%
 Ding, Chuanwei, et al. [136]       FMCW       SVM             3          6 activities                                Acc=95.0%


                                            TABLE IV: Fall Detection with Range-Angle Heatmaps
 Paper                              Radar      Classifier      Subjects   Motions                                     Performance
 Tian, Yonglong, et al. [73]        FMCW       CNN             140        40 activities                               Prec=91.9%, Rec=93.8%, F1=92.9%
 Sun, Yangfan, et al. [149]         FMCW       LSTM            1          7 activities                                Prec=100.0%, Rec=93.6%, F1=96.7%
 Ding, Congzhang, et al. [147]      FMCW       kNN             5          150 falls, 150 non-falls                    Acc=91.2%
 Su, Wei-Chih, et al. [157]         CW         -               1          3 activities                                -
 Yao, Yicheng, et al. [69]          FMCW       CNN             21         12 types of falls, 52 types of non-falls    Prec=97.5%, Rec=98.3%, F1=97.7%



Continued efforts are needed to enhance system robustness                    a 98.0% fall detection rate. Liang et al. [148] leveraged radar
and adaptability. Please refer to Table III for a summary of                 point clouds for human pose identification and 4G technology
fall detection methods with Range-Doppler.                                   for data visualization on a cloud platform. These works
                                                                             underscore the potential of radar point clouds in accurate fall
                                                                             detection. Refer to Table V for a summary.
C. Fall Detection with Range-Doppler-Angles                                     FMCW radar, combined with machine learning techniques,
   FMCW radio’s use of dual antenna arrays permits spatial                   has shown significant potential for accurate fall detection.
separability, enabling differentiation of reflections at varied              Key methods include range-angle heatmaps and 3D point-
elevations.                                                                  cloud data, which effectively discern falls. Performance is fur-
   1) Range-Angles Heatmaps: Aryokee, proposed by Tian et                    ther improved through algorithms like spatio-temporal CNNs.
al. [73], combines FMCW radar and spatio-temporal CNNs                       Additionally, hybrid technologies and unsupervised learning
to distinguish fall and stand-up actions, delivering a recall of             methods present innovative opportunities for this field. As
94.0% and a precision of 92.0%. Sun et al. [149] achieved su-                research continues, these techniques are expected to advance,
perior performance using LSTM over 3-D CNN for processing                    leading to more reliable fall detection solutions.
range-angle heatmaps.
   Ding et al. [147] used mmWave FMCW radar and kNN                                                  V. D ISCUSSION
for fall classification in a 3D coordinate system. Su et al.                    Micro-Doppler methodologies have become prominent in
[157] employed a hybrid radar and AoA estimation to calculate                fall detection research, largely because they easily extract
biometrics and detect falls, regardless of the fall direction.               signatures from radar Analog-to-digital conversion (ADC) raw
   Yao et al. [69] utilized three neural networks for feature                data, present this data as images suitable for image processing
extraction from FMCW radar-generated maps, achieving a                       techniques, and benefit from the early development of Doppler
recall of 98.3% and precision of 97.5%. These approaches                     radar technology. Moreover, radar’s most significant strength
highlight the utility of range-angle data in radar-based fall                is the measurement of velocity. The integration of range
detection. Refer to Table IV for a summary.                                  information in 2016 was a pivotal development, facilitating
   2) 3D Point-Cloud: Jin et al. [150] introduced an unsuper-                superior target distinction and noise reduction capabilities.
vised fall detection method, mmFall, that uses a variational                 This breakthrough revitalized interest in the field and prompted
RNN Autoencoder (VRAE) for point cloud analysis, achieving                   further research efforts. Afterward, the MIMO technology
                                                                                                                                                       10



                                         TABLE V: Fall Detection with 3D Point-Cloud
 Paper                       Radar       Classifier    Subjects     Motions                                  Performance
 Jin, Feng, et al. [150]     FMCW        VAE           2            50 falls, 200 non-falls                  Prec=96.1%, Rec=98.0%, F1=97.0%
 Liang, Jiye, et al. [148]   FMCW        BPNN          -            2 activities                             Prec=96.0%, Rec=94.1%, F1=95.2%



and the advent of PCB-integrated antennas have significantly           also facilitates cumulative scientific understanding. Adherence
enhanced radar’s capabilities, particularly in achieving three-        to standardized assessment benchmarks, such as precision,
dimensional spatial resolution. This has led to an upsurge in in-      recall, and F1 score, provides a common ground for evalu-
terest in Range-Doppler-Angles radar since 2018. Researchers           ating the effectiveness of different approaches. Ideally, data
are exploiting range-angle data, either through preserving             collection should mirror real-world scenarios closely, thereby
original information via range-angle maps or using advanced            bolstering the real-life applicability of research insights. The
3D point cloud data for efficient real-time detection.                 development and availability of a holistic, large-scale radar fall
   While radar-based methods for fall detection offer promis-          detection dataset could serve as a cornerstone for the field, po-
ing outcomes, it is crucial to acknowledge their challenges and        tentially attracting scholars from interdisciplinary backgrounds
limitations: (i) Environmental Factors: Radar sensors can be           to contribute their expertise.
affected by environmental factors, such as interference from
other electronic devices, and metal materials. (ii) Calibration                               VI. C ONCLUSION
and Setup: Proper calibration is crucial for the effectiveness of         In this survey, we navigated the multifaceted domain of fall
the radar system. Changes in room layout or the introduction           detection, initiating our exploration with an understanding of
of new large objects can affect the system’s performance.              falls and progressing toward an analysis of technologies in the
(iii) Hardware Limitations: The resolution of radar sensors            field. These form the foundation of today’s radar-based fall
can be affected by the hardware’s quality and capability, and          detection methods, as evidenced by our extensive review of
is relatively low. Higher-resolution systems often come at a           74 pivotal studies that showcase the technological evolution,
higher cost, posing challenges in large-scale implementations.         categorized into Micro-Doppler, Range-Doppler, and Range-
(iv) Real-world Applications: Despite experimental successes,          Doppler-Angles detection techniques. We hope that this review
transitioning these advancements to reliable real-world ap-            offers a sense of the history, development, and potential future
plications is an ongoing challenge. The variance observed              of radar for fall detection.
between laboratory and real-world outcomes accentuates the
need for bridging this gap.                                                                 ACKNOWLEDGMENT
   Potential strategies for enhancing the efficacy of fall de-           We sincerely thank the authors we referenced and greatly
tection systems involve a multi-faceted approach tailored to           value the constructive feedback from reviewers. We’re also
specific application scenarios. It is crucial to select radar          grateful for the financial support from the National Institutes
sensors that best match the desired performance criteria, such         of Health that enabled this research.
as optimal working distance, frame rate, and FoV. Depending
on the room’s layout and purpose, strategically placing sensors                                        R EFERENCES
in locations that can easily capture fall events is essential.            [1] Worldwide Health Organization, “Ageing and health,” 2022, [Accessed:
Defining the detection range and learning from known inter-                   1-October-2021]. [Online]. Available: https://www.who.int/news-room/
                                                                              fact-sheets/detail/ageing-and-health
ference sources to apply area masking can further optimize                [2] Centers for Disease Control and Prevention, “Keep on
detection. Moreover, customizing user parameters and estab-                   your feet—preventing older adult falls,” 2020, [Accessed: 16-
lishing methods for device recalibration are valuable steps                   December-2020]. [Online]. Available: https://www.cdc.gov/injury/
                                                                              features/older-adult-falls/index.html
toward precision. Exploring techniques like lifelong/continual            [3] G. Bergen, M. R. Stevens, and E. R. Burns, “Falls and fall injuries
learning can help the system adapt over time, refining its                    among adults aged ≥ 65 years—united states, 2014,” Morbidity and
performance based on continuous data ingestion. Periodically                  Mortality Weekly Report, vol. 65, no. 37, pp. 993–998, 2016.
                                                                          [4] B. Moreland, R. Kakara, and A. Henry, “Trends in nonfatal falls and
updating the system based on user feedback ensures that it                    fall-related injuries among adults aged≥ 65 years—united states, 2012–
remains responsive to real-world challenges and maintains user                2018,” Morbidity and Mortality Weekly Report, vol. 69, no. 27, p. 875,
trust. Additionally, the fusion of data from multiple sensors                 2020.
                                                                          [5] R. L. Berg, J. S. Cassells et al., “Falls in older persons: risk factors and
offers a broader perspective, enhancing the system’s accuracy                 prevention,” in The second fifty years: Promoting health and preventing
and robustness in diverse conditions.                                         disability. National Academies Press (US), 1992.
   While implementing these strategies promises a more re-                [6] D. Schoene, C. Heller, Y. N. Aung, C. C. Sieber, W. Kemmler, and
                                                                              E. Freiberger, “A systematic review on the influence of fear of falling
liable and efficient fall detection system, the foundation of                 on quality of life in older people: is there a role for falls?” Clinical
such advancements lies in robust research methodologies.                      interventions in aging, pp. 701–719, 2019.
This involves rigorous data collection protocols, consistent              [7] Centers for Disease Control and Prevention, “Cost of older
                                                                              adult falls,” 2020, [Accessed: 9-July-2020]. [Online]. Available:
statistical analyses, and emphasizing results reproducibility.                https://www.cdc.gov/falls/data/fall-cost.html
Equally important is the disclosure of specific radar param-              [8] M. Popescu, Y. Li, M. Skubic, and M. Rantz, “An acoustic fall detector
eters, including frequency range, power levels, and antenna                   system that uses sound height information to reduce the false alarm
                                                                              rate,” in 2008 30th Annual International Conference of the IEEE
specifications, which can greatly impact results. Promoting                   Engineering in Medicine and Biology Society. IEEE, 2008, pp. 4628–
the sharing of datasets not only enables peer verification but                4631.
                                                                                                                                                              11



 [9] Y. Li, K. Ho, and M. Popescu, “A microphone array system for auto-             [32] M. M. Islam, O. Tayan, M. R. Islam, M. S. Islam, S. Nooruddin, M. N.
     matic fall detection,” IEEE Transactions on Biomedical Engineering,                 Kabir, and M. R. Islam, “Deep learning based systems developed for
     vol. 59, no. 5, pp. 1291–1301, 2012.                                                fall detection: a review,” IEEE Access, vol. 8, pp. 166 117–166 137,
[10] M. S. Khan, M. Yu, P. Feng, L. Wang, and J. Chambers, “An                           2020.
     unsupervised acoustic fall detection system using source separation            [33] D. Singh, M. Gupta, R. Kumar, and A. J. Obaid, “A systematic
     for sound interference suppression,” Signal processing, vol. 110, pp.               review of human fall detection algorithms using machine learning,”
     199–210, 2015.                                                                      in International Conference on Signals, Machines, and Automation.
[11] S. M. Adnan, A. Irtaza, S. Aziz, M. O. Ullah, A. Javed, and M. T.                   Springer, 2022, pp. 579–588.
     Mahmood, “Fall detection through acoustic local ternary patterns,”             [34] Z. Zhang, C. Conly, and V. Athitsos, “A survey on vision-based fall
     Applied Acoustics, vol. 140, pp. 296–300, 2018.                                     detection,” in Proceedings of the 8th ACM international conference
[12] J. Lian, X. Yuan, M. Li, and N.-F. Tzeng, “Fall detection via inaudible             on PErvasive technologies related to assistive environments, 2015, pp.
     acoustic sensing,” Proceedings of the ACM on Interactive, Mobile,                   1–7.
     Wearable and Ubiquitous Technologies, vol. 5, no. 3, pp. 1–21, 2021.           [35] T. Xu, Y. Zhou, and J. Zhu, “New advances and challenges of fall
[13] J. Chen, K. Kwong, D. Chang, J. Luk, and R. Bajcsy, “Wearable sensors               detection systems: A survey,” Applied Sciences, vol. 8, no. 3, p. 418,
     for reliable fall detection,” in 2005 IEEE engineering in medicine and              2018.
     biology 27th annual conference. IEEE, 2006, pp. 3551–3554.                     [36] X. Wang, J. Ellul, and G. Azzopardi, “Elderly fall detection systems:
[14] P. Pierleoni, A. Belli, L. Palma, M. Pellegrini, L. Pernini, and S. Valenti,        A literature survey,” Frontiers in Robotics and AI, vol. 7, p. 71, 2020.
     “A high reliability wearable device for elderly fall detection,” IEEE
                                                                                    [37] A. Singh, S. U. Rehman, S. Yongchareon, and P. H. J. Chong, “Sensor
     Sensors Journal, vol. 15, no. 8, pp. 4544–4553, 2015.
                                                                                         technologies for fall detection systems: A review,” IEEE Sensors
[15] S. Jung, S. Hong, J. Kim, S. Lee, T. Hyeon, M. Lee, and D.-H. Kim,
                                                                                         Journal, vol. 20, no. 13, pp. 6889–6919, 2020.
     “Wearable fall detector using integrated sensors and energy devices,”
                                                                                    [38] S. Nooruddin, M. M. Islam, F. A. Sharna, H. Alhetari, and M. N. Kabir,
     Scientific reports, vol. 5, no. 1, p. 17081, 2015.
                                                                                         “Sensor-based fall detection systems: a review,” Journal of Ambient
[16] S. Mekruksavanich, P. Jantawong, N. Hnoohom, and A. Jitpattanakul,
                                                                                         Intelligence and Humanized Computing, pp. 1–17, 2022.
     “Wearable fall detection based on motion signals using hybrid deep
     residual neural network,” in International Conference on Multi-                [39] R. Tanwar, N. Nandal, M. Zamani, and A. A. Manaf, “Pathway of
     disciplinary Trends in Artificial Intelligence. Springer, 2022, pp. 216–            trends and technologies in fall detection: a systematic review,” in
     224.                                                                                Healthcare, vol. 10, no. 1. MDPI, 2022, p. 172.
[17] E. Auvinet, F. Multon, A. Saint-Arnaud, J. Rousseau, and J. Meunier,           [40] S. Palipana, D. Rojas, P. Agrawal, and D. Pesch, “Falldefi: Ubiquitous
     “Fall detection with multiple cameras: An occlusion-resistant method                fall detection using commodity wi-fi devices,” Proceedings of the ACM
     based on 3-d silhouette vertical distribution,” IEEE transactions on                on Interactive, Mobile, Wearable and Ubiquitous Technologies, vol. 1,
     information technology in biomedicine, vol. 15, no. 2, pp. 290–300,                 no. 4, pp. 1–25, 2018.
     2010.                                                                          [41] M. Zhao, T. Li, M. Abu Alsheikh, Y. Tian, H. Zhao, A. Torralba, and
[18] E. E. Stone and M. Skubic, “Fall detection in homes of older adults                 D. Katabi, “Through-wall human pose estimation using radio signals,”
     using the microsoft kinect,” IEEE journal of biomedical and health                  in Proceedings of the IEEE Conference on Computer Vision and Pattern
     informatics, vol. 19, no. 1, pp. 290–301, 2014.                                     Recognition, 2018, pp. 7356–7365.
[19] Z.-P. Bian, J. Hou, L.-P. Chau, and N. Magnenat-Thalmann, “Fall                [42] J. Ding and Y. Wang, “A wifi-based smart home fall detection system
     detection based on body part tracking using a depth camera,” IEEE                   using recurrent neural network,” IEEE Transactions on Consumer
     journal of biomedical and health informatics, vol. 19, no. 2, pp. 430–              Electronics, vol. 66, no. 4, pp. 308–317, 2020.
     439, 2014.                                                                     [43] T. Nakamura, M. Bouazizi, K. Yamamoto, and T. Ohtsuki, “Wi-fi-csi-
[20] W. Chen, Z. Jiang, H. Guo, and X. Ni, “Fall detection based on key                  based fall detection by spectrogram analysis with cnn,” in GLOBECOM
     points of human-skeleton using openpose,” Symmetry, vol. 12, no. 5,                 2020-2020 IEEE Global Communications Conference. IEEE, 2020,
     p. 744, 2020.                                                                       pp. 1–6.
[21] H. Ramirez, S. A. Velastin, I. Meza, E. Fabregas, D. Makris, and               [44] Z. Yang, Y. Zhang, and Q. Zhang, “Rethinking fall detection with wi-
     G. Farias, “Fall detection and activity recognition using human skeleton            fi,” IEEE Transactions on Mobile Computing, 2022.
     features,” Ieee Access, vol. 9, pp. 33 532–33 542, 2021.                       [45] T. Nakamura, M. Bouazizi, K. Yamamoto, and T. Ohtsuki, “Wi-fi-based
[22] J. Kim, S. Khan, P. Wu, S. Park, H. Park, C. Yu, and W. Kim, “Self-                 fall detection using spectrogram image of channel state information,”
     charging wearables for continuous health monitoring,” Nano Energy,                  IEEE Internet of Things Journal, vol. 9, no. 18, pp. 17 220–17 234,
     vol. 79, p. 105419, 2021.                                                           2022.
[23] T. Shimura, S. Sato, P. Zalar, and N. Matsuhisa, “Engineering the              [46] M. G. Amin, Y. D. Zhang, F. Ahmad, and K. D. Ho, “Radar signal pro-
     comfort-of-wear for next generation wearables,” Advanced Electronic                 cessing for elderly fall detection: The future for in-home monitoring,”
     Materials, p. 2200512, 2022.                                                        IEEE Signal Processing Magazine, vol. 33, no. 2, pp. 71–80, 2016.
[24] G. Mastorakis and D. Makris, “Fall detection system using kinect’s             [47] M. Amin, Radar for indoor monitoring: Detection, classification, and
     infrared sensor,” Journal of Real-Time Image Processing, vol. 9, pp.                assessment. CRC Press, 2017.
     635–646, 2014.
                                                                                    [48] A. Sengupta, F. Jin, R. Zhang, and S. Cao, “mm-pose: Real-time
[25] F. Liang, R. Hernandez, J. Lu, B. Ong, M. J. Moore, W. Sheng, and
                                                                                         human skeletal posture estimation using mmwave radars and cnns,”
     S. Zhang, “Collaborative fall detection using a wearable device and a
                                                                                         IEEE Sensors Journal, vol. 20, no. 17, pp. 10 032–10 044, 2020.
     companion robot,” in 2021 IEEE International Conference on Robotics
                                                                                    [49] J. Li, Z. Zeng, J. Sun, and F. Liu, “Through-wall detection of human
     and Automation (ICRA). IEEE, 2021, pp. 3684–3690.
                                                                                         being’s movement by uwb radar,” IEEE Geoscience and Remote
[26] N. Noury, A. Fleury, P. Rumeau, A. K. Bourke, G. Laighin, V. Rialle,
                                                                                         Sensing Letters, vol. 9, no. 6, pp. 1079–1083, 2012.
     and J.-E. Lundy, “Fall detection-principles and methods,” in 2007 29th
     annual international conference of the IEEE engineering in medicine            [50] B. Vandersmissen, N. Knudde, A. Jalalvand, I. Couckuyt, A. Bourdoux,
     and biology society. IEEE, 2007, pp. 1663–1666.                                     W. De Neve, and T. Dhaene, “Indoor person identification using a low-
[27] A. Ramachandran, A. Karuppiah et al., “A survey on recent advances                  power fmcw radar,” IEEE Transactions on Geoscience and Remote
     in wearable fall detection systems,” BioMed research international, vol.            Sensing, vol. 56, no. 7, pp. 3941–3952, 2018.
     2020, 2020.                                                                    [51] Y. Almalioglu, M. Turan, C. X. Lu, N. Trigoni, and A. Markham,
[28] T. G. Stavropoulos, A. Papastergiou, L. Mpaltadoros, S. Nikolopoulos,               “Milli-rio: Ego-motion estimation with low-cost millimetre-wave
     and I. Kompatsiaris, “Iot wearable sensors and devices in elderly care:             radar,” IEEE Sensors Journal, vol. 21, no. 3, pp. 3314–3323, 2020.
     A literature review,” Sensors, vol. 20, no. 10, p. 2826, 2020.                 [52] R. Zhang and S. Cao, “Real-time human motion behavior detection
[29] M. Mubashir, L. Shao, and L. Seed, “A survey on fall detection:                     via cnn using mmwave radar,” IEEE Sensors Letters, vol. 3, no. 2, pp.
     Principles and approaches,” Neurocomputing, vol. 100, pp. 144–152,                  1–4, 2018.
     2013.                                                                          [53] F. Jin, R. Zhang, A. Sengupta, S. Cao, S. Hariri, N. K. Agarwal,
[30] R. Igual, C. Medrano, and I. Plaza, “Challenges, issues and trends in               and S. K. Agarwal, “Multiple patients behavior detection in real-time
     fall detection systems,” Biomedical engineering online, vol. 12, no. 1,             using mmwave radar and deep cnns,” in 2019 IEEE Radar Conference
     pp. 1–24, 2013.                                                                     (RadarConf). IEEE, 2019, pp. 1–6.
[31] A. Biswas and B. Dey, “A literature review of current vision based             [54] G. MJ, “The prevention of falls in later life: a report of the kellogg
     fall detection methods,” Advances in Communication, Devices and                     international work group on the prevention of falls by the elderly,” Dan
     Networking: Proceedings of ICCDN 2019 3, pp. 411–421, 2020.                         Med Bull, vol. 34, no. 4, pp. 1–24, 1987.
                                                                                                                                                               12



[55] A. A. Zecevic, A. W. Salmoni, M. Speechley, and A. A. Vandervoort,            [77] Y. LeCun, Y. Bengio, and G. Hinton, “Deep learning,” nature, vol. 521,
     “Defining a fall and reasons for falling: comparisons among the views              no. 7553, pp. 436–444, 2015.
     of seniors, health care providers, and the research literature,” The          [78] I. Goodfellow, Y. Bengio, and A. Courville, Deep learning. MIT
     Gerontologist, vol. 46, no. 3, pp. 367–376, 2006.                                  press, 2016.
[56] G. S. Brassington, A. C. King, and D. L. Bliwise, “Sleep problems as a        [79] S. Xu, “Bayesian naı̈ve bayes classifiers to text classification,” Journal
     risk factor for falls in a sample of community-dwelling adults aged 64–            of Information Science, vol. 44, no. 1, pp. 48–59, 2018.
     99 years,” Journal of the American Geriatrics Society, vol. 48, no. 10,       [80] D. A. Pisner and D. M. Schnyer, “Support vector machine,” in Machine
     pp. 1234–1240, 2000.                                                               learning. Elsevier, 2020, pp. 101–121.
[57] T. Kvelde, C. McVeigh, B. Toson, M. Greenaway, S. R. Lord, K. Del-            [81] Y. Izza, A. Ignatiev, and J. Marques-Silva, “On explaining decision
     baere, and J. C. Close, “Depressive symptomatology as a risk factor                trees,” arXiv preprint arXiv:2010.11034, 2020.
     for falls in older people: systematic review and meta-analysis,” Journal      [82] K. Mittal, G. Aggarwal, and P. Mahajan, “Performance study of k-
     of the American Geriatrics Society, vol. 61, no. 5, pp. 694–706, 2013.             nearest neighbor classifier and k-means clustering for predicting the
[58] M. E. Tinetti, M. Speechley, and S. F. Ginter, “Risk factors for falls             diagnostic accuracy,” International Journal of Information Technology,
     among elderly persons living in the community,” New England journal                vol. 11, pp. 535–540, 2019.
     of medicine, vol. 319, no. 26, pp. 1701–1707, 1988.                           [83] X. XIE, “Principal component analysis,” Wiley interdisciplinary re-
[59] L. K. Anderson and K. Lane, “Characteristics of falls and recurrent falls          views, 2019.
     in residents of an aging in place community: A case-control study,”           [84] A. Krizhevsky, I. Sutskever, and G. E. Hinton, “Imagenet classification
     Applied nursing research, vol. 51, p. 151190, 2020.                                with deep convolutional neural networks,” Advances in neural infor-
[60] C. Boelens, E. E. Hekman, and G. J. Verkerke, “Risk factors for falls              mation processing systems, vol. 25, 2012.
     of older citizens,” Technology and Health care, vol. 21, no. 5, pp.           [85] Y. Yu, X. Si, C. Hu, and J. Zhang, “A review of recurrent neural
     521–533, 2013.                                                                     networks: Lstm cells and network architectures,” Neural computation,
[61] E. Vlaeyen, M. Deschodt, G. Debard, E. Dejaeger, S. Boonen, T. Goe-                vol. 31, no. 7, pp. 1235–1270, 2019.
     demé, B. Vanrumste, and K. Milisen, “Fall incidents unraveled: a series      [86] C. Doersch, “Tutorial on variational autoencoders,” arXiv preprint
     of 26 video-based real-life fall events in three frail older persons,” BMC         arXiv:1606.05908, 2016.
     geriatrics, vol. 13, no. 1, pp. 1–10, 2013.                                   [87] A. Aggarwal, M. Mittal, and G. Battineni, “Generative adversarial net-
[62] S. N. Robinovitch, F. Feldman, Y. Yang, R. Schonnop, P. M. Leung,                  work: An overview of theory and applications,” International Journal
     T. Sarraf, J. Sims-Gould, and M. Loughin, “Video capture of the                    of Information Management Data Insights, vol. 1, no. 1, p. 100004,
     circumstances of falls in elderly people residing in long-term care:               2021.
     an observational study,” The Lancet, vol. 381, no. 9860, pp. 47–54,           [88] A. Makhzani, J. Shlens, N. Jaitly, I. Goodfellow, and B. Frey, “Adver-
     2013.                                                                              sarial autoencoders,” arXiv preprint arXiv:1511.05644, 2015.
[63] K. Rapp, C. Becker, I. D. Cameron, H.-H. König, and G. Büchele,             [89] B. Erol, M. G. Amin, and B. Boashash, “Range-doppler radar sensor
     “Epidemiology of falls in residential aged care: analysis of more than             fusion for fall detection,” in 2017 IEEE Radar Conference (Radar-
     70,000 falls from residents of bavarian nursing homes,” Journal of the             Conf). IEEE, 2017, pp. 0819–0824.
     American Medical Directors Association, vol. 13, no. 2, pp. 187–e1,           [90] B. Erol and M. G. Amin, “Radar data cube processing for human
     2012.                                                                              activity recognition using multisubspace learning,” IEEE Transactions
[64] B. Kwolek and M. Kepski, “Human fall detection on embedded                         on Aerospace and Electronic Systems, vol. 55, no. 6, pp. 3617–3628,
     platform using depth maps and wireless accelerometer,” Computer                    2019.
     methods and programs in biomedicine, vol. 117, no. 3, pp. 489–501,            [91] M. Amin, F. Ahmad, and B. Jokanovic, “Personalized fall detection
     2014.                                                                              and classification through walls and in heavy indoor clutter,” in Radar
[65] “Tst fall detection dataset v2,” 2016. [Online]. Available: https:                 Sensor Technology XIX; and Active and Passive Signatures VI, vol.
     //dx.doi.org/10.21227/H2QP48                                                       9461. SPIE, 2015, pp. 114–122.
[66] M. S. Alzahrani, S. K. Jarraya, M. A. Salamah, and H. Ben-Abdallah,           [92] L. Liu, M. Popescu, K. Ho, M. Skubic, and M. Rantz, “Doppler
     “Fallfree: Multiple fall scenario dataset of cane users for monitoring             radar sensor positioning in a fall detection system,” in 2012 Annual
     applications using kinect,” in 2017 13th International Conference on               International Conference of the IEEE Engineering in Medicine and
     Signal-Image Technology & Internet-Based Systems (SITIS). IEEE,                    Biology Society. IEEE, 2012, pp. 256–259.
     2017, pp. 327–333.                                                            [93] P. Karsmakers, T. Croonenborghs, M. Mercuri, D. Schreurs, and
[67] B. Y. Su, K. Ho, M. J. Rantz, and M. Skubic, “Doppler radar fall                   P. Leroux, “Automatic in-door fall detection based on microwave radar
     activity detection using the wavelet transform,” IEEE Transactions on              measurements,” in 2012 9th European Radar Conference. IEEE, 2012,
     Biomedical Engineering, vol. 62, no. 3, pp. 865–875, 2014.                         pp. 202–205.
[68] H. Li, J. Le Kernec, A. Mehul, S. Z. Gurbuz, and F. Fioranelli,               [94] J. Hong, S. Tomii, and T. Ohtsuki, “Cooperative fall detection using
     “Distributed radar information fusion for gait recognition and fall                doppler radar and array sensor,” in 2013 IEEE 24th Annual Interna-
     detection,” in 2020 IEEE Radar Conference (RadarConf20). IEEE,                     tional Symposium on Personal, Indoor, and Mobile Radio Communi-
     2020, pp. 1–6.                                                                     cations (PIMRC). IEEE, 2013, pp. 3492–3496.
[69] Y. Yao, C. Liu, H. Zhang, B. Yan, P. Jian, P. Wang, L. Du, X. Chen,           [95] M. Wu, X. Dai, Y. D. Zhang, B. Davidson, M. G. Amin, and
     B. Han, and Z. Fang, “Fall detection system using millimeter wave                  J. Zhang, “Fall detection based on sequential modeling of radar signal
     radar based on neural network and information fusion,” IEEE Internet               time-frequency features,” in 2013 IEEE International Conference on
     of Things Journal, 2022.                                                           Healthcare Informatics. IEEE, 2013, pp. 169–174.
[70] B. Wang, Z. Zheng, and Y.-X. Guo, “Millimeter-wave frequency                  [96] C. Garripoli, M. Mercuri, P. Karsmakers, P. J. Soh, G. Crupi, G. A.
     modulated continuous wave radar-based soft fall detection using pattern            Vandenbosch, C. Pace, P. Leroux, and D. Schreurs, “Embedded dsp-
     contour-confined doppler-time maps,” IEEE Sensors Journal, vol. 22,                based telehealth radar system for remote in-door fall detection,” IEEE
     no. 10, pp. 9824–9831, 2022.                                                       journal of biomedical and health informatics, vol. 19, no. 1, pp. 92–
[71] M. A. Richards, Fundamentals of radar signal processing. Mcgraw-                   101, 2014.
     hill New York, 2005, vol. 1.                                                  [97] B. Jokanovic, M. G. Amin, Y. D. Zhang, and F. Ahmad, “Multi-
[72] B. Erol, M. G. Amin, B. Boashash, F. Ahmad, and Y. D. Zhang,                       window time–frequency signature reconstruction from undersampled
     “Wideband radar based fall motion detection for a generic elderly,” in             continuous-wave radar measurements for fall detection,” IET Radar,
     2016 50th Asilomar Conference on Signals, Systems and Computers.                   Sonar & Navigation, vol. 9, no. 2, pp. 173–183, 2015.
     IEEE, 2016, pp. 1768–1772.                                                    [98] L. Liu, M. Popescu, M. Skubic, M. Rantz, and P. Cuddihy, “An au-
[73] Y. Tian, G.-H. Lee, H. He, C.-Y. Hsu, and D. Katabi, “Rf-based fall                tomatic in-home fall detection system using doppler radar signatures,”
     monitoring using convolutional neural networks,” Proceedings of the                Journal of Ambient Intelligence and Smart Environments, vol. 8, no. 4,
     ACM on Interactive, Mobile, Wearable and Ubiquitous Technologies,                  pp. 453–466, 2016.
     vol. 2, no. 3, pp. 1–24, 2018.                                                [99] A. Shrestha, J. Le Kernec, F. Fioranelli, E. Cippitelli, E. Gambi, and
[74] A. K. Bourke and G. M. Lyons, “A threshold-based fall-detection                    S. Spinsante, “Feature diversity for fall detection and human indoor
     algorithm using a bi-axial gyroscope sensor,” Medical engineering &                activities classification using radar systems,” 2017.
     physics, vol. 30, no. 1, pp. 84–90, 2008.                                    [100] H. Li, A. Shrestha, F. Fioranelli, J. Le Kernec, H. Heidari, M. Pepa,
[75] Z.-H. Zhou, Machine learning. Springer Nature, 2021.                               E. Cippitelli, E. Gambi, and S. Spinsante, “Multisensor data fusion
[76] M. I. Jordan and T. M. Mitchell, “Machine learning: Trends, perspec-               for human activities classification and fall detection,” in 2017 IEEE
     tives, and prospects,” Science, vol. 349, no. 6245, pp. 255–260, 2015.             sensors. IEEE, 2017, pp. 1–3.
                                                                                                                                                              13



[101] H. Li, A. Shrestha, H. Heidari, J. Le Kernec, and F. Fioranelli,            [121] J. Maitre, K. Bouchard, and S. Gaboury, “Fall detection with uwb
      “Activities recognition and fall detection in continuous data streams             radars and cnn-lstm architecture,” IEEE journal of biomedical and
      using radar sensor,” in 2019 IEEE MTT-S International Microwave                   health informatics, vol. 25, no. 4, pp. 1273–1283, 2020.
      Biomedical Conference (IMBioC), vol. 1. IEEE, 2019, pp. 1–4.                [122] H. Sadreazami, M. Bolic, and S. Rajan, “Contactless fall detection
[102] A. Alnaeb, R. S. A. R. Abdullah, A. A. Salah, A. Sali, N. E. A. Rashid,           using time-frequency analysis and convolutional neural networks,”
      and I. Pasya, “Detection and classification real-time of fall events from         IEEE Transactions on Industrial Informatics, vol. 17, no. 10, pp. 6842–
      the daily activities of human using forward scattering radar,” in 2019            6851, 2021.
      20th International Radar Symposium (IRS). IEEE, 2019, pp. 1–10.             [123] P. Wang, Q. Li, P. Yin, Z. Wang, Y. Ling, R. Gravina, and Y. Li,
[103] K. Hanifi and M. E. Karsligil, “Elderly fall detection with vital signs           “A convolution neural network approach for fall detection based on
      monitoring using cw doppler radar,” IEEE Sensors Journal, vol. 21,                adaptive channel selection of uwb radar signals,” Neural Computing
      no. 15, pp. 16 969–16 978, 2021.                                                  and Applications, pp. 1–14, 2022.
[104] L. Liu, M. Popescu, M. Skubic, and M. Rantz, “An automatic fall             [124] K. Saho, S. Hayashi, M. Tsuyama, L. Meng, and M. Masugi, “Machine
      detection framework using data fusion of doppler radar and motion                 learning-based classification of human behaviors and falls in restroom
      sensor network,” in 2014 36th Annual International Conference of the              via dual doppler radar measurements,” Sensors, vol. 22, no. 5, p. 1721,
      IEEE Engineering in Medicine and Biology Society. IEEE, 2014, pp.                 2022.
      5940–5943.                                                                  [125] H. Sadreazami, M. Bolic, and S. Rajan, “On the use of ultra wideband
[105] Q. Wu, Y. D. Zhang, W. Tao, and M. G. Amin, “Radar-based fall                     radar and stacked lstm-rnn for at home fall detection,” in 2018 IEEE
      detection based on doppler time–frequency signatures for assisted                 Life Sciences Conference (LSC). IEEE, 2018, pp. 255–258.
      living,” IET Radar, Sonar & Navigation, vol. 9, no. 2, pp. 164–172,         [126] H. Li, A. Shrestha, H. Heidari, J. Le Kernec, and F. Fioranelli, “Bi-lstm
      2015.                                                                             network for multimodal continuous human activity recognition and fall
                                                                                        detection,” IEEE Sensors Journal, vol. 20, no. 3, pp. 1191–1201, 2019.
[106] L. Liu, M. Popescu, M. Skubic, M. Rantz, T. Yardibi, and P. Cuddihy,
                                                                                  [127] T. Imamura, V. G. Moshnyaga, and K. Hashimoto, “Automatic fall
      “Automatic fall detection based on doppler radar motion signature,” in
                                                                                        detection by using doppler-radar and lstm-based recurrent neural net-
      2011 5th International Conference on Pervasive Computing Technolo-
                                                                                        work,” in 2022 IEEE 4th Global Conference on Life Sciences and
      gies for Healthcare (PervasiveHealth) and Workshops. IEEE, 2011,
                                                                                        Technologies (LifeTech). IEEE, 2022, pp. 36–37.
      pp. 222–225.
                                                                                  [128] B. Jokanovic, M. Amin, and F. Ahmad, “Radar fall motion detection
[107] L. Liu, M. Popescu, M. Rantz, and M. Skubic, “Fall detection using                using deep learning,” in 2016 IEEE radar conference (RadarConf).
      doppler radar and classifier fusion,” in Proceedings of 2012 IEEE-                IEEE, 2016, pp. 1–6.
      EMBS International Conference on Biomedical and Health Informatics.         [129] M. S. Seyfioğlu, A. M. Özbayoğlu, and S. Z. Gürbüz, “Deep con-
      IEEE, 2012, pp. 180–183.                                                          volutional autoencoder for radar-based classification of similar aided
[108] B. Y. Su, K. Ho, M. Rantz, and M. Skubic, “Radar placement for fall               and unaided human activities,” IEEE Transactions on Aerospace and
      detection: Signature and performance,” Journal of Ambient Intelligence            Electronic Systems, vol. 54, no. 4, pp. 1709–1723, 2018.
      and Smart Environments, vol. 10, no. 1, pp. 21–34, 2018.                    [130] S. A. Shah, A. Tahir, J. Le Kernec, A. Zoha, and F. Fioranelli,
[109] B. Erol, M. Francisco, A. Ravisankar, and M. Amin, “Realization of                “Data portability for activities of daily living and fall detection in
      radar-based fall detection using spectrograms,” in Compressive Sensing            different environments using radar micro-doppler,” Neural Computing
      VII: From Diverse Modalities to Big Data Analytics, vol. 10658. SPIE,             and Applications, vol. 34, no. 10, pp. 7933–7953, 2022.
      2018, pp. 77–88.                                                            [131] J. Lu, Z. Ou, Z. Liu, C. Han, and W. Ye, “Radar based real-time
[110] H. Sadreazami, D. Mitra, M. Bolic, and S. Rajan, “Compressed                      fall detection system with low power consumption,” in 2021 18th
      domain contactless fall incident detection using uwb radar signals,” in           International SoC Design Conference (ISOCC). IEEE, 2021, pp. 266–
      2020 18th IEEE International New Circuits and Systems Conference                  267.
      (NEWCAS). IEEE, 2020, pp. 90–93.                                            [132] A. Gadde, M. G. Amin, Y. D. Zhang, and F. Ahmad, “Fall detection
[111] M. Chen, Z. Yang, J. Lai, P. Chu, and J. Lin, “A three-stage low-                 and classifications based on time-scale radar signal characteristics,” in
      complexity human fall detection method using ir-uwb radar,” IEEE                  Radar Sensor Technology XVIII, vol. 9077. SPIE, 2014, pp. 330–338.
      Sensors Journal, 2022.                                                      [133] L. R. Rivera, E. Ulmer, Y. D. Zhang, W. Tao, and M. G. Amin, “Radar-
[112] B. Jokanovic, M. Amin, F. Ahmad, and B. Boashash, “Radar fall detec-              based fall detection exploiting time-frequency features,” in 2014 IEEE
      tion using principal component analysis,” in Radar Sensor Technology              China Summit & International Conference on Signal and Information
      XX, vol. 9829. SPIE, 2016, pp. 358–363.                                           Processing (ChinaSIP). IEEE, 2014, pp. 713–717.
[113] X. Zhou, L.-C. Qian, P.-J. You, Z.-G. Ding, and Y.-Q. Han, “Fall detec-     [134] B. Erol and M. G. Amin, “Fall motion detection using combined
      tion using convolutional neural network with multi-sensor fusion,” in             range and doppler features,” in 2016 24th European Signal Processing
      2018 IEEE international conference on Multimedia & Expo Workshops                 Conference (EUSIPCO). IEEE, 2016, pp. 2075–2080.
      (ICMEW). IEEE, 2018, pp. 1–5.                                               [135] B. Erol, M. Amin, Z. Zhou, and J. Zhang, “Range information for
[114] H. Sadreazami, M. Bolic, and S. Rajan, “Fall detection using standoff             reducing fall false alarms in assisted living,” in 2016 IEEE Radar
      radar-based sensing and deep convolutional neural network,” IEEE                  Conference (RadarConf). IEEE, 2016, pp. 1–6.
      Transactions on Circuits and Systems II: Express Briefs, vol. 67, no. 1,    [136] C. Ding, J. Yan, H. Hong, and X. Zhu, “Sparsity-based feature
      pp. 197–201, 2019.                                                                extraction in fall detection with a portable fmcw radar,” in 2021 IEEE
                                                                                        International Workshop on Electromagnetics: Applications and Student
[115] ——, “Tl-fall: Contactless indoor fall detection using transfer learning
                                                                                        Innovation Competition (iWEM). IEEE, 2021, pp. 1–3.
      from a pretrained model,” in 2019 IEEE International Symposium on
                                                                                  [137] B. Erol and M. G. Amin, “Radar data cube analysis for fall detection,”
      Medical Measurements and Applications (MeMeA). IEEE, 2019, pp.
                                                                                        in 2018 IEEE International Conference on Acoustics, Speech and
      1–5.
                                                                                        Signal Processing (ICASSP). IEEE, 2018, pp. 2446–2450.
[116] ——, “Residual network-based supervised learning of remotely sensed          [138] C. Ding, Y. Zou, L. Sun, H. Hong, X. Zhu, and C. Li, “Fall detection
      fall incidents using ultra-wideband radar,” in 2019 IEEE International            with multi-domain features by a portable fmcw radar,” in 2019 IEEE
      Symposium on Circuits and Systems (ISCAS). IEEE, 2019, pp. 1–4.                   MTT-S International Wireless Symposium (IWS). IEEE, 2019, pp. 1–3.
[117] ——, “Capsfall: Fall detection using ultra-wideband radar and capsule        [139] C. Ding, H. Hong, Y. Zou, H. Chu, X. Zhu, F. Fioranelli, J. Le Kernec,
      network,” IEEE Access, vol. 7, pp. 55 336–55 343, 2019.                           and C. Li, “Continuous human motion recognition with a dynamic
[118] H. Yoshino, V. G. Moshnyaga, and K. Hashimoto, “Fall detection on a               range-doppler trajectory method based on fmcw radar,” IEEE Transac-
      single doppler radar sensor by using convolutional neural networks,” in           tions on Geoscience and Remote Sensing, vol. 57, no. 9, pp. 6821–6831,
      2019 IEEE International Conference on Systems, Man and Cybernetics                2019.
      (SMC). IEEE, 2019, pp. 2889–2892.                                           [140] M. He, Y. Nian, Z. Zhang, X. Liu, and H. Hu, “Human fall detection
[119] L. Anishchenko, A. Zhuravlev, and M. Chizh, “Fall detection using                 based on machine learning using a thz radar system,” in 2019 IEEE
      multiple bioradars and convolutional neural networks,” Sensors, vol. 19,          Radar Conference (RadarConf). IEEE, 2019, pp. 1–5.
      no. 24, p. 5569, 2019.                                                      [141] Y. Shankar, S. Hazra, and A. Santra, “Radar-based non-intrusive fall
[120] E. L. Chuma, L. L. B. Roger, G. G. De Oliveira, Y. Iano, and                      motion recognition using deformable convolutional neural network,” in
      D. Pajuelo, “Internet of things (iot) privacy–protected, fall-detection           2019 18th IEEE International Conference On Machine Learning And
      system for the elderly using the radar sensors and deep learning,” in             Applications (ICMLA). IEEE, 2019, pp. 1717–1724.
      2020 IEEE International Smart Cities Conference (ISC2). IEEE, 2020,         [142] B. Wang, L. Guo, H. Zhang, and Y.-X. Guo, “A millimetre-wave
      pp. 1–4.                                                                          radar-based fall detection method using line kernel convolutional neural
                                                                                  14



      network,” IEEE Sensors Journal, vol. 20, no. 22, pp. 13 364–13 370,
      2020.
[143] L. Ma, M. Liu, N. Wang, L. Wang, Y. Yang, and H. Wang, “Room-
      level fall detection based on ultra-wideband (uwb) monostatic radar
      and convolutional long short-term memory (lstm),” Sensors, vol. 20,
      no. 4, p. 1105, 2020.
[144] A. Bhattacharya and R. Vaughan, “Deep learning radar design for
      breathing and fall detection,” IEEE Sensors Journal, vol. 20, no. 9,
      pp. 5072–5085, 2020.
[145] T. Liang and H. Xu, “A posture recognition based fall detection
      system using a 24ghz cmos fmcw radar soc,” in 2021 IEEE MTT-S
      International Wireless Symposium (IWS). IEEE, 2021, pp. 1–3.
[146] B. Jokanović and M. Amin, “Fall detection using deep learning in
      range-doppler radars,” IEEE Transactions on Aerospace and Electronic
      Systems, vol. 54, no. 1, pp. 180–189, 2017.
[147] C. Ding, Z. Ding, L. Wang, and Y. Jia, “A fall detection method
      based on k-nearest neighbor algorithm with mimo millimeter-wave
      radar,” in 2021 IEEE 6th International Conference on Signal and Image
      Processing (ICSIP). IEEE, 2021, pp. 624–628.
[148] J. Liang, Y. Huang, and Z. Huang, “Fall detection system based on
      millimeter wave radar and machine learning,” in 2022 6th International
      Conference on Robotics and Automation Sciences (ICRAS). IEEE,
      2022, pp. 178–183.
[149] Y. Sun, R. Hang, Z. Li, M. Jin, and K. Xu, “Privacy-preserving fall
      detection with deep learning on mmwave radar signal,” in 2019 IEEE
      Visual Communications and Image Processing (VCIP). IEEE, 2019,
      pp. 1–4.
[150] F. Jin, A. Sengupta, and S. Cao, “mmfall: Fall detection using 4-
      d mmwave radar and a hybrid variational rnn autoencoder,” IEEE
      Transactions on Automation Science and Engineering, 2020.
[151] Y. Kim and H. Ling, “Human activity classification based on micro-
      doppler signatures using a support vector machine,” IEEE transactions
      on geoscience and remote sensing, vol. 47, no. 5, pp. 1328–1337, 2009.
[152] A. Sengupta, F. Jin, and S. Cao, “Nlp based skeletal pose estimation
      using mmwave radar point-cloud: A simulation approach,” in 2020
      IEEE Radar Conference (RadarConf20). IEEE, 2020, pp. 1–6.
[153] M. G. Amin, Y. D. Zhang, and B. Boashash, “High-resolution time-
      frequency distributions for fall detection,” in Radar Sensor Technology
      XIX; and Active and Passive Signatures VI, vol. 9461. SPIE, 2015,
      pp. 417–423.
[154] M. Mercuri, D. Schreurs, and P. Leroux, “Sfcw microwave radar for in-
      door fall detection,” in 2012 IEEE Topical Conference on Biomedical
      Wireless Technologies, Networks, and Sensing Systems (BioWireleSS).
      IEEE, 2012, pp. 53–56.
[155] Z. Peng, J.-M. Muñoz-Ferreras, R. Gómez-Garcı́a, and C. Li, “Fmcw
      radar fall detection based on isar processing utilizing the properties of
      rcs, range, and doppler,” in 2016 IEEE Mtt-S International Microwave
      Symposium (IMS). IEEE, 2016, pp. 1–3.
[156] H. Wang, L. Ren, E. Mao, and A. E. Fathy, “Phase based mo-
      tion characteristics measurement for fall detection by using stepped-
      frequency continuous wave radar,” in 2016 IEEE Topical Conference
      on Biomedical Wireless Technologies, Networks, and Sensing Systems
      (BioWireleSS). IEEE, 2016, pp. 43–45.
[157] W.-C. Su, X.-X. Wu, T.-S. Horng, and M.-C. Tang, “Hybrid continuous-
      wave and self-injection-locking monopulse radar for posture and fall
      detection,” IEEE Transactions on Microwave Theory and Techniques,
      vol. 70, no. 3, pp. 1686–1695, 2022.

