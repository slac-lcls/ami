
# First Milestone

The first milestone is to be able to do a real-time "t0" measurement
for a spectroscopy experiment in XPP, the hutch which uses AMI in the
most complex ways, typically.  "t0" is the time-difference between a
pump-laser and the LCLS-xray-laser where the system being studied
begins to show an effect of being "pumped".  This real-time analysis
is not possible with the existing LCLS-I AMI.

This requires the following steps in the analysis graph:

* get image
* calibrate
* do peak finding
* filter on laser on/off
* bin laser-on by x,y,t
* bin laser-off by x,y
* take sidebands and interpolate to subtract in signal region (both lason/off)
* project lason/off along y (now have x,t)
* subtract laser-off from laser-on cube (in each time bin)

The laser-off ("background") image is accumulated from the beginning of time.
A more complex example would have the background image be calculated over
a user-definably time window (this is done for timetool analysis in LCLS-I,
for example)
