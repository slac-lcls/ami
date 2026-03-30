# AMI Processing Nodes Reference

This document covers the 5 most commonly used processing nodes for data manipulation in AMI.

## Sum - Array Summation ⭐⭐⭐

**Purpose:** Sum all elements of an array to produce a scalar value.

**Terminals:**
- Input: `In` (N-dimensional array)
- Output: `Out` (scalar sum)

**Key Parameters:**
- None (simple summation operation)

**Common Use Cases:**
- Sum ROI pixels to get total intensity
- Calculate total detector signal
- Reduce 2D images to single values
- Integrate waveforms

**Example:**
```python
# Sum ROI to get total intensity
sum_node = chart.createNode('Sum', 'roi_sum')
amicli.connect_nodes('detector_roi', 'Out', 'roi_sum', 'In')

# Display the sum value
scalar_plot = chart.createNode('ScalarPlot', 'sum_vs_time')
amicli.connect_nodes('roi_sum', 'Out', 'sum_vs_time', 'In')
```

**See also:** Templates - roi_analysis.py, pump_probe.py

---

## Projection - Array Dimensionality Reduction ⭐

**Purpose:** Project N-dimensional arrays down to (N-1) dimensions by summing or averaging along an axis.

**Terminals:**
- Input: `In` (N-dimensional array)
- Output: `Out` ((N-1)-dimensional array)

**Key Parameters:**
- `axis`: Which axis to project along (0, 1, 2, etc.)
- `method`: 'sum' or 'mean'

**Common Use Cases:**
- Create 1D profiles from 2D images
- Reduce detector data for visualization
- Extract horizontal/vertical lineouts
- Prepare data for 1D analysis

**Example:**
```python
# Project 2D detector image to 1D horizontal profile
projection = chart.createNode('Projection', 'horizontal_profile')
# Configure in GUI: set axis=0 for horizontal, axis=1 for vertical
amicli.connect_nodes('detector_image', 'Out', 'horizontal_profile', 'In')

# Display the projection
line_plot = chart.createNode('LinePlot', 'profile_plot')
amicli.connect_nodes('horizontal_profile', 'Out', 'profile_plot', 'In')
```

**See also:** Templates - waveform_analysis.py

---

## Binning - Azimuthal/Radial Binning ⭐

**Purpose:** Perform azimuthal or radial binning of 2D detector images (commonly used for scattering/diffraction).

**Terminals:**
- Input: `In` (2D image)
- Output: `Out` (1D binned array)

**Key Parameters:**
- `bins`: Number of bins
- `x0`, `y0`: Center coordinates for binning
- `rmin`, `rmax`: Radial range (for radial binning)
- `phimin`, `phimax`: Angular range (for azimuthal binning)

**Common Use Cases:**
- Azimuthal integration of diffraction patterns
- Radial profiles from centered data
- Powder diffraction analysis
- Circular feature extraction

**Example:**
```python
# Create azimuthal binning of detector
binning = chart.createNode('Binning', 'azimuthal_integration')
# Configure in GUI: set center (x0, y0), bins, and angular range
amicli.connect_nodes('detector_source', 'Out', 'azimuthal_integration', 'In')

# Display binned result
line_plot = chart.createNode('LinePlot', 'integrated_pattern')
amicli.connect_nodes('azimuthal_integration', 'Out', 'integrated_pattern', 'In')
```

**Important:** Requires manual configuration of center coordinates in GUI.

---

## Average - Rolling Average ⭐

**Purpose:** Compute rolling average over multiple events to reduce noise.

**Terminals:**
- Input: `In` (any data type)
- Output: `Out` (averaged data)

**Key Parameters:**
- `N`: Number of events to average over

**Common Use Cases:**
- Noise reduction
- Smooth time series
- Stabilize fluctuating signals
- Improve signal-to-noise ratio

**Example:**
```python
# Average detector signal over 10 events
average = chart.createNode('Average', 'smoothed_signal')
# Configure in GUI: set N=10 (or desired number)
amicli.connect_nodes('detector_source', 'Out', 'smoothed_signal', 'In')

# Display smoothed result
scalar_plot = chart.createNode('ScalarPlot', 'smooth_vs_time')
amicli.connect_nodes('smoothed_signal', 'Out', 'smooth_vs_time', 'In')
```

**Note:** Higher N values = smoother data but more lag.

---

## Calculator - Mathematical Expressions ⭐

**Purpose:** Apply mathematical expressions to inputs using a simple expression language.

**Terminals:**
- Input: `In`, `In.1`, `In.2`, etc. (multiple inputs)
- Output: `Out` (calculated result)

**Key Parameters:**
- `expression`: Mathematical expression using input names

**Expression Syntax:**
- Inputs referenced as: `In`, `In_1`, `In_2`, etc.
- Operators: `+`, `-`, `*`, `/`, `**` (power)
- Functions: `np.sqrt()`, `np.exp()`, `np.log()`, `np.abs()`, `np.sin()`, `np.cos()`, etc.
- Examples:
  - `In * 2.5 + 10`
  - `(In + In_1) / 2`
  - `np.sqrt(In**2 + In_1**2)`

**Common Use Cases:**
- Scale detector values (calibration)
- Combine multiple signals
- Calculate derived quantities
- Unit conversions
- Simple math without custom code

**Example:**
```python
# Create calculator to scale and offset detector
calc = chart.createNode('Calculator', 'calibrated_signal')
# In GUI, set expression: In * 2.5 + 10
amicli.connect_nodes('detector_raw', 'Out', 'calibrated_signal', 'In')
print('Calculator created. Set expression in GUI: In * 2.5 + 10')
```

**Example - Combining two signals:**
```python
# Calculate distance from two coordinates
calc = chart.createNode('Calculator', 'distance')
# In GUI, set expression: np.sqrt(In**2 + In_1**2)
amicli.connect_nodes('x_position', 'Out', 'distance', 'In')
amicli.connect_nodes('y_position', 'Out', 'distance', 'In.1')
print('Calculator created. Set expression in GUI: np.sqrt(In**2 + In_1**2)')
```

**Decision Tree:**
- Simple math (+-*/)? → Use **Calculator**
- Need loops/conditionals? → Use **Filter** or **PythonEditor**
- Need to load external data? → Use **PythonEditor**

**See also:** nodes_control.md (PythonEditor for complex operations)

---

## Common Processing Patterns

### ROI → Sum → Display
```
Detector → ROI → Sum → ScalarPlot
```

### Image → Projection → Plot
```
Detector2D → Projection → LinePlot
```

### Smooth → Process → Display
```
Source → Average → Calculator → ScalarPlot
```

### Multiple Inputs to Calculator
```
SourceA → Calculator.In
SourceB → Calculator.In.1
SourceC → Calculator.In.2
         ↓
      Result
```

## Performance Tips

1. **Sum before processing** - Reduce data early in pipeline
2. **Use Calculator for simple math** - Faster than PythonEditor
3. **Projection reduces data** - Good for 2D → 1D visualization
4. **Average trades latency for SNR** - Choose N carefully
5. **Binning is expensive** - Use appropriate bin count
