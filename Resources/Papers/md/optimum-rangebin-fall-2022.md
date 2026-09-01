                                                         Biomedical Signal Processing and Control 77 (2022) 103741


                                                                   Contents lists available at ScienceDirect


                                              Biomedical Signal Processing and Control
                                                          journal homepage: www.elsevier.com/locate/bspc




Optimum target range bin selection method for time-frequency analysis to
detect falls using wideband radar and a lightweight network
Mi He *, Yi Yang , Qinwen Ping , Ran Dai , Bingwen Liu , Yongjian Nian , Zhu Zhang
School of Biomedical Engineering and Imaging Medicine, Third Military Medical University (Army Medical University), Chongqing 400038, China




A R T I C L E I N F O                                     A B S T R A C T

Keywords:                                                 Objective: Wideband bio-radars have been applied to fall behaviour recognition research in the last few years. The
Fall detection                                            optimum target range bin is that the time Doppler spectrogram image of signals of the range time matrix in this
Wideband radar                                            range bin is best for the deep learning network to distinguish between falling and non-falling. Thus, selecting an
Time-frequency analysis
                                                          appropriate target range bin for time-frequency analysis is very important for effective fall detection of wideband
Lightweight network
                                                          radar.
                                                          Methods: A K-band wideband frequency modulated continuous wave radar is applied to build a fall detection
                                                          database of 36 subjects in two scenes. The radar data are pre-processed to obtain range-Doppler spectrograms
                                                          where the optimum target range bin is selected for the subsequent time-frequency analysis. The original,
                                                          threshold, and binary time Doppler spectrograms are compared using different target range bin optimum target
                                                          range bin selection methods. To determine the effectiveness of the proposed algorithm in fall recognition, a
                                                          MobileNetV3-Small architecture is implemented for fall detection by automatically extracting features and
                                                          classifying them.
                                                          Results: The proposed method distinguishes falls from non-falls with a 98.93% classification accuracy with 5-fold
                                                          cross validation, which is superior to the existing maximum variance method that is applied to the dataset using
                                                          three kinds of time Doppler spectrograms. The test results in another scene show that our proposed method is
                                                          robust enough to detect falls successfully for unseen subjects in unseen situations.
                                                          Conclusions: The proposed optimum target range bin selection method can effectively and robustly detect falls
                                                          when using wideband radar and a lightweight network.




1. Introduction                                                                               hospitalisation by 26% [4]. Therefore, if we can detect falls and notify
                                                                                              someone in a timely and accurate manner for the elderly (especially
    Due to the effect of a longer life expectancy, the process of ageing in                   empty nesters who live alone), the elderly can be provided with fast and
the global population has accelerated. The World Health Organization                          effective assistance to minimise the negative impact of falls
(WHO) projected that by 2050, nearly 17 percent of the world’s popu­                              In the last few years, radar has been applied to research on human
lation (1.6 billion) will be elderly (age 65 and above) [1]. According to a                   behaviour recognition [5], especially for fall recognition [6,7] because
WHO report, the probability of falling is approximately 28%–35% for                           its performance is unaffected by changes in light, sound and temperature
elderly individuals over 65 years old and 32%–42% for elderly in­                             and it has good user privacy protection. Compared with wearable de­
dividuals over 70 years old [2]. Falling is the main cause of death due to                    vices, such as inertial measurement unit (IMU) sensors and environment
accidental injury for elderly individuals over 79 years old [3]. Elderly                      sensing devices, including cameras, the cost of a radar is relatively high
individuals who have experienced falls are more likely to die than those                      [8]. However, with the maturity of radar chip technology and mass
who have never fallen, with an odds ratio of 5.11 (95% confidence in­                         production of bio-radars, the cost of a radar as one of the smart home
terval: 1.84–14.17, p = 0.002) [2]. Falls seriously threaten the physical                     sensors will be further reduced and widely used. Moreover, the number
and mental health of the elderly and even cause death, placing a greater                      of subjects in the existing studies is relatively small, where most studies
burden on the family and society. Noury et al. showed that if elderly                         have two to three subjects [6], and the largest number of subjects is 20
individuals could obtain timely assistance after falling, they could                          [9], most of the experiments are carried out in a single scene or even a
effectively reduce the risk of death by 80% and the risk of long-term                         microwave anechoic chamber [10,11].


 * Corresponding author.

https://doi.org/10.1016/j.bspc.2022.103741
Received 14 September 2021; Received in revised form 13 April 2022; Accepted 27 April 2022
Available online 26 May 2022
1746-8094/© 2022 Elsevier Ltd. All rights reserved.
M. He et al.                                                                                                 Biomedical Signal Processing and Control 77 (2022) 103741


    In previous studies, continuous wave (CW) Doppler radars were
mostly implemented for fall detection. There is little or no range reso­
lution due to the narrow bandwidth of the CW Doppler radar [12]. For
this kind of radar, the signal processing methods of network front-ends
are mainly time–frequency analysis, such as short time Fourier trans­
form (STFT) and wavelet transform [10]. The time–frequency analysis
results reflect the variation law of different frequency components in the
radar echo signal with time. Next, the extracted feature indices from the
time–frequency analysis results are put into machine learning models, or
the time–frequency analysis results are directly sent into deep learning
networks to distinguish different action and behaviour types [12].
    With the development of microelectronics and chip technology,
several wideband continuous wave bio-radars have emerged in the last
decade [13,14], which have a high resolution of range and velocity at
the same time. Compared with the CW Doppler radar, wideband bio-
radars can provide more multidimensional information for human
behaviour recognition to improve recognition accuracy. Similarly, the
extracted feature indices from the multidimensional information are put
into machine learning models, or the multidimensional spectrograms
are directly sent into deep learning networks to determine whether a fall
occurred [15].
    Compared with the CW Doppler radar, the main difference in the
data processing of the wideband CW bio-radar in the network front-end
radar is the multiple range resolution cells of the range profile [14]. The
radar signal in each range bin changes with the slow time. The time
Doppler spectrograms for each range bin can be obtained after time­
–frequency analysis. As overlapping sampling is employed using a
sliding window, a time–frequency analysis needs more calculation than
a Fourier transform. Thus, it is impossible to implement time–frequency
analysis on the time sequence signal for all range bins, especially for an
online real-time processing situation. Therefore, selecting an appro­
priate target range bin for further time–frequency analysis is very
important for wideband bio-radar data processing. Hamidreza et al.
proposed the maximum variance method (MVM) [14], which was the                    Fig. 1. The framework of this paper using a wideband radar and a lightweight
range bin that had the maximum variance of the range time matrix and              network. The images of the original, threshold, and binary time Doppler
was chosen as the optimum range bin. STFT was carried out on the time             spectrograms are separately input into the deep learning network. Bneck rep­
sequence signal in a period of the optimum range bin to obtain a spec­            resents a bottleneck block with residual and squeeze-and-excite in MobileNet
trogram, which was converted into a binary image and fed into a con­              V3. Conv is the convolution operator. A fully connected layer with a softmax
volutional neural network [14]. The binary time–frequency signature of            operation outputs the prediction as a classifier.
each activity was obtained by applying the k-means clustering algorithm
to the time–frequency representations. The 5-fold cross validation in one         are separately input into the deep learning network. After resizing the
scene achieved 93.54% accuracy using data from 10 subjects [14]. The              time Doppler spectrogram images, the resized images are sent to the
accuracy decreased to 89.12% in another test scene [14]. As there may             MobileNetV3-samll described in Section 3 to automatically extract fea­
have been interferences in the range time spectrograms, which would               tures and classify falls or non-falls. Additionally, the proposed method is
lead to high variance of the range time matrix, the time Doppler spec­            compared with the MVM using the original, threshold, and binary time
trogram signature obtained from MVM and STFT may not have been                    Doppler spectrograms. To make the comparison results convincing, our
able to truly reflect the real change process of the target frequency             team establishes a large radar noncontact fall detection database with
components with time.                                                             comprehensive activity types, including 20 daily life activities and 10
    Considering that range Doppler spectrograms can better reflect the            fall activities of 36 subjects in two scenes. The database is divided into a
span of target velocity than range time spectrograms, this paper pro­             training set, verification set and test set. The subjects in the three sets are
posed an optimal target range bin selection method based on the range             different, and the scenes of the training and verification sets and the test
Doppler spectrogram. In the last decade, deep learning networks tended            set are different. To make the results comparable, all random number
to have deeper and more complicated structures to achieve higher ac­              seeds are fixed when the deep learning network operates.
curacy. However, complex networks could not be executed online due to                 The paper is organised as follows: In Section 2, the proposed opti­
the limited computing resources in many practical online applications.            mum target range bin selection method for time–frequency analysis to
Thus, some scholars have developed lightweight deep learning networks             detect falls is described in detail, including the procedures for optimum
that could be easily matched to the design requirements for mobile and            target range selection, the calculation of the range-Doppler and the time
embedded vision applications [16]. A class of efficient models called             Doppler spectrograms. In Section 3, MobileNetV3-Small, the imple­
MobileNets describes lightweight deep neural networks that efficiently            mentation of the neural network and the performance evaluation met­
trade off latency and accuracy. The latest MobileNet version, i.e.,               rics are described. The experiment and results are presented in Section 4.
MobileNetV3-samll [17], is implemented to automatically extract fea­              Finally, the conclusion is drawn in Section 5.
tures from the time Doppler spectrograms for classification. The
framework of this paper is illustrated in Fig. 1. The wideband radar
echoes are pre-processed by the optimum target range bin selection
method in Section 2 to obtain the time Doppler spectrograms. The im­
ages of the original, threshold, and binary time Doppler spectrograms

                                                                              2
M. He et al.                                                                                              Biomedical Signal Processing and Control 77 (2022) 103741


2. Optimum target range bin selection method based on the
                                                                                 dB(RT) = 20*log10 (abs(RT))                                                   (1)
range-doppler spectrogram
                                                                                     The matrix of RT after normalisation and the dB operator is defined
   Fig. 2 presents the flowchart of the proposed optimum target range            as the range time spectrogram matrix, which contains a large amount of
bin selection method based on the range-Doppler spectrogram. The                 static environment clutter. MTI is performed in the slow time direction
input is the echoes of the wideband radar. Section 2.1 describes how to          to suppress static clutter [20]. The range time spectrogram matrix after
obtain the range time matrix, the range time spectrogram matrix after            MTI is defined as RTMTI.
moving target indication (MTI) and the range-Doppler spectrogram                     Next, a Fourier transform (FT) is performed along the slow time axis
matrix. The proposed optimum target range bin selection method is                of the RTMTI in every range bin. The pink column in Fig. 3(b) indicates
explained in Section 2.2. The method of the calculation of the time              the position of the signals along the slow time axis of the RTMTI in some
Doppler spectrogram is given in Section 2.3. The output is the time              range bin for the FT. After FT in every range bin, the Nfft × M range
Doppler spectrograms. Details of each step are described below.                  Doppler matrix RD is obtained, where Nfft is the number of fast Fourier
                                                                                 transform (FFT) points and M is the number of range bins. The range
2.1. Calculation of the Range-Doppler spectrogram                                Doppler matrix RD after zero-frequency component shift (moving the
                                                                                 zero frequency components to the centre of the spectrum), normal­
    There are two main kinds of waveforms for wideband CW bio-radars:            isation and dB operator is defined as the range Doppler spectrogram
stepped frequency (SF) CW and frequency modulated (FM) CW. Using                 matrix, as seen in Fig. 4 (a). Although the static clutter is removed, the
each period of the radar echo after de-ramping [18] and range                    range Doppler spectrogram still contains system white noise or some
compression (i.e., the Fourier transform) [19], a row vector containing          strong system jitters along the frequency axis separately presented in
M range bins is obtained, as shown in Fig. 3(a). De-ramping (or mixing)          Fig. 4(a) and (b). The parts in the red circles need to be further sup­
is when the received radar echo signal is multiplied by the replica and          pressed to calculate the optimal range bin.
the conjugation of the transmitted signal, and then passed through a                 We ensure that the high-energy part of the range time matrix after
designed low pass filter, which can dramatically reduce the sampling             the MTI of the collected moving targets is roughly placed in the centre of
rate for an SFCM and FMCM radar. The output of the de-ramping or                 the data duration when intercepting data, which can be realised by
mixing process is the beat signal. Range compression applies the Fourier         programming. Then, the moving target is relatively concentrated near
transform to the beat signal to provide the different range bins, which is       the centre of the range-Doppler spectrogram, and thus, there are almost
referred to as fast time. If N period signals are processed above and ar­        no targets in the four corners of the range-Doppler spectrogram (seen in
ranged line-by-line, we can obtain an N × M range time matrix RT seen            Fig. 4).
in Fig. 3(b). The normalisation operator is that each element in matrix
RT is divided by the maximum absolute value of RT. The operator dB is
as follows:




                  Fig. 2. A flowchart of the proposed optimum target range bin selection method based on the range-Doppler spectrogram.

                                                                             3
M. He et al.                                                                                                   Biomedical Signal Processing and Control 77 (2022) 103741




Fig. 3. Range time matrix of a wideband radar: (a) one dimension range bin vector of one period. (b) Arranged multirange bin vectors of multi-periods into a range
time matrix RT.




Fig. 4. Range Doppler spectrograms: (a) Fainting while standing up from a chair; (b) Falling forward. The parts in the red circles are white noise and some strong
system jitters separately in (a) and (b).


2.2. Optimum target range bin selection                                                nonzero element numbers of the four corner matrices, denoted as
                                                                                       CNS (=Cn1 + Cn2 + Cn3 + Cn4), which reflects the system noise.
    The optimum target range bin is that in this range bin, the time                   Step 4: To suppress the strong system jitter along the frequency axis,
Doppler spectrogram image of signals of the range time matrix is best for              two strips at the top and bottom of the matrix mask are taken to
the deep learning network to distinguish between falling and non-                      calculate the noise point number, both with sizeCNfft × M, whereCNfft
falling. The proposed optimum range bin selection method based on                      ≤ b2Nfft (parameter b2 (=1/50) is adjustable based on the noise figure
the range-Doppler spectrogram is as follows.                                           of the radar system equipment). The number of nonzero elements at
                                                                                       the two strips are counted and represented as Cnup and Cndown. To
    Step 1: We calculate and denote the median value of the range-                     retain the target with a large Doppler frequency, the smaller one is
    Doppler spectrogram as a. The transformation factor is denoted by                  chosen and denoted as CNM, which can reflect the system jitter. That
    c, which is given an initial value, i.e., c = 1.                                   is, CNM = min(Cnup, Cndown).
    Step 2: To suppress the noise of the range-Doppler spectrogram, a                  Step 5: We adjust the transformation factor c according to the
    binary mask is constructed. We calculate the threshold Th = a × c. In              thresholds, CNS and CNM. We set the threshold Th1 = b3×CNfft × CM
    the range-Doppler spectrogram matrix, an element less than the                     and the threshold Th2 = b4, where parameters b3(=20) and b4(=1)
    threshold is set to 0, and an element larger than or equal to the                  can be fine-tuned according to the specific system noise. When CNS
    threshold is set to 1. The initial binary mask matrix is obtained,                 ≥ Th1 and CNM ≥ Th2, let c = c-△c update c, where △c is the step
    which is represented as Mask.                                                      size with a default value of 0.1.
    Step 3: As there are almost no targets in the four corners of the range-           Step 6: We repeat Steps 2 to 5 until CNS < Th1 and CNM < Th2 to
    Doppler spectrogram in the proposed method, the mask is modified                   acquire the final threshold Th = a × c. In the range-Doppler spec­
    according to these characteristics to suppress more noise. We count                trogram matrix, elements less than or equal to the threshold are set to
    the number of nonzero elements at the four corners of Mask to                      Th, and elements larger than the threshold remain unchanged. The
    calculate the noise point number, which are denoted as Cn1, Cn2,                   updated range-Doppler spectrogram matrix is denoted as RD’, still
    Cn3, and Cn4 without order. The size of the four corner matrices is                with the dimension Nfft × M. The system noise and the jitter in all the
    usually less than 1/50 of the size of the range-Doppler spectrogram                updated range-Doppler spectrogram matrices are suppressed well
    matrix, where a parameter b1 (=1/50) should be adjusted according                  when using the chosen parameters, which are repeatedly optimised.
    to the noise figure of the radar system equipment. The rows and the                Step 7: Because the reflection of close targets is large, if RD’ is
    columns of the range-Doppler spectrogram are Nfft and M, respec­                   summed directly along the column, the optimum range bin will
    tively. We suppose the size of the four corner matrices isCNfft CNfft ×            deviate from the truth. Therefore, partial components of RD’ with
    CM, whereCNfft ≤ b1Nfft and CM ≤ b1M. We calculate the sum of the                  large amplitude shall be limited first. We sort all the elements of RD’


                                                                                4
M. He et al.                                                                                                Biomedical Signal Processing and Control 77 (2022) 103741


    in ascending order to form a vector X. The percentile of the elements          the original time Doppler spectrogram matrix, an element less than or
    in the vector X for the percentage p in the interval [0,100] is                equal to c’a is set to c’a, and an element larger than c’a remains un­
    calculated and denoted as x. In matrix RD’, an element less than or            changed. The updated time Doppler spectrogram matrix is defined as the
    equal to × remains unchanged, and an element larger than × is set to           threshold time Doppler spectrogram. In previous studies [6,14,21], the
    x. The percentage p equal to 98 is the best choice in this study for all       threshold was usually set to a fixed number in the normalised time
    the range-Doppler spectrogram matrices.                                        Doppler spectrograms. However, for spectrograms of different activities,
    Step 8: Next, we sum up the elements of the updated RD’ along the              the fixed threshold is not rational. Thus, the median value (usually
    column (Doppler frequency axis) to obtain a row vector SRD with                approximately − 100 dB in this study) multiplied by a factor c’ is pro­
    size 1 × M. The range bin corresponding to the maximum value of                posed in this paper for the threshold time Doppler spectrogram.
    the SRD is selected as the optimum range bin.                                      Moreover, the binary time Doppler spectrogram matrix obtained by
                                                                                   applying k-mean clustering, median filtering and a morphological
    During the selection of the optimum range bin, the reason why we               opening operation [14] preserves the shape of the energy content of the
choose the range bin with the maximum value of the SRD instead of the              activity. The images of the binary time Doppler spectrogram are fed into
range bin with the largest Doppler value is that it can suppress the false         the convolutional neural network. Because the time dimension of the
components carried by the artefacts of the multipath interference of               time Doppler spectrogram matrix is large, the time Doppler spectrogram
moving targets in the environment, while considering the stable Doppler            matrix before k-mean clustering is resized to 224 × 224 to reduce the
maximum components, which contain complete and proper information                  amount of computation.
of the frequency changing activity with time.                                          Figs. 5 to 7 show the original, threshold and binary time Doppler
                                                                                   spectrograms of walking and falling, respectively, where c’ equals 0.75
2.3. Calculation of the time Doppler spectrograms                                  for the threshold time Doppler spectrograms. As these images of the
                                                                                   threshold time Doppler spectrograms look very clean and are almost
   A time–frequency analysis is performed by applying the STFT to the              noise free, c’ equals 0.75 in the following experiment. The influence of
time series of the range time matrix RT on the optimum range bin. The              the different values of parameter c’ on the classification results will be
number of frequency bins of the STFT is Nfft. A unit energy Hamming                discussed in Section 4.2. Graphs (a) and (c) in Figs. 5 to 7 are obtained
window with a length of 128 is chosen as the frequency smoothing                   using the proposed method. Graphs (b) and (d) in Figs. 5 to 7 are ac­
window of the STFT. The normalised time Doppler spectrogram is called              quired using the MVM. Compared with the spectrograms using the
the original time Doppler spectrogram.                                             MVM, the time Doppler spectrograms using the proposed method can
   We denote the median value of the time Doppler spectrogram as a                 reflect more detailed information on activities, which is beneficial for
and set a threshold of c’a, where c’ is a parameter between 0 and 1. For           recognising the next action. The patterns in the spectrograms of walk




Fig. 5. Original time Doppler spectrograms: (a) walking towards a radar using the proposed method, (b) walking towards a radar using the MVM, (c) slipping
backwards using the proposed method, (d) slipping backwards using the MVM.

                                                                               5
M. He et al.                                                                                                 Biomedical Signal Processing and Control 77 (2022) 103741




Fig. 6. Threshold time Doppler spectrograms with c’ equal to 0.75: (a) walking towards a radar using the proposed method, (b) walking towards a radar using the
MVM, (c) slipping backwards using the proposed method, (d) slipping backwards using the MVM.


and slip are different. The spectrograms of slip have larger frequency             MobileNetV3-Small can reflect the quality of the different input data.
components than the walk spectrograms. There are positive and nega­
tive frequencies in the original, threshold and the binary time Doppler            3.2. Implementation of the neural network
spectrograms. However, the time Doppler spectrograms in [14] only
present the positive frequency parts.                                                  The inputs of the MobileNetV3-Small include one of the original,
                                                                                   threshold, and binary time Doppler spectrograms. For consistency, the
3. Lightweight network                                                             original and the threshold Doppler spectrograms are both resized into
                                                                                   224 × 224 matrices. The MobileNetV3-Small is implemented to auto­
3.1. MobileNetV3-Small                                                             matically extract features from the time–frequency representation con­
                                                                                   taining the energy of activities. Fivefold cross validation and the cross-
    Since 2017, the Google team has presented a series of MobileNets               entropy cost function are employed on the training and validation
focusing on a lightweight convolutional neural network (CNN) in mobile             datasets to optimise the hyperparameters. To compare the results using
or embedded devices [16]. Compared with a traditional CNN, it can                  the three kinds of spectrograms, random number seeds for the CPU, GPU
greatly reduce the model parameters and the amount of computation on               and dataset division in the deep learning training and testing need to be
the premise of a small reduction in accuracy [16]. MobileNetV3-Small is            fixed.
one of the latest architectural designs [17] and includes 12 bottleneck                The MobileNetV3-small hyperparameters of the training dataset are
residual layers and 4 convolution layers [17]. The particular architec­            as follows: the batch size is 128, the learning rate is 0.01, the dropout
ture of the MobileNetV3-Small used in this work is listed in Table 1. The          regularisation factor is 0.8, and the momentum is 0.9. Finally, the size of
differences between the architecture used in this study and that in [17]           the optimised MobileNetV3-Small model using all of the data of the
are the input and the output size. Considering the input with only one             training and validation datasets is 1.66 Mbytes.
channel, the input size in Table 1 is 2242 × 1. The last output size in
Table 1 is 2, as there are two categories of a fall and non-fall. Moreover,
                                                                                   3.3. Performance evaluation metrics
the squeeze-and-excite is applied in the residual layer, and the hard
version of the swish function is designed as the activation function [17].
                                                                                      To evaluate the effectiveness of the trained classification model,
The specific configuration of the bottleneck residual layers in the
                                                                                   some performance evaluation metrics are applied in this study, which
MobileNetV3-Small architecture can be found in [17]. Batch normal­
                                                                                   mainly include the receiver operating characteristic curve (ROC), the
isation in a deep learning network is different from the definition of
                                                                                   area under the ROC curve (AUC), the sensitivity, the specificity, the
normalisation in Section 2.1. The well-trained architecture of the
                                                                                   accuracy, the precision and the F1-score. The formulas are as follows:

                                                                               6
M. He et al.                                                                                                      Biomedical Signal Processing and Control 77 (2022) 103741




Fig. 7. Binary time Doppler spectrograms: (a) walking towards a radar using the proposed method, (b) walking towards a radar using the MVM, (c) slipping
backwards using the proposed method, (d) slipping backwards using the MVM.


                                                                                                     TP
Table 1                                                                            Precision =                                                                         (2)
                                                                                                   TP + FP
Specifics of the MobileNetV3-Small architecture used in this work.
  Input               Operator                      Exp_size         #out                            TP
                                                                                   Sensitivity =                                                                       (3)
      2
  224 × 1             conv2d, 3 × 3                 –                16                              P
  1122 × 16           bneck, 3 × 3                  16               16
  562 × 16            bneck, 3 × 3                  72               24
                                                                                                     TN TN
                                                                                   Specificity =       =                                                               (4)
  282 × 24            bneck, 3 × 3                  88               24                              N   N
  282 × 24            bneck, 5 × 5                  96               40
  142 × 40            bneck, 5 × 5                  240              40                            TP + TN TP + TN
                                                                                   Accuracy =             =                                                            (5)
  142 × 40            bneck, 5 × 5                  240              40                             P+N     P+N
  142 × 40            bneck, 5 × 5                  120              48
  142 × 48            bneck, 5 × 5                  144              48                          2Precisionn Sensitivity
  142 × 48            bneck, 5 × 5                  288              96            F1− score =                                                                         (6)
                                                                                                 Precision + Sensitivity
  72 × 96             bneck, 5 × 5                  576              96
  72 × 96             bneck, 5 × 5                  576              96
  72 × 96             conv2d, 1 × 1                 –                576           where P and N represent the number of fall and non-fall activities,
  72 × 576            pool, 7 × 7                   –                –             respectively, TP is the true positive, FN is the false negative, TN is the
  12 × 576            conv2d, 1 × 1, NBN            –                1024          true negative, and FP is the false positive.
  12 × 1024           conv2d, 1 × 1, NBN            –                2

Abbreviations: Exp_size denotes the expansion size of channels after the           4. Experiment and results
bottleneck; #out is the output channel number; bneck represents a bottleneck
block with a residual and Squeeze-and-Excite; conv2d denotes 2-dimensional         4.1. Experiment and dataset
convolution; pool represents the average pooling; NBN is no batch
normalisation.                                                                        A K-band wideband linear frequency modulated CW radar (devel­
                                                                                   oped by WuHan RadarDoctor Electronics and Technology CO., Ltd.) is
                                                                                   employed in the experiment to collect the data. The central frequency of
                                                                                   the K-band radar is 23.8 GHz and the bandwidth is 2 GHz. The pulse
                                                                                   repetition frequency, i.e., the sampling frequency of the slow time, is


                                                                               7
M. He et al.                                                                                                      Biomedical Signal Processing and Control 77 (2022) 103741


2000 Hz. A triangular linear frequency modulated waveform is adopted                 Table 3
to maintain a stable frequency variation. The radar is mounted 2 m                   Types of activities performed by the 36 subjects.
above the floor level.                                                                Category      Motion Description
    Thirty-six subjects were recruited and approved by the ethics com­
                                                                                      Fall          Fall forward and backwards (2 kinds)
mittee of Third Military Medical University (Army Medical University)                               Faint forward and backwards (2 kinds)
with approval number AF/sc-03/1.0. The statistical physical informa­                                Accidentally slip while sitting down on a chair
tion of the enrolled subjects is listed in Table 2. As the number of sub­                           Faint while stand up from a chair
jects was small (3 < n < 50), the Shapiro–Wilk statistical test method                              Fall at ± 45◦ angles (2 kinds)
                                                                                                    Trip up the stairs
was used to test whether the variables obeyed a normal distribution. The                            Step down the stairs and trip
results show that there was no substantial difference in the physical
parameters, including height, weight and body mass index (BMI), which
                                                                                      Non-fall      Walk towards or away from a radar (2 kinds)
indicates that only age does not follow a normal distribution. Thus, the                            Walk towards and away from a radar with a pair of crutches (2 kinds)
following statistical information of the age is expressed in quartiles as                           Walk towards or away from a radar with a crutch (2 kinds)
the median (1st quartile, 3rd quartile), while the other parameters are                             Jog towards and away from a radar (2 kinds)
expressed as the mean ± standard deviation (std).                                                   Go up and down stairs (2 kinds)
                                                                                                    Bend down low to tie one shoe
    Due to ethical constraints, it is not possible to collect data on falls of
                                                                                                    Tie one shoe and stand up
the elderly in the experiment with risk. The subjects were asked to                                 Bend down low to pick up a pen
imitate the behaviour of the elderly in this experiment through 20 kinds                            Pick up a pen and stand up
of daily activities, such as walking, jogging, sitting down, lying down,                            Swivel 180◦
                                                                                                    Laying down on the bed
standing up, going up and down stairs, crawling and walking on
                                                                                                    Sit up from lying on the bed
crutches, and 10 kinds of fall activities on a sponge mat, such as falling                          Crawl on a yoga mat
when sitting down or standing up and fainting and slipping in different
directions. The description of the different activities is listed in Table 3.        ‘2 kinds’ denotes that there are two kinds of activities in one description.
We collected radar data in two real room scenes without any constraints.
Both rooms had many types of furniture, such as a bed, a short ladder, a             the MVM, as shown in Fig. 10. When the number of epochs is larger than
desk, some iron filing cabinets, some chairs, a sponge pad and a com­                15, the cross-entropy loss and accuracy values remain steady. Thus, only
puter, and the dimensions of the rooms were 6.40 m × 4.92 m × 2.46 m                 the results of 30 epochs are presented in Fig. 10. It can be seen from
and 5.6 m × 2.47 m × 2.63 m (length × width × height). Scene 1 was                   Fig. 10 that the loss using the proposed method decreases more rapidly
composed of the data of 30 subjects (shown in Fig. 8(a)), and Scene 2                and is smaller than that using the MVM when the model reaches a steady
was composed of the data of 6 subjects (shown in Fig. 8(b)). The dura­               state. Moreover, the accuracy using the proposed method increases more
tion of each data recording was at least 4 s. In the calculation of the              rapidly and is larger than that using MVM for the training and the
following spectrograms, each data segment of 4 s was intercepted. Every              validation datasets.
activity data point had a label, where 0 represented a daily life activity               Table 4 lists the classification metrics obtained using 5-fold cross-
and 1 represented a fall activity.                                                   validation for the proposed method and the MVM. The datasets are all
    To make the trained network model have better generalisability and               from Scene 1. It can be seen from this table that the proposed method
measure the real performance of the network classification at the same               outperforms the MVM using the original, threshold and binary time
time, the principle of the mutual exclusion of the samples was followed              Doppler spectrograms. The proposed method achieves 98.926% classi­
in the dataset division. The data of every subject was either in the                 fication accuracy, 99.222% specificity, and 98.388% F1-score. Table 5
training set, in the verification set, or in the test set. The whole dataset         lists the classification metrics obtained using the test dataset in Scene 2
contains 3240 samples. Data collected in Scene 1 was further divided                 for the proposed method and the MVM. Even in a new scene with unseen
into training and verification sets. Data collected in Scene 2 constituted           subjects, the proposed method achieves high classification performance
the test set.                                                                        by providing 95.370% accuracy and 97.222% specificity. Moreover, it
                                                                                     can be seen from these tables that the original and threshold time
                                                                                     Doppler spectrograms outperform the binary time Doppler spectrograms
4.2. Experimental results                                                            using the proposed method and the MVM in the two scenes. This infers
                                                                                     that the original and the threshold time Doppler spectrograms provide
   The ROC curves and the AUCs of the proposed method through 5-fold                 more information to understand the fundamental composition of human
cross validation are presented in Fig. 9, where the value of the AUC                 activities and determine whether a fall occurs during daily human
equals 1 due to the retention of three substantial digits and rounding.              activities.
Fig. 9(a)–(c) show the results using the original, threshold, and binary                 To analyse the effect of parameter c’ on the classification results, we
time Doppler spectrograms, respectively. It can be seen from these fig­              compare the testing results of Scene 2 using the original time Doppler
ures that the AUCs obtained by using the original and the threshold time             spectrograms and the threshold time Doppler spectrograms with
Doppler spectrograms are higher and have smaller standard deviations                 different parameter c’ values of 0.75, 0.8, 0.85, 0.9, and 0.95. As the
than those obtained by using the binary time Doppler spectrograms.                   accuracy and F-score can comprehensively reflect the classification
   The cross-entropy loss and the accuracy values for the training and               performance, they are selected as indicators. Fig. 11 shows the accuracy
the validation datasets were acquired using the proposed method and                  and the F-score of testing in Scene 2 increasing with parameter c’, which
                                                                                     indicates that the performance worsens when the threshold value in­
           Table 2                                                                   creases. Compared with the original images, there is a loss of informa­
           Statistical physical information of the 36 enrolled subjects.             tion for the threshold and the binary approaches, regardless of how to
               Parameter(Unit)                         Value                         adjust the threshold. The binary approach is further simplified based on
                                                                                     the threshold approach due to worse performance than the threshold
               Age(year)                               22.0(20.0,24.75)
               Height(cm)                              169.1 ± 8.0
                                                                                     approach (as seen in Tables 4 and 5). In Tables 4 and 5, the results of the
               Weight(kg)                              59.9 ± 9.5                    threshold and the mask approach are worse than those of the original
               BMI(kg/m2)                              20.8 ± 2.1                    images, and it can be inferred that the clutter and the noise can be
           BMI: body mass index. The statistical values are expressed as             suppressed automatically by the deep neural network.
           the median (1st quartile, 3rd quartile) or mean ± std.                        Su Boyu et al. implemented a wavelet transform to extract the

                                                                                 8
M. He et al.                                                                                                   Biomedical Signal Processing and Control 77 (2022) 103741




                        Fig. 8. Two indoor scenes for radar data measurement, including different activities: (a) Scene 1 and (b) Scene 2.




         Fig. 9. ROC curves and AUCs obtained using 5-fold cross validation for the (a) original, (b) threshold, and (c) binary time Doppler spectrograms.


time–frequency features for fall activity detection [10]. The activity data          stacked autoencoders to auto-extract features and used a logistic
of 4 actors were used to verify the classification performance, with the             regression classifier to detect falls [22]. The highest accuracy was
highest accuracy being 93% [10]. Branka Jokanović et al. adopted two                97.1%, with a sensitivity of 79.0% when using a dataset, including 117


                                                                                 9
M. He et al.                                                                                                             Biomedical Signal Processing and Control 77 (2022) 103741




                                                                                             Fig. 11. The accuracy and the F1-score of testing in Scene 2 vary with parameter
                                                                                             c’. The asterisk and the dot are the accuracy and the F1-score values using the
                                                                                             original time Doppler spectrograms.


                                                                                             another test scene [14]. At present, our radar can only detect falls of the
Fig. 10. (a) Cross-entropy loss and (b) accuracy values for the training and
                                                                                             human body in one room due to the limitation of radar numbers and
validation datasets using the proposed method and the MVM.
                                                                                             transmission radio frequency. Injurious fall events cannot yet be
                                                                                             distinguished from noninjury-related falls. This work has not researched
Table 4                                                                                      the real-time monitoring of falls over a long period of time and it has not
Classification metrics obtained using the proposed method and the MVM using                  distinguished falls between humans and animals. Due to ethical con­
5-fold cross-validation in Scene 1.                                                          straints, the data on falls of the elderly were not allowed to be collected
  Metrics (%) Method          Acc.       Pre.        Sen.       Spe.        F1-score
                                                                                             in this experiment with risk. In the future, we will try to combine mul­
                                                                                             tiple radars or implement a through-wall frequency band to detect falls
  Proposed     Original       98.926     98.443      98.333     99.222      98.388
                                                                                             in multiple rooms. The data in nursing homes, including the elderly and
               Threshold      98.778     98.328      98.000     99.167      98.164
               Binary         96.667     93.455      96.778     96.611      95.087           animals at the same time, should be collected to truly realise effective
                                                                                             and robust fall monitoring and notification. Identifying injuries that fall
  MVM          Original       98.630     97.262      98.667     98.611      97.959
                                                                                             from noninjury-related falls is worth studying.
               Threshold      96.556     93.063      96.889     96.389      94.937
               Binary         92.815     87.957      90.889     93.778      89.399           5. Conclusion
Abbreviations: Acc., Accuracy; Pre., Precision; Sen., Sensitivity; Spe., Specificity.
                                                                                                 In this work, a novel optimum target range bin selection method for
                                                                                             time–frequency analysis to detect falls is proposed based on wideband
Table 5                                                                                      radar and the MobileNetV3-Small network. Data from 36 subjects were
Classification metrics of testing in Scene 2 using the proposed method and the               collected in two real room environments without any constraints,
MVM.                                                                                         including 10 fall and 20 non-fall activities. The proposed optimum target
  Metrics (%) Method           Acc.       Pre.       Sen.       Spe.       F1-score          range bin selection method based on the range Doppler spectrograms
## N Proposed     Original      95.370     94.286     91.667     97.222     92.958            outperforms the MVM in both 5-fold cross validation and testing. The
                 Threshold     92.593     83.981     96.111     90.833     89.637            input of the original and the threshold time Doppler spectrograms to the
                 Binary        92.778     87.701     91.111     93.611     89.373            deep learning network achieves a clearly better classification perfor­
                                                                                             mance than that of the binary time Doppler spectrograms. The higher
  MVM            Original      93.333     96.753     82.778     98.611      89.222           classification metrics indicate the robustness and the generalisability of
                 Threshold     91.111     89.286     83.333     95.000      86.207           the proposed method, even in unseen scenes and for unseen subjects.
                 Binary        88.519     86.875     77.222     94.167      81.765

Abbreviations: Acc., Accuracy; Pre., Precision; Sen., Sensitivity; Spe., Specificity.        CRediT authorship contribution statement

fall activities and 291 non-fall activities from 3 subjects [22]. Baris Erol                    Mi He: Conceptualization, Methodology, Software, Formal analysis,
et al. proposed multidimensional principal component analysis and                            Writing (original draft, review & editing), Visualization, Supervision,
three-dimensional joint-variable radar signal representation, which                          Project administration and Funding acquisition. Yi Yang: Software,
could achieve 97.88% accuracy when using a dataset from 6 subjects                           Methodology, Validation, Formal analysis, Visualization. Qinwen Ping:
[23]. Fall detection in an indoor environment using UWB radars and a                         Software, Validation, Formal analysis. Ran Dai: Investigation, Data
CNN-LSTM architecture was realised with the best accuracy of 98.51%                          curation. Bingwen Liu: Investigation, Resources. Yongjian Nian:
at one position using the leave-one-subject-out (total 10 male subjects)                     Writing-review and Funding acquisition. Zhu Zhang: Writing-review.
strategy [24]. Hamidreza Sadreazami et al. proposed a fall detection
method using ultrawideband radar and a CNN that relied on multilevel                         Declaration of Competing Interest
feature learning from radar time–frequency representations [14]. The 5-
fold cross validation in one scene achieved 93.54% accuracy using data                           The authors declare that they have no known competing financial
from 10 subjects [14]. However, the accuracy decreased to 89.12% in                          interests or personal relationships that could have appeared to influence

                                                                                        10
M. He et al.                                                                                                                    Biomedical Signal Processing and Control 77 (2022) 103741


the work reported in this paper.                                                                 [11] F. Jin, A. Sengupta, S. Cao, mmFall: fall detection using 4-D mm wave radar and a
                                                                                                      hybrid variational RNN autoencoder, IEEE Trans. Automat. Sci. Eng. 19 (2) (2022)
                                                                                                      1245–1257.
Acknowledgements                                                                                 [12] M.G. Amin, Y.D. Zhang, F. Ahmad, K.C.D. Ho, Radar Signal processing for elderly
                                                                                                      fall detection: the future for in-home monitoring, IEEE Signal Proc. Mag. 33 (2)
   This project was supported by the University-level Projects (No.                                   (2016) 71–80.
                                                                                                 [13] H. Sadreazami, M. Bolic, S. Rajan, Fall detection using standoff radar-based sensing
2019XYY04 and No. 2019XBK09) and the Key Logistics Research Project                                   and deep convolutional neural network, IEEE Trans. Circ. Syst. II Express Briefs 67
(No. BLJ18J005).                                                                                      (1) (2020) 197–201, https://doi.org/10.1109/TCSII.2019.2904498.
                                                                                                 [14] H. Sadreazami, M. Bolic, S. Rajan, Contactless fall detection using time-frequency
                                                                                                      analysis and convolutional neural networks, IEEE Trans. Ind. Inform. 17 (10)
References                                                                                            (2021) 6842–6851.
                                                                                                 [15] B. Erol, M.G. Amin, Radar data cube processing for human activity recognition
 [1] W. He, D. Goodkind and P. Kowal, An aging world: 2015. International Population                  using multisubspace learning, IEEE Trans. Aerospace Electron. Sys. 55 (6) (2019)
     Reports, P95/16-1, U.S. Government Publishing Office, Washington, DC, 2016.                      3617–3628.
     https://doi.org/10.13140/RG.2.1.1088.9362.                                                  [16] A.G. Howard, M. Zhu, B. Chen, D. Kalenichenko, W. Wang, T. Weyand, M.
 [2] J.C. Davis, M.C. Robertson, M.C. Ashe, T. Liu-Ambrose, K.M. Khan, C.A. Marra,                    Andreetto, and H. Adam, MobileNets: Efficient Convolutional Neural Networks for
     International comparison of cost of falls in older adults living in the community: a             Mobile Vision Applications, arXiv e-prints, pp. arXiv:1704.04861, 2017. https://
     systematic review, Osteoporos Int. 21 (8) (2010) 1295–1306, https://doi.org/                     doi.org/10.48550/arXiv.1704.04861.
     10.1007/s00198-009-1162-0.                                                                  [17] A.G. Howard, M. Sandler, G. Chu, L. Chen, B. Chen, M. Tan, W. Wang, Y. Zhu, R.
 [3] H. Fischer, T. Maleitzke, C. Eder, S. Ahmad, U. Stöckle, K.F. Braun, Management of              Pang, V. Vasudevan, Q.V. Le, and H. Adam, Searching for MobileNetV3, arXiv e-
     proximal femur fractures in the elderly: current concepts and treatment options,                 prints, pp. arXiv:1905.02244, 2019. https://doi.org/10.48550/arXiv.1905.02244.
     Eur. J. Med. Res. 26 (1) (2021).                                                            [18] M. He, Y. Nian, X. Wang, S. Xiao, Y. Li, Improved clutter suppression algorithm for
 [4] T. Iio, M. Shiomi, K. Kamei, C. Sharma, N. Hagita, Social acceptance by senior                   atmospheric target detection using polarimetric doppler radar, IEEE J. Stars 4 (4)
     citizens and caregivers of a fall detection system using range sensors in a nnursing             (2011) 911–922, https://doi.org/10.1109/JSTARS.2011.2161756.
     home, Adv. Robot. 30 (3) (2016) 190–205, https://doi.org/10.1080/                           [19] M. He, Y. Nian, Y. Gong, Novel signal processing method for vital sign monitoring
     01691864.2015.1120241.                                                                           using FMCW radar, Biomed. Signal. Process. 33 (2017) 335–345, https://doi.org/
 [5] M. Wang, G. Cui, X. Yang, L. Kong, Human body and limb motion recognition via                    10.1016/j.bspc.2016.12.008.
     stacked gated recurrent units network, IET Radar, Sonar Navigation 12 (9) (2018)            [20] M. He, Y. Nian, L. Xu, L. Qiao, W. Wang, Adaptive separation of respiratory and
     1046–1051, https://doi.org/10.1049/iet-rsn.2018.5054.                                            heartbeat signals among multiple people based on empirical wavelet transform
 [6] S.Z. Gurbuz, M.G. Amin, Radar-based human-motion recognition with deep                           using UWB radar, Sensors. Basel 20 (2020) 4913, https://doi.org/10.3390/
     learning: promising applications for indoor monitoring, IEEE Signal. Proc. Mag. 36               s20174913.
     (4) (2019) 16–28.                                                                           [21] H. Li, A. Mehul, J. Le Kernec, S.Z. Gurbuz, F. Fioranelli, Sequential human gait
 [7] R. Zhang, X. Jing, S. Wu, C. Jiang, J. Mu, F.R. Yu, Device-free wireless sensing for             classification with distributed radar sensor fusion, IEEE Sens. J. 21 (6) (2021)
     human detection: the deep learning perspective, IEEE Int. Things 8 (4) (2021)                    7590–7603, https://doi.org/10.1109/JSEN.2020.3046991.
     2517–2539, https://doi.org/10.1109/JIOT.2020.3024234.                                       [22] B. Jokanovic, M. Amin, Fall detection using deep learning in range-doppler radars,
 [8] L. Ren, Y. Peng, Research of fall detection and fall prevention technologies: a                  IEEE Trans. Aerospace Electron. Sys. 54 (1) (2018) 180–189.
     systematic review, IEEE Access 7 (2019) 77702–77722, https://doi.org/10.1109/               [23] B. Erol and M.G. Amin, Radar Data Cube Analysis for Fall Detection, in: 2018 IEEE
     ACCESS.2019.2922708.                                                                             International Conference on Acoustics, Speech and Signal Processing (ICASSP), 2018,
 [9] H. Li, A. Shrestha, H. Heidari, J. Le Kernec, F. Fioranelli, Magnetic and radar                  pp.2446-2450. https://doi.org/10.1109/ICASSP.2018.8461512.
     sensing for multimodal remote health monitoring, IEEE Sens. J. 19 (20) (2019)               [24] J. Maitre, K. Bouchard, S. Gaboury, Fall detection with UWB radars and CNN-LSTM
     8979–8989, https://doi.org/10.1109/JSEN.2018.2872894.                                            architecture, IEEE J. Biomed. Health 25 (4) (2021) 1273–1283, https://doi.org/
[10] B.Y. Su, K.C. Ho, M.J. Rantz, M. Skubic, Doppler radar fall activity detection using             10.1109/JBHI.2020.3027967.
     the wavelet transform, IEEE Trans Biol. Med. Eng. 62 (3) (2015) 865–875.




                                                                                            11

