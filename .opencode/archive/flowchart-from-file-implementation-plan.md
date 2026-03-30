# Implementation Plan: `flowchart_from_file` Fixture with Result Verification

**Date:** 2026-03-25  
**Goal:** Create test fixture that loads .fc files with auto-mocked sources AND supports result verification  
**Key Features:**
1. Auto-detect and mock sources from .fc file
2. Limit execution to N events
3. Retrieve and verify computed results

---

## User Requirements Summary

1. ✅ Load .fc files in tests
2. ✅ Mock sources using static data (no psana needed)
3. ✅ **Stop after a few events to check computation correctness**

---

## Architecture Overview

```
.fc File → Parse Sources → Generate worker.json → Start AMI (limited events)
                                                         ↓
                                                   Apply Graph
                                                         ↓
                                              Wait for N events to process
                                                         ↓
                                              Retrieve results via comm.fetch()
                                                         ↓
                                              Assert correctness
```

---

## Event Limiting Strategy

### Static Data Source Config

The `workerjson` already has a `"bound"` parameter:

```python
cfg = {
    "interval": 0.01,      # Time between events (seconds)
    "init_time": 0.1,      # Wait time before starting
    "bound": 100,          # NUMBER OF EVENTS TO GENERATE! ← This controls it
    "repeat": True,        # Loop after bound reached
    "files": "data.xtc2",
    "config": {...}
}
```

**Key insight:** Setting `"bound": 10` means static source generates exactly 10 events, then either:
- Stops (if `repeat: false`)
- Loops back to start (if `repeat: true`)

### Test Flow with Event Limiting

```python
# 1. Configure static source with low bound
cfg = {"bound": 10, "repeat": False, ...}  # Only 10 events

# 2. Apply graph
ctrl.applyClicked()

# 3. Wait for events to be processed
qtbot.wait(500)  # Wait 500ms for processing

# 4. Retrieve results
result = comm.fetch('Sum.0')  # Get result from Sum node

# 5. Verify
assert result == expected_value
```

---

## Result Retrieval Methods

### Method 1: GraphCommHandler.fetch()

**Best for: Getting individual feature values**

```python
comm = GraphCommHandler(graphmgr_addr.name, graphmgr_addr.comm)

# Get list of available features
features = comm.features  # Dict: {name: type_info}

# Fetch specific feature value
result = comm.fetch('Sum.0')  # Returns actual computed value
```

### Method 2: GraphCommHandler.features Property

**Best for: Checking what's available**

```python
features = comm.features
# Returns: {'Sum.0': <class 'float'>, 'Roi.0': (<class 'numpy.ndarray'>, 2)}

# Check if computation produced output
assert 'Sum.0' in features
```

### Method 3: Wait for Features Version to Update

**Best for: Knowing when data is ready**

```python
initial_version = comm.featuresVersion

# Apply graph
ctrl.applyClicked()

# Wait for new data
while comm.featuresVersion == initial_version:
    qtbot.wait(100)
    if timeout:
        break

# Now fetch results
result = comm.fetch('Sum.0')
```

---

## Implementation Plan

### Part 1: Helper Functions

**File:** `tests/test_gui.py` (add at top, before fixtures)

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

### Part 2: Main Fixture

**File:** `tests/test_gui.py` (add after other fixtures)

```python
@pytest.fixture(scope='function')
def flowchart_from_file(request, broker, ipc_dir, graphmgr_addr, dmypy, qtbot, tmp_path):
    """
    Create flowchart with auto-mocked sources from .fc file.
    
    Automatically detects sources in the .fc file and creates matching
    mock static data sources. Supports limiting event count and retrieving
    computed results for verification.
    
    Usage:
        # Simple: just load .fc file (default 100 events)
        @pytest.mark.parametrize('flowchart_from_file', [
            'run22.fc',
        ], indirect=True)
        def test_graph(flowchart_from_file):
            fc, broker, comm = flowchart_from_file
            # Graph already loaded, sources mocked
        
        # With custom event limit
        @pytest.mark.parametrize('flowchart_from_file', [
            ('run22.fc', 10),  # Only 10 events
        ], indirect=True)
        def test_graph_with_limit(flowchart_from_file):
            fc, broker, comm = flowchart_from_file
            # Only 10 events will be processed
    
    Parameters (via request.param):
        - String: Path to .fc file (default: 100 events)
        - Tuple: (fc_file_path, num_events)
          - fc_file_path: Path to .fc file (relative to project root)
          - num_events: Number of events to generate (default: 100)
    
    Returns:
        (fc, broker, comm): Tuple of:
            - fc: Flowchart instance with .fc file loaded
            - broker: MessageBroker instance
            - comm: GraphCommHandler for retrieving results
    
    Example - Verify computation:
        @pytest.mark.parametrize('flowchart_from_file', [
            ('simple_sum.fc', 5),  # Process 5 events
        ], indirect=True)
        def test_sum_computation(flowchart_from_file, qtbot):
            fc, broker, comm = flowchart_from_file
            
            # Apply the graph
            ctrl = fc.widget()
            ctrl.applyClicked()
            
            # Wait for processing
            initial_version = comm.featuresVersion
            timeout = 50  # 5 seconds max
            while comm.featuresVersion == initial_version and timeout > 0:
                qtbot.wait(100)
                timeout -= 1
            
            # Check results
            features = comm.features
            assert 'Sum.0' in features
            
            result = comm.fetch('Sum.0')
            assert result > 0  # Verify computation happened
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
        num_events = 100  # Default
    
    fc_path = resolve_fc_path(fc_file)
    
    # Extract source configurations from .fc file
    source_config = extract_sources_from_fc(fc_path)
    
    # Create worker.json with mocked sources
    cfg = {
        "interval": 0.01,
        "init_time": 0.1,
        "bound": num_events,  # Limit number of events!
        "repeat": False,      # Don't loop - stop after bound
        "files": "data.xtc2",
        "config": source_config,  # Auto-generated from .fc file!
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
            
            fc.initialize()  # Initialize flowchart
            
            qtbot.addWidget(fc.widget())  # Add to qtbot for proper cleanup
            
            fc.loadFile(fc_path)  # Load the .fc file!
            
            yield (fc, broker, comm)  # Return comm for result checking!
    
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

## Example Test Cases

### Test 1: Basic .fc File Loading

```python
@pytest.mark.parametrize('flowchart_from_file', ['run22.fc'], indirect=True)
def test_load_run22(flowchart_from_file):
    """Test loading run22.fc with auto-mocked sources."""
    fc, broker, comm = flowchart_from_file
    
    # Check sources were detected and mocked
    assert 'andor' in fc.nodes(data='node')
    assert 'waveforms' in fc.nodes(data='node')
    
    # Check graph structure loaded
    assert 'Projection.0' in fc.nodes(data='node')
    assert 'Sum.0' in fc.nodes(data='node')
    assert len(fc._graph.edges()) > 0
```

### Test 2: Verify Computation with Limited Events

```python
@pytest.mark.parametrize('flowchart_from_file', [
    ('run22.fc', 5),  # Only process 5 events
], indirect=True)
def test_computation_correctness(flowchart_from_file, qtbot):
    """Test that graph computes correctly with limited events."""
    fc, broker, comm = flowchart_from_file
    
    # Apply the graph
    ctrl = fc.widget()
    ctrl.applyClicked()
    
    # Wait for graph version to update
    assert comm.graphVersion > 0
    
    # Wait for features to be available
    initial_version = comm.featuresVersion
    timeout = 50  # 5 seconds max
    while comm.featuresVersion == initial_version and timeout > 0:
        qtbot.wait(100)
        timeout -= 1
    
    assert timeout > 0, "Timeout waiting for features"
    
    # Check features are available
    features = comm.features
    print(f"Available features: {features}")
    
    # Verify specific computations
    if 'Sum.0' in features:
        result = comm.fetch('Sum.0')
        assert isinstance(result, (int, float, np.number))
        assert result > 0  # Static data generates non-zero values
    
    if 'Projection.0' in features:
        result = comm.fetch('Projection.0')
        assert isinstance(result, np.ndarray)
        assert result.shape[0] > 0
```

### Test 3: Test Multiple Events

```python
@pytest.mark.parametrize('flowchart_from_file', [
    ('run22.fc', 3),   # Test with 3 events
    ('run22.fc', 10),  # Test with 10 events
], indirect=True)
def test_different_event_counts(flowchart_from_file, qtbot):
    """Test graph works with different event counts."""
    fc, broker, comm = flowchart_from_file
    
    ctrl = fc.widget()
    ctrl.applyClicked()
    
    # Wait briefly
    qtbot.wait(1000)
    
    # Just check that graph applied successfully
    assert comm.graphVersion > 0
```

### Test 4: Verify Specific Node Computation

```python
@pytest.mark.parametrize('flowchart_from_file', [
    ('simple_roi_sum.fc', 10),
], indirect=True)
def test_roi_sum_computation(flowchart_from_file, qtbot):
    """Test ROI + Sum computation is correct."""
    fc, broker, comm = flowchart_from_file
    
    # Apply graph
    ctrl = fc.widget()
    ctrl.applyClicked()
    
    # Wait for processing
    qtbot.wait(1000)
    
    # Get ROI output
    roi_result = comm.fetch('Roi2D.0')
    assert isinstance(roi_result, np.ndarray)
    
    # Get Sum of ROI
    sum_result = comm.fetch('Sum.0')
    
    # Verify: sum should equal np.sum(roi_result)
    expected_sum = np.sum(roi_result)
    assert np.isclose(sum_result, expected_sum), \
        f"Sum mismatch: got {sum_result}, expected {expected_sum}"
```

---

## Additional Helper: Wait for Features

**Add this helper function for tests:**

```python
def wait_for_features(comm, qtbot, timeout_ms=5000):
    """
    Wait for features to be available.
    
    Args:
        comm: GraphCommHandler instance
        qtbot: pytest-qt qtbot fixture
        timeout_ms: Maximum time to wait in milliseconds
        
    Returns:
        bool: True if features available, False if timeout
    """
    initial_version = comm.featuresVersion
    elapsed = 0
    
    while comm.featuresVersion == initial_version and elapsed < timeout_ms:
        qtbot.wait(100)
        elapsed += 100
    
    return elapsed < timeout_ms
```

**Usage in tests:**

```python
def test_with_helper(flowchart_from_file, qtbot):
    fc, broker, comm = flowchart_from_file
    
    ctrl = fc.widget()
    ctrl.applyClicked()
    
    # Wait for features
    assert wait_for_features(comm, qtbot), "Timeout waiting for results"
    
    # Now check results
    result = comm.fetch('Sum.0')
    assert result > 0
```

---

## Implementation Checklist

### Phase 1: Helper Functions
- [ ] Implement `extract_sources_from_fc()`
- [ ] Implement `map_amitypes_to_config()`
- [ ] Implement `resolve_fc_path()`
- [ ] Implement `wait_for_features()` helper
- [ ] Test helpers with existing .fc files

### Phase 2: Main Fixture
- [ ] Implement `flowchart_from_file` fixture
- [ ] Test with default event count (100)
- [ ] Test with custom event count (10, 5, etc.)
- [ ] Verify comm.features returns correct data
- [ ] Verify comm.fetch() retrieves values

### Phase 3: Example Tests
- [ ] Write test for basic .fc loading
- [ ] Write test for computation verification
- [ ] Write test for different event counts
- [ ] Write test for specific node verification

### Phase 4: Documentation
- [ ] Add comprehensive docstring to fixture
- [ ] Add usage examples in docstring
- [ ] Create simple test .fc files in tests/graphs/
- [ ] Document type mappings

---

## Files to Create/Modify

### Modify
- `tests/test_gui.py` - Add fixture and helper functions (~200 lines)

### Create (Optional - for testing)
- `tests/graphs/simple_roi_sum.fc` - Simple test graph
- `tests/graphs/projection_histogram.fc` - Another test case

---

## Key Design Decisions

### 1. Return (fc, broker, comm) instead of just (fc, broker)

**Why:** Tests need `comm` to retrieve results via `comm.fetch()`

**Impact:** Slightly different from existing `flowchart` fixture, but necessary for result verification

### 2. Default to `repeat: False` in worker config

**Why:** Tests want exactly N events, not looping

**Impact:** Graph stops after N events, perfect for verification tests

### 3. Use tuple parameter for event count

**Why:** Most tests don't care about event count, but some do

**Usage:**
- `'graph.fc'` → 100 events (default)
- `('graph.fc', 10)` → 10 events (custom)

### 4. Add `wait_for_features()` helper

**Why:** Tests need to wait for async processing before checking results

**Alternative:** Could be built into fixture, but helper is more flexible

---

## Testing Strategy

### Unit Test the Helpers

```python
def test_extract_sources():
    """Test source extraction from .fc file."""
    sources = extract_sources_from_fc('tests/graphs/run22.fc')
    assert 'andor' in sources
    assert sources['andor']['dtype'] == 'Image'

def test_map_amitypes():
    """Test type mapping."""
    assert map_amitypes_to_config('amitypes.Array2d')['dtype'] == 'Image'
    assert map_amitypes_to_config('amitypes.int32')['integer'] == True

def test_resolve_path():
    """Test path resolution."""
    assert resolve_fc_path('test.fc') == 'tests/graphs/test.fc'
    assert resolve_fc_path('examples/test.fc') == 'examples/test.fc'
```

### Integration Test the Fixture

```python
@pytest.mark.parametrize('flowchart_from_file', [
    'run22.fc',
    ('run22.fc', 5),
], indirect=True)
def test_fixture_works(flowchart_from_file):
    """Test fixture creates valid flowchart."""
    fc, broker, comm = flowchart_from_file
    assert fc is not None
    assert broker is not None
    assert comm is not None
    assert len(fc.nodes(data='node')) > 0
```

---

## Estimated Implementation Time

- **Helper functions:** 1-2 hours
- **Main fixture:** 1-2 hours
- **Example tests:** 1 hour
- **Testing & debugging:** 1-2 hours
- **Total:** 4-7 hours

---

## Questions for User

Before implementation, please confirm:

1. **Return value:** Is `(fc, broker, comm)` acceptable? (Need `comm` for result verification)

2. **Default event count:** Is 100 events reasonable default? Or prefer 10?

3. **Fixture location:** Add to `tests/test_gui.py` or `tests/conftest.py`?
   - Recommendation: `test_gui.py` since it's GUI-specific

4. **Create example .fc files?** Should I create simple test .fc files like:
   - `tests/graphs/simple_roi_sum.fc` - Just ROI + Sum
   - `tests/graphs/projection_plot.fc` - Projection + Plot

5. **Timeout handling:** Should `wait_for_features()` raise assertion or return bool?
   - Return bool (as designed) = more flexible
   - Raise assertion = less test code

---

## Ready to Implement!

The design is complete and addresses all requirements:
- ✅ Loads .fc files with auto-mocked sources
- ✅ Limits execution to N events
- ✅ Supports result verification via comm.fetch()
- ✅ Simple, clean API
- ✅ Comprehensive examples

Once you approve the design, I can proceed with implementation!
