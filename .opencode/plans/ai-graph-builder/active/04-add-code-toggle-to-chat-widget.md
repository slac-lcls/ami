# Plan: Add Code Display Toggle to Chat Widget

**Date:** April 1, 2026  
**Status:** Ready for approval  
**Estimated time:** 20-30 minutes

---

## Goal

Add a checkbox/toggle to the chat widget that allows users to hide/show the generated code blocks. By default, users will only see:
- Agent's conversational text
- Execution status
- Results

Power users can enable the toggle to also see the generated code.

---

## User Experience

### Default (Code Hidden):
```
You: create a scatter plot

[System] Sending request to agent...
[System] Response received, processing...

Agent:
I'll create a scatter plot to visualize the correlation between laser and detector signals.

[System] ✅ Execution successful!
```

### With Code Shown (Toggle Enabled):
```
You: create a scatter plot

[System] Sending request to agent...
[System] Response received, processing...

Agent:
I'll create a scatter plot to visualize the correlation between laser and detector signals.

--- Generated Code 1 ---
scatter = amicli.create_node('ScatterPlot', 'Laser vs Detector')
amicli.connect_nodes('laser', 'Out', scatter.name(), 'X')
amicli.connect_nodes('detector', 'Out', scatter.name(), 'Y')
--- End Code ---

[System] Executing code...
[System] ✅ Execution successful!
```

---

## Design

### UI Addition

Add a checkbox to the chat widget UI (bottom of output area, above input field):

```
┌─────────────────────────────────────┐
│ AMI Chat - Natural Language      [X]│
├─────────────────────────────────────┤
│ QTextEdit (conversation history)    │
│ - User: create scatter plot         │
│ - Agent: I'll create that...        │
│ - [Executed successfully]           │
│                                      │
├─────────────────────────────────────┤
│ ☑ Show generated code               │  ← NEW CHECKBOX
├─────────────────────────────────────┤
│ You: [QLineEdit]               Send │
└─────────────────────────────────────┘
```

### State Management

- **Instance variable:** `self.show_code = False` (default hidden)
- **Checkbox signal:** Toggle `self.show_code` on click
- **Persistent across messages:** Once toggled, stays in that state

---

## Implementation

### File: `ami/flowchart/chat_widget.py`

### Step 1: Add UI Checkbox

In `_setup_ui()` method, after creating the output text area, before the input layout:

```python
def _setup_ui(self):
    # ... existing code ...
    
    # Output area (conversation history)
    self.output_text = QTextEdit()
    self.output_text.setReadOnly(True)
    # ... existing setup ...
    layout.addWidget(self.output_text)
    
    # NEW: Code display toggle
    self.show_code_checkbox = QCheckBox("Show generated code")
    self.show_code_checkbox.setChecked(False)  # Default: hide code
    self.show_code_checkbox.setToolTip(
        "Show/hide the generated Python code in chat responses"
    )
    layout.addWidget(self.show_code_checkbox)
    
    # Input area (existing)
    input_layout = QHBoxLayout()
    # ... rest of input setup ...
```

### Step 2: Add State Variable

In `__init__()` method:

```python
def __init__(self, ctrl, parent=None):
    super().__init__(parent)
    self.ctrl = ctrl
    self.bridge = None
    self.command_history = []
    self.history_index = -1
    self.current_worker = None
    self.show_code = False  # NEW: Default hide code
    
    self._setup_ui()
    self._connect_signals()
    self._init_bridge()
```

### Step 3: Connect Checkbox Signal

In `_connect_signals()` method:

```python
def _connect_signals(self):
    # Input submission
    self.input_field.returnPressed.connect(self._on_submit)
    self.send_button.clicked.connect(self._on_submit)
    
    # NEW: Code display toggle
    self.show_code_checkbox.stateChanged.connect(self._on_code_toggle)
    
    # Code execution signal
    self.execute_code_signal.connect(self._execute_code_slot)
```

### Step 4: Add Toggle Handler

New method:

```python
def _on_code_toggle(self, state):
    """Handle code display checkbox toggle."""
    from qtpy.QtCore import Qt
    self.show_code = (state == Qt.Checked)
```

### Step 5: Conditionally Display Code

In `_on_response_received()` method, wrap code display in conditional:

**Current:**
```python
if codes:
    self._append_output(f"[System] Found {len(codes)} code block(s)")
    self._append_output("")

    # Display and execute each code block
    for i, code in enumerate(codes, 1):
        self._append_output(f"--- Generated Code {i} ---")
        self._append_output(code)
        self._append_output("--- End Code ---")
        self._append_output("")

        # Auto-execute (emit signal for thread-safe execution)
        self.execute_code_signal.emit(code)
```

**New:**
```python
if codes:
    # Only show code if toggle is enabled
    if self.show_code:
        self._append_output(f"[System] Found {len(codes)} code block(s)")
        self._append_output("")

        # Display each code block
        for i, code in enumerate(codes, 1):
            self._append_output(f"--- Generated Code {i} ---")
            self._append_output(code)
            self._append_output("--- End Code ---")
            self._append_output("")
    
    # Always execute code (regardless of display toggle)
    for code in codes:
        self.execute_code_signal.emit(code)
```

**Key point:** Code execution happens ALWAYS, but display is conditional.

---

## Alternative: Settings Menu Approach

Instead of always-visible checkbox, add to a settings menu:

### Option A: Checkbox (Recommended)
- ✅ Always visible
- ✅ Easy to toggle
- ✅ Clear state
- ❌ Takes up space

### Option B: Menu Action
- ✅ Cleaner UI
- ✅ More professional
- ❌ Less discoverable
- ❌ More complex to implement

**Recommendation:** Use checkbox (Option A) - simpler, more discoverable.

---

## Enhanced Version: Show Code on Execution Errors

**Smart behavior:** Automatically show code when execution fails, even if toggle is off.

```python
def _execute_code(self, code):
    try:
        # ... execution code ...
        self._append_output("[System] ✅ Execution successful!")
    
    except Exception as e:
        # On error, show the code that failed (even if toggle is off)
        if not self.show_code:
            self._append_output("")
            self._append_output("--- Code that failed ---")
            self._append_output(code)
            self._append_output("--- End Code ---")
            self._append_output("")
        
        error_msg = f"[Execution Error] {e}\n{traceback.format_exc()}"
        self._append_output(error_msg)
```

**Rationale:** Users need to see what code failed to debug the issue.

---

## User Settings Persistence (Future Enhancement)

For now: In-memory only (resets when widget closes)

**Future:** Save preference to user config file:
```python
# On close
config = {"show_code": self.show_code}
with open(os.path.expanduser("~/.ami_chat_config.json"), "w") as f:
    json.dump(config, f)

# On init
try:
    with open(os.path.expanduser("~/.ami_chat_config.json"), "r") as f:
        config = json.load(f)
        self.show_code = config.get("show_code", False)
        self.show_code_checkbox.setChecked(self.show_code)
except FileNotFoundError:
    pass
```

**Not implementing now:** Keep it simple for MVP.

---

## Testing

### Test 1: Default Behavior (Code Hidden)
1. Open chat widget (Ctrl+Shift+C)
2. Type: "create a scatter plot"
3. Verify: See agent text and execution status
4. Verify: Do NOT see code block
5. Verify: Scatter plot node appears (code executed)

### Test 2: Toggle Enabled (Show Code)
1. Check "Show generated code" checkbox
2. Type: "create a histogram"
3. Verify: See agent text
4. Verify: See code block
5. Verify: See execution status
6. Verify: Histogram node appears

### Test 3: Toggle Persists
1. Enable "Show generated code"
2. Send message (code shown)
3. Send another message
4. Verify: Code still shown (toggle persists)

### Test 4: Error Shows Code (Enhanced Behavior)
1. Disable "Show generated code"
2. Send request that triggers execution error
3. Verify: Code automatically shown (for debugging)
4. Verify: Error message displayed

### Test 5: Multiple Code Blocks
1. Enable "Show generated code"
2. Send request that generates 2 code blocks
3. Verify: Both blocks shown
4. Disable toggle
5. Send same request
6. Verify: No code blocks shown, but both execute

---

## Files Modified

### Primary Changes:
- `ami/flowchart/chat_widget.py`
  - Add `show_code_checkbox` in `_setup_ui()` (~8 lines)
  - Add `self.show_code` state variable (~1 line)
  - Connect checkbox signal (~1 line)
  - Add `_on_code_toggle()` handler (~4 lines)
  - Wrap code display in conditional (~5 lines changed)
  - Optional: Show code on errors (~8 lines)
  - **Total: ~25-30 lines changed**

### Import Addition:
```python
from qtpy.QtWidgets import QCheckBox  # Add to existing imports
```

---

## Benefits

✅ **Cleaner chat** - Most users just want to see responses  
✅ **Still accessible** - Power users can enable code display  
✅ **Better UX** - Less clutter in conversation  
✅ **Debugging friendly** - Can show code when needed  
✅ **Simple implementation** - Just a checkbox and conditional  

---

## Risks

**Risk 1: Users don't realize code is executing**  
**Mitigation:** Execution status messages still shown ("✅ Execution successful!")

**Risk 2: Users can't debug without seeing code**  
**Mitigation:** 
- Easy toggle to enable
- Automatically show code on errors (enhanced behavior)

**Risk 3: Checkbox takes up space**  
**Mitigation:** Small checkbox, minimal footprint

---

## Implementation Order

1. Add checkbox to UI layout
2. Add state variable and signal connection
3. Add toggle handler
4. Wrap code display in conditional
5. Test with toggle on/off
6. Optional: Add smart error behavior

---

## Estimated Time

- UI addition: 5 minutes
- State management: 5 minutes
- Conditional display: 5 minutes
- Testing: 10 minutes
- Optional enhancements: 5 minutes
- **Total: 25-30 minutes**

---

## Design Questions

### Question 1: Default State
**Options:**
- A) Hidden (recommended) - cleaner for most users
- B) Shown - power users see code immediately

**Recommendation:** A (Hidden) - matches your preference

### Question 2: Error Behavior
**Options:**
- A) Always show code on errors (recommended)
- B) Respect toggle even on errors

**Recommendation:** A - helps debugging

### Question 3: Checkbox Label
**Options:**
- A) "Show generated code"
- B) "Show code"
- C) "Display code blocks"
- D) "Advanced: Show code"

**Recommendation:** A - clear and descriptive

### Question 4: Checkbox Position
**Options:**
- A) Between output and input (recommended)
- B) Top right corner of output area
- C) Bottom left corner

**Recommendation:** A - visible but not intrusive

---

## Approval Checklist

- [ ] User confirms: Default hide code
- [ ] User confirms: Checkbox in UI (vs menu)
- [ ] User confirms: Show code on errors (smart behavior)
- [ ] Ready to implement

---

**Status:** Awaiting user approval to proceed

---

## Integration with Other Plans

This plan works alongside:
- ✅ `fix-chat-widget-issues.md` - Fix agent text and ensure_source
- ✅ `update-skill-for-chat-mode.md` - Update skill documentation

**No conflicts** - this is a pure UI enhancement.

---

**Recommendation:** Implement this AFTER fixing the two chat widget issues, so we have a working baseline to enhance.
