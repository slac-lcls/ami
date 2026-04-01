# Common AMI Graph Patterns

This document describes the 5 most common graph patterns found in real AMI workflows.

## Pattern 1: Simple Correlation - X vs Y Scatter Plot

**Purpose:** Visualize correlation between two scalar data streams.

**Graph Structure:**
```
SourceA → ScatterPlot.X
SourceB → ScatterPlot.Y
```

**Use Cases:**
- Laser intensity vs detector response
- Motor position vs signal
- Beam parameter correlations
- Any two scalar values you want to correlate

**Example Code:**
```python
# Create scatter plot for laser vs detector
scatter = amicli.create_node('ScatterPlot', 'Laser Vs Detector')
amicli.connect_nodes('laser_source', 'Out', scatter.name(), 'X')
amicli.connect_nodes('detector_source', 'Out', scatter.name(), 'Y')
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
# Create ROI and sum
roi = amicli.create_node('Roi2D', 'Signal ROI')
amicli.connect_nodes('detector_source', 'Out', roi.name(), 'In')

sum_node = amicli.create_node('Sum', 'ROI Sum')
amicli.connect_nodes(roi.name(), 'Out', sum_node.name(), 'In')

# Plot intensity over time
scalar_plot = amicli.create_node('ScalarPlot', 'Intensity Vs Time')
amicli.connect_nodes(sum_node.name(), 'Out', scalar_plot.name(), 'In')

print('')
print('⚠️  Draw ROI rectangle in detector source viewer!')
print('⚠️  (Click detector_source node to view image)')
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
roi = amicli.create_node('Roi2D', 'Detector ROI')
amicli.connect_nodes('detector_source', 'Out', roi.name(), 'In')

sum_node = amicli.create_node('Sum', 'ROI Sum')
amicli.connect_nodes(roi.name(), 'Out', sum_node.name(), 'In')

# Filter for pump events (laser on)
filter_pump = amicli.create_node('Filter', 'Pump Filter')
amicli.connect_nodes('laser_status', 'Out', filter_pump.name(), 'In')
print('Set Pump Filter expression in GUI: In == 1')

# Pump signal vs scan
pump_scan = amicli.create_node('MeanVsScan', 'Pump Vs Delay')
amicli.connect_nodes(sum_node.name(), 'Out', pump_scan.name(), 'In')
print('Set Pump Vs Delay scan variable in GUI (e.g., delay_stage)')

pump_plot = amicli.create_node('LinePlot', 'Pump Curve')
amicli.connect_nodes(pump_scan.name(), 'Out', pump_plot.name(), 'In')

# Filter for probe events (laser off)
filter_probe = amicli.create_node('Filter', 'Probe Filter')
amicli.connect_nodes('laser_status', 'Out', filter_probe.name(), 'In')
print('Set Probe Filter expression in GUI: In == 0')

# Probe signal vs scan
probe_scan = amicli.create_node('MeanVsScan', 'Probe Vs Delay')
amicli.connect_nodes(sum_node.name(), 'Out', probe_scan.name(), 'In')

probe_plot = amicli.create_node('LinePlot', 'Probe Curve')
amicli.connect_nodes(probe_scan.name(), 'Out', probe_plot.name(), 'In')

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
# Create projection for profile
projection = amicli.create_node('Projection', 'Waveform Profile')
amicli.connect_nodes('digitizer_source', 'Out', projection.name(), 'In')
print('Set projection axis in GUI')

# Plot the profile
line_plot = amicli.create_node('LinePlot', 'Profile Plot')
amicli.connect_nodes(projection.name(), 'Out', line_plot.name(), 'In')

print('Note: Click digitizer_source to view raw waveform')
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
scan_a = amicli.create_node('MeanVsScan', 'Detector A Scan')
amicli.connect_nodes('detector_a', 'Out', scan_a.name(), 'In')
print('Set Detector A Scan scan variable in GUI (e.g., motor_pos)')

plot_a = amicli.create_node('LinePlot', 'Scan A Plot')
amicli.connect_nodes(scan_a.name(), 'Out', plot_a.name(), 'In')

# Scan signal B
scan_b = amicli.create_node('MeanVsScan', 'Detector B Scan')
amicli.connect_nodes('detector_b', 'Out', scan_b.name(), 'In')
print('Set Detector B Scan scan variable in GUI (same as above)')

plot_b = amicli.create_node('LinePlot', 'Scan B Plot')
amicli.connect_nodes(scan_b.name(), 'Out', plot_b.name(), 'In')

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
SignalA → MeanVsScan_A → ScatterPlot.X
SignalB → MeanVsScan_B → ScatterPlot.Y
```

---

## General Tips

1. **Start simple** - Begin with basic pattern, add complexity as needed
2. **Visualize first** - Always create viewers to see your data
3. **Name descriptively** - Use names like "pump_sum", "laser_vs_detector", "scan_plot"
4. **Test incrementally** - Build graph step by step, verify each stage works
5. **Save frequently** - Save your .fc file as you build complex graphs
