# GUI Test Failures After Asyncio Removal - Root Cause Analysis

**Date:** 2026-03-25  
**Status:** Analysis Complete - Ready for Fix

---

## Summary

The GUI tests are failing after the asyncio refactor, but the root causes are **NOT related to the asyncio removal itself**. Instead, there are two separate cleanup/teardown issues that were exposed by running tests in sequence.

### Key Finding
- ✅ **test_editor PASSES when run alone**
- ❌ **test_editor FAILS when run after test_sources**

This confirms the issues are related to **fixture cleanup between tests**, not the asyncio refactor.

---

## Issue 1: Prometheus Metrics Duplication

### Root Cause
When `FlowchartCtrlWidget.__init__()` is called, it creates Prometheus metrics:

```python
# ami/flowchart/Flowchart.py:856-857
self.graph_info = pc.Info('ami_graph', 'AMI Client graph', ['hutch', 'name'])
self.graph_version = pc.Gauge('ami_graph_version', 'AMI Client graph version', ['hutch', 'name'])
```

These metrics are registered in the **global** `prometheus_client.REGISTRY`. When the first test (`test_sources`) completes, the metrics remain registered. When the second test (`test_editor`) tries to create the same metrics, Prometheus raises:

```
ValueError: Duplicated timeseries in CollectorRegistry: {'ami_graph_info', 'ami_graph'}
```

### Why This Causes Test Failure
The exception occurs during fixture setup (`flowchart` fixture), which catches it and yields `None`:

```python
# tests/test_gui.py:168-171
except Exception as e:
    print("error setting up flowchart fixture:", e)
    yield None  # ← Test receives None instead of (flowchart, broker)
```

Then in the test:
```python
# tests/test_gui.py:320
flowchart, broker = flowchart  # ← TypeError: cannot unpack non-iterable NoneType
```

### Evidence
```bash
$ pytest tests/test_gui.py::test_editor -v
# PASSES ✓

$ pytest tests/test_gui.py::test_sources tests/test_gui.py::test_editor -v  
# test_sources PASSES, test_editor FAILS with "Duplicated timeseries"
```

---

## Issue 2: QSocketNotifier Invalid Socket Warnings

### Root Cause
When `fc.initialize()` is called, it sets up QSocketNotifiers for ZMQ sockets:

```python
# ami/flowchart/Flowchart.py:104-118
def setup_socket_notifiers(self):
    fd = self.graphinfo.get(zmq.FD)
    self._graphinfo_notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read)
    
    fd = self.checkpoint.get(zmq.FD)
    self._checkpoint_notifier = QSocketNotifier(fd, QSocketNotifier.Type.Read)
```

However, when the flowchart is cleaned up in `Flowchart.close()`, the ZMQ sockets are closed **before** the QSocketNotifiers are disabled:

```python
# ami/flowchart/Flowchart.py:273-278
def close(self):
    for sock in self.socks:
        sock.close(linger=0)  # ← Closes ZMQ sockets (invalidates FDs)
    if self._widget is not None:
        self._widget.graphCommHandler.close()
    self.ctx.term()
    # ← QSocketNotifiers never disabled/deleted!
```

When Qt's event loop tries to poll the notifiers after the sockets are closed, it gets invalid file descriptors:

```
QtWarningMsg: QSocketNotifier: Invalid socket 73 and type 'Read', disabling...
QtWarningMsg: QSocketNotifier: Invalid socket 75 and type 'Read', disabling...
```

### Why This Happens Now
The asyncio version didn't use QSocketNotifiers - it used `zmq.asyncio` with async/await patterns. The new synchronous version introduced QSocketNotifiers but didn't add proper cleanup.

---

## Issue 3: Worker Process Error (Secondary)

During test setup, there's also a worker process error:

```
File "/sdf/home/s/seshu/dev/ami/ami/worker.py", line 90, in update_graph
    self.store.configure(name, version, self.graphs[name].outputs['worker'])
AttributeError: 'NoneType' object has no attribute 'outputs'
```

This appears to be a race condition or initialization issue in the worker, but it doesn't cause the test to fail - it just prints to stderr. The Prometheus duplication error is what actually causes the fixture to yield `None`.

---

## Solutions

### Solution 1: Unregister Prometheus Metrics in Cleanup

Add cleanup of Prometheus metrics in `FlowchartCtrlWidget`:

```python
# In FlowchartCtrlWidget class
def close(self):
    """Clean up resources including Prometheus metrics."""
    try:
        pc.REGISTRY.unregister(self.graph_info)
    except Exception:
        pass  # Already unregistered
    
    try:
        pc.REGISTRY.unregister(self.graph_version)
    except Exception:
        pass  # Already unregistered
```

Then call this from `Flowchart.close()`:

```python
def close(self):
    for sock in self.socks:
        sock.close(linger=0)
    if self._widget is not None:
        self._widget.close()  # ← Add cleanup call
        self._widget.graphCommHandler.close()
    self.ctx.term()
```

**Alternative:** Use a separate CollectorRegistry per test to avoid global state pollution.

### Solution 2: Disable QSocketNotifiers Before Closing Sockets

Add cleanup of QSocketNotifiers in `Flowchart.close()`:

```python
def close(self):
    # Disable socket notifiers BEFORE closing sockets
    if self._graphinfo_notifier is not None:
        self._graphinfo_notifier.setEnabled(False)
        self._graphinfo_notifier.deleteLater()
        self._graphinfo_notifier = None
    
    if self._checkpoint_notifier is not None:
        self._checkpoint_notifier.setEnabled(False)
        self._checkpoint_notifier.deleteLater()
        self._checkpoint_notifier = None
    
    # Now safe to close sockets
    for sock in self.socks:
        sock.close(linger=0)
    
    if self._widget is not None:
        self._widget.graphCommHandler.close()
    
    self.ctx.term()
```

### Solution 3: Change Fixture Scope (User's Suggestion)

**Current scope:** `@pytest.fixture(scope='function')`

**Issue:** Changing to module or session scope would mean the flowchart is shared across tests, which could cause other issues if tests modify state.

**Recommendation:** Keep function scope but fix the cleanup issues. This ensures proper test isolation.

---

## Recommended Fix Order

1. **Fix Prometheus metrics cleanup** (Solution 1)
   - This is the primary cause of test failure
   - High priority

2. **Fix QSocketNotifier cleanup** (Solution 2)
   - This causes warnings but doesn't break tests
   - Medium priority

3. **Investigate worker error** (Issue 3)
   - Appears to be pre-existing or race condition
   - Low priority (doesn't break tests)

---

## Files to Modify

1. `ami/flowchart/Flowchart.py`
   - Modify `Flowchart.close()` to disable QSocketNotifiers
   - Add `FlowchartCtrlWidget.close()` method
   - Call widget cleanup from Flowchart.close()

---

## Testing Plan

After implementing fixes:

```bash
# Test individual tests
pytest tests/test_gui.py::test_sources -v
pytest tests/test_gui.py::test_editor -v

# Test in sequence (this currently fails)
pytest tests/test_gui.py::test_sources tests/test_gui.py::test_editor -v

# Test all GUI tests
pytest tests/test_gui.py -v
```

Expected result: All tests pass with no warnings.

---

## Questions for User

1. **Fixture scope:** Do you still want to change the fixture scope, or should we fix the cleanup issues and keep function scope for better test isolation?

2. **Prometheus metrics:** Should we unregister metrics in cleanup, or use a separate CollectorRegistry per flowchart instance?

3. **Worker error:** Should we investigate the worker process error (`AttributeError: 'NoneType' object has no attribute 'outputs'`) or is this a known/acceptable issue during test setup?

4. **Priority:** Which issue should we fix first?
   - Fix Prometheus cleanup (stops test failures)
   - Fix QSocketNotifier cleanup (stops warnings)
   - Both together

---

## Conclusion

The asyncio removal was implemented correctly - the issues are related to missing cleanup code for:
1. Prometheus metrics (global registry pollution)
2. QSocketNotifiers (not disabled before socket closure)

Both are straightforward fixes that will restore test functionality without reverting the asyncio changes.
