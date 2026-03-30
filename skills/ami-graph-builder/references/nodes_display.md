# AMI Display Nodes Reference

This document covers the 7 most commonly used display nodes for visualizing data in AMI.

## ScatterPlot - X vs Y Correlation Plot ⭐⭐⭐⭐⭐

**Purpose:** Create scatter plots to visualize correlations between two data streams.

**Terminals:**
- Input: `In` (X values) and `In.1` (Y values)
- Output: None (terminal display node)

**Key Parameters:**
- `title`: Plot title
- `xLabel`: X-axis label
- `yLabel`: Y-axis label
- `symbolSize`: Size of scatter points
- `symbolPen`: Border color/width of points
- `symbolBrush`: Fill color of points

**Common Use Cases:**
- Correlating two detector signals
- Laser intensity vs detector response
- Pump-probe delay scans
- Motor position vs signal

**Example:**
```python
# Create scatter plot for laser vs detector correlation
scatter = chart.createNode('ScatterPlot', 'laser_vs_detector')
amicli.connect_nodes('laser_source', 'Out', 'laser_vs_detector', 'In')
amicli.connect_nodes('detector_source', 'Out', 'laser_vs_detector', 'In.1')
print('Scatter plot created! Configure axis labels and colors in the GUI.')
```

**See also:** Templates - simple_correlation.py

---

## ScalarPlot - Time Series Plot ⭐⭐⭐⭐

**Purpose:** Plot scalar values vs event number (time series).

**Terminals:**
- Input: `In` (scalar value to plot)
- Output: None (terminal display node)

**Key Parameters:**
- `title`: Plot title
- `length`: Number of events to display (rolling window)
- `pen`: Line color and style

**Common Use Cases:**
- Monitor detector signal over time
- Track beam intensity
- Visualize filter outputs
- Real-time monitoring of calculated values

**Example:**
```python
# Create time series plot for detector sum
scalar_plot = chart.createNode('ScalarPlot', 'detector_trend')
amicli.connect_nodes('detector_sum', 'Out', 'detector_trend', 'In')
```

**See also:** Most scan and monitoring workflows

---

## LinePlot - 1D Profile/Line Plot ⭐⭐⭐⭐

**Purpose:** Display 1D arrays as line plots (profiles, histograms, projections).

**Terminals:**
- Input: `In` (1D array)
- Output: None (terminal display node)

**Key Parameters:**
- `title`: Plot title
- `pen`: Line color and width
- `fillLevel`: Fill area under curve (optional)
- `fillBrush`: Fill color

**Common Use Cases:**
- Display detector projections
- Show azimuthal binning results
- Visualize 1D histograms
- Plot waveform data

**Example:**
```python
# Create line plot for projection
line_plot = chart.createNode('LinePlot', 'projection_plot')
amicli.connect_nodes('detector_projection', 'Out', 'projection_plot', 'In')
```

**See also:** Templates - waveform_analysis.py, scan_analysis.py

---

## WaveformViewer - Waveform Display ⭐⭐

**Purpose:** Display raw waveform data (1D time-series arrays).

**Terminals:**
- Input: `In` (waveform array)
- Output: None (terminal display node)

**Key Parameters:**
- `title`: Viewer title
- `autoRange`: Auto-scale axes
- `pen`: Waveform line color/width

**Common Use Cases:**
- Display digitizer waveforms
- Show detector line-outs
- Visualize time-domain signals

**Example:**
```python
# Display waveform from detector
waveform = chart.createNode('WaveformViewer', 'raw_waveform')
amicli.connect_nodes('digitizer_source', 'Out', 'raw_waveform', 'In')
```

**See also:** Templates - waveform_analysis.py

---

## ImageViewer - 2D Image Display ⭐

**Purpose:** Display 2D detector images.

**Terminals:**
- Input: `In` (2D array)
- Output: None (terminal display node)

**Key Parameters:**
- `title`: Image title
- `colorMap`: Color map for image display
- `autoRange`: Auto-scale color range
- `autoHistogramRange`: Auto-adjust histogram

**Common Use Cases:**
- Display area detector images
- View 2D binning results
- Monitor camera feeds
- Visualize correlation matrices

**Example:**
```python
# Display detector image
image_viewer = chart.createNode('ImageViewer', 'detector_image')
amicli.connect_nodes('cspad_source', 'Out', 'detector_image', 'In')
```

**Important:** ROI nodes connect to ImageViewer to define regions for analysis.

**See also:** Templates - roi_analysis.py

---

## ScalarViewer - Single Value Display ⭐

**Purpose:** Display a single scalar value with large text.

**Terminals:**
- Input: `In` (scalar value)
- Output: None (terminal display node)

**Key Parameters:**
- `title`: Viewer title
- `units`: Display units (optional)
- `precision`: Number of decimal places

**Common Use Cases:**
- Monitor critical values
- Display summary statistics
- Show current beam parameters
- Real-time calculated metrics

**Example:**
```python
# Display ROI sum as large number
scalar_viewer = chart.createNode('ScalarViewer', 'roi_total')
amicli.connect_nodes('roi_sum', 'Out', 'roi_total', 'In')
```

---

## Histogram - Distribution Plot ⭐

**Purpose:** Create histograms to show value distributions.

**Terminals:**
- Input: `In` (values to histogram)
- Output: `Out` (histogram counts)

**Key Parameters:**
- `bins`: Number of histogram bins
- `range`: Min/max range for binning
- `autoRange`: Auto-determine range from data

**Common Use Cases:**
- Show distribution of detector values
- Analyze noise characteristics
- Visualize event statistics
- Quality control monitoring

**Example:**
```python
# Create histogram of detector values
histogram = chart.createNode('Histogram', 'detector_histogram')
amicli.connect_nodes('detector_source', 'Out', 'detector_histogram', 'In')

# Display the histogram
hist_plot = chart.createNode('LinePlot', 'hist_display')
amicli.connect_nodes('detector_histogram', 'Out', 'hist_display', 'In')
```

**Note:** Histogram has an output terminal, so it can feed downstream processing nodes.

---

## General Tips for Display Nodes

1. **Always provide descriptive names** - Makes graphs easier to understand
2. **Configure labels and titles** - Do this in the GUI after creation
3. **Multiple inputs** - Some plots (ScatterPlot) have multiple input terminals (In, In.1, In.2, etc.)
4. **Color customization** - Most support pen/brush parameters for colors
5. **Display is asynchronous** - Plots update when data arrives

## Common Connection Patterns

### Simple Display
```
Source → DisplayNode
```

### Processed Display
```
Source → ProcessingNode → DisplayNode
```

### Multi-Input Display
```
SourceA → ScatterPlot.In
SourceB → ScatterPlot.In.1
```

### Display with Passthrough
```
Source → Histogram → LinePlot
              ↓
         (continue processing)
```
