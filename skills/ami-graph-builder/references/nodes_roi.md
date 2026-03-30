# AMI ROI (Region of Interest) Nodes Reference

ROI nodes allow you to define regions on detector images for focused analysis.

## Roi2D - 2D Rectangular ROI ⭐

**Purpose:** Define a rectangular region of interest on a 2D detector image and extract that region for analysis.

**Terminals:**
- Input: `In` (2D image array)
- Output: `Out` (2D sub-array corresponding to ROI)

**Key Parameters:**
- ROI is drawn **interactively in the image viewer** GUI
- No code-level parameters (geometry defined graphically)

**Common Use Cases:**
- Select specific detector region
- Exclude noise/artifacts from analysis
- Focus on feature of interest
- Multi-ROI analysis (create multiple Roi2D nodes)

**Example:**
```python
# Create ROI on detector image
roi = chart.createNode('Roi2D', 'detector_roi')
amicli.connect_nodes('detector_source', 'Out', 'detector_roi', 'In')

# Sum the ROI pixels
sum_node = chart.createNode('Sum', 'roi_sum')
amicli.connect_nodes('detector_roi', 'Out', 'roi_sum', 'In')

# Display sum over time
scalar_plot = chart.createNode('ScalarPlot', 'roi_intensity')
amicli.connect_nodes('roi_sum', 'Out', 'roi_intensity', 'In')

print('')
print('⚠️  IMPORTANT: Draw the ROI rectangle in the detector image viewer!')
print('   1. Right-click on detector image viewer')
print('   2. Select the ROI node to make it active')
print('   3. Click and drag to draw the rectangle')
print('')
```

**Important Notes:**
1. ROI must be drawn **manually in the GUI** - there is no way to set coordinates programmatically
2. The ROI rectangle appears as an overlay on the detector image
3. ROI can be resized and moved interactively
4. Multiple ROIs can be created on the same image

**Typical Workflow:**
```
Detector → ImageViewer (for visualization)
        → Roi2D → Sum → ScalarPlot
```

**See also:** Templates - roi_analysis.py, pump_probe.py

---

## Working with Multiple ROIs

You can create multiple ROI nodes to analyze different regions:

```python
# Create two ROIs on same detector
roi1 = chart.createNode('Roi2D', 'signal_roi')
roi2 = chart.createNode('Roi2D', 'background_roi')

amicli.connect_nodes('detector_source', 'Out', 'signal_roi', 'In')
amicli.connect_nodes('detector_source', 'Out', 'background_roi', 'In')

# Sum each ROI
sum1 = chart.createNode('Sum', 'signal_sum')
sum2 = chart.createNode('Sum', 'background_sum')

amicli.connect_nodes('signal_roi', 'Out', 'signal_sum', 'In')
amicli.connect_nodes('background_roi', 'Out', 'background_sum', 'In')

# Calculate signal - background
calc = chart.createNode('Calculator', 'corrected_signal')
amicli.connect_nodes('signal_sum', 'Out', 'corrected_signal', 'In')
amicli.connect_nodes('background_sum', 'Out', 'corrected_signal', 'In.1')
print('Calculator created. Set expression in GUI: In - In_1')

print('')
print('⚠️  Draw both ROIs in the detector image viewer:')
print('   - signal_roi: around the feature of interest')
print('   - background_roi: in a background region')
print('')
```

---

## ROI Best Practices

1. **Always create an ImageViewer** - You need to see the detector to draw the ROI
2. **Named ROIs** - Use descriptive names (signal_roi, background_roi, peak1_roi, etc.)
3. **Test ROI placement** - Watch the Sum output to verify ROI captures desired signal
4. **Background subtraction** - Use second ROI for background, subtract with Calculator
5. **ROI persistence** - ROI coordinates are saved with the flowchart (.fc file)

---

## Other ROI Node Types (Less Common)

### Roi1D
- For 1D waveform regions
- Similar concept but operates on 1D arrays

### RoiNonRect
- Non-rectangular ROI shapes
- More flexible geometry
- Requires more complex setup

### AreaDetectorRoi
- Specialized for area detectors
- May have additional features specific to certain detectors

**Note:** Roi2D is by far the most commonly used ROI node type.
