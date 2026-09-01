                    INDOOR FALL DETECTOR BASED ON DOPPLER RADAR
                         1               2                 2,3          2            1            2,3                     2
              C. Garripoli , M. Mercuri , P. Karsmakers , P.J. Soh , C. Pace , P. Leroux                and D. Schreurs
                                     1
                                      Università della Calabria, DIMES, Cosenza, Italy
                                             2
                                             KU Leuven, ESAT, Leuven, Belgium
                                             3
                                                 KU Leuven, AdvlSe, Geel, Belgium
                                   +32(0)16/32.18.20, garripoli.carmine@gmail.com


Abstract                                                          3 Experimental results
A smart fall detector based on a Doppler radar is                 A training set containing 90 activities measured
presented aiming at non-invasive fall detector in                 from a single person is used to estimate a fall
home environment. A Continuous Wave (CW)                          classification model. It was built dividing the
signal is used to assess the changes in speed of                  activities in two main groups, namely fall events
different persons observed during daily activities                and normal movements. The model has been
which include: falling, walking, sitting down,                    tested on 20 signals containing multiple activities
standing up, random movement, and no                              acquired on three different test persons. A sliding
movement. The speed measurements are                              window of 2 s with 95% overlapping is used to
introduced in a machine learning methodology to                   process the signals.
estimate a generic model that discriminates fall                  Fig. 1 shows the classification result of a fall
events from normal movements.                                     event implementing the algorithm both in Matlab
Keywords:      Fall    detection  –    movement                   (Fig. 1a) and with the DSP (Fig. 1b). The
classification – radar remote sensing.                            experimental results equal in both cases and the
                                                                  event was classified as fall for eight consecutive
1 Introduction                                                    windows of signal.
                                                                  The experimental evaluations have shown a
Fall incidents represent the second leading                       success rate in detecting fall events of 95%
cause of injury for elderly people (60 years and                  without reporting false positives.
older) [1]. A fall incident that occurs when a
person is home alone might cause he/she to lay
down for hours before help arrives.
In contrast to current wearable solutions (e.g.,
device with a button, accelerometers), non-
invasive fall detection offers the main advantage
that no action by the person is required.

## 2 Fall detector
A single tone at 5.8 GHz is used to detect the                                                  (a)                         (b)
speed signals produced by different persons                       Fig. 1 – Classification results during a fall event implementing
                                                                  the algorithm both (a) in Matlab and (b) with the DSP. The
during daily activities (i.e., falling, walking, sitting          fall is labeled as “1” while the normal movement as “2”. Each
down, standing up, random movement, no                            dot in (a) indicates the class where a window of 2 s of signal
movement) exploiting the Doppler effect [2]. A                    has been assigned, and corresponds to the n-th position of
movement classification based on a Least                          the vector x in (b).
Squares Support Vector Machines (LS-SVM)
framework combined with Global Alignment (GA)                     References
kernel [3] is applied to discriminate fall event                  [1]       S. R. Lord, C. Sherrington, and H. B. Menz, “Falls in
speed signals from all other speed signals. As                              Older People: Risk Factors and Strategies for
                                                                            Prevention,” Cambridge, U.K., Cambridge Univ. Press,
opposed to [3], where the technique is applied to                           2007.
classify signals consisting of one single activity                [2]       M. Mercuri, P. J. Soh, G. Pandey, P. Karsmakers, G. A.
whose starting and ending points are known, a                               E. Vandenbosch, P. Leroux, and D. Schreurs, “Analysis
sliding window is introduced to process signals                             of an indoor biomedical radar-based system for health
                                                                            monitoring,” IEEE Trans. Microwave Theory Tech., vol.
consisting of multiple activities.                                          61, no. 5, pp. 2061-2068, May 2013.
The LS-SVM classification model has been                          [3]       P. Karsmakers, T. Croonenborghs, M. Mercuri, D.
implemented using a TMDSEVM6678 Multicore                                   Schreurs, and P. Leroux, “Automatic in-door fall
Digital Signal Processor (DSP) platform.                                    detection based on microwave radar measurements,”
                                                                            European Radar Conference, pp. 202-205, Nov. 2012.

