Applied Intelligence (2024) 54:8982–9007
https://doi.org/10.1007/s10489-024-05645-1




Deep learning for computer vision based activity recognition and fall
detection of the elderly: a systematic review
F. Xavier Gaya-Morey1,2,3           · Cristina Manresa-Yee1,2,3     · José M. Buades-Rubio1,2,3

Accepted: 25 June 2024 / Published online: 8 July 2024
© The Author(s) 2024


## Abstract
As the proportion of elderly individuals in developed countries continues to rise globally, addressing their healthcare needs,
particularly in preserving their autonomy, is of paramount concern. A growing body of research focuses on Ambient Assisted
Living (AAL) systems, aimed at alleviating concerns related to the independent living of the elderly. This systematic review
examines the literature pertaining to fall detection and Human Activity Recognition (HAR) for the elderly, two critical tasks for
ensuring their safety when living alone. Specifically, this review emphasizes the utilization of Deep Learning (DL) approaches
on computer vision data, reflecting current trends in the field. A comprehensive search yielded 2,616 works from five distinct
sources, spanning the years 2019 to 2023 (inclusive). From this pool, 151 relevant works were selected for detailed analysis.
The review scrutinizes the employed DL models, datasets, and hardware configurations, with particular emphasis on aspects
such as privacy preservation and real-world deployment. The main contribution of this study lies in the synthesis of recent
advancements in DL-based fall detection and HAR for the elderly, providing insights into the state-of-the-art techniques
and identifying areas for further improvement. Given the increasing importance of AAL systems in enhancing the quality
of life for the elderly, this review serves as a valuable resource for researchers, practitioners, and policymakers involved in
developing and implementing such technologies.

Keywords Human activity recognition · Fall detection · Ambient assisted living · Deep learning · Computer vision · Elderly



## 1 Introduction
F. Xavier Gaya-Morey, Cristina Manresa-Yee and José M. Buades-
Rubio contributed equally to this work
                                                                      The global population is experiencing rapid growth, accom-
B F. Xavier Gaya-Morey                                                panied by a significant increase in life expectancy, particu-
    francesc-xavier.gaya@uib.es                                       larly in developed countries. Bloom and Luca [1] note that
    Cristina Manresa-Yee                                              life expectancy in China and India has surged by nearly 30
    cristina.manresa@uib.es                                           years since 1950. Consequently, a substantial portion of the
    José M. Buades-Rubio                                              population in developed nations, approximately 20%, is aged
    josemaria.buades@uib.es                                           60 and above, a figure projected to surpass 30% in the next
1
                                                                      four decades.
    Group of Computer Graphics, Computer Vision and AI
                                                                          With this demographic shift comes a growing concern
    (UGIVIA), Universitat de les Illes Balears (UIB), Carretera
    de Valldemossa, km 7.5, Palma 07122, Illes Balears, Spain         for elderly1 care, as the need for assistance and support
2                                                                     rises proportionately. Among the myriad challenges faced
    Research Institute of Health Sciences (IUNICS), Universitat
    de les Illes Balears (UIB), Carretera de Valldemossa, km 7.5,
    Palma 07122, Illes Balears, Spain                                 1 In this work, the term “elderly” refers to individuals over 65 years
## 3   Department of Mathematics and Computer Science,                   old, as commonly used in the field of Computer Science. However, ter-
    Universitat de les Illes Balears (UIB), Carretera de              minology may vary in other fields; for instance, the term “older adults”
    Valldemossa, km 7.5, Palma 07122, Illes Balears, Spain            is often preferred in Psychology.




123
Deep learning for computer vision based activity recognition...                                                               8983


by the elderly, falls represent a particularly prevalent and      reviews prior to conducting the SLR, thereby substantiat-
perilous occurrence. The World Health Organization high-          ing its necessity. Hence, we briefly outline related reviews
lights alarming statistics on falls, identifying them as the      and surveys from the past three years, as older reviews can-
second leading cause of unintentional injury deaths world-        not encompass the most recent studies. The full list can be
wide. Each year, an estimated 684,000 individuals succumb         found in Table 1, providing a visual comparison of the main
to fall-related injuries globally, with an additional 37.3 mil-   disparities.
lion falls severe enough to necessitate medical attention             Guerra et al. [9] studied the current state-of-the-art of
[2]. Apart from the physical harm incurred by the elderly,        Ambient Assisted Living (AAL) for frail individuals, includ-
the economic ramifications are substantial, with fall-related     ing the elderly and disabled, encompassing both wearable
treatment costs comprising a significant portion of healthcare    and non-wearable solutions. They explored common steps
expenditures in various countries such as the USA, Australia,     in the Human Activity Recognition (HAR) processing chain.
EU15 and the United Kingdom [3].                                  Similarly, Kumar et al. [10] delved into various types of data
   Automated fall detection for the elderly is feasible through   used for HAR, elucidating common datasets, approaches, and
data collected from wearable or environmental devices,            challenges, but not including the elderly population or fall
such as accelerometers, gyroscopes, and cameras. Further-         detection. In [11], Tay et al. investigated abnormal behav-
more, Human Activity Recognition (HAR) holds promise for          ior detection, such as fall detection, repetition of activities,
diverse applications, ranging from automatic life-logging to      and accidents. They explored multiple solutions, including
identifying patterns indicative of illness [4, 5]. Vision data    visual and wearable sensors, and both conventional and Deep
from cameras is increasingly utilized for fall detection and      Learning (DL) approaches. A review by Momin et al. [12]
HAR tasks due to its numerous advantages over wearable            explores activity pattern monitoring using depth sensors,
devices or other sensors. These advantages include the abil-      considering this visual data as a privacy-preserving alterna-
ity to detect multiple events simultaneously, suitability for     tive to RGB video or images for older adults. The studies
various subjects, environments, and tasks, as well as ease of     are categorized based on the computing technique utilized
installation and visual verification of data [6].                 and the datasets used are analyzed. Olugbade et al. [13] con-
   From an algorithmic standpoint, Deep Learning (DL) has         ducted a scoping review on datasets utilized for HAR and
revolutionized digital image processing, emerging as the          fall detection, resulting in an extensive compilation of over
state-of-the-art approach in numerous domains [7]. Over           700 datasets of various modalities. Multiple taxonomies were
recent years, a plethora of DL architectures have been devel-     developed to categorize the datasets by population groups,
oped and evaluated for computer vision tasks, prompting the       data types, and creation purposes, among others, although
exploration of suitable models for HAR and fall detection         only four datasets include elderly subjects. Alam et al. [14]
among older adults.                                               conducted a review specifically on DL-based fall detection
   In this study, we conduct a Systematic Literature Review       systems, analyzing different fall types, popular datasets, eval-
(SLR) focusing on DL-based HAR and fall detection using           uation metrics, and architectural variations. Rastogi et al. [15]
vision data for elderly care. Our review strictly adheres to      reviewed a broader range of tasks, including falls and other
the guidelines outlined for conducting SLRs in Software           relevant information extracted from video sequences, such
Engineering by Kitchenham and Charters [8], providing a           as body shape changes, posture, and gait. Another relevant
structured methodology and rigorous analysis. The document        review is by Gutiérrez et al. [16], also centered on fall detec-
is structured as follows: we first delve into the background      tion, which describes common processing steps, ML models,
of the study, encompassing previous reviews and defining          datasets, metrics, and tracking techniques, with most studies
key concepts; we then enumerate the review questions; next,       utilizing RGB and depth data.
we elaborate on the review methods, detailing data sources,           While prior reviews have addressed various aspects of our
search strategy, study selection, quality assessment, and data    research domain, notable differences underscore the neces-
extraction; subsequently, we analyze the resulting studies        sity of our study. Table 1 sheds light upon this by displaying
comprehensively to address the review questions; the dis-         the pivotal aspects considered in the current review, along
cussion section synthesizes our findings and addresses the        with whether they are addressed or not in the aforementioned
review questions; finally, we present the conclusions derived     reviews.
from the SLR.                                                         The sole review exclusively focusing on DL techniques
                                                                  was conducted by Alam et al. [14], which, however, omitted
                                                                  HAR from its scope, thus neglecting a significant portion of
## 2 Background                                                      studies included in our analysis. In contrast, other reviews
                                                                  encompassed techniques employing handcrafted features or
In accordance with the guidelines provided by Kitchenham          classical vision approaches, reflecting a broader scope than
and Charters [8], it is imperative to summarize previous          our exclusive focus on DL-based solutions. Furthermore,


                                                                                                                        123
8984                                                                                                                                 G.M F. Xavier et al.


Table 1 Comparison of previous reviews with ours
Work       Year      System       Focus                          Task                 Data                         AAL
                                  DL       Elderly      CV       FD       HAR         RGB       Depth      IR      Privacy      HW        Deployment

Ours       2024      ✓            ✓        ✓            ✓        ✓        ✓           ✓         ✓          ✓       ✓            ✓         ✓
[9]        2023                            ✓                     ✓        ✓           ✓         ✓          ✓       ✓
[10]       2023                                                           ✓           ✓         ✓
[11]       2023                            ✓                     ✓                    ✓         ✓          ✓
[12]       2022                            ✓            ✓        ✓        ✓                     ✓                  ✓
[13]       2022      ✓                                           ✓        ✓           ✓         ✓          ✓
[14]       2022                   ✓        ✓            ✓        ✓                    ✓         ✓          ✓       ✓
[15]       2022                            ✓            ✓        ✓        ✓           ✓         ✓          ✓
[16]       2021                            ✓            ✓        ✓                    ✓         ✓          ✓
By columns, important aspects taken into account in this review, and whether they are addressed or not by each review. From left to right: if the
review is systematic; focuses on the exploration of DL solutions; targets elderly people as the users of the system; centers on the use of vision data;
explores the Fall Detection and the Human Activity Recognition tasks; explores the use of RGB, depth or infrared data; takes privacy as a critical
concern; describes the hardware used in the found studies; and if it studies the deployment of the FD and HAR systems in real environments


previous reviews often overlooked the importance of study-                    3 Review questions
ing DL-related nuances, such as the significance of training
datasets, architectural considerations, and feature extraction                As outlined in [8], specifying the research questions is a crit-
methods. In our review, we meticulously categorize and elu-                   ical aspect of any systematic review, as they guide the entire
cidate these nuances through a comprehensive taxonomy of                      methodology: from the search process identifying primary
identified techniques.                                                        studies to address them, to the data extraction process extract-
   Another notable observation is the limited attention given                 ing the required data items, and finally to the data analysis
to HAR in several previous reviews, with some omitting                        synthesizing the data to answer the questions. The review
the task altogether. As a result, our review unveils a greater                questions for this study are presented in Table 2.
number of studies dedicated to fall detection and HAR in                         The first research question, RQ1, aims to identify the
the elderly. Additionally, our analysis delves deeper into the                methods used to recognize activities or detect falls among
intricacies of these tasks, providing a more comprehensive                    elderly individuals. The choice to specifically investigate
understanding.                                                                HAR and fall detection stemmed from an exploratory ini-
   Moreover, only a few reviews explored applications within                  tial search, where they emerged as the two most relevant
AAL systems and the associated privacy implications. Hard-                    recognition tasks in AAL for the elderly. Given that visual
ware specifications, beyond the prevalent use of Kinect                       data offers numerous advantages over other sensor data types,
cameras, were rarely examined, and the effective deploy-
ment of fall detection or HAR systems was not thoroughly
                                                                              Table 2 Primary and secondary research questions used for this SLR
explored. In contrast, our review emphasizes these aspects,
which are pivotal in facilitating the transference to society.                ID             Research question
   Finally, it is worth noting that, apart from [13], none of                 RQ1            What computer vision deep learning techniques are
the previous reviews adhered to a systematic review process.                                 used for human
By rigorously following the systematic review methodol-                                      activity recognition and fall detection on elderly peo-
ogy outlined by Kitchenham and Charters [8], our study                                       ple?
ensures a robust and unbiased selection and analysis of rel-                  RQ1.1          What is the preferred data type?
evant studies. We conducted a comprehensive search across                     RQ1.2          What are the most extensively used architectures?
various databases, employing well-defined search strings                      RQ1.3          What are the most extended datasets?
aligned with our research questions. Each study underwent
                                                                              RQ2            How can these tasks be deployed successfully in a real
careful quality assessment, and strict exclusion criteria were                               environment?
applied to ensure the inclusion of only the most relevant and                 RQ2.1          What is the most common hardware (cameras, robots,
high-quality literature. This systematic approach minimizes                                  etc.)?
potential biases and ensures that our review is based on a                    RQ2.2          How is privacy of the elderly preserved?
well-rounded selection of literature.




123
Deep learning for computer vision based activity recognition...                                                                8985


such as visual verification and simultaneous subject recog-            SCOPUS and WOS were chosen as comprehensive digi-
nition, and DL has become the state-of-the-art approach in         tal libraries covering a wide range of disciplines, while IEEE
computer vision, conducting an in-depth analysis of the most       Xplore focuses on engineering and technology, ACM Digi-
prevalent methods with these characteristics is crucial for        tal Library specializes in computer science, and PubMed is
informing future research in this domain. Furthermore, three       centered on biomedical studies. This selection ensures the
research subquestions are included regarding common data           inclusion of relevant literature from diverse domains, maxi-
types (e.g., RGB, depth, thermal, etc.), DL architectures (e.g.,   mizing the breadth of content considered in our review.
CNN, RNN, etc.), and datasets found in the reviewed litera-            The distribution of studies retrieved from each source is
ture. These subquestions aim to delve deeper into the solution     illustrated in Fig. 1. As depicted, the majority of studies were
choices at different design steps, which are closely related to    sourced from ACM and SCOPUS, with only a small fraction
various requirements such as privacy preservation, result sta-     (110 out of a total of 2,616) obtained from PubMed.
bility, and inference speed.
   The second research question, RQ2, emerges as a sig-            4.2 Search strategy
nificantly unexplored area, as highlighted in Table 1 of the
Background section. Many previous reviews have focused             We constructed different query strings tailored to match the
on the recognition phase of previous studies, enumerating          syntax of each digital library while minimizing differences
common methods, processing steps, and datasets. However,           and employing consistent synonyms for the concepts being
the effective deployment in real-world scenarios is pivotal        searched. Each query string connected the various concepts
for the transfer of such methods to society, and this aspect       using logical AND, while synonyms for each concept were
remains largely unexplored. Works with implementations in          connected with logical OR. To account for inflection of cer-
real environments, whether through the use of assistive robots     tain keywords, we utilized the “*” operator after the root
or camera-based setups, are expected to be found among             word to allow for any possible word endings. In the SCO-
the selected studies. Therefore, it is desirable to explore        PUS library, the search was restricted to titles, abstracts, or
their design choices, setups, and encountered challenges in        keywords due to the impracticality of retrieving results other-
greater depth. Additionally, privacy is a particularly concern-    wise, with the majority being poorly relevant. Conversely, the
ing aspect to consider when dealing with users, especially         entire text was searched for in the remaining databases. The
when utilizing visual data from cameras, and the approaches        primary concepts searched, along with their corresponding
to addressing it are of interest for future research. For these    lists of synonyms, are as follows:
reasons, RQ2.1 and RQ2.2 delve into common hardware
choices and privacy preservation strategies.
                                                                    • Task to perform (activity recognition or fall detec-
                                                                      tion): “action recognition” OR “activit* recognition”
## 4 Review methods                                                      OR “fall* detection” OR “behaviour recognition” OR
                                                                      “behaviour detection” OR “physical activity recogni-
In this section, we provide a detailed description of the sys-        tion”
tematic review protocol followed, based on the guidelines
outlined by Kitchenham and Charters [8]. Firstly, we list and
analyze the primary data sources used, providing visualiza-
tion of the distribution of studies among these sources. Next,
we define the search strategy, which encompasses search
terms, synonyms, and time restrictions. Following this, we
establish criteria for inclusion and exclusion of studies, fol-
lowed by the design of a quality assessment checklist to
identify and remove low-quality studies. Finally, in the data
extraction and synthesis stage, we define how information
from each primary study is obtained and outline the specific
attributes considered of interest.

## 4.1 Data sources

For this systematic review, we selected five primary data          Fig. 1 Number of publications obtained from each database, before
sources: SCOPUS, Web of Science (WOS), IEEE Xplore                 duplicate removal and study selection (2616 in total)
Digital Library, ACM Digital Library, and PubMed.


                                                                                                                         123
8986                                                                                                                      G.M F. Xavier et al.


 • Ambient Assisted Living: “monitoring” OR “assist*                   and images. Skeleton data was also included, but only if
   living” OR “AAL” OR “smart home” OR “activit* of                    computed from the other three types of data. Studies using
   daily life” OR “activit* of daily living” OR “ADL”                  sensory data along with visual data were also included,
 • Target collective (elderly people): “elder*” OR “old*               allowing for multimodal approaches.
   people” OR “senior”                                               • Accessibility: Studies not accessible for various reasons,
 • Kind of data used (Computer Vision): “vision” OR                    such as being part of paid content (e.g., book chap-
   “rgb” OR “video” OR “image” OR “skeleton” OR                        ters), source website down, or retracted content, were
   “depth” OR “camera” OR “gesture”                                    excluded.
                                                                     • Redundancy: In cases where a journal article extended
   Initially, we included studies published from 2013 onwards          a work already presented in a conference, the conference
in the search. However, upon further examination, we                   proceedings publications were omitted, as the journal
observed that the majority of relevant studies were published          article represented an extension of the same work.
recently. Consequently, we decided to limit the review to the        • Task: Studies focused on tasks other than HAR or fall
last five years. Figure 2 displays the accumulated relevant            detection, such as velocity estimation, gait trend, level of
studies from 2013 to 2023. As depicted, only 19 relevant               tiredness, etc., were excluded. However, studies that did
articles were found during the first six years, while 151 were         not directly perform HAR or fall detection but presented
discovered in the last five. This trend underscores the increas-       a new dataset for these tasks were included.
ing significance of DL-based strategies for HAR and fall             • Target Collective: Studies not centered on elderly people
detection. By focusing on studies published in the last five           were excluded. Merely mentioning the elderly as one of
years, we aim to gain a deeper analysis of recent trends.              the beneficiaries of the work was insufficient; the study
                                                                       had to either use data from elderly people or have them
4.3 Study selection                                                    in mind when designing the experiment.
                                                                     • Works in Progress: Conference proceedings about
After collecting studies from various sources, limiting                works in progress, containing only the initial stages of
by year, and removing duplicates, exclusion criteria were              the study and lacking the experimentation phase, were
applied to eliminate non-relevant studies. The exclusion cri-          excluded.
teria were as follows:                                               • Quality: Publications with very poor quality (e.g.,
                                                                       null reproducibility, highly biased decisions, too small
                                                                       datasets, etc.) were excluded. More information about
 • Deep Learning: Studies not utilizing DL were consid-
                                                                       quality assessment can be found in Section 4.4.
   ered irrelevant for this review. Including this criterion
   in the exclusion criteria rather than in the query strings
   enabled the inclusion of more relevant studies, since                The results of study collection and duplicate removal are
   many studies did not directly reference DL but instead           illustrated in Fig. 3. A total of 2,616 studies were collected
   used the name of a specific model.                               from the different sources using the aforementioned queries,
 • Language: Studies not in English or Spanish were                 of which 633 duplicates were detected and removed, leaving
   excluded.                                                        a total of 1,983 studies.
 • Data Type: Studies using data types other than RGB,                  As depicted in Fig. 3, only 151 studies remained after
   depth, or IR were excluded. This includes both videos            applying the exclusion criteria, comprising 89 conference pro
                                                                    ceedings and 64 journal articles. The conference proceedings




                                                                    Fig. 3 Articles collected at each phase of the systematic search process,
Fig. 2 Accumulated publications from 2013 to 2023 (both included)   including acquisition from various sources, removal of duplicates, and
after study selection and quality assessment                        study selection, which also involved quality assessment


123
Deep learning for computer vision based activity recognition...                                                                8987


were retained for analysis among the relevant studies, as they     • Task (HAR or fall detection)
serve as a standard search strategy to address publication         • Data type (RGB, depth, IR or skeleton)
bias, which can lead to systematic bias in systematic reviews      • Auxiliary sensor data type (accelerometers, gyroscopes,
unless special efforts are made to address this issue [8].           etc.)
                                                                   • Camera used
## 4.4 Quality assessment                                             • Dataset (name of external dataset/s or “custom”)
                                                                   • DL model/s and task (skeleton joints estimation, feature
Given the absence of a universally agreed-upon definition of         extraction, classification, etc.)
study “quality,” the proposed guidelines in [8] were adhered       • Other ML models or computer vision techniques used
to, primarily focusing on bias and validity as measures of         • System integration in a robot (yes/no) and which one
quality. Specifically, the following aspects were taken into       • System integration in a framework (yes/no)
account:                                                           • How is privacy preserved? (depth or IR only, low resolu-
                                                                     tion, etc.)
 • Reproducibility: Assessing whether the work can be              • Reproducible (yes/no)
   replicated. This can be achieved by disclosing the dataset      • Test with external datasets
   used, using external datasets, and either publishing the        • Comparison with other approaches
   code used for the model or providing sufficient details to
   recreate the model.
                                                                     The complete list of relevant studies is provided in
 • Comparison with Other Works: Evaluating whether
                                                                  Tables 4 and 3, which display only basic information for
   the performance of the model is compared with the state-
                                                                  each study. The remaining information will be synthesized in
   of-the-art. It’s essential to ensure that comparisons are
                                                                  Section 5 through tables and plots, allowing for an overview
   made under fair conditions, meaning that the models
                                                                  of the distribution of works by used data types, DL model
   should be trained and tested on the same data to avoid
                                                                  families, datasets, etc. Additionally, particularly relevant or
   introducing bias.
                                                                  interesting aspects of the works will be summarized, and
 • Use of External Datasets: Considering whether the
                                                                  important concepts will be addressed in more detail.
   model is tested on external datasets to mitigate possible
   bias from the data and facilitate comparison with other
   models for the same task. Additionally, using external
   datasets allows other studies to utilize the results without   5 Results
   the need to retrain the model on different data.
                                                                  This section provides an overview of the primary studies dis-
   These aspects were included in the list of fields during       covered through the systematic search process and presents
the data extraction phase (last three fields), as discussed in    the findings. Each study is thoroughly examined, and sum-
Section 4.5. Moreover, these quality aspects were also used       maries are presented in the form of tables and graphs where
as exclusion criteria, as previously mentioned in Section 4.3.    applicable. Subsections are structured to address individual
   In addition to these aspects, the type of study, either con-   research questions, enhancing readability and organization.
ference proceedings or journal articles, was also considered
as a quality indicator, with journal articles typically being     5.1 RQ1: fall detection and human activity
longer and more mature.                                               recognition
## 4.5 Data extraction and synthesis                                 The review primarily focuses on two main tasks: fall detec-
                                                                  tion and Human Activity Recognition (HAR). It is worth
From each study remaining after applying the exclusion cri-       noting that fall detection can be viewed an especially impor-
teria, various data points were extracted to summarize the        tant activity of HAR. As illustrated in Fig. 4, fall detection has
content and establish taxonomies for various aspects of inter-    received the most attention in the past five years, with a total
est. All data were compiled into a table, with each entry         of 72 studies, while HAR has been explored in 52 studies.
containing the following fields:                                  This discrepancy highlights the significance of fall detec-
                                                                  tion when concerning the elderly population. Many works
 • Title                                                          emphasize the importance of accurately and swiftly identi-
 • Author/s                                                       fying falls among the elderly, given the potential for injuries
 • Type (journal article or conference proceedings)               and health implications if prompt actions are not taken. Con-
 • Publication year                                               sequently, several studies mention integrating fall detection


                                                                                                                        123
8988                                                                                      G.M F. Xavier et al.


Table 3 Full list of relevant
                                Ref.    Year   Task       CV Data   Ref.    Year   Task          CV Data
studies examined in this
systematic review               [17]    2023   FD         D         [18]    2022   FD            RGB
                                [19]    2023   FD         RGB       [20]    2022   FD            RGB/D/IR
                                [21]    2023   FD         RGB       [22]    2022   FD            RGB-D
                                [23]    2023   FD         RGB       [24]    2022   FD & HAR      RGB
                                [25]    2023   FD         RGB       [26]    2022   FD & HAR      RGB
                                [27]    2023   FD         RGB       [28]    2022   FD & HAR      RGB
                                [29]    2023   FD         RGB       [30]    2022   FD & HAR      RGB
                                [31]    2023   FD         RGB       [32]    2022   FD & HAR      RGB
                                [33]    2023   FD         RGB       [34]    2022   FD & HAR      RGB
                                [35]    2023   FD         RGB       [36]    2022   HAR           D
                                [37]    2023   FD         RGB       [38]    2022   HAR           D
                                [39]    2023   FD         RGB       [40]    2022   HAR           D
                                [41]    2023   FD         RGB       [42]    2022   HAR           RGB
                                [43]    2023   FD & HAR   D         [44]    2022   HAR           RGB
                                [45]    2023   FD & HAR   IR        [46]    2022   HAR           RGB
                                [47]    2023   FD & HAR   RGB       [48]    2022   HAR           RGB
                                [49]    2023   FD & HAR   RGB       [50]    2022   HAR           RGB
                                [51]    2023   FD & HAR   RGB       [52]    2022   HAR           RGB
                                [53]    2023   FD & HAR   RGB       [54]    2022   HAR           RGB
                                [55]    2023   FD & HAR   RGB       [56]    2022   HAR           RGB
                                [57]    2023   FD & HAR   RGB       [58]    2022   HAR           RGB/D
                                [59]    2023   FD & HAR   RGB       [60]    2022   HAR           RGB-D
                                [61]    2023   FD & HAR   RGB       [62]    2021   FD            RGB
                                [63]    2023   FD & HAR   RGB       [64]    2021   FD            RGB
                                [65]    2023   FD & HAR   RGB       [66]    2021   FD            RGB
                                [67]    2023   FD & HAR   RGB       [68]    2021   FD            RGB
                                [69]    2023   FD & HAR   RGB       [70]    2021   FD            RGB
                                [71]    2023   HAR        RGB       [72]    2021   FD            RGB
                                [73]    2023   HAR        RGB       [74]    2021   FD            RGB
                                [75]    2023   HAR        RGB       [76]    2021   FD            RGB
                                [77]    2023   HAR        RGB       [78]    2021   FD            RGB
                                [79]    2023   HAR        RGB       [80]    2021   FD            RGB
                                [81]    2023   HAR        RGB/D     [82]    2021   FD            RGB
                                [83]    2023   HAR        RGB-D     [84]    2021   FD            RGB
                                [85]    2023   HAR        RGB-D     [86]    2021   FD            RGB
                                [87]    2022   FD         D         [88]    2021   FD            RGB
                                [89]    2022   FD         RGB       [90]    2021   FD            RGB
                                [91]    2022   FD         RGB       [92]    2021   FD            RGB
                                [93]    2022   FD         RGB       [94]    2021   FD            RGB
                                [95]    2022   FD         RGB       [96]    2021   FD            RGB
                                [97]    2022   FD         RGB       [98]    2021   FD            RGB/D
                                [99]    2022   FD         RGB       [100]   2021   FD & HAR      RGB
                                [101]   2022   FD         RGB       [102]   2021   FD & HAR      RGB
                                [103]   2022   FD         RGB       [104]   2021   FD & HAR      RGB
                                [105]   2022   FD         RGB       [106]   2021   FD & HAR      RGB
                                [107]   2022   FD         RGB       [108]   2021   FD & HAR      RGB
                                [109]   2022   FD         RGB       [110]   2021   HAR           D
                                [111]   2022   FD         RGB       [112]   2021   HAR           D




123
Deep learning for computer vision based activity recognition...                                                                               8989


Table 3 continued
                                       Ref.          Year         Task             CV Data         Ref.         Year        Task         CV Data

                                       [113]         2021         HAR              D               [114]        2020        HAR          RGB
                                       [115]         2021         HAR              D               [116]        2020        HAR          RGB
                                       [117]         2021         HAR              D               [118]        2020        HAR          RGB-D
                                       [119]         2021         HAR              IR              [120]        2020        HAR          RGB-D
                                       [121]         2021         HAR              RGB             [122]        2019        FD           IR
                                       [123]         2021         HAR              RGB             [124]        2019        FD           RGB
                                       [125]         2021         HAR              RGB             [126]        2019        FD           RGB
                                       [127]         2021         HAR              RGB             [128]        2019        FD           RGB
                                       [129]         2021         HAR              RGB             [130]        2019        FD           RGB
                                       [131]         2021         HAR              RGB             [132]        2019        FD           RGB
                                       [133]         2021         HAR              RGB/D           [134]        2019        FD           RGB
                                       [135]         2021         HAR              RGB/D           [136]        2019        FD           RGB
                                       [137]         2020         FD               RGB             [138]        2019        FD           RGB
                                       [139]         2020         FD               RGB             [140]        2019        FD           RGB
                                       [141]         2020         FD               RGB             [142]        2019        FD           RGB
                                       [143]         2020         FD               RGB             [144]        2019        FD           RGB, IR
                                       [145]         2020         FD               RGB             [146]        2019        FD           RGB-D
                                       [147]         2020         FD               RGB             [148]        2019        HAR          D
                                       [149]         2020         FD               RGB             [150]        2019        HAR          D
                                       [151]         2020         FD               RGB             [152]        2019        HAR          D
                                       [153]         2020         FD               RGB             [154]        2019        HAR          D
                                       [155]         2020         FD               RGB-D           [156]        2019        HAR          RGB
                                       [157]         2020         FD               RGB-D           [158]        2019        HAR          RGB
                                       [159]         2020         FD & HAR         IR              [160]        2019        HAR          RGB
                                       [161]         2020         FD & HAR         RGB             [162]        2019        HAR          RGB
                                       [163]         2020         HAR              RGB             [164]        2019        HAR          RGB
                                       [165]         2020         HAR              RGB             [166]        2019        HAR          RGB
                                       [167]         2020         HAR              RGB
                                       The tasks of the studies may involve FD (fall detection), HAR (Human Action Recognition), or both (FD,
                                       HAR). The CV data column indicates the type of computer vision data used: RGB, D (depth), or IR (infrared).
                                       Data types are separated by commas if the study requires all of them or by slashes if only one is necessary


into systems or applications capable of alerting medical per-                5.2 RQ1.1: data type
sonnel [41, 49].
   Only 27 out of 151 studies (approximately 18%) address                    Among the studies collected, three types of vision data were
both tasks simultaneously. This disparity arises from the                    considered: RGB, depth, and infrared (IR). The distribution
emphasis placed on fall detection compared to other activi-                  of these data types is illustrated in Fig. 5. RGB data were the
ties (such as walking or standing up), as well as the limited                most prevalent for fall detection and HAR among the elderly
availability of data concerning fall scenarios, often resulting              (132 studies), followed by depth data (30 studies), with IR
in an imbalanced problem. However, some studies manage                       data being the least utilized (6 studies). This discrepancy can
to address both tasks. For instance, in [24, 67, 104], both                  primarily be attributed to the accessibility of common cam-
tasks are computed using the UP-FALL dataset [168], which                    eras compared to specialized ones equipped with depth or
includes five types of falls and six common activities. This                 infrared sensors. Additionally, RGB cameras offer benefits
balanced dataset allows for the preservation of the importance               such as lower costs and easier visual data inspection. Notably,
of accurately detecting falls amidst other activities. A similar             infrared cameras are less frequently employed, typically
approach is adopted in [106], where a custom dataset with                    positioned overhead (top-down perspective) and character-
egocentric videos is utilized. Nevertheless, there are studies               ized by very low resolutions, allowing for the use of simpler
that treat falls as just another task to recognize [30, 47, 161].            CNN models [45, 122], as well as non-convolutional models
                                                                             like LSTM [119, 159] and Transformer [119]. Depth cam-


                                                                                                                                      123
8990                                                                                                                            G.M F. Xavier et al.


                                                                             tion is performed on videos, the result is a sequence of
                                                                             skeleton poses with an added temporal dimension, enabling
                                                                             exploration of pose evolution over time intervals. 35 studies
                                                                             employed the evolution of one or more body landmarks for
                                                                             fall or HAR recognition [49, 107], while the remaining 32
                                                                             studies performed recognition using static poses exclusively
                                                                             [42, 118].
                                                                                 In addition to vision data, some studies utilized sensor data
                                                                             to enhance system performance, employing different mod-
                                                                             els or strategies for classification and subsequently fusing the
                                                                             results. Fourteen studies, listed in Table 4, utilized at least one
                                                                             of five types of sensor data, including Inertial Measurement
                                                                             Unit (IMU)2 , audio, barometer, luminosity, radar, electro-
                                                                             cardiogram (ECG), GPS, and network traffic. IMU data was
Fig. 4 Distribution of studies by target task: fall detection, HAR or both   the most commonly used, featured in 10 of the 14 studies,
                                                                             particularly for fall detection (in 6 out of 10 studies using
                                                                             IMUs), owing to its effectiveness in identifying abrupt move-
eras are more commonly used than infrared ones, although                     ments and subsequent immobility [64, 149]. Barometer, GPS,
they are often employed to extract skeleton joints rather than               radar, luminosity, and ECG data were consistently employed
directly performing fall detection and HAR. Specifically,                    in conjunction with IMU data. Barometer and luminosity
67% of studies utilizing depth data computed skeleton joints                 data served to acquire auxiliary or redundant information to
before classification [38, 152, 152], while the remaining 33%                enhance recognition consistency [74, 149]. ECG data in [47]
did not [20, 148, 155].                                                      was utilized to identify inconsistencies in recognition and
   Skeleton poses and sequences emerged as prevalent data                    trigger specific further computations. In [85], four types of
types across the reviewed studies, with 67 studies incorpo-                  data (IMU, audio, radar, and GPS), along with visual data,
rating skeleton data in some form. Given the human-centric                   were used for federated learning, where independent models
nature of HAR and fall detection tasks, skeletal data represent              were trained using different data modalities.
logical features, offering efficient information compression                     Regarding data fusion, no instances of early fusion were
while maintaining interpretability. Skeletons are typically                  found. Instead, intermediate (7 studies) and late (5 studies)
represented as ordered sets of coordinates of body land-                     fusion methods were prevalent. Late fusion involved using
marks, either in 2D [24, 61, 107] or 3D [22, 38, 152]                        a model for each data modality to produce a classification
positions, depending on whether they were estimated from                     result, with the final classification determined using either
RGB or depth data, respectively. When skeleton estima-                       voting [74, 89] or weight attribution methods [44, 69, 149].
                                                                             In intermediate fusion, different models extracted features
                                                                             from various modalities, with a final model performing clas-
                                                                             sification based on concatenated feature inputs. Various final
                                                                             models were utilized, including CNN [64], fully connected
                                                                             layers [54, 72], SVM [99], and stacked classifiers [77]. In
                                                                             two studies, no fusion was performed, with different options
                                                                             provided for classification using distinct data modalities [47,
                                                                             127].

                                                                             5.3 RQ1.2: DL models

                                                                             Table 5 provides a summary of all DL models utilized in
                                                                             the analyzed studies. These models are often employed for
                                                                             various specific tasks, including skeleton joints estimation,
                                                                             optical flow computation, and feature extraction. Moreover,
                                                                             the input data for these models encompasses not only images
                                                                             or videos but also features frequently computed by other DL

Fig. 5 Distribution of studies by data type used. Note that more than        2 Studies not specifying the use of an IMU but using accelerometers
one data type was used in some studies                                       and gyroscopes have also been included in this group.


123
Deep learning for computer vision based activity recognition...                                                                    8991


Table 4 Studies using
                                       Ref.               Year      Task                Sensors                             Fusion type
multi-modal approaches and
type of fusion with visual data        [85]               2023      HAR                 IMU, Audio, Radar, GPS              Intermediate
                                       [47]               2023      HAR, FD             IMU, ECG                            None
                                       [77]               2023      HAR                 Network traffic                     Intermediate
                                       [69]               2022      HAR, FD             CSI                                 Late
                                       [89]               2022      FD                  IMU                                 Late
                                       [44]               2022      HAR                 IMU                                 Late
                                       [99]               2022      FD                  IMU                                 Intermediate
                                       [54]               2022      HAR                 IMU                                 Intermediate
                                       [60]               2022      HAR                 IMU, Radar                          Intermediate
                                       [127]              2021      HAR                 Audio                               None
                                       [64]               2021      FD                  IMU                                 Intermediate
                                       [74]               2021      FD                  IMU, Luminosity                     Late
                                       [149]              2020      FD                  IMU, Barometer                      Late
                                       [148]              2019      HAR                 Audio                               Intermediate


Table 5 DL models utilized in
## Model                        Studies
the reviewed studies, tasks they
                                       Ref.          Name           Task                           Input data                        N
are employed for, input data they
process, and number of studies         [169]         OpenPose       2D Skeleton                    RGB Image                         25
in which they are featured
                                       [170]         AlphaPose      2D Skeleton                    RGB Image                         10
                                       [171]         MediaPipe      2D Skeleton                    RGB Image                         4
                                       [172]         PoseNet        2D Skeleton                    RGB Image                         3
                                       [173]         MoveNet        2D Skeleton                    RGB Image                         2
                                       [174]         RMPE           2D Skeleton                    RGB Image                         1
                                       [175]         PoseFlow       2D Skeleton                    RGB Image                         1
                                                     Baidu AI       2D Skeleton                    RGB Image                         1
                                       [176]         FastPose       2D Skeleton                    RGB Image                         1
                                       [177]         MobileNet      2D Skeleton, HAR, FD           RGB Image                         7
                                       [178]         DeepHAR        2D Skeleton, HAR, FD           RGB Image                         1
                                       [179]         PoseConv3D     3D Skeleton                    Depth Image                       1
                                       [180]         STN            3D Skeleton                    RGB-D Image                       1
                                       [181]         Autoencoder    FD                             Different features                3
                                       [182]         GAN            FD                             Different features                2
                                       [183]         Siamese CNNs   FD                             RGB or Optical Flow Video         1
                                       [97]          FallNet        FD                             RGB Video                         1
                                       [184]         DeepFall       FD                             RGB, Depth or IR Video            1
                                       [185]         Sep-TCN        FD                             Skeleton sequence                 1
                                       [186]         DCF-Net        Features                       RGB Image                         1
                                       [187]         SqueezeNet     Features                       RGB Image                         1
                                       [188]         EfficientNet   Features                       RGB Image                         1
                                       [189]         C3D            Features                       RGB Video                         1
                                       [190]         R-CNN          Features (OD, OS), FD          RGB Image                         7
                                       [191]         YOLO           Features (OD), HAR, FD         RGB Image                         26
                                       [67]          MSSkip         Features (OS)                  RGB Image                         1
                                       [192]         PointRend      Features (OS)                  RGB Image                         1
                                       [193]         LiteFlowNet    Features (Optical Flow)        RGB Video                         1
                                       [194]         Slowfast       Features, HAR                  RGB Video                         3




                                                                                                                            123
8992                                                                                                                  G.M F. Xavier et al.


Table 5 continued
## Model                            Studies
                                 Ref.       Name                  Task                    Input data                                   N

                                 [195]      InceptionV3           Features, HAR           RGB or Depth Image                           1
                                            CNN                   Features, HAR, FD       Image, Video or different features           52
                                 [196]      LSTM                  Features, HAR, FD       Skel. sequence or Video features             29
                                 [197]      VGG                   Features, HAR, FD       RGB or Depth Image                           13
                                 [198]      ResNet                Features, HAR, FD       RGB or Depth Image or Skel. Pose             12
                                 [199]      GCN                   Features, HAR, FD       Skel. sequence or Video features             9
                                            RNN                   Features, HAR, FD       Skel. sequence or Video features             7
                                 [200]      I3D                   Features, HAR, FD       RGB Video                                    5
                                 [201]      GRU                   Features, HAR, FD       Skel. sequence or Video features             4
                                 [202]      Transformer           HAR                     IR Image (8x8)                               2
                                 [203]      TANet                 HAR                     RGB Video                                    2
                                 [204]      TPN                   HAR                     RGB Video                                    2
                                 [205]      iCAN                  HAR                     Bounding Boxes sequence                      1
                                 [206]      Xception              HAR                     RGB Image                                    1
                                 [207]      TSN                   HAR                     RGB Video                                    1
                                 [208]      VST                   HAR                     RGB Video                                    1
                                 [209]      TimeSformer           HAR                     RGB Video                                    1
                                 [210]      Glimpse Clouds        HAR                     Skeleton sequence                            1
                                 [211]      AIA                   HAR                     Video features and Bounding Boxes            1
                                            MLP                   HAR, FD                 Different features                           5
                                 [212]      AlexNet               HAR, FD                 Feature Image                                1
                                 [28]       ARFD-Net              HAR, FD                 Skeleton sequence                            1
                                 Abbreviations are used for Fall Detection (FD), Object Detection (OD), and Object Segmentation (OS).
                                 Models of to the same family are grouped together, including R-CNN, LSTM, YOLO, VGG, ResNet, RNN,
                                 CNN, and GCN


models, such as 2D or 3D skeleton poses and optical flow.          (appearing in 25 and 10 studies, respectively). OpenPose
A taxonomy of the identified DL models, based on differ-           utilizes a non-parametric representation (referred to as Part
ent characteristics, is presented in Figure 6, offering a total    Affinity Fields) to detect skeleton joints from all humans in
count for each category. There is considerable diversity in        the image simultaneously, while AlphaPose performs human
the utilization of these models, regarding datasets used for       detection first and then predicts the skeleton joints for each
evaluation, data types, and methodology. As demonstrated           individual. Subsequently, multiple models are used for fall
in the next section, in Table 6, a wide range of datasets was      detection and HAR with these skeleton joints:
employed across the analyzed studies, with many utilizing
custom datasets. Additionally, prominent datasets like URFD          • Recurrent Networks: Long-Short Term Memory (LSTM)
and UP-FALL offer various data types, including RGB                    [93, 95, 180] and Gated Recurrent Unit (GRU) [95, 114]
recordings, depth, skeletons, accelerometers, etc., which may          are commonly used, with others grouped as RNN [40,
lead to data differences even when studies are evaluated on            66].
the same dataset. The methodology for training and testing           • Graph-Based Network: The Graph-Convolutional Net-
DL methods also varies across studies, with some employ-               work (GCN) was the only one found, which treats
ing k-fold cross-validation, leave-one-out cross-validation,           skeletons as graphs rather than sequences [44, 107, 112].
or no cross-validation at all. Consequently, due to the lack of        Additionally, graph-based networks have the potential
standardized conditions for a fair comparison, quantitative            to perform collective activity recognition by leveraging
metric results were not included in Table 5.                           interactive relations [213].
   As mentioned in Section 5.2, many studies utilize skele-          • Convolutional Networks: Various models like VGG
ton joints as features for fall detection and HAR. To estimate         architectures [127, 146, 165], MobileNet [42, 81, 141],
these joints, various DL models are employed, with Open-               ResNet family [81, 141], among others [118, 150, 156],
Pose [169] and AlphaPose [170] being the most prevalent                are employed.



123
Deep learning for computer vision based activity recognition...                                                                   8993


                                                                           Additionally, object segmentation plays a crucial role in
                                                                       several studies. The most commonly used model is Mask R-
                                                                       CNN [214], which extends the capabilities of the R-CNN
                                                                       family to object segmentation. Another notable model is
                                                                       PointRend [192], a neural network module that enhances
                                                                       the granularity of segmentation models by treating image
                                                                       segmentation as a rendering problem. Conversely, a novel
                                                                       model proposed in [67] specifically addresses object segmen-
                                                                       tation as part of the processing pipeline for fall detection and
                                                                       post-fall classification, named MSSkip. MSSkip builds upon
                                                                       common ideas from other segmentation models but incorpo-
                                                                       rates multi-scale skip connections and depth-wise separable
                                                                       convolutions in the decoder to minimize computation. Object
                                                                       segmentation serves various purposes in the reviewed stud-
                                                                       ies: in [103], averaged output masks are utilized as spatio-
                                                                       temporal features for further recognition steps; [88] performs
                                                                       direct classification into fall or not fall based on the segmen-
                                                                       tation of fallen individuals; segmentation masks are fed to a
Fig. 6 Taxonomy of the DL techniques used in the found studies. The    convolutional LSTM in [67] and to a CNN followed by an
number of studies where each category was used is displayed in bold.   LSTM in [153] to extract spatial and temporal features for
Note that multiple models were used in many studies, and hence the
                                                                       fall detection; in [108], segmentation masks are input to dif-
same study can be counted in more than one category
                                                                       ferent machine learning models to identify falls. Conversely,
                                                                       in [41], segmentation is used solely to anonymize images
    Only one DL model, LiteFlowNet, was used for opti-                 before feeding them to an autoencoder for fall detection.
cal flow estimation across the studies [149]. However, 11                  Moreover, alongside the aforementioned DL-computed
additional studies utilized optical flow at some stage of the          features, other features are predominantly computed using
recognition pipeline through non-DL-based methods [50, 55,             convolutional models such as VGG-16, VGG-19 [27, 143,
56, 58, 70, 83, 96, 109, 128, 146, 155].                               153], ResNet [55, 145], or InceptionV3 [157]. Less fre-
    Object detection was a prevalent task in the reviewed              quently, non-DL-based features like Histograms of Oriented
studies (found in 35 studies), with models from two fam-               Gradients (HOG) [55, 134], Local Binary Patterns (LBP) [55,
ilies: R-CNN [190] and YOLO [191]. R-CNN involves a                    86], and Bag of Words (BoW) [50, 138] are also utilized. Fol-
multi-step process including region proposal, feature extrac-          lowing feature extraction, multiple DL models are employed
tion, object classification, bounding box regression, and              for classification. However, at this stage, it is common to use
non-maximum suppression. Conversely, YOLO focuses on                   non-deep machine learning models such as Support Vector
real-time object detection with a single pass through the              Machine [55, 58, 106, 136], Random Forest [39, 55], Deci-
image. Both models received several ameliorations in later             sion Tree [39, 106], and KNN [106].
versions. These models were utilized for various purposes                  Furthermore, fall detection is frequently approached as a
across the studies:                                                    normal/abnormal classification task in the reviewed studies,
                                                                       with normal activities modeled and falls treated as abnor-
                                                                       mal data. This involves performing feature extraction, either
 • Obtaining a sequence of bounding boxes from scene
                                                                       using pre-trained models to extract spatio-temporal features
   objects, which can serve as features in next steps [46,
                                                                       from video/images or utilizing estimated skeleton joints,
   52, 99].
                                                                       followed by training a model to identify normal activities.
 • Triggering computation of fall detection or HAR upon
                                                                       Various approaches are employed for this task, such as utiliz-
   detection of human presence, saving computation time
                                                                       ing an MPED-RNN network on skeletal data [94], employing
   [100, 105].
                                                                       DeepFall on multiple data modalities (RGB, depth, and IR)
 • Reducing data complexity by putting the focus on the
                                                                       [20], using autoencoders after obtaining spatio-temporal fea-
   target person [27, 102, 161].
                                                                       tures from other networks [41, 111, 144], and employing
 • Getting features from the humans in the scene, like
                                                                       Generative Adversarial Networks (GANs) by utilizing the
   height-to-width ratio, used for fall detection or HAR in
                                                                       discriminator as the normal/abnormal classifier [86, 103].
   further steps [31, 78, 136].
                                                                           Finally, the choice of architecture in the analyzed stud-
 • Direct detection of falls or recognition of activities [25,
                                                                       ies often depends on the data dimensionality, with recurrent
   76, 139].
                                                                       neural networks (RNNs) primarily used when considering


                                                                                                                            123
8994                                                                                                                                  G.M F. Xavier et al.


Table 6 Comprehensive list of publicly available datasets used in the reviewed studies, along with their basic specifications
Ref.        Dataset                      Eld.       Falls      Type         Data types                 Samples                  Cl.           Studies

[216]       URFD                         No         Yes        Video        RGB-D, Skel., IMU          140                      2             40
[168]       UP-FALL                      No         Yes        Video        RGB, IR, IMU               561                      11            17
[217]       Le2i                         No         Yes        Video        RGB                        191                      2             16
[218]       MultiCam                     No         Yes        Video        RGB                        192                      2             16
[219]       NTU RGB+D                    No         Yes        Video        RGB-D, Skel.               56880                    60            14
[220]       FDD-Adhikari                 No         No         Image        RGB-D                      21499 (frames)           5             6
[221]       MSRDailyActivity3D           No         No         Video        RGB-D, Skel.               320                      16            4
[222]       UTD-MHAD                     No         No         Video        RGB-D, Skel., IMU          861                      27            4
[223]       CAD-60                       No         No         Video        RGB-D                      720                      12            3
[224]       ETRIActivity3D               Yes        Yes        Video        RGB-D, Skel.               112620                   55            3
[225]       HMDB51                       No         Yes        Video        RGB                        6766                     51            3
[226]       KTH                          No         No         Video        RGB                        2391                     6             3
[118]       PRECIS HAR                   No         Yes        Video        RGB-D                      800                      16            3
[154]       ToyotaSmartHome              Yes        No         Video        RGB-D, Skel.               16115                    31            3
[227]       CAD-120                      No         No         Video        RGB-D                      1200                     10            [36, 156]
[228]       DMLSmartActions              No         Yes        Video        RGB-D, Skel.               932                      12            [47, 160]
[136]       FPDS                         No         Yes        Image        RGB                        2064                     2             [101, 136]
[229]       HQFSD                        Yes        Yes        Video        RGB                        55                       2             [46, 151]
[230]       NTU RGB+D 120                No         Yes        Video        RGB-D, Skel.               114480                   120           [107, 135]
[231]       N-UCLA                       No         No         Video        RGB-D, Skel.               100                      10            [161]
[232]       UCF101                       No         No         Video        RGB                        13320                    101           [58, 143]
[233]       UTKinect-Action3D            No         No         Video        RGB-D, Skel.               200                      10            [102, 150]
[234]       UWA3DII                      No         Yes        Video        RGB-D, Skel.               120                      30            [107, 161]
[20]        MUVIM                        Yes        Yes        Video        RGB-D, IR, IMU             244                      2             [20]
[161]       ALMOND                       No         Yes        Video        RGB                        7565                     22            [161]
[235]       BIT-interaction              No         No         Video        RGB                        400                      8             [162]
[236]       C-MHAD                       No         Yes        Video        RGB, IMU                   120                      7             [44]
[97]        FallAction                   No         Yes        Video        RGB                        2000                     20            [97]
[237]       FDD-Chen                     No         Yes        Video        RGB                        30                       2             [126]
[238]       FDD-TST                      No         Yes        Video        RGB-D, Skel., IMU          132                      8             [157]
[239]       FPDS-Elderly                 Yes        Yes        Image        RGB                        413                      2             [101]
[240]       IXMAS                        No         No         Video        RGB, MHV                   330                      11            [161]
[241]       Kinetics 400                 No         No         Video        RGB                        306245                   400           [129]
[242]       Kinetics 600                 No         Yes        Video        RGB                        495547                   600           [97]
[243]       Kinetics 700-2020            No         Yes        Video        RGB                        647907                   700           [125]
[135]       KIST SynADL                  No         Yes        Video        RGB-D, Skel.               462200                   55            [135]
[244]       MMU                          No         Yes        Video        RGB                        51                       2             [93]
[245]       NAD                          No         No         Video        RGB                        84                       7             [135]
[246]       OOPS                         No         Yes        Video        RGB                        20338                    2             [97]
[247]       PKU-MMD                      No         Yes        Video        RGB-D, Skel.               21545                    51            [121]
[248]       Stanford40                   No         No         Image        RGB                        9532                     40            [125]
[249]       V-COCO                       No         No         Image        RGB                        10346                    25            [52]
[101]       VWFP                         No         Yes        Image        RGB                        6071                     2             [101]
[250]       YTBF                         No         Yes        Video        RGB-D, Skel.               606                      2             [151]
The columns “Eld.” and “Cl.” denote the presence of elderly people in the datasets and the number of classes, respectively. The “Studies” column
indicates in which studies they appear, or the number of reviewed studies if it is greater than two




123
Deep learning for computer vision based activity recognition...                                                                8995


the temporal dimension and feedforward neural networks                 samples (e.g., Kinetics 700-2020), reflecting the diversity
(FFNNs) when not. RNNs are well-suited for problems                    in data availability.
involving sequential data due to their ability to remember           • Classes: The number of classes also varies widely, from
input data using internal memory. As such, they are often              binary classification to datasets with hundreds of classes,
employed for fall detection and activity recognition from              though the latter are typically not focused on AAL.
skeleton sequences [49, 180] and feature sequences com-              • Studies: Half of the datasets are utilized in only one
puted frame-wise by CNNs [24, 143, 148]. While CNNs are                study, while only five are used in more than ten stud-
commonly used for extracting visual features from images,              ies, indicating varying degrees of dataset popularity and
transformers have also been utilized in the FFNNs category,            usage.
particularly for tasks involving low-resolution images [119],
3D skeleton data [81], and video by adapting Vision Trans-
former (ViT) [215] to video formats [53, 79]. Additionally,
multilayer perceptrons (MLPs) are consistently employed for             The University of Rzeszow Fall Detection (URFD) dataset
skeleton data [34, 38, 92, 140] or visual features [108].           [216] stands out as the most extensively used, featuring in
                                                                    40 studies [41, 89, 153]. Focused on fall detection, URFD
5.4 RQ1.3: Datasets                                                 offers 70 sequences capturing falls and activities of daily liv-
                                                                    ing (ADL) from two perspectives, along with various data
Table 6 provides a comprehensive list of datasets used in the       modalities including RGB, depth, skeleton joints, and iner-
reviewed studies for activity recognition and fall detection.       tial data. The UP-FALL dataset [168], appearing in 17 studies
Emphasizing the importance of reproducibility and compa-            [24, 39, 103], provides data from 17 subjects performing 11
rability, only publicly available datasets are included, aiming     activities, offering RGB video, infrared images, and inertial
to facilitate future research in the field. Each dataset is cate-   data for both fall detection and human activity recognition
gorized based on several common characteristics:                    (HAR). In contrast, the Le2i dataset [217], used in 16 studies
                                                                    [47, 93, 137], focuses solely on fall detection, featuring 143
                                                                    videos with falls and 48 with normal activities, with varying
 • Elderly: Despite fall detection and activity recogni-            actors, scenery characteristics, and illumination conditions.
   tion often targeting elderly individuals, only a small           Similarly, the MultiCam dataset [218], utilized in 16 studies
   fraction of datasets (12%) include samples from this             [27, 30, 72], provides RGB video from 24 sequences cap-
   demographic. This scarcity highlights the challenge of           tured from eight perspectives, facilitating the study of falls
   collecting real-life data from the elderly population, espe-     and confounding events. The NTU RGB+D dataset [219],
   cially genuine fall incidents.                                   used in 14 studies [112, 118, 131], offers a vast collec-
 • Falls: The majority of datasets (58%) include falls as a         tion of samples from 40 subjects performing 60 activities,
   class, with 23% specifically focusing on binary classifi-        recorded using Kinect cameras, thus providing RGB video,
   cation between fall and not fall activities, underscoring        depth images, and skeleton joints. An extended version of
   the significance of this task in eldercare.                      this dataset also exists: the NTU RGB+D 120 dataset [230],
 • Type: Video data is predominant (85% of datasets), align-        which expands upon it by adding 60 additional classes. How-
   ing with the temporal nature of activities like falls, where     ever, it is only utilized in two of the reviewed studies [107,
   temporal context is crucial for accurate recognition. Fur-       135]. The remaining datasets were utilized fewer than 10
   thermore, video allows for the rapid acquisition of a large      times, with approximately half of them being employed in
   quantity of images in the form of frames, which can then         only one study.
   be utilized by data-driven solutions, such as DL-based               While most datasets are collected from real environments,
   methods.                                                         two exceptions are noted: [101] and [135], offering synthetic
 • Data types: While RGB data is ubiquitous, depth frames,          images and videos, respectively. Despite the advantages of
   skeleton joints, and inertial data are found in 38%, 29%,        synthetic data, such as ease of acquisition and controlled
   and 13% of datasets, respectively. Other data types such         conditions, models trained solely on synthetic data may lack
   as infrared data and motion history volumes (MHV) are            adaptability to real-world scenarios.
   less common. The presence of RGB data in all datasets                Notably, some studies opted for custom datasets instead of
   allows for the discovery of the exact conditions of the          utilizing existing ones. Figure 7 illustrates the proportion of
   recordings (environment, perspective, users, etc.) and           studies using custom, external, or both types of datasets. Only
   serves as a visual check of the data, a feature not offered      19 studies provided evaluations on both custom and external
   by other types of data.                                          datasets, with a greater frequency of evaluations conducted
 • Samples: Dataset sizes vary significantly, ranging from          solely on external datasets (86 studies) compared to those
   less than 50 samples (e.g., FDD-Chen) to over 500,000            exclusively using custom datasets (46 studies).


                                                                                                                         123
8996                                                                                                               G.M F. Xavier et al.


                                                                    are offered in [63], with the addition of face blurring
                                                                    anonymization. [77] conducts all experiments in a connected
                                                                    environment, exploring the use of network traffic from multi-
                                                                    ple smart appliances combined with visual data to recognize
                                                                    various activities. Additionally, to assess the transferability
                                                                    of their approach across environments, they experimented
                                                                    with a smart residential apartment.
                                                                       In [85], federated learning is employed to ensure privacy
                                                                    preservation of users. The system incorporates three sensor
                                                                    modalities (depth, mmWave radar, and audio) and was tested
                                                                    in the homes of 16 elderly subjects.

                                                                    5.6 RQ2.1: hardware

                                                                    A list of the hardware used in the reviewed studies (when
Fig. 7 Distribution of studies by dataset used
                                                                    mentioned) is presented in Table 7. Specialized cameras
                                                                    such as thermal, depth, and wearable cameras, as well as
                                                                    social assistive robots, were included. Information regarding
5.5 RQ2: Framework integration                                      datasets not created in the reviewed studies was excluded.
                                                                    Hardware related to computation or common RGB cameras
In 18 of the reviewed articles, frameworks were proposed            was omitted due to the wide range of possibilities available
to integrate the tasks of HAR or fall detection into real           in these areas.
environments, addressing various aspects such as security,              For depth video retrieval, the most commonly used camera
utilization of cloud services, client-server configuration, net-    is the Microsoft Kinect (7 studies), followed by the Orbbec
work communications, IoT devices, etc. Below, we provide            Astra Pro (3 studies), and Intel RealSense (1 study). These
brief descriptions of the proposed frameworks.                      cameras share similar specifications, offering RGB-D record-
    In [42], a custom robot is suggested to integrate the HAR       ing using an IR camera for the depth channel, which provides
task into the environment, alongside other functionalities like     accurate depth estimation at short distances. Additionally,
language processing to enable chatbot interactions. In [161],       they enable reliable 3D skeleton joint estimation.
a camera system is employed to capture visual data, which is            There is less consensus in the use of thermal cameras,
then sent to a central server for computation. Subsequently,        with multiple camera models employed. Consequently, there
notifications, reports, and alerts are dispatched to a desig-       is considerable variation in the retrieved data, including dif-
nated “guardian”.                                                   ferences in resolution, sensitivity to temperature, maximum
    In [74], a Docker-based system is proposed to manage the        and minimum effective distances, etc.
flow between various programs involved in fall detection, dis-          Only five studies deployed HAR or fall detection in an
tributing resources, and regulating communications. Docker          AAL system using a social assistive robot. Among these,
is also utilized in [78], where the NAO robot is suggested for      two studies utilized the Pepper robot, one employed the NAO
data acquisition and user interaction to prevent falls. In [30,     robot, and the remaining studies used custom-made robots.
32], an intermediary step between recording and DL com-
putation is introduced to preprocess video data and reduce          5.7 RQ2.2: privacy protection
bandwidth consumption.
    In [18, 33, 49, 52, 58, 93, 105], the proposed frameworks       Figure 8 illustrates the various privacy protection methods
integrate the collection of visual data through camera mon-         identified in the reviewed studies. Among the 151 studies
itoring systems, centralized server-based recognition of fall       reviewed, 75 did not address privacy concerns, opting for the
detection or various activities, and trigger various responses      use of unmodified RGB video or images of elderly users.
based on the severity of the situation, such as contacting          Among the remaining studies, the majority employed skele-
health services. For instance, [33] utilizes the third-party ser-   ton data computed from RGB images, while four offered
vice ’Twilio’ to send phone messages in case of a fall, while       specific methods to anonymize RGB data, and others chose
in [105], the system transfers recordings to a computer for         to utilize thermal or depth data instead.
human inspection upon fall detection.                                  The most effective privacy-preserving methods avoid the
    In [123, 127], activity recognition results, along with         deployment of RGB cameras in AAL settings. This is typ-
recorded video data, are transmitted to a mobile applica-           ically achieved through the use of visual data types that
tion used for monitoring system users. Similar capabilities         do not allow for subject identification, such as thermal and


123
Deep learning for computer vision based activity recognition...                                                                             8997


Table 7 Special cameras and
                                       Type                              Model                    Brand                    Studies
social robots found in the
reviewed studies                       RGB-D Camera                      Astra Pro                Orbbec                   [20, 117, 118]
                                                                         Kinect v1                Microsoft                [98, 148, 152, 154]
                                                                         Kinect v2                Microsoft                [17, 38, 43]
                                                                         RealSense D415           Intel                    [83]

                                       Thermal Camera                    AMG8831                  Panasonic                [119]
                                                                         FLIR ONE                 iTherml                  [20]
                                                                         HTPA32x32d               Heimann Sensor           [122]
                                                                         MLX90640                 Melexis                  [45]
                                                                         MLX90641                 Melexis                  [159]
                                                                         PI450                    Optris                   [144]

                                       Wearable RGB Camera               OnReal G1                Fondi                    [55]

                                       LiDAR                             Horizon LiDAR            Livox                    [113]

                                       Social Assistive Robot            Dori                     Custom made              [42]
                                                                         LOLA                     Custom made              [136]
                                                                         NAO                      Aldebaran URG            [78]
                                                                         Pepper                   Aldebaran URG            [116, 158]



depth imaging. Among the collected studies, five exclusively                    A total of 51 studies utilized RGB data at some stage,
employed thermal data [20, 45, 119, 122, 159]. In all cases,                applying anonymization techniques. In contrast to the afore-
DL-based methods utilized CNNs to extract visual features                   mentioned studies, the input data used by these studies can be
and perform classification. Additionally, 21 studies utilized               used to identify subjects, as conventional video recording is
solely depth data, with 17 of them using it to estimate 3D                  involved at the beginning of the processing pipeline. Among
skeleton poses, as demonstrated in [38, 43, 81, 152]. Notably,              these, 47 studies relied on 2D skeleton estimation methods
Microsoft Kinect was utilized in all 17 studies to estimate                 like OpenPose [169] and AlphaPose [170] to protect privacy,
skeletons from depth maps through randomized decision                       removing visual data that can be used to identify users, as
forests [251], leaving RGB data unused for this estimation.                 illustrated in [24, 44, 104, 107, 137]. There were four stud-
Four studies exploited depth data without skeleton estima-                  ies in which privacy was protected through other methods. In
tion, instead relying on the extraction of human silhouettes                [144], an IR camera is used to detect the face region of frames
[148] and visual features using CNNs [20, 113, 117].                        and remove it from the RGB frames. In [86], the RGB frames
                                                                            are modified in such a way that individuals cannot be iden-
                                                                            tified, while fall detection can still be applied effectively. In
                                                                            [55], a wearable camera providing a first-person perspective
                                                                            is used to avoid recording the user of the system. Human sil-
                                                                            houettes are computed in [41] and used for future recognition
                                                                            steps.


## 6 Discussion

                                                                            This section utilizes the discovered results and the responses
                                                                            provided to the review questions to underscore common
                                                                            strengths and weaknesses of the reviewed studies. It also
                                                                            compiles a comprehensive list of recommendations for future
Fig. 8 Distribution of studies by method used to preserve privacy. The      reference based on the findings of this systematic literature
total does not add up to 151 studies because in some studies different      review. In Figure 9, the search process and key findings from
options were given                                                          the reviewed studies are summarized.




                                                                                                                                     123
8998                                                                                                                  G.M F. Xavier et al.

Fig. 9 Summary of the search
process and found results




## 6.1 Strengths and weaknesses of the reviewed                          putting on/off clothes. Nonetheless, confining the analysis to
    studies                                                           spatial data typically offers the advantage of being faster and
                                                                      more straightforward.
Upon reviewing the 151 relevant studies and addressing                   Regarding the choice of model architecture, convolu-
the research questions, the main strengths and weaknesses             tional models were found to be predominant. Their primary
observed are discussed in this subsection, which we believe           strengths lie in their effectiveness in processing spatial data
can provide valuable insights for future studies in the field.        and their extensive history, which has led to numerous
    A notable benefit of utilizing skeleton joints is their ability   improvements and architectural refinements across various
to significantly reduce data size compared to raw image or            fields and tasks. Given their suitability for image-based tasks,
video data, while also offering user anonymization, maintain-         convolutional models are widely preferred and even have 3D
ing data interpretability, and achieving satisfactory results         versions tailored for video processing. In contrast, recurrent
in fall detection and HAR. Furthermore, there is a growing            models excel in handling sequential data, thus complement-
number of methods to derive human skeletons from RGB or               ing the capabilities of CNNs by facilitating the tracking of
depth data, with 13 different skeleton estimation DL models           computed features across different frames. Multi-layer per-
identified in the reviewed studies (as shown in Table 5).             ceptrons, however, do not yield favorable results with spatial
    The primary strength of studies employing only depth or           or sequential data; they are typically employed for classifi-
infrared data lies in the privacy protection they afford, as RGB      cation based on computed features, akin to fully connected
footage is not recorded at any point in the system pipeline.          layers in a convolutional neural network. Transformer-based
However, these studies also face two major weaknesses: a              architectures, being relatively newer, are not as ubiquitous.
reduced amount of data for detection or recognition tasks,            Despite their promise in handling sequential and vision data,
particularly pronounced in the case of IR recordings where            their large parameter count presents challenges in training
resolution tends to be much lower, and less interpretable             and deploying them on low-specification systems. Nonethe-
data, which may pose challenges when manual intervention              less, they have showcased significant potential across various
is required to address errors.                                        domains.
    Among the reviewed studies, 27 perform both fall detec-              Given that fall detection and HAR for the elderly aim to
tion and HAR tasks (refer to Fig. 4). This integration is             assist this population in AAL settings, studies offering frame-
particularly significant, as it is often desirable to detect acci-    works for deploying systems in real environments are of
dental falls while conducting HAR on elderly individuals.             particular interest. Eighteen studies, described in Section 5.5,
It is important to note that while fall detection can be inte-        fall into this category.
grated as another class during HAR, it should be computed                Utilizing only an external dataset may impact the applica-
separately due to its critical nature. Therefore, most stud-          bility of the technique to specific situations or environments,
ies including fall detection implement it differently than the        but it allows for the comparison of different methods on the
recognition of other classes.                                         same data. Conversely, relying solely on a custom dataset
    Numerous studies have overlooked the temporal dimen-              yields the opposite effects. The primary drawback associated
sion when conducting HAR, thereby constraining the task               with using only custom-made datasets is the external validity
significantly. This omission poses a significant weakness,            of the findings, as it becomes challenging to compare results
particularly when incorporating activities that are chal-             with other studies, especially if the custom data is not dis-
lenging to distinguish without temporal data or are more              closed. Including an evaluation on external datasets not only
effectively recognized with it, such as sitting/getting up or         distinguishes studies from previous ones but also enables



123
Deep learning for computer vision based activity recognition...                                                               8999


future studies to build on the obtained performance. While the    CNNs specifically tailored for such devices. These mod-
majority of the reviewed studies evaluate on existing datasets    els can be augmented with recurrent models like LSTM to
for fall detection and HAR, 46 exclusively perform evalua-        accommodate temporal data. Conversely, if model size is not
tions on new custom datasets (as depicted in Fig. 7), limiting    a constraint, 3D CNNs like I3D, TPN, TANet, SlowFast, and
the reliability of the results without comparisons with exist-    C3D are suitable for video data, while GCN can be applied to
ing techniques or models. Conversely, 19 studies utilize both     skeleton data. Alternatively, Transformer-based architectures
custom and external datasets, leveraging the strengths of each    like TimeSformer or VST are also an option for processing
approach: specialization on custom data and comparison with       video input data.
other methodologies.                                                 For model evaluation, utilizing a publicly available dataset
   From a data perspective, three common weaknesses are           is essential to enable comparison with existing models or
evident in the datasets utilized: the absence of elderly indi-    techniques. Prominent datasets for fall detection include
viduals, a limited number of samples, and the inclusion           URFD, UP-FALL, MultiCam, and Le2i, while for HAR,
of numerous classes unrelated to activities of daily living       UP-FALL and NTU RGB+D are commonly used. However,
(ADL), which may render them less suitable for fall detection     we encourage the adoption of ETRIActivity3D or ToyotaS-
and HAR among elderly populations. Primarily, the major-          martHome, which offer a more extensive collection of video
ity of datasets (88%) lack elderly participants, presenting       samples and include elderly participants. Both datasets sup-
challenges during deployment as they represent the target         port HAR, with ETRIActivity3D additionally containing
users of the system but are not represented in the train-         falls and providing multiple perspectives from elderly users,
ing data. In this regard, datasets such as ETRIActivity3D,        diverse classes (at least 30), and various data modalities,
ToyotaSmartHome, MUVIM, and FPDS-Elderly would be                 including RGB, depth, and skeleton joints.
more suitable. Additionally, a limited number of samples             In cases where a custom dataset is provided, authors
may prove insufficient for DL models to generalize effec-         are encouraged to make it publicly available. This facili-
tively. Three of the four most extensive datasets contain         tates its use in future studies, either directly or by merging
fewer than 200 samples, while the remaining dataset con-          it with other datasets to form a larger dataset, enhances
tains fewer than 600, with approximately half of the utilized     the reproducibility of experiments, and enables comparison
datasets containing less than 1,000 samples. Instead, datasets    with newer models or techniques. RGB-D cameras, such as
such as ETRIActivity3D, NTU RGB+D (or NTU RGB+D                   Microsoft Kinect, Orbbec Astra Pro, and Intel RealSense, are
120), or ToyotaSmartHome, all offering more than 10,000           recommended for collecting custom datasets as they facili-
samples, would yield better generalization results. Lastly,       tate experimentation with various types of data, with depth
datasets should be tailored to focus on ADL rather than gen-      data offering privacy preservation capabilities.
eral HAR to avoid unnecessary classes for monitoring elderly         When deploying the system in a real environment, the
individuals in their daily lives. For instance, Kinetics (400,    most common approach, as indicated by the reviewed studies,
600, or 700) or UCF101 would not be suitable for the consid-      involves establishing a camera setup within the environ-
ered tasks as they comprise videos collected from the internet,   ment. This setup records data and transmits it to a central
potentially containing irrelevant activities and cuts.            server for processing. It is also the most cost-effective option,
                                                                  depending on factors such as camera type, resolution, and
## 6.2 Recommendations for future works                              processing requirements. Alternatively, for those preferring
                                                                  to use an assistive robot, both NAO and Pepper robots are
Based on the results of this SLR, a series of particularly        viable solutions. These commercial robots come equipped
important considerations, in our understanding, should be         with cameras, speakers, microphones, and other necessary
taken into account when conducting new studies on the topic.      components, offering customizable options to adapt to dif-
   First and foremost, it is crucial to assess user privacy. As   ferent projects and environments.
observed, the approach to privacy protection will likely influ-
ence the type of data used, ranging from conventional RGB
data to modified RGB, depth, IR, or skeleton data, which          7 Conclusions
prevent user identification in the footage. Therefore, we rec-
ommend considering privacy protection as a fundamental            In this systematic literature review, we have investigated fall
aspect from the outset of the study.                              detection and human activity recognition for the elderly, with
   Selecting an appropriate DL model for fall detection and       a particular focus on deep learning techniques applied to
HAR requires consideration of the deployment conditions.          computer vision data. Our study aimed to address two pri-
For embedded systems or edge-deployments, such as in              mary research questions related to the implementation of DL
social robots or mobile applications, compact models are          methods for these tasks and their deployment in real-world
preferred, such as MobileNet or EfficientNet—well-known           environments, considering hardware and privacy concerns.


                                                                                                                        123
9000                                                                                                                            G.M F. Xavier et al.


   Throughout the review process, we analyzed 151 relevant                by ERDF A way of making Europe, project Playful Experiences with
studies, providing a structured overview of the main findings             Interactive Social Agents and Robots (PLEISAR): Social Learning and
                                                                          Intergenerational Communication. F. X. Gaya-Morey was supported by
to facilitate accessibility for practitioners and researchers.            an FPU scholarship from the Ministry of European Funds, University
The findings offer valuable insights into the effective imple-            and Culture of the Government of the Balearic Islands.
mentation of DL techniques for fall detection and HAR in
elderly care, which are becoming increasingly important in                Data Availability All relevant data for the study can be found, struc-
                                                                          tured and organized in the form of tables, throughout this document.
the context of Ambient Assisted Living (AAL) systems.                     No additional data were generated.
   Privacy emerged as a common concern, with 50% of the
reviewed studies lacking any measures to address it. The most             Declarations
prevalent privacy protection method identified was the use of
skeleton joints estimation, employed in 45% of the studies.
   Convolutional DL models were found to be predominant,                  Competing of interest The authors have no competing interests to
owing to their effectiveness in processing spatial data and               declare that are relevant to the content of this article.
extensive history of refinement. However, we observed a lack              Ethical and informed consent for data used This article does not con-
of consideration for the temporal dimension in many studies,              tain any studies with human participants or animals performed by any
which limits the recognition of some activities.                          of the authors.
   Regarding datasets, we identified three common weak-
nesses: the absence of elderly individuals, a limited number              Open Access This article is licensed under a Creative Commons
                                                                          Attribution 4.0 International License, which permits use, sharing, adap-
of samples, and the inclusion of numerous irrelevant classes              tation, distribution and reproduction in any medium or format, as
for the AAL systems. We recommend datasets such as ETRI-                  long as you give appropriate credit to the original author(s) and the
Activity3D and ToyotaSmartHome, which offer extensive                     source, provide a link to the Creative Commons licence, and indi-
samples and include elderly participants.                                 cate if changes were made. The images or other third party material
                                                                          in this article are included in the article’s Creative Commons licence,
   Moving forward, we emphasize the importance of privacy                 unless indicated otherwise in a credit line to the material. If material
assessment from the outset of studies and recommend select-               is not included in the article’s Creative Commons licence and your
ing appropriate DL models based on deployment conditions.                 intended use is not permitted by statutory regulation or exceeds the
Utilizing publicly available datasets for model evaluation is             permitted use, you will need to obtain permission directly from the copy-
                                                                          right holder. To view a copy of this licence, visit http://creativecomm
crucial, and authors are encouraged to make custom datasets               ons.org/licenses/by/4.0/.
publicly available to enhance reproducibility and facilitate
future research.
   In terms of deployment, camera setups within the envi-
ronment were the most common approach identified, offer-                  References
ing cost-effectiveness and flexibility. Alternatively, assistive
robots like NAO and Pepper provide customizable options                     1. Bloom DE, Luca DL (2016) Chapter 1 - the global demography of
for deployment in various projects and environments.                           aging: Facts, explanations, future. vol 1, pp 3–56. North-Holland
                                                                            2. WHO (2021) World Health Organization fact sheets: Falls. https://
   Overall, this SLR provides a comprehensive overview of
                                                                               www.who.int/en/news-room/fact-sheets/detail/falls
recent advancements in DL-based fall detection and HAR                      3. Heinrich S, Rapp K, Rissmann U, Becker C, König H-H (2010)
for the elderly, offering valuable insights for researchers,                   Cost of falls in old age: a systematic review. Osteoporos Int
practitioners, and policymakers involved in developing and                     21:891–902
                                                                            4. Climent-Pérez P, Spinsante S, Mihailidis A, Florez-Revuelta
implementing AAL technologies.
                                                                               F (2020) A review on video-based active and assisted living
                                                                               technologies for automated lifelogging. Expert Systems with
Author Contributions F.Xavier Gaya-Morey: Conceptualization, Me-
                                                                               Applications. 139
thodology, Validation, Investigation, Writing - Original Draft, Writing
                                                                            5. Khodabandehloo E, Riboni D, Alimohammadi A (2021)
- Review & Editing Preparation, Visualization.
                                                                               Healthxai: Collaborative and explainable ai for supporting
Cristina Manresa-Yee: Conceptualization, Methodology, Writing -
                                                                               early diagnosis of cognitive decline. Futur Gener Comput Syst
Review & Editing Preparation, Supervision, Project administration,
                                                                               116:168–189
Funding acquisition.
                                                                            6. Nizam Y, Jamil MMA (2020) Classification of daily life activities
Jose M. Buades-Rubio: Conceptualization, Methodology, Writing -
                                                                               for human fall detection: A systematic review of the techniques
Review & Editing Preparation, Supervision, Project administration,
                                                                               and approaches. Stud Syst Decis Control 273:137–179
Funding acquisition.
                                                                            7. Walsh J, O’ Mahony N, Campbell S, Carvalho A, Krpalkova L,
                                                                               Velasco-Hernandez G, Harapanahalli S, Riordan D (2019) Deep
Funding Open Access funding provided thanks to the CRUE-CSIC
                                                                               learning vs. traditional computer vision
agreement with Springer Nature. Grant PID2019-104829RA-I00 funded
                                                                            8. Kitchenham B, Charters, S (2007) Guidelines for performing sys-
by                                               MCIN/AEI/10.13-
                                                                               tematic literature reviews in software engineering. 2
039/ 501100011033, project EXPLainable Artificial INtelligence sys-
                                                                            9. Guerra BMV, Torti E, Marenzi E, Schmid M, Ramat S, Leporati F,
tems for health and well-beING (EXPLAINING). Grant PID2022-
                                                                               Danese G (2023) Ambient assisted living for frail people through
136779OB-C32 funded by MCIN/AEI/ 10.13039/501100011033 and
                                                                               human activity recognition: state-of-the-art, challenges and future


123
Deep learning for computer vision based activity recognition...                                                                                9001


     directions. Frontiers in Neuroscience. 17. https://doi.org/10.3389/    27. Agrawal M, Agrawal S (2023) Enhanced deep learning for detect-
     fnins.2023.1256682                                                         ing suspicious fall event in video data. Intell Autom Soft Comput
 10. Kumar R, Kumar S (2023) A survey on intelligent human action               36:2653–2667. https://doi.org/10.32604/iasc.2023.033493
     recognition techniques. Multimed Tools Appl. https://doi.org/10.       28. Yadav SK, Luthra A, Tiwari K, Pandey HM, Akbar SA (2022)
     1007/s11042-023-17529-6                                                    Arfdnet: An efficient activity recognition & fall detection system
 11. Tay NC, Connie T, Ong TS, Teoh ABJ, Teh PS (2023) A review                 using latent feature pooling. Knowledge-Based Systems. 239
     of abnormal behavior detection in activities of daily living. IEEE     29. Dakare AA, Wu Y, Hashimoto N, Kumagai T, Miura T (2023)
     Access. 11:5069–5088. https://doi.org/10.1109/ACCESS.2023.                 Fall detection inside an autonomous driving bus: - examination
     3234974                                                                    of image processing algorithms-, pp 1–4. https://doi.org/10.1109/
 12. Momin MS, Sufian A, Barman D, Dutta P, Dong M, Leo M (2022)                ICCE56470.2023.10043518
     In-home older adults’ activity pattern monitoring using depth sen-     30. Rajavel R, Ravichandran SK, Harimoorthy K, Nagappan P,
     sors: A review. Sensors. 22                                                Gobichettipalayam KR (2022) Iot-based smart healthcare video
 13. Olugbade T, Bieńkiewicz M, Barbareschi G, D’amato V, Oneto                surveillance system using edge computing. J Ambient Intell
     L, Camurri A, Holloway C, Björkman M, Keller P, Clayton M,                 Humanized Comput 13:3195–3207
     Williams ACDC, Gold N, Becchio C, Bardy B, Bianchi-Berthouze           31. M, PV, Shekar M, B SLP, Ngadiran R, Ravindran S (2023) Fall
     N (2022) Human movement datasets: An interdisciplinary scop-               detection system for monitoring elderly people using yolov7-pose
     ing review. ACM Comput, Surv, p 55                                         detection model, pp 1–6. https://doi.org/10.1109/IC2E357697.
 14. Alam E, Sufian A, Dutta P, Leo M (2022) Vision-based human                 2023.10262506
     fall detection systems using deep learning: A review. Comput Biol      32. Wang B, Wu X, Gong M, Zhao J, Sun Y (2022) Lightweight
     Med 146:105626                                                             network based real-time anomaly detection method for caregiving
 15. Rastogi S, Singh J (2022) Human fall detection and activity                at home. Institute of Electrical and Electronics Engineers Inc.,
     monitoring: a comparative analysis of vision-based methods for             Hangzhou, China, pp 1323–1328
     classification and detection techniques. Soft Comput 26:3679–          33. Paul SK, Zisa AA, Walid MAA, Zeem Y, Paul RR, Haque MM,
## 3701                                                                       Hamid ME (2023) Human fall detection system using long-term
 16. Gutiérrez J, Rodríguez V, Martin S (2021) Comprehensive review             recurrent convolutional networks for next-generation healthcare:
     of vision-based fall detection systems. Sensors. 21(3)                     A study of human motion recognition, pp 1–7. https://doi.org/10.
 17. Sudasinghe SATN, Sooriyabandara IKS, Banadara AHMDPM,                      1109/ICCCNT56998.2023.10308247
     Rajendran H, Jayasekara AGBP (2023) Vision attentive robot for         34. Xie L, Sun Y, Chambers JA, Naqvi SM (2022) Privacy preserv-
     elderly room, pp 19–24. https://doi.org/10.1109/MERCon60487.               ing multi-class fall classification based on cascaded learning and
     2023.10355403                                                              noisy labels handling. Institute of Electrical and Electronics Engi-
 18. Zhang Y, Zheng X, Liang W, Zhang S, Yuan X (2022) Visual                   neers Inc., Linköping, Sweden, pp 1–6
     surveillance for human fall detection in healthcare iot. IEEE Mul-     35. Fan S, Li M, Han C (2023) Intelligent video monitoring for real-
     timed 29:36–46                                                             time detection and recognition of elderly falls on the embedded
 19. Wang X, Zheng X, Liu J, Yuan B, Zhao L, Sun J (2023) Abnormal              platform, pp 630–635. https://doi.org/10.1109/ICIPCA59209.
     behavior detection for patients in nursing rehabilitation center. J        2023.10257766
     Appl Sci Eng (Taiwan). 26:925–933. https://doi.org/10.6180/jase.       36. Patsch C, Zakour M, Chaudhari R (2022) Automatic recognition
     202307_26(7).0003                                                          of human activities combining model-based ai and machine learn-
 20. Denkovski S, Khan SS, Malamis B, Moon SY, Ye B, Mihailidis A               ing. SCITEPRESS, Setubal, Portugal, pp 15–22
     (2022) Multi visual modality fall detection dataset. IEEE Access       37. Cheng B, Su Y, Cai Y (2023) Research on real-time human fall
     10:106422–106435                                                           detection method based on yolov5-lite, pp 218–221. https://doi.
 21. Marshal S, Raj SA, Jebaseeli TJ, Niranjan S (2023) An image-               org/10.1109/ICEICT57916.2023.10245195
     based fall detection system for the elderly using yolov5, pp 493–      38. Guerra BMV, Schmid M, Beltrami G, Ramat S (2022) Neural
     498.https://doi.org/10.1109/ICACRS58579.2023.10404248                      networks for automatic posture recognition in ambient-assisted
 22. Li S, Man C, Shen A, Guan Z, Mao W, Luo S, Zhang R, Yu H                   living. Sensors 22
     (2022) A fall detection network by 2d/3d spatio-temporal joint         39. Inturi AR, Manikandan VM, Kumar MN, Wang S, Zhang Y
     models with tensor compression on edge. ACM Trans. Embed.                  (2023) Synergistic integration of skeletal kinematic features for
     Comput, Syst, p 21                                                         vision-based fall detection. Sensors 23. https://doi.org/10.3390/
 23. Eltahir MM, Yousif A, Alrowais F, Nour MK, Marzouk R,                      s23146283
     Dafaalla H, Elnour AAH, Aziz ASA Hamza MA (2023) Deep                  40. Sun H, Chen Y (2022)Real-time elderly monitoring for senior
     transfer learning-enabled activity identification and fall detection       safety by lightweight human action recognition, vol 2022-May,
     for disabled people. Computers, Materials and Continua 75:3239–            pp 1–6. IEEE Computer Society, Lincoln, NE, USA
     3255. https://doi.org/10.32604/cmc.2023.034037                         41. Wahla SQ, Ghani MU (2023) Visual fall detection from activities
 24. Inturi AR, Manikandan VM, Garrapally V (2022) A novel vision-              of daily living for assistive living. IEEE Access 11:108876–
     based fall detection scheme using keypoints of human skeleton              108890. https://doi.org/10.1109/ACCESS.2023.3321192
     with long short-term memory network. Arabian Journal for Sci-          42. Kim J-W, Choi Y-L, Jeong S-H, Han J (2022) A care robot with
     ence and Engineering                                                       ethical sensing system for older adults at home. Sensors (Basel)
 25. Ke Y, Yao Y, Xie Z, Xie H, Lin H, Dong C (2023) Empowering                 22:7515
     intelligent home safety: Indoor family fall detection with yolov5,     43. Jain, A., Akerkar, R., Srivastava, A.: Privacy-preserving human
     pp 942–949. https://doi.org/10.1109/DASC/PiCom/CBDCom/                     activity recognition system for assisted living environments. IEEE
     Cy59711.2023.10361490                                                      Transactions on Artificial Intelligence, pp 1–15 (2023) https://doi.
 26. Suarez JJP, Orillaza N, Naval P (2022) Afar: A real-time vision-           org/10.1109/TAI.2023.3323272
     based activity monitoring and fall detection framework using           44. Lin F, Wang Z, Zhao H, Qiu S, Shi X, Wu L, Gravina R, Fortino
     1d convolutional neural networks. Association for Computing                G (2022) Adaptive multi-modal fusion framework for activity
     Machinery, New York, NY, USA, pp 555–559                                   monitoring of people with mobility disability. IEEE J Biomed
                                                                                Health Inf 26:4314–4324



                                                                                                                                       123
9002                                                                                                                           G.M F. Xavier et al.


45. Rezaei A, Stevens MC, Argha A, Mascheroni A, Puiatti A, Lovell            using 1dcnn-bilstm deep learning. In: Proceedings of the 2023 5th
    NH (2023) An unobtrusive human activity recognition system                International Conference on Image, Video and Signal Processing.
    using low resolution thermal sensors, machine and deep learning.          IVSP ’23, pp 18–26. Association for Computing Machinery, New
    IEEE Trans Biomed Eng 70:115–124. https://doi.org/10.1109/                York, NY, USA. https://doi.org/10.1145/3591156.3591159
    TBME.2022.3186313                                                     64. Galvo YM, Ferreira J, Albuquerque VA, Barros P, Fernandes BJT
46. He J, Xiang M, Zhao X (2022) An elderly indoor behavior recog-            (2021) A multimodal approach using deep learning for fall detec-
    nition method based on improved slowfast network, vol 2216. IOP           tion. Expert Systems with Applications 168
    Publishing Ltd, San Francisco, CA, USA                                65. Sukreep S, Dajpratham P, Nukoolkit C, Yamsaengsung S, Kha-
47. Yazici A, Zhumabekova D, Nurakhmetova A, Yergaliyev Z, Yat-               jontantichaikun T, Mongkolnam P, Jaiyen S, Chongsuphajaisiddhi
    baz HY, Makisheva Z, Lewis M, Ever E (2023) A smart e-health              V (2023) Recognizing fall risk factors with convolutional neu-
    framework for monitoring the health of the elderly and disabled.          ral network, pp 391–396. https://doi.org/10.1109/JCSSE58229.
    INTERNET OF THINGS. 24 https://doi.org/10.1016/j.iot.2023.                2023.10202147
    100971                                                                66. Kang Y-K, Kang H-Y, Kim J-B (2021) A study of fall detection
48. Zhang C, Yang X (2022) Bed-leaving action recognition based               system using context cognition method. Institute of Electrical and
    on yolov3 and alphapose. Association for Computing Machinery,             Electronics Engineers Inc., Ho Chi Minh City, Vietnam, pp 79–83
    New York, NY, USA, pp 117–123                                         67. Mobsite S, Alaoui N, Boulmalf M, Ghogho M (2023) Semantic
49. Zhang Y, Liang W, Yuan X, Zhang S, Yang G, Zeng Z (2023) Deep             segmentation-based system for fall detection and post-fall posture
    learning based abnormal behavior detection for elderly healthcare         classification. Engineering Applications of Artificial Intelligence
    using consumer network cameras. IEEE Transactions on Con-                 117 https://doi.org/10.1016/j.engappai.2022.105616
    sumer Electronics 1. https://doi.org/10.1109/TCE.2023.3309852         68. Raj A, Singh D, Prakash C (2021) Active human pose estimation
50. Prasad SK, Ko Y-B (2022) Deep learning based human activity               for assisted living. Association for Computing Machinery, New
    recognition with improved accuracy, vol 2022-October, pp 1492–            York, NY, USA, pp 110–116
    1495. IEEE Computer Society, Jeju Island, Republic of Korea           69. Zhou F, Zhu G, Li X, Li H, Shi Q (2023) Towards pervasive
51. Gao P (2023) Development of yolo-based model for fall                     sensing: A multimodal approach via csi and rgb image modalities
    detection in iot smart home applications. Int J AdvComput                 fusion. In: Proceedings of the 3rd ACM MobiCom workshop on
    Sci Appl 14:1118–1125.https://doi.org/10.14569/IJACSA.2023.               integrated sensing and communications systems. ISACom ’23, pp
    01410117                                                                  25–30. Association for Computing Machinery, New York, NY,
52. Achirei S-D, Heghea M-C, Lupu R-G, Manta V-I (2022) Human                 USA. https://doi.org/10.1145/3615984.3616505
    activity recognition for assisted living based on scene understand-   70. Yang Y, Ren H, Li C, Ding C, Yu H (2021) An edge-device based
    ing. Applied Sciences (Switzerland) 12                                    fast fall detection using spatio-temporal optical flow model. Insti-
53. Gaya-Morey FX, Manresa-Yee C, Buades-Rubio JM (2023).                     tute of Electrical and Electronics Engineers Inc., New York, NY,
    Explainable activity recognition for the elderly. https://doi.org/        USA, pp 5067–5071
    10.1145/3612783.3612790                                               71. Zaghdoud A, Jemai O (2023) A metaplastic neural network tech-
54. Islam MM, Nooruddin S, Karray F (2022) Multimodal human                   nique for human activity recognition for alzheimer’s patients, pp
    activity recognition for smart healthcare applications, vol 2022-         1–6. https://doi.org/10.1109/INISTA59065.2023.10310437
    October, pp 196–203. Institute of Electrical and Electronics          72. Sultana A, Deb K, Dhar PK, Koshiba T (2021) Classification of
    Engineers Inc., Prague, Czech Republic                                    indoor human fall events using deep learning. Entropy (Basel) 23
55. Wang X, Talavera E, Karastoyanova D, Azzopardi G (2023) Fall          73. Siow CZ, Chin WH, Zhang Y, Naoyuki K (2023) A one-shot
    detection with a nonintrusive and first-person vision approach.           learning method for human activity recognition using extracted
    IEEE Sensors J 23:28304–28317. https://doi.org/10.1109/JSEN.              essential poses from push-fixed adaptive resonance theory, pp
    2023.3314828                                                              569–575. https://doi.org/10.1109/ICMLC58545.2023.10327934
56. Isoi H, Takefusa A, Nakada H, Oguchi M (2022) Performance             74. Divya V, Sri RL (2021) Docker-based intelligent fall detec-
    of domain adaptation schemes in video action recognition using            tion using edge-fog cloud infrastructure. IEEE Internet Things
    synthetic data. Association for Computing Machinery, New York,            J 8:8133–8144
    NY, USA, pp 70–79                                                     75. Shejy G, Chattani B, Batheja V, Patwa M, Deshmukh S
57. Rashid H-A, Mohsenin T (2023) Hac-pocd: Hardware-aware                    (2023) Activity monitoring and unusual activity detection for
    compressed activity monitoring and fall detector edge poc devices,        elderly homes, pp 1–5. https://doi.org/10.1109/ICACTA58201.
    pp 1–5. https://doi.org/10.1109/BioCAS58349.2023.10389023                 2023.10393535
58. Ji Q (2022) The design of the lightweight smart home system and       76. Chen Y, Du R, Luo K, Xiao Y (2021) Fall detection system based
    interaction experience of products for middle-aged and elderly            on real-time pose estimation and svm. Institute of Electrical and
    users in smart cities. Comput Intell Neurosci 2022:1279351                Electronics Engineers Inc., Nanchang, China, pp 990–993
59. Luo, B.: Human fall detection for smart home caring using yolo        77. Liu S, Mangla T, Shaowang T, Zhao J, Paparrizos J, Krishnan S,
    networks. Int J Adv Comput Sci Appl14:59–68 (2023) https://doi.           Feamster N (2023) Amir: Active multimodal interaction recogni-
    org/10.14569/IJACSA.2023.0140409                                          tion from video and network traffic in connected environments.
60. Ouyang X, Shuai X, Zhou J, Shi IW, Xie Z, Xing G, Huang J                 Proceedings of the ACM on Interactive, Mobile, Wearable and
    (2022) Cosmo: Contrastive fusion learning with small data for             Ubiquitous Technologies 7. https://doi.org/10.1145/3580818
    multimodal human activity recognition. Association for Comput-        78. Killian L, Julien M, Kevin B, Maxime L, Carolina B, Mélanie
    ing Machinery, New York, NY, USA, pp 324–337                              C, Nathalie B, Sylvain G, Sebastien G (2021) Fall prevention
61. Ravankar A, Rawankar A, Ravankar AA (2023) Real-time moni-                and detection in smart homes using monocular cameras and an
    toring of elderly people through computer vision. Artif Life Robot        interactive social robot. Association for Computing Machinery,
    28:496–501. https://doi.org/10.1007/s10015-023-00882-y                    New York, NY, USA, pp 7–12
62. Galvao YM, Portela L, Ferreira J, Barros P, Fagundes OADA,            79. Ammar SB, Ho T-C, Karray F, Gueaieb W (2023) Hacer: An
    Fernandes BJT (2021) A framework for anomaly identification               integrated remote monitoring platform for the elderly, pp 1–6.
    applied on fall detection. IEEE ACCESS 9:77264–77274                      https://doi.org/10.1109/iMETA59369.2023.10294645
63. Singh IS, Kaza P, Hosler Iv, PG, Chin ZY, Ang KK (2023) Real-
    time privacy preserving human activity recognition on mobile


123
Deep learning for computer vision based activity recognition...                                                                                9003


 80. Ge W, Luo X, Tao R, Shi Y (2021) Human fall detection algorithm            supervision. IEEE Transactions on Cognitive and Developmental
     based on mixed attention mechanism. Association for Computing              Systems 1
     Machinery, New York, NY, USA, pp 32–37                                 98. Li X, Chen W (2021) Fall recognition algorithm for the elderly
 81. Snoun A, Bouchrika T, Jemai O (2023) Deep-learning-based                   based on home service robot. Institute of Electrical and Electron-
     human activity recognition for alzheimer’s patients’ daily life            ics Engineers Inc., Zhengzhou, China, pp 329–335
     activities assistance. Neural Comput Appl 35:1777–1802. https://       99. Aarthi MS, Juliet S (2022) Intelligent fall detection system based
     doi.org/10.1007/s00521-022-07883-1                                         on sensor and image data for elderly monitoring, pp 1259–1265
 82. Pita MSU, Alon AS, Melo PMB, Hernandez RM, Magboo AI                  100. Fernando YPN, Gunasekara KDB, Sirikumara KP, Galappaththi
     (2021) Indoor human fall detection using data augmentation-                UE, Thilakarathna T, Kasthurirathna D (2021) Computer vision
     assisted transfer learning in an aging population for smart home-          based privacy protected fall detection and behavior monitoring
     care: A deep convolutional neural network approach. Institute of           system for the care of the elderly, vol. 2021-September, pp 1–7.
     Electrical and Electronics Engineers Inc., New York, NY, USA,              Institute of Electrical and Electronics Engineers Inc., New York,
     pp 64–69                                                                   NY, USA
 83. Raza MA, Chen L, Li N, Fisher RB (2023) Eatsense: Human cen-          101. Carrara F, Pasco L, Gennaro C, Falchi F (2022) Learning to
     tric, action recognition and localization dataset for understanding        detect fallen people in virtual worlds. Association for Comput-
     eating behaviors and quality of motion assessment. Image and               ing Machinery, New York, NY, USA, pp 126–130
     Vision Computing 137. https://doi.org/10.1016/j.imavis.2023.          102. Tseng H-T, Hsieh C-C, Hsu T-Y (2021) Elder action recognition
     104762                                                                     based on convolutional neural network and long short-term mem-
 84. Vaiyapuri T, Lydia EL, Sikkandar MY, Diaz VG, Pustokhina IV,               ory, pp 1–2
     Pustokhin DA (2021) Internet of things and deep learning enabled      103. Galvão YM, Portela L, Barros P, Araújo Fagundes RA, Fernandes
     elderly fall detection model for smart homecare. IEEE Access               BJT (2022) Onefall-gan: A one-class gan framework applied to
     9:113879–113888                                                            fall detection. Engineering Science and Technology, an Interna-
 85. Ouyang X, Xie Z, Fu H, Cheng S, Pan L, Ling N, Xing G, Zhou J,             tional Journal
     Huang J (2023) Harmony: Heterogeneous multi-modal federated           104. Ramirez H, Velastin SA, Meza I, Fabregas E, Makris D, Farias G
     learning through disentangled model training. In: Proceedings of           (2021) Fall detection and activity recognition using human skele-
     the 21st Annual International Conference on Mobile Systems,                ton features. IEEE Access 9:33532–33542
     Applications and Services. MobiSys ’23, pp 530–543. Associa-          105. Zheng H, Liu Y, Wu X, Zhang Y (2022) Realization of elderly
     tion for Computing Machinery, New York, NY, USA. https://doi.              fall integration monitoring system based on alphapose and yolov4.
     org/10.1145/3581791.3596844                                                Institute of Electrical and Electronics Engineers Inc., Hangzhou,
 86. Liu J, Tan R, Han G, Sun N, Kwong S (2021) Privacy-preserving              China, pp 604–620
     in-home fall detection using visual shielding sensing and private     106. Wang X, Talavera E, Karastoyanova D, Azzopardi G (2021) Fall
     information-embedding. IEEE Trans Multimed 23:3684–3699                    detection and recognition from egocentric visual data: A case
 87. Fayad M, Hachani M-Y, Mostefaoui A, Chouali S, Yahiaoui R                  study. Lecture Notes in Computer Science (including subseries
     (2022) Elderly fall detection: A lightweight kinect based deep             Lecture Notes in Artificial Intelligence and Lecture Notes in
     learning approach. Association for Computing Machinery, New                Bioinformatics). 12661 LNCS, pp 431–443
     York, NY, USA, pp 89–95                                               107. Zahan S, Hassan GM, Mian A (2022) Sdfa: Structure aware dis-
 88. Zherdev D, Zherdeva L, Agapov S, Sapozhnikov A, Nikonorov                  criminative feature aggregation for efficient human fall detection
     A, Chaplygin S (2021)Producing synthetic dataset for human fall            in video. IEEE Transactions on Industrial Informatics, pp 1–9
     detection in ar/vr environments. Applied Sciences (Switzerland)       108. Hasib R, Khan KN, Yu M, Khan MS (2021) Vision-based human
     11                                                                         posture classification and fall detection using convolutional neural
 89. Meraikhi SA, Al-Rajab M (2022) A multimodal approach of                    network, pp 74–79
     machine and deep learnings to enhance the fall of elderly peo-        109. Rajalaxmi RR, Gothai E, Suganth V, Vignesh S, Varun T (2022)
     ple. J Inf Technol Manag 14:168–184                                        Vision based fall detection using optimized convolutional neural
 90. Feng X, Jiang W (2021) Research on human fall detection based              network. Institute of Electrical and Electronics Engineers Inc.,
     on tiny-yolov3 algorithm. Association for Computing Machinery,             Coimbatore, India, pp 1–6
     New York, NY, USA, pp 1326–1330                                       110. Wang J, Yang W (2021) Action recognition based on cross spatital
 91. Chen P-C, Chang C-H, Chan Y-W, Tasi Y-T, Chu WC (2022) An                  temporal graph convolution. Association for Computing Machin-
     approach to real-time fall detection based on openpose and lstm,           ery, New York, NY, USA
     pp 1573–1578                                                          111. Anitha G, Priya SB (2022) Vision based real time monitoring sys-
 92. Xie L, Yang Y, Zeyu F, Naqvi SM (2021) Skeleton-based fall                 tem for elderly fall event detection using deep learning. Comput
     events classification with data fusion. Institute of Electrical and        Syst Sci Eng 42:87–103
     Electronics Engineers Inc., Karlsruhe, Germany                        112. Budisteanu E-A, Mocanu IG (2021) Combining supervised and
 93. Anwary AR, Rahman MA, Muzahid AJM, Ashraf AWU, Pat-                        unsupervised learning algorithms for human activity recognition.
     wary M, Hussain A (2022) Deep learning enabled fall detection              SENSORS 21
     exploiting gait analysis. Annu Int Conf IEEE Eng Med Biol Soc         113. Tu L, Ouyang X, Zhou J, He Y, Xing G (2021) Feddl: Federated
     2022:4683–4686                                                             learning via dynamic layer sharing for human activity recognition.
 94. Fatima M, Yousaf, MH, Yasin A, Velastin SA (2021) Unsuper-                 Association for Computing Machinery, New York, NY, USA, pp
     vised fall detection approach using human skeletons, pp 1–6                15–28
 95. Lau XL, Connie T, Goh MKO, Lau SH (2022) Fall detection and           114. Jaouedi N, Perales FJ, Buades JM, Boujnah N, Bouhlel MS (2020)
     motion analysis using visual approaches. Int J Technol 13:1173–            Prediction of human activities based on a new structure of skeleton
     1182                                                                       features and deep learning model. Sensors (Switzerland). 20:1–15
 96. Berlin SJ, John M (2021) Vision based human fall detection with       115. Tianming Z, Pengbiao Z, Peng X, Bintao W (2021) Multi-stream
     siamese convolutional neural networks. Journal of Ambient Intel-           cnn-lstm network with partition strategy for human action recog-
     ligence and Humanized Computing                                            nition. Association for Computing Machinery, New York, NY,
 97. Nigam N, Dutta T, Verma D (2022) Fall-perceived action recog-              USA, pp 431–435
     nition of persons with neurological disorders using semantic


                                                                                                                                       123
9004                                                                                                                               G.M F. Xavier et al.


116. Lang X, Feng Z, Yang X (2020) Research on human-robot nat-              133. Byeon Y-H, Kim D, Lee J, Kwak K-C (2021) Body and hand-
     ural interaction algorithm based on body potential perception.               object roi-based behavior recognition using deep learning. Sen-
     Association for Computing Machinery, New York, NY, USA, pp                   sors 21:1–23
     260–264                                                                 134. Kumar D, Ravikumar AK, Dharmalingam V, Kafle VP (2019)
117. Lumetzberger J, Raoofpour A, Kampel M (2021) Privacy preserv-                Elderly health monitoring system with fall detection using multi-
     ing getup detection. Association for Computing Machinery, New                feature based person tracking. Institute of Electrical and Electron-
     York, NY, USA, pp 234–243                                                    ics Engineers Inc., Atlanta, GA, USA, pp 1–9
118. Popescu A-C, Mocanu I, Cramariuc B (2020) Fusion mechanisms             135. Hwang H, Jang C, Park G, Cho J, Kim I-J (2021) Eldersim: A
     for human activity recognition using automated machine learning.             synthetic data generation platform for human action recognition
     IEEE Access 8:143996–144014                                                  in eldercare applications. IEEE Access 1
119. Badarch L, Gochoo M, Batnasan G, Alnajjar F, Tan T-H (2021)             136. Maldonado-Bascón S, Iglesias-Iglesias C, Martín-Martín P,
     Ultra-low resolution infrared sensor-based wireless sensor net-              Lafuente-Arroyo S (2019) Fallen people detection capabilities
     work for privacy-preserved recognition of daily activities of                using assistive robot. Electronics (Switzerland) 8
     living. Institute of Electrical and Electronics Engineers Inc.,         137. Han K, Yang Q, Huang Z (2020) A two-stage fall recognition
     Boston, MA, USA                                                              algorithm based on human posture features. Sensors (Switzerland)
120. Mathe E, Tranou A, Spyrou E, Perantonis S (2020) Human action                20:1–21
     recognition with deep learning techniques. Association for Com-         138. Ferooz F, Ashraf MA, Hussain W, Butt AH, Khan YD (2019) Per-
     puting Machinery, New York, NY, USA                                          son fall recognition by using deep learning: Convolutional neural
121. Giannakos I, Mathe E, Spyrou E, Mylonas P (2021) A study on                  networks and image category classification using bag of feature,
     the effect of occlusion in human activity recognition. Association           pp 1–6
     for Computing Machinery, New York, NY, USA, pp 473–482                  139. Chiang JWH, Zhang L (2020) Deep learning-based fall detection,
122. Rafferty J, Medina-Quero J, Quinn S, Saunders C, Ekerete I,                  vol 12, pp 891–898. WORLD SCIENTIFIC PUBL CO PTE LTD.
     Nugent C, Synnott J, Garcia-Constantino M (2019) Thermal                     Singapore
     vision based fall detection via logical and data driven processes.      140. Safarzadeh M, Alborzi Y, Ardekany AN (2019) Real -time fall
     Institute of Electrical and Electronics Engineers Inc., Honolulu,            detection and alert system using pose estimation, pp 508–511
     HI, USA, pp 35–40                                                       141. Serpa YR, Nogueira MB, Neto PPM, Rodrigues MAF (2020)
123. Awal MI, Iksan LH, Fhamy RZ, Basuki DK, Sukaridhoto S, Wada                  Evaluating pose estimation as a solution to the fall detection prob-
     K (2021) Action recognition with spatiotemporal analysis and                 lem. Institute of Electrical and Electronics Engineers Inc., New
     support vector machine for elderly monitoring system. Institute              York, NY, USA, pp 1–7
     of Electrical and Electronics Engineers Inc., Surabaya, Indonesia,      142. Huang Z, Liu Y, Fang Y, Horn BKP (2019) Video-based fall detec-
     pp 470–475                                                                   tion for seniors with human pose estimation. Institute of Electrical
124. Wang H, Gao Z, Lin W (2019) A fall detection system based                    and Electronics Engineers Inc., Boston, MA, USA
     on convolutional neural networks. Association for Computing             143. Berardini D, Moccia S, Migliorelli L, Pacifici I, Massimo PD,
     Machinery, New York, NY, USA, pp 242–246                                     Paolanti M, Frontoni E(2020) Fall detection for elderly-people
125. Sivakumar M, Iswarya E, Malusha K, Priyadharshini TY (2021)                  monitoring using learned features and recurrent neural networks.
     Computer vision based wellness analysis of geriatrics. Institute of          Experimental Results 1
     Electrical and Electronics Engineers Inc., Coimbatore, India, pp        144. Ma C, Shimada A, Uchiyama H, Nagahara H, Taniguchi R-i
     1762–1765                                                                    (2019) Fall detection using optical level anonymous image sens-
126. Wang F, Liu J, Hu GD (2019) A novel indoor human fall detection              ing system. Opt Laser Technol 110:44–61
     method based on an end-to-end neural network and bagged tree            145. Romaissa BD, Mourad O, Brahim N, Yazid B (2020) Fall detec-
     classifier. Association for Computing Machinery, New York, NY,               tion using body geometry in video sequences, pp 1–5
     USA, pp 384–389                                                         146. Cameiro SA, Silva GPD, Leite GV, Moreno R, Guimaraes SJF,
127. Iksan LH, Awal MI, Fhamy RZ, Pratama AA, Basuki DK,                          Pedrini H (2019) Multi-stream deep convolutional network using
     Sukaridhoto S (2021) Implementation of cloud based action                    high-level features applied to fall detection in video sequences,
     recognition backend platform, pp 1–6                                         vol 2019-June, pp 293–298. IEEE Computer Society, New York,
128. Brieva J, Ponce H, Moya-Albor E, Martinez-Villasenor L (2019)                NY, USA
     An intelligent human fall detection system using a vision-based         147. Wang X, Jia K (2020) Human fall detection algorithm based on
     strategy. Institute of Electrical and Electronics Engineers Inc., Los        yolov3. Institute of Electrical and Electronics Engineers Inc., Bei-
     Alamitos, California, USA, pp 1–5                                            jing, China, pp 50–54
129. Nambissan GS, Mahajan P, Sharma S, Gupta N (2021) The varie-            148. Siriwardhana C, Madhuranga D, Madushan R, Gunasekera K
     gated applications of deep learning techniques in human activity             (2019) Classification of activities of daily living based on depth
     recognition. Association for Computing Machinery, New York,                  sequences and audio. Institute of Electrical and Electronics Engi-
     NY, USA, pp 223–233                                                          neers Inc., Kandy, Sri Lanka, pp 278–283
130. Hassan MFA, Hussain A, Saad MHM, Yusof Y (2019) Con-                    149. Lv X, Gao Z, Yuan C, Li M, Chen C (2020) Hybrid real-time fall
     volution neural network-based action recognition for fall event              detection system based on deep learning and multi-sensor fusion.
     detection. International Journal of Advanced Trends in Computer              Institute of Electrical and Electronics Engineers Inc., Shenzhen,
     Science and Engineering 8                                                    China, pp 386–391
131. Tan T-H, Hus J-H, Liu S-H, Huang Y-F, Gochoo M (2021) Using             150. Phyo CN, Zin TT, Tin P (2019) Deep learning for recognizing
     direct acyclic graphs to enhance skeleton-based action recognition           human activities using motions of skeletal joints. IEEE Trans Con-
     with a linear-map convolution neural network. Sensors 21                     sum Electron 65:243–252
132. Mohamed NA, Zulkifley MA, Kamari NAM (2019) Convolu-                    151. Li J, Xia S-T, Ding Q (2020) Multi-level recognition on falls from
     tional neural networks tracker with deterministic sampling for               activities of daily living. Association for Computing Machinery,
     sudden fall detection. Institute of Electrical and Electronics Engi-         New York, NY, USA, pp 464–471
     neers Inc., New York, NY, USA, pp 1–5                                   152. Saini R, Kumar P, Kaur B, Roy PP, Dogra DP, Santosh KC
                                                                                  (2019) Kinect sensor-based interaction monitoring system using



123
Deep learning for computer vision based activity recognition...                                                                             9005


     the blstm neural network in healthcare. Int J MachLearn Cybern         172. Papandreou G, Zhu T, Chen L-C, Gidaris S, Tompson J, Murphy
     10:2529–2540                                                                K (2018) Personlab: Person pose estimation and instance segmen-
153. Chen Y, Li W, Wang L, Hu J, Ye M (2020) Vision-based fall                   tation with a bottom-up, part-based, geometric embedding model.
     event detection in complex background using attention guided                In: Computer Vision – ECCV 2018, pp 282–299. Springer, Cham
     bi-directional lstm. IEEE Access 8:161337–161348                       173. TensorFlow: MoveNet. https://github.com/tensorflow/tfjs-models
154. Das S, Dai R, Koperski M, Minciullo L, Garattoni L, Bremond F,              /tree/master/pose-detection/src/movenet
     Francesca G (2019) Toyota smarthome: Real-world activities of          174. Fang H-S, Xie S, Tai Y-W, Lu C (2017) Rmpe: Regional multi-
     daily living, vol. 2019-October, pp 833–842. Institute of Electrical        person pose estimation. In: 2017 IEEE international conference
     and Electronics Engineers Inc., Seoul, Korea (South)                        on computer vision (ICCV), pp 2353–2362
155. Khraief C, Benzarti F, Amiri H (2020) Elderly fall detection based     175. Xiu Y, Li J, Wang H, Fang Y, Lu C (2018) Pose flow: Efficient
     on multi-stream deep convolutional networks. Multimed Tools                 online pose tracking. In: BMVC
     Appl 79:19537–19560                                                    176. Zhang J, Zhu Z, Zou W, Li P, Li Y, Su H, Huang G (2019)
156. Phyo CN, Zin TT, Tin P (2019) Complex human-object interac-                 FastPose: Towards Real-time Pose Estimation and Tracking via
     tions analyzer using a dcnn and svm hybrid approach. Applied                Scale-normalized Multi-task Networks
     Sciences (Switzerland) 9                                               177. Howard A, Zhu M, Chen B, Kalenichenko D, Wang W, Weyand T,
157. Kharazian Z, Rahat M, Fatemizadeh E, Nasrabadi AM (2020)                    Andreetto M, Adam H (2017) Mobilenets: Efficient convolutional
     Increasing safety at smart elderly homes by human fall detection            neural networks for mobile vision applications
     from video using transfer learning approaches. Research Publish-       178. Luvizon DC, Picard D, Tabia H (2018) 2D/3D Pose Estimation
     ing Services, Venice, Italy, pp 2774–2780                                   and Action Recognition Using Multitask Deep Learning. https://
158. Nan M, Ghit, ă AS, Gavril A-F, Trascau M, Sorici A, Cramariuc              doi.org/10.1109/CVPR.2018.00539
     B, Florea AM (2019) Human action recognition for social robots,        179. Duan H, Zhao Y, Chen K, Lin D, Dai B (2022) Revisiting skeleton-
     pp 675–681                                                                  based action recognition. In: 2022 IEEE/CVF Conference on
159. Tateno S, Meng F, Qian R, Li T (2020) Human motion detection                Computer Vision and Pattern Recognition (CVPR), pp 2959–
     based on low resolution infrared array sensor, pp 1016–1021                 2968. https://doi.org/10.1109/CVPR52688.2022.00298
160. Mehr HD, Polat H (2019) Human activity recognition in smart            180. Li S, Man C, Shen A, Guan Z, Mao W, Luo S, Zhang R, Yu H
     home with deep learning approach. IEEE, New York, NY, USA,                  (2022) A fall detection network by 2d/3d spatio-temporal joint
     pp 149–153                                                                  models with tensor compression on edge. ACM Trans Embed
161. Buzzelli M, Albé A, Ciocca G (2020) A vision-based system for               Comput Syst 21
     monitoring elderly people at home. Applied Sciences (Switzer-          181. Hinton GE, Salakhutdinov RR (2006) Reducing the dimension-
     land) 10                                                                    ality of data with neural networks. Sci 313(5786):504–507
162. Jalal A, Mahmood M, Hasan AS (2019) Multi-features descriptors         182. Goodfellow I, Pouget-Abadie J, Mirza M, Xu B, Warde-Farley D,
     for human activity tracking and recognition in indoor-outdoor               Ozair S, Courville, A., Bengio, Y (2014) Generative Adversarial
     environments, pp 371–376                                                    Nets. Curran Associates, Inc
163. Tan T-H, Gochoo M, Chen H-S, Liu S-H, Huang Y-F (2020) Activ-          183. Koch GR (2015) Siamese neural networks for one-shot image
     ity recognition based on dcnn and kinect rgb images, pp 1–4                 recognition
164. Ding Q, Yang F, Li J, Wu S, Zhao B, Wang Z, Xia S-T (2019) Rt-         184. Nogas J, Khan S, Mihailidis A (2020) Deepfall: Non-invasive fall
     adi: Fast real-time video representation for multi-view human fall          detection with deep spatio-temporal convolutional autoencoders.
     detection. Institute of Electrical and Electronics Engineers Inc.,          Journal of Healthcare Informatics Research. 4
     New York, NY, USA, pp 13–18                                            185. Hampiholi B, Jarvers C, Mader W, Neumann H (2020) Depthwise
165. Atikuzzaman M, Rahman TR, Wazed E, Hossain MP, Islam MZ                     separable temporal convolutional network for action segmenta-
     (2020) Human activity recognition system from different poses               tion. In: 2020 International conference on 3D vision (3DV), pp
     with cnn. Institute of Electrical and Electronics Engineers Inc.,           633–641
     New York, NY, USA, pp 1–5                                              186. Wang Q, Gao J, Xing J, Zhang M, Hu W (2017) DCFNet: Dis-
166. Priya GGL, Jain M, Santosh KC, Mouli PVSSRC (2019) Tempo-                   criminant Correlation Filters Network for Visual Tracking. arXiv
     ral super-pixel based convolutional neural network (ts-cnn) for        187. Iandola F, Han S, Moskewicz M, Ashraf K, Dally W, Keutzer K
     human activity recognition in unconstrained videos. Commun                  (2016) Squeezenet: Alexnet-level accuracy with 50x fewer param-
     Comput Inf Sci 1035:255–264                                                 eters and ¡0.5mb model size
167. Gul MA, Yousaf MH, Nawaz S, Rehman ZU, Kim H (2020)                    188. Tan M, Le QV (2020) EfficientNet: Rethinking Model Scaling for
     Patient monitoring by abnormal human activity recognition based             Convolutional Neural Networks
     on cnn architecture. Electronics (Switzerland) 9:1–14                  189. Tran D, Bourdev L, Fergus R, Torresani L, Paluri M (2015) Learn-
168. Martínez-Villaseñor L, Ponce H, Brieva J, Moya-Albor E,                     ing spatiotemporal features with 3d convolutional networks, pp
     Núñez-Martínez J, Peñafort-Asturiano C (2019) Up-fall detection             4489–4497
     dataset: A multimodal approach. Sensors 19                             190. Girshick R, Donahue J, Darrell T, Malik J (2013) Rich feature
169. Cao Z, Hidalgo Martinez G, Simon T, Wei S, Sheikh YA                        hierarchies for accurate object detection and semantic segmenta-
     (2019) Openpose: Realtime multi-person 2d pose estimation using             tion. In: Proceedings of the IEEE computer society conference on
     part affinity fields. IEEE Transactions on Pattern Analysis and             computer vision and pattern recognition
     Machine Intelligence                                                   191. Redmon J, Divvala S, Girshick R, Farhadi A (2016) You only look
170. Fang H-S, Li J, Tang H, Xu C, Zhu H, Xiu Y, Li Y-L, Lu C (2022)             once: Unified, real-time object detection, pp 779–788
     Alphapose: Whole-body regional multi-person pose estimation            192. Kirillov A, Wu Y, He K, Girshick R (2020) Pointrend: Image
     and tracking in real-time. IEEE Transactions on Pattern Analysis            segmentation as rendering. In: 2020 IEEE/CVF conference on
     and Machine Intelligence                                                    computer vision and pattern recognition (CVPR), pp 9796–9805.
171. Lugaresi C, Tang J, Nash H, McClanahan C, Uboweja E, Hays                   https://doi.org/10.1109/CVPR42600.2020.00982
     M, Zhang F, Chang C-L, Yong MG, Lee J, Chang W-T, Hua W,               193. Hui T-W, Tang X, Loy CC (2018) LiteFlowNet: A lightweight
     Georg M, Grundmann M (2019) MediaPipe: A Framework for                      convolutional neural network for optical flow estimation
     Building Perception Pipelines. arXiv



                                                                                                                                     123
9006                                                                                                                            G.M F. Xavier et al.


194. Feichtenhofer C, Fan H, Malik J, He K (2019) SlowFast                    Uszkoreit J, Houlsby N (2021) An image is worth 16x16 words:
     Networks for Video Recognition. https://doi.org/10.1109/ICCV.            Transformers for image recognition at scale. In: International con-
     2019.00630                                                               ference on learning representations
195. Szegedy C, Vanhoucke V, Ioffe S, Shlens J, Wojna Z (2016)           216. Kwolek B, Kepski M (2014) Human fall detection on embedded
     Rethinking the inception architecture for computer vision. In:           platform using depth maps and wireless accelerometer. Comput
     2016 IEEE Conference on Computer Vision and Pattern Recog-               Methods Programs Biomed 117:489–501
     nition (CVPR), pp 2818–2826                                         217. Charfi I, Miteran J, Dubois J, Atri M, Tourki R (2013) Optimized
196. Hochreiter S, Schmidhuber J (1997) Long Short-Term Memory.               spatio-temporal descriptors for real-time fall detection: compari-
     Neural Comput 9(8):1735–1780                                             son of support vector machine and adaboost-based classification.
197. Simonyan K, Zisserman A (2014) Very deep convolutional net-              J Electron Imaging 22:41106
     works for large-scale image recognition. arXiv:1409.1556            218. Auvinet E, Rougier C, Meunier J, St-Arnaud A, Rousseau J (2011)
198. He K, Zhang X, Ren S, Sun J (2016) Deep residual learning for            Multiple cameras fall data set
     image recognition. In: 2016 IEEE conference on computer vision      219. Shahroudy A, Liu J, Ng T, Wang G (2016) Ntu rgb+d: A large
     and pattern recognition (CVPR), pp 770–778                               scale dataset for 3d human activity analysis
199. Kipf TN, Welling M (2017) Semi-supervised classification with       220. Adhikari K, Bouchachia H, Nait-Charif H (2017) Activity recog-
     graph convolutional networks                                             nition for indoor fall detection using convolutional neural net-
200. Carreira J, Zisserman A (2017) Quo Vadis, Action Recognition?            work. Institute of Electrical and Electronics Engineers Inc., New
## A New Model and the Kinetics Dataset. https://doi.org/10.1109/           York, NY, USA, pp 81–84
     CVPR.2017.502                                                       221. Wang J, Liu Z, Wu Y, Yuan J (2012) Mining actionlet ensemble
201. Cho K, Merrienboer B, Bahdanau D, Bengio Y (2014) On                     for action recognition with depth cameras, pp 1290–1297
     the properties of neural machine translation: Encoder-decoder       222. Chen C, Jafari R, Kehtarnavaz N (2015) Utd-mhad: A multimodal
     approaches                                                               dataset for human action recognition utilizing a depth camera and
202. Vaswani A, Shazeer N, Parmar N, Uszkoreit J, Jones L, Gomez              a wearable inertial sensor, pp 168–172
     A, Kaiser L, Polosukhin I (2017) Attention is all you need          223. Sung J, Ponce C, Selman B, Saxena A (2012) Unstructured human
203. Liu Z, Wang L, Wu W, Qian C, Lu T (2021) Tam: Tempo-                     activity detection from rgbd images, pp 842–849
     ral adaptive module for video recognition. In: 2021 IEEE/CVF        224. Jang J, Kim D, Park C, Jang M, Lee J, Kim D (2020) Etri-
     International Conference on Computer Vision (ICCV), pp 13688–            activity3d: A large-scale rgb-d dataset for robots to recognize daily
     13698. https://doi.org/10.1109/ICCV48922.2021.01345                      activities of the elderly, pp 10990–10997
204. Yang C, Xu Y, Shi J, Dai B, Zhou B (2020) Temporal pyramid          225. Kuehne H, Jhuang H, Garrote E, Poggio T, Serre T (2011) Hmdb:
     network for action recognition. In: 2020 IEEE/CVF conference             A large video database for human motion recognition, pp 2556–
     on computer vision and pattern recognition (CVPR), pp 588–597.           2563
     https://doi.org/10.1109/CVPR42600.2020.00067                        226. Schuldt C, Laptev I (2004) Caputo B. Recognizing human actions:
205. Gao C, Zou Y, Huang J (2018) iCAN: instance-centric attention            a local svm approach vol 3, pp 32–363
     network for human-object interaction detection. BMVA Press          227. Koppula H, Gupta R, Saxena A (2012) Learning human activi-
206. Chollet F (2017) Xception: Deep learning with depthwise separa-          ties and object affordances from rgb-d videos. The International
     ble convolutions. In: 2017 IEEE conference on computer vision            Journal of Robotics Research 32
     and pattern recognition (CVPR), pp 1800–1807. https://doi.org/      228. Amiri SM, Pourazad MT, Nasiopoulos P, Leung VCM (2013)
     10.1109/CVPR.2017.195                                                    Non-intrusive human activity monitoring in a smart home envi-
207. Wang L, Xiong Y, Wang Z, Qiao Y, Lin D, Tang X, Van Gool L               ronment, pp 606–610
     (2016) Temporal segment networks: Towards good practices for        229. Vanrumste B, Debard G, Croonenborghs T, Mertes G, Baldewijns
     deep action recognition. In: Leibe B, Matas J, Sebe N, Welling M         G (2016) Bridging the gap between real-life data and simulated
     (eds) Computer Vision - ECCV 2016, pp 20–36. Springer, Cham              data by providing a highly realistic fall dataset for evaluating
208. Liu Z, Ning J, Cao Y, Wei Y, Zhang Z, Lin S, Hu H (2022) Video           camera-based fall detection algorithms. Healthcare Technology
     swin transformer. In: 2022 IEEE/CVF conference on computer               Letters 3
     vision and pattern recognition (CVPR), pp 3192–3201. https://       230. Liu J, Shahroudy A, Perez M, Wang G, Duan L-Y, Kot A (2019)
     doi.org/10.1109/CVPR52688.2022.00320                                     Ntu rgb+d 120: A large-scale benchmark for 3d human activ-
209. Bertasius G, Wang H, Torresani L (2021) Is space-time attention          ity understanding. IEEE Transactions on Pattern Analysis and
     all you need for video understanding? In: ICML, vol 2, pp 4              Machine Intelligence, pp 1–18
210. Baradel F, Wolf C, Mille J, Taylor G (2018) Glimpse clouds:         231. wang J, Nie X, Xia Y, Wu Y, Zhu S (2014) Cross-view action
     Human activity recognition from unstructured feature points, pp          modeling, learning, and recognition. In: Proceedings of the IEEE
     469–478                                                                  computer society conference on computer vision and pattern
211. Tang J, Xia J, Mu X, Pang B, Lu C (2020) Asynchronous inter-             recognition
     action aggregation for action detection. In: Computer Vision –      232. Soomro K, Zamir A, Shah M (2012) Ucf101: A dataset of 101
     ECCV 2020, pp 71–87. Springer, Cham                                      human actions classes from videos in the wild. CoRR
212. Krizhevsky A, Sutskever I, Hinton GE (2017) Imagenet classifi-      233. Xia L, Chen C-C, Aggarwal JK (2012) View invariant human
     cation with deep convolutional neural networks. Commun ACM               action recognition using histograms of 3d joints, pp 20–27
     60(6):84–90. https://doi.org/10.1145/3065386                        234. Rahmani H, Mahmood A, Huynh D, Mian A (2016) Histogram of
213. Lu L, Lu Y, Yu R, Di H, Zhang L, Wang S (2020) Gaim: Graph               oriented principal components for cross-view action recognition.
     attention interaction model for collective activity recognition.         IEEE Trans Pattern Anal Mach Intell 38:2430–2443
     IEEE Trans Multimed 22(2):524–539. https://doi.org/10.1109/         235. Kong Y, Jia Y, Fu Y (2012) Learning human interaction by inter-
     TMM.2019.2930344                                                         active phrases, pp 300–313
214. He K, Gkioxari G, Dollár P, Girshick R (2020) Mask r-cnn. IEEE      236. Wei H, Chopada P, Kehtarnavaz N (2020) C-mhad: Continuous
     Trans Pattern Anal Mach Intell 42(2):386–397. https://doi.org/10.        multimodal human action dataset of simultaneous video and iner-
     1109/TPAMI.2018.2844175                                                  tial sensing. Sensors 20
215. Dosovitskiy A, Beyer L, Kolesnikov A, Weissenborn D, Zhai X,        237. Chen Z (2019) Fall detection dataset
     Unterthiner T, Dehghani M, Minderer M, Heigold G, Gelly S,


123
Deep learning for computer vision based activity recognition...                                           9007


238. Gasparrini S, Cippitelli E, Gambi E, Spinsante S, Wåhslén J,           Cristina Manresa-Yee received her
     Orhan I, Lindh T (2016) Proposal and experimental evaluation of        degree in Computer Science and
     fall detection solution based on wearable and depth data fusion,       her Ph. D. in Computer Science
     vol 399, pp 99–108                                                     from the University of Balearic
239. Maldonado-Bascón S, Iglesias-Iglesias C, Martín-Martín P,              Islands. She is currently an Asso-
     Lafuente-Arroyo S (2021) Elderly Dataset                               ciate Professor at the University
240. Weinland D, Ronfard R, Boyer E (2006) Free viewpoint action            of the Balearic Islands. Her
     recognition using motion history volumes. Comp Vision Image            research interests include human-
     Underst 104:249–257                                                    computer interaction, computer
241. Kay W, Carreira J, Simonyan K, Zhang B, Hillier C, Vijaya-             vision and explainable AI.
     narasimhan S, Viola F, Green T, Back T, Natsev P, Suleyman
     M, Zisserman A (2017) The kinetics human action video dataset.
     arXiv
242. Carreira J, Noland E, Banki-Horvath A, Hillier C, Zisserman A
     (2018) A Short Note about Kinetics-600. arXiv
243. Smaira L, Carreira J, Noland E, Clancy E, Wu A, Zisserman A
     (2020) A Short Note on the Kinetics-700-2020 Human Action              José M. Buades-Rubio received
     Dataset. arXiv                                                         his degree in Computer Sci-
244. Chua J-L, Chang Y, Lim W (2013) A simple vision-based fall             ence and his Ph. D. in Computer
     detection technique for indoor video surveillance. Signal, Image       Science from the University of
     and Video Processing, p 9                                              Balearic Islands. He is currently
245. Chen Y, Yu L, Ota K, Dong M (2018) Robust activity recognition         an Associate Professor at the Uni-
     for aging society. IEEE J Biomed Health Inform 22:1754–1764            versity of the Balearic Islands. His
246. Epstein D, Chen B, Vondrick C (2020) Oops! predicting uninten-         research interests include com-
     tional action in video. https://doi.org/10.1109/CVPR42600.2020.        puter graphics, computer vision
     00100                                                                  and artificial intelligence.
247. Liu C, Hu Y, Li Y, Song S, Liu J (2017) PKU-MMD: A Large
     Scale Benchmark for Continuous Multi-Modal Human Action
     Understanding. arXiv
248. Yao B, Jiang X, Khosla A, Lin A, Guibas L, Li F-F (2011) Human
     action recognition by learning bases of action attributes and parts,
     pp 1331–1338
249. Gupta S, Malik J (2015) Visual Semantic Role Labeling. arXiv
250. Fan Y, Levine M, Gongjian W, Qiu S (2017) A deep neural network
     for real-time detection offalling humans in naturally occurring
     scenes. Neurocomputing. 260
251. Shotton J, Fitzgibbon A, Cook M, Sharp T, Finocchio M, Moore R,
     Kipman A, Blake A (2011) Real-time human pose recognition in
     parts from single depth images. CVPR 2011:1297–1304. https://
     doi.org/10.1109/CVPR.2011.5995316



Publisher’s Note Springer Nature remains neutral with regard to juris-
dictional claims in published maps and institutional affiliations.



                                      F. Xavier Gaya-Morey is a Ph.
                                      D. candidate and professor at
                                      the University of the Balearic
                                      Islands. He holds a bachelor’s
                                      degree in computer engineering
                                      and a master’s degree in data sci-
                                      ence and computer vision. His
                                      research is centered on the areas
                                      of explainable artificial intelli-
                                      gence and computer vision, with
                                      special focus on their applications
                                      to improve the life quality of the
                                      older adults.




                                                                                                   123

