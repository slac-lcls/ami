# User Intent Parsing Examples

This document shows how to handle various ambiguous and unclear user requests by asking clarifying questions.

---

## Example 1: Ambiguous Source Reference

### Scenario: Multiple matching sources

**User Request:** `%build_graph show me the detector`

**Problem:**
- Multiple detectors exist in available sources
- Unclear if user wants raw view or processing

**Agent Response:**
```json
{
  "type": "question",
  "message": "I found multiple detectors in the available sources. I need to know which one you want to view.",
  "questions": [
    {
      "question": "Which detector would you like to view?",
      "options": ["cspad_detector", "epix_detector", "jungfrau_detector"],
      "context": "Found 3 detectors in available sources"
    },
    {
      "question": "What would you like to do with the detector?",
      "options": [
        "Just view the raw image (no code needed - click the source)",
        "Set up ROI analysis on the detector",
        "Create time series of detector sum",
        "Correlate detector with another signal"
      ],
      "context": "This determines whether we need to create processing nodes"
    }
  ],
  "assumptions_if_skipped": "I'll use 'cspad_detector' and tell you to click it to view the raw image"
}
```

**User's refined request:** `%build_graph set up ROI analysis on cspad_detector`

**Agent's code response:**
```json
{
  "explanation": "Creates ROI analysis pipeline for cspad_detector with sum over time",
  "code": "print('Setting up ROI analysis...')\\nroi = amicli.create_node('Roi2D', 'CSPAD ROI')\\namicli.connect_nodes('cspad_detector', 'Out', roi.name(), 'In')\\nsum_node = amicli.create_node('Sum', 'ROI Sum')\\namicli.connect_nodes(roi.name(), 'Out', sum_node.name(), 'In')\\nplot = amicli.create_node('ScalarPlot', 'Sum Vs Time')\\namicli.connect_nodes(sum_node.name(), 'Out', plot.name(), 'In')\\nprint('')\\nprint('⚠️  Click cspad_detector to view image and draw ROI rectangle!')\\nprint('')",
  "warnings": ["You must draw the ROI rectangle in the cspad_detector viewer before data will flow"],
  "next_steps": ["Draw ROI in the detector viewer", "Watch the Sum Vs Time plot update"]
}
```

---

## Example 2: Vague Operation Request

### Scenario: User says "analyze" without specifics

**User Request:** `%build_graph analyze the laser signal`

**Problem:**
- "analyze" is too vague - could mean many things
- Unknown what kind of analysis is needed

**Agent Response:**
```json
{
  "type": "question",
  "message": "The term 'analyze' can mean many different things. I need to know what kind of analysis you want to perform.",
  "questions": [
    {
      "question": "What kind of analysis do you want?",
      "options": [
        "View laser value over time (ScalarPlot)",
        "Correlate laser with detector signal (ScatterPlot)",
        "Filter events by laser threshold (Filter)",
        "Bin laser values vs scan variable (MeanVsScan)",
        "Calculate statistics (mean, RMS, etc.)"
      ]
    }
  ],
  "assumptions_if_skipped": "I'll create a simple ScalarPlot to monitor laser intensity over time"
}
```

---

## Example 3: Unclear Visualization Need

### Scenario: Just "show X" - raw or processed?

**User Request:** `%build_graph show cspad`

**Problem:**
- Unclear if they just want to view raw data (no code needed)
- Or if they want to set up analysis

**Agent Response:**
```json
{
  "type": "question",
  "message": "I can help you work with the cspad detector. What do you want to do?",
  "questions": [
    {
      "question": "Choose an option:",
      "options": [
        "Just view raw cspad image (no code needed - click the source node)",
        "View cspad AND set up ROI analysis",
        "View cspad AND correlate with laser",
        "Monitor cspad sum over time"
      ],
      "context": "Source nodes have built-in viewers, so just viewing doesn't require code"
    }
  ]
}
```

**If user says option 1 (just view):**
```json
{
  "explanation": "Source nodes are already viewable - no code needed",
  "code": "print('The cspad source node is already viewable!')\\nprint('')\\nprint('👉 Simply click on the \"cspad\" source node in the flowchart')\\nprint('👉 An image viewer will automatically appear')\\nprint('')\\nprint('If you want to analyze the detector (ROI, sum, etc.), run %build_graph again with more details')",
  "next_steps": ["Click on cspad source node to view the detector image"]
}
```

---

## Example 4: Missing Connection Details

### Scenario: User wants correlation but doesn't say what with

**User Request:** `%build_graph correlate laser`

**Problem:**
- Correlation needs two signals (X and Y)
- User only specified one

**Agent Response:**
```json
{
  "type": "question",
  "message": "To create a correlation plot, I need two signals. You specified 'laser', but what should it be correlated with?",
  "questions": [
    {
      "question": "What would you like to correlate the laser signal with?",
      "options": ["cspad_detector sum", "epix_detector sum", "motor position", "another signal"],
      "context": "ScatterPlot needs two inputs: X (laser) and Y (your choice)"
    },
    {
      "question": "If correlating with a detector, do you want:",
      "options": [
        "Total detector sum",
        "ROI sum (I'll create ROI for you)",
        "Specific pixel value"
      ]
    }
  ]
}
```

---

## Example 5: Ambiguous Node Type

### Scenario: User uses colloquial term instead of node type

**User Request:** `%build_graph create a histogram of laser values`

**Problem:**
- "histogram" could mean Binning node (creates histogram data) or Histogram node (displays it)
- User probably wants both

**Agent Response (if clear enough to proceed):**
```json
{
  "explanation": "Creates histogram of laser values and displays it",
  "code": "print('Creating histogram...')\\nbinning = amicli.create_node('Binning', 'Laser Histogram')\\namicli.connect_nodes('laser', 'Out', binning.name(), 'In')\\nhistogram_display = amicli.create_node('Histogram', 'Histogram Display')\\namicli.connect_nodes(binning.name(), 'Out', histogram_display.name(), 'In')\\nprint('')\\nprint('Configure histogram bins and range in Laser Histogram node GUI')\\nprint('')",
  "warnings": ["Configure number of bins and range in the Binning node"],
  "next_steps": ["Set histogram bins (e.g., 100)", "Set range to match your laser values"]
}
```

**Note:** This is clear enough - "histogram of values" implies binning + display

---

## Example 6: Domain-Specific Terminology

### Scenario: User uses physics terminology

**User Request:** `%build_graph pump-probe analysis`

**Problem:**
- "pump-probe" is physics terminology that implies specific graph structure
- But details matter: which signals, how to distinguish pump vs probe

**Agent Response:**
```json
{
  "type": "question",
  "message": "I can help set up pump-probe analysis. I need a few details about your setup.",
  "questions": [
    {
      "question": "Which detector signal do you want to analyze?",
      "options": ["cspad", "epix", "jungfrau"],
      "context": "This will be the signal we split into pump/probe"
    },
    {
      "question": "How do you distinguish pump from probe events?",
      "options": [
        "Laser on/off (binary laser status signal)",
        "Laser above/below threshold (continuous laser signal)",
        "Scan variable (e.g., delay stage position)",
        "Other condition (I'll create Filter nodes for you to configure)"
      ]
    },
    {
      "question": "What analysis do you want on pump and probe separately?",
      "options": [
        "ROI sum vs time",
        "ROI sum vs scan variable",
        "Full detector sum",
        "Statistics (mean, RMS)"
      ]
    }
  ]
}
```

**After clarification, user says:** `%build_graph cspad ROI sum vs delay, laser on/off for pump/probe`

**Agent's code response:**
```json
{
  "explanation": "Creates pump-probe analysis with cspad ROI sum binned vs delay stage for pump (laser on) and probe (laser off) separately",
  "code": "print('Setting up pump-probe analysis...')\\nprint('')\\n# Create ROI and sum\\nroi = chart.createNode('Roi2D', 'cspad_roi')\\namicli.connect_nodes('cspad', 'Out', 'cspad_roi', 'In')\\nsum_node = chart.createNode('Sum', 'roi_sum')\\namicli.connect_nodes('cspad_roi', 'Out', 'roi_sum', 'In')\\nprint('Created ROI and sum nodes')\\n\\n# Pump path (laser on)\\nfilter_pump = chart.createNode('Filter', 'pump_filter')\\namicli.connect_nodes('laser_status', 'Out', 'pump_filter', 'In')\\nprint('Set pump_filter expression in GUI: In == 1')\\n\\npump_scan = chart.createNode('MeanVsScan', 'pump_vs_delay')\\namicli.connect_nodes('roi_sum', 'Out', 'pump_vs_delay', 'In')\\nprint('Set pump_vs_delay scan variable in GUI to delay stage name')\\n\\npump_plot = chart.createNode('LinePlot', 'pump_curve')\\namicli.connect_nodes('pump_vs_delay', 'Out', 'pump_curve', 'In')\\nprint('Created pump analysis path')\\n\\n# Probe path (laser off)\\nfilter_probe = chart.createNode('Filter', 'probe_filter')\\namicli.connect_nodes('laser_status', 'Out', 'probe_filter', 'In')\\nprint('Set probe_filter expression in GUI: In == 0')\\n\\nprobe_scan = chart.createNode('MeanVsScan', 'probe_vs_delay')\\namicli.connect_nodes('roi_sum', 'Out', 'probe_vs_delay', 'In')\\n\\nprobe_plot = chart.createNode('LinePlot', 'probe_curve')\\namicli.connect_nodes('probe_vs_delay', 'Out', 'probe_curve', 'In')\\nprint('Created probe analysis path')\\n\\nprint('')\\nprint('⚠️  IMPORTANT CONFIGURATION STEPS:')\\nprint('1. Click cspad to view image and draw ROI rectangle')\\nprint('2. Set pump_filter expression: In == 1')\\nprint('3. Set probe_filter expression: In == 0')\\nprint('4. Set scan variable in both MeanVsScan nodes (e.g., delay_stage)')\\nprint('5. Set number of bins in MeanVsScan nodes')\\nprint('')",
  "warnings": [
    "Assumes laser_status source exists with values 0 (off) and 1 (on)",
    "You must configure filter expressions and scan variables in GUI",
    "Draw ROI in cspad viewer before data flows"
  ],
  "next_steps": [
    "Draw ROI in cspad detector viewer",
    "Configure filter expressions (pump: In == 1, probe: In == 0)",
    "Set scan variable name in both MeanVsScan nodes",
    "Set appropriate number of bins for your scan range"
  ]
}
```

---

## Example 7: Unclear Processing Chain

### Scenario: User wants endpoint but not clear on intermediate steps

**User Request:** `%build_graph plot detector vs motor`

**Problem:**
- What aspect of detector? (full sum, ROI sum, pixel value?)
- Direct correlation or scan analysis?

**Agent Response:**
```json
{
  "type": "question",
  "message": "I can create a plot of detector vs motor. I need to clarify a few details.",
  "questions": [
    {
      "question": "What detector quantity do you want to plot?",
      "options": [
        "Sum of entire detector",
        "Sum of ROI (I'll create ROI node)",
        "Specific pixel value",
        "Detector mean"
      ]
    },
    {
      "question": "What type of plot?",
      "options": [
        "Scatter plot (point-by-point correlation)",
        "Mean vs motor position (binned scan analysis)",
        "Both scatter and binned scan"
      ],
      "context": "Scatter shows individual points, MeanVsScan shows binned averages"
    }
  ]
}
```

---

## Example 8: Source Exists vs Doesn't Exist

### Scenario: User references source that may or may not exist

**User Request:** `%build_graph show laser_intensity`

**CRITICAL:** Always check the available_sources list before generating code!

**Check available sources:**
- If `laser_intensity` exists in available_sources → Simple response
- If it doesn't exist → Ask for clarification with fuzzy matching

**If source exists:**
```json
{
  "explanation": "The laser_intensity source already exists and is viewable",
  "code": "print('The laser_intensity source node is already in your graph')\\nprint('')\\nprint('👉 Click on \"laser_intensity\" to view its value')\\nprint('👉 Or run %build_graph with what you want to do with it')\\nprint('')\\nprint('Examples:')\\nprint('  - correlate laser_intensity with detector')\\nprint('  - plot laser_intensity vs scan')\\nprint('  - filter events where laser_intensity > 100')\\nprint('')",
  "next_steps": ["Click laser_intensity source to view", "Or specify what analysis you need"]
}
```

**If source doesn't exist:**
```json
{
  "type": "question",
  "message": "I don't see a source named 'laser_intensity' in the available sources.",
  "questions": [
    {
      "question": "Did you mean one of these sources?",
      "options": ["laser_power", "laser_energy", "laser_diode"],
      "context": "These are the laser-related sources I found in available_sources"
    },
    {
      "question": "Or would you like me to:",
      "options": [
        "Show all available sources",
        "List sources matching 'laser'",
        "Help me search for the right source"
      ]
    }
  ]
}
```

**Example with correlation (multiple sources):**

**User Request:** `%build_graph can we do a correlation of laser and delta_t?`

**Check available_sources:**
- Is `laser` in the list? 
- Is `delta_t` in the list?

**If BOTH don't exist:**
```json
{
  "type": "question",
  "message": "I don't see sources named 'laser' or 'delta_t' in the available sources.",
  "questions": [
    {
      "question": "For 'laser', did you mean:",
      "options": ["laser_power", "laser_diode", "laser_timing"],
      "context": "Closest matches in available sources"
    },
    {
      "question": "For 'delta_t', did you mean:",
      "options": ["delay_time", "time_delta", "dt_laser"],
      "context": "Closest matches in available sources"
    }
  ],
  "assumptions_if_skipped": "Please check available sources with: list(amicli.chart.source_library.sourceList.keys())"
}
```

**If ONE exists, ONE doesn't:**
```json
{
  "type": "question",
  "message": "I found 'laser' in the available sources, but I don't see 'delta_t'.",
  "questions": [
    {
      "question": "For 'delta_t', did you mean:",
      "options": ["delay_time", "time_delta", "dt_laser", "timing_delta"],
      "context": "These are timing-related sources I found"
    },
    {
      "question": "Or do you want to:",
      "options": [
        "See all available sources",
        "Correlate laser with a different signal"
      ]
    }
  ]
}
```

**If BOTH exist:**
```json
{
  "explanation": "Creates scatter plot correlating laser (X) and delta_t (Y)",
  "code": "print('Creating correlation scatter plot...')\\nscatter = amicli.create_node('ScatterPlot', 'Laser Vs Delta T')\\namicli.connect_nodes('laser', 'Out', scatter.name(), 'X')\\namicli.connect_nodes('delta_t', 'Out', scatter.name(), 'Y')\\nprint('Scatter plot created!')\\nprint('Configure axis labels in the GUI if desired')",
  "warnings": ["Assumes 'laser' and 'delta_t' sources exist and are already in the graph"],
  "next_steps": ["Set axis labels in scatter plot GUI", "Adjust point size/colors if needed"]
}
```

**CRITICAL VALIDATION RULE:**
Before generating code that uses `amicli.connect_nodes('source_name', ...)`, you MUST verify that 'source_name' is in the available_sources list provided in the prompt!

---

## Example 9: Multiple Valid Interpretations

### Scenario: Request could go multiple ways

**User Request:** `%build_graph average the detector`

**Problem:**
- Average over time (Average2D node)?
- Average projection (Projection node)?
- Mean per scan point (MeanVsScan)?

**Agent Response:**
```json
{
  "type": "question",
  "message": "There are several ways to average detector data. Which do you need?",
  "questions": [
    {
      "question": "What kind of averaging?",
      "options": [
        "Average over N events (time averaging)",
        "Average over scan variable (binned mean)",
        "Projection average (sum along axis / N)",
        "Exponential moving average"
      ],
      "context": "Each type uses a different node"
    }
  ]
}
```

---

## Example 10: Clear Request (No Questions Needed)

### Scenario: Specific, unambiguous request

**User Request:** `%build_graph create a scatter plot with laser on x-axis and cspad ROI sum on y-axis`

**Analysis:**
- ✓ Clear what to create (scatter plot)
- ✓ Clear X input (laser)
- ✓ Clear Y input (cspad ROI sum) - implies ROI + Sum nodes
- ✓ Only one reasonable interpretation

**Agent Response (Code, not Question):**
```json
{
  "explanation": "Creates scatter plot correlating laser (X) with cspad ROI sum (Y), including ROI and Sum nodes",
  "code": "print('Creating ROI analysis and scatter plot...')\\n\\n# Create ROI and sum for cspad\\nroi = amicli.create_node('Roi2D', 'CSPAD ROI')\\namicli.connect_nodes('cspad', 'Out', roi.name(), 'In')\\n\\nsum_node = amicli.create_node('Sum', 'ROI Sum')\\namicli.connect_nodes(roi.name(), 'Out', sum_node.name(), 'In')\\n\\n# Create scatter plot\\nscatter = amicli.create_node('ScatterPlot', 'Laser Vs CSPAD Sum')\\namicli.connect_nodes('laser', 'Out', scatter.name(), 'X')\\namicli.connect_nodes(sum_node.name(), 'Out', scatter.name(), 'Y')\\n\\nprint('')\\nprint('✓ Scatter plot created!')\\nprint('⚠️  Click on cspad to view image and draw ROI rectangle')\\nprint('👉 Configure axis labels in the scatter plot GUI')\\nprint('')",
  "warnings": [
    "Assumes 'laser' and 'cspad' sources exist in graph",
    "You must draw ROI rectangle in cspad viewer before correlation data appears"
  ],
  "next_steps": [
    "Click cspad source to view detector image",
    "Draw ROI rectangle in the image",
    "Set X-axis label to 'Laser Intensity' in scatter plot",
    "Set Y-axis label to 'CSPAD ROI Sum' in scatter plot"
  ]
}
```

**Note:** This doesn't need a question because the request is completely unambiguous.

---

## Decision Framework

### When to Ask Questions

**ASK when:**
1. Multiple sources match vague description
2. Operation is ambiguous ("analyze", "process", "show")
3. Missing critical information (what to correlate with?)
4. Unclear if user wants raw view vs processing
5. Domain terminology without details (pump-probe, scan, binning)
6. Multiple valid node choices (average could mean 5 different things)

### When to Proceed with Code

**PROCEED when:**
1. Request is specific and unambiguous
2. Only one reasonable interpretation exists
3. All required information is present
4. Source names are explicit and exist
5. Common, well-defined pattern (ROI analysis, scatter plot, etc.)

**BUT:** Always document assumptions in warnings field!

---

## Key Principles

1. **Be helpful, not obstructive** - Don't ask questions if request is clear
2. **Provide options** - Give user concrete choices to pick from
3. **Explain context** - Why does this matter? What will it affect?
4. **Offer assumptions** - "If you just want me to proceed, I'll assume..."
5. **Show available choices** - List actual sources/options from the graph state
6. **Guide next steps** - If asking questions, show how to refine the request

---

## Anti-Patterns to Avoid

❌ **Don't ask obvious questions:**
```json
{
  "question": "Do you want to create a scatter plot?",
  "context": "User literally said 'create scatter plot'"
}
```

❌ **Don't ask too many questions at once:**
```json
{
  "questions": [/* 7 different questions */]
}
```
Limit to 2-3 focused questions.

❌ **Don't ask without providing options:**
```json
{
  "question": "What do you want to do?",
  "options": []  // No options provided!
}
```

❌ **Don't ask when you can reasonably assume:**
If user says "create ROI" and there's only one detector, don't ask which detector.

✅ **Do provide context for your questions:**
```json
{
  "question": "Which detector?",
  "context": "Found 3 detectors: cspad, epix, jungfrau",
  "options": ["cspad", "epix", "jungfrau"]
}
```
