                                      IEEE JOURNAL OF BIOMEDICAL AND HEALTH INFORMATICS, VOL. 25, NO. 4, APRIL 2021                                       1273




                 Fall Detection With UWB Radars and
                       CNN-LSTM Architecture
           Julien Maitre , Kévin Bouchard, Member, IEEE, and Sébastien Gaboury, Member, IEEE


   Abstract—Fall detection is a major challenge for re-                         more than 65 by 2030, which would represent about 25% of the
searchers. Indeed, a fall can cause injuries such as femoral                    Canadian population [3]. Therefore, the issues associated with
neck fracture, brain hemorrhage, or skin burns, leading to                      the care and well-being of older people are becoming major
significant pain. However, in some cases, trauma caused by
an undetected fall can get worse with the time and conducts                     concerns for families, institutions, and companies. Currently, it
to painful end of life or even death. One solution is to                        is common for families to institutionalize their seniors in care
detect falls efficiently to alert somebody (e.g., nurses) as                    centers. The main advantage of this solution is the continuous
quickly as possible. To respond to this need, we propose                        presence (24/7) of caregivers, nurses, and physicians. They can
to detect falls in a real apartment of 40 square meters by                      intervene in cases of discomfort, injuries, or meet the needs of the
exploiting three ultra-wideband radars and a deep neural
network model. The deep neural network is composed of                           elderly. Nevertheless, there are still periods (during the day and
a convolutional neural network stacked with a long-short                        night) where seniors are left alone. These periods are defined as
term memory network and a fully connected neural network                        critical because events such as myocardial infarction, respiratory
to identify falls. In other words, the problem addressed in                     distress, or fall can occur without anyone being informed. In
this paper is a binary classification attempting to differen-                   cases like these, it is vital to intervene as quickly as possible
tiate fall and non-fall events. As it can be noticed in real
cases, the falls can have different forms. Hence, the data                      because injuries provoked by these events can get worse and
to train and test the classification model have been gen-                       become permanent, leading to a painful end of life (e.g., physical
erated with falls (four types) simulated by 10 participants                     and cognitive disability) or even death.
in three locations in the apartment. Finally, the train and                         The work presented in this paper focuses on fall detection.
test stages have been achieved according to three strate-                       Indeed, according to the World Health Organization (WHO),
gies, including the leave-one-subject-out method. This lat-
ter method allows for obtaining the performances of the                         30% of the persons over 65 years suffer accidentally from one
proposed system in a generalization context. The re-                            or more falls per year, and for persons over 80 years, this rate
sults are very promising since we reach almost 90% of                           increases to reach 50% [4]. This fact is more alarming when
accuracy.                                                                       one considers that falls often happen in indoor environments
  Index Terms—Fall, Detection, Classification, Ultra-                           and are related to normal activities of daily living (ADLs).
wideband radar, CNN-LSTM, Leave-one-subject-out.                                The consequences related to a fall are major injuries (e.g.,
                                                                                femoral neck fracture, brain injuries, skin burns), often leading to
                                                                                physical and cognitive disability or death in cases of undetected
                          I. INTRODUCTION
                                                                                falls [5]. However, it is possible to reduce these risks (death
      ECENT demographic studies have statistically confirmed                    rate and severity of injuries) by detecting falls as quickly as
R     the overall aging of the world’s population. For example,
the median age increased from 21.5 years in 1970 to over
                                                                                possible. In that sense, researchers proposed a significant num-
                                                                                ber of solutions, which can be divided into two categories. The
30 years in 2019 [1]. Besides, this aging is more significant                   first one relies on the use of wearable devices [6], [7], such
in western societies where the elderly populations can reach                    as smartwatches or smartphones. Despite the popularity of this
meaningful proportion. Indeed, the medicine and quality of                      approach, the number of false positives (identifying a fall when
life have improved significantly, which affect directly the life                it is not) is consequent [8]. Also, it is frequent that seniors forget
expectancy (increased by a rate of 5 years from 2000 to now) [2].               to wear the device, conducting the system to be ineffective [9].
For example, in Canada, the number of seniors increased from                    Moreover, wearable devices have a limitation concerning bat-
3.88 million in 2001 to 16 million in 2016. Also, according to                  tery management since there are inoperative if the battery is
forecasts by the federal agency, one in four Canadians will be                  discharged. The second category is represented by non-wearable
                                                                                solutions, such as smart floors or cameras [10], [11]. Although
   Manuscript received March 30, 2020; revised June 11, 2020 and July           non-wearable solutions represent an interesting alternative due
22, 2020; accepted September 26, 2020. Date of publication October              to the absence of battery management and a non-dependency of
5, 2020; date of current version April 5, 2021. (Corresponding author:          seniors (wearing the device), the related work does not provide
Julien Maitre.)
   The authors are with the Laboratoire d’Intelligence Ambiante pour            enough tests to evaluate performances correctly.
la Reconnaissance d’Activités (LIARA), 555 Boulevard de l’Université,               Despite the significant number of solutions to recognize falls
Chicoutimi, Québec G7H 2B1, Canada (e-mail: julien1_maitre@                     in the literature, there are two main challenges. The first chal-
uqac.ca; kevin_bouchard@uqac.ca; sebastien_gaboury@uqac.ca).
   Digital Object Identifier 10.1109/JBHI.2020.3027967                          lenge is to develop and adapt various solutions (technologies) to

                  2168-2194 © 2020 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission.
                                See https://www.ieee.org/publications/rights/index.html for more information.


       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.
1274                                                                IEEE JOURNAL OF BIOMEDICAL AND HEALTH INFORMATICS, VOL. 25, NO. 4, APRIL 2021



senior’s preferences. The main reason is that seniors can feel dis-              Section V,the experiments that have been conducted are detailed.
comfort (well-being reduced) with a particular technology (e.g.,                 Section VI introduces performances and discussion. Finally, the
cameras are considered intrusive), and hence, it is necessary to                 last section concludes the proposed work and gives future works.
propose alternative solutions.
   Thus, we propose a new system based on multiple ultra-                                                   II. RELATED WORK
wideband (UWB) radars to detect falls. The motivation to exploit
this type of radar is the richness of information without the                       The literature on fall detection can be divided into two main
possibility of identifying the person or its activities as easily as             trends, which are the techniques relying on wearable technolo-
images provided by cameras. Then, the last challenge is taking                   gies and those relying on non-wearable solutions.
advantage of UWB radars and manipulating data to differentiate
falls from ADLs. In addition, we programmed one architecture                     A. Wearable Solutions
of deep neural network (DNN), which is a convolutional neural                       For the first one (wearable devices), most of the researches
network (CNN) combined with a long short-term memory net-                        exploit a triaxial accelerometer [6], [7] to detect falls. This sensor
work (LSTM). Compared to the literature exploiting this type                     is integrated into a device (e.g., smartwatch, smartphones, box
of sensor, the work presented in this paper gives new research                   attached to a belt) that users can wear in some locations of the
results. Indeed, we conducted experiments with 10 participants,                  body. The most common locations are the waist [6], a wrist [16],
at three different locations in a realistic home setting of approx-              or the chest [17]. In some cases, researchers also combine gyro-
imately 40 square meters. Only a few existing works collected                    scope [18] or air pressure sensor [19] into the device. The role
data in such an environment (e.g., size of the apartment, fully                  of these technologies is to capture human movements by pro-
furnished) [12], [13]. The data related to simulated falls and                   viding a series of values (raw signals). Then, signals are used to
ADLs (e.g., cleaning a room, drinking a glass of water) have                     detect falls with different approaches divided into three detection
been acquired thanks to three UWB radars at different times                      strategies: (i) Threshold + If-Then rules; (ii) Feature Extraction
in the day and different days (over two months). It should be                    + Machine Learning Algorithms; (iii) Raw Data + Machine and
mentioned that simulated ADLs are more complex than those                        Deep Learning Algorithms. Strategy (i) [20], [21] is defined as
in the literature. Also, it is the first time that three UWB radars              a handcrafted method since it relies, in general, on the detection
have been exploited at the same time to detect falls. Indeed, the                of the maximum or/and minimum peak(s) in signals. Then, the
maximum number of radars that we found in the literature is                      identified peak(s) is compared with a threshold value computed
two [14]. In addition, four types of falls, namely forward fall,                 from the available dataset. Finally, rules (if-then) can be used
side (left or right) fall, backward fall, and fall after trying to               to classify events. However, this strategy presents a significant
sit down, are simulated according to a video capture study [15].                 number of false positives (disturbing the nurses in their work)
Although there are four types of falls, the addressed problem is a               and false negatives when the model is tested with new instances.
binary classification attempting to differentiate fall and non-fall              For example, in [20], the rate of false negatives (falls classified as
events. The falls are therefore based on documented cases in                     non-fall event) was 10.4%. The main reasons of this unsatisfying
the scientific literature and the diversification make this study                performance are related to the low number of features and
more realistic than most of those found in the literature. This re-              the use of handcraft rules based on threshold values. Strategy
sulting dataset is our first contribution. The second contribution               (ii) [22]–[25] relies on features extracted (e.g., maximum and
represents the testing phase of the trained CNN-LSTM models.                     minimum peak, acceleration, angular velocity, velocity) from a
Specifically, we tested deep learning models in order to obtain                  sliding window and classical machine learning algorithms (e.g.,
performances which would generalize to different contexts. To                    k-Nearest Neighbors, Support Vector Machine, Nave Bayes).
do so, the dataset was split with three strategies. The first one                The performances are very good. For example, in [23], they
was split on the instances. The second strategy separates files of               obtained an area under the receiver operating characteristic curve
the dataset. The last one is based on the leave-one-subject-out                  (AUC) of 0.96. Concerning the strategy (iii) [7], [16], [17], it
experiment, which is rarely used in existing studies. The idea is                is based on the use of raw data provided by sensors. Indeed,
to divide the dataset into N − 1 persons to train the model and                  the raw data represent the inputs of classical and deep neural
test it with the N th person. Applying these three strategies in                 network algorithms. However, the main disadvantages of this
the same work is also a novelty compared to related work. We                     first trend are battery management, cases where users forget to
obtained very promising results since the average accuracies on                  wear the device, and some uncomfortable body locations (e.g.,
the third strategy are 88.1%, 91.5%, and 82.6% for positions 1,                  chest, back, waist).
2, and 3, respectively. In the best case, where we attempted to
detect falls with the data provided by the closest UWB radar
(only one radar), we reached accuracies of 98.51% (position 1),                  B. Non-Wearable Solutions
96.75% (position 2), and 95.48% (position 3).                                       For the second trend (non-wearable devices), the literature
   The remainder of the paper is organized as follows: Section II                can be divided into two categories according to the used tech-
presents a complete state of the art dealing with fall detection                 nologies. We divide them into those depending on vision sensors
systems. Section III describes the setup. More specifically, de-                 and those using non-vision sensors.
tails of the apartment and UWB radars are given. Section IV                         The first category is based on the use of cameras and computer
explains the data preprocessing and CNN-LSTM architecture. In                    vision techniques. Cameras are very popular with researchers

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.
MAITRE et al.: FALL DETECTION WITH UWB RADARS AND CNN-LSTM ARCHITECTURE                                                                                   1275



since the information contained in the image is rich. However,                  a deep ConvNet. More specifically, their work is based on the
unlike researchers, humans are reluctant to accept cameras due                  concept of dynamic image, which combines the frames of a video
to privacy concerns. Thus, other types of cameras have been                     into a single image in order to identify the sequences of action.
proposed to detect falls, such as thermal and depth cameras [10],               Then, the deep ConvNet is trained with the dynamic images,
[11], [25], [26]. The main advantage of these latter technologies               and the final decision is given by a sliding window framework
is that patients cannot be recognized (or it is a very complex                  and a Difference Scoring Method (DSM). They evaluated their
task to recognize patients). Indeed, these cameras do not provide               approach on three publicly available fall detection datasets
details about the face and clothes, making identification almost                (simulated falls) and on the YouTube Fall Dataset (YTFD).
impossible. However, the movements (actions) performed by the                   The performances have been expressed with the sensitivity and
patients can be easily distinguished, which can still affect their              specificity, and the scores greatly depend on the dataset. For
acceptance of the technology. Concerning exploited methods                      example, the sensitivity and specificity obtained on the Le2i fall
to detect falls with cameras, the literature proposes innovative                detection dataset are 98.43% and 100%, respectively. For the
approaches.                                                                     YTFD, the values of the sensitivity and specificity are 63.7%
   For instance, Khan et al. [26] present an architecture of a                  and 68.1, respectively.
deep neural network composed of one autoencoder followed                           The second category relies on sensors providing one-
by one 3D convolutional neural network. The model has been                      dimensional (1D) discrete-time signals. Compared to cameras
trained with only image sequences of ADLs (and by excluding                     (providing 2D, 3D, and 4D data), the information contained in
fall events). The output of the model is a probability related to               1D signals is complex to interpret by an observer. Also, these
the chance of an image sequence to be an ADL. If the probability                technologies overcome the limitations of wearable devices and
is close to 0, then the image sequence is probably a fall. They                 cameras, namely battery management problems, the absence
tested their approach on three open datasets and obtained the                   of data (when patients forget to wear the device), and privacy
Area Under the Curve (AUC) values of 0.91 (twice) and 0.95.                     concerns of cameras. According to the literature, the number
The approach is interesting but needs all existing ADLs in a                    of solutions to detect falls is extensive. Indeed, smart floors
real-case.                                                                      (where the floor is composed of a network of seismic sensors,
   In another example of a vision-based approach, Lu et al. [27]                accelerometers, or pressure sensors) [29], acoustic sensors (e.g.,
proposed to detect falls from video kinematic data. The videos                  ultrasonic array sensors) [30], or infrared array sensors [31] are
are provided by open datasets such as the Multiple Cameras Fall                 examples of technologies to detect falls.
Dataset (MCFD), the Fall Detection Dataset (FDD), or the UR                        During these last years, some researchers did exploit radars
Fall Dataset (URFD) and so on. However, the authors mainly                      and machine learning algorithms to recognize falls and human
focused on MCFD. This dataset covers 24 scenarios, where                        activities [32]–[34]. Some of them used data provided by con-
each scenario is composed of nine activities. Also, eight cameras               tinuous wave (CW) radars [35], [36]; others take advantage of
separately captured the scene in each scenario. It results in 192               the information given by frequency-modulated continuous-wave
(24x9) videos for a total of 736 actions. The frame rate of each                (FMCW) radars [33], [37] and, in some cases, UWB radars
video is 30 fps. They developed a 3D CNN combined with an                       were employed [14], [38]. Two different ways (uses) to perform
LSTM to classify the data (Fall and Non-Fall actions). The 3D                   this recognition are statistical learning [14], [33], and deep
CNN is trained to extract discriminant features. In addition, the               learning [37]–[39] approaches.
3D convolution could extract motion features from a temporal                       For example, Erol et al. [32] presented a method that exploits
sequence while the 2D CNN could only encode spatial informa-                    the slow-time, fast-time, and Doppler frequency (three radar
tion. The LSTM has the property to locate the region of interest in             signal variables) to generate a radar data cube (RDC). They
each frame. Hence, the proposed combination of the 3D CNN                       then applied a multi-dimensional principal component analysis
and the LSTM locates the region of interest in the video and                    (MPCA) to reduce the number of information of the RDC. In
encode the motion information. Also, it should be mentioned                     other words, the MPCA acts as a feature extractor. The remaining
that 3D CNN and the LSTM have been separately trained. The                      data from the RDC were used to feed a k-NN algorithm. The
video inputs are divided into 15 clips of 16 frames, and the                    accuracy is 97.88%, which outperformed the standard principal
amount of overlap between two consecutive clips is eight frames.                component analysis (PCA). The latter has only 86.01% for the
They employed the five-fold cross-validation in order to validate               accuracy. Unfortunately, the experiments are the weak part of the
their approach. The accuracy obtained reaches 100%, which is                    study. Indeed, only six participants took part in the experiments,
the best performance on the MCFD. The authors confirmed the                     and only four classes are considered, where each class has
efficiency of their approach by obtaining excellent results on                  approximately 100 recorded motions of 10 s duration. Also,
the other datasets, namely the FDD and the URFD. Indeed, the                    the approach has not been tested with the leave-one-subject-out
accuracies are 99.36% and 99.27%, respectively. Finally, they                   strategy, which allows determining the real performances of the
transposed their deep learning algorithm on datasets specialized                system with new persons (in a real case) and confirm general-
in video-based activity recognition. The performance varies                     ization over new participants.
from 50% to 98% approximately.                                                     Another example, Shrestha et al. [33] proposed detecting
   To conclude this part, in [28], the authors proposed a system                falls and recognizing human indoor activities using radar sys-
detecting in real-time human falls in naturally occurring scenes.               tems. The main objective of this work is to show the potential
The system relies on a vision-based approach using cameras and                  effectiveness of various features and classifiers. Two datasets

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.
1276                                                                IEEE JOURNAL OF BIOMEDICAL AND HEALTH INFORMATICS, VOL. 25, NO. 4, APRIL 2021



were created to reach this goal. The first one is composed
of experiments performed in an indoor meeting room at the
University of Glasgow. They used one FMCW radar located
at the height of approximately 1.2 m to be in front (of the
torso) of the participants. Six persons participated in the data
collection. These persons simulated twice each of the seven
activities. The second dataset has been created in the laboratory
of the Telecommunication Systems Group at the Universit Po-
litecnica delle Marche. The same radar was used. However, this
dataset is composed of ten activities, including the simulation
of a frontal fall after tripping. Seven participants took part in
this experiment. Additional data were recorded for the same
                                                                                 Fig. 1. Plan of the LIARA apartment. red circles are the location of the
activities performed by two older people (58 and 62 years old).                  UWB radars. green rectangles are the location of simulated falls.
Different signal processing techniques were successfully applied
(e.g., Short Time Fourier transform, IIR filter) on the radar data
to generate micro-Doppler signatures. From those signatures,                     falls. The data are acquired from three wearable inertial sensors
the authors extracted ten features (e.g., centroid and bandwidth                 (on the wrist, waist, and ankle) and one Frequency-Modulated
of the signatures, the entropy of the signatures) to create vectors              Continuous-Wave (FMCW) radar. Each inertial sensor has one
(instances) that can be used to classify data with classical ma-                 tri-axial accelerometer, gyroscope, and magnetometer. 16 par-
chine learning algorithms. The best performances were obtained                   ticipants simulated daily activities in a common room at the
with the Support Vector Machine (SVM). The dataset has been                      University of Glasgow. More specifically, the radar was placed
randomly shared into a training (80% of the data) and a testing                  in front of the activity zone of a surface size of 3 m × 2.2 m. The
set (20% of the data), and they repeated 50 times this splitting                 dataset is composed of six human activities (walking, sitting on a
strategy. They reached 94% and 76.44% (average accuracies)                       chair, standing up, bending to pick up an object, drinking a glass
for the first and the second dataset, respectively. These results                of water, and simulated a frontal fall). It should be noted that the
show the influence of the type of activities performed by the                    authors take into consideration the transition between activities.
participants (activities in the second dataset are more complex                  To validate their approach, they employed the strategy of the
than those in the first dataset) and the number of participants on               leave-one-subject-out. The best results were obtained with the
the performances. It is noteworthy that the fall class in the second             hybrid approach of soft-hard combination fusion. Indeed, they
dataset has 82% accuracy, which is low compared to our paper.                    reached approximately 96% of average classification accuracy.
   Sadreazami et al. [40] used only one UWB radar and one                        However, the two drawbacks of this work are the experimental
CNN architecture to recognize fall events. They obtained an                      design (which is limited in a small activity zone), the daily
accuracy of 92.72%. However, the experiment presents some                        activities (which are simple), and the difficulty of setting the
limitations. First, the dataset is poor in diversity, since there are            soft-hard combination fusion (the number of virtual classifiers)
only 5 participants. Also, all participants performed 121 falls                  correctly.
and 85 non-fall activities. Secondly, the proposed approach has                     For all these reasons, the proposed study is interesting for
not been tested following the leave-one-subject-out method. In                   the scientific community because it realistically depicts the real
other words, the obtained performance is not representative of                   conditions for detecting falls and uses the leave-one-subject-out
the generalization (for any subject) of the solution.                            strategy to show the generalization over new participants.
   Another example, Wang et al. [41] also proposed to exploit
one UWB radar to detect falls. The range-time image provided
by the radar is processed with the short-time Fourier transform                                         III. SETUP OF THE STUDY
in order to get time-varying range-Doppler images. Then, a                           The achieved study, namely, fall detection in an indoor envi-
sequence of this latter image is used to extract features with                   ronment, has been completed in the Laboratoire d’Intelligence
a convolutional AutoEncoder. Finally, the extracted features fed                 Ambiante pour la Reconnaissance d’Activits (LIARA). The
a GRU architecture [42]. They reached an accuracy of 96.80%.                     LIARA has an apartment of 40 square meters and possesses more
Despite this interesting approach, the experiments also presents                 than a hundred different sensors (e.g., radio frequency iden-
important limitations. Indeed, there are only four participants.                 tification transponders and antennas, contact sensors, passive
Also, all activities have been performed in only one location. It                infrared sensors) and effectors (e.g., screens, speakers, lights).
shall be noted that all research, to the best of our knowledge,                  The objective of these sensors is to provide data and enhance
presented in the literature did not test the generalization of their             the habitat with ambient intelligence. Fig. 1 shows the plan of
approach with the leave-one-subject-out method, and recorded                     LIARA’s apartment.
activities at only one location. It has been shown that the angle                    In this study, the proposed fall detection only relies on
of the performed activity with the radar has an influence on the                 the three UWB radars installed in the apartment.We decided
recognition results [34].                                                        to consider using UWB radars instead of CW radars due to
   Li et al. [37] used a multi-layer bidirectional LSTM for                      better penetrating and fine range resolving abilities of UWB
multimodal sensor fusion to classify daily activities’ patterns and              radars [43], [44]. Red circles in Fig. 1 give their locations,

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.
MAITRE et al.: FALL DETECTION WITH UWB RADARS AND CNN-LSTM ARCHITECTURE                                                                                   1277




Fig. 2. The radar scattering matrix provided by one UWB radar during
a non-fall activity.
                                                                                Fig. 3.    The radar scattering matrix.


and each of them is mounted 36 cm above the ground on the
wall. This position above the ground has been chosen because                    seconds. Then, the data preprocessing step has the objective
electric outlets, in Canada, are at this height. The idea is to have a          to transform this radar scattering matrix X into a radar time
plug-and-play solution. Also, we exploited the Xethru X4M200                    serie y = yi ∈ R1×M . To do so, we normalize all the data in
from Novelda. This radar uses a UWB transceiver operating                       one column (amplitude values of one frame) according to the
in the frequency range of 6.0–10.2 GHz (6.0–8.5 GHz for low                     maximum absolute value in this same column. Then, we sum
frequency 252 bands, and 7.25–10.2 GHz for high frequency                       all the normalized values of the column in order to obtain the
bands), which provides high spatial resolution, unobtrusiveness,                value yi at time i of our new signal. Equation (1) describes the
and privacy-preserving monitoring by sending short pulses at                    operation transforming the radar scattering matrix into a radar
high frequencies. These radars have been configured to acquire                  time-series.
                                                                                                                   N
                                                                                                                   
scans (frames) at a rate of 50 frames/second. Thus, recorded data                                     1
during a period P results in a radar scattering matrix, where each                  yi =                                xj,i , ∀i ∈ {1, 2, . . ., M }.    (1)
                                                                                            max1≤j≤N (|xj,i |) j=1
row represents the spatial samples from different ranges (bins
– fast time), and each column represents observations (frames)                    Finally, the resulting time-series y is also normalized by
recorded at different time intervals (slow-time). Fig. 2 illustrates            subtracting the mean and dividing by the standard deviation in
one radar scattering matrix. Also, the scanning system has been                 order to provide the time-series z = zi ∈ R1×M . Equation (2)
set to operate in a distance range of [0.4–9.8] meters implying                 expresses this last operation to obtain a time-series that is the
that one bin corresponds to 5.14 cm.                                            input to deep learning models.
                                                                                                     yi − mean(y)
                  IV. THE PROPOSED METHOD                                                     zi =                , ∀i ∈ {1, 2, . . ., M }.               (2)
                                                                                                         std(y)
  The proposed method can be decomposed into two steps.
                                                                                   The resulting time-series represents one instance of the dataset
The first step is the data preprocessing to transform the radar
                                                                                used to train the deep learning models. Fig. 4 shows the normal-
scattering matrix into a time series. The second step is to exploit
                                                                                ized radar time-series of one activity.
a CNN-LSTM architecture in order to generate classification
                                                                                   It shall be mentioned that the time window defined in this work
models.
                                                                                has a length of 15 seconds, with an 95% overlap between each
                                                                                window. The choice to set 15 seconds for the time window length
A. Data Preprocessing                                                           was made according to the experiments (falls and the types of
   Let X = xj,i ∈ RN ×M be the radar scattering matrix in a                     the simulated ADLs). Indeed, in the case of the falls, data have
conceptual form illustrated in Fig. 3, where xj,i is the amplitude              been recorded for 20 seconds. More specifically, the participants
value related to the bin j of the frame i. N and M denotes                      started to simulate the fall between 5 and 10 seconds from the
the total number of bins of one frame (fast-time) and the total                 beginning of the recording. Then, the participant simulated the
number of frames (slow-time) respectively. In other words, X                    fall and stayed on the mattress with the possibility to move until
represents a successive concatenation (recording) of the received               the end of the recording. We wanted to get the maximum of the
radar signals (frames) during a specific period (time window),                  fall sequence in the time window to get better performances. In
say P seconds. Thus, M corresponds to the multiplication                        addition, the performed ADLs (e.g., washing your hands, clean-
of the sampling rate (S frames/second) by the duration of P                     ing the room, taking the medications) are well recognized with

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.
1278                                                                IEEE JOURNAL OF BIOMEDICAL AND HEALTH INFORMATICS, VOL. 25, NO. 4, APRIL 2021




Fig. 4. Resulting time series from the data preprocessing applied to
the radar scattering matrix of a non-fall event.



a larger time window. Hence, the length of 15 seconds for the
time window was satisfying in order to differentiate falls from
ADLs. For the overlap between two successive time windows,
                                                                                 Fig. 5.    The CNN-LSTM architecture.
the choice was made according to the response performance of
the system that we want. We wanted, at least, one classification
per second. With an overlap ratio of 0.95, the system can provide
                                                                                 to extract relevant information. It results in five series of features
a classification every 0.76 second, which is also satisfying.
                                                                                 feeding the LSTM network. LSTM network is a special kind of
   Since we have three UWB radars, the same preprocessing is
                                                                                 recurrent neural network learning from short-term as well as
applied to the two other radars. Consequently, one real instance
                                                                                 long-term dependencies. In other words, LSTM networks can
is composed of three time-series denoted by [T S1 , T S2 , T S3 ]T ,
                                                                                 model the temporal changes in a sequence of data thanks to
where T S1 , T S2 , and T S3 are the time-series related to the
                                                                                 their recurrent architecture and memory units [45].
UWB radar 1, UWB radar 2, and UWB radar 3, respectively.
                                                                                     More specifically, the 1D CNN provides an abstract represen-
                                                                                 tation of the input sensor data in feature maps thanks to the con-
B. CNN-LSTM
                                                                                 volutional filters. It shall be mentioned that we added a dropout
   The architecture of the CNN-LSTM network exploited in                         (rate of 0.5) layer between each layer of the CNN-LSTM model.
this work is constructed by stacking 1D CNN, two LSTM                            Dropout layers consist of setting to 0 a fraction of input units in
layers, and one fully connected layer. The choice to exploit                     order to prevent overfitting. The CNN architecture contains two
the architecture of the CNN-LSTM was made according to                           one-dimensional convolutional layers: 64 (1 × 3) and 64 (1 × 3)
the preliminary results obtained with an LSTM model. The                         filters respectively in the forward direction. The two parameters
LSTM model has the same architecture as the LSTM part of                         consist of the definition of the dimensionality of the output space
the presented CNN-LSTM. In the case where we only used the                       and the length of the 1D convolution window, respectively. Each
data of one radar related to its closest fall, we obtained 89%, 85%              of this convolutional layers implements the rectified linear unit
and 76% of accuracies for the position 1, 2, and 3, respectively.                (ReLu) activation function. The other parameters are those set
Also, the processing time of the training stage is much longer                   by default in KERAS.1 After these convolutional layers, we
than the CNN-LSTM. Indeed, the LSTM model trained for                            added a one-dimensional max pooling layer with a pool size
100 minutes approximately while the CNN-LSTM architecture                        equal to 2. This layer allows to down-sample an output with
trained for 2 minutes and 30 seconds. Hence, The CNN-LSTM                        also the objective to prevent overfitting. After the CNN part,
model can automatically extract features (better than an LSTM                    the output is flattened into a one-dimensional vector feeding
model) and learn time-series patterns for classification. It is                  the LSTM network. As explained, the role of the LSTM net-
the main reason for this deep learning model choice. Fig. 5                      work is to recognize and synthesize temporal dynamics. In this
illustrates the architecture of the CNN-LSTM. However, we                        CNN-LSTM architecture, the LSTM network has two stacked
must make these three types of neural networks compatible.                       layers. The choice of stacking layers of LSTM units has been
Indeed, since one fall is an event evolving dynamically with                     made according to the work presented by Grave et al. [46].
time, some temporal relationships from the signal (time series)                  Indeed, he demonstrated that the depth of the network is more
should be extracted. Thus, the input (pre-processed data) of the                 important than the number of memory cells. Stacking LSTM
CNN-LSTM model is split into five subsequences, where each
of them has 150 samples. Then, each subsequence feds one CNN                        1 https://keras.io/




       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.
MAITRE et al.: FALL DETECTION WITH UWB RADARS AND CNN-LSTM ARCHITECTURE                                                                                   1279



layers allows extracting better information than a single layer.                we compute some well-known metrics representing the perfor-
Hence, the first layer has 100 LSTM units, and the second one has               mances of the classification model. In this study, we exploited the
50 LSTM units. The decrease of LSTM units between the two                       accuracy (Acc.), Kappa measure (K.), precision (P.), the recall
LSTM layers reduces the chance to explode the dimensionality,                   (R.), and the F1-score (F1-Sc.).
leading to an overfitted model. To conclude the architecture of                    Moreover, to propose an in-depth study, we decided to explore
the CNN-LSTM, we connected the output of the LSTM to a                          three strategies to evaluate the performances. The first strategy
fully connected neural network having two layers. Layer 1 has                   consists of splitting the dataset (all created instances) randomly
100 neurons set with the ReLu activation function. Layer 2 is                   into two parts, where 70% of instances represent the training
defined by the SoftMax activation function in order to classify                 dataset, and the balance (30% of instances) defines the testing
instances in Fall or Non-Fall class. It is noteworthy that the                  dataset. As described previously, one instance is given by three
objective of this work is not to propose the perfect architecture.              time-series (one per UWB radar) on a period of 15 seconds (time
Therefore, we did not perform a grid search to determine the                    window). Also, we defined an overlap of 95% between two time-
best hyperparameters of the presented model.                                    windows. In other words, one data file consisting of a recorded
                                                                                event over 20 seconds has multiple instances (7 instances can be
                                                                                created with an event of 20 seconds). This splitting method is the
                          V. EXPERIMENTS                                        traditional way of evaluating classification models in machine
   All experiments have been conducted in the LIARA apartment                   learning.
under ethical clearance. Indeed, ethical clearance was obtained                    The second strategy focuses on file splitting. More precisely,
through the Universit du Qubec Chicoutimi human research                        70% of files constitute the training dataset, and the testing dataset
ethics board (ID number: 2019-235). The study implied ten                       is composed of the rest (30% of files). The main difference with
male participants, aged from 23 to 39. Also, all participants                   the first strategy is that the split has been performed before the
were healthy adults. It shall be mentioned that data acquisition                creation of instances. Indeed, in the first strategy, we created
has been achieved at different time in a days and different days                instances from data files, then we split the dataset. In the second
(over two months).                                                              strategy, we first split files, and then we created instances.
   The procedure of the data acquisition has been designed to                   Also, from the second strategy, we can compute two types of
demonstrate that falls can be detected from UWB radars. More                    performances. Hence, we have performances based on instances
specifically, we wanted to obtain performances that showed the                  (comparable to strategy 1) and based on files. Actually, one file is
proposed system operating under realistic conditions. To do so,                 tagged by the corresponding class, which means that instances
each participant simulated four types of falls, namely forward                  created from one file belong to this class. For example, if 10
fall, side (left or right) fall, backward fall, and fall after trying           instances on 13 are classified class A, then the file is predicted
to sit down.                                                                    class A (it is a majority vote). It should be mentioned that only
   The simulated fall can be divided into two steps. In the first               falls performed in position 1 have been used for strategies 1
one, the participants simulate the fall between 5 and 10 seconds.               and 2.
In the second step, the participant stays on the ground and                        The third strategy is more sophisticated and allows evaluating
does not move much anymore. The overall period to perform                       the generalization of the proposed system operating in real con-
one fall (the two previous steps) was 20 seconds and corre-                     ditions. To do so, we exploit the leave-one-subject-out method.
sponded to the time of the data acquisition. Each type of fall                  The idea behind it is to select N − 1 persons to represent the
was repeated five times at three positions in the apartment, as                 training dataset, and to use the N th person as the testing dataset.
illustrated by green rectangles in Fig. 1. Thus, the total number               In this study, N = 10.
of simulated falls is 600. All participants performed one time                     Most information on the training of the CNN-LSTM models
two minutes of ADLs for each batch of simulated falls (20 falls                 should be mentioned. First, the project has been developed with
per position), resulting in a total of six minutes of simulated                 the open-source neural network library Keras and the integrated
ADLs per participant. During these six minutes, participants                    development environment PyCharm. Second, we used the opti-
were free (without constraints) to perform any ADLs anywhere                    mizer that implements the Adadelta algorithm. It is an extension
in the apartment. Finally, we have 200 minutes of recording                     of the Adagrad algorithm, which is a stochastic gradient descent
data for Fall and 60 minutes of Non-Fall data. The dataset is                   method. The Adadelta algorithm has the particularity to adapt
unbalanced if we considered the number of minutes. However,                     the learning rate, while the model is training. Accordingly, the
we created instances by applying a sliding time window. To do                   algorithm can adapt its learning with updated gradients. The
so, we defined 15 seconds for the length of the time window with                initial learning rate is 0.001. Also, we defined a batch size of
an overlap of 95%. Consequently, the Fall class and Non-Fall                    256 instances. According to the computer (OS: Windows, RAM:
class have 140 instances each (7 instances x 20 falls) per position             32 GB, Processor: i7-8850H, GPU: NVIDIA Quadra P3200) on
per participant.                                                                which the training is done, it is a satisfying batch size since the
                                                                                tradeoff between the duration of the training (approximately 2
                                                                                minutes and 30 seconds) and the performances (see after) of the
                 VI. RESULTS AND DISCUSSION                                     model is excellent.
   In general, a classification model is generated (trained) with a                When we train neural network models, it is common to use
training dataset, and evaluated by using a testing dataset. Then,               a validation dataset. This dataset allows tracking if the model

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.
1280                                                                IEEE JOURNAL OF BIOMEDICAL AND HEALTH INFORMATICS, VOL. 25, NO. 4, APRIL 2021



                                                                                                             TABLE I
                                                                                    PERFORMANCES FOR FALL DETECTION BY TRAINING AND TESTING THE
                                                                                                   MODEL WITH THE STRATEGY 1




                                                                                                            TABLE II
                                                                                    PERFORMANCES FOR FALL DETECTION BY TRAINING AND TESTING THE
                                                                                                   MODEL WITH THE STRATEGY 2




Fig. 6. Evolution of the accuracy vs. epoch during the training stage of
the model related to the results presented in Table I.




                                                                                    Finally, we proceed to a data augmentation for the training
                                                                                 stage by creating 5 other instances from one instance. To
                                                                                 do so, we permuted time-series T Si , where i = 1, 2, 3. In
                                                                                 other words, the instance denoted by [T S1 , T S2 , T S3 ]T gives
                                                                                 [T S1 , T S3 , T S2 ]T , [T S2 , T S3 , T S1 ]T , [T S2 , T S1 , T S3 ]T ,
                                                                                 [T S3 , T S2 , T S1 ]T , and [T S3 , T S1 , T S2 ]T . The main
                                                                                 advantage of this technique is that the proposed system
                                                                                 becomes independent of the localization of activities (events).
                                                                                 Unfortunately, we did not perform classical data augmentation
Fig. 7. Evolution of the loss vs. epoch during the training stage of the
model related to the results presented in Table I.                               to increase the size of the dataset. The data augmentation task
                                                                                 is very complex in this work and deserves more research.
                                                                                 Indeed, the radar provides data that are arranged as a radar
                                                                                 scattering matrix. The radar scattering matrix can be viewed
overfits the training data. In other words, the model continues                  as an image with only one channel. However, we have three
to improve their performances on the training data while it gets                 UWB radars in the apartment, collecting the data of one action
worse on the validation and testing datasets. In this work, we                   at three different locations. It is like taking a picture in three
used the testing dataset as a validation dataset to track the training           different angles of a subject performing a particular action.
of the model since we do not perform any fine tuning on the                      In this case, it is challenging to generate three different but
selected models. Also, all presented performances belong to                      coherent (for the same action) images (one for each angle) of the
classification models, which are not overfitted. Figs. 6 and 7                   subject.
illustrate the evolution of the accuracy and the loss versus epoch                  Tables I and II present the performances of our approach.
during the training stage of the model related to performances                      Performances in Table I represent fall detection efficiency
given in Table I (for strategy 1). We observe that the accuracy                  according to strategy 1, which splits the dataset into two parts
stops to increase after several epochs. At the same time, the loss               (70-30). It should be recalled that the present paper addresses
of the validation dataset starts to increase while the loss of the               a binary classification problem, where the Fall and Non-Fall
training dataset continues to decrease. This situation represents                events represent the positive and negative classes, respectively.
when the model starts to overfit (even if the loss value is low).                The CNN-LSTM model, in this case, reaches 89% of global
Thanks to a callback function based on the evolution of the                      accuracy and 77% for Cohen’s Kappa. In other words, for 394
accuracy and loss values, we saved the weights and bias of the                   instances belonging to the Non-Fall event, 347 instances are
model before it falls into overfitting.                                          correctly classified (47 false positives). Concerning the Fall


       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.
MAITRE et al.: FALL DETECTION WITH UWB RADARS AND CNN-LSTM ARCHITECTURE                                                                                   1281




Fig. 8. Fall detection performances of the leave-one-subject at
                                                                                Fig. 9.    Fall detection performances of the leave-one-subject at Posi-
Position 1.
                                                                                tion 2.




instances, 279 on 314 instances are detected as a Fall event (35
false negatives). As we can see, the performances are high, and
only the false negatives of the Fall class is concerning.
   In Table II, we can see that global performances are slightly
lower than those in Table I. The difference can be explained by
the Strategy 2, which splits the dataset into two parts (70-30),
according to the number of files. Indeed, each Fall event can be
unique, and, in this case, there is a possibility that one fall in the
testing dataset does not share any similarities with all simulated
falls in the training dataset. However, the performances of the
                                                                                Fig. 10.    Fall detection performances of the leave-one-subject at Posi-
CNN-LSTM model for instances are 85% and 70% for global                         tion 3.
accuracy and Cohen’s Kappa, respectively. From a different
point of view, 326 on 402 instances belonging to the Non-Fall
class are correctly classified (76 false positives). Also, the model
assigned the label Fall to 345 instances and 269 from those                     and 90%. More surprisingly, two of over ten participants have
belong to that class. Concerning the number of false negatives                  poor performances (lower than 50%).
for the class Fall, there are only 27 instances. In the second part                Some reasons can explain these performance differences.
of Table II, we compute performances based on the majority                      First, simulated falls are different from one person to another.
classification of instances per file (or per period of 20 seconds               Thus, to increase the generalization of our models, we need many
without overlap). From this point of view, the performance for                  more participants. Secondly, walls, doors, and furniture can
fall detection is very high since 50 falls have been correctly                  reduce the quality of the recorded data. It is the main explanation
identified over 52 falls.                                                       of the significant difference in the performances for position 3
   For the last strategy (Strategy 3), we proceed by using the                  (Fig. 10).
leave-one-subject-out. The method is simple. Indeed, in our                        The performances presented in this paper are lower than those
study, Fall and Non-Fall events of 9 participants compose the                   in the literature. However, it is difficult to compare adequately.
training dataset, while instances of the 10th participant represent             Indeed, as you can see in Table III, most of the study exploits
the testing dataset. Then, iteratively, each of the ten subjects is             only one radar, and the conditions of the experiments depend
isolated to be the testing dataset. This method allows for observ-              greatly on the room configuration. For example, as presented in
ing the generalization performances of our solution. Figs. 8 to                 the related work, most of the work collected data in a small room
10 illustrate results. It shall be noted that the average accuracy              (with or without furniture), where the participant is very close to
is very close to performances from Table I. Fig. 8 represents                   the radar, increasing the detection rate. Furthermore, according
the simulation of falls at the position 1, we have 6 persons                    to the study presented in [33], the number of participants, and
with scores superior to 90%, 2 participants with an accuracy                    the types of simulated ADLs play a significant role in the
between 80% and 90%, and 2 participants with a score lower                      performances. Besides, in our study, the quality of data for the
than 80%. In Fig. 9, there are 8 persons with a global accuracy                 recording falls in the bathroom is affected by the presence of
superior to 90%, 1 participant with an accuracy between 80%                     walls. Finally, it shall be noted that we detected falls in each
and 90%, and only 1 participant with a score lower than 80%.                    position separately with data provided by the closest UWB radar.
Finally, in Fig. 10, we observe many performance differences                    The obtained performances are comparable to those presented in
between participants. Indeed, the CNN-LSTM model performs                       the literature. Indeed, global accuracies (with the corresponding
efficiently with 5 persons since global accuracy is superior to                 Kappa coefficient) are 98.51% (94.80%), 96.75% (90.88%), and
90%. Also, there are 3 participants with a score between 80%                    95.48% (87.39%) for positions 1, 2, and 3, respectively.



       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.
1282                                                                 IEEE JOURNAL OF BIOMEDICAL AND HEALTH INFORMATICS, VOL. 25, NO. 4, APRIL 2021



                                                                         TABLE III
                                                        PERFORMANCES OF THE LITERATURE VS. THIS STUDY




  TTS: Train/Test split; LOSO: Leave-One-Subject-Out.


                           VII. CONCLUSION                                       Québec (Canada) for the grant that made this project possible,
                                                                                 and the Canadian Foundation for Innovation (CFI). Also, the
   We proposed a new system to detect falls in an indoor environ-
                                                                                 authors would like to thank all participants, without them,
ment by using UWB radars and a CNN-LSTM architecture. Re-
                                                                                 this work would not have been possible. We want to thank
sults show high performances since we reached approximately
                                                                                 Camille Bertuglia, master student in our laboratory. He help us
a global accuracy of 90%. Also, compared to the literature
                                                                                 to acquire data.
exploiting UWB radars, it is the first time that such an in-depth
study is performed. Indeed, experiments have been conducted
in an apartment of 40 square meters, participants simulated falls
## REFERENCES
at three locations, data are recorded from three UWB radars,
and CNN-LSTM models have been tested with three strategies                        [1] H. Ritchie and M. Roser, “Age structure,” Our World in Data, 2020,
                                                                                      [Online]. Available: https://ourworldindata.org/age-structure
(Strategy 1, 2, and 3) including one that tests generalization of                 [2] W. H. Organization, World Health Statistics 2016: Monitoring Health for
the proposed solution. Hence, according to this study, we can                         the SDGs Sustainable Development Goals. Geneva, Switzerland: World
assert that UWB radars are an up-and-coming technology for                            Health Organization, 2016.
                                                                                  [3] N. Bohnert et al., Population Projections for Canada (2013 to 2063),
fall detection and activity recognition.                                              Provinces and Territories (2013 to 2038). Ottawa, On, Canada: Statistics
   However, some improvements can be made to increase the                             Canada, 2015.
fall detection rate. Here, there are three perspectives: we should                [4] S. A. Alshammari et al., “Falls among elderly and its relation with their
                                                                                      health problems and surrounding environmental factors in riyadh,” J.
recruit much more participants; participants should simulate                          Family Community Med., vol. 25, no. 1, p. 29, 2018.
falls in more locations; we can explore other data pre-processing                 [5] C. V. Weel, H. Vermeulen, and W. V. D. Bosch, “Falls, a community care
techniques such as those presented in the related work.                               perspective,” Lancet, vol. 345, no. 8964, pp. 1549–1551, 1995.
                                                                                  [6] D. Yacchirema, J. S. De Puga, C. Palau, and M. Esteve, “Fall detection
   Moreover, one of the future works is to get performances                           system for elderly people using IoT and big data,” Procedia Comput. Sci.,
of fall detection in real-time. Thus, we need to develop three                        vol. 130, pp. 603–610, 2018.
identical wireless communication (e.g., Wi-Fi) devices that                       [7] I. W. W. Wisesa and G. Mahardika, “Fall detection algorithm based on
                                                                                      accelerometer and gyroscope sensor data using recurrent neural networks,”
transfer the UWB data to a central system where the model                             in Proc. IOP Conf. Series: Earth Environ. Sci., IOP Publishing, 2019,
is implemented. More specifically, each device embeds a UWB                           vol. 258, no. 1, p. 012035.
radar connected to a highly-integrated System-in-Module (e.g.,                    [8] H. Gjoreski, J. Bizjak, and M. Gams, “Using smartwatch as telecare
                                                                                      and fall detection device,” in Proc. 12th Int. Conf. Intell. Environ., 2016,
Samsung’s ARTIK 520). Each device will also integrate a power                         pp. 242–245.
adapter that converts the power supply provided by the AC plug.                   [9] Z. Huang, Y. Liu, Y. Fang, and B. K. Horn, “Video-based fall detection
Then, the highly-integrated System-in-Module gets the UWB                             for seniors with human pose estimation,” in Proc. 4th Int. Conf. Universal
                                                                                      Village, 2018, pp. 1–4.
radar data and transfers them to the central system. The central                 [10] I. Halima, J.-M. Laferté, G. Cormier, A.-J. Fougère, and J.-L. Dillenseger,
system could be a small-board computer (e.g., Raspberry Pi) that                      “Depth and thermal information fusion for head tracking using particle
acquires, processes the data, and gives the classification with the                   filter in a fall detection context,” Integr. Comput.-Aided Eng., vol. 27,
                                                                                      no. 2, pp. 195–208, 2020.
implemented model. Further study is needed to make the right                     [11] C. Taramasco, Y. Lazo, T. Rodenas, P. Fuentes, F. Martínez, and J.
choice of components.                                                                 Demongeot, “System design for emergency alert triggered by falls using
   Finally, we are very enthusiastic (from the results obtained                       convolutional neural networks,” J. Med. Syst., vol. 44, no. 2, p. 50,
                                                                                      2020.
in our first exploration with raw data) to continue the research                 [12] L. Liu, M. Popescu, M. Skubic, M. Rantz, and P. Cuddihy, “An automatic
exploiting UWB radars.                                                                in-home fall detection system using doppler radar signatures,” J. Ambient
                                                                                      Intell. Smart Environ., vol. 8, no. 4, pp. 453–466, 2016.
                                                                                 [13] S. A. Shah and F. Fioranelli, “Human activity recognition: Preliminary
                          ACKNOWLEDGMENT                                              results for dataset portability using FMCW radar,” in Proc. Int. Radar
                                                                                      Conf., 2019, pp. 1–4.
   The authors would like to thank the Ministére de lÉconomie                    [14] B. Erol, M. G. Amin, and B. Boashash, “Range-doppler radar sensor fusion
et de lInnovation from the government of the province of                              for fall detection,” in Proc. IEEE Radar Conf., 2017, pp. 0819–0824.

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.
MAITRE et al.: FALL DETECTION WITH UWB RADARS AND CNN-LSTM ARCHITECTURE                                                                                          1283



[15] S. N. Robinovitch et al., “Video capture of the circumstances of falls in       [31] W.-H. Chen and H.-P. Ma, “A fall detection system based on infrared array
     elderly people residing in long-term care: An observational study,” Lancet,          sensors with tracking capability for the elderly at home,” in Proc. 17th Int.
     vol. 381, no. 9860, pp. 47–54, 2013.                                                 Conf. E-health Netw., Appl. Serv. (HealthCom)., 2015, pp. 428–434.
[16] L. Chen, R. Li, H. Zhang, L. Tian, and N. Chen, “Intelligent fall detection     [32] B. Erol and M. G. Amin, “Radar data cube analysis for fall detection,” in
     method based on accelerometer data from a wrist-worn smart watch,”                   Proc. IEEE Int. Conf. Acoust., Speech Signal Process., 2018, pp. 2446–
     Measurement, vol. 140, pp. 215–226, 2019.                                            2450.
[17] A. Chelli and M. Pätzold, “A machine learning approach for fall detection       [33] A. Shrestha, J. Le Kernec, F. Fioranelli, E. Cippitelli, E. Gambi, and S.
     and daily living activity recognition,” IEEE Access, vol. 7, pp. 38 670–             Spinsante, “Feature diversity for fall detection and human indoor activities
     38 687, 2019.                                                                        classification using radar systems,” 2017.
[18] E. Casilari and M. A. Oviedo-Jiménez, “Automatic fall detection system          [34] J. Le Kernec et al., “Radar signal processing for sensing in assisted living:
     based on the combined use of a smartphone and a smartwatch,” PLoS One,               The challenges associated with real-time implementation of emerging al-
     vol. 10, no. 11, 2015.                                                               gorithms,” IEEE Signal Process. Mag., vol. 36, no. 4, pp. 29–41, Jul. 2019.
[19] A. M. Sabatini, G. Ligorio, A. Mannini, V. Genovese, and L. Pinna, “Prior-      [35] H. Li, A. Shrestha, H. Heidari, J. Le Kernec, and F. Fioranelli, “Magnetic
     to-and post-impact fall detection using inertial and barometric altimeter            and radar sensing for multimodal remote health monitoring,” IEEE Sensors
     measurements,” IEEE Trans. Neural Syst. Rehabil. Eng., vol. 24, no. 7,               J., vol. 19, no. 20, pp. 8979–8989, Oct. 2018.
     pp. 774–783, Jul. 2015.                                                         [36] H. Hong, L. Zhang, C. Gu, Y. Li, G. Zhou, and X. Zhu, “Noncontact sleep
[20] A. Diaz, M. Prado, L. Roa, J. Reina-Tosina, and G. Sanchez, “Preliminary             stage estimation using a CW doppler radar,” IEEE J. Emerg. Sel. Topics
     evaluation of a full-time falling monitor for the elderly,” in Proc. 26th            Circuits Syst., vol. 8, no. 2, pp. 260–270, Jun. 2018.
     Annu. Int. Conf. IEEE Eng. Med. Biol. Soc., 2004, vol. 1, pp. 2180–2183.        [37] H. Li, A. Shrestha, H. Heidari, J. Le Kernec, and F. Fioranelli, “Bi-lstm
[21] A. Bourke, J. Obrien, and G. Lyons, “Evaluation of a threshold-based                 network for multimodal continuous human activity recognition and fall
     tri-axial accelerometer fall detection algorithm,” Gait Posture, vol. 26,            detection,” IEEE Sensors J., vol. 20, no. 3, pp. 1191–1201, Feb. 2020.
     no. 2, pp. 194–199, 2007.                                                       [38] H. Sadreazami, M. Bolic, and S. Rajan, “Capsfall: Fall detection using
[22] H. Kerdegari, K. Samsudin, A. R. Ramli, and S. Mokaram, “Evaluation                  ultra-wideband radar and capsule network,” IEEE Access, vol. 7, pp.
     of fall detection classification approaches,” in Proc. 4th Int. Conf. Intell.        55 336–55 343, 2019.
     Adv. Syst., 2012, vol. 1, pp. 131–136.                                          [39] M. S. Seyfioğlu, A. M. Özbayoğlu, and S. Z. Gürbüz, “Deep convolutional
[23] C. Medrano, R. Igual, I. Plaza, and M. Castro, “Detecting falls as novelties         autoencoder for radar-based classification of similar aided and unaided
     in acceleration patterns acquired with smartphones,” PLoS One, vol. 9, no.           human activities,” IEEE Trans. Aerosp. Electron. Syst., vol. 54, no. 4,
     4, 2014.                                                                             pp. 1709–1723, Aug. 2018.
[24] X. Yang, A. Dinh, and L. Chen, “A wearable real-time fall detector based        [40] H. Sadreazami, M. Bolic, and S. Rajan, “Fall detection using standoff
     on naive bayes classifier,” in Proc. Can. Conf. Elect. Comput. Eng., 2010,           radar-based sensing and deep convolutional neural network,” IEEE Trans.
     pp. 1–4.                                                                             Circuits Syst. II: Exp. Briefs, vol. 67, no. 1, pp. 197–201, Jan. 2020.
[25] R. Gupta, P. Anand, S. Chaudhury, B. Lall, and S. Singh, “Compressive           [41] Y. Wang, J. Zhou, J. Tong, and X. Wu, “UWB-radar-based synchronous
     sensing based privacy for fall detection,” 2019, arXiv:2001.03463.                   motion recognition using time-varying range–doppler images,” IET Radar,
[26] S. S. Khan, J. Nogas, and A. Mihailidis, “Spatio-temporal adversarial                Sonar Navig., vol. 13, no. 12, pp. 2131–2139, 2019.
     learning for detecting unseen falls,” 2019, arXiv:1905.07817.                   [42] R. Fu, Z. Zhang, and L. Li, “Using lstm and gru neural network methods for
[27] N. Lu, Y. Wu, L. Feng, and J. Song, “Deep learning for fall detec-                   traffic flow prediction,” in Proc. 31st Youth Academic Annu. Conf. Chin.
     tion: Three-dimensional cnn combined with lstm on video kinematic                    Assoc. Autom., 2016, pp. 324–328.
     data,” IEEE J. Biomed.l Health Inform., vol. 23, no. 1, pp. 314–323,            [43] J. Li, Z. Zeng, J. Sun, and F. Liu, “Through-wall detection of human being’s
     Jan. 2018.                                                                           movement by uwb radar,” IEEE Geosci. Remote Sens. Lett., vol. 9, no. 6,
[28] Y. Fan, M. D. Levine, G. Wen, and S. Qiu, “A deep neural network                     pp. 1079–1083, Nov. 2012.
     for real-time detection of falling humans in naturally occurring scenes,”       [44] V.-H. Nguyen and J.-Y. Pyun, “Location detection and tracking of mov-
     Neurocomputing, vol. 260, pp. 43–58, 2017.                                           ing targets by a 2d ir-uwb radar system,” Sensors, vol. 15, no. 3,
[29] J. Clemente, F. Li, M. Valero, and W. Song, “Smart seismic sensing for               pp. 6740–6762, 2015.
     indoor fall detection, location and notification,” IEEE J. Biomed. Health       [45] S. Hochreiter and J. Schmidhuber, “Long short-term memory,” Neural
     Inform., vol. 24, no. 2, pp. 524–532, Feb. 2020.                                     Comput., vol. 9, no. 8, pp. 1735–1780, 1997.
[30] M. Popescu and A. Mahnot, “Acoustic fall detection using one-class              [46] A. Graves and J. Schmidhuber, “Framewise phoneme classification with
     classifiers,” in Proc. Annu. Int. Conf. IEEE Eng. Med. Biol. Soc., 2009,             bidirectional lstm networks,” in Proc. IEEE Int. Joint Conf. Neural Netw.,
     pp. 3505–3508.                                                                       2005, vol. 4, pp. 2047–2052.




        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:39:42 UTC from IEEE Xplore. Restrictions apply.

