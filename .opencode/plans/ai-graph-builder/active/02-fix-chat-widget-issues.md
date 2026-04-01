# Plan: Fix Chat Widget Issues

**Date:** April 1, 2026  
**Status:** Ready to implement  
**Estimated time:** 20-30 minutes

---

## Issues Found

### Issue 1: Agent text not showing in widget
The agent's conversational text is being printed to stdout instead of appearing in the chat widget.

**Evidence:** User reports seeing agent text in terminal, but not in the widget.

### Issue 2: `ensure_source` attribute error
Code execution fails with:
```
AttributeError: 'AmiCli' object has no attribute 'ensure_source'
```

**Root Cause:** The skill documentation tells the agent to use `amicli.ensure_source()`, but we're providing `ensure_source` as a standalone function in the namespace, not as a method on `amicli`.

---

## Root Cause Analysis

### Issue 1 Investigation

Looking at `_show_agent_text()` (lines 399-440):
- The method correctly extracts text from events
- It correctly appends to `agent_texts` list
- It correctly calls `self._append_output()` to display

**Hypothesis:** The agent might not be sending separate text events. All text might be embedded in the JSON code block itself.

Let me check what's actually in the response. The agent likely sends:
```json
{"type":"text","part":{"text":"```json\n{\"explanation\":\"...\",\"code\":\"...\"}\n```"}}
```

And the explanation is INSIDE the JSON, not in separate text events!

**Solution:** We need to also extract and display the `explanation`, `warnings`, and `next_steps` fields from the JSON code block.

### Issue 2 Investigation

The namespace setup (lines 473-482):
```python
namespace = {
    "amicli": self.ctrl.amicli,
    "ensure_source": lambda name: ensure_source(self.ctrl.amicli, name),
}
```

But the agent generates code like:
```python
amicli.ensure_source('cspad')  # This fails!
```

**The Problem:** 
- We provide `ensure_source` as a standalone function
- Agent expects it as `amicli.ensure_source()` method
- These don't match!

**Why this happens:**
- The skill (SKILL.md) documents it as `amicli.ensure_source()`
- The agent learns to use this API
- But AmiCli class doesn't actually have this method
- graph_builder.py provides ensure_source as standalone function

**Solutions:**
1. Add `ensure_source` as a method to AmiCli class (changes AmiCli)
2. Create a wrapper AmiCli in namespace with ensure_source method
3. Update skill docs to use standalone `ensure_source()` (breaks existing code)

**Best Solution:** Option 2 - Create an enhanced AmiCli wrapper in the namespace.

---

## Solution Plan

### Fix 1: Show Explanation/Warnings from JSON Response

**File:** `ami/flowchart/chat_widget.py`

**Location:** In `_extract_code()` method, after extracting code (around line 357)

**Current code:**
```python
# Extract code from response
if "code" in response:
    code = response["code"]
    
    codes.append(code)
    
    # Only process the first (most recent) JSON block found
    if codes:
        return codes
```

**Change to:**
```python
# Extract code from response
if "code" in response:
    code = response["code"]
    
    # Show explanation if provided
    if "explanation" in response:
        self._append_output(f"Agent: {response['explanation']}")
        self._append_output("")
    
    # Show warnings if provided
    if "warnings" in response:
        for warning in response["warnings"]:
            self._append_output(f"⚠️  {warning}")
        self._append_output("")
    
    codes.append(code)
    
    # Only process the first (most recent) JSON block found
    if codes:
        return codes
```

**Reasoning:** The explanation and warnings ARE the agent's conversational text, just embedded in the JSON structure rather than separate text events.

### Fix 2: Add `ensure_source` Method to AmiCli Namespace

**File:** `ami/flowchart/chat_widget.py`

**Location:** In `_execute_code()` method, namespace setup (around lines 473-482)

**Current code:**
```python
namespace = {
    "chart": self.ctrl.chart,
    "graph": self.ctrl.chart._graph,
    "amicli": self.ctrl.amicli if hasattr(self.ctrl, "amicli") else None,
    "ensure_source": lambda name: ensure_source(
        self.ctrl.amicli if hasattr(self.ctrl, "amicli") else None, name
    ),
    "np": np,
    "pg": pg,
}
```

**Change to:**
```python
# Build execution namespace
from ami.flowchart.graph_builder import ensure_source
import numpy as np
import pyqtgraph as pg

# Create enhanced AmiCli wrapper with helper methods
class AmiCliWrapper:
    """Wrapper around AmiCli that adds helper methods for code execution."""
    
    def __init__(self, amicli):
        self._amicli = amicli
    
    def __getattr__(self, name):
        # Delegate all attributes to the wrapped amicli
        return getattr(self._amicli, name)
    
    def ensure_source(self, source_name):
        """Ensure source exists in graph (wrapper for standalone function)."""
        return ensure_source(self._amicli, source_name)

# Wrap amicli to add helper methods
amicli_wrapped = AmiCliWrapper(self.ctrl.amicli) if hasattr(self.ctrl, "amicli") else None

namespace = {
    "chart": self.ctrl.chart,
    "graph": self.ctrl.chart._graph,
    "amicli": amicli_wrapped,  # Use wrapped version
    "ensure_source": lambda name: ensure_source(
        self.ctrl.amicli if hasattr(self.ctrl, "amicli") else None, name
    ),  # Keep for backward compatibility
    "np": np,
    "pg": pg,
}
```

**Reasoning:** 
- Creates a wrapper that delegates all normal attributes to the real AmiCli
- Adds `ensure_source()` as a method that calls the standalone function
- Agent's code `amicli.ensure_source('cspad')` now works
- Keeps standalone `ensure_source()` for backward compatibility

**Alternative (Simpler):** Just monkey-patch the method onto the amicli instance:

```python
# Add ensure_source as method to amicli instance
if hasattr(self.ctrl, "amicli") and self.ctrl.amicli is not None:
    # Bind ensure_source to amicli for this execution
    amicli = self.ctrl.amicli
    amicli.ensure_source = lambda source_name: ensure_source(amicli, source_name)
else:
    amicli = None

namespace = {
    "chart": self.ctrl.chart,
    "graph": self.ctrl.chart._graph,
    "amicli": amicli,
    "ensure_source": lambda name: ensure_source(amicli, name),
    "np": np,
    "pg": pg,
}
```

**Preferred:** Use the simpler monkey-patch approach (cleaner, less code).

---

## Implementation Steps

### Step 1: Fix Agent Text Display

In `ami/flowchart/chat_widget.py`, in the `_extract_code()` method around line 357:

**Before:**
```python
if "code" in response:
    code = response["code"]
    codes.append(code)
```

**After:**
```python
if "code" in response:
    code = response["code"]
    
    # Show explanation if provided
    if "explanation" in response:
        self._append_output(f"Agent: {response['explanation']}")
        self._append_output("")
    
    # Show warnings if provided
    if "warnings" in response:
        for warning in response["warnings"]:
            self._append_output(f"⚠️  {warning}")
        self._append_output("")
    
    codes.append(code)
```

### Step 2: Fix ensure_source Method

In `ami/flowchart/chat_widget.py`, in the `_execute_code()` method around lines 467-482:

**Replace entire namespace setup with:**
```python
# Build execution namespace
# self.ctrl is FlowchartCtrlWidget, which has .chart (Flowchart) and .amicli
from ami.flowchart.graph_builder import ensure_source
import numpy as np
import pyqtgraph as pg

# Add ensure_source as method to amicli instance for this execution
if hasattr(self.ctrl, "amicli") and self.ctrl.amicli is not None:
    amicli = self.ctrl.amicli
    # Bind ensure_source to amicli so agent can call amicli.ensure_source()
    amicli.ensure_source = lambda source_name: ensure_source(amicli, source_name)
else:
    amicli = None

namespace = {
    "chart": self.ctrl.chart,
    "graph": self.ctrl.chart._graph,
    "amicli": amicli,
    "ensure_source": lambda name: ensure_source(amicli, name),  # Backward compat
    "np": np,
    "pg": pg,
}

exec(code, namespace)
```

---

## Testing

After implementation:

### Test 1: Agent Text Display
**Input:** "show me image sources"

**Expected Output:**
```
You: show me image sources

[System] Sending request to agent...
[System] Response received, processing...

Agent: I'll create the cspad image source for you to view detector data

⚠️  Make sure to click on the cspad node to open the detector viewer

[System] Found 1 code block(s)

--- Generated Code 1 ---
<code>
--- End Code ---

[System] Executing code...
[System] ✅ Execution successful!
```

### Test 2: ensure_source Execution
**Input:** "create cspad source"

**Expected:** Code executes successfully without AttributeError

**Verify:** 
1. No error messages
2. cspad source node appears in graph
3. Chat shows "✅ Execution successful!"

---

## Files Modified

- `ami/flowchart/chat_widget.py`
  - Add explanation/warnings display in `_extract_code()` (~8 lines)
  - Update namespace setup in `_execute_code()` (~12 lines changed)
  - **Net change:** ~20 lines

---

## Rollback Plan

If issues persist:
```bash
git diff ami/flowchart/chat_widget.py  # Review changes
git checkout HEAD -- ami/flowchart/chat_widget.py  # Revert if needed
```

---

## Risk Assessment

**Low Risk Changes:**
- Both fixes are isolated to chat_widget.py
- No changes to core AMI functionality
- Execution namespace is local to each code execution
- Monkey-patching is temporary (per execution)

**Potential Issues:**
- If amicli is None, ensure_source will fail (already handled)
- Monkey-patching might affect other code (unlikely - namespace is local)

---

## Estimated Time

- Implementation: 15 minutes
- Testing: 10-15 minutes
- **Total: 25-30 minutes**

---

## Approval Status

**Issues identified:** ✅ Yes (2 issues)  
**Root causes found:** ✅ Yes  
**Solutions designed:** ✅ Yes  
**Ready to implement:** ✅ Yes

---

**Ready for implementation!**
