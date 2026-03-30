# Common AMI Graph Patterns

This document describes the 5 most common graph patterns found in real AMI workflows.

## Pattern 1: Simple Correlation - X vs Y Scatter Plot

**Purpose:** Visualize correlation between two scalar data streams.

**Graph Structure:**
```
SourceA → ScatterPlot.In
SourceB → ScatterPlot.In.1
```

**Use Cases:**
- Laser intensity vs detector response
- Motor position vs signal
- Beam parameter correlations
- Any two scalar values you want to correlate

**Example Code:**
```python
# Create scatter plot for laser vs detector
scatter = chart.createNode('ScatterPlot', 'laser_vs_detector')
amicli.connect_nodes('laser_source', 'Out', 'laser_vs_detector', 'In')
amicli.connect_nodes('detector_source', 'Out', 'laser_vs_detector', 'In.1')
print('Scatter plot created! Configure axis labels in GUI.')
```

**Template:** `templates/simple_correlation.py`

---

## Pattern 2: ROI Analysis - Extract and Analyze Region

**Purpose:** Define region of interest on detector, sum pixels, and monitor over time.

**Graph Structure:**
```
Detector → ImageViewer (for visualization)
        → Roi2D → Sum → ScalarPlot
```

**Use Cases:**
- Monitor specific detector region
- Track feature intensity
- Background-subtracted analysis
- Multi-region comparison

**Example Code:**
```python
# View the detector image
image_viewer = chart.createNode('ImageViewer', 'detector_image')
amicli.connect_nodes('detector_source', 'Out', 'detector_image', 'In')

# Create ROI and sum
roi = chart.createNode('Roi2D', 'signal_roi')
amicli.connect_nodes('detector_source', 'Out', 'signal_roi', 'In')

sum_node = chart.createNode('Sum', 'roi_sum')
amicli.connect_nodes('signal_roi', 'Out', 'roi_sum', 'In')

# Plot intensity over time
scalar_plot = chart.createNode('ScalarPlot', 'intensity_vs_time')
amicli.connect_nodes('roi_sum', 'Out', 'intensity_vs_time', 'In')

print('')
print('⚠️  Draw ROI rectangle in detector_image viewer!')
print('')
```

**Template:** `templates/roi_analysis.py`

---

## Pattern 3: Pump-Probe Analysis - Filtered Dual Path

**Purpose:** Separate pump and probe events, analyze each separately, compare results.

**Graph Structure:**
```
Detector → Roi2D → Sum → Filter(laser==1) → MeanVsScan → LinePlot(pump)
                               |
                               ├→ Filter(laser==0) → MeanVsScan → LinePlot(probe)
                               
LaserStatus → Filter inputs
```

**Use Cases:**
- Laser on/off comparison
- X-ray pump / X-ray probe
- Difference signal analysis
- Time-resolved measurements

**Example Code:**
```python
# Setup detector ROI and sum
roi = chart.createNode('Roi2D', 'detector_roi')
amicli.connect_nodes('detector_source', 'Out', 'detector_roi', 'In')

sum_node = chart.createNode('Sum', 'roi_sum')
amicli.connect_nodes('detector_roi', 'Out', 'roi_sum', 'In')

# Filter for pump events (laser on)
filter_pump = chart.createNode('Filter', 'pump_filter')
amicli.connect_nodes('laser_status', 'Out', 'pump_filter', 'In')
print('Set pump_filter expression in GUI: In == 1')

# Pump signal vs scan
pump_scan = chart.createNode('MeanVsScan', 'pump_vs_delay')
amicli.connect_nodes('roi_sum', 'Out', 'pump_vs_delay', 'In')
print('Set pump_vs_delay scan variable in GUI (e.g., delay_stage)')

pump_plot = chart.createNode('LinePlot', 'pump_curve')
amicli.connect_nodes('pump_vs_delay', 'Out', 'pump_curve', 'In')

# Filter for probe events (laser off)
filter_probe = chart.createNode('Filter', 'probe_filter')
amicli.connect_nodes('laser_status', 'Out', 'probe_filter', 'In')
print('Set probe_filter expression in GUI: In == 0')

# Probe signal vs scan
probe_scan = chart.createNode('MeanVsScan', 'probe_vs_delay')
amicli.connect_nodes('roi_sum', 'Out', 'probe_vs_delay', 'In')

probe_plot = chart.createNode('LinePlot', 'probe_curve')
amicli.connect_nodes('probe_vs_delay', 'Out', 'probe_curve', 'In')

print('')
print('⚠️  Remember to:')
print('   1. Draw ROI in detector image')
print('   2. Configure filter expressions')
print('   3. Set scan variable for MeanVsScan nodes')
print('')
```

**Template:** `templates/pump_probe.py`

---

## Pattern 4: Waveform Analysis - Peak Finding and Projection

**Purpose:** Analyze 1D waveform data to find peaks, extract features, create profiles.

**Graph Structure:**
```
WaveformSource → PeakFinder → Stats → Viewer
               → Projection → Binning → LinePlot
```

**Use Cases:**
- Digitizer waveform analysis
- Peak detection in time series
- Spectral analysis
- Line-out analysis

**Example Code:**
```python
# Display raw waveform
waveform_viewer = chart.createNode('WaveformViewer', 'raw_waveform')
amicli.connect_nodes('digitizer_source', 'Out', 'raw_waveform', 'In')

# Create projection for profile
projection = chart.createNode('Projection', 'waveform_profile')
amicli.connect_nodes('digitizer_source', 'Out', 'waveform_profile', 'In')
print('Set projection axis in GUI')

# Plot the profile
line_plot = chart.createNode('LinePlot', 'profile_plot')
amicli.connect_nodes('waveform_profile', 'Out', 'profile_plot', 'In')
```

**Template:** `templates/waveform_analysis.py`

---

## Pattern 5: Scan Analysis - Parameter Sweep with Multiple Signals

**Purpose:** Monitor multiple signals during a parameter scan (motor, energy, delay, etc.).

**Graph Structure:**
```
SourceA → MeanVsScan → LinePlot(signal A)
SourceB → MeanVsScan → LinePlot(signal B)
SourceC → MeanVsScan → LinePlot(signal C)
(all use same scan variable)
```

**Use Cases:**
- Motor scans (rocking curves, alignment)
- Energy scans
- Delay scans
- Multi-parameter monitoring

**Example Code:**
```python
# Scan signal A
scan_a = chart.createNode('MeanVsScan', 'detector_a_scan')
amicli.connect_nodes('detector_a', 'Out', 'detector_a_scan', 'In')
print('Set detector_a_scan scan variable in GUI (e.g., motor_pos)')

plot_a = chart.createNode('LinePlot', 'scan_a_plot')
amicli.connect_nodes('detector_a_scan', 'Out', 'scan_a_plot', 'In')

# Scan signal B
scan_b = chart.createNode('MeanVsScan', 'detector_b_scan')
amicli.connect_nodes('detector_b', 'Out', 'detector_b_scan', 'In')
print('Set detector_b_scan scan variable in GUI (same as above)')

plot_b = chart.createNode('LinePlot', 'scan_b_plot')
amicli.connect_nodes('detector_b_scan', 'Out', 'scan_b_plot', 'In')

print('')
print('⚠️  Configure MeanVsScan nodes with:')
print('   - scan: Name of scan variable')
print('   - bins: Number of scan points')
print('')
```

**Template:** `templates/scan_analysis.py`

---

## Pattern Selection Guide

**I want to...**

- **Compare two scalar signals** → Pattern 1 (Simple Correlation)
- **Analyze a detector region** → Pattern 2 (ROI Analysis)
- **Do pump-probe / on-off comparison** → Pattern 3 (Pump-Probe)
- **Analyze waveforms / 1D data** → Pattern 4 (Waveform Analysis)
- **Monitor signals during a scan** → Pattern 5 (Scan Analysis)

---

## Combining Patterns

Patterns can be combined! Examples:

### ROI + Scan Analysis
```
Detector → ROI → Sum → MeanVsScan → LinePlot
```

### Pump-Probe + ROI
```
Detector → ROI → Sum → Filter(pump) → Stats
                     → Filter(probe) → Stats
```

### Correlation + Scan
```
SignalA → MeanVsScan_A → ScatterPlot.In
SignalB → MeanVsScan_B → ScatterPlot.In.1
```

---

## General Tips

1. **Start simple** - Begin with basic pattern, add complexity as needed
2. **Visualize first** - Always create viewers to see your data
3. **Name descriptively** - Use names like "pump_sum", "laser_vs_detector", "scan_plot"
4. **Test incrementally** - Build graph step by step, verify each stage works
5. **Save frequently** - Save your .fc file as you build complex graphs
