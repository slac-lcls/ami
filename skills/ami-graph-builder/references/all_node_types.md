# AMI Node Types Reference

**Generated:** 2026-04-01 21:01:08

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
- `In` (float|Array1d|Array2d)

*Outputs:*
- `Bins` (Array1d)
- `Counts` (Array1d)

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
- `X` (float|Array1d)
- `Y` (float|Array1d)

*Outputs:*
- `Counts` (Array2d)
- `XBins` (Array1d)
- `YBins` (Array1d)

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
- `Bins` (Array1d)
- `Counts` (Array1d)

**Capabilities:**

- ✓ Can add/remove input terminals

---

### Histogram2D

**Module:** Display

**Description:**

Histogram2D plots a 2d histogram created from Binning2D.

**Terminals:**

*Inputs:*
- `Counts` (Array2d)
- `XBins` (Array1d)
- `YBins` (Array1d)

---

### ImageViewer

**Module:** Display

**Description:**

ImageViewer displays 2D arrays.

**Terminals:**

*Inputs:*
- `In` (Array2d)

---

### LinePlot

**Module:** Display

**Description:**

Line Plot plots arrays.

**Terminals:**

*Inputs:*
- `X` (Array1d)
- `Y` (Array1d)

**Capabilities:**

- ✓ Can add/remove input terminals

---

### MeanWaveformVsScan

**Module:** Operators

**Description:**

MeanWaveformVsScan creates a 2d histogram using a variable number of bins.

Returns a dict with keys Bins and values mean waveform of bins.

**Terminals:**

*Inputs:*
- `Bin` (float)
- `Value` (Array1d)

*Outputs:*
- `Counts` (Array2d)
- `X Bins` (Array1d)
- `Y Bins` (Array1d)

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
- `In` (Any)

**Capabilities:**

- ✓ Can add/remove input terminals

**Parameters:**

- `Num Points` (intSpin)

---

### MultiWaveformViewer

**Module:** Display

**Description:**

MultiWaveformViewer displays 2D arrays as series of 1D arrays.

**Terminals:**

*Inputs:*
- `In` (MultiChannelWaveform)

---

### ObjectViewer

**Module:** Display

**Description:**

ObjectViewer displays string representation of a python object.

**Terminals:**

*Inputs:*
- `In` (Any)

---

### ScalarPlot

**Module:** Display

**Description:**

Scalar Plot collects scalars and plots them.

**Terminals:**

*Inputs:*
- `Y` (float)

**Capabilities:**

- ✓ Can add/remove input terminals

**Parameters:**

- `Num Points` (intSpin)

---

### ScalarViewer

**Module:** Display

**Description:**

ScalarViewer displays the value of a scalar.

**Terminals:**

*Inputs:*
- `In` (float)

---

### ScatterPlot

**Module:** Display

**Description:**

Scatter Plot collects two scalars and plots them against each other.

**Terminals:**

*Inputs:*
- `X` (float)
- `Y` (float)

**Capabilities:**

- ✓ Can add/remove input terminals

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
- `X` (float)
- `Y` (float)

*Outputs:*
- `Out.X` (Array1d)
- `Out.Y` (Array1d)

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
- `X` (float)
- `Y` (float)

**Capabilities:**

- ✓ Can add/remove input terminals

**Parameters:**

- `Num Points` (intSpin)

---

### WaveformViewer

**Module:** Display

**Description:**

WaveformViewer displays 1D arrays.

**Terminals:**

*Inputs:*
- `In` (Array1d)

**Capabilities:**

- ✓ Can add/remove input terminals

---

## Data Processing

**Description:** Transform, compute, and manipulate data

### Average

**Module:** Numpy

**Description:**

Compute average using np.average

**Terminals:**

*Inputs:*
- `In` (Array1d|Array2d)

*Outputs:*
- `Out` (float)

**Capabilities:**

- ✓ Can add/remove input terminals

**Parameters:**

- `axis` (intSpin)

---

### Average0D

**Module:** Numpy

**Description:**

Collect N scalars and average them.

**Terminals:**

*Inputs:*
- `In` (float)

*Outputs:*
- `Out` (float)

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
- `In` (Array1d)

*Outputs:*
- `Out` (Array1d)

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
- `In` (Array2d)

*Outputs:*
- `Out` (Array2d)

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
- `In` (float|Array1d|Array2d|Array3d)

*Outputs:*
- `Out` (Any)

**Capabilities:**

- ✓ Can add/remove input terminals

---

### Combinations

**Module:** Operators

**Description:**

Generate combinations using itertools.combinations.

**Terminals:**

*Inputs:*
- `In` (Array1d)

*Outputs:*
- `Out` (Array1d)

**Parameters:**

- `length` (intSpin)

---

### Constant

**Module:** Operators

**Description:**

Constant

**Terminals:**

*Outputs:*
- `Out` (Any)

---

### ExponentialMovingAverage1D

**Module:** Operators

**Description:**

Exponential Moving Average for Waveforms.

**Terminals:**

*Inputs:*
- `In` (Array1d)

*Outputs:*
- `Count` (int)
- `Out` (Array1d)

**Parameters:**

- `Fraction of old` (doubleSpin)

---

### ExponentialMovingAverage2D

**Module:** Operators

**Description:**

Exponential Moving Average for Images.

**Terminals:**

*Inputs:*
- `In` (Array2d)

*Outputs:*
- `Count` (int)
- `Out` (Array2d)

**Parameters:**

- `Fraction of old` (doubleSpin)

---

### HistMeanRMS

**Module:** Numpy

**Description:**

HistMeanRMS

**Terminals:**

*Inputs:*
- `In` (Array1d)

*Outputs:*
- `Mean` (float)
- `Stdev` (float)

---

### Identity

**Module:** Operators

**Description:**

Identity

**Terminals:**

*Inputs:*
- `In` (Any)

*Outputs:*
- `Out` (Any)

**Capabilities:**

- ✓ Can add/remove input terminals

---

### LoadReference1D

**Module:** Numpy

**Description:**

Load 1d reference array from csv.

**Terminals:**

*Outputs:*
- `X` (Array1d)
- `Y` (Array1d)

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
- `Bin` (float)
- `Value` (float)

*Outputs:*
- `Bins` (Array1d)
- `Counts` (Array1d)

**Capabilities:**

- ✓ Can add/remove input terminals

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
- `In` (Array1d)

*Outputs:*
- `Out` (Array1d)

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
- `In` (Array2d)

*Outputs:*
- `Out` (Array1d)

**Capabilities:**

- ✓ Can add/remove input terminals

**Parameters:**

- `axis` (intSpin)

---

### PythonEditor

**Module:** Operators

**Description:**

Write a python function.

**Capabilities:**

- ✓ Can add/remove input terminals
- ✓ Can add/remove output terminals

---

### Split

**Module:** Numpy

**Description:**

Split a 2d array into 1d arrays using np.split.

**Terminals:**

*Inputs:*
- `In` (Array2d)

*Outputs:*
- `Out` (Array1d)

**Capabilities:**

- ✓ Can add/remove output terminals

**Parameters:**

- `axis` (intSpin)

---

### Stack1d

**Module:** Numpy

**Description:**

Stacks scalars into 1d array using np.stack

**Terminals:**

*Inputs:*
- `In` (float|list[float])

*Outputs:*
- `Out` (Array1d)

**Capabilities:**

- ✓ Can add/remove input terminals

**Parameters:**

- `axis` (intSpin)

---

### Stack2d

**Module:** Numpy

**Description:**

Stacks 1d arrays into 2d array using np.stack

**Terminals:**

*Inputs:*
- `In` (Array1d|list[Array1d])

*Outputs:*
- `Out` (Array2d)

**Capabilities:**

- ✓ Can add/remove input terminals

**Parameters:**

- `axis` (intSpin)

---

### Sum

**Module:** Numpy

**Description:**

Returns the sum of an array.

**Terminals:**

*Inputs:*
- `In` (Array)

*Outputs:*
- `Out` (float)

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
- `In` (Array)

*Outputs:*
- `Out` (float|Array1d|Array2d)

**Capabilities:**

- ✓ Can add/remove input terminals

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
- `In` (float)

*Outputs:*
- `Mean` (float)
- `RMS` (float)

**Parameters:**

- `N` (intSpin)

---

### TimeMeanRMS1D

**Module:** Numpy

**Description:**

TimeMeanRMS1D

**Terminals:**

*Inputs:*
- `In` (Array1d)

*Outputs:*
- `Mean` (Array1d)
- `RMS` (Array1d)

**Parameters:**

- `N` (intSpin)

---

### TimeMeanRMS2D

**Module:** Numpy

**Description:**

TimeMeanRMS2D

**Terminals:**

*Inputs:*
- `In` (Array2d)

*Outputs:*
- `Mean` (Array2d)
- `RMS` (Array2d)

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
- `In` (Array2d)

*Outputs:*
- `Out` (float)

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
- `In` (Array1d)

*Outputs:*
- `Out` (Array1d)

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
- `In` (Array2d)

*Outputs:*
- `Out` (Array2d)
- `Roi_Coordinates` (Array1d)

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
- `image` (Array2d)
- `mask` (Array2d) *[optional, can remove]*

*Outputs:*
- `ABinCent` (Array1d)
- `ABinEdges` (Array1d)
- `AProj` (Array1d)
- `BBox` (Array1d)
- `Mask` (Array2d)
- `RBinCent` (Array1d)
- `RBinEdges` (Array1d)
- `ROIPars` (Array1d)
- `RProj` (Array1d)
- `RadAngBinStatist` (Array2d)
- `RadAngNormIntens` (Array2d)

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
- `In` (Array1d|Array2d)

*Outputs:*
- `Out` (float)

**Capabilities:**

- ✓ Can add/remove input terminals

---

### StatsVsScan

**Module:** Operators

**Description:**

StatsVsScan creates a histogram using a variable number of bins.

Returns a dict with keys Bins and values mean, std, error of bins.

**Terminals:**

*Inputs:*
- `Bin` (float)
- `Value` (float)

*Outputs:*
- `Bins` (Array1d)
- `Error` (Array1d)
- `Mean` (Array1d)
- `Stdev` (Array1d)

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
- `In` (Array1d)

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
- `In` (Any)

*Outputs:*
- `Out` (Any)

**Capabilities:**

- ✓ Can add/remove input terminals
- ✓ Can add/remove output terminals

---

### GaussianFilter1D

**Module:** Scipy

**Description:**

Scipy Gaussian Filter 1D

**Terminals:**

*Inputs:*
- `In` (Array1d)

*Outputs:*
- `Out` (Array1d)

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
- `In` (T)

*Outputs:*
- `Out` (T)

---

### PickN

**Module:** Accumulators

**Description:**

PickN collects N of its input.

**Terminals:**

*Inputs:*
- `In` (T)

*Outputs:*
- `Out` (Array1d)

**Capabilities:**

- ✓ Can add/remove input terminals

**Parameters:**

- `N` (intSpin)

---

### TestQtPickle

**Module:** Psalg

**Description:**

psana TestQtPickle - converts n-d array (n>=3) for detector data to 2-d table of segments.

**Terminals:**

*Inputs:*
- `arr3d` (Array3d)

*Outputs:*
- `arr2d` (Array2d)

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
- `In` (Array2d)

*Outputs:*
- `Out` (Array2d)

---

## Accumulators & Buffers

**Description:** Accumulate or buffer data over time/events

### Accumulator

**Module:** Accumulators

**Description:**

Accumulator

**Terminals:**

*Inputs:*
- `In` (Any)

*Outputs:*
- `Count` (int)
- `Sum` (Any)

**Capabilities:**

- ✓ Can add/remove input terminals

---

### ReduceByKey

**Module:** Accumulators

**Description:**

ReduceByKey

**Terminals:**

*Inputs:*
- `Key` (Any)
- `Value` (Any)

*Outputs:*
- `Out` (dict)

---

### RollingBuffer

**Module:** Accumulators

**Description:**

RollingBuffer collects N of its input.

**Terminals:**

*Inputs:*
- `In` (T)

*Outputs:*
- `Count` (int)
- `Out` (Array1d)

**Capabilities:**

- ✓ Can add/remove input terminals

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
- `In` (str|int|float|Array1d)
- `eventid` (int)

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
- `In` (Any)
- `Timestamp` (float)

*Outputs:*
- `Out` (Any)

**Parameters:**

- `alias` (text)

---

### PvExport

**Module:** Export

**Description:**

Export data through an AMI hosted PV using either PV access or channel access.

**Terminals:**

*Inputs:*
- `In` (Any)
- `eventid` (int)

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
- `In` (str|int|float|Array1d|Array2d)
- `eventid` (int)

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
- `In` (Any)
- `eventid` (int)

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
- `In` (Any)
- `Timestamp` (float)

**Capabilities:**

- ✓ Can add/remove input terminals

---

## Advanced Processing

**Description:** Advanced signal processing and transformations

### BlobFinder1D

**Module:** Scipy

**Description:**

Find blobs in a waveform.

**Terminals:**

*Inputs:*
- `In` (Array1d)

*Outputs:*
- `NBlobs` (int)
- `Sum` (Array1d)
- `X` (Array1d)

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
- `In` (Array2d)

*Outputs:*
- `NBlobs` (int)
- `Sum` (Array1d)
- `X` (Array1d)
- `Y` (Array1d)

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
- `In` (Array1d)

*Outputs:*
- `Out` (float)

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
- `Y` (Array1d)

*Outputs:*
- `fx` (Array1d)
- `p0` (Array1d)
- `pcov` (Array2d)

**Capabilities:**

- ✓ Can add/remove input terminals

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
- `Calib` (dict)
- `IIR` (Array1d)
- `Image` (Array1d)

*Outputs:*
- `amplitude` (float)
- `amplitude_next` (float)
- `edge` (float)
- `fwhm` (float)
- `ref_amplitude` (float)

---

### FFT

**Module:** FFTW

**Description:**

pyfftw.builders.fft

**Terminals:**

*Inputs:*
- `In` (Array1d)

*Outputs:*
- `Out` (Array1d)

---

### FFT2

**Module:** FFTW

**Description:**

pyfftw.builders.fft2

**Terminals:**

*Inputs:*
- `In` (Array2d)

*Outputs:*
- `Out` (Array2d)

---

### Geometry

**Module:** Psalg

**Description:**

psana Geometry - uses geometry constants to generate arrays of pixel coordinates etc.

**Terminals:**

*Inputs:*
- `arr3d` (Array3d) *[optional, can remove]*
- `calibcons` (dict)

*Outputs:*
- `coords_xyz` (list)
- `image` (Array2d)
- `inds_xy` (list)

**Parameters:**

- `geofname` (file_in)

---

### HSDPeakTest

**Module:** Validators

**Description:**

HSDPeakTest

**Terminals:**

*Inputs:*
- `Peaks` (Peaks)
- `Waveform` (Array1d)

*Outputs:*
- `Fail` (int)
- `Pass` (int)

---

### Hexanode

**Module:** Psalg

**Description:**

Hexanode

**Terminals:**

*Inputs:*
- `Calib` (dict)
- `Event Number` (float)
- `Num of Hits` (Array1d)
- `Peak Times` (Array2d)

*Outputs:*
- `R` (Array1d)
- `T` (Array1d)
- `X` (Array1d)
- `Y` (Array1d)

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
- `Num of Hits` (Array1d)
- `Peak Times` (Array2d)

*Outputs:*
- `T` (Array1d)
- `X` (Array1d)
- `Y` (Array1d)

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
- `In` (Array1d)

*Outputs:*
- `Out` (Array1d)

---

### IFFT2

**Module:** FFTW

**Description:**

pyfftw.builders.ifft2

**Terminals:**

*Inputs:*
- `In` (Array2d)

*Outputs:*
- `Out` (Array2d)

---

### IRFFT

**Module:** FFTW

**Description:**

pyfftw.builders.irfft

**Terminals:**

*Inputs:*
- `In` (Array1d)

*Outputs:*
- `Out` (Array1d)

---

### IRFFT2

**Module:** FFTW

**Description:**

pyfftw.builders.irfft2

**Terminals:**

*Inputs:*
- `In` (Array2d)

*Outputs:*
- `Out` (Array2d)

---

### Linregress0D

**Module:** Scipy

**Description:**

Collect N scalars and apply Scipy.stats.linregress

**Terminals:**

*Inputs:*
- `X.In` (float)
- `Y.In` (float)

*Outputs:*
- `Fit` (Array1d)
- `X` (Array1d)
- `Y` (Array1d)
- `rvalue` (float)

**Parameters:**

- `N` (intSpin)

---

### Linregress1D

**Module:** Scipy

**Description:**

Scipy.stats.linregress

**Terminals:**

*Inputs:*
- `X` (Array1d)
- `Y` (Array1d)

*Outputs:*
- `fit` (Array1d)
- `intercept` (float)
- `pvalue` (float)
- `rvalue` (float)
- `slope` (float)
- `stderr` (float)

---

### Mask

**Module:** Psalg

**Description:**

psana Mask 

**Terminals:**

*Inputs:*
- `calibconst` (dict)

*Outputs:*
- `Mask` (Array2d)
- `Mask3D` (Array3d)

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
- `inds_xy` (list)
- `mask2d` (Array2d)

*Outputs:*
- `mask3d` (Array3d)

---

### PeakFinder1D

**Module:** Psalg

**Description:**

1D Peakfinder

**Terminals:**

*Inputs:*
- `Waveform` (Array1d)

*Outputs:*
- `Centroid` (Array1d)
- `Width` (Array1d)

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
- `Image` (Array2d)

*Outputs:*
- `amp_tot` (Array1d) *[optional, can remove]*
- `col_cgrav` (Array1d) *[optional, can remove]*
- `npix` (Array1d) *[optional, can remove]*
- `row_cgrav` (Array1d) *[optional, can remove]*
- `son` (Array1d) *[optional, can remove]*

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
- `In` (Array1d)

*Outputs:*
- `ampl` (float)
- `center` (float)
- `fit` (Array1d)
- `fwhm` (float)
- `offset` (float)
- `width` (float)

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
- `In` (Array1d)

*Outputs:*
- `Out` (Array1d)

---

### RFFT2

**Module:** FFTW

**Description:**

pyfftw.builders.rfft2

**Terminals:**

*Inputs:*
- `In` (Array2d)

*Outputs:*
- `Out` (Array2d)

---

### Rotate

**Module:** Scipy

**Description:**

Scipy.ndimage.rotate

**Terminals:**

*Inputs:*
- `In` (Array2d)

*Outputs:*
- `Out` (Array2d)

**Parameters:**

- `angle` (doubleSpin)

---

### TableFromArr3d

**Module:** Psalg

**Description:**

psana TableFromArr3d - converts n-d array (n>=3) for detector data to 2-d table of segments.

**Terminals:**

*Inputs:*
- `arr3d` (Array3d)

*Outputs:*
- `arr2d` (Array2d)

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
- `Times` (Array2d)
- `Waveform` (Array2d)

*Outputs:*
- `Index` (Array2d)
- `Num of Hits` (Array1d)
- `Peak Times` (Array2d)
- `Values` (Array2d)

---

### XTCAVLasingOn

**Module:** Psalg

**Description:**

XTCAVLasingOn

**Terminals:**

*Inputs:*
- `cam` (Detector)
- `pars` (Detector)
- `src` (DataSource)

*Outputs:*
- `agreement` (float)
- `power` (Array2d)
- `pulse` (Array1d)
- `time` (Array2d)

**Parameters:**

- `num bunches` (intSpin)
- `snr filter` (doubleSpin)
- `roi expand` (doubleSpin)
- `roi fraction` (doubleSpin)
- `island split method` (combo)
- `island split par1` (doubleSpin)
- `island split par2` (doubleSpin)

---
