# Design: GUI Test Fixture for Loading .fc Files

**Date:** 2026-03-25  
**Goal:** Create flexible test fixtures for loading saved .fc flowchart files  
**Question:** Do we need separate fixtures for random sources vs psana sources?

---

## Current State Analysis

### Existing Fixtures

**1. `flowchart` fixture (tests/test_gui.py:134)**
- Creates AMI process with specified data source (via `request.param`)
- Creates Flowchart but does NOT load any .fc file
- Returns: `(fc, broker)`
- Usage: `@pytest.mark.parametrize('flowchart', ['static'], indirect=True)`
- Data source types: 'static', 'random', 'psana', etc.

**2. `flowchart_hdf` fixture (tests/test_gui.py:188)**
- Creates AMI process with HDF5 data source
- Creates Flowchart AND loads .fc file
- Parameters: `(hdf_file, fc_file)` tuple
- Returns: `(fc, broker, comm)`
- Example: `@pytest.mark.parametrize('flowchart_hdf', [('run22.h5', 'run22.fc')], indirect=True)`

**3. `workerjson` fixture (tests/conftest.py:167)**
- Creates configuration for static/random data source
- Session-scoped
- Generates random data based on config

### Key Differences: Random vs Psana Sources

**Random/Static Sources:**
- Defined in `workerjson` fixture
- Configuration in worker.json
- Data types: delta_t (Scalar), cspad (Image), laser (Scalar)
- No real data files needed

**Psana Sources:**
- Requires actual .xtc2 or .h5 files
- Different data types from real detectors
- Needs psana library available

**HDF5 Sources:**
- Uses pre-recorded data files
- `flowchart_hdf` fixture handles this case
- Can replay specific experiment data

---

## Design Options

### Option 1: Single Unified Fixture (Recommended)

Create one flexible fixture that can handle any data source type and optionally load .fc files.

```python
@pytest.fixture(scope='function')
def flowchart_with_file(request, workerjson, broker, ipc_dir, graphmgr_addr, dmypy, qtbot):
    """
    Create flowchart with optional .fc file loading.
    
    Usage:
        @pytest.mark.parametrize('flowchart_with_file', [
            ('static', None),                    # No .fc file
            ('static', 'test_graph.fc'),         # Load .fc from tests/graphs/
            ('static', 'examples/complex.fc'),   # Load .fc from examples/
        ], indirect=True)
        def test_something(flowchart_with_file):
            fc, broker = flowchart_with_file
    
    Parameters (via request.param):
        - Tuple: (data_source, fc_file_path)
        - data_source: 'static', 'random', 'psana://...', 'hdf5://...'
        - fc_file_path: Path to .fc file (relative to project root) or None
    """
```

**Pros:**
- Single fixture for all use cases
- Flexible - handles any data source + optional .fc file
- Consistent API across tests
- Easy to extend

**Cons:**
- Slightly more complex parameter structure
- Need to handle different data source types internally

### Option 2: Separate Fixtures per Data Source

Create specialized fixtures for each common case.

```python
@pytest.fixture(scope='function')
def flowchart_static_with_file(request, ...):
    """Static data source + .fc file"""
    pass

@pytest.fixture(scope='function')
def flowchart_psana_with_file(request, ...):
    """Psana data source + .fc file"""
    pass

@pytest.fixture(scope='function')
def flowchart_hdf_with_file(request, ...):
    """HDF5 data source + .fc file (already exists)"""
    pass
```

**Pros:**
- Clear separation of concerns
- Type-specific handling

**Cons:**
- Code duplication
- More fixtures to maintain
- Not as flexible

### Option 3: Extend Existing `flowchart` Fixture

Modify the existing `flowchart` fixture to optionally accept .fc file path.

```python
@pytest.fixture(scope='function')
def flowchart(request, workerjson, broker, ipc_dir, graphmgr_addr, dmypy, qtbot):
    # request.param can be:
    # - String: 'static' (existing behavior)
    # - Tuple: ('static', 'path/to/file.fc') (new behavior)
```

**Pros:**
- Extends existing fixture
- Backward compatible
- No new fixture names

**Cons:**
- Changes existing API (could break tests if not careful)
- Mixed responsibilities

---

## Recommended Design: Option 1 (New Unified Fixture)

### Fixture Implementation Plan

**Name:** `flowchart_with_file`

**Location:** `tests/test_gui.py` (keep GUI-specific fixtures together)

**Parameters Structure:**
```python
# Simple tuple: (data_source, fc_file)
('static', None)                          # Just static data, no .fc
('static', 'my_graph.fc')                 # Static + .fc from tests/graphs/
('static', 'examples/complex.fc')         # Static + .fc from examples/
('random', 'my_graph.fc')                 # Random + .fc
('hdf5://path/to/data.h5', 'graph.fc')   # HDF5 + .fc
```

**Return Value:**
```python
(fc, broker)  # Same as existing flowchart fixture
```

**Features:**
1. Accepts any data source type (static, random, psana, hdf5)
2. Optionally loads .fc file
3. Adds widget to qtbot if .fc file is loaded
4. Handles file path resolution (tests/graphs/, examples/, absolute paths)
5. Proper cleanup on teardown

### Alternative: Simple Wrapper Approach

If we want minimal changes, create a helper fixture that wraps the existing `flowchart`:

```python
@pytest.fixture(scope='function')
def flowchart_load_file(flowchart, qtbot, request):
    """
    Wrapper around flowchart fixture that loads .fc file.
    
    Usage:
        @pytest.fixture
        def my_flowchart(flowchart_load_file):
            return flowchart_load_file
        
        @pytest.mark.parametrize('flowchart', ['static'], indirect=True)
        @pytest.mark.parametrize('flowchart_load_file', ['my_graph.fc'], indirect=True)
        def test_something(flowchart_load_file):
            fc, broker = flowchart_load_file
    """
    fc, broker = flowchart
    fc_file = request.param
    
    if fc_file:
        qtbot.addWidget(fc.widget())
        fc.loadFile(resolve_fc_path(fc_file))
    
    return (fc, broker)
```

**Pros:**
- Minimal code
- Reuses existing infrastructure
- Composable

**Cons:**
- Requires two parametrize decorators
- Less intuitive API

---

## Questions for User

### Question 1: Fixture Design
**Which approach do you prefer?**

A. **Option 1: New unified fixture `flowchart_with_file`**
   - Single fixture handles all data sources + optional .fc file
   - Usage: `@pytest.mark.parametrize('flowchart_with_file', [('static', 'graph.fc')], indirect=True)`

B. **Option 2: Separate fixtures per data source**
   - `flowchart_static_with_file`, `flowchart_psana_with_file`, etc.
   - Usage: `@pytest.mark.parametrize('flowchart_static_with_file', ['graph.fc'], indirect=True)`

C. **Option 3: Wrapper fixture**
   - Wrap existing `flowchart` fixture
   - Usage: Two `@pytest.mark.parametrize` decorators

### Question 2: Do We Need Random AND Psana Variants?

**Background:**
- Random/static sources: Defined in workerjson, generate fake data, fast, no dependencies
- Psana sources: Require real data files (.xtc2/.h5), slower, need psana library

**Question:**
- Do you need to test .fc files with **both** random and psana data sources?
- Or is testing with random/static data sufficient for most .fc file tests?

**Recommendation:** Start with random/static support, add psana support later if needed.

### Question 3: File Path Resolution

**How should we resolve .fc file paths?**

A. **Auto-search multiple locations:**
   ```python
   # Searches: tests/graphs/, examples/, project root
   flowchart_with_file(('static', 'my_graph.fc'))
   ```

B. **Require explicit paths:**
   ```python
   # Must specify full path relative to project root
   flowchart_with_file(('static', 'tests/graphs/my_graph.fc'))
   ```

C. **Default to tests/graphs/, allow overrides:**
   ```python
   # Defaults to tests/graphs/
   flowchart_with_file(('static', 'my_graph.fc'))
   # Or specify full path
   flowchart_with_file(('static', 'examples/complex.fc'))
   ```

**Recommendation:** Option C (default to tests/graphs/, allow overrides)

### Question 4: Return Value

**What should the fixture return?**

A. `(fc, broker)` - Same as existing `flowchart` fixture
B. `(fc, broker, comm)` - Same as `flowchart_hdf` (includes GraphCommHandler)
C. Just `fc` - Simplest, can access broker via other fixtures

**Recommendation:** Option A for consistency with existing `flowchart` fixture

---

## Example Usage (After Implementation)

```python
# Test 1: Load simple .fc file with static data
@pytest.mark.parametrize('flowchart_with_file', [
    ('static', 'simple_roi.fc')
], indirect=True)
def test_simple_graph(flowchart_with_file):
    fc, broker = flowchart_with_file
    
    # Graph already loaded from .fc file
    assert 'Roi2D.0' in fc.nodes(data='node')
    assert len(fc._graph.edges()) > 0

# Test 2: Load complex .fc file from examples
@pytest.mark.parametrize('flowchart_with_file', [
    ('static', 'examples/complex_example.fc')
], indirect=True)
def test_complex_graph(flowchart_with_file):
    fc, broker = flowchart_with_file
    
    # Test applying the graph
    ctrl = fc.widget()
    ctrl.applyClicked()
    # ... more tests

# Test 3: Multiple .fc files in one test
@pytest.mark.parametrize('flowchart_with_file', [
    ('static', 'graph1.fc'),
    ('static', 'graph2.fc'),
    ('static', 'graph3.fc'),
], indirect=True)
def test_multiple_graphs(flowchart_with_file):
    fc, broker = flowchart_with_file
    # Each parametrization loads a different .fc file
    assert len(fc.nodes(data='node')) > 0
```

---

## Implementation Checklist

Once design is approved:

- [ ] Decide on fixture approach (Option 1, 2, or 3)
- [ ] Decide on data source support (random only, or random + psana)
- [ ] Decide on file path resolution strategy
- [ ] Implement fixture in tests/test_gui.py or tests/conftest.py
- [ ] Add helper function for path resolution
- [ ] Create example .fc files in tests/graphs/ if needed
- [ ] Write example tests demonstrating usage
- [ ] Document fixture in tests/TEST_README.md (if exists) or docstring
- [ ] Test with existing .fc files (run22.fc, examples/complex_example.fc)

---

## Additional Considerations

### Existing .fc Files Available for Testing
```
./tests/graphs/run22.fc          # HDF5-based graph
./examples/complex_example.fc    # Complex example
./examples/complex_example_psana.fc  # Psana-based
```

### Potential Issues

1. **Graph compatibility:** .fc files might reference nodes/sources not available in test environment
   - Solution: Create simple test-specific .fc files

2. **Data source mismatch:** .fc file expects psana but test uses random
   - Solution: Document which .fc files work with which data sources

3. **Widget initialization:** Some .fc files might need widget to be visible
   - Solution: Always add widget to qtbot when loading .fc file

---

## Next Steps

Please review and answer the questions above so I can create the implementation plan:

1. Which fixture design approach? (Option 1, 2, or 3)
2. Do we need psana support, or is random/static sufficient?
3. How should we resolve file paths? (Auto-search, explicit, or default with override)
4. What should the fixture return? (fc+broker, fc+broker+comm, or just fc)

After your input, I'll create a detailed implementation plan!
