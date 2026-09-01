Journal of Ambient Intelligence and Smart Environments 8 (2016) 453–466                                                          453
DOI 10.3233/AIS-160388
IOS Press




An automatic in-home fall detection system
using Doppler radar signatures
Liang Liu a,* , Mihail Popescu b , Marjorie Skubic a , Marilyn Rantz c and Paul Cuddihy d
a Department of Electrical and Computer Engineering, University of Missouri, Columbia, MO, USA
b Department of Health Management and Informatics, University of Missouri, Columbia, MO, USA
c Sinclair School of Nursing, University of Missouri, Columbia, MO, USA
d General Electric Global Research, Niskayuna, NY, USA




Abstract. One in three elders over the age of 65 falls each year in the United States. This paper describes a non-invasive fall
detection system based on a Doppler radar sensor. The developed system has been tested in two environments: laboratory and
real senior living apartments. While some laboratory results appeared in our previous papers, the main novelty of this paper
consists in the deployment of our fall detection system in six apartments from TigerPlace (a senior living facility in Columbia,
Missouri). The fall detection results obtained in our laboratory were excellent, with the radar placed on the ceiling performing
better than on the floor. The fall detection system was then evaluated using radar data collected over two weeks in six TigerPlace
apartments. The fall detection system successfully detected all six natural senior falls in an apartment for the examined one week.

Keywords: Doppler radar, eldercare, fall detection, MFCC




1. Introduction                                                           ones [10]. Moreover, wearable devices are not suit-
                                                                          able for night time or shower use [26]. Conversely,
   Falls are the dominant reason for accidental death                     non-wearable devices such as floor vibration sensors
in population above age 65 [25]. Moreover, the death                      [4,5,39], video cameras [6], passive infrared sensor
rate caused by falling is increasing in the past decade                   [33,39], microphone arrays [18,27,28], and sensor net-
as more Americans live longer and more independent                        works [9,36] are more appropriate for less active elders
lives [34]. While prevention is desirable, falls still oc-                and night-time use. In assistive living and ambient in-
cur due to the limited success of prediction algorithms                   telligence applications [7,8,29], each non-wearable de-
and intervention strategies [31]. After an injurious fall                 vice has its own advantages and disadvantages. Aside
occurs, it is important that medical intervention fol-                    from privacy preserving, Doppler radars have advan-
lows as soon as possible in order to reduce long term                     tages, such as independence on lighting conditions, in-
consequences [15,24]. This paper describes a Doppler                      expensive, non-invasive, sensing through occlusions,
radar automatic fall detection system that could be                       and deployable in bathrooms.
used to alert the nursing personnel as soon as a fall                        Based on the idea that different human body parts
happened.                                                                 produce specific radar signatures, different types of
   Recently, many fall monitoring devices have been                       radar sensors could recognize various human activ-
described in the literature. They can be divided into                     ities, such as continuous-wave (CW) radar for gait
two categories: wearable and non-wearable. Wearable                       analysis [12], two-element receiver array for running,
devices, such as accelerometers, gyroscopes [13] or                       walking, and standing [17], M-sequence-based ultra-
“push-buttons”, are suitable for active elders but are                    wideband sensor network for vitality monitoring [32].
less appropriate for less active or cognitively impaired                  We note that none of the above radars are deployed
                                                                          in a real life setting collecting realistic data. There are
  * Corresponding author. E-mail: llpfd@mail.missouri.edu.                two main categories of Doppler signature representa-

1876-1364/16/$35.00 © 2016 – IOS Press and the authors. All rights reserved
454                    L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures


tion methods. The methods in the first category are
based on the pattern extracted from the spectrogram.
Kim et al. [17] extracts six features from a filtered
spectrogram: torso Doppler frequency, total bandwidth
(BW), offset of the total Doppler, BW without micro-
Dopplers, the normalized standard deviation (STD) of
the signal strength, and the period of the limb motion.
Wu et al. [37] applies image segmentation and mor-
phological operations using the spectrogram as a bi-
nary image. The maximum/minimum frequency and
time values generate three features: extreme frequency
magnitude, extreme frequency ratio, and the time span
                                                                       Fig. 1. Radar sensor hardware setup. (a) Schematic view. (b) Floor
of the event. In the second category, the features are                 sensor 0.42 m × 0.32 m × 0.23 m deployment box.
derived from sound processing techniques due to the
fact that sound waves and radar waves share similar                    is that it evaluates a Doppler radar fall detection sys-
characteristics in frequency changes. The sound wave                   tem in a real living environment. A real living environ-
frequency changes when the listener moves toward or                    ment poses many challenges for fall detection such as
away from the source [14]. An example of this kind                     antenna configuration, room size, furniture occlusions
of feature is represented by the mel-frequency cepstral                and movement, building materials, pets and visitors.
coefficients (MFCCs) [16,20–22,38]. This approach is                      The context of our research is a parent study for ad-
supported by the fact that human operators can differ-                 dressing falls in elderly with a two-fold aim: to mon-
entiate certain targets by listening to the audio output               itor gait for fall risk [10] and to develop methods for
of the surveillance Doppler radar [16].                                fall detection using Doppler radar. Radar sensors were
   In a related project, we used floor radars to com-                  first deployed on the floor for optimal gait detection.
pute gait velocity and stride duration to estimate the                 Although we previously showed that a ceiling place-
fall risk [38]. Inspired by this system, we proposed                   ment is better than a floor one for fall detection [20],
the idea of an automatic fall detection system based                   TigerPlace fall experiments presented here were per-
on Doppler radar signatures and presented preliminary                  formed with both of the floor radars due to our empha-
laboratory results in [22]. In subsequent work [20,21],                sis on fall prevention using gait evaluation, and ceiling
we proposed a two radar sensor system together with                    radar for better performance in detecting natural falls.
a decision-level fuzzy fusion method for integrating                      This paper is organized as follows. Section 2 in-
multiple information sources [21]. We examined the                     troduces the system overview. Section 3 describes the
system performance in our laboratory for various sen-                  methods and algorithms. Section 4 provides the data
sor positions and fall directions because only the ra-                 collection and evaluation. Section 5 presents the exper-
dial velocity (i.e. collinear to the beam) component of                imental results. More details about the results are dis-
the moving subject can be detected by a Doppler radar                  cussed in Section 6. We draw conclusions in Section 7.
[20]. We concluded that for sensors positioned on the
floor, the detection of a fall lateral to the radar is not
as good as a fall towards or away from it. At the same                 2. System overview
time, sensors installed on the ceiling are less sensitive
to falling direction, since there will always be a down-                  The fall detection system is composed of a Doppler
ward (away from the radar) component of the radar                      radar sensor, and the related signal processing and pat-
signal.                                                                tern recognition algorithms.
   In this paper we introduce two new refinements to                      We used a commercial GE range controlled Doppler
our radar processing algorithm, one related to feature                 radar (RCR) as in [20–22] with a center frequency
alignment and another needed for online fall detection.                of 5.8 GHz and a target velocity between 0.15 and
The developed algorithms were tuned first in our lab-                  1.5 m/s. The range of the radar is set to 6 meters with
oratory and then were evaluated in TigerPlace, a se-                   a 90° viewing angle. Figure 1(a) shows the diagram of
nior living facility in Columbia, MO [31]. Unlike other                the hardware setup. We use a wireless router to trans-
fall detection systems that are only evaluated in artifi-              mit and store the sensor data from RCR to the apart-
cial environments [11], the main novelty of this paper                 ment computer using a DI-710 DataQ (www.dataq.
                       L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures           455




                                  Fig. 2. Block diagram for the processing procedure to detect a fall.

com) data logger. The data are then transferred from                    termine whether or not the feature vector represents a
each apartment computer to a central server for further                 fall. A detailed description of each block in Fig. 2 is
processing.                                                             given in the following Section 3.
   We used a 0.42 m × 0.32 m × 0.23 m wood box
to deploy the RCR and its auxiliary equipment such
as power supply, data acquisition board, and wireless                   3. Methodology and algorithms
router (see Fig. 1(b)). The RCR was mounted on a                        3.1. Potential fall segmentation
bracket inside the box at a height of 10 cm from the
bottom. The data logger was mounted on the top of                         A typical time domain radar signal waveform seg-
the RCR and the wireless router was placed on top                       ment in time domain with two falls is shown in Fig. 3.
of the DataQ. The signal and power supply wires are                     Two second windows around each fall are marked by
placed outside of the RCR range. The floor RCR sur-                     dotted lines.
face is wrapped by foil with a slot to exclude potential                  The fall location procedure is based on finding the
false alarm sources, such as possible electronic fields                 energy burst peaks in the spectrogram. To compute the
formed by electric motors or high voltage equipment,                    spectrogram of the radar signal x(n) we first compute
and moving or vibrating objects, such as fans, pulleys                  the short time Fourier transform (STFT) as:
and conveyor belts.                                                                            ∞
   For ceiling RCR, we did not use the slotted foil in                       STFT(m, ω) =           x(n)w(n − m)e−j ωn , (1)
order to allow for a wider view range. In the laboratory                                          n=−∞
tests, we placed the RCR on the ceiling of the labora-                  where w(n) is the Hamming window with N-width
tory at the room center (about 3.5 m high). In the apart-               (N = 512) defined by
ment, we fixed the RCR in a wooden bracket in the at-                                                   
tic, above the ceiling dry wall, at the living room center                                           2πn
                                                                            w(n) = 0.54 − 0.46 cos        .       (2)
facing down to the floor. All the RCRs were carefully                                               N −1
calibrated to obtain a clear signal before installation.
   In order to assess the timing of the fall and to inves-                The spectrogram is defined as the magnitude of
tigate the types of false alarms detected in each apart-                squared of STFT as:
ment by the fall detection system, we used a depth
camera (Kinect). The Kinect camera was installed in                           spectrogram{x(n)} = |STFT(m, ω)|2 .           (3)
the living room, above the entrance door.
   The block diagram of the fall detection algorithm is                    The spectrogram of the time domain radar signal
displayed in Fig. 2. After the temporal position of a po-               from Fig. 3 is shown in Fig. 4.
tential fall is identified, features are extracted in a two                To identify falls using the spectrogram shown in
                                                                        Fig. 4, we compute the spectral energy burst (EB) by
second window around it. Then, mel-frequency cep-
                                                                        summing the energy in the [A, B] Hz frequency range
stral coefficients (MFCC) features are computed and
                                                                        as:
aligned with similar feature vectors from the training
set. The feature alignment procedure makes the fall de-                                      
                                                                                           ω=A/(2π)
tection algorithm more resilient to the fall location in                      EB(m) =                    |STFT(m, ω)|2 .    (4)
the temporal window. Finally, a classifier is used to de-                                  ω=B/(2π)
456                        L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures




                                                                                           Fig. 5. Energy burst curve for Fig. 4.
Fig. 3. A typical time domain radar signal waveform segment in-
cluding two falls (the signal waveform measured along time). Each
fall is labeled with a 2-s green dotted window.




                                                                           Fig. 6. Influence of the frequency range on detecting potential falls
                                                                           (marked by red stars) on energy burst curve: a) original radar signal
Fig. 4. Spectrogram of the signal waveform from Fig. 3. The
                                                                           including 4 falls (green lines) and walking (red box); b) [10, 50] Hz
non-negative frequencies are only displayed because the negative
                                                                           range; c) [25, 50] Hz range; d) [30, 200] Hz range.
frequency STFT values are complex-conjugates of the positive fre-
quency values. So the magnitudes-squared are identical to their pos-
itive counterparts.                                                        in the spectrogram, we analyzed a 20 min radar signal
                                                                           segment by identifying the energy bursts over a given
A peak in the energy burst curve (see Fig. 5) is asso-                     threshold and correlated them to the ground truth (see
ciated with the occurrence of a high velocity motion,                      Fig. 6).
such as a fall.                                                               The frequencies below 25 Hz are typically associ-
   One question is determining the best choice for the                     ated with low speed activities such as walking (see
frequency range [A, B]. The Doppler shift (hence the                       extra detections in Fig. 6(b) vs 6(c)). As we increase
signal waveform in Fig. 3) f is proportional to the                       the lower frequency threshold, A, the number of false
speed variation v along radar axis, f ∼ v, for                          alarms produced by walking decreases. Similarly, in-
every point of the falling body. In the falling process,                   creasing the higher threshold, B, seems to slightly de-
some points of the body are going toward while oth-                        crease the false alarms (see Fig. 6(c) vs 6(d)). How-
ers are going away from the radar (imagine a twisting                      ever, less useful information seems to be present past
motion during falling), hence generating the frequency                     200 Hz (see Fig. 4). In this paper, for fall detection, we
patterns in Fig. 4. To choose the useful frequency range                   choose the [A, B] frequency range as [25, 50] Hz.
                        L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures                     457


  After the EB curve is computed, we then smooth it
using a moving average with K = 5 (K was selected
empirically by trial and error) as:

                
                K−1
     EB(m) =           EB(m − i).                           (5)
                 i=1

   On the energy burst curve, a peak means the oc-
currence of an extreme motion, such as a fall. A peak
finder with a threshold is used to locate this potential
fall location. By adjusting the threshold, the number of
potential fall activities varies. Figure 5 shows an en-
ergy burst curve with located fall peaks.

3.2. Feature extraction
                                                                        Fig. 7. Examples of fall (a) and nonfall (b) feature vectors for a
                                                                        2-second signal window.
   To describe the Doppler signal we used features em-
ployed in speech recognition such as Mel-frequency                      vectors for a 2 s signal window are shown in Figs 7(a)
cepstral coefficients (MFCC) and 1-D local binary pat-                  and (b), respectively. The fall feature vector contains
terns [40]. The reason for this choice is that human                    larger values within a blob shape at the vector center
radar operators were able to identify certain targets by                to represent the fall event in Fig. 7(a), while the non-
listening to the Doppler audio output [16]. In our lab-                 fall feature vector shows a random variation pattern in
oratory experiments MFCCs outperformed other fea-                       Fig. 7(b).
tures, such as zero crossing rate and energy frequency
bands [27] and LBP (see Fig. 12) due to, we believe,                    3.3. Feature alignment algorithm
a superior false alarm representation.
   We extracted MFCCs features from a 2 s window                           One of the most challenging parts of developing our
located around the potential fall. The window size                      fall recognition system was developing a radar signa-
is selected from the exhaustive searching of window                     ture library. Although the ground truth has been ob-
size in [0.5 s, 6 s] with 0.5 s interval on floor radar                 served by the depth camera monitoring system, there
dataset. Each 2 s window is considered as an input sig-                 may be some uncertainty in the fall timing due to the
nal frame, which needs to be divided into sub-frames                    fall type, direction and the clock difference between
to extract features. If the signal sampling frequency is                the PC and DataQ logger. In fact, it is hard to tell just
960 Hz, an input signal frame has 2×960 samples. The                    by looking at a radar signature if it comes from a fall or
sub-frame in each frame has a size of 256 samples with                  not (see Fig. 3). To alleviate the effect of the fall timing
an overlap of 11.72% to each other. So the total num-                   in the 2 s window, we propose to apply a feature align-
ber of sub-frames in an input signal frame is computed                  ment procedure (somewhat similar to the ones used
with L = (960 × 2 − 256)/(256 × 11.72%) = 55.                         in bioinformatics [19]) for the entire training dataset.
For each sub-frame, we choose (see Section 5.1) to                      This will ensure the presence of fewer outliers in the
compute N = 7 cepstral coefficients. Therefore, the                     training data and more compact fall and non-fall clus-
feature matrix for the i-th signal window is given by:                  ters in the feature space.
           ⎡                        ⎤                                      The feature vectors were aligned such that their cor-
           C1,1        ···    C1,55                                     relation is maximized. For two feature vectors v1 and
          ⎢ ..
     Ci = ⎣ .          ..       .. ⎥ .                                  v2 , we compute their correlation as:
                          .      . ⎦                        (6)
               CN,1    ···    CN,55
                                                                        corrv1 ,v2 (d)
   After ignoring the first coefficient (DC term) in each                                 P
                                                                                          i=1 (v1 (i) − v1 )(v2 (i − d) − v2 )
sub-frame, we obtain a feature vector with the dimen-                       =                                                           ,
                                                                                      P                       P
sion of 55 × 6 = 330 by concatenating the columns of                                  i=1 (v1 (i) − v1 )      i=1 (v2 (i − d) − v2 )
                                                                                                        2                           2

the above matrix, C i . Typical fall and non-fall feature                                                                             (7)
458                    L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures


where P = 330 is the dimension, and vk (k = 1, 2) are                  Algorithm 1 Feature shifting algorithm
the means of the feature vectors. The above corrv1 ,v2 is              Input: A fall signature library with Mf fall and Mnf
computed at all shifts d = 1, . . . , P . The total amount               non-fall feature vectors;
of shift or lag τ required to align v2 to v1 is the one                Align strategy: “zero-padding”, “4 s window”
that maximizes the correlation between v1 and v2 . It is               Output: Aligned version of the signature library
defined as:                                                              {vi∗ }i=1,...,Mf +Mnf

      τ = argmax(corrv1 ,v2 (d)).                          (8)            For i ∈ [1, . . . , Mf ]
              d                                                              Choose vi as reference
                                                                             For j in {{1, . . . , Mf + Mnf }\i}
   We tried two alignment strategies: a simple one                               – Compute shift τj (formula 8) require to align
based on zero padding and a more complicated one                                   vj to vi
based on search in a larger feature window. The zero-                            – Shift vj to vj∗ using the chosen alignment
padding strategy consisted of shifting v2 by τ index                               strategy
and padding the remaining places in the 2 s window                               – Use a classifier to compute AUCi (Eq. 9) for
with zeros. For example, if we shift v2 to the right by                            vi
τ locations, we set v2 (1) = 0, . . . , v2 (τ ) = 0 and                      End
discard v2 (P − τ + 1) . . . v2 (P ). A bigger window,                    End
4 s in our case, allowed us to avoid zero-padding and                     Choose iopt = argmaxi {AUCi } and related library
feature discarding at the expense of more computation                     {vi∗ }i=1,...,Mf +Mnf
time. All feature vectors v2 in the library were aligned
to a single fall vector vi chosen such that the result-
                                                                       (see Fig. 11). The fall detection algorithm used for ex-
ing classifier had the best overall performance. The
                                                                       periments on a signature library is summarized in Al-
reference fall feature vector was found by exhaustive
                                                                       gorithm 2 below.
search. For a dataset with Mf falls and Mnf non-falls,
                                                                          The online classification procedure used for contin-
the i-th vector from Mf falls is the reference to align-
                                                                       uous data was similar to Algorithm 2 except for three
ment the rest Mf + Mnf − 1 feature vectors. We calcu-
                                                                       details. First, a sliding 2 s window with a 0.5 over-
lated an area under the receiver operating characteris-
                                                                       lap rate was employed in step 1 above. Second, a 4 s
tic curve (AUC, defined in Section 4.2 and Eq. (9)) for
                                                                       buffer was available to perform the feature alignment
each aligned dataset. The reference vector is the one
                                                                       procedure. Third, to reduce the number of false alarms,
that generates the largest AUC. The feature shifting al-
                                                                       we used an energy threshold e to decide if steps 1–7
gorithm was summarized in Algorithm 1.                                 from Algorithm 2 will be performed or not. If the en-
                                                                                                                   −1
                                                                       ergy of the signal in window i, Ei = N               2
                                                                                                                  n=0 xi (n) , is
3.4. Classifiers                                                       smaller than e we label the window as a non-fall (i.e.
                                                                       fall confidenceValue = 0). The classifier used for the
   Support vector machines (SVM) are a popular clas-                   online classification procedure was trained on the lab-
sification method for two class problems. We em-                       oratory floor signature library (all the radars in Tiger-
ployed LibSVM implementation for both training and                     Place were placed on the floor at the time of this data
testing steps [1,2]. We used a linear kernel SVM for                   collection).
computational efficiency.
   The classifiers were first trained and tested on signa-
ture libraries (ceiling and floor) obtained in our labo-               4. Data collection and criteria of performance
ratory using a leave-one-out cross validation approach.                   evaluation
Then, we used the classifiers trained on the laboratory
signature to classify the continuous data obtained in                  4.1. Data collection
the TigerPlace apartments. We also used a set of clas-
sifiers trained on the stunt actor falls obtained in Tiger-              The fall/non-fall activities were performed by stunt
Place to test the influence of the environment in the                  actors in both our laboratory and the senior apartments.
training process. This aspect is important for the real                Our nursing collaborators trained stunt actors using
life application since we would like to avoid training                 21 fall types at the University of Missouri to fall in
the system for each apartment and person, if possible                  ways similar to older adults [30]. In our laboratory,
                      L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures                      459

                                                                                                     Table 1
Algorithm 2 Fall detection algorithm
                                                                                        Stunt actor profile in DATA_lab
Input:
  A set {xi } of radar signal segments with Mf fall and               Subject#        Gender        Age           Height   Weight (Lbs)
  Mnf non-falls;                                                      1               female         32            5’3”        135
  Window size winSize = 2 s;                                          2               female         46            5’4”        117
  Signal sampling frequency fs;                                       3               male           30            5’8”        170
  Classifier classifierType;
Output:                                                               collection, the floor mat was placed in the center of
  A fall signature library {vi }i=1,...,Mf +Mnf ;                     room and directly under the ceiling RCR. The stunt ac-
  A trained classifier.                                               tors performed 21 types of falls in the following five
  ROC and AUC (defined in Section 4.2)                                categories: a) lose balance – forward, backwards, left,
                                                                      right; b) lose consciousness – forward, backwards, left,
– Compute the feature vectors {vi }i=1,...,Mf +Mnf as:
                                                                      right, crumple; c) trip & fall – forwards, sideways, for-
  For each signal segment xi , i ∈ [1, Mf + Mnf ]
                                                                      wards, sideways, backwards; d) reach & fall on chair –
     1. Compute the STFT of xi (formula 1), STFT i
                                                                      forwards, left, right, forwards, backwards; e) fall from
     2. Compute spectrogram of STFTi (formula 3),
                                                                      couch – upper body first, hips first. Each fall type is
         spectogrami
                                                                      repeated 5 times to generate 105 falls. We extracted 8
     3. Compute the energy burst of spectrogrami
                                                                      types of non-fall activities from 5 daily scenarios in-
         (formula 4), EBi
                                                                      cluding 383 non-fall activities: walk, turn around, sit
     4. Smooth energy burst EBi (formula 5), EBi
                                                                      down, stand up, body sway, bend over, stretch arms,
     5. Find the maximum location tmax of EBi
                                                                      and step over. We had three different stunt actors dur-
     Extract MFCC features vi in a window of size
                                                                      ing our data collection in order to capture some vari-
     winSize around tmax
                                                                      ance in body size as shown in Table 1. Each event was
  End
                                                                      captured by both of the ceiling and the floor RCR.
  6. Perform feature alignment
                                                                         DATA_Apt1 was collected in six senior apartments
  7. Use leave-one-out cross validation and clas-
                                                                      similar to the one shown in Fig. 9 using radars placed
  sifierType to compute fall confidence values
                                                                      on the floor. The size of the living room was 5.8 m ×
  confidenceValuei for each vi in {vi }
                                                                      3.6 m × 2.7 m. The height of the laboratory room
  8. Compute ROC and AUC (Eq. (9)) by threshold-
                                                                      (3.5 m) is about 30% higher than the typical liv-
  ing {confidenceValuei }
                                                                      ing room in a senior apartment, which resulted in
                                                                      a different coverage range for the ceiling RCR be-
aside from elderly falls, the stunt actors performed                  tween the two settings. As we explained later, that
other possible activities of daily living in an indepen-              impacted the performance of the ceiling radar in
dent living facility, such as walking, picking objects                the senior apartments. DATA_Apt1 had three parts:
from the floor, sitting and standing [3] which might                  DATA_Apt1_s and DATA_Apt1_s_b collected from
generate false alarms. While stunt actor falls were still             stunt actors, and DATA_Apt1_r collected from res-
used in TigerPlace, we obtained a large amount of                     idents. DATA_Apt1_s consisted of 20 falls and 16
data (mostly normal daily activities) from the Tiger-                 non-falls from the stunt actors in the living room.
Place residents themselves. While a variety of activi-                DATA_Apt1_s_b contained 72 falls and 98 non-falls
ties were recorded in the apartment, no real falls were               from the stunt actors in the bathroom during five
observed during the two weeks period of the data col-                 months. We were limited to a small number of falls
lection. Note that our project had University of Mis-                 in order to minimize the test time in the resident’s
souri Institutional Review Board approval and written                 apartment. The fall/non-fall types were similar to
consents from all senior apartment residents involved                 the 21 types of falls performed in the laboratory.
in data collection. In this paper, we used three datasets             DATA_Apt1_r was collected from six residents dur-
denoted as DATA_Lab, DATA_Apt1 and DATA_Apt2,                         ing two weeks. No natural falls by residents occurred
respectively.                                                         during that time. The mix of stunt actor and resident
   DATA_Lab was generated in a 9 m × 8 m × 3.5                        data was necessary for algorithm evaluation since we
m room situated in our laboratory (see Fig. 8). One                   expected a low number of natural falls.
radar sensor (RCR) was placed on the floor and an-                       DATA_Apt2 was collected in an apartment of a
other on the ceiling (denoted by triangles). For the data             frequent faller. During one week, the resident fell 6
460                      L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures




          Fig. 8. Lab environment. RCR 1 is on floor and RCR 2 is on ceiling. (a) Front camera view. (b) Right side camera view.




      Fig. 9. Senior apartment in TP. RCR 1 is on the floor and RCR 2 is in the attic. (a) Left side camera view. (b) Front camera view.

times. The radar placement was in the attic above                             We mention that in the case of continuous radar
the ceiling. This dataset is important for assessing                       data (DATA_Apt1_r and DATA_Apt2) the number of
if we can detect non-actor falls and will answer the                       events that can lead to false alarms is unknown. In this
question if our algorithm training is adequate for de-                     case we report the number of detected false positives
tecting falls of persons not included in the training                      (false alarms) per unit time (hour). Since this is not a
data.                                                                      traditional ROC, we will call it a “pseudo ROC”. In our
                                                                           opinion, this pseudo ROC is more suitable for evaluat-
4.2. Performance evaluation                                                ing online algorithms that run in real settings. Report-
                                                                           ing the number of false alarms per hour instead of the
   We used a receiver operating characteristic (ROC)                       false alarm rate, allows the clinical personnel to more
curve to evaluate the performance of the classifier in                     easily evaluate and understand the fall detection sys-
the fall detection algorithm. The ROC is obtained by                       tem.
thresholding the fall confidence (a number between
0 and 1) generated by the classifier with a series of
n thresholds, Ti ∈ [0, 1], i = 1, . . . , n. For each                      5. Experimental results
threshold Ti we obtain a true positive rate (TPRi ),
                                                                              In this section we present the results of several ex-
and false positive rate (FPRi ) pair. Then, the area
                                                                           periments designed to answer the following questions:
under the ROC curve (AUC) can be calculated us-                            (1) Is feature alignment useful? (2) What is the best
ing:                                                                       position of the radar sensor (floor/ceiling)? (3) What is
                                                                           the performance of a radar fall detection system in real
        
        n
          (TPRi + TPRi−1 )(FPRi − FPRi−1 )
AUC =                                                      . (9)           settings? (4) Is this performance different from the one
                                    2                                      observed in the laboratory? Why?
         i=2
                           L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures                       461




                                                                               Fig. 11. Fall detection in lab environment with DATA_Lab.

Fig. 10. Fall detection performance for three feature alignment op-
tions: no alignment, zero-padding, and 4 s window, with the variable       5.2. Influence of the radar position on detection
number of MFCC features, respectively.                                          performance

                                                                              To determine which radar position leads to better
5.1. Influence of feature alignment on classification                      fall detection performance, we first used our laboratory
                                                                           data, DATA_Lab, and then the stunt actor part of the
    This paper used a window based approach for fea-                       TigerPlace data, DATA_Apt1_s.
ture alignment. The size of the window is chosen and
compared to other known windows using features. Al-                        5.2.1. Fall detection in the laboratory setting
though a segmentation based approach might be better,                         The ROC curves obtained for two radar positions
it requires a good segmentation process and a dynamic                      using a SVM classifier with DATA_Lab are given in
time warping method for alignment with a variable sig-                     Fig. 11. From Fig. 11, we see that the ceiling RCR
nal window. One of the greatest problems for the seg-                      generates a larger AUC value. In addition, the ceiling
mentation based approach would be that it is not easy                      RCR detects all the falls with only 20% false positive
to produce the ground truth for Doppler signal seg-                        rate, which is better than the floor RCR. Clearly, plac-
mentation. So the window based approach is chosen                          ing the radar on the ceiling produced better results than
to investigate the effect of feature alignment. We used                    placing it on the floor.
the data collected in our laboratory, DATA_Lab (only                       5.2.2. Fall detection in apartment setting
the floor RCR), and ran multiple classification exper-                        We conducted similar experiments using stunt ac-
iments with different numbers of MFCC coefficients                         tor data collected in TigerPlace, DATA_Apt1_s and
for three cases: unaligned features, aligned using zero                    DATA_Apt1_s_b.
padding, and aligned using a 4 s window (see Fig. 10).                        The features were validated on DATA_Apt1_s_b,
We used a classifier and AUC to quantify the algorithm                     which has a clean signal background and full cover-
performance for each case. As expected, both feature                       age to the room because of the limited space and furni-
alignment procedures resulted in better classification                     ture in the bathroom. For comparison, the performance
performances than the unaligned case: zero-padding                         of the LBP features [40] (AUC = 0.79) is about 20%
by about 3% and 4 s window by about 6%. The in-                            worse than MFCC (AUC = 0.98) on the ceiling data
crease in performance was independent of the num-                          collected in TigerPlace bathroom in Fig. 12.
ber of MFCC coefficients employed. However, the best                          To test if a classifier trained in the laboratory can be
classification performance was observed in all three                       used in real settings, we performed two sets of exper-
cases for N = 7 cepstral coefficients number, which is                     iments, as shown in Fig. 13: we tested DATA_Apt1_s
used throughout all our experiments. For later applica-                    with classifiers trained on DATA_Apt1_s (circles), and
tion, we use SVM to avoid the possible over-fitting due                    with classifiers trained on DATA_Lab (triangles). As
to the small training data size from real senior apart-                    we can see from Fig. 13, the loss in performance is
ment.                                                                      only of about 2–3% between the two classifiers. This
462                        L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures




Fig. 12. Performance comparison between different features: LBP
and MFCC features on the ceiling data collected in TigerPlace bath-        Fig. 14. Fall detection and false alarm of floor RCR with two weeks
room.                                                                      senior apartment data in 6 different TigerPlace apartments.

                                                                           cation required) but may not be accessible for some
                                                                           homes (such as apartment buildings).

                                                                           5.3. Results obtained on DATA_Apt1_r

                                                                              We used the fall detection algorithms described
                                                                           above, trained on DATA_Lab and DATA_Apt, to detect
                                                                           falls in the two weeks of data collected in 6 TigerPlace
                                                                           apartments using floor RCRs. We centered our data
                                                                           collection on the day that the stunt actor performed 12
                                                                           falls in each apartment near the floor radar, to make
                                                                           sure that our data included enough falls. Details about
                                                                           the detection algorithm used in this experiment are
                                                                           given in Algorithm 2 and its performance is shown
                                                                           in Fig. 14. For two apartments (1 and 4) we obtained
Fig. 13. Fall detection in senior apartment environment with               100% detection with about 2 false alarms per week
DATA_Apt1_s by using different training datasets, DATA_Lab and
                                                                           (0.015 FA/hour). This proves that a Doppler radar can
DATA_Apt1_s, respectively.
                                                                           be used for fall detection. However, in two other apart-
                                                                           ments (5 and 6) the number of false alarms was greater
finding has important implications for the development                     than 1 FA/hour at 100% detection, which is clearly in-
of an online fall detection system. Immediately after                      acceptable.
deployment time, we can use a classifier trained in the
laboratory that will later be improved using some on-                      5.4. Results obtained on DATA_Apt2
line adaptive training strategy.
   From Fig. 13 we also see that the performance of                           In Fig. 15, we show the results on DATA_Apt2. A 75
both RCRs decreased in the real setting due to vari-                       years old resident lives alone in this apartment and she
ous factors such as lower ceilings, apartment clutter                      is a frequent faller. The data contains 6 natural falls
and motion interference from other people present in                       during the one week long data collection.
the apartment. However, the results from Fig. 13 con-                         As we see from Fig. 15, the Doppler radar system is
firm that the best placement of the radar is on the ceil-                  able to detect all the real senior falls but with a signifi-
ing. We note that the actual RCR position in the Tiger-                    cant number of false alarms. So this answers the ques-
Place apartment was above the ceiling (in the attic)                       tion if we can identify falls from persons that were not
which on one hand was clean (no apartment modifi-                          included in the training dataset. To further reduce the
                        L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures            463


                                                                        placed on the detector in order to prevent secondary re-
                                                                        flections to reach the antenna [10]. The size and place-
                                                                        ment of the shielding were not identical among the six
                                                                        apartments, being a possible source of the variability
                                                                        observed in Fig. 14.
                                                                           In Table 2 we show an analysis of the false alarms
                                                                        detected by our algorithm in all six apartments. We
                                                                        chose the false alarms with fall confidence greater
                                                                        than 0.5 for apartments 1–4, and 0.95 for apartments
                                                                        5 and 6. The false alarms were identified based on
                                                                        the Kinect depth images and classified into six cate-
                                                                        gories: bend over or pick up an object, drop things on
                                                                        floor/chair, sitting or standing, running or fast walk-
                                                                        ing, leave/enter the room and other. Figure 16 uses the
                                                                        raw signal waveform, spectrogram and energy burst
           Fig. 15. Result obtained for DATA_Apt2.                      curve to present the patterns for eight daily activities.
                                                                        Those activities in Figs 6(a)–(g) represent the most
false alarms, we can use a fusion approach with other                   common false positives in a daily living environment.
sensors such as motion detectors. Using the depth cam-                  Figure 6(h) shows the occurrence of a fall.
eras installed in the apartment (i.e. Microsoft Kinect)                    Another possible explanation for the variability ob-
we were able to determine which activities produced                     served in Fig. 14 is the number of people and visitors in
false alarms. Among the most frequent false alarm                       the apartments. For example, apartment 5 has a couple
sources we mention a big cat (around 4 kg) jumping                      living in it, rather than just one person. The residents
on/off the chairs/couch and visits by the nursing staff                 like to spend a lot of time in the living room and have
and other visitors that come to help the resident multi-                many visitors. The fast runs observed in apartment 5
ple times every day in his apartment. All those activi-                 are due to kids running and sitting on the floor. In
ties contribute to a high false alarm rate during this one              apartment 6, the female resident has severe osteoarthri-
week data collection. However, in the meantime, our                     tis, and she uses an aluminum walker during walk-
motion detectors are pet-insensitive and we should be                   ing. It is possible that the reflections caused by the
able to tell if the activity is performed by the resident or            walker resulted in the extra false alarms. Moreover, a
by the cat [23]. Moreover, our Kinect based gait detec-                 physical therapist and nursing staff visit her apartment
tion system is able to identify the resident in the room                frequently leading to more false alarms. Pets are also
based on his gait [35]. Using the radar in conjunc-                     a problem for our current system. The “other” false
tion with other sensors (such as motion sensors [23] or                 alarms (see Table 2) observed in apartment 4 are due
Kinect [35]) can further reduce the false alarm rate.                   to a dog jumping up/down from the couch.
                                                                           The radar position on the floor is another source of
                                                                        variability. The floor radars are by the front door in
6. Discussions                                                          the first two apartments being prone to detect walks
                                                                        in/out of the apartment. In apartment 4, the floor radar
   We showed in Section 5.2 that the ceiling is the best                is in the bedroom and pointing toward the living room.
position for RCR to detect fall. However, since our                     This could lead to various false alarms (“other” in Ta-
work was part of a parent study that comprises both fall                ble 2) caused by sudden turns or entering the bedroom.
risk assessment and fall detection, the team decided to                 In the apartments 5 and 6, the radar is put beside the
focus on prevention using gait assessment, which re-                    counter which is close to the center of the livingroom.
quires radars on the floor for a higher accuracy. Since                 This placement captures more visitor activity than the
the parent study has ended, we are in the process of                    bedroom placement.
moving all our floor radar on the ceiling to collect more
data for fall detection.                                                7. Conclusions
   The use of the floor RCR for gait detection had an-
other implication on fall detection. To optimize gait de-                 In this paper, we describe a fall detection system
tection, a thin aluminum foil shielding with a slit was                 based on a Doppler radar sensor in senior homes. This
464                          L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures

                                                                       Table 2
                                                  False alarms from two weeks data in each apartment
Apt                                                                   False alarm                                                                   Total
              bend over/pick up            drop           sit/stand          run/fast walk            walk in/out of door           other
1                      0                     0                0                     0                          5                      0               5
2                      2                     2                1                     0                          6                      4              15
3                      6                     0                1                     0                          0                      1               8
4                      0                     1                1                     1                          0                      6               9
5                      2                     1                5                    19                          0                      3              30
6                      5                     1                2                     8                          2                      5              23




Fig. 16. Motions for different daily activities: (a) sit down on floor with butt on floor first and keep both leg straight in front; (b) cross leg and sit
down on floor; (c) lay down on floor; (d) sit down on a chair; (e) kneel down on floor; (f) drop a book on floor, bend over and squat down to pick
it; (g) walking; (h) fall. The y-axis units are voltage (V), frequency (Hz) and squared-voltage (v2 ) for the raw signal, spectrogram and energy
burst, respectively. The x-axis unit is time in second.

system can differentiate a fall from daily non-fall activ-                       cients, feature alignment and radar position. We found
ities based on MFCC features extracted from the radar                            that using 7 MFCC coefficients, feature alignment and
signal using a SVM classifier. We first deployed the                             ceiling positioning leads to the best performance.
system in a simulated home-like laboratory environ-                                 Then, we deployed the system in six apartments
ment and investigated classification performance for                             in TigerPlace, an aging in place facility in Columbia,
various variables such as the number of MFCC coeffi-                             MO. The results obtained in TigerPlace varied from
                           L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures                        465


about 2 false alarms/week to about 4 false alarms/hour                          M. Skubic and M. Rantz, Radar walking speed measurements
at 100% detection rate. After analyzing the false                               of seniors in their apartments: Technology for fall prevention,
                                                                                in: Proc. of 34th EMBS, San Diego, CA, Aug. 28–Sep. 1, 2012,
alarms, we concluded that the variability of the results
                                                                                pp. 260–263.
was due to factors such as radar construction and posi-                    [11] C. Garripoli, M. Mercuri, P. Karsmakers, P.J. Soh, G. Crupi,
tioning, number of people in the room (resident or visi-                        G. Vandenbosch, C. Pace, P. Leroux and D. Schreurs, Embed-
tors), pets and walkers. Moreover, the proposed system                          ded DSP-based telehealth radar system for remote in-door fall
effectively detected all six natural falls in a continuous                      detection, IEEE Journal of Biomedical and Health Informatics
                                                                                19(1) (Jan. 2015), 92–101. doi:10.1109/JBHI.2014.2361252.
one week data from an apartment where a senior faller
                                                                           [12] J.L. Geisheimer, W.S. Marshall and E. Greneker,
is living there.                                                                A continuous-wave (CW) radar for gait analysis, in: The 35th
   In future work, we will try to address the variabil-                         Asilomar Conf. on Signals, Systems and Computers, Vol. 1,
ity of results by developing algorithms more robust to                          Nov. 2001, pp. 834–838.
visitors, pets and interferences. We are currently de-                     [13] D. Giansanti, G. Maccioni and V. Macellari, The develop-
                                                                                ment and test of a device for the reconstruction of 3D position
ploying Doppler radars on the ceiling of ten TigerPlace
                                                                                and orientation by means of a kinematic sensor assembly with
apartments in order to further confirm the results pre-                         rate gyroscopes and accelerometers, IEEE Trans. Biomed. Eng.
sented in this paper.                                                           52(7) (2005), 1271–1277. doi:10.1109/TBME.2005.847404.
                                                                           [14] S. Gupta, D. Morris, S. Patel and D. Tan, Soundwave: Using
                                                                                the Doppler effect to sense gestures, in: Proc. of the SIGCHI
                                                                                Conference on Human Factors in Computing Systems, 2012,
Acknowledgement                                                                 pp. 1911–1914.
                                                                           [15] R.J. Gurley, N. Lum, M. Sande, B. Lo and M.H. Katz,
  This paper was funded by the AHRQ grant                                       Persons found in their homes helpless or dead, N. Engl.
5R01HS018477.                                                                   J. Med. 334(26) (Jun. 27, 1996), 1710–1716. doi:10.1056/
                                                                                NEJM199606273342606.
                                                                           [16] E.J. Hughes and M. Lewis, The application of speech recog-
                                                                                nition techniques to radar target Doppler recognition: A case
References                                                                      study, in: The Institution of Engineering and Technology Sem-
                                                                                inar on High Resolution Imaging and Target Classification,
 [1] http://neural.cs.nthu.edu.tw/jang/books/audioSignalProcessing/             Nov. 21–21, 2006, pp. 145–152. doi:10.1049/ic:20060082.
     speechFeatureMfcc.asp?title=12-2MFCC.                                 [17] Y. Kim and H. Ling, Human activity classification based
 [2] http://www.csie.ntu.edu.tw/~cjlin/libsvm/.                                 on micro-Doppler signatures using a Support Vector Ma-
 [3] http://www.americareusa.net/independent_living/columbia_                   chine, IEEE Transactions on Geoscience and Remote Sens-
     mo/zip_65201/americare/1335.html.                                          ing 47(5) (May 2009), 1328–1337. doi:10.1109/TGRS.2009.
 [4] M. Addlesee, A. Jones, F. Livesey and F. Samaria, The ORL                  2012849.
     active floor, IEEE Personal Communications 4 (1997), 35–41.           [18] Y. Li, K.C. Ho and M. Popescu, A microphone array system
     doi:10.1109/98.626980.                                                     for automatic fall detection, IEEE Transactions on Biomedical
 [5] M. Alwan, P.J. Rajendran, S. Kell, D. Mack, S. Dalal, M. Wolfe             Engineering 59(2) (May 2012), 1291–1301.
     and R. Felder, A smart and passive floor-vibration based fall         [19] D.J. Lipman, S.F. Altschul and J.D. Kececioglu, A tool for
     detector for elderly, in: 2nd IEEE Int. Conf. on Inf. & Comm.              multiple sequence alignment, Proc. Natl. Acad. Sci. USA
     Tech., Damascus, Syria, Apr. 24–28, Vol. 1, 2006, pp. 1003–                86(12) (1989), 4412–4415. doi:10.1073/pnas.86.12.4412.
     1007.                                                                 [20] L. Liu, M. Popescu, M. Rantz and M. Skubic, Doppler radar
 [6] D. Anderson, R.H. Luke, J. Keller, M. Skubic, M. Rantz and                 sensor positioning in a fall detection system, in: Proc. of 34th
     M. Aud, Linguistic summarization of activities from video for              EMBS, San Diego, Aug. 28–Sep. 1, 2012, pp. 256–259.
     fall detection using voxel person and fuzzy logic, Computer           [21] L. Liu, M. Popescu, M. Rantz and M. Skubic, Fall detection
     Vision and Image Understanding 113(1) (Jan. 2009), 80–89.                  using Doppler radar and classifier fusion, in: Proc. of EMBS on
     doi:10.1016/j.cviu.2008.07.006.                                            BHI, Shenzhen, Jan. 2–7, 2012, pp. 180–183.
 [7] J.C. Augusto, H. Nakashima and H. Aghajan, Ambient intelli-           [22] L. Liu, M. Popescu, M. Rantz, M. Skubic, T. Yardibi and
     gence and smart environments: A state of the art, in: The Hand-            P. Cuddihy, Automatic fall detection based on Doppler radar
     book of Ambient Intelligence and Smart Environments, 2010,                 motion, in: Proc. of 5th International Conference on Pervasive
     pp. 3–31. doi:10.1007/978-0-387-93808-0_1.                                 Computing Technologies for Healthcare, Dublin, Ireland, May
 [8] A.J. Carlos and M. Paul, Ambient intelligence: Concepts and                23–26, 2011, pp. 222–225.
     applications, Computer Science and Information Systems 4              [23] L. Liu, M. Popescu, M. Skubic and M. Rantz, An automatic
     (2007), 1–26. doi:10.2298/CSIS0701001A.                                    fall detection framework using data fusion of Doppler radar
 [9] F. Castanedo, D. Lopez-de-Ipina, H. Aghajan and R. Klei-                   and motion sensor network, in: Proc. of 36th EMBS, Chicago,
     horst, Learning routines over long-term sensor data using topic            Aug. 26–30, 2014, pp. 5940–5943.
     models, Expert Systems Journal 31(4) (Sep. 2014), 365–377.            [24] C.G. Moran, R.T. Wenn, M. Sikand and A.M. Taylor, Early
     doi:10.1111/exsy.12033.                                                    mortality after hip fracture: Is delay before surgery impor-
[10] P.E. Cuddihy, T. Yardibi, Z.J. Legenzoff, L. Liu, C.E. Phillips,           tant, J. of Bone and Joint Surgery 87(3) (Mar. 2005), 483–489.
     C. Abbott, C. Galambos, J. Keller, M. Popescu, J. Back,                    doi:10.2106/JBJS.D.01796.
466                        L. Liu et al. / An automatic in-home fall detection system using Doppler radar signatures


[25] S.L. Murhy, Deaths: Final data for 1998, National Vital Statis-            J. Phys. IV France 128 (2005), 153–160. doi:10.1051/jp4:
     tics Reports 48(11) (July 24, 2000), 1–105.                                2005128024.
[26] N. Noury, A. Fleury, P. Rumeau, A.K. Bourke, G.O. Laighin,            [34] J.A. Stevens, Fatalities and injuries from falls among older
     V. Rialle and J.E. Lundy, Fall detection-principles and meth-              adults – United States, 1993–2003 and 2001–2005, MMWR
     ods, in: Proc. of the 29th IEEE EMBS, Lyon, France, Aug. 23–               55(45) (Nov. 17, 2006), 1221–1224.
     26, 2007, pp. 1663–1666.                                              [35] E. Stone and M. Skubic, Unobtrusive, continuous, in-home
[27] M. Popescu and S. Coupland, A fuzzy logic system for fall                  gait measurement using the Microsoft kinect, IEEE Transac-
     detection, in: AAAI Fall Symposium, Washington, DC, Nov. 7–                tions on Biomedical Engineering 60(10) (2013), 2925–2932.
     9, 2008, pp. 78–83.                                                        doi:10.1109/TBME.2013.2266341.
[28] M. Popescu, Y. Li, M. Skubic and M. Rantz, An acoustic fall           [36] L. Tessens, M. Morbee, H. Aghajan and W. Philips, Camera
     detector system that uses sound height information to reduce               selection for tracking in distributed smart camera networks,
     the false alarm rate, in: 30th Int. IEEE EMBS Conf, Vancouver,             ACM Transactions on Sensor Networks 10(2) (Jan. 2014),
     BC, Aug. 20–24, 2008, pp. 4628–4631.                                       23:1–33.
[29] C. Ramos, J.C. Augusto and D. Shapiro, Ambient intelli-               [37] Q. Wu, Y.D. Zhang, W. Tao and M.G. Amin, Radar-based fall
     gence – The next step for artificial intelligence, IEEE Intelli-           detection based on Doppler time-frequency signatures for as-
     gent Systems 23 (2008), 15–18. doi:10.1109/MIS.2008.19.                    sisted living, IET Radar, Sonar & Navigation 9(2) (Feb. 2015),
[30] M. Rantz, M. Aud, G. Alexander, B. Wakefield, M. Skubic,                   164–172. doi:10.1049/iet-rsn.2014.0250.
     R.H. Luke, D. Anderson and J. Keller, Falls, technology, and          [38] T. Yardibi, P. Cuddihy, S. Genc, C. Bufi, M. Skubic, M. Rantz,
     stunt actors: New approaches to fall detection and fall risk as-           L. Liu and C. Phillips, Gait characterization via pulse-Doppler
     sessment, Journal of Nursing Care Quality 23(3) (2008), 195–               radar, in: IEEE International Conference on Pervasive Com-
     201. doi:10.1097/01.NCQ.0000324581.59557.42.                               puting and Communications Workshops (PERCOM Work-
[31] M. Rantz, K. Marek, M. Aud, R. Johnson, D. Otto and                        shops), Mar. 21–25, 2011, 662–667.
     R. Porter, TigerPlace: A new future for older adults, Jour-           [39] A. Yazar, F. Keskin, B.U. Toreyin and A.E. Cetin, Fall de-
     nal of Nursing Care Quality 20(1) (Jan.–Mar. 2005), 1–4. doi:              tection using single-tree complex wavelet transform, Pat-
     10.1097/00001786-200501000-00001.                                          tern Recognition Letters 34(15) (Nov. 2013), 1945–1952.
[32] J. Sachs and R. Hermann, M-sequence-based ultra-wideband                   doi:10.1016/j.patrec.2012.12.010.
     sensor network for vitality monitoring of elders at home, IET         [40] Q. Zhu, N. Chatlani and J.J. Soraghan, 1-D local binary pat-
     Radar, Sonar & Navigation 9(2) (Feb. 2015), 125–137. doi:                  terns based VAD used INHMM-based improved speech recog-
     10.1049/iet-rsn.2014.0214.                                                 nition, in: Proc. of the 20th European Signal Processing Con-
[33] A. Sixsmith, N. Johnson and R. Whatmore, Pyrolytic IR                      ference (EUSIPCO), Aug. 27–31, 2012, pp. 1633–1637.
     sensor arrays for fall detection in the older population,

