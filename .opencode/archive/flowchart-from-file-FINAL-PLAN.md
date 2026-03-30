# FINAL Implementation Plan: `flowchart_from_file` Fixture

**Date:** 2026-03-25  
**Status:** Ready for Implementation  
**Approved by User:** ✅

---

## User Decisions

1. **Return value:** `(fc, broker, comm)` ✅
2. **Default event count:** 10 events ✅
3. **Fixture location:** TBD - Recommend `tests/test_gui.py` (GUI-specific)
4. **Create example .fc files:** Yes ✅
5. **Helper timeout behavior:** TBD - Recommend return bool (more flexible)

---

## Implementation Summary

### What We're Building

A pytest fixture that:
1. Loads any .fc file
2. Auto-detects and mocks sources from the .fc file
3. Limits execution to N events (default: 10)
4. Provides `GraphCommHandler` for result verification

### API

```python
# Simple usage - 10 events default
@pytest.mark.parametrize('flowchart_from_file', ['my_graph.fc'], indirect=True)
def test_graph(flowchart_from_file):
    fc, broker, comm = flowchart_from_file

# Custom event count
@pytest.mark.parametrize('flowchart_from_file', [('my_graph.fc', 5)], indirect=True)
def test_graph_5_events(flowchart_from_file):
    fc, broker, comm = flowchart_from_file
```

---

## Files to Create/Modify

### 1. Modify: `tests/test_gui.py`

**Add 3 helper functions** (before fixtures, ~60 lines):
- `extract_sources_from_fc(fc_path)` - Parse .fc file for SourceNodes
- `map_amitypes_to_config(ttype)` - Map amitypes → static source config
- `resolve_fc_path(fc_file)` - Resolve file paths (defaults to tests/graphs/)

**Add 1 helper function** (for tests, ~15 lines):
- `wait_for_features(comm, qtbot, timeout_ms=5000)` - Wait for results
  - **Behavior:** Return `True` if features available, `False` if timeout
  - **Why:** More flexible - tests can choose to assert or handle differently

**Add main fixture** (~150 lines):
- `flowchart_from_file(request, broker, ipc_dir, graphmgr_addr, dmypy, qtbot, tmp_path)`
- Returns: `(fc, broker, comm)`
- Default: 10 events
- Accepts: String or Tuple `(fc_file, num_events)`

**Total additions to test_gui.py:** ~225 lines

### 2. Create: `tests/graphs/simple_roi_sum.fc`

Simple test graph:
- Source: `cspad` (Array2d)
- Node 1: `Roi2D.0` - Extract ROI
- Node 2: `Sum.0` - Sum the ROI
- Perfect for testing computation correctness

### 3. Create: `tests/graphs/simple_projection.fc`

Another simple test graph:
- Source: `image` (Array2d)
- Node 1: `Projection.0` - Project to 1D
- Node 2: `WaveformViewer.0` - Display

---

## Implementation Steps

### Phase 1: Helper Functions (~1 hour)

**Step 1.1:** Add `extract_sources_from_fc()`
```python
def extract_sources_from_fc(fc_path):
    # Read .fc file
    # Find nodes where class == 'SourceNode'
    # Extract name and ttype from terminals
    # Return dict: {source_name: config}
```

**Step 1.2:** Add `map_amitypes_to_config()`
```python
def map_amitypes_to_config(ttype):
    # Map 'amitypes.Array2d' → {"dtype": "Image", "shape": [512, 512], ...}
    # Map 'amitypes.Array1d' → {"dtype": "Waveform", "length": 1024}
    # Map 'amitypes.int*' → {"dtype": "Scalar", "integer": True, ...}
    # Default to Scalar
```

**Step 1.3:** Add `resolve_fc_path()`
```python
def resolve_fc_path(fc_file):
    # If absolute path → return as-is
    # If has directory → return as-is
    # Else → prepend 'tests/graphs/'
```

**Step 1.4:** Add `wait_for_features()` helper
```python
def wait_for_features(comm, qtbot, timeout_ms=5000):
    # Track initial featuresVersion
    # Loop with qtbot.wait(100) until version changes
    # Return True if changed, False if timeout
```

### Phase 2: Main Fixture (~2 hours)

**Step 2.1:** Implement fixture skeleton
```python
@pytest.fixture(scope='function')
def flowchart_from_file(request, broker, ipc_dir, graphmgr_addr, dmypy, qtbot, tmp_path):
    # Parse request.param (string or tuple)
    # Extract fc_file and num_events (default: 10)
```

**Step 2.2:** Implement source mocking
```python
    # fc_path = resolve_fc_path(fc_file)
    # source_config = extract_sources_from_fc(fc_path)
    # Create worker.json with:
    #   - "bound": num_events (default 10)
    #   - "repeat": False
    #   - "config": source_config
```

**Step 2.3:** Start AMI and create flowchart
```python
    # Start AMI process with static://worker.json
    # Create GraphCommHandler (comm)
    # Wait for sources
    # Create Flowchart
    # fc.initialize()
    # qtbot.addWidget(fc.widget())
    # fc.loadFile(fc_path)
    # Yield (fc, broker, comm)
```

**Step 2.4:** Add cleanup
```python
    # finally:
    #   Stop AMI process
    #   Check exit code
```

### Phase 3: Create Test .fc Files (~30 min)

**Step 3.1:** Create `tests/graphs/simple_roi_sum.fc`
- Manually create simple graph in AMI GUI
- Add SourceNode: cspad (Array2d)
- Add Roi2D node
- Add Sum node
- Connect: cspad → Roi2D → Sum
- Save as `simple_roi_sum.fc`

**Step 3.2:** Create `tests/graphs/simple_projection.fc`
- Add SourceNode: image (Array2d)
- Add Projection node
- Add WaveformViewer
- Connect: image → Projection → WaveformViewer
- Save as `simple_projection.fc`

### Phase 4: Write Example Tests (~1 hour)

**Test 1:** Basic loading
```python
@pytest.mark.parametrize('flowchart_from_file', ['simple_roi_sum.fc'], indirect=True)
def test_load_simple_graph(flowchart_from_file):
    fc, broker, comm = flowchart_from_file
    assert 'cspad' in fc.nodes(data='node')
    assert 'Roi2D.0' in fc.nodes(data='node')
    assert 'Sum.0' in fc.nodes(data='node')
```

**Test 2:** Verify computation
```python
@pytest.mark.parametrize('flowchart_from_file', [
    ('simple_roi_sum.fc', 5),
], indirect=True)
def test_roi_sum_correctness(flowchart_from_file, qtbot):
    fc, broker, comm = flowchart_from_file
    
    ctrl = fc.widget()
    ctrl.applyClicked()
    
    assert wait_for_features(comm, qtbot), "Timeout waiting for features"
    
    # Get results
    roi_result = comm.fetch('Roi2D.0')
    sum_result = comm.fetch('Sum.0')
    
    # Verify
    expected = np.sum(roi_result)
    assert np.isclose(sum_result, expected)
```

**Test 3:** Different event counts
```python
@pytest.mark.parametrize('flowchart_from_file', [
    ('simple_roi_sum.fc', 3),
    ('simple_roi_sum.fc', 10),
], indirect=True)
def test_different_event_counts(flowchart_from_file):
    fc, broker, comm = flowchart_from_file
    # Just verify fixture works with different counts
    assert len(fc.nodes(data='node')) > 0
```

**Test 4:** Existing .fc file
```python
@pytest.mark.parametrize('flowchart_from_file', ['run22.fc'], indirect=True)
def test_existing_fc_file(flowchart_from_file):
    fc, broker, comm = flowchart_from_file
    assert 'andor' in fc.nodes(data='node')
    assert 'waveforms' in fc.nodes(data='node')
```

### Phase 5: Testing & Refinement (~2 hours)

**Step 5.1:** Test helper functions
- Test `extract_sources_from_fc()` with run22.fc
- Test `map_amitypes_to_config()` with various types
- Test `resolve_fc_path()` with different inputs

**Step 5.2:** Test fixture
- Run example tests
- Check that sources are correctly mocked
- Verify event limiting works
- Verify result retrieval works

**Step 5.3:** Debug and refine
- Fix any issues found
- Improve error messages
- Add edge case handling

**Step 5.4:** Documentation
- Ensure docstrings are complete
- Add usage examples to fixture docstring
- Comment complex sections

---

## Detailed Implementation Code

### Helper Function 1: `extract_sources_from_fc`

```python
def extract_sources_from_fc(fc_path):
    """
    Parse .fc file and extract source node configurations.
    
    Args:
        fc_path: Path to .fc file
        
    Returns:
        dict: Source configurations for worker.json
        Example: {
            'andor': {'dtype': 'Image', 'shape': [512, 512], 'pedestal': 5, 'width': 1},
            'laser': {'dtype': 'Scalar', 'range': [0, 100], 'integer': True}
        }
    """
    import json
    
    with open(fc_path, 'r') as f:
        data = json.load(f)
    
    sources = {}
    for node in data.get('nodes', []):
        if node.get('class') == 'SourceNode':
            name = node['name']
            terminals = node.get('state', {}).get('terminals', {})
            if 'Out' in terminals:
                ttype = terminals['Out'].get('ttype', '')
                sources[name] = map_amitypes_to_config(ttype)
    
    return sources
```

### Helper Function 2: `map_amitypes_to_config`

```python
def map_amitypes_to_config(ttype):
    """
    Map amitypes type string to static source config.
    
    Args:
        ttype: String like "amitypes.Array2d"
        
    Returns:
        dict: Config for static data source
    """
    # Default config
    default = {"dtype": "Scalar", "range": [0, 100]}
    
    if not ttype:
        return default
    
    # Extract base type
    if 'Array2d' in ttype:
        return {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [512, 512]}
    elif 'Array1d' in ttype:
        return {"dtype": "Waveform", "length": 1024}
    elif 'Array3d' in ttype:
        return {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [100, 512, 512]}
    elif 'int' in ttype.lower():
        return {"dtype": "Scalar", "range": [0, 100], "integer": True}
    elif 'float' in ttype.lower():
        return {"dtype": "Scalar", "range": [0.0, 100.0]}
    else:
        return default
```

### Helper Function 3: `resolve_fc_path`

```python
def resolve_fc_path(fc_file):
    """
    Resolve .fc file path.
    
    Args:
        fc_file: Filename or relative path
        
    Returns:
        str: Path to .fc file
        
    Examples:
        'my_graph.fc' → 'tests/graphs/my_graph.fc'
        'examples/complex.fc' → 'examples/complex.fc'
        '/abs/path/graph.fc' → '/abs/path/graph.fc'
    """
    import os
    
    # Already absolute
    if os.path.isabs(fc_file):
        return fc_file
    
    # Has directory component - use as-is
    if os.path.dirname(fc_file):
        return fc_file
    
    # Just filename - default to tests/graphs/
    return os.path.join('tests/graphs', fc_file)
```

### Helper Function 4: `wait_for_features`

```python
def wait_for_features(comm, qtbot, timeout_ms=5000):
    """
    Wait for features to be available (featuresVersion to update).
    
    Args:
        comm: GraphCommHandler instance
        qtbot: pytest-qt qtbot fixture
        timeout_ms: Maximum time to wait in milliseconds (default: 5000)
        
    Returns:
        bool: True if features available, False if timeout
        
    Example:
        if wait_for_features(comm, qtbot):
            result = comm.fetch('Sum.0')
        else:
            pytest.fail("Timeout waiting for features")
    """
    initial_version = comm.featuresVersion
    elapsed = 0
    
    while comm.featuresVersion == initial_version and elapsed < timeout_ms:
        qtbot.wait(100)
        elapsed += 100
    
    return elapsed < timeout_ms
```

### Main Fixture: `flowchart_from_file`

```python
@pytest.fixture(scope='function')
def flowchart_from_file(request, broker, ipc_dir, graphmgr_addr, dmypy, qtbot, tmp_path):
    """
    Create flowchart with auto-mocked sources from .fc file.
    
    Automatically detects sources in the .fc file and creates matching
    mock static data sources. Supports limiting event count and retrieving
    computed results for verification.
    
    Usage:
        # Simple: just load .fc file (default 10 events)
        @pytest.mark.parametrize('flowchart_from_file', [
            'my_graph.fc',
        ], indirect=True)
        def test_graph(flowchart_from_file):
            fc, broker, comm = flowchart_from_file
            # Graph already loaded, sources mocked
        
        # With custom event limit
        @pytest.mark.parametrize('flowchart_from_file', [
            ('my_graph.fc', 5),  # Only 5 events
        ], indirect=True)
        def test_graph_with_limit(flowchart_from_file):
            fc, broker, comm = flowchart_from_file
            # Only 5 events will be processed
    
    Parameters (via request.param):
        - String: Path to .fc file (default: 10 events)
        - Tuple: (fc_file_path, num_events)
          - fc_file_path: Path to .fc file (relative to project root)
          - num_events: Number of events to generate (default: 10)
    
    Returns:
        (fc, broker, comm): Tuple of:
            - fc: Flowchart instance with .fc file loaded
            - broker: MessageBroker instance
            - comm: GraphCommHandler for retrieving results
    
    Example - Verify computation:
        @pytest.mark.parametrize('flowchart_from_file', [
            ('simple_sum.fc', 5),
        ], indirect=True)
        def test_sum_computation(flowchart_from_file, qtbot):
            fc, broker, comm = flowchart_from_file
            
            ctrl = fc.widget()
            ctrl.applyClicked()
            
            if wait_for_features(comm, qtbot):
                result = comm.fetch('Sum.0')
                assert result > 0
            else:
                pytest.fail("Timeout waiting for results")
    """
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass
    
    # Parse parameters
    if isinstance(request.param, tuple):
        fc_file, num_events = request.param
    else:
        fc_file = request.param
        num_events = 10  # Default: 10 events
    
    fc_path = resolve_fc_path(fc_file)
    
    # Extract source configurations from .fc file
    source_config = extract_sources_from_fc(fc_path)
    
    # Create worker.json with mocked sources
    cfg = {
        "interval": 0.01,
        "init_time": 0.1,
        "bound": num_events,  # Limit number of events
        "repeat": False,      # Don't loop - stop after bound
        "files": "data.xtc2",
        "config": source_config,  # Auto-generated from .fc file
    }
    
    workerjson_path = os.path.join(tmp_path, 'worker.json')
    with open(workerjson_path, 'w') as fd:
        json.dump(cfg, fd)
    
    # Start AMI with static data source
    parser = build_parser()
    args = parser.parse_args(["-n", "1", '-i', str(ipc_dir), '--headless',
                              f'static://{workerjson_path}'])
    
    queue = mp.Queue()
    ami = mp.Process(name='ami', target=run_ami, args=(args, queue))
    ami.start()
    
    try:
        # Wait for AMI to be ready and create persistent comm handler
        comm = GraphCommHandler(graphmgr_addr.name, graphmgr_addr.comm)
        while not comm.sources:
            time.sleep(0.1)
        
        os.makedirs(os.path.expanduser("~/.cache/ami/"), exist_ok=True)
        
        # Create flowchart
        with Flowchart(broker_addr=broker.broker_sub_addr,
                       graphmgr_addr=graphmgr_addr,
                       checkpoint_addr=broker.checkpoint_pub_addr) as fc:
            
            fc.initialize()
            
            qtbot.addWidget(fc.widget())
            
            fc.loadFile(fc_path)
            
            yield (fc, broker, comm)
    
    except Exception as e:
        print(f"error setting up flowchart_from_file fixture: {e}")
        import traceback
        traceback.print_exc()
        yield None
    finally:
        # Cleanup
        queue.put(None)
        ami.join(2)
        if ami.is_alive():
            ami.terminate()
            ami.join()
        
        if ami.exitcode == 0 or ami.exitcode == -signal.SIGTERM:
            return 0
        else:
            print(f'AMI exited with non-zero status code: {ami.exitcode}')
            return 1
```

---

## Testing Checklist

After implementation:

- [ ] Helper functions work correctly
  - [ ] `extract_sources_from_fc('tests/graphs/run22.fc')` returns sources
  - [ ] `map_amitypes_to_config('amitypes.Array2d')` returns Image config
  - [ ] `resolve_fc_path('test.fc')` returns 'tests/graphs/test.fc'
  - [ ] `wait_for_features()` waits and returns correctly

- [ ] Fixture works with existing .fc files
  - [ ] Can load `tests/graphs/run22.fc`
  - [ ] Sources are detected: 'andor', 'waveforms'
  - [ ] Returns (fc, broker, comm) tuple

- [ ] Event limiting works
  - [ ] Default 10 events
  - [ ] Custom event count via tuple parameter
  - [ ] Events actually limited (not infinite)

- [ ] Result verification works
  - [ ] `comm.features` returns dict
  - [ ] `comm.fetch('nodename')` returns values
  - [ ] `wait_for_features()` detects when data ready

- [ ] Example .fc files created
  - [ ] `simple_roi_sum.fc` loads and works
  - [ ] `simple_projection.fc` loads and works

- [ ] Example tests pass
  - [ ] Basic loading test
  - [ ] Computation verification test
  - [ ] Different event counts test

---

## Open Questions (Revisit During Implementation)

### Question 1: Fixture Location

**Option A:** `tests/test_gui.py`
- Pro: GUI-specific, keeps related code together
- Con: Already a long file

**Option B:** `tests/conftest.py`
- Pro: Available to all test files
- Con: Not all tests need GUI fixtures

**Recommendation:** Start with `tests/test_gui.py`, can move to conftest later if needed

### Question 2: `wait_for_features()` Behavior

**Current design:** Return `True`/`False`
```python
if wait_for_features(comm, qtbot):
    result = comm.fetch('Sum.0')
else:
    pytest.fail("Timeout")
```

**Alternative:** Raise assertion
```python
wait_for_features(comm, qtbot)  # Raises if timeout
result = comm.fetch('Sum.0')
```

**Recommendation:** Keep return bool - more flexible, tests can choose behavior

---

## Estimated Timeline

- **Helper functions:** 1 hour
- **Main fixture:** 2 hours
- **Create .fc files:** 30 minutes
- **Example tests:** 1 hour
- **Testing & debugging:** 2 hours
- **Total:** ~6.5 hours

---

## Success Criteria

✅ **Core functionality:**
- Fixture loads any .fc file
- Sources auto-detected and mocked
- Events limited to specified count
- Results retrievable via `comm.fetch()`

✅ **Code quality:**
- Comprehensive docstrings
- Error handling for edge cases
- Clean, readable code

✅ **Testing:**
- All example tests pass
- Works with existing run22.fc
- Works with new simple test .fc files

✅ **Documentation:**
- Fixture usage documented in docstring
- Example tests demonstrate all features
- Type mappings documented

---

## Ready to Implement!

All design decisions made, detailed code provided, ready for execution.

**Waiting for:** Final approval to proceed with implementation (currently in plan mode).
