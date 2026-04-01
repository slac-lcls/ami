# AMI Node Terminals Quick Reference

**Generated:** 2026-04-01 13:00:31

Quick lookup table for node terminal names and connection patterns.

---

| Node | Input Terminals | Output Terminals |
|------|-----------------|------------------|
| **Accumulator** | `In` | `Count`, `Sum` |
| **ArrayThreshold** | `In` | - |
| **Average** | `In` | `Out` |
| **Average0D** | `In` | `Out` |
| **Average1D** | `In` | `Out` |
| **Average2D** | `In` | `Out` |
| **Binning** | `In` | `Bins`, `Counts` |
| **Binning2D** | `X`, `Y` | `Counts`, `XBins`, `YBins` |
| **BlobFinder1D** | `In` | `NBlobs`, `Sum`, `X` |
| **BlobFinder2D** | `In` | `NBlobs`, `Sum`, `X`, `Y` |
| **CFD** | `In` | `Out` |
| **Calculator** | `In` | `Out` |
| **Caput** | `In`, `eventid` | - |
| **Combinations** | `In` | `Out` |
| **Constant** | - | `Out` |
| **CurveFit** | `Y` | `fx`, `p0`, `pcov` |
| **EdgeFinder** | `Calib`, `IIR`, `Image` | `amplitude`, `amplitude_next`, `edge`, `fwhm`, `ref_amplitude` |
| **ExponentialMovingAverage1D** | `In` | `Count`, `Out` |
| **ExponentialMovingAverage2D** | `In` | `Count`, `Out` |
| **ExportToWorker** | `In`, `Timestamp` | `Out` |
| **FFT** | `In` | `Out` |
| **FFT2** | `In` | `Out` |
| **Filter** | `In` | `Out` |
| **GaussianFilter1D** | `In` | `Out` |
| **Geometry** | `arr3d`, `calibcons` | `coords_xyz`, `image`, `inds_xy` |
| **HSDPeakTest** | `Peaks`, `Waveform` | `Fail`, `Pass` |
| **Hexanode** | `Calib`, `Event Number`, `Num of Hits`, `Peak Times` | `R`, `T`, `X`, `Y` |
| **HistMeanRMS** | `In` | `Mean`, `Stdev` |
| **Histogram** | `Bins`, `Counts` | - |
| **Histogram2D** | `Counts`, `XBins`, `YBins` | - |
| **HitFinder** | `Num of Hits`, `Peak Times` | `T`, `X`, `Y` |
| **IFFT** | `In` | `Out` |
| **IFFT2** | `In` | `Out` |
| **IRFFT** | `In` | `Out` |
| **IRFFT2** | `In` | `Out` |
| **Identity** | `In` | `Out` |
| **ImageViewer** | `In` | - |
| **LinePlot** | `X`, `Y` | - |
| **Linregress0D** | `X.In`, `Y.In` | `Fit`, `X`, `Y`, `rvalue` |
| **Linregress1D** | `X`, `Y` | `fit`, `intercept`, `pvalue`, `rvalue`, `slope`, `stderr` |
| **LoadReference1D** | - | `X`, `Y` |
| **Mask** | `calibconst` | `Mask`, `Mask3D` |
| **Mask3dFrom2d** | `inds_xy`, `mask2d` | `mask3d` |
| **MeanVsScan** | `Bin`, `Value` | `Bins`, `Counts` |
| **MeanWaveformVsScan** | `Bin`, `Value` | `Counts`, `X Bins`, `Y Bins` |
| **Monitor** | `In` | - |
| **MultiWaveformViewer** | `In` | - |
| **ObjectViewer** | `In` | - |
| **PeakFinder1D** | `Waveform` | `Centroid`, `Width` |
| **PeakFinderV4R3** | `Image` | `amp_tot`, `col_cgrav`, `npix`, `row_cgrav`, `son` |
| **PeakFit** | `In` | `ampl`, `center`, `fit`, `fwhm`, `offset`, `width` |
| **Pick1** | `In` | `Out` |
| **PickN** | `In` | `Out` |
| **Polynomial** | `In` | `Out` |
| **Projection** | `In` | `Out` |
| **PvExport** | `In`, `eventid` | - |
| **Pvput** | `In`, `eventid` | - |
| **PythonEditor** | - | - |
| **RFFT** | `In` | `Out` |
| **RFFT2** | `In` | `Out` |
| **RMS** | `In` | `Out` |
| **ReduceByKey** | `Key`, `Value` | `Out` |
| **Roi0D** | `In` | `Out` |
| **Roi1D** | `In` | `Out` |
| **Roi2D** | `In` | `Out`, `Roi_Coordinates` |
| **RoiArch** | `image`, `mask` | `ABinCent`, `ABinEdges`, `AProj`, `BBox`, `Mask`, `RBinCent`, `RBinEdges`, `ROIPars`, `RProj`, `RadAngBinStatist`, `RadAngNormIntens` |
| **RollingBuffer** | `In` | `Count`, `Out` |
| **Rotate** | `In` | `Out` |
| **ScalarPlot** | `Y` | - |
| **ScalarViewer** | `In` | - |
| **ScatterPlot** | `X`, `Y` | - |
| **ScatterRoi** | `X`, `Y` | `Out.X`, `Out.Y` |
| **Split** | `In` | `Out` |
| **Stack1d** | `In` | `Out` |
| **Stack2d** | `In` | `Out` |
| **StatsVsScan** | `Bin`, `Value` | `Bins`, `Error`, `Mean`, `Stdev` |
| **Sum** | `In` | `Out` |
| **SumN** | - | - |
| **TableFromArr3d** | `arr3d` | `arr2d` |
| **Take** | `In` | `Out` |
| **TestQtPickle** | `arr3d` | `arr2d` |
| **ThresholdingHitFinder** | `In` | `Out` |
| **TimeMeanRMS0D** | `In` | `Mean`, `RMS` |
| **TimeMeanRMS1D** | `In` | `Mean`, `RMS` |
| **TimeMeanRMS2D** | `In` | `Mean`, `RMS` |
| **TimePlot** | `X`, `Y` | - |
| **UDPMcast** | `In`, `eventid` | - |
| **WFPeaks** | `Times`, `Waveform` | `Index`, `Num of Hits`, `Peak Times`, `Values` |
| **WaveformViewer** | `In` | - |
| **XTCAVLasingOn** | `cam`, `pars`, `src` | `agreement`, `power`, `pulse`, `time` |
| **ZMQ** | `In`, `Timestamp` | - |

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
