# AMI Statistics Nodes Reference

Statistics nodes are used for scan analysis and computing statistics binned by scan variables.

## MeanVsScan - Binned Mean vs Scan Variable ⭐⭐⭐⭐

**Purpose:** Compute the mean (average) of an input value binned by a scan control variable. Essential for scan analysis.

**Terminals:**
- Input: `In` (values to average)
- Output: `Out` (array of mean values vs scan variable)

**Key Parameters:**
- `scan`: Name of the scan control variable (motor, delay stage, etc.)
- `bins`: Number of bins for the scan range
- `range`: [min, max] range for scan variable (optional, can auto-range)

**Common Use Cases:**
- Motor scans (position vs signal)
- Delay scans (pump-probe timing)
- Energy scans
- Rocking curve measurements
- Any experiment with a scanned parameter

**Example:**
```python
# Create MeanVsScan for detector vs delay scan
mean_scan = chart.createNode('MeanVsScan', 'detector_vs_delay')
# In GUI, configure: scan='las_comp_wp', bins=50
amicli.connect_nodes('detector_sum', 'Out', 'detector_vs_delay', 'In')

# Display the scan result
line_plot = chart.createNode('LinePlot', 'scan_plot')
amicli.connect_nodes('detector_vs_delay', 'Out', 'scan_plot', 'In')

print('MeanVsScan created.')
print('⚠️  Configure in GUI:')
print('   - scan: Name of scan variable (e.g., las_comp_wp, lxt_ttc)')
print('   - bins: Number of scan points')
print('   - range: [min, max] if known, or leave for auto-range')
```

**How It Works:**
1. For each event, node receives the scan variable value
2. Events are binned based on scan variable value
3. For each bin, computes the mean of all input values in that bin
4. Output is an array of mean values, one per bin

**Important Notes:**
- Scan variable must exist in the data stream
- Common scan variables: motor positions, delay stages, energy
- Use with LinePlot to visualize scan curves
- Data accumulates over the scan - output updates as scan progresses

**See also:** Templates - scan_analysis.py, pump_probe.py

---

## StatsVsScan - Full Statistics vs Scan Variable ⭐⭐

**Purpose:** Compute full statistics (mean, std, min, max, count) binned by scan variable.

**Terminals:**
- Input: `In` (values to analyze)
- Outputs: 
  - `mean` - Mean values per bin
  - `std` - Standard deviation per bin
  - `min` - Minimum value per bin
  - `max` - Maximum value per bin
  - `count` - Number of events per bin

**Key Parameters:**
- `scan`: Name of the scan control variable
- `bins`: Number of bins
- `range`: [min, max] range for scan variable

**Common Use Cases:**
- Scan analysis with error bars
- Quality assessment of scan data
- Understanding scan point statistics
- Detecting outliers or unstable regions

**Example:**
```python
# Create StatsVsScan for detailed scan analysis
stats_scan = chart.createNode('StatsVsScan', 'detector_stats')
# In GUI, configure: scan='motor_pos', bins=50
amicli.connect_nodes('detector_sum', 'Out', 'detector_stats', 'In')

# Plot mean with error bars
line_plot_mean = chart.createNode('LinePlot', 'mean_plot')
amicli.connect_nodes('detector_stats', 'mean', 'mean_plot', 'In')

line_plot_std = chart.createNode('LinePlot', 'std_plot')
amicli.connect_nodes('detector_stats', 'std', 'std_plot', 'In')

print('StatsVsScan created.')
print('⚠️  Configure scan variable and bins in GUI')
print('Available outputs: mean, std, min, max, count')
```

**Comparison with MeanVsScan:**
- **MeanVsScan**: Just the mean, simpler, faster
- **StatsVsScan**: Full statistics, more comprehensive

**Typical Workflow:**
```
Detector → ROI → Sum → MeanVsScan → LinePlot
                              ↓
                         (scan curve)
```

---

## Scan Analysis Best Practices

1. **Know your scan variable name** - Check data source configuration
2. **Choose appropriate bins** - Match expected scan points
3. **Use LinePlot for visualization** - Best for scan curves
4. **MeanVsScan is usually enough** - Use StatsVsScan only if you need error analysis
5. **Multiple signals per scan** - Create separate MeanVsScan nodes for each signal

---

## Common Scan Patterns

### Simple Scan
```
Source → MeanVsScan → LinePlot
```

### ROI Scan
```
Detector → ROI → Sum → MeanVsScan → LinePlot
```

### Pump-Probe Scan
```
Detector → Filter (laser on) → Sum → MeanVsScan → LinePlot
                                      (delay scan)
```

### Dual-Signal Scan
```
SignalA → MeanVsScan_A → LinePlot_A
SignalB → MeanVsScan_B → LinePlot_B
(both use same scan variable)
```

### Correlation Scan
```
SignalA → MeanVsScan_A ─→ ScatterPlot.In
SignalB → MeanVsScan_B ─→ ScatterPlot.In.1
(both use same scan variable)
```

---

## Troubleshooting Scans

**Problem:** Scan plot is empty or not updating
- Check scan variable name is correct
- Verify scan range includes actual scan values
- Ensure scan is running and data flowing

**Problem:** Too few or too many bins
- Match bin count to expected scan points
- Use auto-range first, then set explicit range if needed

**Problem:** Noisy scan curve
- Increase averaging (more events per bin point)
- Check for unstable beam/detector
- Filter outliers before MeanVsScan

**Problem:** Multiple scans in same session
- Scans accumulate data - may need to reset between scans
- Use graph reset or create new graph for each scan
