# Performance Timing Instrumentation - Usage Guide

**Date**: 2026-03-31  
**Status**: Ready to Test  
**Purpose**: Identify where the 12 seconds is spent in agent responses

---

## What Was Added

I've added detailed timing instrumentation to the `chat()` function that measures:

1. **State request**: Time spent waiting for graph state (currently 0.5s timeout)
2. **Prompt building**: Time to construct the agent prompt
3. **Command building**: Time to build subprocess command
4. **Process spawn**: Time to spawn the `opencode run` subprocess
5. **First byte**: Time until first response byte from agent
6. **First text**: Time until first text output appears
7. **Response streaming**: Total time streaming response
8. **AI inference**: Calculated as (response time - first byte time)
9. **Total time**: End-to-end request time

---

## How to Test

### Step 1: Start AMI with Random Source

```bash
ami-local random://
```

### Step 2: Open Console and Enter Chat Mode

Click the **Console** button, then:

```python
>>> chat()
```

### Step 3: Make a Test Request

Try a simple request:

```
> create a scatter plot
```

### Step 4: Observe Timing Output

After the agent responds, you'll see timing breakdown like:

```
⏱️  Performance Timing:
  State request (timeout): 0.50s
  Prompt building:         0.003s
  Command building:        0.001s
  Process spawn:           0.234s
  Time to first byte:      1.245s
  Time to first text:      1.250s
  Response streaming:      10.52s
  AI inference time:       9.27s
  ─────────────────────────────────────
  TOTAL TIME:              12.45s
```

---

## Interpreting Results

### Scenario A: Process Spawn is High (>1s)

```
  Process spawn:           2.150s
  Time to first byte:      2.800s
  AI inference time:       8.500s
  TOTAL TIME:              11.50s
```

**Interpretation**: Subprocess overhead is significant (2.15s)

**Recommendation**: Switch to REST API - potential **2s savings** → **9.5s total**

---

### Scenario B: Process Spawn is Low (<500ms)

```
  Process spawn:           0.234s
  Time to first byte:      0.450s
  AI inference time:       11.20s
  TOTAL TIME:              12.10s
```

**Interpretation**: Process spawn is minimal (0.23s), AI inference dominates

**Recommendation**: 
- REST API would only save **~0.3s** → **11.8s total** (marginal)
- Focus on other optimizations:
  - Skill caching investigation
  - Reduce skill documentation
  - Improve UX (progress indicators)

---

### Scenario C: First Byte is Very High

```
  Process spawn:           0.234s
  Time to first byte:      8.500s
  AI inference time:       2.100s
  TOTAL TIME:              11.20s
```

**Interpretation**: Long delay before response starts (8.5s), fast inference after (2.1s)

**Likely cause**: Skill loading taking 8+ seconds

**Recommendation**: 
- Investigate server-side skill caching (potential **8s savings**!)
- Contact OpenCode team about caching strategy
- Or reduce skill documentation size

---

### Scenario D: State Request Timeout is Significant

```
  State request (timeout): 2.50s  ← High!
  Process spawn:           0.234s
  Time to first byte:      0.450s
  AI inference time:       8.20s
  TOTAL TIME:              12.10s
```

**Interpretation**: Graph state timeout is wasting 2.5s

**Recommendation**: Fix Comm async reception (already planned!) - saves **2s**

---

## Key Metrics to Look For

### 1. Process Spawn Time

**Good**: < 500ms  
**Concerning**: > 1s  
**Action if high**: Consider REST API

### 2. Time to First Byte

**Good**: < 1s  
**Concerning**: > 5s  
**Components**:
- Process spawn
- CLI init
- Server connection
- Skill loading
- Agent startup

**Action if high**: Investigate what's happening between spawn and first byte

### 3. AI Inference Time

This is: `Response streaming time - First byte time`

**Typical**: 8-11s for complex requests  
**Can't optimize much**: This is the AI model thinking  
**Options**:
- Use faster model (may reduce quality)
- Reduce prompt size
- Improve streaming UX (feels faster)

### 4. State Request Time

**Current**: 0.5s (wasted timeout)  
**After Comm fix**: < 0.1s  
**Savings**: ~0.4-0.5s

---

## Expected Baselines

Based on typical performance:

| Metric | Expected Range | Notes |
|--------|----------------|-------|
| State request | 0.5s | Timeout waste, will fix |
| Prompt building | < 0.01s | Should be instant |
| Command building | < 0.01s | Should be instant |
| Process spawn | 0.1-0.5s | System dependent |
| First byte | 0.5-2.0s | Includes skill loading |
| AI inference | 8-11s | Model processing time |
| **Total** | **9-14s** | Current baseline |

---

## Data Collection

Please run **3 test requests** and record the timing for each:

### Test 1: Simple Request
```
> create a scatter plot
```

**Timing**:
```
State request:    _____s
Process spawn:    _____s
First byte:       _____s
AI inference:     _____s
TOTAL:            _____s
```

### Test 2: Same Request Again (Cache Test)
```
> create a histogram
```

**Timing**:
```
State request:    _____s
Process spawn:    _____s
First byte:       _____s
AI inference:     _____s
TOTAL:            _____s
```

**Question**: Is Test 2 faster than Test 1? If yes, skill caching is working!

### Test 3: Complex Request
```
> create ROI on detector, sum it, and plot vs time
```

**Timing**:
```
State request:    _____s
Process spawn:    _____s
First byte:       _____s
AI inference:     _____s
TOTAL:            _____s
```

**Question**: Is AI inference longer for complex requests?

---

## Analysis After Testing

### Compare First vs Second Request

If **Test 2 is much faster than Test 1**:
- ✅ Skill caching is working
- Bottleneck is likely AI inference
- REST API won't help much
- Focus on UX improvements

If **Test 2 is about the same as Test 1**:
- ❌ Skill not being cached
- Investigate skill caching (big potential!)
- Could save 5-8 seconds

### Identify Bottleneck

1. **State request > 1s**: Fix Comm async (already planned)
2. **Process spawn > 1s**: Consider REST API
3. **First byte > 5s**: Investigate skill loading
4. **AI inference > 10s**: Can't optimize easily, focus on UX

---

## Next Steps Based on Results

### After collecting timing data:

1. **Share the results** - Post the timing breakdown from your tests

2. **We'll analyze** and decide priority:
   - Fix Comm async (already planned)
   - Investigate REST API (if process spawn is high)
   - Investigate skill caching (if first byte is high)
   - Reduce skill docs (if inference is high)
   - Improve UX (if nothing else helps)

3. **Create optimization plan** based on data

---

## Removing Timing Code Later

Once we've identified bottlenecks and optimized, we can:

**Option A**: Remove timing code entirely (cleaner)

**Option B**: Keep behind a flag:
```python
DEBUG_TIMING = os.environ.get('AMI_DEBUG_TIMING', 'false').lower() == 'true'

if DEBUG_TIMING:
    # Print timing breakdown
```

**Option C**: Make it an optional chat command:
```
> timing on
> create scatter plot
⏱️ [timing breakdown shown]
> timing off
```

---

## Current Status

✅ **Timing instrumentation added** to:
- `ami/flowchart/Flowchart.py` lines 2075-2195 (approximately)

✅ **Ready to test**:
1. Start AMI
2. Open console
3. Type `chat()`
4. Make requests
5. Observe timing output

📊 **Waiting for**: Test results to identify bottlenecks

---

**Next**: Run the tests and share the timing results!
