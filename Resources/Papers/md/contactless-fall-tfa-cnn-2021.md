6842                                                     IEEE TRANSACTIONS ON INDUSTRIAL INFORMATICS, VOL. 17, NO. 10, OCTOBER 2021




## Contactless Fall Detection Using
       Time-Frequency Analysis and Convolutional
## Neural Networks
                 Hamidreza Sadreazami , Member, IEEE, Miodrag Bolic , Senior Member, IEEE,
                                and Sreeraman Rajan , Senior Member, IEEE


   Abstract—Automatic detection of a falling person based                                                    I. INTRODUCTION
on noncontact sensing is a challenging problem with ap-
                                                                                         UMAN activity recognition has become increasingly
plications in smart homes for elderly care. In this article,
we propose a radar-based fall detection technique based
on time-frequency analysis and convolutional neural net-
                                                                                 H       important in recent years as it enables automatic
                                                                                 assessment of subjects’ health and well-being [1]–[3]. Among
works. The time-frequency analysis is performed by apply-                        the elderly, most injury-related hospitalizations are due to
ing the short-time Fourier transform to each radar return
signal. The resulting spectrograms are converted into bi-                        falls [4]. Therefore, accidental fall detection is an important
nary images, which are fed into the convolutional neural                         subset of human activity recognition [5]–[7]. If no preventive
network. The network is trained using labeled examples                           measures are undertaken, the number of injuries due to falls
of fall and nonfall activities. Our method employs high-                         can double by 2030 due to aging population [8]. Unfortunately,
level feature learning, which distinguishes it from previ-                       continuous 24-h human monitoring of elderly to prevent falls
ously studied methods that use heuristic feature extraction.
The performance of the proposed method is evaluated by                           is impossible, and therefore, an automated way of monitoring
conducting several experiments on a set of radar return                          them is needed in order to detect and prevent falls.
signals. We show that our method distinguishes falls from                           Activity-monitoring methods currently use inexpensive wear-
nonfalls with 98.37% precision and 97.82% specificity, while                     able sensors such as accelerometers [9]. With the emergence of
maintaining a low false-alarm rate, which is superior to                         smart homes, noncontact indoor monitoring using radar-based
existing methods. We also show that our proposed method
is robust in that it successfully distinguishes falls from                       technology is gaining interest as radar signals can penetrate ob-
nonfalls when trained on subjects in one room, but tested                        stacles such as wall to locate targets [10]. In addition, radar-based
on different subjects in a different room. In the proposed                       methods do not violate the privacy of the monitored subjects [11]
convolutional neural network, the hierarchical features ex-                      and preclude the need for wearing a sensor [2]. More recently,
tracted from the radar return signals are the key to under-                      ultrawideband (UWB) radars have gained popularity as active
stand the fundamental composition of human activities and
determine whether or not a fall has occurred during human                        monitoring sensors. UWB radars are more suited for activity and
daily activities. Our method may be extended to other radar-                     fall recognition because of robustness to multipath fading, higher
based applications such as apnea detection and gesture                           penetration ability, finer time resolution [12], and higher spatial
detection.                                                                       resolution when compared to continuous wave radars [13]–[17].
   Index Terms—Convolutional neural network, fall detec-                            Radar-based monitoring methods use either a threshold [18]
tion, time-frequency analysis, ultrawideband (UWB) radar.                        or learning-based approach [19] to detect falls. Threshold-based
                                                                                 fall detection requires effective features or descriptors, and when
                                                                                 such descriptors exceed preset thresholds during a fall, an alarm
                                                                                 would be triggered. Learning-based approaches require models
                                                                                 trained using features extracted from either the time or the
                                                                                 frequency domain.
   Manuscript received August 14, 2020; revised November 5, 2020
                                                                                    In [19], a human activity recognition method based on radar
and December 3, 2020; accepted January 1, 2021. Date of publication              micro-Doppler data was designed by extracting features from
January 5, 2021; date of current version June 30, 2021. Paper no.                time-velocity and cadence-velocity domains while in [20], a
TII-20-3918. (Corresponding author: Hamidreza Sadreazami.)
   Hamidreza Sadreazami and Miodrag Bolic are with the School of Elec-
                                                                                 similar design was used to classify people. In [21], a human gait
trical Engineering and Computer Science, University of Ottawa, Ottawa,           classification method was proposed using the motion signature
ON K1N 6N5, Canada (e-mail: hamidreza.sadreazami@mail.mcgill.ca;                 from arm and leg movements. In [22], using micro-Doppler
mbolic@eecs.uottawa.ca).
   Sreeraman Rajan is with the Department of Systems and Computer
                                                                                 signature, different human activities were classified over an
Engineering, Carleton University, Ottawa, ON K1S 5B6, Canada (e-mail:            extended time duration, through a wall, and at multiple angles
sreeramanr@sce.carleton.ca).                                                     to the radar. A wavelet-based approach was devised in [23] for
   Color versions of one or more figures in this article are available at
https://doi.org/10.1109/TII.2021.3049342.
                                                                                 fall detection using Doppler radars. In [24], fall detection was
   Digital Object Identifier 10.1109/TII.2021.3049342                            achieved exploiting time-frequency characteristics of the radar

                    1551-3203 © 2021 IEEE. Personal use is permitted, but republication/redistribution requires IEEE permission.
                                  See https://www.ieee.org/publications/rights/index.html for more information.


       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:34:05 UTC from IEEE Xplore. Restrictions apply.
SADREAZAMI et al.: CONTACTLESS FALL DETECTION USING TIME-FREQUENCY ANALYSIS AND CONVOLUTIONAL NEURAL NETWORKS                                             6843



Doppler signatures and the events were classified by a sparse
Bayesian classifier using the joint statistics of three different
features. In all these methods, feature engineering had to be
done by a human and the classification accuracy depended on
the engineered features.
   Instead of using engineered features, automatic feature ex-
traction for fall detection can be achieved through deep learn-
ing methods [25]. A deep neural network approach for fall
detection was presented in [26]. Gray-scale images were ob-
tained from spectrograms, and stack auto-encoders were used
to extract the features from the gray-scale images. Softmax
regression was used to classify different kinds of activities
including falls. In [27], transfer learning was investigated for
classifying activities using data collected from wearable sen-                  Fig. 1.   Postures in one of the room environments. (a) Before. (b) After
sors. The pretrained AlexNet was used for feature extraction                    a fall.
from spectrogram images followed by a linear or nonlinear
support vector machine (SVM) for classification. In [28], human
micro-Doppler signatures of different simulated activities were                 5.7 × 2.2 m2 . The radar was mounted 1.5 m above the floor
classified using a convolutional (convolutional) neural network                 level. The sampling rate of the radar was 200 Hz, which is
using both color and gray-scale time-frequency representations                  high enough to capture high-frequency components of the radar
as input to the network. All the previous research cited above                  signal that appear during a fall (around 60 Hz). The dataset
used object-specific feature extraction. None of them addressed                 used in our experiments included different types of fall and
radar-based fall detection using automatic features that were                   nonfall activities performed by ten different healthy subjects
based on shape of the distribution of the energy in the joint                   aging from 20–35, namely, walking toward radar and falling
time-frequency domain.                                                          down at different distances to the radar, i.e., 3 or 4 m, standing in
   This article proposes a fall detection method by projecting                  front of radar and falling down at different distances to the radar,
the energy content of the fall and nonfall activities, contained in             standing and falling down perpendicular to the radar line of sight,
their corresponding spectrograms, into binary image represen-                   lying down with or without side rolling or other movements, and
tations. The binary image is enhanced using a morphological                     standing up in front of the radar, and lying down and standing up
operation and then is used as input into a deep convolutional                   perpendicular to the radar line of sight. Each activity lasted 15 s,
neural network that performs automatic feature extraction. The                  within which one of these activities occurred. The signals were
proposed method will be compared with other machine learning                    then digitized at a rate of 200 samples/s. The range of the radar
approaches such as decision trees (DTs), k-nearest neighbors                    used in this study was set to 10 m. Since it has a 5.35 cm range
(KNN), and SVMs. These approaches are presented with the                        resolution, there are 189 range bins. The type and number of
same input that was applied to the deep convolutional network                   different activities performed are given in Table I. Fig. 1 shows
used in the proposed approach.                                                  the posture of one of the subjects before and after a fall incident.
   The rest of this article is organized as follows. In Section II,             The data were manually labeled as fall or nonfall. Ethics approval
the UWB radar used in the data acquisition and experiment setup                 for conducting the experiments was obtained from the Research
in the proposed method is described. In Section III, the proposed               Ethics Board at the University of Ottawa.
fall detection method comprising of target range selection, time-
frequency analysis, binary image generation, and data augmen-                               III. PROPOSED FALL DETECTION METHOD
tation along with automatic feature extraction are described. In
                                                                                  In this section, the proposed fall detection method based
Section IV, experimental results, current challenges, and future
                                                                                on time-frequency representation of the radar return signals
directions on radar-based fall detection are presented. Finally,
                                                                                and automatic feature extraction using a convolutional neural
Section V concludes this article.
                                                                                network is presented. Fig. 2 shows the block diagram of the
                                                                                proposed radar-based fall detection method.
       II. EXPERIMENTAL SETUP AND MEASUREMENT
   The radar used in this experiment was the Xethru X4M03                       A. Target Range Selection
development kit, manufactured by Novelda (Oslo, Norway) [29].                      The radar return signals were recorded into a matrix, where
This radar uses a UWB transceiver operating in the range of                     each column represents the spatial samples from different ranges
5.9–10.3 GHz and a patch antenna with a 65◦ aperture in both                    (fast-time), while the data in each row corresponds to obser-
azimuth and elevation axes. This particular radar was chosen                    vations recorded at different time intervals (slow-time). The
because of its low cost, small size, and high spatial resolu-                   first 20 range bins, corresponding to all ranges less than 1 m
tion. The experiments were conducted in two realistic room                      from the radar, were noisy and were removed before further
environments at the University of Ottawa. Both rooms were                       processing. The observations from the range bin having the
cluttered and had the following dimensions: 12.6 × 4.1 and                      highest variance was chosen to be the target range bin and used

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:34:05 UTC from IEEE Xplore. Restrictions apply.
6844                                                                  IEEE TRANSACTIONS ON INDUSTRIAL INFORMATICS, VOL. 17, NO. 10, OCTOBER 2021



                                                                 TABLE I
                        TYPES AND NUMBER OF ACTIVITIES PERFORMED BY TEN DIFFERENT SUBJECTS IN TWO DIFFERENT ROOMS




Fig. 2. Block diagram of the proposed radar-based fall detection
method which is built upon time-frequency analysis and convolutional
neural network.




                                                                                 Fig. 4.   Time-frequency signature. (a) Falling down. (b) Standing up.



                                                                                 frequency contents [7]. In view of this, in order to analyze the
                                                                                 radar return signals, a joint time-frequency representation is ob-
                                                                                 tained by applying the short-time Fourier transform (STFT) [30].
                                                                                 For a radar return signal in the target range bin x[·], STFT is
                                                                                 defined as follows:
                                                                                                         ∞
                                                                                                         
                                                                                           X[n, k] =           x[r]W [r − n] exp(−j2πrk/N )               (1)
                                                                                                        r=−∞

                                                                                 where W [·] is a finite length sliding window function (e.g., a
                                                                                 Hamming window), n is the time index, k = 0, 1, . . ., N − 1 is
Fig. 3. Radar return signal in the target range bin. (a) Falling down.
(b) Standing up.
                                                                                 the frequency index, and N is the number of frequency points.
                                                                                 The squared magnitude of STFT yields the spectrogram, i.e.,
                                                                                 S(n, k) = |X[n, k]|2 . In this experiment, a Hamming window of
for further processing. Fig. 3(a) and (b) shows the radar return
                                                                                 size 256 samples was applied to the radar returns. The main lobe
signals normalized by the maximum amplitude for the target
                                                                                 of the Hamming window is inversely proportional to the window
range bin after clutter removal, corresponding to falling down
                                                                                 length and the magnitude of its sidelobes is well attenuated.
and standing up activities, respectively. More specifically, in
                                                                                 We use an 80% overlap between adjacent windows in order to
Fig. 3(a), the subject is standing in front of the radar and then
                                                                                 minimize the effect of spectral leakage [30] and to better localize
falls, while in Fig. 3(b), the subject is lying down and then stands
                                                                                 the fall events (to make sure the event is not missed). We found
up while facing the radar.
                                                                                 that lower amounts of overlap do not work as well. For example,
                                                                                 with 50% overlap, falls were not always completely localized.
B. Time-Frequency Analysis
                                                                                 With larger overlaps, the whole event is captured in at least
 It is known that the nature of the radar return signal from                     one window [31]; this cannot be assured with smaller overlaps.
moving human subjects is nonstationary with time-varying                         Fig. 4(a) and (b) shows the time-frequency plot of the falling

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:34:05 UTC from IEEE Xplore. Restrictions apply.
SADREAZAMI et al.: CONTACTLESS FALL DETECTION USING TIME-FREQUENCY ANALYSIS AND CONVOLUTIONAL NEURAL NETWORKS                                                6845



                                                                                                                 TABLE II
                                                                                                  CONFIGURATION OF THE PROPOSED NETWORK




Fig. 5.    Binary time-frequency signature. (a) Falling down. (b) Standing
up.
                                                                                   energy of an activity is converted into a binary image, which will
                                                                                   be denoted as Z. The image is then fed into the convolutional
down and standing up activities, corresponding to the radar                        neural network. The key attribute of this network is that it
return signals of Fig. 3, respectively, where the horizontal axis                  contains different processing units such as convolution, pooling,
is time and the vertical axis is frequency. The image intensities                  activation, and normalization.
indicate the energy corresponding to the micro motion signature                        Inspired by [35] and [36], we construct a neural network to
at each time instant [32]. It is seen from Fig. 4 that the energy                  solve our binary classification problem by stacking two convo-
content of each activity is distinguishable in the time-frequency                  lutional layers and four FC layers. In the first convolutional layer
domain. More specifically, a fall incident results in an instan-                   c1 , 64 kernels {kjc1 }64
                                                                                                          j=1 of size 3 × 3 were convolved with the
taneous high-frequency content with a specific distribution of                     input images with a stride of 1. A bias value was then added
energy over time, whereas a nonfall activity exhibits a lower                      and an activation function was applied to the output resulting in
frequency peak with different energy distribution.                                 a feature map Zc1 with a depth of 64. The rectified linear unit
                                                                                   activation function (ReLU), defined as f (x) = max(0, x), was
C. Binary Image Generation                                                         employed. Each unit in a convolutional layer was connected to
                                                                                   a local patch in the feature maps of the previous layer via a set
   Radar signals of fall and nonfall activities were processed and
                                                                                   of convolutional kernels.
converted into binary image representations. Each binary image
                                                                                       In order to obtain distortion-invariant features and reduce
has a size of m1 × m2 pixels, corresponding to m1 frequencies
                                                                                   the spatial resolution of the feature map, a nonoverlapping
and m2 time instants at which the spectrogram is computed. It is
                                                                                   2 × 2 max-pooling (MP) layer p1 was used. The pooling was
known that the raw spectrogram images exhibit a high level of
                                                                                   performed by selecting the maximum values of the convolved
noise, which may obscure the true signature of the activity under
                                                                                   features among the adjacent neurons that are located in the
study [26]. This may result in a lower classification performance,
                                                                                   preceding convolutional layer.
especially when using a neural network. To address this issue,
                                                                                       The number of filters increases from the first to second
a binary time-frequency signature of each activity was first
                                                                                   convolutional layer since the spatial size of the feature maps
obtained by applying the k-means clustering algorithm [33] to
                                                                                   decreases after pooling operation, and thus, the depth needs
the time-frequency representations, i.e., pixel clustering. The
                                                                                   to be increased by adding more filters. In view of this, in the
clusters were then passed through a median filter to remove the
                                                                                   next convolution layer c2 , the feature map from the previous
outliers. In addition, a morphological opening operation was
                                                                                   pooling layer Zc1 p1 was convolved with 128 kernels {kjc2 }128   j=1
performed to remove disconnected regions and fully preserve
                                                                                   of size 3 × 3 with a stride of 1. A bias value was added and the
the shape of the energy content of the activity. We do this by
                                                                                   ReLU activation function was applied to the output, resulting
creating a structuring element [34], which identifies the pixel
                                                                                   in a feature map Zc2 with a depth of 128. The second MP
in the image that is being processed together with the adjacent
                                                                                   layer p2 of size 2 × 2 was then applied. The convolutional
neighboring pixels. The result of this postprocessing is the sig-
                                                                                   layers capture low-level features, while higher layers extract
nature of different activities. Fig. 5 shows binary time-frequency
                                                                                   higher-level features by combining low-level ones. In addition,
signatures corresponding to the fall and nonfall spectrograms in
                                                                                   in the convolutional layers, a weight sharing mechanism exists
Fig. 4, respectively.
                                                                                   among the neurons that are located in the same feature map. In
                                                                                   the proposed network, the convolutional layers were followed
D. Deep Neural Network
                                                                                   by four FC layers and one output layer for class prediction. The
   Automatic feature extraction precludes the domain specific                      four FC layers have 500, 200, 100, and 50 neurons, respectively.
feature extraction crafted manually by the experts. In order to                    The output of the second convolutional layer Zc2 p2 was flattened
automatically extract features from the radar binary images, a                     into a 1-D vector, resulting in parameter concatenation and used
neural network comprising of convolutional and fully connected                     as the input to the first FC layer. Neurons in each FC layer
(FC) layers was constructed. Fig. 6 shows the architecture of                      have full connections to all neurons in the previous layer. Their
the proposed convolutional neural network, and Table II gives                      activations can be computed by applying a matrix multiplication
kernel sizes and output shapes for each layer. As discussed in                     and a bias offset followed by the ReLU activation function for
Section III-C, the time-frequency representation containing the                    the first four layers and the softmax function for the output layer.
          Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:34:05 UTC from IEEE Xplore. Restrictions apply.
6846                                                                     IEEE TRANSACTIONS ON INDUSTRIAL INFORMATICS, VOL. 17, NO. 10, OCTOBER 2021




Fig. 6.     Architecture of the proposed convolutional neural network with Convolutional, MP, and FC layers.



The softmax function is given by the following:                                     E. Data Augmentation
                           exp(Zr )                                                    Because falling is not a common human activity, fall data are
                   hr =  2           , for r = 1, 2                         (2)    scarce. In order to ensure that the fall detection model has good
                                    v
                          v=1 exp(Z )
                                                                                    generalization, we employ data augmentation. Data augmenta-
where Zr is the rth score of the output layer and hr denotes                        tion artificially increases the number of exemplars or patterns
the output of the softmax function, i.e., the probability of the                    in the training set, so that the network never sees twice the
predicted classes. If Ntr is the number of trials, the actual                       exact same image. This prevents the network from overfitting.
labels for each fall or nonfall are {li }N
                                         i=1 , and the probabilistic
                                           tr
                                                                                    There are several ways of augmenting the data described in
outcomes are hi , then the softmax cross-entropy cost function                      the literature. They can be broadly divided into two groups,
L is defined as follows:                                                            namely, oversampling and data warping [39]. Oversampling
                                  N
                       1    tr        2                                           methods such as random over sampling or synthetic minority
                   L=−             I(li = v)log(hvi )                        (3)    oversampling technique artificially increase the exemplars. The
                       Ntr i=1 v=1
                                                                                    exemplars are nothing but copies of the existing ones in the
where I(.) is the indicator function. The entire network was                        dataset. Data warping uses image transformation processes such
trained by means of the back-propagation algorithm [37] to                          as geometric transformations, flipping, cropping, and translation
iteratively update the weights and minimize the cost function.                      to produce exemplars, which are different from the existing
The Adam optimizer was used in the learning process, which has                      exemplars in the dataset. Fall detection using radars has sev-
been shown to provide fast convergence rates [38]. It is known                      eral dependencies such as different return power, presence or
that the Adam optimizer combines the properties of the AdaGrad                      absence of clutters, elevation and angle of the radars. As all
and RMSProp algorithms and enables an optimization algorithm                        these variabilities cannot be captured in a dataset, data aug-
to handle sparse gradients [38]. Through the optimization model,                    mentation is needed. Oversampling augmentation is unsuitable
the feature learning and classification are mutually enhanced                       because it will not produce exemplars that are representative
and the learned features gain more discriminative power for the                     of these variabilities. Therefore, image transformations were
ultimate classification task.                                                       used to realize such feature variability and account for phys-
   In the proposed convolutional neural network, hyperparam-                        ically meaningful and intuitive interpretation of the activities.
eter selection was done by tuning the model with different                          The image transformations used in this work were rotation,
values of hyperparameters and selecting the one based on the                        width shifting, height shifting, horizontal flipping, shearing,
validation accuracy, i.e., a grid search optimization technique.                    and zooming. For instance, patterns resulting from horizontal
The hyperparameters of the proposed network are the learn-                          flipping and width shifting could represent fall/nonfall activities
ing rate, which determines the magnitude of weight changes                          at different distances from the radar sensor, while those obtained
when a classification error occurs during the training phase, and                   using zooming and height shifting may account for falling down
the drop-out regularization factor, which restricts the network                     at different angles relative to the radar. Note that the proposed
adaptation to the training data and, thus, avoids overfitting and                   convolutional neural network aims to extract robust features to
high-dimensionality issues.                                                         correctly classify a variety of instances. Such robust features can



          Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:34:05 UTC from IEEE Xplore. Restrictions apply.
SADREAZAMI et al.: CONTACTLESS FALL DETECTION USING TIME-FREQUENCY ANALYSIS AND CONVOLUTIONAL NEURAL NETWORKS                                             6847



                           TABLE III                                            SVM (LSVM) and Gaussian SVM (GSVM) were employed.
  CONFUSION MATRIX DEFINITION FOR THE FALL DETECTION PROBLEM
                                                                                The LSVM uses the l2 regularization and the squared hinge loss
                                                                                function [41]. The parameters of the GSVM are the regulariza-
                                                                                tion parameter C = 1, which aims at classifying the training
                                                                                dataset by providing the model with freedom to select more
                                                                                samples as support vectors and the cutoff parameter γ = 0.001,
                                                                                which identifies the extent of the influence of a single training
                                                                                sample (exemplar) [41]. The abovementioned model parameters
be learned only if a sufficiently large number of different types
                                                                                were tuned using a grid search on a validation set for higher
of instances are presented to the network.
                                                                                classification accuracy.
                                                                                   Table IV describes the classification metrics obtained when
   IV. RESULTS, CHALLENGES, AND FUTURE DIRECTIONS                               each classifier was trained on 336 data samples, as well as the
   In this section, the experimental results, obtained using the                same metrics when the classifiers were trained on an augmented
proposed method, are presented. The performance of the con-                     dataset (augmented by a factor of 10). The classifiers were
volutional neural network is compared with an auto-encoder                      trained using the radar data for nine human subjects and tested
(AE) [26], a SVM [40], DTs, and KNN [4]. To evaluate the                        using the data from the tenth subject in a leave-one-subject-out
performance of the proposed fall detection method, a set of                     cross-validation sense (tenfold). It is seen from this table that the
radar data, collected as described in Section II, was used. The                 proposed method outperforms the other methods when tested
radar return signal was processed to obtain the spectrogram.                    with unseen set of data. When the number of data samples
The spectrogram was treated as an image containing the energy                   increases, the performance improvement using the proposed
content of a particular activity. The image was then binarized and              method is more significant than that using the other methods,
further enhanced using the morphological opening operation.                     as evidenced by the specificity values. It should be noted that
In the experiments, the image size, discussed in Section III-C,                 the hierarchical features extracted from radar binary images are
was fixed by setting the values of m1 and m2 to 129 and                         the key to understand the fundamental composition of human
139, respectively. The resulting binary image was augmented                     activities and determine whether or not a fall occurs during
to obtain enough data to train the proposed convolutional neural                human daily activities.
network. The trained network is then used to test whether or not                   Tables V and VI give classification metrics obtained using a
a test image represents a fall incident.                                        fivefold cross validation for the proposed fall detection method
   To evaluate the classification performance of the proposed                   and those obtained using other methods, with original data
method, a fivefold cross validation was performed. For the ease                 and with the data augmented by a factor of 10, respectively.
of defining metrics, the true positives (TP), false positives (FP),             In the case of the DT approach, two attribute selection mea-
true negatives (TN), and false negatives (FN), corresponding                    sures, namely, the Gini index (DTG) and information gain or
to the fall and nonfall activities, are defined in Table III. The               entropy (DTE) were considered [42]. It is seen from these tables
main diagonal entries are the correct classification rates for                  that the proposed method is capable of detecting falls with
fall and nonfall activities. The off-diagonal entries indicate the              higher accuracy, precision, and specificity values, indicating
misclassification rates.                                                        the capability to better detect a fall incident when it occurs
   The following metrics are used to evaluate the performance                   and avoiding false alarms. Without data augmentation, DTG,
of the proposed fall detection method:                                          DTE, LSVM, GSVM, KNN, and AE achieve 81.30%, 82.47%,
    1) Precision (PR), PR = TP+FP  TP                                           89.01%, 85.71%, 92.84%, and 92.85% classification accura-
    2) Recall or sensitivity (SE), SE = TP+FN
                                            TP                                  cies, respectively, while the proposed method outperforms the
                                                                                other methods by providing 95.83% classification accuracy and
    3) Specificity (SP), SP = TN+FP TN
                                                                                97.82% specificity. It is also seen from Table VI that when
    4) False Positive Rate (FPR), FPR = FP+TN  FP
                                                                                the data are augmented, the proposed method detects the fall
    5) False Negative Rate (FNR), FNR = FN+TP    FN
                                                                                incidents with a lower false alarm rate as evidenced by the higher
    6) F-score, F = 2TP+FP+FN .
                           2TP
                                                                                value of specificity. The overall result indicates that the proposed
   Table IV gives various classification metrics obtained using                 method is effective in classifying fall from nonfall activities.
the proposed method and those of the other methods, namely,                     The superior performance of the proposed convolutional neural
KNN, DT, AE, and SVM. It should be noted that for all these                     network-based fall detection method can be attributed to the fact
methods, the resulting binary images from Section III-C were                    that the proposed model finds the saliency of the signal in feature
vectorized and used as the input to the classifier.                             representation more accurately than the other methods. This is
   In the case of AE, we followed the approach in [26] to reduce                due to the fact that the convolutional neural networks make use
the dimensionality of the feature vector in such a way that the                 of hierarchical distributed representations.
binary images were compressed into 300 and 150 features using                      The statistical significance of the proposed method was also
two stacked encoders with l2 regularization. In addition, the                   investigated. The p-value for a balanced one-way analysis of
softmax regression classifier was used in the output layer. In the              variance (ANOVA) between different methods, when comparing
case of KNN, different values for k were examined and the best                  the classification accuracies, is 0.0299; when comparing pre-
results, i.e., k = 1 were reported. In the case of SVM, linear                  cision values, it is 0.0333. This indicates that the differences

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:34:05 UTC from IEEE Xplore. Restrictions apply.
6848                                                                           IEEE TRANSACTIONS ON INDUSTRIAL INFORMATICS, VOL. 17, NO. 10, OCTOBER 2021



                                                                   TABLE IV
                         PR, SP, SE, FPR, AND FNR (%) FOR VARIOUS METHODS, IN A LEAVE-ONE-SUBJECT-OUT CROSS VALIDATION




                          The bold entities show the result of the proposed method.
                            TABLE V
            PERFORMANCE METRICS FOR VARIOUS CLASSIFIERS




The bold entities show the result of the proposed method.

                           TABLE VI
        PERFORMANCE METRICS FOR VARIOUS CLASSIFIERS AFTER
                      DATA AUGMENTATION




The bold entities show the result of the proposed method.                               Fig. 7. Box plots for classification metrics of various methods. (a)
                                                                                        Accuracy. (b) Precision.
between the methods are significant. Fig. 7 shows box plots for                                                        TABLE VII
classification metrics of various methods. It is seen from this                            CLASSIFICATION METRICS (AC, PR, SE, SP) OBTAINED USING THE
figure that the proposed method using the convolutional neural                           PROPOSED FALL DETECTION METHOD AND THOSE OBTAINED USING [26]
                                                                                        AND [43] AND THE ONE WITH 27 FEATURES EXTRACTED FROM THE RADAR
network provides higher accuracy and precision on a fivefold                                         DATA (27F ), IN A FIVEFOLD CROSS VALIDATION
cross validation. This figure also shows that the proposed method
provides lower standard deviation in both the metrics, indicating
the high level of agreement between the results of each fold.
   Receiver operating characteristic (ROC) curves for various
methods were also obtained. Fig. 8 shows the ROC curves
for KNN-, AE-, and CNN-based methods obtained through                                       The bold entities show the result of the proposed method.
fivefold cross validation. The area under the ROC curve (AUC)
for each method was obtained from the corresponding average                             features (27F ) including maximum, minimum, mean, standard
ROC curve. It is seen from these figures that the proposed                              deviation, skewness, kurtosis, interquartile range, area under the
method based on the convolutional neural network provided the                           curve, area under the squared curve of the radar time series
highest AUC, indicating its superiority to the other methods in                         signal, its first derivative, and its discrete Fourier transformed
discriminating fall from nonfall activities.                                            version. The extracted features were classified using a SVM
   We now compare the performance of the proposed fall de-                              classifier. Table VII gives classification metrics in fivefold cross
tection method to those presented in [26] and [43]. To this end,                        validation obtained using the proposed method and those of the
as discussed in [26], three features, namely, extreme frequency                         other methods. It is seen from this table that the proposed method
magnitude, extreme frequency ratio, and time-span of event,                             provides higher classification metrics as compared to the other
were extracted from the spectrograms. These features were used                          methods based on manual feature extraction techniques.
to classify the fall and nonfall activities using a SVM classifier. In                     We also investigated the performance of the proposed fall
addition, as discussed in [43], several features including higher-                      detection method when the network was trained on the dataset
order statistics such as moments, cumulants, and the energy                             collected from a set of subjects in one room and tested on the
of the normalized signal were extracted. We also extracted 27                           dataset collected from different subjects in the another room.

       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:34:05 UTC from IEEE Xplore. Restrictions apply.
SADREAZAMI et al.: CONTACTLESS FALL DETECTION USING TIME-FREQUENCY ANALYSIS AND CONVOLUTIONAL NEURAL NETWORKS                                                6849




Fig. 8.    ROC curves and AUCs obtained using fivefold cross validation for (a) KNN, (b) AE, and (c) proposed method.



                           TABLE VIII                                              augmentation helps the model to generalize better and improves
     CLASSIFICATION METRICS FOR VARIOUS METHODS, WHEN THE
 CLASSIFIERS ARE TRAINED USING THE DATA COLLECTED IN ONE ROOM
                                                                                   the classification accuracy.
AND TESTED AGAINST THE DATA FROM DIFFERENT SUBJECTS IN ANOTHER                        In the proposed fall detection method, the range bin having
              ROOM IN A TWOFOLD CROSS VALIDATION                                   the highest variance was chosen to be the target range bin and
                                                                                   used for further processing. In addition, a range spread of four
                                                                                   consecutive bins for the target and the average scattered signal
                                                                                   over these range bins were also examined. However, only minor
                                                                                   difference in the performance was observed.
                                                                                      When the subject falls down perpendicularly to the radar line
                                                                                   of sight, the time-frequency representation and binary image are
     The bold entities show the result of the proposed method.
                                                                                   both slightly different from falling down along the radar line of
                                                                                   sight. This results in confusion between fall and nonfall classes.
Table VIII gives classification metrics obtained in this scenario.                 This confusion can be prevented and the fall detection rate can
It is seen from this table that the proposed method generalizes                    be increased by employing multiple radar sensors [44]. Doing
well to other unseen environments and datasets.                                    so would raise the precision of fall detection by covering the
   As discussed in Section III-D, the proposed convolutional                       target from multiple directions and reducing the chance that the
neural network automatically extracts features from the radar                      target may be obscured from one of the sensors. In addition, as
returns. Visualizing the activations of the network is useful                      discussed in [45], combining range features may further improve
for understanding how different layers transform their input                       the recognition accuracy, especially when the target motion is
and reduce the size of the feature map. To understand the                          perpendicular to the radar. Integrating range information as a
automatically extracted features at each layer, feature maps                       parallel input to the proposed convolutional neural network can
(activations) of the flatten layer, the fully connected layers, and                be a direction for future research.
the output layer are depicted in Fig. 9. The convolutional layers                     So far, there is no automated system for human gait analysis
retain the shape existing in the input image. As we go deeper                      and fall risk assessment based on the radar, which is mostly due
into the layers toward the output layer, the activations become                    to the lack of publicly available datasets. Previous researchers
increasingly abstract and less visually interpretable. In that case,               have mostly collected their own data and tried to validate their
the network begins to encode higher-level concepts. Activations                    algorithms statistically. In view of this, benchmark datasets are
in the higher layers carry increasingly less information about the                 important to realize qualitative comparisons of new analysis
visual contents of the image, and increasingly more information                    algorithms and pipelines. In order to help create standard bench-
related to the class of the image. This is clearly visible in Fig. 9.              mark datasets, the dataset used in this research work will be made
The cross-entropy loss and accuracy values for the training and                    publicly available.
test sets were obtained using the proposed network. Fig. 10                           Radar-based indoor monitoring, and in particular radar-based
shows cross-entropy loss and accuracy values on the training                       fall detection, is in its infancy. There is huge potential for more
and test dataset obtained using the proposed method with and                       advanced radars and algorithms to overcome the existing chal-
without data augmentation. The gradually decreasing trend of                       lenges. Radar-based systems may carry great potential as one of
the loss seen from this figure demonstrates that the network is                    the leading technologies in the future of indoor monitoring.
successfully trained after a fixed number of epochs. The accuracy                     We are currently investigating the use of the micro-Doppler
improves with the number of epochs and finally reaches a steady                    radar to detect motion and falls through the fusion of the range-
state. It can also be seen from this figure that the use of data                   Doppler image and extracted spectrogram images, as it is known
                                                                                   that the Doppler signature and rate of change in Doppler contain

          Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:34:05 UTC from IEEE Xplore. Restrictions apply.
6850                                                                     IEEE TRANSACTIONS ON INDUSTRIAL INFORMATICS, VOL. 17, NO. 10, OCTOBER 2021




Fig. 9.     Activations of (a) flatten layer, (b)–(e) FC layers, and (f) output layer, for one sample binary image.



                                                                                    as walking, running, sitting, standing from falls is also still in its
                                                                                    infancy. This article proposed a binary classification of fall from
                                                                                    a nonfall activity. A multiactivity classifier will be built in the
                                                                                    future to distinguish not only falls from nonfalls, but to classify
                                                                                    various types of activities. However, when multiple people are
                                                                                    in the view of the radar, activity monitoring becomes very
                                                                                    difficult. Future research will focus on automatic identification
                                                                                    and tracking of multiple people and also on building systems that
                                                                                    can learn activities in time, using unsupervised learning, through
                                                                                    extended observation in time. Also, current systems require large
                                                                                    datasets for training. Recently introduced ideas such as con-
                                                                                    trastive learning could be considered for enabling learning with
                                                                                    fewer examples. Also, as systems often get trained offline and are
                                                                                    required to work in a new environment, transfer learning prefer-
                                                                                    ably in an unsupervised manner will be considered in the future.


                                                                                                                 V. CONCLUSION
                                                                                       In this article, a novel radar-based fall detection method was
                                                                                    proposed based on time-frequency analysis and deep learning
                                                                                    techniques. Data were collected in room environments without
Fig. 10. (a) Cross-entropy loss, and (b) accuracy values for the training           any constraints, including fall and nonfall activities. The radar
and test sets, with and without data augmentation, obtained using the               return data were preprocessed to determine the target range bin
proposed convolutional neural network. The results are averaged over
tenfolds corresponding to each subject in a leave-one-subject-out cross
                                                                                    and removed the effect of clutters. Time-frequency analysis was
validation.                                                                         performed by using the STFT and to obtain the spectrogram for
                                                                                    different activities. The spectrograms were further processed to
                                                                                    obtain binary images and enhanced using morphological opera-
rich information about posture, movement, and sudden changes.                       tors. The binary images were augmented using class-preserving
In addition, the Doppler rate may be identified by using two                        transformations and fed into the proposed convolutional neu-
radars which are synchronously capturing the information.                           ral network for feature extraction. The proposed network was
   Fall detection using radars is only in its gestation stage.                      devised by stacking convolutional and FC layers. Several ex-
Automatic real-time detection of falls using the radar is still                     periments were conducted to evaluate the performance of the
not a reality; distinguishing other activities of daily living such                 proposed fall detection method and to compare it with those of

          Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:34:05 UTC from IEEE Xplore. Restrictions apply.
SADREAZAMI et al.: CONTACTLESS FALL DETECTION USING TIME-FREQUENCY ANALYSIS AND CONVOLUTIONAL NEURAL NETWORKS                                                     6851



the other methods. The results showed that the proposed method                        [20] M. Otero, “Application of a continuous wave radar for human gait recog-
outperforms other methods in accuracy, precision, sensitivity,                             nition,” Signal Proc., Sensor Fusion, Target Recognit., vol. 5809, pp. 538–
                                                                                           548, 2005.
and specificity. The performance of the proposed fall detection                       [21] I. Orovic, S. Stankovic, and M. Amin, “A new approach for classification
method when the network was trained on a dataset collected from                            of human gait based on time-frequency feature representations,” Signal
a set of subjects in one room and tested on a dataset collected                            Process., vol. 91, no. 6, pp. 1448–1456, 2011.
                                                                                      [22] Y. Kim and H. Ling, “Human activity classification based on micro-
from different subjects in another room was also investigated.                             Doppler signatures using a support vector machine,” IEEE Trans. Geosci.
The higher classification metrics indicates the robustness of the                          Remote Sens., vol. 47, no. 5, pp. 1328–1337, May 2009.
proposed method.                                                                      [23] B. Y. Su, K. Ho, M. J. Rantz, and M. Skubic, “Doppler radar fall
                                                                                           activity detection using the wavelet transform,” IEEE Trans. Biomed.
                                                                                           Eng., vol. 62, no. 3, pp. 865–875, Mar. 2015.
                               REFERENCES                                             [24] Q. Wu, Y. D. Zhang, W. Tao, and M. Amin, “Radar-based fall detection
                                                                                           based on Doppler time-frequency signatures for assisted living,” IET
 [1] S. Kim, K. Hirota, T. Nozaki, and T. Murakami, “Human motion analysis                 Radar, Sonar Navigation, vol. 9, no. 2, pp. 164–172, 2015.
     and its application to walking stabilization with COG and ZMP,” IEEE             [25] J. Han, D. Zhang, G. Cheng, N. Liu, and D. Xu, “Advanced deep-learning
     Trans. Ind. Informat., vol. 14, no. 11, pp. 5178–5186, Nov. 2018.                     techniques for salient and category-specific object detection: A survey,”
 [2] A. Ozdemir and B. Barshan, “Detecting falls with wearable sensors using               IEEE Signal Process. Mag., vol. 35, no. 1, pp. 84–100, Jan. 2018.
     machine learning techniques,” Sensors, vol. 14, pp. 10691–10708, 2014.           [26] B. Jokanovic, M. Amin, and F. Ahmad, “Radar fall motion detection using
 [3] M. Forouzanfar, M. Mabrouk, S. Rajan, M. Bolic, H. R. Dajani, and                     deep learning,” in Proc. IEEE Radar Conf., 2016, pp. 1–6.
     V. Z. Groza, “Event recognition for contactless activity monitoring              [27] D. Wagner, K. Kalischewski, J. Velten, and A. Kummert, “Activity recog-
     using phase-modulated continuous wave radar,” IEEE Trans. Biomed.                     nition using inertial sensors and a 2D convolutional neural network,” in
     Eng., vol. 64, no. 2, pp. 479–491, Feb. 2017.                                         Proc. Int. Workshop Multidimensional Syst., 2017, pp. 1–6.
 [4] M. Yu, A. Rhuma, S. M. Naqvi, L. Wang, and J. Chambers, “A                       [28] Y. Lang, C. Hou, Y. Yang, D. Huang, and Y. He, “Convolutional neural
     posture recognition-based fall detection system for monitoring an el-                 network for human micro-Doppler classification,” in Proc. Eur. Microw.
     derly person in a smart home environment,” IEEE Trans. Inf. Technol.                  Conf., 2017, pp. 1–4.
     Biomed., vol. 16, no. 6, pp. 1274–1286, Nov. 2012.                               [29] Novelda’s XeThruX4M03, 2018. [Online]. Available: https://www.xethru.
 [5] A. Shahzad and K. Kim, “FallDroid: An automated smart phone based                     com/x4-radar-chip.html/
     fall detection system using multiple kernel learning,” IEEE Trans. Ind.          [30] L. Stankovic, M. Dakovic, and T. Thayaparan, Time-Frequency Signal
     Informat., vol. 15, no. 1, pp. 35–44, Jan. 2019.                                      Analysis With Applications. Norwood, MA, USA: Artech House, 2013.
 [6] C. Wang et al., “Low-power fall detector using triaxial accelerom-               [31] B. Erol, M. Francisco, A. Ravisankar, and M. Amin, “Realization of radar-
     etry and barometric pressure sensing,” IEEE Trans. Ind. Infor-                        based fall detection using spectrograms,” Compressive Sensing VII: From
     mat., vol. 12, no. 6, pp. 2302–2311, Dec. 2016.                                       Diverse Modalities Big Data Anal., vol. 10658, 2018, Art. no. 106580B.
 [7] M. G. Amin, Y. D. Zhang, F. Ahmad, and K. C. D. Ho, “Radar signal                [32] A. Gadde, M. G. Amin, Y. D. Zhang, and F. Ahmad, “Fall detection and
     processing for elderly fall detection: The future for in-home monitoring,”            classifications based on timescale radar signal characteristics, in Proc.
     IEEE Signal Process. Mag., vol. 33, no. 2, pp. 71–80, Mar. 2016.                      Radar Sensor Tech. XVIII, vol. 9077, 2014, Art. no. 907712.
 [8] WHO Global Report on Falls Prevention in Older Age, World Health                 [33] N. Dhanachandra, K. Manglem, and Y. J. Chanu, “Image segmentation
     Organization, Geneva, Switzerland, 2007.                                              using k-means clustering algorithm and subtractive clustering algorithm,”
 [9] P. Corbishley and E. Rodriguez-Villegas, “Breathing detection: Towards a              Procedia Comput. Sci., vol. 54, pp. 764–771, 2015.
     miniaturized, wearable, battery operated monitoring system,” IEEE Trans.         [34] R. C. Gonzalez and R. E. Woods, Digital Image Processing, 3rd ed.
     Biomed. Eng., vol. 55, no. 1, pp. 196–204, Jan. 2008.                                 Englewood Cliffs, NJ, USA: Prentice-Hall, 2008.
[10] V. C. Chen, D. Tahmoush, and W. J. Miceli, Radar Micro-Doppler                   [35] O. C.-Reyes, P. Scully, and K. B. Ozanyan, “Deep neural networks for
     Signatures: Processing and Applications, Radar, Sonar, Navigation and                 learning spatio-temporal features from tomography sensors,” IEEE Trans.
     Avionics. London, U.K.: Institution of Engineering and Technology,                    Ind. Electron., vol. 65, no. 1, pp. 645–653, Jan. 2018.
     2014.                                                                            [36] L. Li, K. Ota, and M. Dong, “Deep learning for smart industry: Efficient
[11] L. Hazelhoff, J. Han, and P. H. N. de-With, “Video-based fall detection               manufacture inspection system with fog computing,” IEEE Trans. Ind.
     in the home using principal component analysis,” in Proc. Int. Conf. Adv.             Informat., vol. 14, no. 10, pp. 4665–4673, Oct. 2018.
     Concepts Intell. Vis. Syst., 2008, pp. 298–309.                                  [37] G. E. Hinton, S. Osindero, and Y.-W. Teh, “A fast learning algorithm for
[12] J. D. Bryan, J. Kwon, N. Lee, and Y. Kim, “Application of ultra-wideband              deep belief nets,” Neural Comput., vol. 18, no. 7, pp. 1527–1554, 2006.
     radar for classification of human activities,” IET Radar, Sonar Naviga-          [38] D. P. Kingma and J. L. Ba, “Adam: A method for stochastic optimization,”
     tion, vol. 6, no. 3, pp. 172–179, 2012.                                               in Proc. Int. Conf. Learn. Representations, 2015, pp. 1–13.
[13] C. Ding et al., “Non-contact human motion recognition based on UWB               [39] C. Shorten and T. Khoshgoftaar, “A survey on image data augmentation
     radar,” IEEE Trans. Emerg. Sel. Topics Circuits Syst., vol. 8, no. 2, pp. 306–        for deep learning,” J. Big Data, vol. 6, no. 60, pp. 1–48, 2019.
     315, Jun. 2018.                                                                  [40] L. Liu, M. Popescu, M. Skubic, M. Rantz, T. Yardibi, and P. Cuddihy,
[14] I. Nejadgholi, H. Sadreazami, S. Rajan, and M. Bolic, “Classification of              “Automatic fall detection based on Doppler radar motion signature,” in
     Doppler radar reflections as preprocessing for breathing rate monitoring,”            Proc. Int. Conf. Pervasive Comput. Tech. Healthcare, 2011, pp. 222–225.
     IET Signal Process., vol. 13, no. 1, pp. 21–28, 2019.                            [41] C. Cortes and V. Vapnik, “Support vector machine,” Mach.
[15] H. Sadreazami, M. Bolic, and S. Rajan, “On the use of ultra-wideband                  Learn., vol. 20, no. 3, pp. 273–297, 1995.
     radar and stacked LSTM-RNN for at home fall detection,” in Proc. Life            [42] L. Raileanu and K. Stoffel, “Theoretical comparison between the Gini
     Sci. Conf., 2018, pp. 255–258.                                                        index and information gain criteria,” Annu. Math. AI, vol. 41, no. 1, pp. 77–
[16] H. Sadreazami, M. Bolic, and S. Rajan, “Fall detection using standoff                 93, 2004.
     radar-based sensing and deep convolutional neural network,” IEEE Trans.          [43] M. A. Kiasari, S. Y. Na, and J. Y. Kim, “Classification of human postures
     Circuits Syst. II, Express Briefs, vol. 67, no. 1, pp. 197–201, Jan. 2020.            using ultra-wideband radar based on neural networks,” in Proc. Int. Conf.
[17] H. Sadreazami, M. Bolic, and S. Rajan, “Residual network-based su-                    IT Convergence Secur., 2014, pp. 1–4.
     pervised learning of remotely sensed fall incidents using ultra-wideband         [44] S. Gurbuz, C. Clemente, A. Balleri, and J. Soraghan, “Micro-Doppler
     radar,” in Proc. IEEE Int. Symp. Circuits Syst., 2019, pp. 1–4.                       based in-home aided and unaided walking recognition with multiple radar
[18] S. Abdelhedi, R. Bourguiba, J. Mouine, and M. Baklouti, “Development                  and sonar systems,” IET Radar, Sonar Navigation, vol. 11, no. 1, pp. 107–
     of a two-threshold-based fall detection algorithm for elderly health moni-            115, 2017.
     toring,” in Proc. IEEE Int. Conf. Res. Challenges Inf. Sci., 2016, pp. 1–5.      [45] B. Erol and M. Amin, “Fall motion detection using combined range and
[19] S. Bjorklund, H. Petersson, and G. Hendeby, “Features for micro-Doppler               Doppler features,” in Proc. IEEE Eur. Signal Conf., 2016, pp. 2075–2080.
     based activity classification,” IET Radar, Sonar Navigation, vol. 9,
     no. 9, pp. 1181–1187, 2015.




        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:34:05 UTC from IEEE Xplore. Restrictions apply.

