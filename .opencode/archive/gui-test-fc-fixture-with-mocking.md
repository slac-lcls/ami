# Design: GUI Test Fixture for .fc Files with Source Mocking

**Date:** 2026-03-25  
**Approach:** Static data source with mocked sources from .fc file  
**Goal:** Single fixture that loads .fc files and auto-generates matching mock data sources

---

## User Input

> "maybe just the static source is fine if we can mock the required sources from a fc file?"

**Excellent idea!** This approach:
- ✅ Uses fast static/random data generation (no psana required)
- ✅ Auto-configures sources by parsing the .fc file
- ✅ Single fixture handles any .fc file
- ✅ Simple, clean API

---

## How Source Mocking Works

### Step 1: Parse .fc File to Find SourceNodes

Example from `tests/graphs/run22.fc`:
```json
{
  "class": "SourceNode",
  "name": "andor",
  "state": {
    "terminals": {
      "Out": {
        "ttype": "amitypes.Array2d"
      }
    }
  }
}
```

**Extract:**
- Source name: `"andor"`
- Data type: `"amitypes.Array2d"` → Maps to `"Image"` dtype

### Step 2: Generate Mock Configuration

Create worker.json config for static data source:
```python
cfg = {
    "interval": 0.01,
    "init_time": 0.1,
    "bound": 100,
    "repeat": True,
    "files": "data.xtc2",
    "config": {
        "andor": {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [512, 512]},
        "waveforms": {"dtype": "Image", "pedestal": 5, "width": 1, "shape": [512, 512]},
    }
}
```

### Step 3: Start AMI with Mock Config

AMI's static data source generates random data matching these specs.

### Step 4: Load .fc File

Flowchart loads the .fc file, connects to the mock sources.

---

## Type Mapping

Map amitypes to static data source dtypes:

| amitypes Type | Static Source dtype | Config |
|---------------|---------------------|--------|
| `amitypes.Array1d` | `"Waveform"` | `{"dtype": "Waveform", "length": 1024}` |
| `amitypes.Array2d` | `"Image"` | `{"dtype": "Image", "shape": [512, 512]}` |
| `amitypes.Array3d` | `"Image"` (3D) | `{"dtype": "Image", "shape": [100, 512, 512]}` |
| `int`, `amitypes.int*` | `"Scalar"` | `{"dtype": "Scalar", "range": [0, 100], "integer": True}` |
| `float`, `amitypes.float*` | `"Scalar"` | `{"dtype": "Scalar", "range": [0.0, 100.0]}` |
| Other | Default to Scalar | `{"dtype": "Scalar", "range": [0, 100]}` |

---

## Fixture Design

### Fixture: `flowchart_from_file`

**Location:** `tests/test_gui.py` or `tests/conftest.py`

**Signature:**
```python
@pytest.fixture(scope='function')
def flowchart_from_file(request, broker, ipc_dir, graphmgr_addr, dmypy, qtbot, tmp_path):
    """
    Create flowchart with auto-mocked sources from .fc file.
    
    Usage:
        @pytest.mark.parametrize('flowchart_from_file', [
            'run22.fc',                      # From tests/graphs/
            'examples/complex_example.fc',   # From examples/
        ], indirect=True)
        def test_something(flowchart_from_file):
            fc, broker = flowchart_from_file
            # Graph already loaded, sources mocked
    
    Parameters (via request.param):
        - String: Path to .fc file (relative to project root)
          - Defaults to tests/graphs/ if no directory specified
          - Example: 'my_graph.fc' → 'tests/graphs/my_graph.fc'
          - Example: 'examples/complex.fc' → 'examples/complex.fc'
    
    Returns:
        (fc, broker): Flowchart and MessageBroker instances
    """
```

### Implementation Steps

1. **Parse .fc file** to extract SourceNodes
2. **Generate worker.json** with mocked sources
3. **Start AMI** with static data source
4. **Create Flowchart** and initialize
5. **Load .fc file** into flowchart
6. **Return** (fc, broker)

---

## Implementation Plan

### Helper Function: `extract_sources_from_fc`

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
        str: Absolute path to .fc file
        
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

### Main Fixture Implementation

```python
@pytest.fixture(scope='function')
def flowchart_from_file(request, broker, ipc_dir, graphmgr_addr, dmypy, qtbot, tmp_path):
    """Create flowchart with auto-mocked sources from .fc file."""
    try:
        from pytest_cov.embed import cleanup_on_sigterm
        cleanup_on_sigterm()
    except ImportError:
        pass
    
    # Get .fc file path
    fc_file = request.param
    fc_path = resolve_fc_path(fc_file)
    
    # Extract source configurations from .fc file
    source_config = extract_sources_from_fc(fc_path)
    
    # Create worker.json with mocked sources
    cfg = {
        "interval": 0.01,
        "init_time": 0.1,
        "bound": 100,
        "repeat": True,
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
        # Wait for AMI to be ready
        with GraphCommHandler(graphmgr_addr.name, graphmgr_addr.comm) as comm:
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
            
            yield (fc, broker)
    
    except Exception as e:
        print(f"error setting up flowchart_from_file fixture: {e}")
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

## Example Usage

### Test 1: Simple .fc File Test

```python
@pytest.mark.parametrize('flowchart_from_file', ['run22.fc'], indirect=True)
def test_run22_graph(flowchart_from_file):
    """Test loading run22.fc with auto-mocked sources."""
    fc, broker = flowchart_from_file
    
    # Sources were auto-detected and mocked!
    assert 'andor' in fc.nodes(data='node')
    assert 'waveforms' in fc.nodes(data='node')
    
    # Graph structure loaded from .fc file
    assert 'Projection.0' in fc.nodes(data='node')
    assert len(fc._graph.edges()) > 0
    
    # Apply the graph
    ctrl = fc.widget()
    ctrl.applyClicked()
    
    # Verify graph was submitted
    assert ctrl.graphCommHandler.graphVersion > 0
```

### Test 2: Multiple .fc Files

```python
@pytest.mark.parametrize('flowchart_from_file', [
    'run22.fc',
    'examples/complex_example.fc',
], indirect=True)
def test_various_graphs(flowchart_from_file):
    """Test loading various .fc files."""
    fc, broker = flowchart_from_file
    
    # Each .fc file has its sources auto-mocked
    assert len(fc.nodes(data='node')) > 0
    
    # Can apply any graph
    ctrl = fc.widget()
    ctrl.applyClicked()
```

### Test 3: Test Specific Node Functionality

```python
@pytest.mark.parametrize('flowchart_from_file', ['my_roi_graph.fc'], indirect=True)
def test_roi_functionality(flowchart_from_file):
    """Test ROI node with pre-built graph."""
    fc, broker = flowchart_from_file
    
    # Graph already has ROI node configured
    roi_node = fc.nodes(data='node')['Roi2D.0']
    
    # Test ROI controls
    ctrl = fc.widget()
    # ... test ROI-specific functionality
```

---

## Advantages of This Approach

1. **No psana dependency** - Tests run fast with static data
2. **Auto-configuration** - Sources detected from .fc file
3. **Single fixture** - Works with any .fc file
4. **Simple API** - Just pass .fc filename
5. **Flexible** - Easy to extend with custom type mappings
6. **Testable** - Can test real .fc files from examples/

---

## Limitations & Solutions

### Limitation 1: Complex Data Types

**Problem:** .fc file uses custom amitypes that don't map cleanly to static source types

**Solution:** 
- Add more type mappings in `map_amitypes_to_config()`
- Default to sensible Scalar/Image types
- Document which types are supported

### Limitation 2: Source Names Must Match

**Problem:** .fc file expects source name "epix_1" but we generate "epix1"

**Solution:**
- Use exact names from .fc file (we already do this)
- Static data source accepts any name

### Limitation 3: Data Shapes Don't Match Node Expectations

**Problem:** ROI expects 1024x1024 but we generate 512x512

**Solution:**
- Extract shape hints from downstream nodes if needed
- Use configurable default shapes
- Allow override via fixture parameter (future enhancement)

---

## Future Enhancements (Optional)

### Enhancement 1: Custom Source Config Override

Allow overriding auto-detected config:
```python
@pytest.mark.parametrize('flowchart_from_file', [
    ('run22.fc', {'andor': {'shape': [1024, 1024]}})  # Override shape
], indirect=True)
```

### Enhancement 2: Source Type Hints in .fc Files

Add metadata to .fc files to help mocking:
```json
{
  "source_hints": {
    "andor": {"shape": [1024, 1024], "dtype": "uint16"}
  }
}
```

### Enhancement 3: Validation Mode

Check if graph can execute with mocked data:
```python
@pytest.mark.parametrize('flowchart_from_file', ['graph.fc'], indirect=True)
def test_graph_validation(flowchart_from_file):
    fc, broker = flowchart_from_file
    ctrl = fc.widget()
    
    # Apply and check for errors
    ctrl.applyClicked()
    assert ctrl.graphCommHandler.graphVersion > 0
    # Wait for processing
    qtbot.wait(1000)
    # Check no nodes have exceptions
    for name, gnode in fc._graph.nodes().items():
        assert not gnode['node'].exception
```

---

## Implementation Checklist

- [ ] Create helper functions:
  - [ ] `extract_sources_from_fc(fc_path)`
  - [ ] `map_amitypes_to_config(ttype)`
  - [ ] `resolve_fc_path(fc_file)`

- [ ] Implement `flowchart_from_file` fixture in `tests/test_gui.py`

- [ ] Test with existing .fc files:
  - [ ] `tests/graphs/run22.fc`
  - [ ] `examples/complex_example.fc`

- [ ] Create simple test .fc files for unit testing:
  - [ ] Simple ROI graph
  - [ ] Projection + histogram graph
  - [ ] Multi-source graph

- [ ] Write example tests demonstrating usage

- [ ] Document fixture in docstring

---

## Questions Resolved

1. **Separate fixtures for random vs psana?** → NO, single fixture with mocking
2. **File path resolution?** → Default to `tests/graphs/`, allow full paths
3. **Return value?** → `(fc, broker)` to match existing `flowchart` fixture
4. **Design approach?** → Source mocking from .fc file

---

## Next Steps

Ready to implement! The design is clear:

1. **Parse .fc file** → Extract SourceNodes and types
2. **Generate config** → Map amitypes to static source configs
3. **Start AMI** → With auto-generated worker.json
4. **Load .fc file** → Into flowchart
5. **Return** → (fc, broker) ready for testing

Estimated implementation time: ~2-3 hours
- Helper functions: 1 hour
- Fixture implementation: 1 hour
- Testing & refinement: 1 hour

Would you like me to create a detailed implementation plan with the exact code to add?
