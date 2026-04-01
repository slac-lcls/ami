# Complete AMI Node Type Reference

**CRITICAL**: Only use node types from this list. Never invent node names that aren't listed here.

This is the **exhaustive** list of all valid AMI node types. If a node type isn't on this list, it doesn't exist.

**⚠️ TERMINAL NAMES MATTER!** Different nodes use different terminal names:
- **ScatterPlot, LinePlot, TimePlot**: Use `X` and `Y` terminals
- **ScalarPlot**: Uses `Y` terminal only (time is implicit)
- **Histogram**: Uses `Bins` and `Counts` terminals
- **Histogram2D**: Uses `XBins`, `YBins`, `Counts` terminals
- **Most processing nodes** (Sum, Average, Filter, Calculator, etc.): Use `In` and `Out` terminals
- Always check the terminal names for each node type below!

---

## Quick Reference by Use Case

### Want to View Data?

**Raw source data:**
- ✅ Click SourceNode (built-in viewer) - **NO CODE NEEDED**

**Scalar values:**
- **ScalarViewer** - Display single scalar value
- **ScalarPlot** - Time series of scalar (collects history)

**1D data (waveforms, arrays):**
- **WaveformViewer** - Display waveform
- **LinePlot** - Plot 1D array (X vs Y)

**2D data (images, detectors):**
- **ImageViewer** - Display 2D array as image

**Correlations:**
- **ScatterPlot** - X vs Y correlation (self-displaying)

**Distributions:**
- **Histogram** - Display histogram from Binning node
- **Histogram2D** - Display 2D histogram from Binning2D node

**Time series:**
- **TimePlot** - Plot values vs time of day

**Multi-channel:**
- **MultiWaveformViewer** - Display 2D array as series of waveforms

**Generic:**
- **ObjectViewer** - String representation of any object

---

### Want to Process Data?

**Array operations:**
- **Sum** - Sum all elements in array
- **Average**, **Average0D**, **Average1D**, **Average2D** - Compute averages
- **RMS** - Root mean square
- **Projection** - Project 2D → 1D along axis
- **Split** - Split 2D array into 1D arrays
- **Stack1d** - Stack scalars into 1D array
- **Stack2d** - Stack 1D arrays into 2D array
- **Take** - Index into array

**Math operations:**
- **Calculator** - Math expressions (e.g., `In * 2 + 5`)
- **Polynomial** - Evaluate polynomial
- **Identity** - Pass-through (no change)
- **Constant** - Generate constant values

**Region extraction:**
- **Roi0D** - Single pixel from image
- **Roi1D** - Region from 1D array
- **Roi2D** - Rectangular region from image
- **RoiArch** - Arch/donut region from image
- **ScatterRoi** - Region from scatter plot

**Filtering & selection:**
- **Filter** - Boolean event filtering (e.g., `In > 100`)
- **PythonEditor** - Custom Python code

**Binning & histograms:**
- **Binning** - 1D histogram with fixed bins
- **Binning2D** - 2D histogram with fixed bins

**Combinations:**
- **Combinations** - Generate combinations using itertools

---

### Want to Analyze Scans?

- **MeanVsScan** - Mean vs scan variable (most common)
- **MeanWaveformVsScan** - Mean waveforms vs scan
- **StatsVsScan** - Mean, stdev, error vs scan

---

### Want Statistics & Fitting?

**Statistics:**
- **TimeMeanRMS0D**, **TimeMeanRMS1D**, **TimeMeanRMS2D** - Mean & RMS over time
- **HistMeanRMS** - Mean & stdev from histogram

**Fitting (requires scipy/sympy):**
- **Linregress0D**, **Linregress1D** - Linear regression
- **CurveFit** - Fit custom function
- **PeakFit** - Fit Gaussian/Lorentzian peaks

---

### Want Signal Processing?

**Filtering:**
- **GaussianFilter1D** - Gaussian smoothing (requires scipy)

**FFT (requires pyfftw):**
- **FFT**, **IFFT** - 1D forward/inverse FFT
- **FFT2**, **IFFT2** - 2D forward/inverse FFT
- **RFFT**, **IRFFT** - 1D real FFT
- **RFFT2**, **IRFFT2** - 2D real FFT

**Averaging:**
- **ExponentialMovingAverage1D** - EMA for waveforms
- **ExponentialMovingAverage2D** - EMA for images

**Image processing:**
- **Rotate** - Rotate 2D arrays (requires scipy)

---

### Want Peak/Blob Finding?

**Peak finding:**
- **PeakFinder1D** - 1D peak finder (requires numba)
- **PeakFinderV4R3** - Psana peakfinder v4r3 (requires psalg_ext)
- **WFPeaks** - Waveform peak finding (requires psana.hexanode)

**Blob finding:**
- **BlobFinder1D** - Find blobs in waveforms (requires psana.peakFinder)
- **BlobFinder2D** - Find blobs in images (requires psana.peakFinder)

**Hit finding:**
- **HitFinder** - Hit finder for hexanode (requires psana.hexanode)
- **ThresholdingHitFinder** - Threshold-based hit finding

**Edge detection:**
- **EdgeFinder** - Find edges (requires psana.pyalgos)

---

### Want Specialized LCLS Detectors?

**Hexanode:**
- **Hexanode** - Process hexanode detector (requires psana.hexanode)
- **HitFinder** - Hit finding for hexanode

**XTCAV:**
- **XTCAVLasingOn** - XTCAV lasing characterization (requires psana.xtcav)

**Calibration:**
- **Mask**, **Mask3dFrom2d** - Generate detector masks
- **Geometry** - Generate pixel coordinates from geometry

**Table conversion:**
- **TableFromArr3d** - Convert 3D detector data to 2D table

---

### Want Waveform Analysis?

**Discriminators:**
- **CFD** - Constant fraction discriminator (requires constFracDiscrim)

**Statistics:**
- **Average1D** - Average N waveforms

**References:**
- **LoadReference1D** - Load 1D reference from CSV

---

### Want Accumulators?

- **Pick1** - Collect one input
- **PickN** - Collect N inputs
- **SumN** - Sum N inputs
- **RollingBuffer** - Rolling buffer of N inputs
- **Accumulator** - Custom accumulator with reduction (requires PythonEditor)
- **ReduceByKey** - Reduce by key with custom function (requires PythonEditor)

---

### Want Monitoring/Alerts?

- **ArrayThreshold** - Alert when array values exceed threshold
- **Monitor** - Debug widget showing which nodes have events
- **HSDPeakTest** - Test HSD peak validity

---

### Want to Export Data?

**To workers/collectors:**
- **ExportToWorker** - Send data back to worker from global collector

**To external systems:**
- **PvExport** - Export via AMI-hosted PV (PVA or CA)
- **ZMQ** - Export over ZMQ PUB/SUB
- **UDPMcast** - UDP multicast in BLD format
- **Caput** - Send to external PV via CA (requires caproto)
- **Pvput** - Send to external PV via PVA (requires p4p)

---

## Complete Alphabetical List

### Display Nodes (11 types)

1. **Histogram** - Plot histograms from Binning node
   - Inputs: `Bins` (bin edges), `Counts` (bin values)
   - Use: Visualizing distributions
   - ⚠️ Use terminals `Bins` and `Counts`, NOT `In`!

2. **Histogram2D** - Plot 2D histograms from Binning2D node
   - Inputs: `XBins`, `YBins`, `Counts`
   - Use: Visualizing 2D distributions
   - ⚠️ Use terminals `XBins`, `YBins`, `Counts`, NOT `In`!

3. **ImageViewer** - Display 2D arrays as images
   - Input: 2D array
   - Use: Viewing detector images, processed 2D data
   - ⚠️ NOT for raw sources (sources are already viewable!)

4. **LinePlot** - Plot 1D arrays (X vs Y)
   - Inputs: `X` (X values), `Y` (Y values)
   - Use: Profiles, projections, scan results
   - ⚠️ CRITICAL: Use terminals `X` and `Y`, NOT `In` and `In.1`!

5. **MultiWaveformViewer** - Display 2D arrays as series of waveforms
   - Input: 2D array
   - Use: Multi-channel waveforms

6. **ObjectViewer** - Display string representation of objects
   - Input: Any object
   - Use: Debugging, viewing structured data

7. **ScalarPlot** - Collect and plot scalars over time
   - Input: `Y` (scalar value, time is implicit)
   - Use: Time series monitoring, trending
   - Self-displaying: Yes
   - ⚠️ Use terminal `Y`, NOT `In`!

8. **ScalarViewer** - Display single scalar values
   - Input: Scalar value
   - Use: Showing current value

9. **ScatterPlot** - Correlate two scalars (X vs Y)
   - Inputs: `X` (first value), `Y` (second value)
   - Use: Correlations, pump-probe analysis
   - Self-displaying: Yes
   - ⚠️ CRITICAL: Use terminals `X` and `Y`, NOT `In` and `In.1`!

10. **TimePlot** - Plot values against time of day
    - Input: Scalar value
    - Use: Long-term monitoring with timestamps

11. **WaveformViewer** - Display 1D arrays
    - Input: 1D array
    - Use: Viewing waveforms
    - ⚠️ NOT for raw sources (sources are already viewable!)

---

### Processing Nodes (28 types)

#### Basic Operations

12. **Average** - Compute average
    - Input: Array
    - Output: Scalar or array (depends on input)

13. **Average0D** - Collect and average N scalars
    - Input: Scalar
    - Output: Averaged scalar
    - Configure: N (number of events) in GUI

14. **Average1D** - Collect and average N 1D arrays
    - Input: 1D array
    - Output: Averaged 1D array
    - Configure: N in GUI

15. **Average2D** - Collect and average N 2D arrays
    - Input: 2D array
    - Output: Averaged 2D array
    - Configure: N in GUI

16. **Binning** - Create 1D histogram with fixed bins
    - Input: Array
    - Output: Histogram
    - Configure: Number of bins, range in GUI

17. **Binning2D** - Create 2D histogram with fixed bins
    - Input: 2D array
    - Output: 2D histogram
    - Configure: Bins, center, range in GUI

18. **Calculator** - Evaluate math expressions (requires sympy)
    - Inputs: `In` (first input), `Out` (output)
    - Can add more inputs via GUI: `In.1`, `In.2`, etc.
    - Configure: Expression in GUI (e.g., `In * 2.5 + 10`)
    - Use: Calibration, simple math
    - Note: Calculator uses `In`/`Out` like most processing nodes

19. **Combinations** - Generate combinations using itertools
    - Use: Creating combinations of inputs

20. **Constant** - Generate constant values
    - Output: Configured constant (float, array, etc.)
    - Configure: Value in GUI

21. **ExponentialMovingAverage1D** - EMA for 1D data
    - Input: 1D array
    - Output: Smoothed 1D array
    - Configure: Alpha parameter in GUI

22. **ExponentialMovingAverage2D** - EMA for 2D data
    - Input: 2D array
    - Output: Smoothed 2D array
    - Configure: Alpha parameter in GUI

23. **Filter** - Filter events based on boolean condition
    - Input: Value to test
    - Output: Filtered events
    - Configure: Expression in GUI (e.g., `In > 100`)
    - Use: Pump-probe, event selection

24. **Identity** - Pass-through (no operation)
    - Use: Debugging, graph organization

25. **MeanVsScan** - Create histogram with mean of bins from scan variable
    - Input: Value to bin
    - Output: 1D array of means vs scan
    - Configure: Scan variable name, bins in GUI
    - Use: **Most common scan analysis node**

26. **MeanWaveformVsScan** - Create 2D histogram with mean waveforms
    - Input: Waveform
    - Output: 2D array (waveforms vs scan)
    - Configure: Scan variable, bins in GUI

27. **Polynomial** - Evaluate polynomial
    - Input: Value
    - Output: Polynomial result
    - Configure: Coefficients in GUI

28. **Projection** - Project 2D array along axis
    - Input: 2D array
    - Output: 1D array (projection)
    - Configure: Axis in GUI
    - Use: Creating profiles from images

29. **PythonEditor** - Write custom Python functions
    - Input: Configurable
    - Output: Configurable
    - ⚠️ Requires manual coding in GUI
    - Use: Custom logic that Calculator/Filter can't handle

30. **RMS** - Root mean square
    - Input: Array
    - Output: RMS value

31. **Split** - Split 2D array into 1D arrays
    - Input: 2D array
    - Output: Multiple 1D arrays

32. **Stack1d** - Stack scalars into 1D array
    - Inputs: Multiple scalars
    - Output: 1D array

33. **Stack2d** - Stack 1D arrays into 2D array
    - Inputs: Multiple 1D arrays
    - Output: 2D array

34. **StatsVsScan** - Full statistics vs scan variable
    - Input: Value to analyze
    - Outputs: mean, std, min, max, count vs scan
    - Configure: Scan variable, bins in GUI

35. **Sum** - Sum all array elements
    - Input: Array
    - Output: Scalar sum
    - Use: ROI sums, totals

36. **Take** - Index into array using np.take
    - Input: Array
    - Output: Selected elements
    - Configure: Indices in GUI

#### Time Statistics

37. **TimeMeanRMS0D** - Mean and RMS over time for scalars
    - Input: Scalar
    - Outputs: Mean, RMS over time window

38. **TimeMeanRMS1D** - Mean and RMS over time for 1D arrays
    - Input: 1D array
    - Outputs: Mean, RMS arrays over time

39. **TimeMeanRMS2D** - Mean and RMS over time for 2D arrays
    - Input: 2D array
    - Outputs: Mean, RMS images over time

---

### ROI Nodes (5 types)

40. **Roi0D** - Single pixel selection from image
    - Input: 2D array
    - Output: Scalar (pixel value)
    - Configure: Pixel position in GUI

41. **Roi1D** - Region of interest for 1D arrays
    - Input: 1D array
    - Output: Sliced 1D array
    - Configure: Start, end in GUI

42. **Roi2D** - Rectangular region of interest for images
    - Input: 2D array
    - Output: 2D array (ROI region)
    - ⚠️ **MUST draw ROI rectangle in GUI**
    - Use: Most common ROI operation

43. **RoiArch** - Arch-shaped (cut-donut) ROI for images (requires UtilsROI)
    - Input: 2D array
    - Output: Arch-shaped region
    - Configure: Parameters in GUI

44. **ScatterRoi** - Region of interest for scatter plots
    - Input: Scatter plot data
    - Output: Filtered scatter data
    - Configure: Draw region in scatter plot

---

### Statistics & Fitting Nodes (6 types)

45. **HistMeanRMS** - Mean and stdev from histogram
    - Input: Histogram
    - Outputs: Mean, stdev

46. **Linregress0D** - Linear regression on collected scalars
    - Input: Scalars over time
    - Outputs: Slope, intercept, correlation
    - Use: Trend analysis

47. **Linregress1D** - Linear regression on arrays
    - Input: 1D array
    - Outputs: Fit parameters

48. **CurveFit** - Fit custom function (requires scipy, sympy)
    - Input: 1D data
    - Output: Fit parameters
    - Configure: Function expression in GUI

49. **PeakFit** - Fit Gaussian/Lorentzian peaks (requires scipy, sympy)
    - Input: 1D data
    - Output: Peak parameters

50. **LoadReference1D** - Load 1D reference array from CSV
    - Output: Reference array
    - Configure: File path in GUI

---

### Accumulator Nodes (6 types)

51. **Accumulator** - Custom accumulator with user-defined reduction (requires PythonEditor)
    - Use: Complex accumulation logic

52. **Pick1** - Collect one input
    - Input: Any
    - Output: Single collected value

53. **PickN** - Collect N inputs
    - Input: Any
    - Output: List of N values
    - Configure: N in GUI

54. **ReduceByKey** - Reduce by key with user-defined reduction (requires PythonEditor)
    - Use: Map-reduce style operations

55. **RollingBuffer** - Collect N inputs in rolling buffer
    - Input: Any
    - Output: Rolling buffer of N values
    - Configure: N in GUI

56. **SumN** - Sum N inputs
    - Input: Numeric
    - Output: Sum of N values
    - Configure: N in GUI

---

### Signal Processing Nodes (11 types)

#### FFT (requires pyfftw)

57. **FFT** - Forward FFT (1D)
58. **IFFT** - Inverse FFT (1D)
59. **FFT2** - Forward FFT (2D)
60. **IFFT2** - Inverse FFT (2D)
61. **RFFT** - Real FFT (1D)
62. **IRFFT** - Inverse Real FFT (1D)
63. **RFFT2** - Real FFT (2D)
64. **IRFFT2** - Inverse Real FFT (2D)

#### Filtering

65. **GaussianFilter1D** - Gaussian smoothing for 1D (requires scipy)
    - Input: 1D array
    - Output: Smoothed array
    - Configure: Sigma in GUI

66. **Rotate** - Rotate 2D arrays (requires scipy)
    - Input: 2D array
    - Output: Rotated array
    - Configure: Angle in GUI

67. **CFD** - Constant fraction discriminator (requires constFracDiscrim)
    - Input: Waveform
    - Output: Discriminated signal
    - Use: Timing analysis

---

### Peak/Blob/Hit Finding Nodes (9 types)

68. **BlobFinder1D** - Find blobs in waveforms (requires psana.peakFinder)
    - Input: 1D array
    - Output: Blob positions

69. **BlobFinder2D** - Find blobs in images (requires psana.peakFinder)
    - Input: 2D array
    - Output: Blob positions

70. **EdgeFinder** - Find edges (requires psana.pyalgos)
    - Input: Array
    - Output: Edge positions

71. **HitFinder** - Hit finder for hexanode (requires psana.hexanode)
    - Input: Hexanode data
    - Output: Hits

72. **PeakFinder1D** - 1D peak finder (requires numba)
    - Input: 1D array
    - Output: Peak positions

73. **PeakFinderV4R3** - Psana peakfinder v4r3d2 (requires psalg_ext)
    - Input: 2D array
    - Output: Peak positions
    - Use: X-ray detector peak finding

74. **ThresholdingHitFinder** - Threshold-based hit finding
    - Input: Array
    - Output: Hits above threshold
    - Configure: Threshold in GUI

75. **WFPeaks** - Waveform peak finding (requires psana.hexanode)
    - Input: Waveform
    - Output: Peak positions

76. **Hexanode** - Hexanode detector processing (requires psana.hexanode)
    - Input: Hexanode data
    - Output: Processed hexanode data

---

### LCLS-Specific Nodes (6 types)

77. **XTCAVLasingOn** - XTCAV lasing characterization (requires psana.xtcav)
    - Input: XTCAV data
    - Output: Lasing parameters

78. **Mask** - Generate detector masks from calibration (requires psana.detector)
    - Output: Mask array

79. **Mask3dFrom2d** - Convert 2D mask to 3D array (requires psana.pscalib)
    - Input: 2D mask
    - Output: 3D mask array

80. **Geometry** - Generate pixel coordinates from geometry (requires psana.pscalib)
    - Output: Coordinate arrays

81. **TableFromArr3d** - Convert 3D detector data to 2D table (requires ami.pyalgos)
    - Input: 3D array
    - Output: 2D table

82. **TestQtPickle** - Test node for Qt pickle functionality (requires ami.pyalgos)
    - Use: Testing only

---

### Alert & Monitoring Nodes (3 types)

83. **ArrayThreshold** - Display alert when array values exceed threshold
    - Input: Array
    - Configure: Threshold in GUI
    - Use: Monitoring, alerts

84. **Monitor** - Debug widget showing which nodes have events
    - Use: Debugging graph execution

85. **HSDPeakTest** - Test HSD peak validity
    - Input: HSD peak data
    - Output: Validation result

---

### Export Nodes (6 types)

86. **ExportToWorker** - Send data back to worker from global collector
    - Use: Feedback loops

87. **PvExport** - Export through AMI-hosted PV (PVA or CA)
    - Input: Data to export
    - Configure: PV name, type in GUI

88. **ZMQ** - Export data over ZMQ PUB/SUB
    - Input: Data to export
    - Configure: Port, topic in GUI

89. **UDPMcast** - UDP multicast in BLD format
    - Input: Data to export
    - Configure: Multicast address in GUI

90. **Caput** - Send to external PV via Channel Access (requires caproto)
    - Input: Value to send
    - Configure: PV name in GUI

91. **Pvput** - Send to external PV via PVAccess (requires p4p)
    - Input: Value to send
    - Configure: PV name in GUI

---

## Node Availability

Some nodes require optional dependencies. If a dependency is missing, the node won't be available:

**Always available (core nodes):** Display, basic processing, ROI, accumulators, basic statistics

**Requires scipy:** GaussianFilter1D, Rotate, curve fitting nodes

**Requires sympy:** Calculator, PythonEditor, Filter, CurveFit, PeakFit

**Requires pyfftw:** All FFT nodes

**Requires psana/psalg:** Peak finders, blob finders, LCLS-specific nodes

**Requires caproto:** Caput node

**Requires p4p:** Pvput node

**Requires numba:** PeakFinder1D

---

## Common Node Combinations

**ROI analysis:**
```
Source → Roi2D → Sum → ScalarPlot
```

**Correlation:**
```
SourceA → ScatterPlot.In
SourceB → ScatterPlot.In.1
```

**Scan analysis:**
```
Source → MeanVsScan → LinePlot
```

**Pump-probe:**
```
Detector → Roi2D → Sum → Filter(pump) → MeanVsScan
                        → Filter(probe) → MeanVsScan
```

**Image processing:**
```
Source → Roi2D → Projection → LinePlot
```

---

## Remember

- **SourceNodes are viewable** - Don't add viewers for raw sources!
- **Only use nodes from this list** - If it's not here, it doesn't exist
- **Check dependencies** - Some nodes require optional packages
- **Configure in GUI** - Node parameters (except name) set in GUI
- **Self-displaying nodes** - ScatterPlot, ScalarPlot, LinePlot, Histogram show themselves
