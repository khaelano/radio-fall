Igual et al. BioMedical Engineering OnLine 2013, 12:66
http://www.biomedical-engineering-online.com/content/12/1/66




 REVIEW                                                                                                                                         Open Access

Challenges, issues and trends in fall detection
systems
Raul Igual*, Carlos Medrano and Inmaculada Plaza


* Correspondence: rigual@unizar.es
R&D&I EduQTech Group, Escuela             Abstract
Universitaria Politecnica de Teruel,
University of Zaragosa, Teruel, Spain     Since falls are a major public health problem among older people, the number of
                                          systems aimed at detecting them has increased dramatically over recent years. This
                                          work presents an extensive literature review of fall detection systems, including
                                          comparisons among various kinds of studies. It aims to serve as a reference for both
                                          clinicians and biomedical engineers planning or conducting field investigations.
                                          Challenges, issues and trends in fall detection have been identified after the reviewing
                                          work. The number of studies using context-aware techniques is still increasing but
                                          there is a new trend towards the integration of fall detection into smartphones as well
                                          as the use of machine learning methods in the detection algorithm. We have also
                                          identified challenges regarding performance under real-life conditions, usability, and
                                          user acceptance as well as issues related to power consumption, real-time operations,
                                          sensing limitations, privacy and record of real-life falls.
                                          Keywords: Fall detection, Review, Smart phones, Assistive technology, Health care


## Introduction
                                        According to the World Health Organization [1] approximately 28-35% of people aged
                                        65 and over fall each year increasing to 32-42% for those over 70 years of age. The fre-
                                        quency of falls increases with age and frailty level. In fact, falls exponentially increase
                                        with age-related biological changes, which is leading to a high incidence of falls and fall
                                        related injuries in the ageing societies. If preventive measures are not taken in the im-
                                        mediate future, the number of injuries caused by falls is projected to be a 100% higher
                                        in 2030. In this context, assistive devices that could help to alleviate this major health
                                        problem are a social necessity. Indeed, fall detectors are being actively investigated.
                                          A fall detection system can be defined as an assistive device whose main objective is
                                        to alert when a fall event has occurred. In a real-life scenario, they have the potential
                                        to mitigate some of the adverse consequences of a fall. Specifically, fall detectors can
                                        have a direct impact on the reduction in the fear of falling and the rapid provision of
                                        assistance after a fall. In fact, falls and fear of falling depend on each other: an individual
                                        who falls may subsequently develop fear of falling and, viceversa, the fear of falling may
                                        increase the risk of suffering from a fall [2]. Fear of falling has been shown to be associ-
                                        ated with negative consequences such as avoidance of activities, less physical activity, fall-
                                        ing, depression, decreased social contact and lower quality of life [3]. The effect of
                                        automatic fall detection units on the fear of falling has been studied by Brownsel et al.
                                        [4]. They conducted a study with community alarm users who had experienced a fall in
                                        © 2013 Igual et al.; licensee BioMed Central Ltd. This is an Open Access article distributed under the terms of the Creative Commons
                                        Attribution License (http://creativecommons.org/licenses/by/2.0), which permits unrestricted use, distribution, and reproduction in
                                        any medium, provided the original work is properly cited.
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                             Page 2 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                the previous six months. At the end of the study, those who wore the fall detector appro-
                priately reported that they felt more confident and independent, and considered that the
                detector improved their safety. One of the conclusions of the study was that the fear of
                falling is likely to be substantially affected by user perception of the reliability and accur-
                acy of the fall detector.
                   The other important aspect that fall detectors may help to reduce is the time the elderly
                remain lying on the floor after falling (long lie). This time is one of the key factors that
                determine the severity of a fall. Many older fallers are unable to get up again without
                assistance and any subsequent long lie can lead to hypothermia, dehydration, broncho-
                pneumonia and pressure sores [5,6]. This is particularly critical if the person lives
                alone or loses consciousness after falling. Lord et al. [7] reviewed different studies on
                the long lie. They found that the long lie is a marker of weakness, illness and social iso-
                lation and is associated with high mortality rates among the elderly. More than 20% of
                patients admitted to hospital because of a fall had been on the ground for an hour or
                more, and even if there was no direct injury from the fall, their morbidity rates within
                6 months were very high. Robust fall detectors may have the potential to diminish this
                long lie. A robust fall detector is one that is able to classify the falls as falls and the
                non-falls as non-falls even under real life conditions. If a fall event occurs and the sys-
                tem does not detect it, the consequences can be dramatic: the person can remain lying
                on the floor for a long time with all that this implies. In addition, the loss of confidence
                in the system may eliminate the benefits of the detector on the fear of falling. By con-
                trast, if the system reports an excessive number of false activations, caregivers may
                perceive it as ineffective and useless, which may lead to device rejection. But robust-
                ness is not easy to achieve. Although several commercial products are available on the
                market, the fact is that they are not widely used and do not have a real impact on the
                elders’ lives yet [8,9]. Besides, the vast majority of their potential users do not know of
                their existence. However, when the concept of fall detection is presented, they find in
                it a great potential to improve their security and safety in home.
                   For these and many more reasons, the number of studies on fall detection has in-
                creased dramatically over recent years. Unfortunately, there are not many reviews on
                fall detection. The work of Noury et al. [10], which appeared in 2008, can be considered
                the first one in this field. Shortly thereafter, Perry et al. [11] published a similar analysis.
                These studies provided a general overview of the fall detection status, but it has
                changed greatly since they were published, and the current fall detection trends have
                little in common with those of previous years. Mubashir et al. [12] is more recent, but
                it includes only 2 papers from 2011 and lacks later papers anyway, for instance many
                smartphone-based detectors. In our study, we do not present a detailed discussion of
                each paper, like [12], but rather we show the information schematically by means of
                tables including relevant information for people conducting research in this field: the
                types of falls used in the simulations, the number of users involved in the tests,
                whether they include data from older people, detectors’ performance, methods and
                features used for classification, etc. In addition we have performed a longitudinal
                study to identify the current trends. We have also included our view of the challenges
                that fall detection faces and we have highlighted the critical issues that can comprom-
                ise its use in real-world scenarios. We hope that our work will serve as a reference for
                both clinicians and biomedical engineers planning or conducting field investigations.
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                                   Page 3 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                   The study has been carried out through the analysis of several journal articles and
                conference proceedings. A search of IEEE Xplore, PubMed, MEDLINE, Google Scholar,
                and Web of Knowledge has been conducted. The search strategy included either “fall
                detection”, “fall detector”, “detection of falls”, “automatic fall detection”, “fall detection
                mobile phones”, “fall detection accelerometers”, “fall detection context” or “fall events”
                as the keywords. References were searched by hand and further relevant papers identi-
                fied from their citations. A total of 327 studies on fall detection were found, which were
                then categorized into different groups (see section Classification of fall detection systems).
                Some of them were selected for a further analysis that is presented in this paper. The
                selection criteria were:

                   – Firstly, we considered the most cited study per year in each category, from 2005 to
                     2012, according to the ranking provided by the Web of Knowledge.
                   – Secondly, among the remaining studies, we made a personal selection in order to
                     obtain those works that may help to identify the challenges, issues and trends in fall
                     detection as well as to provide a comprehensive vision of the different detection
                     techniques and the current status of this field. Only studies including some
                     experimental results or pioneering investigations have been considered.

                  The rest of this paper is organized as follows: firstly, a classification of fall detection
                systems is presented, distinguishing between context-aware systems and wearable devices;
                secondly, we discuss the challenges, issues and trends in fall detection.



                Classification of fall detection systems
                The literature reviewed provides evidence of the lack of a common approach. Noury et al.
                [10] classify the different studies on fall detection according to whether they only focus on
                the detection of the impact shock, or they also include the detection of the postfall phase.
                By contrast, Mubashir et al. [12] divide fall detectors into three categories: wearable device
                based, ambience sensor based and camera (vision) based. Perry et al. [11] group them into
                three categories: methods that measure acceleration, methods that measure acceleration
                combined with other methods, and methods that do not measure acceleration.
                   Essentially, the structure of all fall detection systems is always similar. Their main
                objective is to discriminate between fall events and activities of daily living (ADL). This
                is not an easy task as certain ADL, like sitting down or going from standing position to
                lying down, have strong similarities to falls. Thus, in order to test a fall detector, it is
                necessary to collect data from falls and ADL, which can be real (very difficult, especially
                for falls) or simulated by young volunteers (a feasible option adopted by most authors).
                These data are recorded by sensors and can be in form of acceleration signals, images,
                pressure signals, etc. Then, they are processed and classified using a fall detection tech-
                nique capable of distinguishing between falls and ADL. In most cases, the performance of
                the detector is expressed in terms of sensitivity (SE) and specificity (SP). The sensitivity is
                the ability of a detector to correctly classify a fall as a fall, while the specificity is the ability
                of a detector to correctly classify an ADL as ADL [13].
                   After reviewing the literature, we conclude that fall detectors can be broadly categorized
                into two types: context-aware systems and wearable devices. The first category includes
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                             Page 4 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                151 studies, while 197 papers belong to the second one. Twenty-one studies have been
                included in both categories since they use a combination of techniques. Next sections
                investigate some of the most relevant studies in both groups.



                Context-aware systems
                These systems use sensors deployed in the environment to detect falls. Their main advan-
                tage is that the person does not need to wear any special device. However, their operation
                is limited to those places where the sensors have been previously deployed [14].
                   Among all the possible types of sensors, the most common are cameras, floor sensors,
                infrared sensors, microphones and pressure sensors. Video-based systems can be consid-
                ered as a subcategory in this group as they use computer vision techniques that differ
                from the rest of the detection methods. Table 1 compares some of the most significant
                works in this area. For the comparison, we suggest a set of 9 items: the year of their publi-
                cation, a brief description of the fall detection technique, the features extracted to perform
                the fall detection, the fall types considered in the study, the subjects involved in the testing
                phase, the type of sensor used and whether they include data from older people or not.
                   There is a high variability in detection techniques as they are dependent on the type
                of sensor used. All methods start with a feature extraction, for example, the ratio of
                people’s height and weight [15], the edge points from the silhouette of a person [14],
                changes in illumination [16], the orientation of the main axis of the person [17], the
                width, height and depth of the human posture [18], the skin colour to detect people
                [19], etc. Then these features are compared and classified to distinguish normal activities
                from real falls using different techniques (Table 2). At present, lots of different features
                have been examined and none of them prevails over the rest since they give similar results
                and no comparison has been done.
                   The number of subjects involved in the tests is still low if compared to acceleration-
                based studies (next section). In addition, common to all of these works is the absence
                of older people during the test period.
                   Although most of the studies report relatively high accuracies, the experimental findings
                may not be generalized since there are significant limitations in the test dataset. For
                example, video-based systems only consider one or two specific sequences in con-
                trolled environments [14,15,17,19-24] and other studies with different types of sensors
                (pressure [25], infrared [18], etc.) only use a few tens of data collected from some
                young volunteers. Longer real-world tests could probably lead to more realistic results.
                   Privacy concerns in context aware systems are not minor problems. Methods to protect
                privacy are dependent on the type of sensor used. In the extreme case of video-based
                technology, some authors have opted to obscure or distort the person’s appearance in the
                video to ensure privacy [26]. Although privacy should already be considered in the design
                stage [27], not all the studies have followed this approach, which is a clear sign that some
                context aware systems are mainly focused on the technological development rather than
                on a real-world deployment.
                   If we focus on the fall detection techniques used in the different studies, a variety of ap-
                proaches can be found. Table 2 summarizes the contributions of the different authors.
                   In general, the structure of all methods is very similar. Most of them start with an object
                detection that can be performed through a background subtraction in the video-based
Table 1 Comparison of context-aware systems                                                                                                                                                                 Igual et al. BioMedical Engineering OnLine 2013, 12:66
Article                 Year Basis                        Features used for fall detection        Fall types          Subjects        Declared            Type of         Elders Comments
                                                                                                                                      performance         sensor          Yes/No
Lee et al. [20]         2005 Vision-based method          State and geometrical orientation       Fall lying down     21 subjects     SP: 80.5%           Camera          No    Personalized thresholds
                             for monitoring falls         of the silhouette at time t, spatial    in a ‘stretched’    (age 20–40)                                               are established based
                                                                                                                                      SE: 93.9%
                             at home                      orientation and speed of the centre     position and fall                                                             on the height of the
                                                          of the silhouette                       lying down in a                                                               subjects




                                                                                                                                                                                                            http://www.biomedical-engineering-online.com/content/12/1/66
                                                                                                  ‘tucked’ position
Miaou et al. [15]       2006 Customized fall detection    The ratio of people’s height            Not specified       20 subjects     With personal       Camera          No    Determining a proper
                             system using omni-           and weight                                                                  information:                              threshold statistically
                             camera                                                                                                   SP: 86% SE: 90%                           for different ranges of
                             images                                                                                                                                             height or weight alone
                                                                                                                                                                                does not improve the
                                                                                                                                                                                system performance
Vishwakarma et al. [21] 2007 Automatic detection of       Aspect ratio, horizontal and vertical   Sideways,           1 subject       SP: 100% SE: 100%   Camera          No    Both indoor and
                             human fall in video          gradient distribution of object in XY   forward,                                                                      outdoor video
                                                          plane and fall angle                    backward falls                                                                containing different
                                                                                                                                                                                types of possible falls
                                                                                                                                                                                are taken
Cucchiara et al. [19]   2007 A multi-camera vision        Geometrical and colour features         Not specified       Not specified   Difficulties with   Camera          No    If a fall is suspected it
                             system for detecting and     together with the projection of the                                         occlusions are                            delivers live video
                             tracking people and          silhouette’s shape on the x and y axes.                                     reported                                  streams to clinicians in
                             recognizing dangerous                                                                                                                              order to check the
                             behaviours                                                                                                                                         validity of a received
                                                                                                                                                                                alarm
Fu et al. [16]          2008 Contrast vision system       Change in illumination                  Backward,           3 subjects      3 possible          Contrast        No    Instantaneous motion
                             designed to detect                                                   forward and                         scenarios           vision sensor         vectors are computed
                             accidental falls                                                     sideways falls                      evaluated with                            and fall hazards are
                                                                                                                                      positive results                          immediately reported
                                                                                                                                                                                with low
                                                                                                                                                                                computational effort
Hazelhoff et al. [17]   2008 Real-time vision system to   The orientation of the main axis        Not specified       At least 2      SE: 100% when       Camera          No    The position of the
                             detect fall incidents in     of the person and the ratio of the                          subjects        large occlusions                          head is taken into
                             unobserved home              variances in horizontal and vertical                                        are absent                                account in order to
                             situations                   direction Skin colour                                                                                                 obtain a high
                                                                                                                                                                                robustness




                                                                                                                                                                                                                                              Page 5 of 24
Table 1 Comparison of context-aware systems (Continued)                                                                                                                                             Igual et al. BioMedical Engineering OnLine 2013, 12:66
Anderson et al. [22]   2009 3D representation of         At low level: silhouettes from each        At least, falls   Not specified   SE: 100%          Camera       No   The system can
                            humans (voxels) using        camera, to build a set of voxels. At       forward,                                                              produce sentences
                            multiple cameras. Two        an intermediate level: centroid, height,   backwards, and                    SP: 93.75%                          like “the person is on-
                            levels of fuzzy logic        major orientation of the body and          to the side (with                                                     the-ground in the
                            determines first a state     similarity of the major orientation with   recovery,                                                             kitchen for a
                            and then activities          the ground plane normal.                   attempting to                                                         moderate amount of




                                                                                                                                                                                                    http://www.biomedical-engineering-online.com/content/12/1/66
                            (f.i. a fall)                                                           get back up,                                                          time”
                                                                                                    lying
                                                                                                    motionless)
Lie et al. [23]        2010 Vision fall detection        The ratio and difference of human   Not specified            15 subjects     Accuracy 84.44%   Camera       No   Activities are divided
                            system considering           body silhouette bounding box height                          (age 24–60)                                         into three categories:
                            privacy issues               and width                                                                                                        standing posture,
                                                                                                                                                                          temporary posture
                                                                                                                                                                          and lying down
                                                                                                                                                                          posture
Rimminen et al. [28]   2010 Fall-detection method        Features related to the near-field         Backward to sit, 10 subjects      SE: 91%           Near-field   No   The fall-detection
                            using a floor sensor         imaging floor (the number of               backward to                                         image             performance is valid
                                                                                                                                      SP: 91%
                            based on near-field          observations, the sum of magnitudes        lateral, to supine,                                 sensor            for multiple people in
                            imaging                      and dimensional features)                  onto knees, arm                                                       the same room
                                                                                                    protect, to
                                                                                                    prone, rotate
                                                                                                    right and left,
                                                                                                    right and left
                                                                                                    lateral
Tzeng et al. [25]      2010 A system that adjusts the    Floor pressure signal                      Backward,         Not specified   SP: 96.7%         Pressure/    No   The floor pressure
                            detection sensitivity on a                                              forward and                                         infrared          sensor is combined
                                                         Image features: standard deviation                                           SE: 100%
                            case-by-case basis to                                                   sideways falls                                      sensors           with the infrared
                            reduce unnecessary           of vertical projection histogram,                                                                                sensor
                            alarms                       standard deviation of horizontal
                                                         projection histogram, and aspect ratio
Diraco et al. [24]     2010 An active vision system      People’s silhouette and their              Backward falls,   Not specified   SE: 80%           Camera       No   Information about the
                            for the detection of falls   centre-of-mass                             forward falls,                                                        3D position of the
                                                                                                                                      SP: 97.3%
                            and the recognition of                                                  lateral falls                                                         subject is combined
                            postures for elderly                                                                                                                          with the detection of
                            homecare applications.                                                                                                                        inactivity.




                                                                                                                                                                                                                                      Page 6 of 24
Table 1 Comparison of context-aware systems (Continued)                                                                                                                                         Igual et al. BioMedical Engineering OnLine 2013, 12:66
                                                                                                                                                                    An approach for
                                                                                                                                                                    posture recognition is
                                                                                                                                                                    proposed
Rougier et al. [14]      2011 A vision system based on   Some edge points from the         Forward falls,      Not specified     Accuracy (falls and Camera   No    The fall impact is an
                              analyzing human shape      silhouette of the person          backward falls,                       ADL correctly                      important feature to




                                                                                                                                                                                                http://www.biomedical-engineering-online.com/content/12/1/66
                              deformation                                                  falls when                            classified): 98%                   detect a fall, but the
                                                                                           inappropriately                                                          lack of movement
                                                                                           sitting down,                                                            after the fall is crucial
                                                                                           loss of balance                                                          for robustness
Li et al. [29]           2012 Acoustic fall detection    Acoustic signals sampled          Backward,           3 subjects         SE: 100%         Array of    No   The source of the
                              system                     at 20 KHz                         forward and         (2 female, 1 male,                  microphones      sound is located.
                                                                                           sideways falls      ages 30, 32, 46)   SP: 97%
                                                                                                                                                                    The performance of
                                                                                           (balance, lose
                                                                                                                                                                    the acoustic detector
                                                                                           consciousness,
                                                                                           trip, slip, reach                                                        is evaluated using
                                                                                           chair, couch)                                                            simulated fall and
                                                                                                                                                                    nonfall sounds
Mastorakis et al. [18]   2012 Real-time fall detection   The width, height and depth       Backward,           8 subjects        All falls were    Infrared   No    The system requires
                              system based on the        of the human posture, which       forward and                           accurately        sensor           no pre-knowledge of
                              Kinect sensor              define a 3D bounding box          sideways falls                        detected                           the scene and three
                                                                                                                                                                    parameters to
                                                                                                                                                                    operate; the width,
                                                                                                                                                                    height and depth of
                                                                                                                                                                    the subject
Zhang et al. [27]        2012 Privacy Preserving         Deformation and person’s height   Fall from chair,    5 subjects        Accuracy 94%      RGBD       No    The system can
                              Automatic Fall Detection                                     fall from                                               cameras          handle special cases
                                                                                           standing                                                                 such as light turning
                                                                                                                                                                    off (insufficient
                                                                                                                                                                    illumination)




                                                                                                                                                                                                                                  Page 7 of 24
Table 2 Fall detection techniques in the context-aware studies                                                                                                                                             Igual et al. BioMedical Engineering OnLine 2013, 12:66
                                                                                               Fall detection method
                        1st step                        2nd step                          3rd step                         4th step                                 5th step
Lee et al. [20]         Adaptive background             Image processing using            Feature extraction               Determination of the threshold
                        subtraction to detect the       a connective-component                                             values for each of the features
                        object of interest              labelling technique, with                                          based on the height of the users




                                                                                                                                                                                                           http://www.biomedical-engineering-online.com/content/12/1/66
                                                        the end product being a
                                                        ‘blob’ or silhouette
Miaou et al. [15]       Background subtraction          Image processing: erosion         Feature extraction               Simple threshold-based decision
                        to detect the objects.          and dilatation, connected         (height and width of             algorithm for fall detection
                                                        component labelling               object’s silhouettes)
                                                        technique
Vishwakarma et al. [21] Patient detection               Feature extraction                Fall detection using aspect      Fall confirmation using the fall
                        (adaptive background                                              ratio and pixel's gradient       angle and applying rule-based
                        subtraction method using                                          distribution and applying        decisions
                        Gaussian mixture model)                                           rule-based decisions
Cucchiara et al. [19]   Extraction of moving objects    Tracking algorithm:               Classification as people         Posture classifier based on the          Hidden Markov Models formulation
                        using background suppression    A probabilistic and               of tracks that satisfy some      projection histograms computed           is adopted to classify the posture
                        with selective and adaptive     appearance-based tracking         geometrical and colour           over the temporal probabilistic
                        update                                                            constraints                      maps obtained by the tracker
Fu et al. [16]          Extraction of changing pixels   A lightweight algorithm           Fall events are reported
                        (motion events) from the        computes the instantaneous        using the temporal average
                        background                      motion vectors                    of the motion events
Hazelhoff et al. [17]   Object segmentation:            Object tracking: the tracker      PCA-based feature extraction:    Fall detection: using a multi-frame      Head tracking using skin-colour
                        (background subtraction and     can mark objects as non-human,    the direction of the principal   Gaussian classifier                      model to confirm the fall
                        connection of information       which are identified based on     component and the variance
                        components)                     size and absence of both motion   ratio are extracted
                                                        and a head region
Anderson et al. [22]    Silhouette extraction from      Extraction of centroid, height,   Human state inferred using      Information in sequences of states     Fall detected by a second level
                        each camera. Then, a 3D         major orientation of the body     fuzzy logic (3 states: upright, is reduced by linguistic summarization of fuzzy logic, taking inputs from
                        representation of the body      and similarity of the major       on-the-ground and in-between) to produce human readable sentences a single summary: average state,
                        is constructed                  orientation with the ground                                                                              time duration, speed, oscillation, etc.
                                                        plane normal




                                                                                                                                                                                                                                             Page 8 of 24
Table 2 Fall detection techniques in the context-aware studies (Continued)                                                                                                                                  Igual et al. BioMedical Engineering OnLine 2013, 12:66
Lie et al. [23]          Human body identification         Image processing: mean filter   Features extraction and            k-nearest neighbour classifier for         Fall event detection flow:
                         using frame differencing approach to make the image more smooth, reduction of upper limb             human body postures classification         the decision of a fall incident
                                                           thresholding to obtain a binary activities effect                                                             is determined by the event
                                                           image, connected component                                                                                    transition and time difference
                                                           labelling                                                                                                     between events




                                                                                                                                                                                                            http://www.biomedical-engineering-online.com/content/12/1/66
Rimminen et al. [28]     Estimate the position of the      Tracking (Kalman filter) and       Features extraction related     Modelling of the state evolution           Pose estimation using Bayesian
                         subject using the near-field      multi-target tracking (Rao-        to the NFI floor                as a two-state Markov chain                filtering. It combines the prior
                         image sensor observations         Blackwellized Monte Carlo data                                     (falling, getting up)                      model with information from
                                                           association algorithm)                                                                                        the features
Tzeng et al. [25]        Fall suspection: Thresholding     If the floor preassure exceeds a   Background subtraction          Image features extraction                  Combination of the floor
                         of the floor pressure signal      given threshold: Image capture     through an image thresholding.                                             pressure signal and image
                                                                                              Objects labelling and expansion                                            features to report on a fall
                                                                                              (morphological operations)
Diraco et al. [24]       Camera calibration                Background modelling using         Moving regions detection      Fall suspection: The distance                Fall confirmation if an
                                                           Mixture of Gaussians method        (Bayesian segmentation) and   of the centroid from the floor               unchangeable situation persists
                                                                                              segmented blobs refining      plane is lower than a prefixed value         for at least 4 seconds
                                                                                              (morphological operations and
                                                                                              connected components)
Rougier et al. [14]      Silhouette detection              Silhouette edge points             Shape analysis using the mean Fall classification: Gaussian mixture
                         (foreground segmentation          matching through the video         matching cost and the full    model, based on shape deformation
                         method) and edge points           sequence                           Procrustes distance           during the fall and the subsequent
                         extraction (Canny edge                                                                             lack of movement
                         detector)
Li et al. [29]           Locate the position of the        Beamforming to enhance the         Mel-frequency cepstral          A nearest neighbour classifier
                         sound source                      sound signal using the             coefficients features are       determines if the sound is from
                                                           estimated source position          extracted from the sound signal a fall
Mastorakis et al. [18]   Feature extraction: width,        Obtaining of the velocities of     When both velocities exceed     Inactivity detection: a fall is detected
                         height and depth of the           height and the composite           particular thresholds fall      if the height velocity is less than a
                         human posture                     vector of width and depth          initiation is detected          certain threshold
Zhang et al. [27]        Kinematic Model Based             Person tracking by background      Histogram represented           Hierarchy Support Vector Machine
                         Feature Extraction from           subtraction                        features                        classification
## Depth Channel




                                                                                                                                                                                                                                              Page 9 of 24
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                          Page 10 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                systems [14,15,17,19-23], or from the information provided by the sensors’ observation
                [28,29]. Some methods also consider a tracking algorithm to filter objects’ position
                [17,19,27,28]. Then, some features of the detected objects are extracted (Table 1), which
                should have sufficient discriminative power to identify the fall events. They are used to
                classify the events as falls or non-falls using a wide range of techniques: Gaussian Mixture
                Model [14], Rule-based Techniques [21], Multi-frame Gaussian Classifier [17], Bayesian
                Filtering [28], Nearest-neighbour Rule [23,29], Hidden Markov Models [19], Thresholding
                Techniques [15,20,25], Fuzzy Logic [22], etc. Some studies confirm that a fall has occurred
                by performing inactivity detection in the postfall phase [14,18,24].
                  As a result of this extensive literature search, we found that lots of strategies have
                been adopted, although currently there is no standardized context-aware technique that
                was widely accepted by the research community in this field.


                Wearable devices
                They can be defined as miniature electronic sensor-based devices that are worn by the
                bearer under, with or on top of clothing [30]. The vast majority of wearable fall detectors
                are in the form of accelerometer devices (186 out of 197). Some of them also incorporate
                other sensors such as gyroscopes to obtain information about the patient’s position. The
                use of applications based on accelerometers and gyroscopes in gait and balance evalu-
                ation, fall risk assessment and mobility monitoring has been actively explored [31]. This
                trend has increased over the last years due to the availability of cheap embedded sensors
                included in smartphones. In this paper, we classify the different studies using wearable de-
                vices according to whether or not sensors are built into smartphones, 30 and 156 papers
                respectively. The next two sections provide more details about these subgroups.

                Accelerometer attached to the body
                Acceleration data are collected during falls using independent tri-axial accelerometers
                attached to different parts of the body. A review of several research studies was conducted.
                For the purpose of comparison, Table 3 examines the most relevant works. The fields are
                the same as in section Context-aware systems, including a new item with the accelerometer
                placement on the body. Since Table 3 is only focused on acceleration-based systems, the
                possible techniques for fall detection are reduced to just two: i) threshold-based methods,
                TBM, in which a fall is reported when the acceleration peaks, valleys or other shape features
                reach predefined thresholds; ii) machine learning methods, MLM [32]. The aim is to
                visualize progress in research over the last years.
                  Most of the existing works use thresholding techniques for automatic fall detection
                [9,33-41], although the machine learning approach has increased its influence since
                2010 [42-44]. The methods applied include Support Vector Machine [42,44-46], Regrouping
                Particle Swarm Optimization, Gaussian Distribution of Clustered Knowledge [43], Multi-
                layer Perceptron, Naive Bayes, Decision tree [44,47], ZeroR and OneR [44]. The multilayer
                perceptron seems to be a good supervised option according to Kerdegari et al. [44], although
                there is no standardized technique that is widely accepted by the scientific community.
                  The average number of subjects involved in the tests is about 17, which is signifi-
                cantly higher than in context-aware systems (previous section). This indicates a
                higher reliability of this technology but still insufficient; only 6 of the works involve
                older people in the ADL study [9,33,35,37,40,45], while the rest use simulated data
Table 3 Comparison of acceleration based fall detectors using external accelerometers                                                                                                                                Igual et al. BioMedical Engineering OnLine 2013, 12:66
Article                Year        Basis               Detection technique                   Fall types                    Subjects                Declared      Position Elders            Comments
                                                                                                                                                   perform                Yes/No
Lindeman et al. [33]   2005   A fall detector       TBM considering the spatial       Falls to the front, side        A young volunteer              High          Ear     Yes         Accelerometers were
                              placed at head         direction of the head, the       with a 90° turn, back,        and an elderly woman           sensitivity                     integrated into a hearing-aid
                                    level          velocity right before the initial  back with hip flexion.              (83 years)                  and                            housing, which was fixed
                                                  contact with the ground and the                                                                  specificity                            behind the ear




                                                                                                                                                                                                                     http://www.biomedical-engineering-online.com/content/12/1/66
                                                                                     Falls backwards against
                                                                impact
                                                                                     a wall, while picking up
                                                                                     an object and collapse.
Chen et al. [34]       2005      Detect the       TBM considering the impact and Backward and sideways                     2 subjects                 The         Waist    No      The final orientation of the
                              occurrence of a        the change in orientation            falls                                                   acceleration                        wearer is considered
                                fall and the                                                                                                       for ADL is
                              location of the                                                                                                      much less
                                    victim                                                                                                          than the
                                                                                                                                                    observed
                                                                                                                                                  from falling
Zhang et al. [45]      2006   Fall detection       MLM. 1) Extraction of temporal            Soft fall               12 subjects (8 males,         Accuracy       Waist    Yes           To the best of our
                              using machine       and magnitude features from the                                   4 females, ages 10–70)          96,7%                          knowledge, this study is the
                                                                                     Hard fall in the ground,
                                  learning         acceleration signal, 2) One-class                                                                                                  first in using machine
                                 strategies       Support Vector Machine classifier stairs and slopes (using                                                                            learning techniques
                                                                                          a mannequin)
Bourke et al. [35]     2007 Investigation into    TBM using information from the      Forward falls, backward               10 subjects              Trunk        Trunk,   Yes     The trunk appears to be the
                              the ability to                  impact                  falls and lateral falls left         (ages 21–29)                           thigh             optimum location for a fall
                               discriminate                                            and right, performed                                        SP:100%                                    sensor
                            between falls and                                          with legs straight and       10 community-dwelling            Thigh
                                   ADL                                                          flexed             elderly subjects (3 females,
                                                                                                                                                   SP: 83.3%
                                                                                                                      7 males, ages 70–83)
Doukas et al. [46]     2007   Accelerometers        MLM. The acceleration in the           Not specified                   1 subject               SE: 98.2%      Foot     No       If a fall is suspected it also
                              transmit patient      three axis is classified using                                                                                                  transmits video images to
                              movement data           Support Vector Machine                                                                       SP: 96.7%                         remote monitoring units
                              wirelessly to the
                              monitoring unit




                                                                                                                                                                                                                                                       Page 11 of 24
Table 3 Comparison of acceleration based fall detectors using external accelerometers (Continued)                                                                                                            Igual et al. BioMedical Engineering OnLine 2013, 12:66
Kangas et al. [36]    2008 Comparison of 3     TBM considering the start of the      Forward, backward, and           3 volunteers (1 female,     Waist      Wrist,   No     Waist worn accelerometer
                            low-complexity     fall, the velocity, the impact and          lateral falls             2 males; ages 38, 42, 48)               head,            might be optimal for fall
                                                                                                                                                 SP: 100%
                              algorithms                the lying posture                                                                                    waist          detection considering the fall
                                                                                                                                                 SE: 98%                     associated impact and the
                                                                                                                                                                                posture after the fall




                                                                                                                                                                                                             http://www.biomedical-engineering-online.com/content/12/1/66
Kangas et al. [37]    2009   To validate the   TBM considering two or more of            Syncope, tripping,                20 subjects           SP: 100%    Waist    Yes   Middle-aged persons could
                             data collection     the following phases of a fall        sitting on empty air,            (40–65 years old),                                  be considered to mimic the
                                                                                                                                                 SE: 97.5%
                              of a new fall      event: start of the fall, falling      slipping, lateral fall,        21 voluntary older                                    fall events of older people
                                detector       velocity, fall impact, and posture        rolling out of bed          people (58–98 years old)                               more adequately than young
                               prototype                   after the fall                                                                                                           subjects would
Li et al. [38]        2009    Fall detection    TBM analyzing the intensity of         Forward, backward,               3 male subjects          SP: 92%     Chest,   No    Human activities are divided
                              system using       the activity, the posture and        sideways and vertical                (age 20)                          thigh            into static postures and
                                                                                                                                                 SE: 91%
                                   both        whether the transition to a lying      falls. Falling on stairs                                                                  dynamic transitions
                             accelerometers    posture was unintentional or not       and fall against walls
                             and gyroscopes                                           ending with a sitting
                                                                                              position
Shan et al. [42]      2010 Investigation of a MLM 1) A discriminant analysis is      Forward falls, backward            5 male subjects          SP: 100%    Waist    No    Impending falls are detected
                             pre-impact fall applied to time-domain statistical      falls, lateral falls left and       (ages 21 – 28)                                      in their descending phase
                                                                                                                                                 SE: 100%
                                detector        characteristics to select the          right (subjects were                                                                   before the body hits the
                                                features, 2) Support Vector          instructed to keep their                                                                          ground
                                                  Machine is used for fall               postures for about
                                                        recognition                  2 seconds after the fall)
Bianchi et al. [39]   2010 Augmentation of TBM considering the impact, the Forward, backward and           20 subjects (12 male,                 SP: 96.5%   Waist    No         A system based on a
                            accelerometer-   postural orientation, and the lateral falls (ending lying, 8 female; mean age: 23.7)                                           barometric pressure sensor is
                            based systems    change in altitude associated    with recovery, with                                                SE: 97.5%                        compared with an
                                                                                                            5 subjects (2 male,
                           with a barometric          with a fall            attempt to break the                                                                                accelerometry-based
                                                                                                        3 female; mean age: 24)
                            pressure sensor                                             fall)                                                                                technique. The acceleration
                                                                                                                                                                               and air pressure data are
                                                                                      Resting against a wall,          5 subjects (5 male,                                    recorded using a wearable
                                                                                      then sliding vertically           mean age: 26.4)
                                                                                                                                                                                        device
                                                                                     down to the end in the
                                                                                         sitting position




                                                                                                                                                                                                                                               Page 12 of 24
Table 3 Comparison of acceleration based fall detectors using external accelerometers (Continued)                                                                                                               Igual et al. BioMedical Engineering OnLine 2013, 12:66
Bourke et al. [40]      2010      It compares        TBM considering the fall impact,     Forward falls, backward           10 male subjects         SP: 100%    Waist    Yes   The algorithms were tested
                                    novel fall-        the velocity and the posture       falls, lateral falls left and       (age 24–35)                                       against ADL performed by
                                    detection                                             right all performed with                                                                    elderly subjects
                                                                                                                            10 older subjects       SE: 94.6%
                                 algorithms of                                             both legs straight and
                                     varying                                                 with knees relaxed             (6 male, 4 female,
                                   complexity                                                                                  age 73–90)




                                                                                                                                                                                                                http://www.biomedical-engineering-online.com/content/12/1/66
Lai et al. [41]         2011       Several            TBM to differentiate dynamic/          Forward, backward,                16 subjects           Accuracy    Neck,    No    After a fall accident occurs,
                                 acceleration            static states using the           rightward or leftward                                      92.92%     hand,          the system determines the
                               sensors for joint      acceleration of the three axis                falls                                                        waist,                level of injury
                                 sensing fall                                                                                                                     foot
                                   events
Bagala et al. [9]       2012     Benchmark the        TBM including, among others,        Real-world falls: indoor/       9 subjects (7 women,      Average 13   Lower    Yes       Algorithms that were
                                 performance of        the algorithms published in            outdoor, forward            2 men, age: 66.4±6.2)     algorithms    back             successful at detecting
                                  published fall-                 [35,36]                  /backward /sideward,                                                                    simulated falls did not
                                    detection                                             impact against the floor             15 subjects          SP: 83.0%                        perform well when
                                 methods when                                              /wall or locker before                                    ±30.3%                      attempting to detect real-
                                they are applied                                           hitting the floor / sofa            29 subjects          SE: 57.0%                            world falls
                               to real-world falls                                               or bed/ desk
                                                                                                                                1 subject            ±27.3%
Yuwono et al. [43]      2012      Use of a                MLM. 1) Discrete wavelet              Not specified                 8 individuals         SP: 99.6%    Waist    No    Training and clustering are
                               sophisticated fall     transform, 2) Associate a cluster                                       (age 19–28)                                        done off-line. Clustering is
                                                                                                                                                    SE: 98.6%
                                  detection          to the input feature vector; fuse                                                                                            done using Regrouping
                                   method            cluster information with input, 3)                                                                                         particle swarm optimization
                                                        Combined classification (vote
                                                      majority): Multilayer Perceptron
                                                        and Augmented Radial Basis
                                                                  Function
Kerdegari et al. [44]   2012    Investigation of        MLM. Input is pre-processed           With flexed knees:          50 volunteers (18 male,   SE: 90.15%   Waist    No    Multilayer Perceptron, Naive
                               the performance         using windowing techniques.           forward, backward,             32 female, average                                  Bayes, Decision tree, Support
                                   of different        Features include acceleration,           sideways falls                   age 32)                                         Vector Machine, ZeroR and
                                  classification         angular velocity, velocity,                                                                                                OneR algorithms are
                                                                                          Base on wall: backward,
                                   algorithms            position and time domain                                                                                                        compared.
                                                      features: maximum, minimum,              sideways falls
                                                        mean, range, variance and          Backward falls sitting                                                                  Results show that the
                                                        standard deviation. Several        on empty, turning left                                                                  Multilayer Perceptron
                                                          methods are compared.                 and right                                                                       algorithm is the best option




                                                                                                                                                                                                                                                  Page 13 of 24
Table 3 Comparison of acceleration based fall detectors using external accelerometers (Continued)                                                                                                Igual et al. BioMedical Engineering OnLine 2013, 12:66
Cheng et al. [47]    2013     Daily activity    TBM using a decision tree: 1) A    Four types of falls: from   10 subjects (6 males,   SE: 95.33%   Chest   No     Dynamic gait activities are
                             monitoring and     decision tree is applied to the      standing to face-up       4 females, age 22–26)                              also identified using Hidden
                                                                                                                                       SP: 97.66%   Thigh
                              fall detection    angles of all the body postures    lying, face-down lying,                                                           Markov Models. Surface
                                               to recognize posture transitions,      left-side lying, and                                                       electromyography signals are
                                                  2) the impact magnitude is            right-side lying                                                               combined with the
                                                thresholded to detect the falls                                                                                       acceleration signals.




                                                                                                                                                                                                 http://www.biomedical-engineering-online.com/content/12/1/66
TBM: Threshold Based Method, MLM: Machine Learning Method.




                                                                                                                                                                                                                                   Page 14 of 24
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                         Page 15 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                from young volunteers. As in the previous section, longer real-world tests with target
                users would be required.
                  Nearly all the studies concur that the broader categories of typical fall events are for-
                ward, backward and sideways, although some of them extend these categories to cover
                a large number of fall situations [33,38,39]. Regarding the position of the accelerometer,
                the placement site at the waist seems to be optimal for fall detection. Waist attached
                accelerometers are located near the body’s centre of gravity, providing reliable informa-
                tion on subject body movements [36].
                  As in the previous category, the declared performance is very high, but the fact is
                that there is little use of these devices in daily geriatric practice and no significant in-
                dustrial deployment of fall detectors due mainly to the significant number of false
                alarms, resulting in inappropriate alerts [8]. The declared results are valid for labora-
                tory environments with limited data or under restricted conditions, but in real-world
                scenarios there are lots of uncontrolled factors that lead to a dramatic loss in per-
                formance [9]. Therefore, studies should incorporate longer tests and include indica-
                tors closer to a real-world usage, for example the number of false alarms per day,
                which may provide target users with a more realistic idea of the true performance of
                the system.

                Smartphone built-in accelerometer
                Today’s smartphones come with a rich set of embedded sensors, such as an accelerometer,
                digital compass, gyroscope, GPS, microphone, and camera [48]. Several researchers are
                currently taking advantage of this fact to develop smartphone based fall detectors. Table 4
                summarizes some relevant works in this field.
                   Low-complexity algorithms based on thresholding are used in most of the studies
                [49-53], and only few go further and adopt machine learning strategies [54,55]. They
                use Support Vector Machines, Sparse Multinomial Logistic Regression, Naïve Bayes,
                K-Nearest Neighbors, Decision Trees [54] and Multi-layer Neural Networks [55].
                   The types of falls considered and the number of subjects involved in the studies are
                similar to those of the previous section. Regarding the position of the phone, the waist
                is still the preferred part of the body [52,55], although there is an emerging trend towards
                the thigh, coinciding with the location of the pocket [49-51,53].
                   Some of these studies [49] have resulted in real fall detection applications that are
                available for download in Google Play [56]. This site offers another source of information.
                Thus, a search has been conducted in this repository including either “fall detector” or
                “fall detection” as the keywords. As a result, a total of 9 applications were obtained, of
                which 7 were for seniors. To quote some statistics, 3 of them reported between 1000 and
                5000 downloads, while the rest had less than 500. Although these numbers indicate a
                certain level of interest, they are still far from the number of potential users. Focusing
                on the app rating, we found that an average of only 6 people have given their opinions
                on them. This is a symptom that people using these apps do not seem to be enthusiastic
                about them.
                   The number of published studies based on smartphones is still low in comparison with
                the previous categories, and none of them involve older people to evaluate the detector.
                Therefore, studies still need to incorporate a more exhaustive evaluation. These are signs
                that we are facing an emerging field.
Table 4 Smartphone based fall detectors                                                                                                                                                                          Igual et al. BioMedical Engineering OnLine 2013, 12:66
       Article         Year           Basis               Detection technique               Fall types                Study design           Declared        Position Elders            Comments
                                                                                                                                             perform                  Yes/No
 Sposaro et al. [49]   2009    Alert system for fall      TBM considering the             Not included                Not included          Not included      Thigh     No      First documented mobile
                              detection using smart     impact, the difference in                                                                            (pocket)           phone-based fall detector
                                      phones            position before and after
                                                                                                                                                                                 The existence of a lying
                                                        the fall and whether the




                                                                                                                                                                                                                 http://www.biomedical-engineering-online.com/content/12/1/66
                                                                                                                                                                               period after falling is checked
                                                         fallen patient is able to
                                                            regain the upright
                                                                  position
   Dai et al. [50]     2010    Mobile phones as a         TBM considering the          Forward, lateral and        15 participants   Good detection           Chest,    No      A detection algorithm with
                                  platform for            impact, the wearer’s         backward falls with   from 20 to 30 years old  performance             waist,              an external accessory is
                                developing fall            orientation and the        different speeds (fast   (2 females, 13 males)                          thigh                      included
                               detection systems        common step mechanics            and slow) and in
                                                              during falling          different environment
                                                                                      (living room, kitchen,
                                                                                                etc.)
  Lopes et al. [51]    2011   Application to detect       TBM considering the         Fall into bed, forward          Not specified         Not specified     Thigh     No     Five scenarios to validate the
                                 and report falls,              impact                fall, backward fall, fall                                                                detector are presented. Each
                                 sending SMS or                                           in slow motion                                                                        scenario includes ADL and
                               locating the phone                                                                                                                                           falls.
  Albert et al. [54]   2012       Demonstrate           MLMs using a large time-      Left and right lateral,     15 subjects (8 females,   Across an         Back      No         Five machine learning
                               techniques to not        series feature set from the    forward trips, and          7 males, ages 22–50) average week of                           classifiers are compared:
                              only reliably detect a        acceleration signal.         backward slips                                      everyday                            Support vector machines,
                                 fall but also to                                                                                          movements                            Sparse multinomial logistic
                              automatically classify                                                                                      there are 2–3                         regression, Naïve Bayes, K-
                                     the type                                                                                                non-falls                            nearest neighbours, and
                                                                                                                                          misclassified as                              Decision trees
                                                                                                                                                falls
   Lee et al. [52]     2012   Study the sensitivity       TBM considering the         Forwards, backwards,         18 subjects (12 males,     SP: 81%         Waist     No     The motion signals acquired
                              and specificity of fall           impact                lateral left and lateral    6 females, ages 29±8.7)                                      by the phone are compared
                                detection using                                                 right                                         SE: 77%                           with those recorded by an
                                 mobile phone                                                                                                                                  independent accelerometer
                                  technology




                                                                                                                                                                                                                                                   Page 16 of 24
Table 4 Smartphone based fall detectors (Continued)                                                                                                                                              Igual et al. BioMedical Engineering OnLine 2013, 12:66
  Fang et al. [53]    2012       Fall detection          TBM considering the             Not specified               4 subjects         SP: 73.78%   Chest,   No    Different phone-attached
                               prototype for the       impact and the patient’s                                                                      waist         locations are analysed. The
                                                                                                                                        SE: 77.22%
                                Android-based                orientation                                                                             thigh         chest seems to be the best
                                    platform                                                                                                                                  place.
 Abbate et al. [55]   2012    A system to monitor       MLM Eight acceleration       Forward fall, backward     7 volunteers (5 male,   SP: 100%     Waist    No   The proposed approach is




                                                                                                                                                                                                 http://www.biomedical-engineering-online.com/content/12/1/66
                               the movements of          properties of fall-like      fall, and faint (normal   2 female, ages 20–67)                                 compared with the
                                                                                                                                        SE: 100%
                              patients, recognize a    events are classified using        speed and slow                                                            techniques described in
                             fall, and automatically    multi-layer feed-forward              motion)                                                                    [35,36,49,66]
                               send a request for           neural network
                             help to the caregivers




                                                                                                                                                                                                                                   Page 17 of 24
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                                                      Page 18 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




## Discussion
                Trends, challenges and issues
                Based on the extensive literature search, challenges, issues, and trends in fall detection
                systems have been identified. This section presents the most relevant ones.


                Trends
                We start by describing the current and future trends in fall detection systems.
                Trend 1: Vision and smartphone-based detectors
                Context-aware techniques appeared over a decade ago and the number of studies is still
                increasing after a drop some years ago (Figure 1), most of them being video-based systems.
                It is unfortunate that the algorithmic details of these systems do not seem to converge.
                Computer Vision approaches are very complex and it is difficult to obtain a system that
                can work under real life conditions. On the other hand, the use of body-worn accelerome-
                ters has stagnated in the last years, but this trend is offset by the increase in the num-
                ber of smartphone-based studies. In fact, this is still a novel technology: the first study
                using smartphones appeared in 2009 [49] and since then the research in this field has
                grown steadily. These are signs that we are facing an emerging trend, which may be
                explained by the advantages offered by smartphones. As self-contained devices, they
                present a mature hardware and software environment for developing pervasive fall de-
                tection systems [50]. They have built-in communication protocols that allow simple
                data logging to the device and wireless transmission. Price is also significantly reduced
                due to high production volume [54,57].
                Trend 2: Machine learning approach
                There are two main approaches to detect falls using acceleration signals: thresholding
                techniques and machine learning methods. Applications based on the first approach



                                     50                                                            40
                                     45                                                            35
                                     40
## 30                       Context-aware




                                                                                                        Number of studies
                                     35




                    Percentage (%)
                                     30                                                            25                       Worn
                                                                                                                            accelerometer
                                     25                                                            20                       Smartphone-
                                     20                                                                                     based
                                                                                                   15
                                     15
                                                                                                   10
                                     10
                                     5                                                             5

                                     0                                                             0
                                          2005   2006   2007   2008   2009   2010   2011   2012
                  Figure 1 Estimation of the number of fall detection studies. We have made a longitudinal study of
                  published papers, classifying the detection techniques into three categories. The line graph (associated with
                  the right axis) represents the estimated absolute number of studies published in the three categories from
                  2005 to 2012. The bar graph (associated with the left axis) shows the estimated percentage of studies
                  published every year in relation to the total number of existing studies for each category (e.g., 43.3% of the
                  existing smartphone-based studies were published in 2012).
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                         Page 19 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                are simple to implement and their computational work is minimal. They are able to
                detect when a fall occurs. However, the rate of false positives is a significant issue [54].
                The machine learning approach is more sophisticated and leads to better detection
                rates. Nevertheless, there have been documented difficulties with implementing these
                techniques (for example: requirement of high mathematical skills, use of more computa-
                tion resources, etc.), although they are currently the prevailing trend, since thresholding
                methods proved to be ineffective [9]. In addition, no method has been widely accepted
                and each paper presents a different approach among the variety of machine learning
                algorithms.


                Challenges
                The design of fall detectors faces some major challenges described in this section.

                Challenge 1: Performance under real-life conditions
                Fall detectors need to be as accurate and reliable as possible. A robust fall detection
                system should exhibit both high sensitivity and specificity. This is sometimes reached
                in experimental environments, but when applied to a real situation, the detection rate
                decreases [8]. These devices are designed and tested under controlled conditions, for
                example they use data from falls and ADL of young people simulated at the discretion
                of each author due to the lack of a standardized procedure or a public database for
                comparison. Furthermore, it is worth pointing out that fall detectors are aimed at older
                people, so they should also be involved in their development. Only few studies incorporate
                data from older people [9,33,35,37,40,45], although their participation is limited to per-
                form a set of simulated activities of daily living for a few minutes or hours. That is not
                enough to assess the system performance in a real situation. Users should wear the de-
                vices for longer periods (at least months). Some studies have worked in this direction
                [4,9], resulting in a significant number of false activations, among other concerns.

                Challenge 2: Usability
                Smartphone-based fall detectors are attractive because of the widespread use of phones,
                even among the older population [58]. However, the majority of the studies referenced
                in Table 4 placed them in a standardized position. This allowed highly stereotypical
                measurements that aided accuracy ratings, but made the results less applicable to the
                way people carry their smartphones every day (for example: in pockets or handbags)
                [54]. Future smartphone-based detectors should not limit the placement of the device
                to a single part of the body (waist, wrist, chest, etc.). Smartphones should be used in a
                normal way, with no restrictions regarding their position or functionalities. This may
                lead to lower detection rates.

                Challenge 3: Acceptance
                Little is published about the practicality and acceptability of the technology. Elders’
                acceptance poses a major problem since they may not be familiar with electronic de-
                vices. To overcome this challenge, the way the system operates is essential [59]. The
                detector should activate and operate automatically, without user intervention. Vision
                systems, like other non intrusive methods, are very good in this sense. However, some
                wearable devices like smartphones have other advantages that can help to improve
                the acceptance of fall detectors. They can operate both indoors and outdoors and
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                           Page 20 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                integrate not only fall detection but also other healthcare applications in the same de-
                vice. In this way, the traditional reluctance to carry different devices, each one
                targeting a specific function, would be overcome. However, the use of smartphones by
                older people is not without difficulty: these devices, as they were conceived, represent
                a major usability barrier for them. Proof of this is the absence of rating in the existing
                fall detection applications, which is a symptom of little real use. In this sense, poten-
                tial solutions to improve the usability and accessibility of smartphones are needed.
                Nevertheless, as a result of a study still in progress we have found that fall detectors
                were highly valued by the elderly, who showed a positive attitude towards smartphone-
                based solutions after carrying out a practical demonstration of several assistive tech-
                nologies. This conclusion agrees with the work of Plaza et al. [60], who reviewed mobile
                applications for older people and found that they are most frequently related to two
                domains: “Health – wellness – home care” and “Safety – security – mobility”.

                Issues
                This section describes the most significant issues which could hinder the system
                performance.

                Issue 1: Smartphone limitations
                The trend towards smartphone-based detectors poses some problems. Firstly, smartphones
                are not devices initially intended for fall detection or any other safety critical application
                [49]. There might be difficulties with real-time operations, the sensing architecture,
                the stability of the accelerometer’s sampling frequency, the specific features of the op-
                erating system, etc. Indeed, the same fall detector might behave slightly differently
                depending on the smartphone model in which it is installed. This possibility should
                be taken into account in a real-world scenario. Secondly, smartphones cannot be
                overloaded with continuous sensing commitments that undermine the performance
                of the phone, for example by depleting battery power. It is essential to manage the
                sleep cycle of sensing components in order to trade off the amount of battery consumed
                [48]. Nonetheless, smartphone’s battery life is always low, which could hinder its accept-
                ance. This is not a minor problem, especially considering that the system is intended for
                older people with impaired mobility. Thirdly, there is a need for easy-to-use smartphones
                and here we are in the hands of manufacturers. The potential market of the applications
                for people with low technical skills will influence the development of adapted devices.
                Nonetheless, fall detectors are unlikely to reach in the near future the robustness and sta-
                bility achieved by other assistive technologies such as press-for-help devices.

                Issue 2: Privacy concerns
                Privacy concerns of sensor-based systems, and fall detectors are, have been a hot topic
                [61]. Of course, not all types of sensors are equally vulnerable: context-aware systems
                in general, and vision-based systems in particular, are much more prone to privacy con-
                cerns than, for example, body-worn acceleration-based devices. In any case, the protec-
                tion of sensitive context data must be guaranteed [62]. Privacy problems should not
                prevent the potential benefits of assistive technologies as, at the same time, privacy
                cannot be sacrificed in order to bring about other benefits [63]. In general, studies on
                fall detection usually lack strategies to ensure data privacy. This shows that they are
                still far from a real-life deployment.
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                                                          Page 21 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                Issue 3: Comparison among different techniques: public data bases
                Comparing different approaches is difficult because each author obtains data in a different
                way: types of simulated falls and ADL, position of the detector, sampling frequency, tem-
                poral length of signal, extracted features, etc. The research focus should be not only on
                the algorithm to be used but also on the way signals are acquired and treated before feed-
                ing a classifier. A public database with accelerometer signals and videos of people falling
                could help to compare different methods and to improve the reproducibility of the results.
                Sharing source code of the algorithms would also be a valuable option.

                Issue 4: Real-life falls
                Most studies use data of simulated ADL and falls from young or mature people. Even
                assuming they were made publicly available for a fair comparison among different methods,
                it is unclear whether the simulated activities are representative of their real counterparts.
                Since it is not acceptable to subject older people to simulated falls, the evaluation of
                the detectors is severely limited. Only few studies present acceleration data from the
                real-life falls of older people [64,65], but the number of events recorded remain low. In
                addition, the mechanisms of the falls are not known as they could not be accurately
                documented [36].


## Conclusion
                In conclusion, fall detection is a complex process for which currently there is not a
                standardized solution. Fall detectors are essential in order to provide a rapid assistance
                and to prevent fear of falling and their adverse health consequences. This review pro-
                vides a classification for fall detectors from the analysis of several studies, examines
                their evolution over time, and ultimately identifies the challenges, issues and trends in
                fall detection systems.
                  The number of studies in vision-based systems is still increasing. Besides, there is a
                new trend towards the integration of fall detectors into smartphones, but their use in
                real-world scenarios can still be compromised by the factors highlighted in this paper.
                Both biomedical engineers and clinicians should become aware of the limitations and
                potential of fall detection systems.

                Abbreviations
                ADL: Activities of daily living; SE: Sensitivity; SP: Specificity; TBM: Threshold-based method; MLM: Machine Learning Method.

                Competing interests
                The authors declare that they have no competing interests.

                Authors’ contributions
                RI and CM carried out the research and drafted the manuscript. IP participated in its design, performed the statistical
                analysis and revised it critically for important intellectual content. All authors read and approved the final manuscript.

## Acknowledgments
                This work was supported by the “European Social Fund”, the “Departamento de Ciencia, Tecnología y Universidad, Gobierno
                de Aragón" and the “Departamento de Industria e Innovación, Gobierno de Aragón (CTPP 11/12 sMartxan basic)”.

                Received: 9 April 2013 Accepted: 1 July 2013
                Published: 6 July 2013

## References
                1. World Health Organization: Global report on falls prevention in older age. [http://www.who.int/ageing/publications/
                    Falls_prevention7March.pdf]
                2. Friedman SM, Munoz B, West SK, Rubin GS, Fried LP: Falls and Fear of Falling: Which Comes First? A Longitudinal
                    Prediction Model Suggests Strategies for Primary and Secondary Prevention. J Am Geriatr Soc 2002, 50:1329–1335.
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                                                                Page 22 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                3.    Scheffer AC, Schuurmans MJ, van Dijk N, van der Hooft T, de Rooij SE: Fear of falling: measurement strategy,
                      prevalence, risk factors and consequences among older persons. Age Ageing 2008, 37:19–24.
                4.    Brownsell S, Hawley MS: Automatic fall detectors and the fear of falling. J Telemed Telecare 2004, 10:262–266.
                5.    Rubenstein LZ, Josephson KR: The epidemiology of falls and syncope. Clin Geriatr Med 2002, 18:141–58.
                6.    Tinetti MD, Liu WL, Claus EB: Predictors and prognosis of inability to get up after falls among elderly persons.
                      J Am Med Assoc 1993, 269(1):65–70.
                7.    Lord SR, Sherrington C, Menz HB: Falls in older people. Risk, factors and strategies for prevention. Cambridge:
                      Cambridge University Press; 2001.
                8.    Noury N, Fleury A, Rumeau P, Bourke AK, Laighin GO, Rialle V, Lundy JE: Fall detection - principles and methods.
                      In Proceedings of the Annual International Conference of the IEEE Engineering in Medicine and Biology Society. Lyon:
                      Institute of Electrical and Electronics Engineers; 2007:1663–1666. doi:10.1109/IEMBS.2007.4352627. http://ieeexplore.
                      ieee.org/xpl/login.jsp?tp=&arnumber=4352627&url=http%3A%2F%2Fieeexplore.ieee.org%2Fxpls%2Fabs_all.jsp%
                      3Farnumber%3D4352627.
                9.    Bagala F, Becker C, Cappello A, Chiari L, Aminian K, Hausdorff JM, Zijlstra W, Klenk J: Evaluation of Accelerometer-Based
                      Fall Detection Algorithms on Real-World Falls. PLoS One 2012, 7:e37062.
                10.   Noury N, Rumeau P, Bourke AK, OLaighin G, Lundy JE: A proposal for the classification and evaluation of fall
                      detectors. Irbm 2008, 29:340–349.
                11.   Perry JT, Kellog S, Vaidya SM, Youn JH, Ali H, Sharif H: Survey and evaluation of real-time fall detection approaches.
                      In Proceedings of the 6th International Symposium High-Capacity Optical Networks and Enabling Technologies. Alexandria:
                      Institute of Electrical and Electronics Engineers; 2009:158–164. doi:10.1109/HONET.2009.5423081. http://ieeexplore.ieee.
                      org/xpl/login.jsp?tp=&arnumber=5423081&url=http%3A%2F%2Fieeexplore.ieee.org%2Fxpls%2Fabs_all.jsp%
                      3Farnumber%3D5423081.
                12.   Mubashir M, Shao L, Seed L: A survey on fall detection: Principles and approaches. Neurocomputing 2012,
                      100:144–152.
                13.   Parikh R, Mathai A, Parikh S, Sekhar GC, Thomas R: Understanding and using sensitivity, specificity and
                      predictive values. Indian J Ophthalmol 2008, 56:45–50.
                14.   Rougier C, Meunier J, St-Arnaud A, Rousseau J: Robust video surveillance for fall detection based on human
                      shape deformation. IEEE Trans Circuits Syst for Video Technol 2011, 21:611–622.
                15.   Miaou SG, Sung PH, Huang CY: A customized human fall detection system using omni-camera images and
                      personal information. In Proceedings of the 1st Distributed Diagnosis and Home Healthcare Conference. Arlington:
                      Institute of Electrical and Electronics Engineers; 2006:39–42. doi:10.1109/DDHH.2006.1624792. http://ieeexplore.
                      ieee.org/xpl/articleDetails.jsp?arnumber=1624792.
                16.   Fu Z, Delbruck T, Lichtsteiner P, Culurciello E: An address-event fall detector for assisted living applications.
                      IEEE Trans Biomed Circuits Syst 2008, 2:88–96.
                17.   Hazelhoff L, Han J, de With PHN: Video-based fall detection in the home using principal component analysis.
                      In Proceedings of the 10th International Conference on Advanced Concepts for Intelligent Vision Systems. Edited by
                      Bland-Talon J, Bourennane S, Philips W, Popescu D, Scheunders P. Juan-les-Pins: Springer-Verlag Berlin; 2008:298–309.
                      doi:10.1007/978-3-540-88458-3_27. http://citeseerx.ist.psu.edu/viewdoc/summary?doi=10.1.1.139.4748.
                18.   Mastorakis G, Makris D: Fall detection system using Kinect’s infrared sensor. J Real-Time Image Proc 2012:1–12.
                      doi:10.1007/s11554-012-0246-9. http://link.springer.com/article/10.1007%2Fs11554-012-0246-9.
                19.   Cucchiara R, Rita H, Prati A, Andrea O, Vezzani R, Roberto C: A multi-camera vision system for fall detection and
                      alarm generation. Expert Syst 2007, 24:334–345.
                20.   Lee T, Mihailidis A: An intelligent emergency response system: preliminary development and testing of
                      automated fall detection. J Telemed Telecare 2005, 11:194–198.
                21.   Vishwakarma V, Mandal C, Sural S: Automatic detection of human fall in video. Lect Notes Comput Sci Pattern
                      Recognit Mach Intell 2007, 4815:616–623.
                22.   Anderson D, Luke RH, Keller JM, Skubic M, Rantz M, Aud M: Linguistic summarization of video for fall detection
                      using voxel person and fuzzy logic. Comput Vis Image Underst 2009, 113:80–89.
                23.   Liu CL, Lee CH, Lin PM: A fall detection system using k-nearest neighbor classifier. Expert Syst Appl 2010,
                      37:7174–7181.
                24.   Diraco G, Leone A, Siciliano P: An active vision system for fall detection and posture recognition in elderly
                      healthcare. In Conference & Exhibition: Design, Automation & Test in Europe. Dresden: European Design and
                      Automation Association; 2010:1536–1541. doi:10.1109/DATE.2010.5457055. http://ieeexplore.ieee.org/xpl/login.jsp?
                      tp=&arnumber=5457055&url=http%3A%2F%2Fieeexplore.ieee.org%2Fxpls%2Fabs_all.jsp%3Farnumber%3D5457055.
                25.   Tzeng HW, Chen MY, Chen JY: Design of fall detection system with floor pressure and infrared image. In Proceedings
                      of the International Conference on System Science and Engineering. Taipei: Institute of Electrical and Electronics Engineers;
                      2010:131–135. doi:10.1109/ICSSE.2010.5551751. http://ieeexplore.ieee.org/xpl/login.jsp?tp=&arnumber=5551751&url=http%
                      3A%2F%2Fieeexplore.ieee.org%2Fxpls%2Fabs_all.jsp%3Farnumber%3D5551751.
                26.   Edgcomb A, Vahid F: Privacy perception and fall detection accuracy for in-home video assistive monitoring
                      with privacy enhancements. Spec Interest Group Health Inform Rec 2012, 2(2):6–15.
                27.   Zhang C, Tian Y, Capezuti E: Privacy preserving automatic fall detection for elderly using RGBD cameras.
                      In Proceedings of the 13th International Conference on Computers Helping People with Special Needs. Edited by
                      Miesenberger K, Karshmer A, Penaz P, Zagler W. Linz: Springer-Verlag Berlin; 2012:625–633. doi:10.1109/ICSSE.2010.5551751.
                      http://ieeexplore.ieee.org/xpl/login.jsp?tp=&arnumber=5551751&url=http%3A%2F%2Fieeexplore.ieee.org%2Fxpls%
                      2Fabs_all.jsp%3Farnumber%3D5551751.
                28.   Rimminen H, Lindström J, Linnavuo M, Sepponen R: Detection of falls among the elderly by a floor sensor
                      using the electric near field. IEEE Trans Inf Technol Biomed 2010, 14:1475–1476.
                29.   Li Y, Ho KC, Popescu M: A microphone array system for automatic fall detection. IEEE Trans Biomed Eng 2012,
                      59:1291–1301.
                30.   Mann S: Wearable Computing. http://www.interaction-design.org/encyclopedia/wearable_computing.html.
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                                                       Page 23 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                31. Culhane KM, O’Connor M, Lyons D, Lyons GM: Accelerometers in rehabilitation medicine for older adults. Age Ageing
                    2005, 34:556–560.
                32. Alpaydin E: Introduction to Machine Learning. New Haven: The MIT Press; 2004.
                33. Lindemann U, Hock A, Stuber M, Keck W, Becker C: Evaluation of a fall detector based on accelerometers: A pilot
                    study. Med Biol Eng Comput 2005, 43:548–551.
                34. Chen J, Kwong K, Chang D, Luk J, Bajcsy R: Wearable Sensors for Reliable Fall Detection. In Proceedings of the
                    IEEE Engineering in Medicine and Biology 27th Annual Conference. Shanghai: Institute of Electrical and Electronics
                    Engineers; 2005:1–4. doi:10.1109/IEMBS.2005.1617246. http://ieeexplore.ieee.org/xpl/login.jsp?
                    tp=&arnumber=1617246&url=http%3A%2F%2Fieeexplore.ieee.org%2Fxpls%2Fabs_all.jsp%3Farnumber%3D1617246.
                35. Bourke A, O’Brien J, Lyons G: Evaluation of a threshold-based triaxial accelerometer fall detection algorithm.
                    Gait Posture 2007, 26:194–199.
                36. Kangas M, Konttila A, Lindgren P, Winblad I, Jms T: Comparison of low-complexity fall detection algorithms for
                    body attached accelerometers. Gait Posture 2008, 28:285–291.
                37. Kangas M, Vikman I, Wiklander J, Lindgren P, Nyberg L, Jämsä T: Sensitivity and specificity of fall detection in
                    people aged 40 years and over. Gait Posture 2009, 29:571–574.
                38. Li Q, Stankovic JA, Hanson M, Barth A, Lach J: Accurate, fast fall detection using gyroscopes and accelerometer-
                    derived posture information. In Proceedings of the 6th International Workshop on Wearable and Implantable Body
                    Sensor Networks. Edited by Lo B, Mitcheson P. Berkeley; 2009:138–143. doi:10.1109/BSN.2009.46. http://ieeexplore.
                    ieee.org/xpl/login.jsp?tp=&arnumber=5226903&url=http%3A%2F%2Fieeexplore.ieee.org%2Fxpls%2Fabs_all.jsp%
                    3Farnumber%3D5226903.
                39. Bianchi F, Redmond SJ, Narayanan MR, Cerutti S, Lovell NH: Barometric pressure and triaxial accelerometry-based
                    falls event detection. IEEE Trans Neural Syst Rehabil Eng 2010, 18:619–627.
                40. Bourke AK, de Ven V, Gamble M, O'Connor R, Murphy K, Bogan E, McQuade E, Finucane P, OLaighin G, Nelson J:
                    Assessment of waist-worn tri-axial accelerometer based fall-detection algorithms using continuous
                    unsupervised activities. In Proceedings of the Annual International Conference of the IEEE Engineering in Medicine
                    and Biology Society. Buenos Aires: Institute of Electrical and Electronics Engineers; 2010:2782–2785. doi:10.1109/
                    IEMBS.2010.5626364. http://ieeexplore.ieee.org/xpl/login.jsp?tp=&arnumber=5626364&url=http%3A%2F%
                    2Fieeexplore.ieee.org%2Fiel5%2F5608545%2F5625939%2F05626364.pdf%3Farnumber%3D5626364.
                41. Lai CF, Chang SY, Chao HC, Huang YM: Detection of cognitive injured body region using multiple triaxial
                    accelerometers for elderly falling. IEEE Sensors J 2011, 11:763–770.
                42. Shan S, Yuan T: A wearable pre-impact fall detector using feature selection and support vector machine.
                    In Proceedings of the IEEE 10th International Conference on Signal Processing. Beijing: Institute of Electrical and
                    Electronics Engineers; 2010:1686–1689. doi:10.1109/ICOSP.2010.5656840. http://ieeexplore.ieee.org/xpl/login.jsp?
                    tp=&arnumber=5656840&url=http%3A%2F%2Fieeexplore.ieee.org%2Fxpls%2Fabs_all.jsp%3Farnumber%3D5656840.
                43. Yuwono M, Moulton B, Su S, Celler B, Nguyen H: Unsupervised machine-learning method for improving the
                    performance of ambulatory fall-detection systems. Biomed Eng Online 2012, 11:1–11.
                44. Kerdegari H, Samsudin K, Ramli AR, Mokaram S: Evaluation of fall detection classification approaches. In Proceedings
                    of the 4th International Conference on Intelligent and Advanced Systems. Kuala Lumpur: Institute of Electrical and
                    Electronics Engineers; 2012:131–136. doi:10.1109/ICIAS.2012.6306174. http://ieeexplore.ieee.org/xpl/login.jsp?
                    tp=&arnumber=6306174&url=http%3A%2F%2Fieeexplore.ieee.org%2Fxpls%2Fabs_all.jsp%3Farnumber%3D6306174.
                45. Zhang T, Wang J, Xu L, Liu P: Fall detection by wearable sensor and one-class SVM algorithm. In Lecture Notes
                    in Control and Information Science, Volume 345. Edited by Huang DS, Li K, Irwin GW. Berlin Heidelberg: Springer;
                    2006:858–863.
                46. Doukas C, Maglogiannis I, Tragkas F, Liapis D, Yovanof G: Patient Fall Detection using Support Vector Machines.
                    Int Fed Inf Process 2007, 247:147–156.
                47. Cheng J, Chen X, Shen M: A framework for daily activity monitoring and fall detection based on surface
                    electromyography and accelerometer signals. IEEE J Biomed and Health Inform 2013, 17(1):38–45.
                48. Lane N, Miluzzo E, Lu H, Peebles D, Choudhury T, Campbell A: A survey of mobile phone sensing. IEEE Commun
                    Mag 2010, 48:140–150.
                49. Sposaro F, Tyson G: iFall: an Android application for fall monitoring and response. In Proceedings of the Annual
                    International Conference of the IEEE Engineering in Medicine and Biology Society. Minneapolis: Institute of Electrical
                    and Electronics Engineers; 2009:6119–6122. doi:10.1109/IEMBS.2009.5334912. http://ieeexplore.ieee.org/xpl/
                    articleDetails.jsp?arnumber=5334912.
                50. Dai J, Bai X, Yang Z, Shen Z, Xuan D: Mobile phone-based pervasive fall detection. Pers Ubiquitous Comput 2010,
                    14:633–643.
                51. Lopes IC, Vaidya B, Rodrigues J: Towards an autonomous fall detection and alerting system on a mobile and
                    pervasive environment. Telecommun Syst 2011, 48:1–12.
                52. Lee RYW, Carlisle AJ: Detection of falls using accelerometers and mobile phone technology. Age Ageing 2011, 0:1–7.
                53. Fang SH, Liang YC, Chiu KM: Developing a mobile phone-based fall detection system on android platform.
                    In Proceedings of the Conference on Computing, Communications and Applications. Hong Kong: Institute of
                    Electrical and Electronics Engineers; 2012:143–146. doi:10.1109/ComComAp.2012.6154019. http://ieeexplore.
                    ieee.org/xpl/login.jsp?tp=&arnumber=6154019&url=http%3A%2F%2Fieeexplore.ieee.org%2Fiel5%2F6145284%
                    2F6153941%2F06154019.pdf%3Farnumber%3D6154019.
                54. Albert MV, Kording K, Herrmann M, Jayaraman A: Fall classification by machine learning using mobile phones.
                    PLoS One 2012, 7:e36556.
                55. Abbate S, Avvenuti M, Bonatesta F, Cola G, Corsini P, Vecchio A: A smartphone-based fall detection system.
                    Pervasive Mob Comput 2012, 8:883–899.
                56. Google Play. [https://play.google.com/store?hl=en]
                57. Bagchi KK, Kirs P, Lopez F: The impact of price decreases on telephone and cell phone diffusion. Inf Manag
                    2008, 45:183–193.
Igual et al. BioMedical Engineering OnLine 2013, 12:66                                                                                         Page 24 of 24
http://www.biomedical-engineering-online.com/content/12/1/66




                58. Roupa Z, Νikas M, Gerasimou E, Zafeiri V, Giasyrani L, Κazitori E, Sotiropoulou P: The use of technology by the elderly.
                    Health Sci J 2010, 4:118–126.
                59. Kurniawan S: Older people and mobile phones: A multi-method investigation. Int J Human-Comput Stud 2008,
                    66:889–901.
                60. Plaza I, Martin L, Martin S, Medrano C: Mobile applications in an aging society: Status and trends. J Syst Softw
                    2011, 84:1977–1988.
                61. Drost C: Privacy in context-aware systems. [http://www.utwente.nl/ewi/asna/assignments/completed/drost.pdf]
                62. Baldauf M: A survey on context-aware systems. Int J Ad Hoc and Ubiquitous Comput 2007, 2(4):263–277.
                63. Sensors and In-Home Collection of Health Data: A Privacy by Design Approach. [http://www.ipc.on.ca/images/
                    Resources/pbd-sensor-in-home.pdf]
                64. Kangas M, Vikman I, Nyberg L, Korpelainen R, Lindblom J, Jms T: Comparison of real-life accidental falls in older
                    people with experimental falls in middle-aged test subjects. Gait Posture 2012, 35:500–505.
                65. Klenk J, Becker C, Lieken F, Nicolai S, Maetzler W, Alt W, Zijlstra W, Hausdorff JM, van Lummel RC, Chiari L,
                    Lindemann U: Comparison of acceleration signals of simulated and real-world backward falls. Med Eng Phys
                    2011, 33:368–373.
                66. Degen T, Jaeckel H, Rufer M, Wyss S: SPEEDY: A fall detector in a wrist watch. In Proceedings of the 7th
                    International Symposium on Wearable Computers. New York: IEEE Computer Society; 2003:184–187. doi:10.1109/
                    ISWC.2003.1241410. http://ieeexplore.ieee.org/xpl/login.jsp?tp=&arnumber=1241410&url=http%3A%2F%
                    2Fieeexplore.ieee.org%2Fxpls%2Fabs_all.jsp%3Farnumber%3D1241410.

                  doi:10.1186/1475-925X-12-66
                  Cite this article as: Igual et al.: Challenges, issues and trends in fall detection systems. BioMedical Engineering
                  OnLine 2013 12:66.




                                                                    Submit your next manuscript to BioMed Central
                                                                    and take full advantage of:

                                                                    • Convenient online submission
                                                                    • Thorough peer review
                                                                    • No space constraints or color ﬁgure charges
                                                                    • Immediate publication on acceptance
                                                                    • Inclusion in PubMed, CAS, Scopus and Google Scholar
                                                                    • Research which is freely available for redistribution


                                                                    Submit your manuscript at
                                                                    www.biomedcentral.com/submit

