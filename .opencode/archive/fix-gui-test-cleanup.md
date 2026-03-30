# Implementation Plan: Fix GUI Test Cleanup Issues

**Date:** 2026-03-25  
**Goal:** Fix Prometheus metrics duplication and QSocketNotifier warnings  
**Files to modify:** `ami/flowchart/Flowchart.py`

---

## Overview

Two cleanup issues need to be fixed in `Flowchart.close()`:
1. **Prometheus metrics** - Not being unregistered from global registry
2. **QSocketNotifiers** - Not being disabled before sockets are closed

Both fixes will be made in the same file, in logical order (notifiers first, then sockets).

---

## Change 1: Add Prometheus Metrics Cleanup to FlowchartCtrlWidget

### Location
`ami/flowchart/Flowchart.py` - Add new method to `FlowchartCtrlWidget` class (after line 1078)

### Code to Add

```python
def close(self):
    """Clean up resources including Prometheus metrics."""
    # Unregister Prometheus metrics from global registry
    # This allows new Flowchart instances to register metrics with the same name
    try:
        pc.REGISTRY.unregister(self.graph_info)
    except Exception:
        pass  # Already unregistered or never registered
    
    try:
        pc.REGISTRY.unregister(self.graph_version)
    except Exception:
        pass  # Already unregistered or never registered
```

### Why This Works
- Prometheus `REGISTRY.unregister()` removes metrics from global registry
- Subsequent Flowchart instances can register metrics with same names
- Wrapped in try/except to handle edge cases gracefully
- This is called from `Flowchart.close()` during cleanup

---

## Change 2: Add QSocketNotifier Cleanup to Flowchart

### Location
`ami/flowchart/Flowchart.py` - Modify `Flowchart.close()` method (line 273)

### Current Code (lines 273-278)
```python
def close(self):
    for sock in self.socks:
        sock.close(linger=0)
    if self._widget is not None:
        self._widget.graphCommHandler.close()
    self.ctx.term()
```

### New Code
```python
def close(self):
    # STEP 1: Disable and delete QSocketNotifiers BEFORE closing sockets
    # This prevents Qt from trying to poll closed file descriptors
    if self._graphinfo_notifier is not None:
        self._graphinfo_notifier.setEnabled(False)
        self._graphinfo_notifier.deleteLater()
        self._graphinfo_notifier = None
    
    if self._checkpoint_notifier is not None:
        self._checkpoint_notifier.setEnabled(False)
        self._checkpoint_notifier.deleteLater()
        self._checkpoint_notifier = None
    
    # STEP 2: Close ZMQ sockets (now safe - notifiers are disabled)
    for sock in self.socks:
        sock.close(linger=0)
    
    # STEP 3: Clean up widget resources (including Prometheus metrics)
    if self._widget is not None:
        self._widget.close()  # Call new close() method
        self._widget.graphCommHandler.close()
    
    # STEP 4: Terminate ZMQ context
    self.ctx.term()
```

### Why This Works
1. **Notifiers disabled first** - Prevents Qt from polling closed FDs
2. **deleteLater()** - Qt will clean up when safe
3. **References cleared** - Helps garbage collection
4. **Widget cleanup added** - Unregisters Prometheus metrics
5. **Order matters** - Notifiers → Sockets → Widget → Context

---

## Testing Plan

### Test 1: Individual Test Execution
```bash
pytest tests/test_gui.py::test_sources -v
pytest tests/test_gui.py::test_editor -v
```
**Expected:** Both pass ✓

### Test 2: Sequential Test Execution (Currently Fails)
```bash
pytest tests/test_gui.py::test_sources tests/test_gui.py::test_editor -v
```
**Expected:** Both pass ✓ (This currently fails - should pass after fix)

### Test 3: All GUI Tests
```bash
pytest tests/test_gui.py -v
```
**Expected:** All pass with no warnings ✓

### Test 4: Check for Warnings
```bash
pytest tests/test_gui.py -v 2>&1 | grep -i "qsocketnotifier\|duplicated"
```
**Expected:** No output (no warnings) ✓

---

## Validation Checklist

After implementation, verify:
- [ ] No "Duplicated timeseries" errors
- [ ] No "QSocketNotifier: Invalid socket" warnings  
- [ ] All GUI tests pass individually
- [ ] All GUI tests pass when run together
- [ ] No regression in GUI functionality (manual test if possible)

---

## Edge Cases Considered

### Edge Case 1: Widget Never Created
**Scenario:** `Flowchart.close()` called but `widget()` never called  
**Handling:** `if self._widget is not None:` check protects against this ✓

### Edge Case 2: Notifiers Not Set Up
**Scenario:** `close()` called before `initialize()`  
**Handling:** `if self._graphinfo_notifier is not None:` check protects ✓

### Edge Case 3: Multiple close() Calls
**Scenario:** `close()` called multiple times  
**Handling:** 
- Notifiers set to `None` after first call
- Try/except around `unregister()` handles already-unregistered metrics
- Socket close is idempotent (ZMQ handles it gracefully) ✓

### Edge Case 4: Exception During Cleanup
**Scenario:** Prometheus unregister fails  
**Handling:** Try/except ensures cleanup continues ✓

---

## Implementation Steps

1. **Add `FlowchartCtrlWidget.close()` method**
   - Location: After line 1078 in `FlowchartCtrlWidget` class
   - Add Prometheus cleanup code

2. **Modify `Flowchart.close()` method**
   - Location: Line 273
   - Add QSocketNotifier cleanup (before socket close)
   - Add widget.close() call (before graphCommHandler.close())

3. **Test changes**
   - Run individual tests
   - Run sequential tests
   - Run all GUI tests

4. **Verify no warnings**
   - Check for QSocketNotifier warnings
   - Check for Prometheus duplication errors

---

## Code Review Questions

Before implementation, please confirm:

1. **Cleanup order:** Is the order correct?
   - Notifiers → Sockets → Widget → Context ✓

2. **Exception handling:** Should we log exceptions from `unregister()`?
   - Current: Silent pass (user should decide)

3. **Testing:** Should we add a specific test for cleanup?
   - Current: Rely on existing tests (user should decide)

4. **Backwards compatibility:** Any concerns about calling `widget.close()`?
   - Should be safe - widget.close() is new, only called during teardown

---

## Alternative Approaches Considered

### Alternative 1: Separate CollectorRegistry per Flowchart
**Pros:** Complete isolation, no global state pollution  
**Cons:** More complex, requires passing registry to widget  
**Decision:** Not chosen - unregister is simpler

### Alternative 2: Use Python's atexit for cleanup
**Pros:** Automatic cleanup on exit  
**Cons:** Doesn't help with tests (tests don't exit), not tied to instance lifecycle  
**Decision:** Not chosen - explicit cleanup is better

### Alternative 3: Change fixture scope to module/session
**Pros:** Avoids creating multiple instances  
**Cons:** Breaks test isolation, state pollution between tests  
**Decision:** Not chosen - proper cleanup is better than shared state

---

## Summary

**Changes required:** 2 additions to 1 file  
**Lines added:** ~30 lines  
**Lines modified:** 1 method (Flowchart.close)  
**Risk level:** Low (only affects cleanup path)  
**Testing impact:** Fixes 1 failing test, removes warnings

The fixes are minimal, well-scoped, and address the root causes without changing any core functionality.
