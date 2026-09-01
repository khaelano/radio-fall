1328                                                                     IEEE TRANSACTIONS ON GEOSCIENCE AND REMOTE SENSING, VOL. 47, NO. 5, MAY 2009




                     Human Activity Classification Based on
                       Micro-Doppler Signatures Using a
## Support Vector Machine
                                       Youngwook Kim, Member, IEEE, and Hao Ling, Fellow, IEEE



   Abstract—The feasibility of classifying different human activi-                   [1], [9]–[22]. Doppler-based radars are excellent for detecting
ties based on micro-Doppler signatures is investigated. Measured                     movement while suppressing any stationary clutters in the
data of 12 human subjects performing seven different activities                      background. Low-cost sensors using off-the-shelf components
are collected using a Doppler radar. The seven activities include
running, walking, walking while holding a stick, crawling, boxing                    or even single-chip modules are readily available. Finally, a
while moving forward, boxing while standing in place, and sitting                    very unique and interesting aspect of Doppler returns from
still. Six features are extracted from the Doppler spectrogram. A                    humans is the appearance of “micro-Doppler” features [9], [12].
support vector machine (SVM) is then trained using the measure-                      Micro-Dopplers are generated from the non-rigid-body motions
ment features to classify the activities. A multiclass classification is             of humans and contain valuable information related to human
implemented using a decision-tree structure. Optimal parameters
for the SVM are found through a fourfold cross-validation. The                       movements. Since it was first reported in [9], a number of works
resulting classification accuracy is found to be more than 90%.                      have appeared on exploiting micro-Dopplers for human classi-
The potentials of classifying human activities over extended time                    fication. For example, van Dorp [13] estimated the parameters
duration, through wall, and at oblique angles with respect to the                    of human gait from frequency modulated continuous wave
radar are also investigated and discussed.                                           radar data. Otero [14] designed a simple classifier to recognize
  Index Terms—Human activity classification, micro-doppler,                          walking humans using a spectral analysis. In [15]–[17], micro-
support vector machine, through-wall.                                                Doppler features of radar target returns were extracted through
                                                                                     various time-frequency analyses. Micro-Doppler features were
                            I. I NTRODUCTION                                         explored to distinguish among humans, animals, and vehicles in
                                                                                     [18]–[22]. In this paper, we pose a different research question,
D     UE TO THE increasing demand for physical security and
      surveillance, one of the emerging applications of radar
recently is the detection and tracking of people in a highly
                                                                                     namely, whether it is possible to distinguish various human
                                                                                     activities such as walking, running, crawling, etc., based on
cluttered environment [1]–[11]. For instance, it is desirable to                     the micro-Doppler features. The reliable recognition of simple
locate humans through walls and extract information on their                         human activities may be a first step toward addressing the more
activities in real time by using electromagnetic-based sensors.                      difficult yet important question of determining human intent.
The applications of through-wall human monitoring include                               Our approach is to apply a support vector machine (SVM),
disaster search-and-rescue, physical security, law enforcement,                      trained using measured micro-Doppler data, to classify activ-
and urban military operations.                                                       ities of a human. SVM is a binary classifier that constructs a
   There has been a significant amount of research for devel-                        maximal-margin hyperplane to separate data between classes
oping human detection and tracking sensors. One approach is                          [23]–[25]. It has been used extensively for many diverse clas-
the use of wide bandwidth (BW) to achieve high-resolution                            sification problems due to its superior performance over other
imaging in the down-range dimension. Several studies have                            classification methods such as the Fisher linear discrimina-
shown promising results from imaging building interiors to ul-                       tor and the Bayesian decision method. In the radar commu-
timately detecting and tracking humans in indoor environments                        nity, SVM has been applied to array signal processing [26],
as reported in [2]–[8]. Another choice is to use a Doppler radar                     [27] and radar target recognition [28], [29] problems. In this
                                                                                     paper, we consider seven different human activities such as
   Manuscript received May 12, 2008; revised September 11, 2008 and
                                                                                     running, walking, walking while holding a stick, crawling,
November 28, 2008. First published March 16, 2009; current version published         boxing while moving forward, boxing while standing in place,
April 24, 2009. This work was supported in part by the National Science              and sitting still. In order to recognize the activities, the time-
Foundation under Grant CBET-0730924 and in part by the A.D. Hutchison
Fellowship from the University of Texas at Austin.
                                                                                     varying Doppler signatures are examined using the short-time
   Y. Kim is with the Department of Electrical and Computer Engineering,             Fourier transform (STFT), and different features are extracted
California State University at Fresno, Fresno, CA 93740 USA (e-mail:                 from the spectrogram. Based on the extracted features, an
youngkim@csufresno.edu).
   H. Ling is with the Department of Electrical and Computer Engi-                   SVM is constructed to classify the seven activities. For the
neering, University of Texas at Austin, Austin, TX 78712 USA (e-mail: ling@          generation of training data, measurements on 12 human sub-
ece.utexas.edu).                                                                     jects are collected in the laboratory using a 2.4-GHz Doppler
   Color versions of one or more of the figures in this paper are available online
at http://ieeexplore.ieee.org.                                                       radar [10]. To implement a multiclass problem using the SVM,
   Digital Object Identifier 10.1109/TGRS.2009.2012849                               which is a binary classifier, a decision-tree-based structure is

                                                                  0196-2892/$25.00 © 2009 IEEE
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:27:05 UTC from IEEE Xplore. Restrictions apply.
KIM AND LING: HUMAN ACTIVITY CLASSIFICATION BASED ON MICRO-DOPPLER SIGNATURES USING AN SVM                                                                   1329




Fig. 1.   Illustration of measurements of seven different human activities.

employed. The training process and the resulting classification                                                TABLE I
                                                                                                   SEVEN HUMAN ACTIVITIES UNDER STUDY
accuracy are evaluated. The importance of each feature is
also investigated. Finally, the potentials of classifying human
activities over extended time duration, through wall, and at
oblique angles with respect to the radar are investigated and
discussed.
   This paper is organized as follows. The measurement data
collection of the different human activities is described in
Section II. Section III discusses the feature selection and extrac-
tion process from the spectrogram. In Section IV, the concept
and training results of the SVM are described. Section V ad-
dresses some additional issues of monitoring humans including
through-wall. Section VI presents the conclusion.

  II. M EASUREMENT OF D IFFERENT H UMAN A CTIVITIES
   Measured data of 12 human subjects undergoing different
activities are collected using a Doppler radar testbed [10]. The                   wide Doppler signal spread, which can be as large as 120 Hz.
radar operates at 2.4 GHz. The transmitter operates in the                         The walking motion shows similar Doppler patterns with the
continuous-wave mode. The receiver comprises a microstrip                          running case, except that the maximum Doppler shift from the
antenna connected to a commercial integrated receiver board.                       torso is lower (20 Hz) and the period of the micro-Doppler is
The antennas are installed to collect vertical polarization data.                  longer. Walking while holding a stick has a similar spectrogram
Since the human body is typically vertically elongated, the use                    with the walking case, but it has a slightly narrower micro-
of vertical polarization results in a stronger radar return. The re-               Doppler frequency spread. In the crawling motion, the torso
ceived signals are downconverted and then digitized (at 1 kHz)                     Doppler is nearly zero. In addition, the spectrogram shows that
for offline processing. The measurements are performed in an                       most of the micro-Dopplers are skewed toward the positive with
indoor environment under the line-of-sight condition. Only a                       respect to the torso Doppler. This is expected since contrary to
single human subject is tested at one time, with the subject                       the earlier motions, there is no back-swing in the crawling mo-
moving directly toward the radar. The range of the measurement                     tion. In the boxing while standing in place motion in Fig. 2(f),
is between 2 and 8 m.                                                              periodic micro-Dopplers from the arms are clearly observed.
   Data for human subjects undergoing seven different activ-                       In Fig. 2(e), the boxing while moving forward motion has a
ities are collected, such as follows: (a) running, (b) walking,                    positive torso Doppler component in addition to the micro-
(c) walking while holding a stick (using both hands), (d) crawl-                   Dopplers from the arms. In comparison to normal walking, it is
ing, (e) boxing while moving forward, (f) boxing while standing                    also clear that the micro-Doppler spread is quite wide due to the
in place, and (g) sitting still (with slight fidgeting movements).                 rapid punching motion. The sitting still has almost a zero torso
An illustration of the performed activities is shown in Fig. 1.                    frequency and shows small sporadic micro-Dopplers due to
The descriptions of each activity are given in Table I. The data                   fidgeting motions. These characteristics of Doppler signatures
are collected over a 6-s interval. The STFT is then applied to                     will be extracted in the next section.
the data to generate the corresponding spectrogram. A 0.25-s
Kaiser window is used in the STFT. The resulting spectrograms                                III. F EATURE E XTRACTION AND T RAINING
of the seven activities from one particular subject are shown                                            D ATA G ENERATION
in Fig. 2.
                                                                                   A. Doppler Signal Detection and Feature Extraction
   As shown in Fig. 2, the spectrograms show rather interesting
and distinct signatures depending on the activity. The strongest                      In order to extract distinct Doppler features from a spectro-
return in each spectrogram comes from that of the torso, while                     gram, it is necessary to distinguish the Doppler signal from
the periodic micro-Doppler modulations surrounding the torso                       noise. A key issue is the determination of a noise threshold.
return come from arm and leg movements. Among all the ac-                          A histogram of the signal strength of the noise (i.e., received
tivities, the running motion has the highest Doppler frequency                     signal with no target present) is shown in Fig. 3(a). In the figure,
due to the torso, which can be as high as 30 Hz. It also has a                     the noise is found to have a Gaussian-like distribution. Fig. 3(b)
          Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:27:05 UTC from IEEE Xplore. Restrictions apply.
1330                                                                  IEEE TRANSACTIONS ON GEOSCIENCE AND REMOTE SENSING, VOL. 47, NO. 5, MAY 2009




Fig. 2. Spectrograms of seven human activities. (a) Running. (b) Walking. (c) Walking while holding a stick. (d) Crawling. (e) Boxing while moving forward.
(f) Boxing while standing in place. (g) Sitting with slight movements.

shows a histogram when the human Doppler signal is present.                      work in more complex environments containing interference,
Thus, the lowest power level at which the signal histogram                       through-wall, or multipath effects.
starts to deviate from the Gaussian-like noise distribution can                     Next, different Doppler features are extracted from the de-
be used as the noise threshold, which, reading from the figure, is               noised spectrogram. The spectrogram itself can be used as
−83 dBm. By using this threshold, the spectrogram of a repre-                    input to a classifier without any processing to identify different
sentative activity (boxing while standing in place) is processed                 activities. However, such high-dimensional data would result
and shown in Fig. 4. We note here that while this approach                       in a classifier with a very complex inner structure and, thus,
works well in the present line-of-sight situation, it may not                    an enormous training process. The proper choice of features
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:27:05 UTC from IEEE Xplore. Restrictions apply.
KIM AND LING: HUMAN ACTIVITY CLASSIFICATION BASED ON MICRO-DOPPLER SIGNATURES USING AN SVM                                                                   1331




Fig. 3.   (a) Histogram of the noise. (b) Histogram of the target return and noise.




Fig. 4.   Spectrogram of the boxing while standing in place motion. (a) Before the processing. (b) After thresholding.

                                                                                      or legs. The offset of the total Doppler signal (3) is a measure
                                                                                      of the asymmetry between the forward and backward motions
                                                                                      of the limbs. This offset would be the same as the torso speed
                                                                                      if the forward and backward swings are exactly symmetrical
                                                                                      when the limbs move back and forth. The BW without micro-
                                                                                      Dopplers (4) represents the Doppler BW of the torso alone. It
                                                                                      accounts for the bobbing motion of the torso while the human
                                                                                      performs an activity. The normalized STD of the Doppler signal
                                                                                      strength (5) is related to the dynamic range of the motion. For
                                                                                      example, a large motion like running tends to have a high STD
                                                                                      in the Doppler signal strength, while sitting still has a small
Fig. 5.   Selected features of the Doppler spectrogram.                               value. We normalize the STD value by the mean of the Doppler
                                                                                      signal strength to eliminate the effect of distance between the
can reduce data dimensions while maintaining the essential                            human subject and the radar. The period of the limb motion (6)
characteristics of the micro-Doppler signatures. Based on the                         corresponds to the swing rate of the arms and legs.
initial observations in Section II, we choose the following six                          A Matlab routine is written to extract these six features
features to characterize the micro-Doppler signatures: (1) the                        automatically by processing data over a 3-s time window. The
torso Doppler frequency, (2) the total BW of the Doppler signal,                      torso Doppler frequency (1) is the average frequency of the
(3) the offset of the total Doppler, (4) the BW without micro-                        peak signal in strength over the time bins within the window.
Dopplers, (5) the normalized standard deviation (STD) of the                          For the calculation of features (2), (3), (4), and (6), two signal
Doppler signal strength, and (6) the period of the limb motion.                       envelopes are first identified. The highest Doppler frequency at
An illustration of the features is shown in Fig. 5.                                   each time bin makes up a high-frequency envelope. The lowest
   The torso Doppler frequency (1) corresponds to the speed of                        Doppler frequency at each time bin makes up a low-frequency
the human subject. The human torso speed is a very basic yet                          envelope. The BW (2) is the averaged difference between
important piece of information since there is a large variation                       the largest frequencies from the high-frequency envelope and
in the torso speed depending on the different activities. The                         the smallest frequencies from the low-frequency envelope. The
total BW of the Doppler signal (2) is related to the speed of                         offset of the Doppler frequency (3) is the mean value between
the limb motions. A large BW results from fast swings of arms                         the largest frequencies of the high-frequency envelope and the
          Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:27:05 UTC from IEEE Xplore. Restrictions apply.
1332                                                                    IEEE TRANSACTIONS ON GEOSCIENCE AND REMOTE SENSING, VOL. 47, NO. 5, MAY 2009



                                                                       TABLE II
                                                              MEAN VALUES OF THE SIX FEATURES




Fig. 6. Training and validation data set for the fourfold validation. (a) First scenario. (b) Second scenario.

smallest frequencies of the low-frequency envelope. The BW                              IV. H UMAN A CTIVITY C LASSIFICATION U SING SVM
without micro-Dopplers (4) is the averaged difference between
                                                                                       An SVM is applied to classify the seven human activities
the smallest frequencies from the high-frequency envelope
                                                                                    based on the features extracted from the Doppler spectrogram.
and the largest frequencies from the low-frequency envelope.
                                                                                    SVM is a binary classifier developed for non-linear boundary
Feature (5) is the STD of the signal strength divided by the
                                                                                    problems [23]–[25]. It is a supervised learning method that is
average of the signal strength of all the above-noise Doppler
                                                                                    based on a kernel technique. The original optimal hyperplane
signals in the spectrogram. The period (6) is the time period of
                                                                                    algorithm is limited to a linear classification problem. However,
the micro-Doppler from the limbs.
                                                                                    SVM is developed to create a nonlinear class boundary by
                                                                                    applying the kernel technique to achieve the maximum margin
B. Training Feature Set Generation
                                                                                    between classes. Through the kernel technique, the input data
   A classifier implemented using a machine learning technique                      are transformed to a high-dimensional space. In the transformed
requires a training data set. In this paper, the data set is                        feature space, the data may be classified by a linear hyperplane.
constructed by extracting the features from the measured data,                      The linear optimal hyperplane results in a nonlinear boundary
which consists of 12 human subjects performing seven activ-                         in the original input space. Because the classification accuracy
ities. Each human subject repeats a particular activity for 6 s                     depends on the kernel used, the selection of kernel is very
four different times. Then, we use a 3-s time window to extract                     critical in practice.
three different realizations of the features per measurement.                          We utilize LibSVM, a freely available SVM library im-
Thus, 12 realizations of each activity from a particular person                     plemented by Chang and Lin [30]. For the given penalty
are formed. The total number of feature sets is (12 subjects) ×                     parameter and the kernel parameter, LibSVM constructs the
(7 activities) × (12 realizations) = 1008. The mean values of                       decision boundary based on the training data and then
each feature from all 12 subjects are shown in Table II. It can                     calculates the classification error for the validation data. In
be seen that the mean values show clear differences among                           our case, three quarters of the data collected are used for the
activities, making classification potentially possible. However,                    training data set, and the remaining one quarter is used as the
by also examining the histograms (not shown here), we find that                     validation set.
the distributions show considerable overlap with one another.                          For the training procedure, two scenarios are used as shown
This means that it is not an easy task to construct a classifier                    in Fig. 6. The first scenario uses all the data from nine subjects
to distinguish the activities, and a more sophisticated classifier                  for training and the data from the remaining three subjects for
like the SVM is therefore needed.                                                   validation. The second scenario uses nine realizations of all
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:27:05 UTC from IEEE Xplore. Restrictions apply.
KIM AND LING: HUMAN ACTIVITY CLASSIFICATION BASED ON MICRO-DOPPLER SIGNATURES USING AN SVM                                                                   1333




                                                                                   Fig. 8. Suggested decision tree using SVM.



                                                                                   We note that this structure is constructed heuristically so that it
                                                                                   may not be optimal.
                                                                                      We use the Gaussian kernel for the construction of the SVMs.
                                                                                   For successful learning, the penalty parameter of the SVM and
                                                                                   the Gaussian kernel width should be carefully determined. The
                                                                                   optimal values are searched exhaustively to have the minimum
                                                                                   average classification error over the fourfold cross-validation
Fig. 7.   Process of fourfold validation.
                                                                                   for each SVM.
                                                                                      For the first scenario, the average and the variance of the
12 subjects as the training set, and the remaining three re-                       validation error of classification are 0.081 and 0.007, respec-
alizations of all the subjects as the validation set. The first                    tively. For the second scenario, the average and the variance
scenario is more realistic because it classifies the activities of                 of the validation error of classification are 0.072 and 0.010.
unknown humans based on the data from known subjects. The                          The second scenario has slightly smaller validation error, or
second scenario classifies a person’s activity based on training                   better accuracy (92.8% versus 91.9%), as compared to that
data that include that individual. The final classification error is               of the first case. This is expected since the second scenario
calculated using a fourfold cross-validation. In the validation,                   classifies a person’s activity based on training data that include
the error is calculated four times with different combinations                     that individual. It is also worth noting that the performance
of training and validation data set for the given total data set.                  of the SVM is better than that of an artificial neural network
This process generalizes the performance of the SVM and is                         classifier [33], which achieved a classification accuracy in the
summarized in Fig. 7. Successful training should result in both                    mid-80% range.
small average error and small error variance.                                         The resulting averaged confusion matrices are shown in
   The formulation of the SVM is based on the two-class                            Table III. The boxing while moving forward (e) has the highest
problem. In order to apply an SVM to the multiclass problem                        classification error in the first scenario, but it has a very small
like the one at hand, it should be reformulated into several                       error in the second scenario. We believe that this is caused by
binary class problems. Different methods have been developed                       the large deviations in how each subject performs this activity.
to handle such multiclass problems using SVMs [31], [32].                          Thus, predicting an unknown person’s activity results in a
In this paper, we apply SVMs to a decision-tree classifier.                        high error. We also observe that the walking while holding
The decision-tree method breaks multiple classes into several                      a stick (c) activity is easily confused with the walking (b)
distinct binary decision problems using a tree structure. At each                  activity in both scenarios. This shows that such a fine motion
nonleaf node of the structure, a binary SVM classifier is used.                    difference is harder to detect. In particular, at 2.4 GHz, the
A decision-tree-based SVM is selected because it is simple and                     Doppler resolution is poor and the arm micro-Doppler is very
intuitive. Furthermore, it requires the least number of SVMs to                    much buried inside the micro-Doppler from the leg motions.
be trained and has the shortest training and testing time. The                     The only distinction between the two activities appears to
configuration of the suggested decision tree is shown in Fig. 8.                   be the slightly smaller average values of all six features in
Six different SVMs should be constructed. Each SVM uses a                          activity (c) in comparison to activity (b), as shown earlier
different amount of training data. For example, the training data                  in Table II.
set for SVM1 consists of activities (a), (b), (c), (d), (e), (f),                     The SVM classification of activities using the Doppler fea-
and (g). That of SVM3 is from only activities (b) and (c).                         tures results in a low validation error. However, it is instructive
   In our decision-tree structure, SVM1 is used at the top node                    to investigate which features are more important in the classi-
to separate all activities into two groups: a group with high torso                fication. First, we carry out the classification process using one
speed and a group with low torso speed. Among the group with                       single feature at a time. The fourfold validation error trained
high torso speed, the running activity (a) is separated from other                 with only a given feature is shown in Table IV. From the table,
two through SVM2, while SVM3 is used to classify between                           the orders of features in terms of classification performance are
activities (b) and (c). SVM4, SVM5, and SVM6 are used to                           as follows: the torso frequency (feature 1), the BW without
divide the group with low torso speed into specific activities.                    micro-Dopplers (4), the total BW (2), the offset of the total
          Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:27:05 UTC from IEEE Xplore. Restrictions apply.
1334                                                                  IEEE TRANSACTIONS ON GEOSCIENCE AND REMOTE SENSING, VOL. 47, NO. 5, MAY 2009



                                                                   TABLE III
                  RESULTS OF THE SVM BASED ON A DECISION-TREE STRUCTURE. (a) CONFUSION MATRIX FOR THE FIRST SCENARIO.
                  (b) CONFUSION MATRIX FOR THE SECOND SCENARIO. Es REPRESENTS THE ESTIMATED CLASS, AND Ac REPRESENTS
                    THE A CTUAL C LASS . T HE N UMBER R EPRESENTS THE P ERCENTAGE OF C ORRECT C LASSIFICATION IN E ACH C ASE




                                                                    TABLE IV
                                               CLASSIFICATION ERROR ONLY WITH A PARTICULAR FEATURE




Fig. 9. Accuracy of the SVM classification with an increasing number of input
features.

Doppler (3), the normalized STD (5), and the period (6). The
torso frequency alone can achieve a 70% performance, while
the classification accuracies from the normalized STD of signal
strengths and the period are only around 30%.
   Next, we evaluate the combined effect of these features by
adding the features one at a time based on the orders determined
earlier. Note that since the features can interact in a complex
way in the classification process, it is not easy to predict the
exact effect of combining features. The classification accuracy
as more features are added sequentially is shown in Fig. 9.
As expected, more features result in a higher accuracy overall.
However, the last two features, namely, the normalized STD
of signal strengths and the period, only improve the result very                 Fig. 10. Spectrograms of a sequence of activities and their classification
                                                                                 results. (a) Crawling, boxing while standing in place, followed by walking.
marginally. Therefore, good accuracy can be achieved with only                   (b) Walking, boxing while standing in place, boxing while moving forward,
the four most important features.                                                followed by walking while holding a stick.
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:27:05 UTC from IEEE Xplore. Restrictions apply.
KIM AND LING: HUMAN ACTIVITY CLASSIFICATION BASED ON MICRO-DOPPLER SIGNATURES USING AN SVM                                                                 1335




Fig. 11. (a) Trajectory of the oblique angle (30◦ ) case. (b) Measured spectrogram for the walking motion.




Fig. 12. (a) Histogram of noise in case of line of sight. (b) Histogram of the through-wall case.


                V. A DDITIONAL I NVESTIGATIONS                                     correctly except for the transition from boxing while standing in
                                                                                   place to walking. The misclassification region is shaded in the
A. Classification of a Sequence of Activities
                                                                                   figure. In the transition, the activity is classified as boxing while
   In practice, human behaviors may consist of a sequence                          moving forward (e). Because the features are averaged values in
of activities when observed over an extended time period,                          the 3-s time window, the classification can be erroneous when
transitioning from one activity to another. It would be useful                     the activity changes during the time window. However, the
to investigate whether it is possible to reliably classify human                   misclassified result of boxing while moving forward (e) is not
activities on a continuous basis. If so, then it may be possible to                unreasonable as it can be regarded as a combination of boxing
determine higher order human intent through the classification                     while standing in place (f) and walking (b). The second case
of a series of simple activities discussed previously. With the                    has two intervals where misclassifications occur. The transition
SVM classifier, we have developed, for single-event activities,                    from walking (b) to boxing while standing in place (f) is again
one question that is how it will perform during the transition                     misclassified as boxing while moving forward (e) by the SVM.
between activities. Measurement data from a person undergoing                      The transition from boxing moving forward (e) to walking
a sequence of activities over a longer time duration are collected                 while holding a stick (c) is classified as sitting still (g). Since
and tested using the constructed SVM. A 3-s time window is                         these transitional motions are not included in the training data,
first applied to the data and input to the classifier. The window is               the results for these intervals can be interpreted as examples of
then slid forward by 0.5 s at a time, and the process is repeated                  how our classifier performs under an unknown activity. With its
onward. Two cases are considered for the sequential activities.                    structure, the classifier simply forces a decision based on the
The first case comprises crawling motion (d), followed by                          match in the extracted features.
boxing while standing in place (f), followed by walking (b).
The second case comprises walking (b), boxing while standing
                                                                                   B. Oblique Angle Case
in place (f), and boxing while moving forward (e), followed
by walking while holding a stick (c). Fig. 10(a) and (b) shows                        In the collected data, the human subject always moves di-
the measured spectrograms and the classification results for the                   rectly toward the radar. This will not, in general, be true in
two cases. The SVM predicts the activities of the first case                       a more realistic situation. To assess the effect of the oblique
        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:27:05 UTC from IEEE Xplore. Restrictions apply.
1336                                                                  IEEE TRANSACTIONS ON GEOSCIENCE AND REMOTE SENSING, VOL. 47, NO. 5, MAY 2009




Fig. 13. (a) Through-wall measurement of the walking activity. (b) Through-wall measurement of the crawling activity.

angle case, the seven activities of a particular human subject                   is still troublesome for our current feature extractor. While this
are measured when the subject approaches to the radar while                      through-wall result is somewhat pessimistic, we believe that
maintaining a 30◦ angle with respect to the radial direction. The                the main bottleneck is in our radar hardware. With a pulsed
measurement setup and the path are shown in Fig. 11(a). Note                     waveform and more sophisticated timing to avoid transmitter
that to maintain a fixed 30◦ angle with respect to the radial                    jamming, a significant improvement in the SNR may be pos-
direction, the chosen path is not straight. The subject repeats                  sible. Other than the SNR issue, our recent study has shown
the seven activities four times. Features from 12 realizations                   that the wall effect on the Doppler frequency is actually quite
are extracted in the same manner as before for each activity.                    negligible [30].
The previously trained SVM based on the head-on data under
the second scenario is then used to classify the newly measured                                              VI. C ONCLUSION
data. The result shows almost the same classification perfor-
mance. The classification accuracy was 91.4% (versus 92.8%).                        In this paper, we investigated the feasibility of classifying
It is believed that the accuracy is not significantly deteriorated               different human activities based on micro-Doppler signatures.
because the effect of the oblique-angle case is just a scaling of                Measured data of 12 human subjects performing seven different
the Doppler information and the amount is not large when the                     activities were collected using a Doppler radar. Six features
angle is not too large. Fig. 11(b) shows a spectrogram from the                  were extracted from the Doppler spectrogram. An SVM was
walking case. Very little difference exists between this figure                  then trained using the measurement features to classify the
and the head-on walking data shown in Fig. 2(b).                                 activities. The multiclass classification was implemented using
                                                                                 a decision-tree structure. The classification accuracy based on
                                                                                 the six features was found to be above 90%.
C. Through-Wall Measurements
                                                                                    While the results shown in the this paper are promising, we
   In-situ through-wall measurements are also performed to see                   also briefly investigated the possibility of classifying human
how the micro-Doppler features are affected by wall. The test is                 activities over an extended time duration, at oblique angles
carried out on an exterior building wall, which is a 40-cm-thick                 with respect to the radar, and through a wall. Among the three
brick wall. The radar is placed in the interior of the building                  issues, through-wall human classification remains the most
0.1 m behind the wall, and a human subject carries out the                       challenging problem. The low SNR in our measurements made
activities on the other side of wall outside the building. The                   the use of micro-Doppler signatures very difficult. Improved
signal experiences approximately a 25-dB two-way attenuation                     hardware is needed to overcome the transmitter jamming issue.
due to the wall. Moreover, the noise level is increased by 11 dB                 Additional studies of the wall phenomenology are also needed
due to the reflection of the incident signal from the wall. Thus,                to understand the effect of different walls on the micro-Doppler
the signal-to-noise ratio (SNR) suffers a 36-dB reduction. The                   features.
histograms of noise signal strength for the line of sight and                       We found that a 30◦ oblique approach angle with respect to
through-wall cases are shown in Fig. 12. It would be much more                   the radar did not significantly impact the classification results.
difficult to detect the target from noise due to the reduced SNR.                However, more severe degradation may occur at larger angles.
   Fig. 13 shows the spectrograms of the walking and the                         It may be necessary to consider distributed Doppler sensors to
crawling activity measured in the through-wall environment. A                    classify the activities of human moving in any direction.
60-Hz ac line can now be seen due to the much lower signal                          Finally, the classification of a sequence of human activities
level. The human subject approaches the radar as time pro-                       when observed over an extended period of time was investi-
gresses. While the torso return can still be seen, it is now much                gated. By using a moving window approach, we were able to
more difficult to identify the micro-Dopplers when the human                     use the developed classifier to successfully classify activities
subject is far from the radar (more than 4 m). When the human                    on a continuous basis. This approach may be a good first step
is within 4 m from the wall, the micro-Doppler signatures of                     toward determining the intent of a human by a sequence of basic
each activity can be better observed, although the limited SNR                   activities.
       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:27:05 UTC from IEEE Xplore. Restrictions apply.
KIM AND LING: HUMAN ACTIVITY CLASSIFICATION BASED ON MICRO-DOPPLER SIGNATURES USING AN SVM                                                                      1337



                               R EFERENCES                                          [28] Q. Zhao and J. C. Principe, “Support vector machine for SAR automatic
                                                                                         target recognition,” IEEE Trans. Aerosp. Electron. Syst., vol. 37, no. 2,
 [1] L. M. Frazier, “Motion detector radar for law enforcement,” IEEE                    pp. 643–654, Apr. 2001.
     Potentials, vol. 16, no. 5, pp. 23–26, Jan. 1998.                              [29] B. Krishnapuram, J. Sichina, and L. Carin, “Physics-based detection of
 [2] S. Nag, M. A. Barnes, T. Payment, and G. Holladay, “Ultrawide-                      targets in SAR imagery using support vector machines,” IEEE Sensors J.,
     band through-wall radar for detecting the motion of people in real time,”           vol. 3, no. 2, pp. 147–157, Apr. 2003.
     in Proc. SPIE Radar Sensor Technol. Data Vis., Jul. 2002, vol. 4744,           [30] C. Chang and C. Lin, LIBSVM: A Library for Support Vector Machines,
     pp. 48–57.                                                                          2001. [Online]. Available: http://www.csie.ntu.edu.tw/~cjlin/libsvm
 [3] G. Franceschetti, J. Tatoian, D. Giri, and G. Gibbs, “Timed arrays and their   [31] T. Fumitake and A. Shigeo, “Decision-tree-based multi-class support
     application to impulse SAR for through-the-wall imaging,” in Proc. IEEE             vector machines,” in Proc. IEEE ICONIP, 2002, vol. 3, pp. 1418–1422.
     Antennas Propag. Soc. Int. Symp. Dig., Jun. 2004, vol. 3, pp. 3067–3070.       [32] C. Hsu and C. Lin, “A comparison of methods for multiclass support
 [4] A. R. Hunt, “A wideband imaging radar for through-the-wall surveil-                 vector machines,” IEEE Trans. Neural Netw., vol. 13, no. 2, pp. 415–425,
     lance,” in Proc. SPIE Sensors, Command, Control, Commun., Intell. (C3I)             Mar. 2002.
     Technol., Sep. 2004, vol. 5403, pp. 590–596.                                   [33] Y. Kim and H. Ling, “Human activity classification based on micro-
 [5] L. Song, C. Yu, and Q. Liu, “Through-wall imaging (TWI) by radar:                   Doppler signatures using an artificial neural network,” in Proc. IEEE
     2-D tomographic results and analyses,” IEEE Trans. Geosci. Remote                   Antennas Propag. Soc. Int. Symp. Dig., San Diego, CA, Jul. 2008, pp. 1–4.
     Sens., vol. 43, no. 12, pp. 2793–2798, Dec. 2005.                              [34] Y. Kim, “Through-wall human monitoring using data-driven models with
 [6] Y. Yang and A. E. Fathy, “See-through-wall imaging using ultra-wideband             Doppler information,” Ph.D. dissertation, Univ. Texas, Austin, Austin,
     short-pulse radar system,” in Proc. IEEE Antennas Propag. Soc. Int.                 TX, May 2008.
     Symp. Dig., Jul. 2005, vol. 3B, pp. 334–337.
 [7] R. Solimene, R. Soldovieri, and G. Prisco, “A multiarray tomographic
     approach for through-wall imaging,” IEEE Trans. Geosci. Remote Sens.,
     vol. 46, no. 4, pp. 1192–1199, Apr. 2008.
 [8] M. Dehmollaian and K. Sarabandi, “Refocusing through building walls                                      Youngwook Kim (S’02–M’09) received the B.S.
     using synthetic aperture radar,” IEEE Trans. Geosci. Remote Sens.,                                       degree in electrical engineering from Seoul National
     vol. 46, no. 6, pp. 1589–1599, Jun. 2008.                                                                University, Seoul, Korea, in 2003, and the M.S. and
 [9] J. L. Geisheimer, E. F. Greneker, and W. S. Marshall, “High-resolution                                   Ph.D. degrees in electrical and computer engineering
     Doppler model of the human gait,” in Proc. SPIE Radar Sensor Technol.                                    from the University of Texas, Austin, in 2005 and
     Data Vis., Jul. 2002, vol. 4744, pp. 8–18.                                                               2008, respectively.
[10] A. Lin and H. Ling, “A Doppler and direction-of-arrival (DDOA) radar                                        He is currently an Assistant Professor with the
     for multiple-mover sensing based on a two-element array,” IEEE Trans.                                    Department of Electrical and Computer Engineer-
     Aerosp. Electron. Syst., vol. 43, no. 4, pp. 1496–1509, Oct. 2007.                                       ing, California State University, Fresno. His primary
[11] P. Setlur, M. Amin, F. Ahmad, and T. Thayaparan, “Indoor imaging of                                      topic of research lies in radar signal processing
     targets enduring simple harmonic motion using Doppler radars,” in Proc.                                  for through-wall human monitoring using machine-
     IEEE Int. Symp. Signal Process. Inf. Technol., Dec. 2005, pp. 141–146.         learning techniques. Other topics of interest include wireless power transfer,
[12] V. C. Chen and H. Ling, Time Frequency Transforms for Radar Imaging            development of fast algorithms for broadband antenna design, and equivalent-
     and Signal Analysis. Boston, MA: Artech House, 2002.                           circuit modeling of broadband antennas.
[13] P. van Dorp and F. C. A. Groen, “Human walking estimation with radar,”
     Proc. Inst. Elect. Eng.—Radar, Sonar Navig., vol. 150, no. 5, pp. 356–365,
     Oct. 2003.
[14] M. Otero, “Application of a continuous wave radar for human gait recog-                                    Hao Ling (S’83–M’86–SM’92–F’99) received the
     nition,” in Proc. SPIE Signal Process., Sensor Fusion, Target Recog.,                                      B.S. degree in electrical engineering and physics
     May 2005, vol. 5809, pp. 538–548.                                                                          from the Massachusetts Institute of Technology,
[15] J. Li and H. Ling, “ISAR feature extraction from non-rigid body                                            Cambridge, in 1982, and the M.S. and Ph.D. de-
     targets using adaptive chirplet signal representation,” Proc. Inst. Elect.                                 grees in electrical engineering from the University
     Eng.—Radar, Sonar Navig., vol. 150, pp. 284–291, Aug. 2003.                                                of Illinois at Urbana-Champaign, in 1983 and 1986,
[16] T. Thayaparan, S. Abrol, E. Riseborough, L. Stankovic, D. Lamothe, and                                     respectively.
     G. Duff, “Analysis of radar micro-Doppler signatures from experimental                                        Since September 1986, he has been with the
     helicopter and human data,” IET Radar, Sonar Navig., vol. 1, no. 4,                                        faculty at the University of Texas, Austin, where
     pp. 289–299, Aug. 2007.                                                                                    he is currently a Professor of electrical and com-
[17] P. Setlur, M. Amin, and F. Ahmad, “Urban target classifications using                                      puter engineering and a holder of the L. B. Meader
     time-frequency micro-Doppler signatures,” in Proc. 9th Int. Symp. Signal
                                                                                    Professorship in Engineering. His principal areas of research are in radar
     Process. Appl., Feb. 2007, pp. 1–4.
                                                                                    signature prediction and radar feature extraction. He has actively contributed
[18] A. G. Stove and S. R. Sykes, “A Doppler-based automatic target classifier
                                                                                    to the development and validation of numerical and asymptotic methods for
     for a battlefield surveillance radar,” in Proc. IEEE Radar Conf., Oct. 2002,
                                                                                    characterizing the radar signatures from complex targets. In 1986, he and
     pp. 419–423.
[19] I. Bilik, J. Tabrikian, and A. Cohen, “GMM-based target classification for     his collaborators pioneered the shooting and bouncing ray (SBR) technique
     ground surveillance Doppler radar,” IEEE Trans. Aerosp. Electron. Syst.,       for predicting the radar returns from realistic aerospace vehicles. He was a
     vol. 42, no. 1, pp. 267–278, Jan. 2006.                                        Codeveloper of the SBR-based code Xpatch, which has been distributed to over
[20] G. E. Smith, K. Woodbridge, and C. J. Baker, “Template based micro-            450 government and industrial organizations in the U.S. Xpatch was an en-
     Doppler signature classification,” in Proc. Eur. Radar Conf., Sep. 2006,       abling technology in several radar target identification programs, including the
     pp. 158–161.                                                                   U.S. Air Force Non-Cooperative Target Identification Program and DARPA’s
[21] M. Anderson and R. Rogers, “Micro-Doppler analysis of multiple fre-            Moving and Stationary Target Acquisition and Recognition Program. His recent
     quency continuous wave radar signatures,” in Proc. SPIE Radar Sensor           research interests also include radar signal processing, radar sensing of humans,
     Technol., May 2007, vol. 6547, p. 654 70A.                                     miniaturized and broadband antenna design, and propagation channel modeling
[22] G. E. Smith, K. Woodbridge, and C. J. Baker, “Naïve Bayesian radar micro-      in non-line-of-sight environments. His research activities have been funded
     Doppler recognition,” in Proc. Int. Conf. Radar, Sep. 2008, pp. 111–116.       by NSF, ONR, AFRL, AFOSR, DARPA, and NASA, as well as aerospace
[23] V. Vapnik, Statistical Learning Theory. New York: Wiley, 1998.                 companies including Lockheed, Boeing, and Northrop. He has published
[24] N. Cristianini and J. Shawe-Taylor, An Introduction to Support Vector          160 journal papers and 180 conference papers to date and coauthored a book
     Machines and Other Kernel-based Learning Methods. Cambridge,                   on radar imaging (Artech House, 2002). He was a Guest Editor of a 2003
     U.K.: Cambridge Univ. Press, 2000.                                             Special Issue on Time-Frequency Analysis for Synthetic Aperture Radar and
[25] T. Hastie, R. Tibshirani, and J. Friedman, The Elements of Statistical         Feature Extraction for the IEE Proceedings on Radar, Sonar and Navigation.
     Learning. New York: Springer-Verlag, 2001.                                     He has served on a number of U.S. and NATO panels on high-resolution SAR
[26] M. M. Ramon, X. Nan, and C. G. Christodoulou, “Beamforming using               and ISAR imaging, including the NATO Sensors and Electronics Technology
     support vector machines,” IEEE Antennas Wireless Propag. Lett., vol. 4,        Panel and the Naval International Cooperative Opportunities in Science and
     no. 1, pp. 439–442, 2005.                                                      Technology program.
[27] M. M. Ramon, J. L. Rojo-Alvarez, G. Camps-Valls, and C. G.                        Dr. Ling received the National Science Foundation Presidential Young
     Christodoulou, “Kernel antenna array processing,” IEEE Trans. Antennas         Investigator Award in 1987, the NASA Certificate of Appreciation in 1991, and
     Propag., vol. 55, no. 3, pp. 642–650, Mar. 2007.                               several teaching awards from the University of Texas.
        Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:27:05 UTC from IEEE Xplore. Restrictions apply.

