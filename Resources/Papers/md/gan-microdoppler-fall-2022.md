                                                                                                                                                                 GAN-based Radar Micro-Doppler Augmentation for
## High Accuracy Fall Detection System




IECON 2022 – 48th Annual Conference of the IEEE Industrial Electronics Society | 978-1-6654-8025-3/22/$31.00 ©2022 IEEE | DOI: 10.1109/IECON49645.2022.9968957
                                                                                                                                                                    1st Ritesh Chandra Tewari               2nd Patitapaban Palo                    3rd Jhareswar Maiti                    4th Aurobinda Routray
                                                                                                                                                                               ATDC                           Dept. of Electrical           Dept. of Industrial and Systems                   Dept. of Electrical
                                                                                                                                                                           IIT Kharagpur                        IIT Kharagpur                        IIT Kharagpur                              IIT Kharagpur
                                                                                                                                                                          Kharagpur, India                     Kharagpur, India                     Kharagpur, India                           Kharagpur, India



                                                                                                                                                                    Abstract—Convolution Neural Network (CNN) is one of the                      interference, and long detection range make it a more suitable
                                                                                                                                                                 powerful deep learning tools used in many computer vision                       choice for fall detection [5]. However, one disadvantage of the
                                                                                                                                                                 tasks; however, it is still in a premature state while dealing with             radar sensor is that it reacts to any movement. Therefore, we
                                                                                                                                                                 sensor data due to the unavailability of a large data set. Here in
                                                                                                                                                                 this paper, we present a CNN-based fall detection system. Deep                  can not easily get the desired activity information if there are
                                                                                                                                                                 convolution generative adversarial network (DCGAN) is used to                   other movements in the radar working area.
                                                                                                                                                                 synthesize more fall data before analysis. Sensor data along with               The occurrence of a fall is a very infrequent and diverse
                                                                                                                                                                 synthesized data is prepossessed, and time-varying spectrograms                 phenomenon, leading to insufficient training data for the clas-
                                                                                                                                                                 are derived. We apply CNN on raw spectrogram images of                          sifiers. Varieties of falls can occur, and their unexpectedness
                                                                                                                                                                 different activities to categorize a fall from other activities.
                                                                                                                                                                 As a result, we successfully attain a classification accuracy of                makes it even more challenging to design an accurate system
                                                                                                                                                                 97.2%, surpassing the conventional machine learning methods                     [6]. Natural fall data can be collected by installing the devices
                                                                                                                                                                 and previous works on the same data by a large margin.                          for an extended period in fall-prone areas like the bathroom
                                                                                                                                                                    Index Terms—CNN, FMCW Radar Sensor, GAN, Human Fall                          and old homage [7]. However, due to difficulties in natural fall
                                                                                                                                                                 Detection.                                                                      data collection, maximum research depends on the artificial
                                                                                                                                                                                                                                                 fall data collected by performing false fall-like activities in
                                                                                                                                                                                        I. INTRODUCTION                                          a laboratory setup with the help of young volunteers. Radar
                                                                                                                                                                    According to the World Health Organization (WHO), falls                      systems play a crucial role while collecting data in laboratory
                                                                                                                                                                 are the second foremost reason for unintended or accidental                     setup due to their user-friendly characteristics.
                                                                                                                                                                 death worldwide. Each year around 6,46,000 people die from                      The primary problem researchers face while dealing with
                                                                                                                                                                 injuries due to falls, and 80% of those deaths are from low                     sensor data for fall detection is feature extraction [8]. It
                                                                                                                                                                 and middle-income countries. Although older adults are more                     requires specific domain knowledge to identify the efficient
                                                                                                                                                                 prone to fall, young adults and children are also not barred                    properties of the signal. Moreover, the success of any machine
                                                                                                                                                                 from it. The Centers for Disease Control and Prevention                         learning algorithms like k- Nearest Neighbor (k-NN), Sup-
                                                                                                                                                                 (CDC) reported that children aged 19 and under account for                      port Vector Machine (SVM), Sparse Bayesian Classifier, etc.,
                                                                                                                                                                 8000 hospital emergency room visits every day for fall-related                  depends upon how efficient our features are [9]. Automatic
                                                                                                                                                                 injuries. Fall-associated injuries may include ache, dysfunc-                   feature extraction with the help of deep learning makes the
                                                                                                                                                                 tionality, permanent damage to body parts, and sometimes                        task easier [10], [11]. However, it requires a large dataset
                                                                                                                                                                 even premature death [1]. Quick detection of the fall followed                  to increase the layers of the neural networks. Obtaining a
                                                                                                                                                                 by a proper response by the concerned authority or caregiver                    sizeable human activity dataset is challenging due to various
                                                                                                                                                                 decide the person’s well-being.                                                 reasons like human resource limitations. In this case, GAN-
                                                                                                                                                                 Various fall detection systems have been proposed starting                      based approaches can be beneficial, augmenting synthetic data
                                                                                                                                                                 from wearable systems like accelerometers, push-button types                    from actual data.
                                                                                                                                                                 to non-wearable systems like video cameras, radar, etc. [2].                       The main contributions of this study are the following:
                                                                                                                                                                 Wearable systems need user interventions, or it has to be
                                                                                                                                                                 carried on the body parts all the time, which is not feasible.                     • We propose Deep Convolution neural network-based
                                                                                                                                                                 Camera-based systems [3] suffer from privacy issues as they                          Generative Adversarial Networks (DCGAN) to synthesize
                                                                                                                                                                 will intervene in a person’s private life if installed in a bedroom                  more fall-like data that will help us to achieve higher
                                                                                                                                                                 or bathroom-like areas. Furthermore, its performance highly                          classification accuracy. It can solve one of the major
                                                                                                                                                                 deteriorates in occlusion and low lighting conditions. The                           limitations, lack of data, faced by fall detection-based
                                                                                                                                                                 radar-based system has emerged as one of the researcher’s                            research.
                                                                                                                                                                 prominent choices for automatic fall detection [4]. The ability                    • We also propose a CNN model that takes time-varying
                                                                                                                                                                 to operate in an adverse environment such as darkness, rain,                         raw spectrograms as input for classifying a fall from other
                                                                                                                                                                 fog, dirt, heat, etc., helps to build a robust fall detection system.                non-fall activities. Direct use of spectrogram images en-
                                                                                                                                                                 Its small size, strong resistance to radio frequency (RF)                            ables us to perform classification without getting involved




                                                                                                                                                                       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:35:29 UTC from IEEE Xplore. Restrictions apply.
     in manual feature extraction where domain knowledge is                     A. Data collection
     necessary.                                                                    The used FMCW radar sensor architecture is shown in Fig.
                                                                                2. At first, a synthesizer generates an electromagnetic wave
   II. LITERATURE SURVEY ON SIMILAR WORK                                        with the varying frequency with time, also called a chirp.
                                                                                Then the generated electromagnetic(EM) wave is transmitted
   Fall detection methodologies has several aspects that need                   through the transmitter antenna, and after hitting the target, a
special attention. One such aspect is to decide the position                    few portions are reflected and received at the receiver antenna.
of the sensor [12]. Deep learning based models require a                        The received signal passes through the mixer and results
large amount of data for higher accuracy [13]. In human                         in IF(Intermediate Frequency) signal, which gets amplified
motion analysis, the large amount of data collection involves                   before passing through a low pass filter (LPF) and an analog to
a higher cost which is an inherent problem. As a solution,                      digital converter (ADC) [34]. After converting into the digital
Alnujaim et al. proposed Generative Adversarial Networks                        domain, further data processing takes place. Fioranelli et al.
(GAN) to augment human motion micro-doppler data. Total                         collected most parts of the data at the University of Glasgow.
seven human activities were collected using a micro-Doppler                     A few portions were collected at North Glasgow Housing
sensor. Due to the use of GAN, the accuracy of human                            Association facilities and Age UK West Cumbria Centre [18].
motion recognition increased from 90% to 94% for the same                       Volunteers were encouraged to do few repetitions of each of
CNN model that was used before using GAN [14]. Alharbi                          the six activities, which includes walking back and forth from
et al. proposed Wasserstein GAN (WGAN) to synthesize                            the sensor, sitting down on a chair, standing up from the chair,
balanced and realistic sensor data automatically. Synthetic data                bending forward to pick up an object, drinking anything from
were assessed using CNN and the Long Short-Term Memory                          the cup or glass and a frontal fall. Fall data were collected in
(LSTM) network. Accuracy was improved for incorporating                         a laboratory-controlled environment with only physically fit
WGAN synthesized data with the real data [15]. Kim et al. also                  volunteers. Walking data have a duration of 10s, and all other
proposed a CNN model to identify humans from other objects                      activities have a span of 5s.
like dogs, horses, and cars. Seven different human activities
were also performed for data collection. The proposed method                    B. Generative Adversarial Networks(GAN)
achieved an accuracy of 97.6% for human detection, and                             GAN is an unsupervised machine learning technique that
90.9% accuracy for human activity classification [16]. Li et                    discovers the patterns and regularities in the original data so
al. suggested a Bidirectional LSTM (bi-LSTM) network that                       that it can produce a similar kind of synthesized data. It has
implemented the fusion of features of both wearable and radar                   a wide range of applications due to its unique capabilities,
sensors that attained an accuracy of 96 % [17]. In our work,                    ranging from image de-noising to image-to-image translation
we use DCGAN along with the CNN model to classify fall                          [35]. A GAN is based on the game theory concept of
and non-fall activities. Accuracy has been increased from 96%                   minimax game, and it is made up of two sub-models, such
to 97.2% for the same dataset [18]. Summary of previous and                     as a generator model (G) and a discriminator model(D).
our proposed work on radar based fall detection system has                      These two sub-models compete with each other at the time of
been presented in table I.                                                      training to optimize the outcome of the system. The generator
                                                                                model generates new plausible data, and the discriminator
               III. PROPOSED WORKFLOW                                           model decides whether the data is generated or taken from the
                                                                                actual sample. The discriminator uses a binary classification
   The proposed workflow is presented with a block diagram                      approach using a sigmoid function resulting in the output
as shown in Fig1. In this work, we are using open-source                        value in the range of 0 to 1. The generative model analyzes
data that were collected at the University of Glasgow using a
Frequency Modulated Continuous Wave radar sensor (FMCW)
                                                                                                   Generate
operating at 5.8 GHz center frequency and an instantaneous                          Data
                                                                                                   synthetic      Preprocess        Feature
                                                                                                                                                  Classification
## Collection                                       Extraction
bandwidth of 400 MHz [18]. For convenience now on, we refer                                          data
to open data as Glasgow data. All the Radar specifications
                                                                                                      Fig. 1: Proposed Workflow
are tabulated in the Table II. A total of six types of human
activities were recorded by sixty volunteers aged between 21
to 98, such as walking, sitting down, stand up, pick up an
object, drink water, and fall. In this work, we focus on fall
recognition, where our goal is to discriminate fall from all the
other five activities. At first, we generated synthetic fall data
using GAN to increase our data. Then, time-varying micro-
doppler signatures were extracted from the different activity
data to use as a input in the classification model. 80% of the
total data was used to train the model, and 20% were used for
testing purposes.                                                                              Fig. 2: FMCW Radar Sensor Architecture




      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:35:29 UTC from IEEE Xplore. Restrictions apply.
                                         TABLE I. Previous Work on Radar-based Fall Detection System
                           Radar Type                                                                                      Classification Method
       Reference                                             Dataset               Feature Extraction Method
                      (Operating Frequency)                                                                                     (Accuracy)
                                                                                                                           SVM(89%), NB(81%),
                                                                                       MPA using Sliding
           [4]             CW (24GHz)                Fall-121, Non-Fall-117                                               5-NN(79%), LDA(88%)
                                                                                    root mean square method
                                                                                                                               and DT (77%)
          [19]         IR-UWB(5.9-10.3GHz)          Fall-187, Non-Fall-149              Time frequency plot                    CNN(89.12%)
          [20]         IR-UWB(5.9-10.3GHz)           Fall-121, Non-fall-85                Time series plot                    DCNN(95.83%)
          [21]           FMCW(76-81GHz)           Fall + Non-Fall data = 231             STFT Spectrogram                Line Kernal CNN(95.24%)
                         FMCW(5.8GHz)+                                                     Statistical and
          [17]                                       Fall- 48, Non-Fall-96                                                   Bi-LSTM(95.9%)
                         3 wearable sensors                                           time-frequency features
          [22]         IR-UWB(5.9-10.3GHz)         Fall-1870, Non-Fall-1490             Time-Frequency Plot              Capsul Network(95.43%)
          [23]            CW (10.525GHz)            Fall-500, Non-Fall-250               STFT Spectrogram                      CNN(96%)
## Time Frequency
          [24]              CW(8GHz)                  Fall-32, Non-Fall-32                                                       SVM (NA)
                                                                                          Representations
         [25]             SFCW(5.8GHz)               Fall-60, Non-Fall-40                STFT Spectrogram                     DTW(94.3%)
         [26]               CW(25GHz)               Fall-120, Non-Fall-1236              STFT Spectrogram               ACGAN-DCNN(82.56%)
         [27]              Kinect(4GHz)             Fall-120, Non-Fall-1236              STFT Spectrogram                    DivNet(95.7%)
         [28]                  RCR                  Fall-105, Non-Fall-704               Wavelet Transform                     1-NN(83%)
         [29]               CW(6GHz)                 Fall-15, Non-Fall-45                STFT Spectrogram                     DNN(87.0%)
         [30]            IR-UWB(24GHz)               Fall-80, Non-fall-240                      DWT                           SVM(79.6%)
         [31]           FMCW(2.425GHz)                        NA                         STFT Spectrogram                      CNN(95%)
         [32]               CW(8GHz)                 Fall-20, Non-Fall-10                Wavelet Transform           Mahalanobis Distance Metric(NA)
         [33]             IR-UWB(4GHz)              Fall-102, Non-Fall-408               Wavelet Transform                    CNN(92.6%)
       Proposed           FMCW(5.8GHz)              Fall-198, Non-Fall-350               STFT Spectrogram                DCGAN+CNN(97.2%)
  IR-UWB=Impulse-radio Ultrawide Band, CW = Continuous Wave, FMCW = Frequency Modulated Continuous Wave, SFCW = Step Frequency Continuous Wave, RCR =
  Range-Controlled Radar, MPA = Major Physical Activities, STFT = Short-time Fourier transform, DWT = Discrete Wavelet transform, SVM = Support Vector Machine, NB
  = Naive Bayes, k-NN = k-Nearest Neighbour, LDA = Linear Discriminant Analysis, DT = Decision Tree, CNN = Convolution Neural Network, DCNN = Deep Convolution
  Neural Network, Bi-LSTM = Bidirectional Long Short Term Memory, DTW = Dynamic Time Wrapping, ACGAN = Auxiliary Classifier Generative Adversarial Network,
  DivNet = Diversity Networks




                                                         Fig. 3: Proposed CNN Architecture

                 TABLE II. Specification of used system
                                                                                 structure of our GAN-based model.
## Parameter              Value
                    Transmitted Power        +19 dBm
                    Starting Frequency        5.8 GHz
                     Stop Frequency           6.2 GHz                               In our case, we have 198 fall data and 350 non-fall data
                        Bandwidth            400 MHz                             consisting of different activities. Each fall data is five seconds
                     Frequency Slope        0.4 MHz/µs                           span data, sampled at the rate of 128 kHz, which gives us
                      Chirp Duration            1ms
                                                                                 6,40,000 samples per data. Direct application of this data into
                    ADC sampling rate        128 KHz
                                                                                 any GAN network would require more powerful processors.
                                                                                 In order to successfully apply GAN to these data, we divided
the distribution of the data in such a way that, after the                       it into 100 parts of 6,400 samples each. We train all the 100
training phase, the probability of the discriminator making                      samples independently; then, we combine all the generated
a mistake maximizes [36]. Algorithm 1 shows the overall                          100 samples to get one complete five-second fall data. We




     Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:35:29 UTC from IEEE Xplore. Restrictions apply.
Algorithm 1 Generalised Adversarial Network (GAN)                                   Raw                              IIR
                                                                                                                                    Range
                                                                                   Sensor           FFT             Notch                            STFT
    1) Define the Problem                                                           Data                            Filter
                                                                                                                                   Selection
       At first, the goal is set, and data is collected.
    2) Set Architecture of the GAN                                                                   Fig. 4: Preprocessing Steps
       Based on the specific problem, we set the architecture
       of the GAN. In our case, the generator model consists
       of four convolutional layers followed by ReLU acti-
       vation. Furthermore, the final convolutional layer has
       activation of Tanh. In contrast, the discriminator model
       consists of five convolutional layers followed by Leaky
       ReLU activation. Furthermore, The final convolutional
       layer has a sigmoid activation. Batch Normalization is
       used to avoid overfitting. The batch size is kept to
       16, and the learning rate is 0.002. Adam optimizer is
       used with a beta value of 0.5. The number of input
       channels to the training set data is 2, and the size of
       feature maps is 6,400.
    3) Train the Discriminator with real data
       Train the discriminator with the real data to predict
       them as a real value.
    4) Generate Synthetic Data from Generator
       In this step, we generate fake or synthetic samples out
       of the generator.
    5) Train the Discriminator with Synthetic Data
       Again train the discriminator with the fake data gen-
       erated by the generator. This way discriminator knows
       what kind of data is accurate and which is fake.
    6) Train Generator with the help of Discriminator
       Output
       Based on the predictions, we train the generator to fool
       the discriminator. The generator’s (G) objective is to
       generate data indistinguishable from the actual data by
       discriminator (D).
                                                                                Fig. 5: Time-varying spectrograms of six actions: (a) Walking;
                                                                                (b) Sitting Down; (c) Stand up; (d) Pick up an object; (e) Drink
consider the deep convolutional neural network-based GAN                        Water; (f) Fall
(DCGAN). DCGAN is nothing but uses convolutional layers
in the generator and discriminator models. We successfully
increased our fall data from 198 to 250 with the help of the                    notch filter having a cut-off frequency 0.0075Hz was applied.
GAN.                                                                            It helps us remove the range components near the 0Hz frequen-
                                                                                cies created by stationary objects surrounded by the target.
C. Preprocessing                                                                Then Short-time Fourier transform (STFT) was implemented,
   Fig. 3 shows a blueprint of our proposed CNN model.                          having a 0.2s hamming window and 95% overlapping factor on
Before feeding the model, data must go through the prepro-                      the obtained range-time data matrix to extract the time-varying
cessing part to remove unwanted noise and components often                      micro-doppler spectrogram [37]. Fig. 5 shows the spectrogram
created from the small vibrations of the device. The necessary                  images of different activities.
preprocessing steps are shown in Fig 4. At first, the data
was rearranged in a matrix form containing 128 rows and M                       D. Feature Extraction
columns, where M represents a total number of chirps in the                        Human movement generates two kinds of signatures, i.e.,
activity duration and 128 is the number of time samples within                  Doppler and micro-Doppler. Doppler signature is based on
one chirp. Then, we apply fast Fourier transform (FFT) to each                  the movement of the overall body, where micro-Doppler
column of the data matrix and find spectrum centered at the                     signatures are generated due to the movement of the different
beat frequency, which is proportional to the target’s distance                  limbs of the body, like swinging of head, torso, and limbs of
from the sensor. Thus after obtaining the range profile of the                  the person. Micro Doppler frequencies represent the sideband
target, we apply a filter to identify only moving objects. A 9th                of the primary Doppler frequency [38]–[40] and play a
order infinite impulse response (IIR) high-pass Butterworth                     prominent role in distinguishing different human activities




      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:35:29 UTC from IEEE Xplore. Restrictions apply.
                                                                                A. Results of Our Approach
                                                                                   We note down the accuracy while each fold acts as a test
                                                                                set and show in Table III. We can see from the table, we have
                                                                                achieved the highest accuracy of 99% using fold-1 as the test
                                                                                set and the lowest accuracy of 95% using fold-4 as the test
                                                                                set. Overall, an average of 97.2% accuracy is attained by our
                                                                                proposed model, which was improved by 1.1% for using the
                                                                                GAN generated fall data along with the real fall data as shown
                                                                                in Table IV. We also measured the standard deviation of our
                                                                                results to 1.48.
Fig. 6: Time-varying spectrogram of fall (a) without GAN-
generated data, (b) with GAN-generated data                                     B. Comparison with Previous Approaches
with higher accuracy. To incorporate micro-Doppler signatures                      We compared our work with previous works [41], [42], [43]
in our experiment, we use time-varying spectrogram images                       and [17] on the same Glasgow dataset [18]. The compared
directly as input to the CNN model. Images were reshaped to                     works deal with multi-class classification having fall one of the
a dimension of 54 × 68 before feeding to the input layer and                    class. We show the accuracy of only falls vs. other activities
extracting complex features.                                                    from the confusion matrix. The accuracy of all the mentioned
Our proposed CNN model consists of two convolution layers                       work is shown in Table V. It is clearly seen that, our proposed
followed by two pooling layers and four fully connected                         method achieved a higher accuracy as compared to others. Our
layers. The first convolution layer contains six, and the second                proposed DCGAN structure generates high-quality synthetic
convolutions layer consists of sixteen convolution filters of                   data, which eventually increases the count of our training data,
size 5 × 5 each. We used a maxpool of size 2 × 2 for pooling                    leading to a higher accuracy.
layers, and the usual ReLU (Rectified Linear Unit) served
                                                                                                 TABLE III. Five-fold cross validation
as the activation unit. The primary purpose of ReLU is to
remove all the negative values from the feature matrix while                              Fold       Fold 1     Fold 2    Fold 3     Fold 4       Fold 5
keeping the positive values intact. Pooling is applied after                            Accuracy      99%        97%       98%        95%          97%
passing through the activation layer, and it is responsible for                        TABLE IV. Accuracy With and Without synthetic data
shrinking the image stack into a smaller size.
                                                                                                      Without synthetic data     96.1%
At last, we took our filtered and shrunk images and stack
                                                                                                       With synthetic data       97.2%
them together in one column, often called flattening of data, to
feed into the fully connected layer. In fully connected layers,
                                                                                       TABLE V. Comparative Analysis on Glasgow data [18]
every neuron of the first layer is connected to every neuron in
the second layer. To optimize the weights of the convolution                        Ref.                          Method                            Accuracy
                                                                                    [41]                       Sensor Fusion                         91.3%
filters backpropagation algorithm used cross-entropy loss and
                                                                                    [42]        Spectrogram features with different classifiers       94%
an Adagrad optimizer with a learning rate of 0.0001. We                             [43]          SVM+Artificial Neural Network (ANN)                 96%
run the optimization loop for 100 epochs, and as the data                           [17]                    Bi-LSTM Network                          95.9%
size was not that big, it took around five minutes to train the                   Proposed                    DCGAN+CNN                              97.2%
model.
                                                                                         V. CONCLUSION AND FUTURE WORK
                                                                                   CNN and other deep learning techniques have received close
E. Classification                                                               attention in various research areas. However, collecting a large
                                                                                dataset for training the neural network is still a big chal-
   Softmax function, also known as a normalized exponential
                                                                                lenge. This paper presented Generative Adversarial Network
function, was used as the activation function in the last layer of
                                                                                to augment Doppler radar data of human falls measured by
the model to normalize the output to a probability distribution
                                                                                the FMCW radar setup. We used CNN for the classification
over predicted output classes.
                                                                                of a human fall from other activities. As micro-Doppler
                                                                                characteristic provides minute signatures of particular human
              IV. EXPERIMENTAL RESULTS
                                                                                activity, we prefer raw time-varying spectrogram as the input
   We generated a total of 52 fall data using GAN. Fig 6 shows                  of the CNN model. One point to be noted here is that in this
a time-varying spectrogram of augmented fall data along with                    work, we have not used much domain knowledge to extract
a spectrogram of original fall data . We used five-fold cross-                  the complex features out of the data; instead, the spectrogram
validation to find the effectiveness of our model. At first,                    itself served as an input to our CNN model. Due to the
we divided our whole dataset into five equal parts. Then we                     augmentation of data, we could construct and train deeper
train the model with four folds and test the model using the                    neural networks effectively, and as a result, we achieved a
remaining one fold. This same process is repeated until each                    classification accuracy of 97.2%. We want to shift our research
fold serves as a test set once.                                                 work from binary to multi-class classification in the future.




      Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:35:29 UTC from IEEE Xplore. Restrictions apply.
                              R EFERENCES                                         [23] Haruka Yoshino, Vasily G Moshnyaga, and Koji Hashimoto. Fall
                                                                                       detection on a single doppler radar sensor by using convolutional neural
 [1] World Health Organization, World Health Organization. Ageing, and                 networks. In 2019 IEEE International Conference on Systems, Man and
     Life Course Unit. WHO global report on falls prevention in older age.             Cybernetics (SMC), pages 2889–2892. IEEE, 2019.
     World Health Organization, 2008.                                             [24] Branka Jokanovic, Moeness G Amin, Yimin D Zhang, and Fauzia
 [2] Fatih Erden, Senem Velipasalar, Ali Ziya Alkar, and A Enis Cetin.                 Ahmad. Multi-window time–frequency signature reconstruction from
     Sensors in assisted living: A survey of signal and image processing               undersampled continuous-wave radar measurements for fall detection.
     methods. IEEE Signal Processing Magazine, 33(2):36–44, 2016.                      IET Radar, Sonar & Navigation, 9(2):173–183, 2015.
 [3] Na Lu, Yidan Wu, Li Feng, and Jinbo Song. Deep learning for                  [25] Marco Mercuri, Ping Jack Soh, Gokarna Pandey, Peter Karsmakers,
     fall detection: Three-dimensional cnn combined with lstm on video                 Guy AE Vandenbosch, Paul Leroux, and Dominique Schreurs. Analysis
     kinematic data. IEEE journal of biomedical and health informatics,                of an indoor biomedical radar-based system for health monitoring. IEEE
     23(1):314–323, 2018.                                                              Transactions on Microwave Theory and Techniques, 61(5):2061–2068,
 [4] Khadija Hanifi and M Elif Karsligil. Elderly fall detection with vital            2013.
     signs monitoring using cw doppler radar. IEEE Sensors Journal,               [26] Baris Erol, Sevgi Z Gurbuz, and Moeness G Amin. Gan-based synthetic
     21(15):16969–16978, 2021.                                                         radar micro-doppler augmentations for improved human activity recog-
 [5] Michalis Vrigkas, Christophoros Nikou, and Ioannis A Kakadiaris. A                nition. In 2019 IEEE Radar Conference (RadarConf), pages 1–5. IEEE,
     review of human activity recognition methods. Frontiers in Robotics               2019.
     and AI, 2:28, 2015.                                                          [27] Mehmet S Seyfioglu, Baris Erol, Sevgi Z Gurbuz, and Moeness G
 [6] Raul Igual, Carlos Medrano, and Inmaculada Plaza. Challenges, issues              Amin. Diversified radar micro-doppler simulations as training data
     and trends in fall detection systems. Biomedical engineering online,              for deep residual neural networks. In 2018 IEEE radar Conference
     12(1):1–24, 2013.                                                                 (radarConf18), pages 0612–0617. IEEE, 2018.
 [7] Liang Liu, Mihail Popescu, Marjorie Skubic, Marilyn Rantz, and Paul          [28] Bo Yu Su, KC Ho, Marilyn J Rantz, and Marjorie Skubic. Doppler radar
     Cuddihy. An automatic in-home fall detection system using doppler                 fall activity detection using the wavelet transform. IEEE Transactions
     radar signatures. Journal of Ambient Intelligence and Smart Environ-              on Biomedical Engineering, 62(3):865–875, 2014.
     ments, 8(4):453–466, 2016.                                                   [29] Branka Jokanovic, Moeness Amin, and Fauzia Ahmad. Radar fall
 [8] Muhammad Mubashir, Ling Shao, and Luke Seed. A survey on fall                     motion detection using deep learning. In 2016 IEEE radar conference
     detection: Principles and approaches. Neurocomputing, 100:144–152,                (RadarConf), pages 1–6. IEEE, 2016.
     2013.                                                                        [30] Baris Erol, Moeness G Amin, and Boualem Boashash. Range-doppler
 [9] Samina Khalid, Tehmina Khalil, and Shamila Nasreen. A survey of                   radar sensor fusion for fall detection. In 2017 IEEE Radar Conference
     feature selection and feature extraction techniques in machine learning.          (RadarConf), pages 0819–0824. IEEE, 2017.
     In 2014 science and information conference, pages 372–378. IEEE,             [31] Abhijit Bhattacharya and Rodney Vaughan. Deep learning radar design
     2014.                                                                             for breathing and fall detection. IEEE Sensors Journal, 20(9):5072–
[10] Sevgi Zubeyde Gurbuz and Moeness G Amin. Radar-based human-                       5085, 2020.
     motion recognition with deep learning: Promising applications for indoor     [32] Ajay Gadde, Moeness G Amin, Yimin D Zhang, and Fauzia Ahmad.
     monitoring. IEEE Signal Processing Magazine, 36(4):16–28, 2019.                   Fall detection and classifications based on time-scale radar signal
[11] Ping Wang, Qimeng Li, Peng Yin, Zhonghao Wang, Yu Ling, Raffaele                  characteristics. In Radar Sensor Technology XVIII, volume 9077, pages
     Gravina, and Ye Li. A convolution neural network approach for fall                330–338. SPIE, 2014.
     detection based on adaptive channel selection of uwb radar signals.          [33] Liang Ma, Meng Liu, Na Wang, Lu Wang, Yang Yang, and Hongjun
     Neural Computing and Applications, pages 1–14, 2022.                              Wang. Room-level fall detection based on ultra-wideband (uwb) mono-
[12] Tao Yang, Jun Cao, and Yongxin Guo. Placement selection of millimeter             static radar and convolutional long short-term memory (lstm). Sensors,
     wave fmcw radar for indoor fall detection. In 2018 IEEE MTT-S                     20(4):1105, 2020.
     International Wireless Symposium (IWS), pages 1–3. IEEE, 2018.               [34] Anuradha Singh, Saeed Ur Rehman, Sira Yongchareon, and Peter
[13] Yann LeCun, Yoshua Bengio, and Geoffrey Hinton. Deep learning.                    Han Joo Chong. Sensor technologies for fall detection systems: A
     nature, 521(7553):436–444, 2015.                                                  review. IEEE Sensors Journal, 20(13):6889–6919, 2020.
[14] Ibrahim Alnujaim and Youngwook Kim. Augmentation of doppler radar            [35] Qingsong Yang, Pingkun Yan, Yanbo Zhang, Hengyong Yu, Yongyi Shi,
     data using generative adversarial network for human motion analysis.              Xuanqin Mou, Mannudeep K Kalra, Yi Zhang, Ling Sun, and Ge Wang.
     Healthcare informatics research, 25(4):344–349, 2019.                             Low-dose ct image denoising using a generative adversarial network
[15] Fayez Alharbi, Lahcen Ouarbya, and Jamie A Ward. Synthetic sensor                 with wasserstein distance and perceptual loss. IEEE transactions on
     data for human activity recognition. In 2020 International Joint                  medical imaging, 37(6):1348–1357, 2018.
     Conference on Neural Networks (IJCNN), pages 1–9. IEEE, 2020.                [36] Antonia Creswell, Tom White, Vincent Dumoulin, Kai Arulkumaran,
[16] Youngwook Kim and Taesup Moon. Human detection and activity clas-                 Biswa Sengupta, and Anil A Bharath. Generative adversarial networks:
     sification based on micro-doppler signatures using deep convolutional             An overview. IEEE Signal Processing Magazine, 35(1):53–65, 2018.
     neural networks. IEEE geoscience and remote sensing letters, 13(1):8–        [37] Xingzhuo Li, Zhenghui Li, Francesco Fioranelli, Shufan Yang, Olivier
     12, 2015.                                                                         Romain, and Julien Le Kernec. Hierarchical radar data analysis for
[17] Haobo Li, Aman Shrestha, Hadi Heidari, Julien Le Kernec, and                      activity and personnel recognition. Remote Sensing, 12(14):2237, 2020.
     Francesco Fioranelli. Bi-lstm network for multimodal continuous              [38] Victor C Chen, Fayin Li, S-S Ho, and Harry Wechsler. Analysis of
     human activity recognition and fall detection. IEEE Sensors Journal,              micro-doppler signatures. IEE Proceedings-Radar, Sonar and Naviga-
     20(3):1191–1201, 2019.                                                            tion, 150(4):271–276, 2003.
[18] Francesco Fioranelli, Syed Aziz Shah, Haobo Li, Aman Shrestha, Shufan        [39] Dave Tahmoush. Review of micro-doppler signatures. IET Radar, Sonar
     Yang, and Julien Le Kernec. Radar signatures of human activities. 2019.           & Navigation, 9(9):1140–1146, 2015.
[19] Hamidreza Sadreazami, Miodrag Bolic, and Sreeraman Rajan. Contact-           [40] Ram M Narayanan and Matthew Zenaldin. Radar micro-doppler
     less fall detection using time-frequency analysis and convolutional neural        signatures of various human activities. IET Radar, Sonar & Navigation,
     networks. IEEE Transactions on Industrial Informatics, 17(10):6842–               9(9):1205–1215, 2015.
     6851, 2021.                                                                  [41] Haobo Li, Aman Shrestha, Francesco Fioranelli, Julien Le Kernec,
[20] Hamidreza Sadreazami, Miodrag Bolic, and Sreeraman Rajan. Fall                    Hadi Heidari, Matteo Pepa, Enea Cippitelli, Ennio Gambi, and Susanna
     detection using standoff radar-based sensing and deep convolutional               Spinsante. Multisensor data fusion for human activities classification
     neural network. IEEE Transactions on Circuits and Systems II: Express             and fall detection. In 2017 IEEE SENSORS, pages 1–3. IEEE, 2017.
     Briefs, 67(1):197–201, 2019.                                                 [42] A Shrestha, J Le Kernec, F Fioranelli, E Cippitelli, E Gambi, and
[21] Bo Wang, Liang Guo, Hao Zhang, and Yong-Xin Guo. A millimetre-                    S Spinsante. Feature diversity for fall detection and human indoor
     wave radar-based fall detection method using line kernel convolutional            activities classification using radar systems. 2017.
     neural network. IEEE Sensors Journal, 20(22):13364–13370, 2020.              [43] Haobo Li, Aman Shrestha, Hadi Heidari, Julien Le Kernec, and
[22] Hamidreza Sadreazami, Miodrag Bolic, and Sreeraman Rajan. Capsfall:               Francesco Fioranelli. Magnetic and radar sensing for multimodal remote
     Fall detection using ultra-wideband radar and capsule network. IEEE               health monitoring. IEEE Sensors Journal, 19(20):8979–8989, 2018.
     Access, 7:55336–55343, 2019.




       Authorized licensed use limited to: Universitas Brawijaya. Downloaded on September 01,2026 at 11:35:29 UTC from IEEE Xplore. Restrictions apply.

