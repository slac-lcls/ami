# GUI Test Failures - Fix Summary

**Date:** 2026-03-25  
**Status:** ✅ FIXED - All tests passing  
**Branch:** debug

---

## Problem Summary

After removing asyncio from the flowchart GUI, tests were failing when run in sequence:
- ✅ `test_editor` PASSED when run alone
- ❌ `test_editor` FAILED when run after `test_sources`
- Error: `TypeError: cannot unpack non-iterable NoneType object`
- Root cause: `ValueError: Duplicated timeseries in CollectorRegistry`

Additionally, QSocketNotifier warnings appeared during cleanup:
- `QtWarningMsg: QSocketNotifier: Invalid socket 73 and type 'Read', disabling...`

---

## Root Causes Identified

### Issue 1: Prometheus Metrics Duplication
- **Problem:** Prometheus metrics registered in global registry but never unregistered
- **Impact:** Second test fixture creation failed with "Duplicated timeseries" error
- **Location:** `FlowchartCtrlWidget.__init__()` creates `ami_graph` and `ami_graph_version` metrics

### Issue 2: QSocketNotifier Invalid Socket Warnings
- **Problem:** ZMQ sockets closed before QSocketNotifiers disabled
- **Impact:** Qt tried to poll closed file descriptors, causing warnings
- **Location:** `Flowchart.close()` closed sockets without disabling notifiers

---

## Solution Implemented

### Change 1: Added `FlowchartCtrlWidget.close()` Method

**Location:** `ami/flowchart/Flowchart.py` (after line 1095)

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

**Why:** Removes metrics from global Prometheus registry, allowing new Flowchart instances to register metrics with the same name.

### Change 2: Enhanced `Flowchart.close()` Method

**Location:** `ami/flowchart/Flowchart.py` (line 273)

Added proper cleanup order:
1. **Disable QSocketNotifiers** - Prevents Qt from polling closed file descriptors
2. **Close ZMQ sockets** - Safe now that notifiers are disabled
3. **Call widget.close()** - Cleans up Prometheus metrics
4. **Terminate ZMQ context** - Final cleanup

```python
def close(self):
    # STEP 1: Disable and delete QSocketNotifiers BEFORE closing sockets
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

**Why:** Proper cleanup order prevents Qt warnings and ensures all resources are released.

---

## Changes Summary

**File Modified:** `ami/flowchart/Flowchart.py`
- **Lines added:** 32 lines
- **Methods added:** 1 (`FlowchartCtrlWidget.close()`)
- **Methods modified:** 1 (`Flowchart.close()`)

---

## Test Results

### Before Fix
```bash
$ pytest tests/test_gui.py -v
tests/test_gui.py::test_broker_sub PASSED                    [ 33%]
tests/test_gui.py::test_sources[static] PASSED               [ 66%]
tests/test_gui.py::test_editor[static] FAILED                [100%]

Errors:
- Duplicated timeseries in CollectorRegistry: {'ami_graph_info', 'ami_graph'}
- QSocketNotifier: Invalid socket 73 and type 'Read', disabling...
```

### After Fix
```bash
$ pytest tests/test_gui.py -v
tests/test_gui.py::test_broker_sub PASSED                    [ 33%]
tests/test_gui.py::test_sources[static] PASSED               [ 66%]
tests/test_gui.py::test_editor[static] PASSED                [100%]

========================= 3 passed, 1 warning in 15.90s =========================
```

✅ **All tests passing**  
✅ **No Prometheus duplication errors**  
✅ **No QSocketNotifier warnings**

---

## Key Insights

1. **Asyncio removal was correct** - The issues were not related to the asyncio refactor itself, but to missing cleanup code for the new QSocketNotifier implementation.

2. **Global state cleanup matters** - Prometheus metrics in the global registry must be unregistered when instances are destroyed to allow new instances.

3. **Cleanup order is critical** - Notifiers must be disabled before closing the underlying file descriptors to prevent Qt warnings.

4. **Test isolation works** - With proper cleanup, function-scoped fixtures provide good test isolation without changing fixture scope.

---

## Validation

- [x] Individual tests pass
- [x] Sequential tests pass (previously failed)
- [x] All GUI tests pass
- [x] No Prometheus duplication errors
- [x] No QSocketNotifier warnings
- [x] No regression in functionality

---

## Next Steps

Optional improvements (not required for fix):
- [ ] Consider adding explicit cleanup test
- [ ] Review other components for similar cleanup issues
- [ ] Document cleanup patterns for future development

---

## Related Files

- Implementation plan: `.opencode/plans/fix-gui-test-cleanup.md`
- Analysis document: `.opencode/plans/gui-test-failures-analysis.md`
- Asyncio removal plan: `.opencode/plans/asyncio-removal-plan.md`
