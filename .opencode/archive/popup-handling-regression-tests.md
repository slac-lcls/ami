# Plan: Implement Strict Popup Handling in AMI GUI Regression Tests

**Date:** 2026-03-25  
**Status:** Ready for Implementation  
**Goal:** Implement popup tracking and verification system that fails tests by default if unexpected QMessageBox appears  

---

## Executive Summary

Implement a comprehensive popup handling system for AMI GUI regression tests that:
- **Fails tests by default** if any QMessageBox popup appears (strict mode)
- **Tracks popup details** (text, type) for verification when expected
- **Updates ALL existing tests** to explicitly handle popup expectations
- **Investigates and fixes** the ATM_crix_new.fc Filter node issue
- **Deletes obsolete** test_asyncqt.py that blocks test collection

---

## Background

### Current State

**Popup Locations in Production Code:**
- `Flowchart.py:720` - File not found error → `msg.exec()` (blocking)
- `Flowchart.py:972, 977` - Disconnected nodes / Failed graph submission → `msg.exec()` (blocking)
- `Flowchart.py:1320` - Pending changes warning → `msg.show()` (non-blocking)
- `library/Alert.py:45` - Alert node threshold → `msg.exec_()` (blocking with custom buttons)
- `Node.py:776` - Node-level errors → `msg.exec()` (blocking)
- `Terminal.py:389` - Terminal connection errors → `msg.exec()` (blocking)

**Current Test Environment:**
- ✅ CI uses `xvfb-run pytest` (both workflows)
- ✅ Tests use `--headless` flag
- ✅ DISPLAY is set on development machine
- ❌ No popup suppression currently implemented
- ⚠️ Tests avoid triggering popups through careful design (fragile)

**Problems:**
1. **Modal dialogs block tests** - `QMessageBox.exec()` blocks event loop even with xvfb
2. **Silent failures** - Tests pass even when unexpected popups appear
3. **Unclear expectations** - No explicit verification of popup behavior
4. **Blocking test collection** - Obsolete `test_asyncqt.py` prevents tests from running

### Why Not Just xvfb-run?

**Critical insight:** `xvfb-run` creates a virtual X11 server but **does NOT prevent modal dialogs from blocking**:
- Virtual display renders GUI normally
- `QMessageBox.exec()` STILL blocks waiting for user input
- Tests hang indefinitely
- AMI CI works because tests are designed to avoid triggering popups

**Solution:** Monkeypatch QMessageBox to:
- Track popup details
- Prevent blocking
- Fail tests if unexpected
- Allow verification when expected

---

## Goals

1. ✅ Make tests fail if unexpected popup appears
2. ✅ Allow popups when explicitly expected  
3. ✅ Track popup details for verification
4. ✅ Update all 6 existing GUI tests
5. ✅ Fix or document ATM_crix_new.fc issue
6. ✅ Delete obsolete test_asyncqt.py

---

## Implementation Plan

### Phase 1: Create Popup Tracking Infrastructure

**File:** `tests/conftest.py`

**Add PopupTracker class and fixture:**

```python
import pytest
from qtpy import QtWidgets

class PopupTracker:
    """Track and verify QMessageBox popups during tests."""
    
    def __init__(self):
        self.popups = []
        self.strict_mode = True  # Fail on unexpected popups by default
    
    def record_popup(self, text='', informative_text='', icon=None):
        """Record a popup that was shown."""
        self.popups.append({
            'text': text,
            'informative_text': informative_text,
            'icon': icon,
        })
    
    def assert_no_popups(self):
        """Assert no popups were shown."""
        if self.popups:
            texts = [p['text'] for p in self.popups]
            pytest.fail(f"Unexpected popup(s) shown: {texts}")
    
    def assert_popup_shown(self, expected_text=None):
        """Assert a popup was shown, optionally matching text."""
        if not self.popups:
            pytest.fail("Expected popup but none was shown")
        
        if expected_text:
            texts = [p['text'] for p in self.popups]
            matches = [expected_text in text for text in texts]
            if not any(matches):
                pytest.fail(f"Expected popup containing '{expected_text}' but got: {texts}")
    
    def clear(self):
        """Clear popup history."""
        self.popups.clear()
    
    def allow_popups(self):
        """Disable strict mode for this test."""
        self.strict_mode = False


@pytest.fixture(autouse=True)
def popup_tracker(monkeypatch, request):
    """
    Automatically track and suppress QMessageBox popups in all tests.
    
    By default, tests FAIL if any popup appears (strict mode).
    
    Usage:
        # Test expects no popups (default)
        def test_something(popup_tracker):
            # ... test code ...
            popup_tracker.assert_no_popups()  # Optional, auto-checked
        
        # Test expects popup
        @pytest.mark.expect_popup
        def test_error(popup_tracker):
            popup_tracker.allow_popups()
            # ... trigger error ...
            popup_tracker.assert_popup_shown("expected message")
        
        # Allow real dialogs (use with xvfb-run)
        @pytest.mark.allow_dialogs
        def test_real_dialog():
            # popup_tracker not active
    """
    # Skip if test explicitly allows real dialogs
    if 'allow_dialogs' in request.keywords:
        return None
    
    tracker = PopupTracker()
    
    # Check if test is marked to expect popups
    if 'expect_popup' in request.keywords:
        tracker.allow_popups()
    
    # Store original methods
    original_init = QtWidgets.QMessageBox.__init__
    
    # Track popup state on instance
    def tracked_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._popup_text = ''
        self._popup_informative_text = ''
        self._popup_icon = None
    
    def tracked_setText(self, text):
        self._popup_text = text
        # Don't call original - we're mocking
    
    def tracked_setInformativeText(self, text):
        self._popup_informative_text = text
    
    def tracked_setIcon(self, icon):
        self._popup_icon = icon
    
    def tracked_text(self):
        return getattr(self, '_popup_text', '')
    
    def tracked_informativeText(self):
        return getattr(self, '_popup_informative_text', '')
    
    def tracked_exec(self):
        # Record popup
        tracker.record_popup(
            text=getattr(self, '_popup_text', ''),
            informative_text=getattr(self, '_popup_informative_text', ''),
            icon=getattr(self, '_popup_icon', None)
        )
        
        # Fail immediately if in strict mode
        if tracker.strict_mode:
            pytest.fail(f"Unexpected QMessageBox popup: {self._popup_text}")
        
        # Return default button
        return QtWidgets.QMessageBox.Ok
    
    # Apply monkeypatches
    monkeypatch.setattr(QtWidgets.QMessageBox, '__init__', tracked_init)
    monkeypatch.setattr(QtWidgets.QMessageBox, 'setText', tracked_setText)
    monkeypatch.setattr(QtWidgets.QMessageBox, 'setInformativeText', tracked_setInformativeText)
    monkeypatch.setattr(QtWidgets.QMessageBox, 'setIcon', tracked_setIcon)
    monkeypatch.setattr(QtWidgets.QMessageBox, 'text', tracked_text)
    monkeypatch.setattr(QtWidgets.QMessageBox, 'informativeText', tracked_informativeText)
    monkeypatch.setattr(QtWidgets.QMessageBox, 'exec', tracked_exec)
    monkeypatch.setattr(QtWidgets.QMessageBox, 'exec_', tracked_exec)
    
    yield tracker
```

**Estimated effort:** 1-2 hours

---

### Phase 2: Update Existing Tests

**File:** `tests/test_gui.py`

**Tests to Update:** 6 tests

#### Test 1: `test_broker_sub` (line 448)
✅ No popups expected - add strict verification

```python
def test_broker_sub(broker, popup_tracker):
    # ... existing test code ...
    
    # Add at end:
    popup_tracker.assert_no_popups()
```

#### Test 2: `test_sources` (line 485)
✅ No popups expected - add strict verification

```python
@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
def test_sources(qtbot, flowchart, popup_tracker):
    # ... existing test code ...
    
    # Add at end:
    popup_tracker.assert_no_popups()
```

#### Test 3: `test_editor` (line 514)
✅ No popups expected - add strict verification

```python
@pytest.mark.parametrize('flowchart', ['static'], indirect=True)
def test_editor(qtbot, flowchart, tmp_path, popup_tracker):
    # ... existing test code ...
    
    # Add at end:
    popup_tracker.assert_no_popups()
```

#### Test 4: `test_load_atm_crix` (line 590) ⚠️ **NEEDS INVESTIGATION**

**Issue:** Comment says "causes 'Failed to submit graph' popup" but test currently passes

**Root Cause:** 
- Filter.0 and Filter.1 nodes raise exceptions during `to_operation()`
- Exceptions caught at `Flowchart.py:951-956`
- Nodes added to `failed_nodes` set
- **Should** trigger popup at line 977
- **BUT** `loadFile()` calls `applyClicked(build_views=False)` which may suppress

**Recommended Fix (Option C - Split into two tests):**

```python
def test_load_atm_crix_structure(flowchart_from_file, popup_tracker):
    """Test that ATM_crix_new.fc loads and has correct structure."""
    popup_tracker.allow_popups()  # Filter nodes will fail during load
    
    fc, broker, comm = flowchart_from_file
    
    # Check sources were auto-detected and mocked
    assert 'timing:raw:eventcodes' in fc.nodes(data='node')
    assert 'c_piranha:raw:raw' in fc.nodes(data='node')
    assert 'c_atmopal:raw:image' in fc.nodes(data='node')
    assert 'c_piranha:ttfex:fltpos' in fc.nodes(data='node')
    
    # Check graph has processing nodes
    nodes = fc.nodes(data='node')
    assert len(nodes) > 4  # More than just sources
    
    # Check connections exist
    assert len(fc._graph.edges()) > 0
    
    # Clear popups - we don't care about them for structure test
    popup_tracker.clear()

@pytest.mark.expect_popup
def test_atm_crix_filter_errors(flowchart_from_file, popup_tracker):
    """Test that broken Filter nodes in ATM_crix_new.fc are handled correctly."""
    popup_tracker.allow_popups()
    
    fc, broker, comm = flowchart_from_file
    
    # Verify Filter nodes exist but have exceptions
    filter0 = fc.nodes(data='node').get('Filter.0')
    filter1 = fc.nodes(data='node').get('Filter.1')
    
    if filter0:
        assert filter0.hasException()
    if filter1:
        assert filter1.hasException()
    
    # Verify appropriate error popup appeared during load
    popup_tracker.assert_popup_shown("Failed to submit graph")
```

**Alternative (Option A - Fix .fc file):**
- Remove broken Filter nodes from ATM_crix_new.fc
- Add `popup_tracker.assert_no_popups()` to test
- Cleaner but loses error testing coverage

**Alternative (Option B - Keep as error test):**
- Mark with `@pytest.mark.expect_popup`
- Verify popup + Filter node exceptions
- Update comment to be accurate

#### Test 5: `test_atm_different_event_counts` (line 622)
Same file, same Filter node issue

```python
@pytest.mark.parametrize('flowchart_from_file', [
    ('ATM_crix_new.fc', 5),
    ('ATM_crix_new.fc', 10),
], indirect=True)
def test_atm_different_event_counts(flowchart_from_file, popup_tracker):
    """Test fixture works with different event counts."""
    popup_tracker.allow_popups()  # Filter nodes may fail
    
    fc, broker, comm = flowchart_from_file
    
    # Just verify fixture created flowchart successfully
    assert fc is not None
    assert comm is not None
    assert len(fc.nodes(data='node')) > 0
    
    # Don't verify popups - just testing fixture event count parameter
    popup_tracker.clear()
```

#### Test 6: `test_run22` (line 551)
Already commented out - skip

**Estimated effort:** 2-3 hours

---

### Phase 3: Investigate ATM_crix_new.fc Issue

**Investigation steps:**

1. **Understand why loadFile doesn't trigger popup:**
   ```python
   # Check Flowchart.py:731
   ctrl.applyClicked(build_views=False)
   
   # Trace through to line 975-978
   if failed_nodes:
       self.chartWidget.updateStatus("failed to submit graph", color='red')
       msg.exec()  # Should popup here
       return
   ```

2. **Test hypothesis:**
   - Add debug logging to verify `failed_nodes` is populated
   - Check if `build_views=False` affects popup logic
   - Manually trigger `loadFile()` to see actual behavior

3. **Resolution options:**
   - **Option A:** Fix .fc file (remove Filter nodes)
   - **Option B:** Document as error test (keep Filter nodes, verify popup)
   - **Option C:** Split into structure test + error test (recommended)
   - **Option D:** Create simple_test.fc without problematic nodes

**Recommended action:**
- Keep ATM_crix_new.fc as-is (real-world test case)
- Split into two tests (Option C from Phase 2)
- Optionally create `tests/graphs/simple_test.fc` for clean positive tests

**Estimated effort:** 2-3 hours

---

### Phase 4: Cleanup and Documentation

#### 4.1 Delete Obsolete Files

**File to delete:** `tests/test_asyncqt.py`

**Why:**
- Untracked file testing removed asyncio functionality
- Imports `create_qt_event_loop` from `ami/asyncqt.py` which doesn't exist
- Blocks test collection with import error
- Asyncio was removed from flowchart in commits f62b340-0c89ab5

**Command:**
```bash
rm tests/test_asyncqt.py
```

#### 4.2 Update Test Documentation

**File:** `tests/TEST_README.md`

**Add section:**

```markdown
## Popup Handling in GUI Tests

GUI tests automatically track and suppress QMessageBox popups using the `popup_tracker` fixture.

### Default Behavior (Strict Mode)

By default, tests **FAIL** if any popup appears:

```python
def test_something(flowchart, popup_tracker):
    # This will FAIL if popup appears
    flowchart.loadFile("valid.fc")
    
    # Explicit verification (optional, automatic at teardown)
    popup_tracker.assert_no_popups()
```

### Testing Error Conditions

Tests that expect popups must explicitly allow them:

```python
@pytest.mark.expect_popup
def test_error_handling(flowchart, popup_tracker):
    popup_tracker.allow_popups()
    
    # Trigger error
    flowchart.loadFile("nonexistent.fc")
    
    # Verify correct popup appeared
    popup_tracker.assert_popup_shown("does not exist")
```

### Allowing Real Dialogs

To test actual dialog rendering (requires xvfb-run):

```python
@pytest.mark.allow_dialogs
def test_real_dialog():
    # popup_tracker not active - real dialogs appear
    # Must use QTimer to auto-close or run with xvfb-run
```

### Multiple Popups in One Test

```python
@pytest.mark.expect_popup
def test_multiple_errors(flowchart, popup_tracker):
    popup_tracker.allow_popups()
    
    # First error
    flowchart.loadFile("bad1.fc")
    popup_tracker.assert_popup_shown("error 1")
    
    # Clear for next check
    popup_tracker.clear()
    
    # Second error
    flowchart.loadFile("bad2.fc")
    popup_tracker.assert_popup_shown("error 2")
```

### Pytest Markers

- `@pytest.mark.expect_popup` - Allow popups, disable strict mode
- `@pytest.mark.allow_dialogs` - Disable popup_tracker entirely (for real dialog tests)
```

#### 4.3 Update AGENTS.md

**File:** `AGENTS.md`

**Add to "Regression Testing Strategy" section:**

```markdown
#### Popup Handling

GUI tests use strict popup tracking to catch unexpected errors:

- **Default:** Tests fail if any QMessageBox appears
- **Expected popups:** Mark with `@pytest.mark.expect_popup` and verify message
- **Implementation:** `popup_tracker` fixture in `tests/conftest.py`
- **Details:** See `tests/TEST_README.md` for usage examples
```

**Estimated effort:** 1 hour

---

### Phase 5: Verification

**Run comprehensive test suite:**

#### 5.1 Basic Functionality
```bash
# All GUI tests should pass
pytest tests/test_gui.py -v

# Check that popup tracking works
pytest tests/test_gui.py::test_broker_sub -v
pytest tests/test_gui.py::test_sources -v  
pytest tests/test_gui.py::test_editor -v
```

#### 5.2 Popup Detection Test
```bash
# Temporarily modify test_broker_sub to trigger a popup
# Verify test FAILS with clear message about unexpected popup
# Revert change
```

#### 5.3 CI Compatibility
```bash
# Test with xvfb-run (CI environment simulation)
xvfb-run pytest tests/test_gui.py -v

# Should work identically
```

#### 5.4 Full Test Suite
```bash
# Run all tests to ensure no regressions
pytest tests/ -v --ignore=tests/test_asyncqt.py

# After deletion:
pytest tests/ -v
```

#### 5.5 Cross-Platform Check
```bash
# Run on local machine with DISPLAY
DISPLAY=localhost:16.0 pytest tests/test_gui.py -v

# Should work identically to CI
```

**Success Criteria:**
- ✅ All 6 GUI tests pass
- ✅ Tests fail when popup triggered unexpectedly
- ✅ Tests pass when popup expected and verified
- ✅ No regressions in other test files
- ✅ CI tests pass with xvfb-run

**Estimated effort:** 1-2 hours

---

## Total Effort Estimate

- **Phase 1** (Infrastructure): 1-2 hours
- **Phase 2** (Update tests): 2-3 hours  
- **Phase 3** (Investigation): 2-3 hours
- **Phase 4** (Cleanup & docs): 1 hour
- **Phase 5** (Verification): 1-2 hours

**Total: 7-11 hours**

---

## Risk Mitigation

### Risk 1: Popup tracking misses some dialog types

**Mitigation:**
- Mock both `exec()` and `exec_()` methods
- Also track `show()` for non-blocking dialogs
- Add logging to detect unmocked dialog creation
- Test with various dialog types (QFileDialog, QInputDialog, etc.)

### Risk 2: Breaking existing functionality

**Mitigation:**
- Popup suppression is test-only (via monkeypatch)
- Production code completely unchanged
- Can disable per-test with `@pytest.mark.allow_dialogs`
- Gradual rollout - test each change independently

### Risk 3: ATM_crix investigation takes longer than expected

**Mitigation:**
- Time-box investigation to 3 hours
- If complex root cause, defer deep fix
- Create simpler test file as alternative
- Document issue in test comment for future work

### Risk 4: False positives (legitimate popups marked as errors)

**Mitigation:**
- Strict mode can be disabled per-test
- Clear documentation on when to use `@pytest.mark.expect_popup`
- Popup message verification helps distinguish expected vs unexpected

---

## Open Questions

### Question 1: ATM_crix_new.fc handling preference?

**Options:**
- **A:** Fix .fc file (remove Filter nodes) - cleaner
- **B:** Keep as error test (verify popup) - maintains coverage
- **C:** Split into structure + error tests - thorough
- **D:** Create new simple test file - safest

**Recommendation:** Option C (split tests) - best of both worlds

**Decision:** _[To be filled during review]_

---

### Question 2: Popup message verification depth?

**Options:**
- **Simple:** Just check if popup appeared (yes/no)
- **Moderate:** Verify popup contains expected text substring
- **Strict:** Verify exact text + icon type + buttons

**Recommendation:** Moderate (contains expected text) - good balance

**Decision:** _[To be filled during review]_

---

### Question 3: Documentation location?

**Options:**
- **TEST_README only:** Test-specific docs
- **AGENTS.md only:** AI agent guide
- **Both:** TEST_README primary, AGENTS references it

**Recommendation:** Both - TEST_README for details, AGENTS for overview

**Decision:** _[To be filled during review]_

---

### Question 4: Test organization?

**Options:**
- **Keep in test_gui.py:** Currently small (6 tests)
- **Split files:** test_gui_basic.py + test_gui_errors.py

**Recommendation:** Keep in test_gui.py - premature to split

**Decision:** _[To be filled during review]_

---

## Implementation Checklist

### Phase 1: Infrastructure
- [ ] Add `PopupTracker` class to `tests/conftest.py`
- [ ] Add `popup_tracker` fixture to `tests/conftest.py`
- [ ] Test fixture works (basic test)
- [ ] Verify strict mode fails on popup
- [ ] Verify allow mode permits popup

### Phase 2: Update Tests
- [ ] Update `test_broker_sub` - add `popup_tracker.assert_no_popups()`
- [ ] Update `test_sources` - add `popup_tracker.assert_no_popups()`
- [ ] Update `test_editor` - add `popup_tracker.assert_no_popups()`
- [ ] Split `test_load_atm_crix` into structure + error tests
- [ ] Update `test_atm_different_event_counts` - allow popups
- [ ] Run each test individually to verify

### Phase 3: Investigation
- [ ] Add debug logging to understand ATM_crix popup behavior
- [ ] Verify Filter nodes raise exceptions
- [ ] Verify `failed_nodes` is populated
- [ ] Determine if popup actually appears or is suppressed
- [ ] Document findings
- [ ] Implement chosen option (A/B/C/D)

### Phase 4: Cleanup
- [ ] Delete `tests/test_asyncqt.py`
- [ ] Update `tests/TEST_README.md` with popup handling section
- [ ] Update `AGENTS.md` with regression testing note
- [ ] Review all documentation for accuracy

### Phase 5: Verification
- [ ] Run `pytest tests/test_gui.py -v` - all pass
- [ ] Trigger unexpected popup - verify test fails
- [ ] Test with xvfb-run - verify compatibility
- [ ] Run full test suite - verify no regressions
- [ ] Cross-platform check (local + CI)

---

## Success Criteria

✅ **All tests must:**
- Pass when no popups appear
- Fail when unexpected popup appears
- Pass when expected popup appears and is verified

✅ **Documentation must:**
- Clearly explain popup handling system
- Provide usage examples
- Document all pytest markers

✅ **Test coverage must:**
- Include positive cases (no popups)
- Include negative cases (expected popups)
- Cover error handling paths

✅ **Implementation must:**
- Not modify production code
- Work with and without xvfb-run
- Be backwards compatible with existing tests (after update)

---

## Future Enhancements

**Out of scope for this plan but consider later:**

1. **Screenshot capture on popup:**
   - Save screenshot when popup appears (with xvfb)
   - Helps debugging what triggered popup
   
2. **Popup history logging:**
   - Log all popups to file for post-test analysis
   - Useful for CI troubleshooting

3. **QFileDialog/QInputDialog support:**
   - Extend tracking to other dialog types
   - Currently only handles QMessageBox

4. **Popup timing analysis:**
   - Track when each popup occurred
   - Correlate with test execution timeline

5. **Auto-close real dialogs:**
   - QTimer-based auto-close for integration tests
   - Allows testing actual dialog rendering

---

## References

- **pytest-qt documentation:** https://pytest-qt.readthedocs.io/en/latest/note_dialogs.html
- **AMI CI workflows:** `.github/workflows/run_tests.yaml`, `.github/workflows/main.yaml`
- **Existing tests:** `tests/test_gui.py`
- **Production code:** `ami/flowchart/Flowchart.py`, `ami/flowchart/library/Alert.py`
- **Asyncio removal:** Commits f62b340 through 0c89ab5

---

## Notes

- This plan assumes asyncio removal from flowchart is complete (Phase 5 commit 0c89ab5)
- All tests currently run with `--headless` flag
- CI already uses `xvfb-run pytest` so popup suppression is additional safety
- Monkeypatch approach is cross-platform (works on Windows/macOS unlike xvfb)
- Strict mode prevents silent failures where tests pass but popups indicate errors

---

## Author

Plan created: 2026-03-25  
Last updated: 2026-03-25  
Status: Ready for implementation
