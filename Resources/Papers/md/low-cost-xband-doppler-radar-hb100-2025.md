Low-Cost X-band Doppler Radar for Nadir Velocity Detection

Author
Thiel, David V, Cabrita, Julian, Fickenscher, Thomas, Espinosa, Hugo G


Published
2025


## Conference Title
2025 6th Australian Microwave Symposium (AMS)


Version
Accepted Manuscript (AM)


DOI
10.1109/ams63679.2025.10937823


Rights statement
This work is covered by copyright. You must assume that re-use is limited to personal use and
that permission from the copyright owner must be obtained for all other uses. If the document
is available under a specified licence, refer to the licence for details of permitted re-use. If you
believe that this work infringes copyright please make a copyright takedown request using the
form at https://www.griffith.edu.au/copyright-matters.


Downloaded from
https://hdl.handle.net/10072/435873


## Griffith Research Online
https://research-repository.griffith.edu.au
6th Australian Microwave Symposium, Gold Coast, Australia, 10 – 11 February 2025


              Low-Cost X-band Doppler Radar for Nadir
## Velocity Detection
                            David V. Thiel1, Julian Cabrita2, Thomas Fickenscher3, Hugo G. Espinosa1
                      1
                          School of Engineering and Built Environment, Griffith University, QLD 4111, Australia
                             2
                               SeaTech School of Engineering, University of Toulon, 83130 La Garde, France
                                3
                                 Helmut Schmidt University, Holstenhofweg 85, 22043 Hamburg, Germany
                                                         d.thiel@griffith.edu.au


    Abstract— The low-cost, low power, small X-band (10.5 GHz)         elevation (E-plane). The module requires 4.75-5.25 V DC with
Doppler radar module HB100, was designed and is used                   a CW output signal at 10.525 GHz. The antenna configuration is
commercially for movement detection. As with most radars, radial       a rectangular arrangement of four patches with linear
displacements of targets provide positive or negative Doppler          polarization (Fig 1). The output signal from the module was
shifts – depending whether they are approaching or receding in         amplified, sampled at 10,000 samples per second and logged by
the radial direction. However, in many applications the movement       computer via a USB port. The radar module was held in position
tangential to the radial direction is of interest as well. The radar   in a hole on a wooden plank and connected via a 2 m USB cable.
return from a short steel pipe (outer diameter 170 mm) rolling at
a constant velocity on a horizontal plane was used to investigate
the effect on the radar output as the pipe rolled through the E-
plane and H-plane radar beams. Given the finite beamwidths (40
degrees and 80 degrees, respectively), the voltage output signal
versus time is symmetrical with respect to the Nadir in both the
approaching and receding part of the trajectory of the pipe for
uniform displacement perpendicular to the radar beam. With a
null recording immediately beneath the radar in both planes, the
velocity of the pipe is monotonically related to the time between
the two major peaks and troughs. This allows the velocity
determination of objects moving through the radar beam
tangentially.
                                                                       Fig. 1. Electrical connections and patch antenna array of the HB100 Doppler
   Keywords— Doppler radar, E-plane, H-plane, nadir detection,         radar module showing the E and H planes of linear polarisation. The circuit
low cost, low power, movement velocity                                 board is 45 × 36 mm2 on FR4.


                       I. INTRODUCTION                                                      III. METHODS AND RESULTS
    There are many applications important for the detection of             A round, steel pipe (outer diameter 170 mm) was released
movement through a radar beam. Such applications include               from a stationary position at the end of a rigid inclined ramp onto
motor vehicles, light switching, and water flow. The basic theory      a flat rigid surface at various elevation heights (see Fig 2).
relating to Doppler radar is the detection of radial velocity which
imparts a positive or negative frequency shift on the received
signal. Commonly small, unobtrusive radars would be placed
conformally with a mounting structure. As the radar has a finite
beamwidth, a single moving scatterer should create a Doppler
shift before and after the main beam direction. To resolve this
ambiguity, most Doppler radars are oriented at an acute angle to
the expected incoming direction of the target [1-4]. This paper
reports the incoming and outgoing movement of a rolling steel
pipe through both planes of the bistatic antenna array of an
HB100 commercial Doppler radar at 10.525 GHz.
                                                                       Fig. 2. Schematic diagram showing the initial and final positions of the
                                                                       circular pipe as it rolls through the radar beam. The radar was positioned at the
          II. THE HB100 DOPPLER RADAR MODULE                           centre of the horizontal plane at z = 0 m and z = -1.05 m from the initial position.
    The earliest published record describing the HB100 radar
sensor was published in 2014 [5], with the description as a               The velocity of the pipe v was calculated from the potential
“miniature microwave sensor X-band bi-static Doppler                   energy at the initial height h, converted to the velocity of the
transceiver module” with a range of 20 m with half-power beam          equated kinetic energy (both linear and angular):
widths of 80 degrees in azimuth (H-plane) and 40 degrees in
6th Australian Microwave Symposium, Gold Coast, Australia, 10 – 11 February 2025

                                                ≅                     ℎ         (1)   both cases there is an apparent symmetry about the central
                                                                                      minimum position when the pipe is directly beneath the radar
where g is the gravitational acceleration. Note that the velocity                     nadir.
is independent of the mass, diameter, and path length. This
relationship is shown in Fig. 3. The initial heights ranged from
0 (no movement) to 300 mm with a velocity of up to 2.0 m/s. It
is assumed that the rolling friction is minimal so that the velocity

                                                                                      time difference (s)                                       time difference (s)
through the main beam is relatively constant for each starting
height. For this reason, one can expect that the Doppler profiles
will be symmetrical if the radiation pattern of the radar is
symmetrical.


                                                                                                                           (a)                                        (b)




                  Linear Velocity (m/s)
                                                                                      Fig. 5. Time differences around the central minimum for the adjacent
                                                                                      maximum and minimum values, respectively. (a) H-plane. (b) E-plane.


                                                                                                                                  IV. CONCLUSIONS
                                                                                          The velocity of this large object can be determined providing
                                                                                      the radar height above the plane remains constant. For this
                                                                                      reason, velocity measurements using the HB100 radar can be
                                                                                      accurately achieved for very low cost, very small infrastructure
Fig. 3. The relationship between the linear velocity and drop height.                 and low power. For example, the recording of ripple velocity
                                                                                      (much smaller scatterers) in semi-filled, storm water pipes from
    Figs. 4a and 4b show the radar voltage output as a function                       this radar positioned at the highest point inside a pipe can
of time for the H-plane and the E-plane transits for an                               provide water surface velocity measurements. This is the
approximate pipe horizontal velocity of 1.6 m/s and 1.7 m/s                           ultimate goal of this preliminary experiment.
respectively. Both H- and E-plane plots are approximately
symmetrical on either side of the central minimum value.                                                                          ACKNOWLEDGMENT
                                                                                      The authors thank Noah Becker for the design and fabrication of
                                                                                      interface electronics.


Doppler voltage                                     Doppler voltage
## REFERENCES
                                                                                      [1]                   N.S. A. Bringer, C-A. Guerin, B. Chapron, A.A. Mouche, “Peakedness
                                                                                                            effects in near-nadir radar observations of the sea surface”, IEEE Trans.
                                                                                                            Geosci. & Remote Sensing, vol 50 (9), pp. 3293-3301, 2012.
                                                                                      [2]                   S. C. Fatras et al., "Radar backscattering coefficient over bare soils at Ka-
                                                                                                            band close to nadir angle," IEEE Geoscience and Remote Sensing Letters,
                                                                                                            vol. 13, no. 9, pp. 1290-1294, Sept. 2016.
                                          (a)                             (b)         [3]                   C. Decourt, R. VanRullen, D. Salle and T. Oberlin, "DAROD: A deep
                                                                                                            automotive radar object detector on range-Doppler maps," 2022 IEEE
Fig. 4. (a) H-plane Doppler voltage as a function of time (v = 1.6 m/s). (b) E-                             Intelligent Vehicles Symposium (IV), Aachen, Germany, 2022, pp. 112-
plane Doppler voltage as a function of time (v = 1.7 m/s).                                                  118, 2022.
                                                                                      [4]                   A.A. Pramudita, Lukas & Edwar, “Time and frequency domain feature
    The time between the two maximum features symmetrically                                                 extraction method of Doppler radial for hand gesture based human to
placed around the central minimum (H-plane) were measured as                                                machine interface”, PIER C, vol 98. pp 83-96, 2020.
a function of the velocity v. Fig.5a shows the result in addition                     [5]                   T. Tauqeer & M. Islam, and A.K. Aziz., “Short range continuous wave
to the time between the first two minimum values adjacent to the                                            radar for target detection in various mediums”, Microwave & Optical
                                                                                                            Tech. Lett., vol. 56 (11), pp. 2484-2489, 2014.
central minimum. A similar relationship is evident for the E-
plane case (Fig. 5b), however, the linearity is less evident. In

