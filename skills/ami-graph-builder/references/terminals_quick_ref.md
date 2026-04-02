# AMI Node Terminals Quick Reference

**Generated:** 2026-04-01 21:01:08

Quick lookup table for node terminal names and connection patterns.

---

| Node | Inputs | Outputs |
|------|--------|---------|
| **Accumulator** | In (Any) | Count (int), Sum (Any) |
| **ArrayThreshold** | In (Array1d) | - |
| **Average** | In (Array1d|Array2d) | Out (float) |
| **Average0D** | In (float) | Out (float) |
| **Average1D** | In (Array1d) | Out (Array1d) |
| **Average2D** | In (Array2d) | Out (Array2d) |
| **Binning** | In (float|Array1d|Array2d) | Bins (Array1d), Counts (Array1d) |
| **Binning2D** | X (float|Array1d), Y (float|Array1d) | Counts (Array2d), XBins (Array1d), YBins (Array1d) |
| **BlobFinder1D** | In (Array1d) | NBlobs (int), Sum (Array1d), X (Array1d) |
| **BlobFinder2D** | In (Array2d) | NBlobs (int), Sum (Array1d), X (Array1d), Y (Array1d) |
| **CFD** | In (Array1d) | Out (float) |
| **Calculator** | In (float|Array1d|Array2d|Array3d) | Out (Any) |
| **Caput** | In (str|int|float|Array1d), eventid (int) | - |
| **Combinations** | In (Array1d) | Out (Array1d) |
| **Constant** | - | Out (Any) |
| **CurveFit** | Y (Array1d) | fx (Array1d), p0 (Array1d), pcov (Array2d) |
| **EdgeFinder** | Calib (dict), IIR (Array1d), Image (Array1d) | amplitude (float), amplitude_next (float), edge (float), fwhm (float), ref_amplitude (float) |
| **ExponentialMovingAverage1D** | In (Array1d) | Count (int), Out (Array1d) |
| **ExponentialMovingAverage2D** | In (Array2d) | Count (int), Out (Array2d) |
| **ExportToWorker** | In (Any), Timestamp (float) | Out (Any) |
| **FFT** | In (Array1d) | Out (Array1d) |
| **FFT2** | In (Array2d) | Out (Array2d) |
| **Filter** | In (Any) | Out (Any) |
| **GaussianFilter1D** | In (Array1d) | Out (Array1d) |
| **Geometry** | arr3d (Array3d), calibcons (dict) | coords_xyz (list), image (Array2d), inds_xy (list) |
| **HSDPeakTest** | Peaks (Peaks), Waveform (Array1d) | Fail (int), Pass (int) |
| **Hexanode** | Calib (dict), Event Number (float), Num of Hits (Array1d), Peak Times (Array2d) | R (Array1d), T (Array1d), X (Array1d), Y (Array1d) |
| **HistMeanRMS** | In (Array1d) | Mean (float), Stdev (float) |
| **Histogram** | Bins (Array1d), Counts (Array1d) | - |
| **Histogram2D** | Counts (Array2d), XBins (Array1d), YBins (Array1d) | - |
| **HitFinder** | Num of Hits (Array1d), Peak Times (Array2d) | T (Array1d), X (Array1d), Y (Array1d) |
| **IFFT** | In (Array1d) | Out (Array1d) |
| **IFFT2** | In (Array2d) | Out (Array2d) |
| **IRFFT** | In (Array1d) | Out (Array1d) |
| **IRFFT2** | In (Array2d) | Out (Array2d) |
| **Identity** | In (Any) | Out (Any) |
| **ImageViewer** | In (Array2d) | - |
| **LinePlot** | X (Array1d), Y (Array1d) | - |
| **Linregress0D** | X.In (float), Y.In (float) | Fit (Array1d), X (Array1d), Y (Array1d), rvalue (float) |
| **Linregress1D** | X (Array1d), Y (Array1d) | fit (Array1d), intercept (float), pvalue (float), rvalue (float), slope (float), stderr (float) |
| **LoadReference1D** | - | X (Array1d), Y (Array1d) |
| **Mask** | calibconst (dict) | Mask (Array2d), Mask3D (Array3d) |
| **Mask3dFrom2d** | inds_xy (list), mask2d (Array2d) | mask3d (Array3d) |
| **MeanVsScan** | Bin (float), Value (float) | Bins (Array1d), Counts (Array1d) |
| **MeanWaveformVsScan** | Bin (float), Value (Array1d) | Counts (Array2d), X Bins (Array1d), Y Bins (Array1d) |
| **Monitor** | In (Any) | - |
| **MultiWaveformViewer** | In (MultiChannelWaveform) | - |
| **ObjectViewer** | In (Any) | - |
| **PeakFinder1D** | Waveform (Array1d) | Centroid (Array1d), Width (Array1d) |
| **PeakFinderV4R3** | Image (Array2d) | amp_tot (Array1d), col_cgrav (Array1d), npix (Array1d), row_cgrav (Array1d), son (Array1d) |
| **PeakFit** | In (Array1d) | ampl (float), center (float), fit (Array1d), fwhm (float), offset (float), width (float) |
| **Pick1** | In (T) | Out (T) |
| **PickN** | In (T) | Out (Array1d) |
| **Polynomial** | In (Array1d) | Out (Array1d) |
| **Projection** | In (Array2d) | Out (Array1d) |
| **PvExport** | In (Any), eventid (int) | - |
| **Pvput** | In (str|int|float|Array1d|Array2d), eventid (int) | - |
| **PythonEditor** | - | - |
| **RFFT** | In (Array1d) | Out (Array1d) |
| **RFFT2** | In (Array2d) | Out (Array2d) |
| **RMS** | In (Array1d|Array2d) | Out (float) |
| **ReduceByKey** | Key (Any), Value (Any) | Out (dict) |
| **Roi0D** | In (Array2d) | Out (float) |
| **Roi1D** | In (Array1d) | Out (Array1d) |
| **Roi2D** | In (Array2d) | Out (Array2d), Roi_Coordinates (Array1d) |
| **RoiArch** | image (Array2d), mask (Array2d) | ABinCent (Array1d), ABinEdges (Array1d), AProj (Array1d), BBox (Array1d), Mask (Array2d), RBinCent (Array1d), RBinEdges (Array1d), ROIPars (Array1d), RProj (Array1d), RadAngBinStatist (Array2d), RadAngNormIntens (Array2d) |
| **RollingBuffer** | In (T) | Count (int), Out (Array1d) |
| **Rotate** | In (Array2d) | Out (Array2d) |
| **ScalarPlot** | Y (float) | - |
| **ScalarViewer** | In (float) | - |
| **ScatterPlot** | X (float), Y (float) | - |
| **ScatterRoi** | X (float), Y (float) | Out.X (Array1d), Out.Y (Array1d) |
| **Split** | In (Array2d) | Out (Array1d) |
| **Stack1d** | In (float|list[float]) | Out (Array1d) |
| **Stack2d** | In (Array1d|list[Array1d]) | Out (Array2d) |
| **StatsVsScan** | Bin (float), Value (float) | Bins (Array1d), Error (Array1d), Mean (Array1d), Stdev (Array1d) |
| **Sum** | In (Array) | Out (float) |
| **SumN** | - | - |
| **TableFromArr3d** | arr3d (Array3d) | arr2d (Array2d) |
| **Take** | In (Array) | Out (float|Array1d|Array2d) |
| **TestQtPickle** | arr3d (Array3d) | arr2d (Array2d) |
| **ThresholdingHitFinder** | In (Array2d) | Out (Array2d) |
| **TimeMeanRMS0D** | In (float) | Mean (float), RMS (float) |
| **TimeMeanRMS1D** | In (Array1d) | Mean (Array1d), RMS (Array1d) |
| **TimeMeanRMS2D** | In (Array2d) | Mean (Array2d), RMS (Array2d) |
| **TimePlot** | X (float), Y (float) | - |
| **UDPMcast** | In (Any), eventid (int) | - |
| **WFPeaks** | Times (Array2d), Waveform (Array2d) | Index (Array2d), Num of Hits (Array1d), Peak Times (Array2d), Values (Array2d) |
| **WaveformViewer** | In (Array1d) | - |
| **XTCAVLasingOn** | cam (Detector), pars (Detector), src (DataSource) | agreement (float), power (Array2d), pulse (Array1d), time (Array2d) |
| **ZMQ** | In (Any), Timestamp (float) | - |

---

## Common Terminal Patterns

### Display Nodes
- **ScatterPlot**: Inputs: `X`, `Y` (NEVER use `In` or `In.1`)
- **LinePlot**: Inputs: `X`, `Y` for single trace
- **Histogram**: Input: `Bins` (binned data from Binning node)
- **ScalarPlot**: Input: `Y` (scalar values)

### Processing Nodes
- **Binning**: Input: `Bins` (data to bin); Output: `Out` (NEVER use `XBins`)
- **Binning2D**: Inputs: `XBins`, `YBins` (2D binning)
- **Calculator**: Input: `In`; Output: `Out`

### ROI Nodes
- **Roi0D**: Input: `In`; Output: `Out` (single value)
- **Roi1D**: Input: `In`; Output: `Out` (1D region)
- **Roi2D**: Input: `In`; Output: `Out` (2D region)
