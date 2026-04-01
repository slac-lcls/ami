# AMI Node Types Reference

**Generated:** 2026-04-01 13:00:31

**Organization:** By functional category (optimized for AI agent semantic search)

---

## Table of Contents

- [Display & Visualization](#display--visualization)
- [Data Processing](#data-processing)
- [ROI (Region Selection)](#roi-region-selection)
- [Statistics & Analysis](#statistics--analysis)
- [Filtering & Logic](#filtering--logic)
- [Accumulators & Buffers](#accumulators--buffers)
- [Export](#export)
- [Advanced Processing](#advanced-processing)

---

## Display & Visualization

**Description:** Nodes that visualize and display data (all self-displaying)

### Binning

**Module:** Numpy

**Description:**

Binning creates a histogram with a fixed number of bins using numpy.histogram.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Bins`
- `Counts`

**Parameters:**

- `bins` (intSpin)
- `auto range` (check)
- `range min` (doubleSpin)
- `range max` (doubleSpin)
- `weighted` (check)
- `density` (check)

---

### Binning2D

**Module:** Numpy

**Description:**

Binning2D creates a 2d histogram with a fixed number of bins using numpy.histogram2d.

**Terminals:**

*Inputs:*
- `X`
- `Y`

*Outputs:*
- `Counts`
- `XBins`
- `YBins`

**Parameters:**

- `x bins` (intSpin)
- `y bins` (intSpin)
- `range x min` (doubleSpin)
- `range x max` (doubleSpin)
- `range y min` (doubleSpin)
- `range y max` (doubleSpin)
- `density` (check)

---

### Histogram

**Module:** Display

**Description:**

Histogram plots a histogram created from Binning.

**Terminals:**

*Inputs:*
- `Bins`
- `Counts`

---

### Histogram2D

**Module:** Display

**Description:**

Histogram2D plots a 2d histogram created from Binning2D.

**Terminals:**

*Inputs:*
- `Counts`
- `XBins`
- `YBins`

---

### ImageViewer

**Module:** Display

**Description:**

ImageViewer displays 2D arrays.

**Terminals:**

*Inputs:*
- `In`

---

### LinePlot

**Module:** Display

**Description:**

Line Plot plots arrays.

**Terminals:**

*Inputs:*
- `X`
- `Y`

---

### MeanWaveformVsScan

**Module:** Operators

**Description:**

MeanWaveformVsScan creates a 2d histogram using a variable number of bins.

Returns a dict with keys Bins and values mean waveform of bins.

**Terminals:**

*Inputs:*
- `Bin`
- `Value`

*Outputs:*
- `Counts`
- `X Bins`
- `Y Bins`

**Parameters:**

- `binned` (check)
- `bins` (intSpin)
- `min` (intSpin)
- `max` (intSpin)

---

### Monitor

**Module:** Alert

**Description:**

Debug box which plots which boxes have an event in a heartbeat

**Terminals:**

*Inputs:*
- `In`

**Parameters:**

- `Num Points` (intSpin)

---

### MultiWaveformViewer

**Module:** Display

**Description:**

MultiWaveformViewer displays 2D arrays as series of 1D arrays.

**Terminals:**

*Inputs:*
- `In`

---

### ObjectViewer

**Module:** Display

**Description:**

ObjectViewer displays string representation of a python object.

**Terminals:**

*Inputs:*
- `In`

---

### ScalarPlot

**Module:** Display

**Description:**

Scalar Plot collects scalars and plots them.

**Terminals:**

*Inputs:*
- `Y`

**Parameters:**

- `Num Points` (intSpin)

---

### ScalarViewer

**Module:** Display

**Description:**

ScalarViewer displays the value of a scalar.

**Terminals:**

*Inputs:*
- `In`

---

### ScatterPlot

**Module:** Display

**Description:**

Scatter Plot collects two scalars and plots them against each other.

**Terminals:**

*Inputs:*
- `X`
- `Y`

**Parameters:**

- `Num Points` (intSpin)
- `Unique` (check)

---

### ScatterRoi

**Module:** Roi

**Description:**

Region of Interest of 1d array.

**Terminals:**

*Inputs:*
- `X`
- `Y`

*Outputs:*
- `Out.X`
- `Out.Y`

**Parameters:**

- `origin` (intSpin)
- `extent` (intSpin)
- `Num Points` (intSpin)

---

### TimePlot

**Module:** Display

**Description:**

Plot a number against time of day.

**Terminals:**

*Inputs:*
- `X`
- `Y`

**Parameters:**

- `Num Points` (intSpin)

---

### WaveformViewer

**Module:** Display

**Description:**

WaveformViewer displays 1D arrays.

**Terminals:**

*Inputs:*
- `In`

---

## Data Processing

**Description:** Transform, compute, and manipulate data

### Average

**Module:** Numpy

**Description:**

Compute average using np.average

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `axis` (intSpin)

---

### Average0D

**Module:** Numpy

**Description:**

Collect N scalars and average them.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `N` (intSpin)
- `infinite` (check)

---

### Average1D

**Module:** Numpy

**Description:**

Collect N 1d arrays and average them.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `N` (intSpin)
- `infinite` (check)

---

### Average2D

**Module:** Numpy

**Description:**

Collect N 2d arrays and average them.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `N` (intSpin)
- `infinite` (check)

---

### Calculator

**Module:** Operators

**Description:**

Calculator

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### Combinations

**Module:** Operators

**Description:**

Generate combinations using itertools.combinations.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `length` (intSpin)

---

### Constant

**Module:** Operators

**Description:**

Constant

**Terminals:**

*Outputs:*
- `Out`

---

### ExponentialMovingAverage1D

**Module:** Operators

**Description:**

Exponential Moving Average for Waveforms.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Count`
- `Out`

**Parameters:**

- `Fraction of old` (doubleSpin)

---

### ExponentialMovingAverage2D

**Module:** Operators

**Description:**

Exponential Moving Average for Images.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Count`
- `Out`

**Parameters:**

- `Fraction of old` (doubleSpin)

---

### HistMeanRMS

**Module:** Numpy

**Description:**

HistMeanRMS

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Mean`
- `Stdev`

---

### Identity

**Module:** Operators

**Description:**

Identity

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### LoadReference1D

**Module:** Numpy

**Description:**

Load 1d reference array from csv.

**Terminals:**

*Outputs:*
- `X`
- `Y`

**Parameters:**

- `path` (text)

---

### MeanVsScan

**Module:** Operators

**Description:**

MeanVsScan creates a histogram using a variable number of bins.

Returns a dict with keys Bins and values mean of bins.

**Terminals:**

*Inputs:*
- `Bin`
- `Value`

*Outputs:*
- `Bins`
- `Counts`

**Parameters:**

- `binned` (check)
- `bins` (intSpin)
- `min` (intSpin)
- `max` (intSpin)

---

### Polynomial

**Module:** Numpy

**Description:**

Evaluate a polynomial using np.polynomial.polynomial.polyval

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `c0` (doubleSpin)
- `c1` (doubleSpin)
- `c2` (doubleSpin)

---

### Projection

**Module:** Numpy

**Description:**

Projection projects a 2d array along the selected axis.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `axis` (intSpin)

---

### PythonEditor

**Module:** Operators

**Description:**

Write a python function.

---

### Split

**Module:** Numpy

**Description:**

Split a 2d array into 1d arrays using np.split.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `axis` (intSpin)

---

### Stack1d

**Module:** Numpy

**Description:**

Stacks scalars into 1d array using np.stack

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `axis` (intSpin)

---

### Stack2d

**Module:** Numpy

**Description:**

Stacks 1d arrays into 2d array using np.stack

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `axis` (intSpin)

---

### Sum

**Module:** Numpy

**Description:**

Returns the sum of an array.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### SumN

**Module:** Accumulators

**Description:**

SumN sums N of its input.

**Parameters:**

- `N` (intSpin)

---

### Take

**Module:** Numpy

**Description:**

Index into a list or array using np.take

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `axis` (intSpin)
- `index` (intSpin)
- `mode` (combo)

---

### TimeMeanRMS0D

**Module:** Numpy

**Description:**

TimeMeanRMS0D

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Mean`
- `RMS`

**Parameters:**

- `N` (intSpin)

---

### TimeMeanRMS1D

**Module:** Numpy

**Description:**

TimeMeanRMS1D

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Mean`
- `RMS`

**Parameters:**

- `N` (intSpin)

---

### TimeMeanRMS2D

**Module:** Numpy

**Description:**

TimeMeanRMS2D

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Mean`
- `RMS`

**Parameters:**

- `N` (intSpin)

---

## ROI (Region Selection)

**Description:** Extract regions of interest from data

### Roi0D

**Module:** Roi

**Description:**

Selects single pixel from image.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `x` (intSpin)
- `y` (intSpin)

---

### Roi1D

**Module:** Roi

**Description:**

Region of Interest of 1d array.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `origin` (intSpin)
- `extent` (intSpin)

---

### Roi2D

**Module:** Roi

**Description:**

Region of Interest of image.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`
- `Roi_Coordinates`

**Parameters:**

- `origin x` (intSpin)
- `origin y` (intSpin)
- `extent x` (intSpin)
- `extent y` (intSpin)

---

### RoiArch

**Module:** Roi

**Description:**

Region of Interest of image shaped as arch (a.k.a. cut-donat).

**Terminals:**

*Inputs:*
- `image`
- `mask`

*Outputs:*
- `ABinCent`
- `ABinEdges`
- `AProj`
- `BBox`
- `Mask`
- `RBinCent`
- `RBinEdges`
- `ROIPars`
- `RProj`
- `RadAngBinStatist`
- `RadAngNormIntens`

**Parameters:**

- `center x` (intSpin)
- `center y` (intSpin)
- `radius o` (intSpin)
- `radius i` (intSpin)
- `angdeg o` (intSpin)
- `angdeg i` (intSpin)
- `nbins rad` (intSpin)
- `nbins ang` (intSpin)

---

## Statistics & Analysis

**Description:** Compute statistics and analyze data

### RMS

**Module:** Numpy

**Description:**

RMS

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### StatsVsScan

**Module:** Operators

**Description:**

StatsVsScan creates a histogram using a variable number of bins.

Returns a dict with keys Bins and values mean, std, error of bins.

**Terminals:**

*Inputs:*
- `Bin`
- `Value`

*Outputs:*
- `Bins`
- `Error`
- `Mean`
- `Stdev`

**Parameters:**

- `binned` (check)
- `bins` (intSpin)
- `min` (intSpin)
- `max` (intSpin)

---

## Filtering & Logic

**Description:** Filter and gate data based on conditions

### ArrayThreshold

**Module:** Alert

**Description:**

Display an alert when the values and number of values in an array are greater than a threshold and count.

**Terminals:**

*Inputs:*
- `In`

**Parameters:**

- `Threshold` (intSpin)
- `Count` (intSpin)

---

### Filter

**Module:** Operators

**Description:**

Filter

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### GaussianFilter1D

**Module:** Scipy

**Description:**

Scipy Gaussian Filter 1D

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `sigma` (doubleSpin)
- `axis` (intSpin)
- `order` (intSpin)
- `mode` (combo)
- `cval` (doubleSpin)
- `truncate` (doubleSpin)

---

### Pick1

**Module:** Accumulators

**Description:**

Pick1 collects one of its input.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### PickN

**Module:** Accumulators

**Description:**

PickN collects N of its input.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `N` (intSpin)

---

### TestQtPickle

**Module:** Psalg

**Description:**

psana TestQtPickle - converts n-d array (n>=3) for detector data to 2-d table of segments.

**Terminals:**

*Inputs:*
- `arr3d`

*Outputs:*
- `arr2d`

**Parameters:**

- `transpose` (check)
- `rot_n90` (combo)

---

### ThresholdingHitFinder

**Module:** Psalg

**Description:**

Apply a threshold to an image and sum.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

## Accumulators & Buffers

**Description:** Accumulate or buffer data over time/events

### Accumulator

**Module:** Accumulators

**Description:**

Accumulator

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Count`
- `Sum`

---

### ReduceByKey

**Module:** Accumulators

**Description:**

ReduceByKey

**Terminals:**

*Inputs:*
- `Key`
- `Value`

*Outputs:*
- `Out`

---

### RollingBuffer

**Module:** Accumulators

**Description:**

RollingBuffer collects N of its input.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Count`
- `Out`

**Parameters:**

- `N` (intSpin)

---

## Export

**Description:** Export data to external systems (EPICS PVs, files, etc.)

### Caput

**Module:** Export

**Description:**

Send data to an existing externally hosted PV via Channel Access.

**Terminals:**

*Inputs:*
- `In`
- `eventid`

**Parameters:**

- `pvname` (text)
- `events` (intSpin)
- `wait` (check)
- `timeout` (doubleSpin)

---

### ExportToWorker

**Module:** Export

**Description:**

Send data back to worker from global collector.

**Terminals:**

*Inputs:*
- `In`
- `Timestamp`

*Outputs:*
- `Out`

**Parameters:**

- `alias` (text)

---

### PvExport

**Module:** Export

**Description:**

Export data through an AMI hosted PV using either PV access or channel access.

**Terminals:**

*Inputs:*
- `In`
- `eventid`

**Parameters:**

- `alias` (text)
- `events` (intSpin)

---

### Pvput

**Module:** Export

**Description:**

Send data to an existing externally hosted PV via PVAccess.

**Terminals:**

*Inputs:*
- `In`
- `eventid`

**Parameters:**

- `pvname` (text)
- `events` (intSpin)
- `wait` (check)
- `timeout` (doubleSpin)

---

### UDPMcast

**Module:** Export

**Description:**

UDP multicast a reduced rate of input in BLD format.

**Terminals:**

*Inputs:*
- `In`
- `eventid`

**Parameters:**

- `Multicast Group` (text)
- `Port` (text)
- `events` (intSpin)

---

### ZMQ

**Module:** Export

**Description:**

Export data over ZMQ PUB/SUB

**Terminals:**

*Inputs:*
- `In`
- `Timestamp`

---

## Advanced Processing

**Description:** Advanced signal processing and transformations

### BlobFinder1D

**Module:** Scipy

**Description:**

Find blobs in a waveform.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `NBlobs`
- `Sum`
- `X`

**Parameters:**

- `threshold` (doubleSpin)
- `min sum` (doubleSpin)

---

### BlobFinder2D

**Module:** Scipy

**Description:**

Find blobs in an image.

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `NBlobs`
- `Sum`
- `X`
- `Y`

**Parameters:**

- `threshold` (doubleSpin)
- `min sum` (doubleSpin)

---

### CFD

**Module:** Psalg

**Description:**

Constant fraction descriminator

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `Sample Interval` (doubleSpin)
- `horpos` (doubleSpin)
- `gain` (doubleSpin)
- `offset` (doubleSpin)
- `delay` (intSpin)
- `walk` (doubleSpin)
- `threshold` (doubleSpin)
- `fraction` (doubleSpin)

---

### CurveFit

**Module:** Scipy

**Description:**

Calls scipy.optimize.curve_fit to fit a function to its inputs.

**Terminals:**

*Inputs:*
- `Y`

*Outputs:*
- `fx`
- `p0`
- `pcov`

**Parameters:**

- `f` (text)
- `variables` (text)
- `p0` (text)

---

### EdgeFinder

**Module:** Psalg

**Description:**

psana edgefinder

**Terminals:**

*Inputs:*
- `Calib`
- `IIR`
- `Image`

*Outputs:*
- `amplitude`
- `amplitude_next`
- `edge`
- `fwhm`
- `ref_amplitude`

---

### FFT

**Module:** FFTW

**Description:**

pyfftw.builders.fft

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### FFT2

**Module:** FFTW

**Description:**

pyfftw.builders.fft2

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### Geometry

**Module:** Psalg

**Description:**

psana Geometry - uses geometry constants to generate arrays of pixel coordinates etc.

**Terminals:**

*Inputs:*
- `arr3d`
- `calibcons`

*Outputs:*
- `coords_xyz`
- `image`
- `inds_xy`

**Parameters:**

- `geofname` (file_in)

---

### HSDPeakTest

**Module:** Validators

**Description:**

HSDPeakTest

**Terminals:**

*Inputs:*
- `Peaks`
- `Waveform`

*Outputs:*
- `Fail`
- `Pass`

---

### Hexanode

**Module:** Psalg

**Description:**

Hexanode

**Terminals:**

*Inputs:*
- `Calib`
- `Event Number`
- `Num of Hits`
- `Peak Times`

*Outputs:*
- `R`
- `T`
- `X`
- `Y`

**Parameters:**

- `num chans` (combo)
- `num hits` (intSpin)
- `verbose` (check)

---

### HitFinder

**Module:** Psalg

**Description:**

HitFinder

**Terminals:**

*Inputs:*
- `Num of Hits`
- `Peak Times`

*Outputs:*
- `T`
- `X`
- `Y`

**Parameters:**

- `runtime_u` (doubleSpin)
- `runtime_v` (doubleSpin)
- `tsum_avg_u` (doubleSpin)
- `tsum_hw_u` (doubleSpin)
- `tsum_avg_v` (doubleSpin)
- `tsum_hw_v` (doubleSpin)
- `f_u` (doubleSpin)
- `f_v` (doubleSpin)
- `Rmax` (doubleSpin)

---

### IFFT

**Module:** FFTW

**Description:**

pyfftw.builders.ifft

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### IFFT2

**Module:** FFTW

**Description:**

pyfftw.builders.ifft2

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### IRFFT

**Module:** FFTW

**Description:**

pyfftw.builders.irfft

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### IRFFT2

**Module:** FFTW

**Description:**

pyfftw.builders.irfft2

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### Linregress0D

**Module:** Scipy

**Description:**

Collect N scalars and apply Scipy.stats.linregress

**Terminals:**

*Inputs:*
- `X.In`
- `Y.In`

*Outputs:*
- `Fit`
- `X`
- `Y`
- `rvalue`

**Parameters:**

- `N` (intSpin)

---

### Linregress1D

**Module:** Scipy

**Description:**

Scipy.stats.linregress

**Terminals:**

*Inputs:*
- `X`
- `Y`

*Outputs:*
- `fit`
- `intercept`
- `pvalue`
- `rvalue`
- `slope`
- `stderr`

---

### Mask

**Module:** Psalg

**Description:**

psana Mask 

**Terminals:**

*Inputs:*
- `calibconst`

*Outputs:*
- `Mask`
- `Mask3D`

**Parameters:**

- `status` (check)
- `status_bits` (intSpin)
- `gain_range_inds` (text)
- `neighbors` (check)
- `rad` (intSpin)
- `ptrn` (combo)
- `edges` (check)
- `width` (intSpin)
- `edge_rows` (intSpin)
- `edge_cols` (intSpin)
- `center` (check)
- `wcenter` (intSpin)
- `center_rows` (intSpin)
- `center_cols` (intSpin)
- `calib` (check)
- `umask` (file_in)

---

### Mask3dFrom2d

**Module:** Psalg

**Description:**

psana Mask3dFrom2d - converts mask2d (as image) to mask3d array shaped as data

**Terminals:**

*Inputs:*
- `inds_xy`
- `mask2d`

*Outputs:*
- `mask3d`

---

### PeakFinder1D

**Module:** Psalg

**Description:**

1D Peakfinder

**Terminals:**

*Inputs:*
- `Waveform`

*Outputs:*
- `Centroid`
- `Width`

**Parameters:**

- `threshold lo` (doubleSpin)
- `threshold hi` (doubleSpin)

---

### PeakFinderV4R3

**Module:** Psalg

**Description:**

psana peakfinder v4r3d2

**Terminals:**

*Inputs:*
- `Image`

*Outputs:*
- `amp_tot`
- `col_cgrav`
- `npix`
- `row_cgrav`
- `son`

**Parameters:**

- `npix min` (doubleSpin)
- `npix max` (doubleSpin)
- `amax thr` (doubleSpin)
- `atot thr` (doubleSpin)
- `son min` (doubleSpin)
- `thr low` (doubleSpin)
- `thr high` (doubleSpin)
- `rank` (doubleSpin)
- `r0` (doubleSpin)
- `dr` (doubleSpin)

---

### PeakFit

**Module:** Scipy

**Description:**

Fit a peak to 1d data
Models:
    Gaussian
    Lorentzian

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `ampl`
- `center`
- `fit`
- `fwhm`
- `offset`
- `width`

**Parameters:**

- `Model` (combo)
- `Use offset` (check)
- `Initial amplitude` (doubleSpin)
- `Initial x0` (doubleSpin)
- `Initial FWHM` (doubleSpin)
- `Initial offset` (doubleSpin)

---

### RFFT

**Module:** FFTW

**Description:**

pyfftw.builders.rfft

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### RFFT2

**Module:** FFTW

**Description:**

pyfftw.builders.rfft2

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

---

### Rotate

**Module:** Scipy

**Description:**

Scipy.ndimage.rotate

**Terminals:**

*Inputs:*
- `In`

*Outputs:*
- `Out`

**Parameters:**

- `angle` (doubleSpin)

---

### TableFromArr3d

**Module:** Psalg

**Description:**

psana TableFromArr3d - converts n-d array (n>=3) for detector data to 2-d table of segments.

**Terminals:**

*Inputs:*
- `arr3d`

*Outputs:*
- `arr2d`

**Parameters:**

- `transpose` (check)
- `rot_n90` (combo)

---

### WFPeaks

**Module:** Psalg

**Description:**

WFPeaks

**Terminals:**

*Inputs:*
- `Times`
- `Waveform`

*Outputs:*
- `Index`
- `Num of Hits`
- `Peak Times`
- `Values`

---

### XTCAVLasingOn

**Module:** Psalg

**Description:**

XTCAVLasingOn

**Terminals:**

*Inputs:*
- `cam`
- `pars`
- `src`

*Outputs:*
- `agreement`
- `power`
- `pulse`
- `time`

**Parameters:**

- `num bunches` (intSpin)
- `snr filter` (doubleSpin)
- `roi expand` (doubleSpin)
- `roi fraction` (doubleSpin)
- `island split method` (combo)
- `island split par1` (doubleSpin)
- `island split par2` (doubleSpin)

---
