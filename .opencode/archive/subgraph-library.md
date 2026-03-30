# Subgraph Library Implementation Plan

## Overview
Add library management for subgraphs, similar to the existing "Manage Library" feature for nodes. Users can export subgraphs to files, import entire flowcharts as subgraphs, and drag-and-drop from a library to create multiple instances.

---

## Design Decisions

### Confirmed Decisions
1. **UI Organization**: Add third section to left dock (Sources → Operations → **Subgraphs**)
2. **File Format**: Reuse `.fc` format for subgraph files
3. **Export Flow**: Show dialog for name/description before exporting
4. **Import Support**: Import entire `.fc` files as subgraphs
5. **Source Nodes**: Include them in imported subgraphs (outputs become subgraph inputs)
6. **Boundary Detection**: 
   - **Inputs**: Auto-expose all unconnected input terminals
   - **Outputs**: User manually adds via context menu
7. **Name Conflicts**: Use existing auto-rename (`NodeType.0`, `NodeType.1`, etc.)
8. **Nested Subgraphs**: Not supported initially - warn and flatten if detected
9. **Multiple Instances**: Each drag from library creates independent copy with unique names

---

## Architecture

### New Files to Create

#### 1. `ami/flowchart/SubgraphLibrary.py`
```python
class SubgraphLibrary:
    """Library of subgraph templates that can be instantiated"""
    
    def __init__(self):
        self.subgraphList = OrderedDict()  # {name: template}
        self.subgraphTree = OrderedDict()  # Tree structure for UI
        
    def addSubgraph(self, name, template, paths):
        """Register a subgraph template"""
        
    def getSubgraph(self, name):
        """Get subgraph template by name"""
        
    def removeSubgraph(self, name):
        """Remove a subgraph from library"""
        
    def hasSubgraph(self, name):
        """Check if subgraph exists in library"""

class SubgraphTemplate:
    """Template for creating subgraph instances"""
    
    def __init__(self, name, description, state):
        self.name = name
        self.description = description
        self.nodes = state['nodes']
        self.connects = state['connects']
        self.source_file = state.get('source_file')
        self.inputs = []  # Auto-detected on load
        self.outputs = []
```

### Files to Modify

#### 2. `ami/flowchart/Flowchart.py`

**Add methods:**
- `exportSubgraph(subgraph_name, fileName)` - Export existing subgraph to file
- `importSubgraphFromFile(fileName, pos)` - Import .fc file and create subgraph instance
- `instantiateSubgraphFromLibrary(template_name, pos)` - Create instance from library
- `_detectBoundaryTerminalsForImport(state, node_mapping)` - Find unconnected inputs
- `_showExportDialog(default_name, default_desc)` - Name/description dialog
- `_showNestedSubgraphWarning(num_subgraphs)` - Warning for nested subgraphs
- `_generateUniqueSubgraphName(base_name)` - Generate unique subgraph name
- `_generateUniqueNodeName(base_name)` - Generate unique node name

**Add attributes:**
- `self.subgraph_library` - SubgraphLibrary instance

#### 3. `ami/flowchart/Editor.py`

**Add `SubgraphLibraryEditor` class:**
```python
class SubgraphLibraryEditor(QtWidgets.QWidget):
    """Editor for managing subgraph library (similar to LibraryEditor)"""
    
    sigApplyClicked = QtCore.Signal()
    
    def __init__(self, ctrlWidget, library):
        # UI: Load Files, Load Directory, Tree, Apply buttons
        
    def loadFile(self):
        """Load .fc files as subgraph templates"""
        
    def loadDirectory(self):
        """Load directory of .fc files"""
        
    def fileDialogFilesSelected(self, paths):
        """Parse .fc files and add to tree"""
        
    def applyClicked(self):
        """Add selected subgraphs to library"""
```

**Modify `FlowchartCtrlWidget.__init__`:**
- Add `self.subgraphLibraryEditor`
- Add "Manage Subgraph Library" button
- Add third tree section to left dock (subgraph_model, subgraph_search, subgraph_tree)

#### 4. `ami/flowchart/FlowchartGraphicsView.py`

**Modify `FlowchartViewBox.dropEvent`:**
```python
def dropEvent(self, ev):
    # ... existing code for nodes and sources ...
    
    # NEW: Handle subgraph drops from library
    try:
        if self.widget.chart.subgraph_library.hasSubgraph(node):
            self.widget.chart.instantiateSubgraphFromLibrary(
                node, 
                pos=self.mapToView(ev.pos())
            )
            ev.accept()
            return
    except KeyError:
        pass
```

#### 5. `ami/flowchart/SubgraphNode.py`

**Modify `SubgraphNodeGraphicsItem.buildMenu`:**
- Add "Export Subgraph..." action to context menu
- Wire up to `flowchart.exportSubgraph()`

---

## Implementation Phases

### Phase 1: Core Infrastructure
1. Create `SubgraphLibrary.py` with basic data structures
2. Add `SubgraphLibrary` instance to `Flowchart.__init__`
3. Implement `SubgraphTemplate` class

### Phase 2: Export Functionality
4. Implement `_showExportDialog()` in Flowchart
5. Implement `exportSubgraph()` in Flowchart
6. Add "Export Subgraph..." to context menu in SubgraphNode
7. Test: Export existing subgraph, verify .fc file structure

### Phase 3: Import/Detection
8. Implement `_detectBoundaryTerminalsForImport()` 
   - Parse state, find unconnected inputs
   - Return list of input terminals to expose
9. Implement `_showNestedSubgraphWarning()`
10. Implement `importSubgraphFromFile()`
    - Load .fc file
    - Detect nested subgraphs (warn if present)
    - Restore nodes with unique names
    - Restore connections
    - Create subgraph via `makeSubgraphFromSelection`
    - Expose detected boundary inputs
11. Test: Import simple .fc file, verify inputs exposed

### Phase 4: Library UI
12. Create `SubgraphLibraryEditor` widget
    - Copy structure from `LibraryEditor`
    - Modify to load .fc files instead of .py
13. Add subgraph tree to left dock in Editor
    - Add search box
    - Add tree view with drag enabled
    - Wire up to model
14. Add "Manage Subgraph Library" button
15. Test: Load files to library, verify tree population

### Phase 5: Drag-and-Drop
16. Implement `instantiateSubgraphFromLibrary()` in Flowchart
    - Get template from library
    - Call import logic with template data
17. Modify `dropEvent()` to handle subgraph drops
18. Test: Drag from library, verify instance creation
19. Test: Multiple drags create independent instances

### Phase 6: Persistence
20. Save library paths in flowchart state
    - Add `state['subgraph_library']` in `saveState()`
21. Restore library on load
    - Auto-reload library files in `restoreState()`
22. Test: Save flowchart, reload, verify library restored

### Phase 7: Polish & Edge Cases
23. Handle file path edge cases (absolute vs relative)
24. Add error handling for corrupted .fc files
25. Add tooltips showing subgraph descriptions
26. Test with complex flowcharts (10+ nodes)
27. Test name conflict resolution
28. Test with flowcharts containing subgraphs (flatten warning)

---

## Key Algorithms

### Export Subgraph

**Location:** `ami/flowchart/Flowchart.py`

```python
def exportSubgraph(self, subgraph_name, fileName=None):
    """Export an existing subgraph to a .fc file
    
    Args:
        subgraph_name: Name of the subgraph in self._subgraphs
        fileName: Path to save file (optional, shows dialog if None)
    """
    # 1. Show dialog for name/description
    name, desc = self._showExportDialog(subgraph_name, '')
    if not name:
        return
    
    # 2. Show file dialog if no filename provided
    if fileName is None:
        fileName = self._showSaveFileDialog(
            title="Export Subgraph",
            default_name=f"{name}.fc"
        )
        if not fileName:
            return
    
    # 3. Get subgraph data
    sg_data = self._subgraphs[subgraph_name]
    
    # 4. Collect nodes in subgraph
    nodes = []
    for node_name in sg_data['nodes']:
        node = self._graph.nodes[node_name]['node']
        nodes.append({
            'class': type(node).__name__,
            'name': node_name,
            'state': node.saveState()
        })
    
    # 5. Collect internal connections only
    connects = []
    for from_node, to_node, data in self._graph.edges(data=True):
        if from_node in sg_data['nodes'] and to_node in sg_data['nodes']:
            connects.append((from_node, data['from_term'], 
                           to_node, data['to_term']))
    
    # 6. Create state dict
    state = {
        'subgraph_metadata': {
            'name': name,
            'description': desc
        },
        'nodes': nodes,
        'connects': connects,
        'views': {
            'root': sg_data['view'].viewBox().saveState()
        }
    }
    
    # 7. Save to file
    with open(fileName, 'w') as f:
        json.dump(state, f, indent=2, cls=TypeEncoder)
    
    self.widget().updateStatus(f"Exported subgraph to: {fileName}")
```

### Import Flowchart as Subgraph

**Location:** `ami/flowchart/Flowchart.py`

```python
def importSubgraphFromFile(self, fileName, pos=None):
    """Import a .fc file and create a subgraph instance
    
    Args:
        fileName: Path to .fc file
        pos: Position for subgraph placeholder (optional)
        
    Returns:
        subgraph_name: Name of created subgraph, or None if cancelled
    """
    # 1. Load file
    with open(fileName, 'r') as f:
        state = json.load(f)
    
    # 2. Check for nested subgraphs
    if 'subgraphs' in state and state['subgraphs']:
        if not self._showNestedSubgraphWarning(len(state['subgraphs'])):
            return None
    
    # 3. Generate unique subgraph name
    base_name = state.get('subgraph_metadata', {}).get('name', 
                    os.path.splitext(os.path.basename(fileName))[0])
    name = self._generateUniqueSubgraphName(base_name)
    
    # 4. Restore nodes with unique names
    node_mapping = {}  # old_name -> new_name
    restored_nodes = []
    
    for node_state in state['nodes']:
        old_name = node_state['name']
        new_name = old_name  # createNode will auto-rename if conflict
        
        # Create node
        if node_state['class'] == 'SourceNode':
            # Handle SourceNode specially
            terminals = node_state['state']['terminals']
            # Eval ttype strings
            for term_name, term_info in terminals.items():
                if isinstance(term_info['ttype'], str):
                    term_info['ttype'] = eval(term_info['ttype'])
            node = SourceNode(name=new_name, terminals=terminals)
            self.addNode(node=node)
        else:
            node = self.createNode(node_state['class'], name=new_name, 
                                  prompt=False)
        
        node_mapping[old_name] = node.name()  # Get actual assigned name
        
        node.blockSignals(True)
        node.restoreState(node_state['state'])
        node.blockSignals(False)
        restored_nodes.append(node)
    
    # 5. Restore connections with mapped names
    for from_node, from_term, to_node, to_term in state['connects']:
        term1 = self._graph.nodes[node_mapping[from_node]]['node'][from_term]
        term2 = self._graph.nodes[node_mapping[to_node]]['node'][to_term]
        term1.connectTo(term2, signal=False)
        
        # Add edge to graph
        self._graph.add_edge(
            node_mapping[from_node], 
            node_mapping[to_node],
            key=f"{node_mapping[from_node]}.{from_term}->{node_mapping[to_node]}.{to_term}",
            from_term=from_term,
            to_term=to_term
        )
    
    # 6. Create subgraph from restored nodes
    self.makeSubgraphFromSelection(
        nodes=restored_nodes,
        name=name,
        pos=pos
    )
    
    # 7. Detect and expose boundary inputs
    inputs = self._detectBoundaryTerminalsForImport(state, node_mapping)
    sg_placeholder = self._subgraphs[name]['placeholder']
    
    for inp in inputs:
        mapped_node_name = node_mapping[inp['node']]
        term_name = f"{mapped_node_name}.{inp['terminal']}"
        # Check if already exists (from makeSubgraphFromSelection)
        if term_name not in sg_placeholder.inputs():
            sg_placeholder.addInput(name=term_name, ttype=inp['ttype'])
    
    return name
```

### Detect Boundary Inputs

**Location:** `ami/flowchart/Flowchart.py`

```python
def _detectBoundaryTerminalsForImport(self, state, node_mapping):
    """Find unconnected input terminals to expose as subgraph inputs
    
    Args:
        state: Flowchart state dict from .fc file
        node_mapping: Dict mapping old node names to new node names
        
    Returns:
        List of dicts with keys: 'node', 'terminal', 'ttype'
    """
    # Build set of connected inputs
    connected_inputs = set()
    for from_node, from_term, to_node, to_term in state['connects']:
        connected_inputs.add((to_node, to_term))
    
    # Find dangling inputs
    inputs = []
    for node_state in state['nodes']:
        node_name = node_state['name']
        terminals = node_state['state'].get('terminals', {})
        
        for term_name, term_info in terminals.items():
            if term_info['io'] == 'in':
                if (node_name, term_name) not in connected_inputs:
                    # Parse ttype string to actual type
                    if isinstance(term_info['ttype'], str):
                        ttype = eval(term_info['ttype'])
                    else:
                        ttype = term_info['ttype']
                    
                    inputs.append({
                        'node': node_name,
                        'terminal': term_name,
                        'ttype': ttype
                    })
    
    return inputs
```

### Instantiate from Library

**Location:** `ami/flowchart/Flowchart.py`

```python
def instantiateSubgraphFromLibrary(self, template_name, pos=None):
    """Create a new instance of a subgraph from the library
    
    Args:
        template_name: Name of template in library
        pos: Position for placeholder
        
    Returns:
        subgraph_name: Name of created subgraph
    """
    # Get template
    template = self.subgraph_library.getSubgraph(template_name)
    
    # Create state dict from template
    state = {
        'subgraph_metadata': {
            'name': template.name,
            'description': template.description
        },
        'nodes': template.nodes,
        'connects': template.connects
    }
    
    # Use import logic to create instance
    return self.importSubgraphFromFile(state, pos=pos, from_dict=True)
```

---

## UI Components

### Export Dialog

**Location:** `ami/flowchart/Flowchart.py`

```python
def _showExportDialog(self, default_name, default_desc='', isImport=False):
    """Show dialog for entering subgraph name and description
    
    Returns:
        (name, description) tuple, or (None, None) if cancelled
    """
    dialog = QtWidgets.QDialog()
    dialog.setWindowTitle("Import Subgraph" if isImport else "Export Subgraph")
    
    layout = QtWidgets.QVBoxLayout()
    
    # Name field
    name_label = QtWidgets.QLabel("Name:")
    name_edit = QtWidgets.QLineEdit(default_name)
    layout.addWidget(name_label)
    layout.addWidget(name_edit)
    
    # Description field
    desc_label = QtWidgets.QLabel("Description:")
    desc_edit = QtWidgets.QTextEdit()
    desc_edit.setPlainText(default_desc)
    desc_edit.setMaximumHeight(100)
    layout.addWidget(desc_label)
    layout.addWidget(desc_edit)
    
    # Buttons
    button_box = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
    )
    button_box.accepted.connect(dialog.accept)
    button_box.rejected.connect(dialog.reject)
    layout.addWidget(button_box)
    
    dialog.setLayout(layout)
    
    if dialog.exec_() == QtWidgets.QDialog.Accepted:
        return name_edit.text(), desc_edit.toPlainText()
    else:
        return None, None
```

### Nested Subgraph Warning

**Location:** `ami/flowchart/Flowchart.py`

```python
def _showNestedSubgraphWarning(self, num_subgraphs):
    """Show warning about nested subgraphs not being supported
    
    Returns:
        True if user accepts, False if cancelled
    """
    msg = QtWidgets.QMessageBox()
    msg.setIcon(QtWidgets.QMessageBox.Warning)
    msg.setWindowTitle("Nested Subgraphs Not Supported")
    msg.setText(
        f"This flowchart contains {num_subgraphs} subgraph(s).\n\n"
        "Nested subgraphs are not yet supported. "
        "The flowchart will be imported as a flat subgraph "
        "with all nodes at the same level.\n\n"
        "Original subgraph structure will be lost."
    )
    msg.setStandardButtons(
        QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
    )
    msg.setDefaultButton(QtWidgets.QMessageBox.Cancel)
    
    return msg.exec_() == QtWidgets.QMessageBox.Ok
```

### Subgraph Tree in Left Dock

**Location:** `ami/flowchart/Editor.py` - modify `Ui_Toolbar.setupUi`

```python
# Existing code creates source_tree and node_tree...

# NEW: Add subgraph tree
self.subgraph_model = build_model()
self.subgraph_search = QtWidgets.QLineEdit()
self.subgraph_search.setPlaceholderText('Search Subgraphs...')
self.subgraph_tree = build_tree(self.subgraph_model, parent)

# Add to dock (after node_tree)
self.node_dock.addWidget(self.subgraph_search, 5, 0, 1, 1)
self.node_dock.addWidget(self.subgraph_tree, 6, 0, 1, 1)
```

---

## Testing Strategy

### Unit Tests

**Test file:** `tests/test_subgraph_library.py`

```python
def test_export_subgraph(flowchart_with_subgraph, tmp_path):
    """Test exporting a subgraph to .fc file"""
    fc = flowchart_with_subgraph
    export_path = tmp_path / "exported.fc"
    
    fc.exportSubgraph("combined.0", str(export_path))
    
    assert export_path.exists()
    with open(export_path) as f:
        state = json.load(f)
    assert 'subgraph_metadata' in state
    assert 'nodes' in state
    assert 'connects' in state

def test_import_flowchart_as_subgraph(flowchart, tmp_path):
    """Test importing entire .fc file as subgraph"""
    fc = flowchart
    
    # Import example file
    sg_name = fc.importSubgraphFromFile('examples/complex_example.fc')
    
    assert sg_name in fc._subgraphs
    sg_data = fc._subgraphs[sg_name]
    assert len(sg_data['nodes']) > 0

def test_boundary_detection(flowchart):
    """Test detection of unconnected input terminals"""
    # Create test state with dangling inputs
    state = {
        'nodes': [
            {
                'name': 'Node1',
                'state': {
                    'terminals': {
                        'In': {'io': 'in', 'ttype': 'float'},
                        'Out': {'io': 'out', 'ttype': 'float'}
                    }
                }
            }
        ],
        'connects': []  # No connections
    }
    
    inputs = flowchart._detectBoundaryTerminalsForImport(state, {'Node1': 'Node1'})
    
    assert len(inputs) == 1
    assert inputs[0]['terminal'] == 'In'

def test_multiple_instances_from_library(flowchart):
    """Test creating multiple instances from library template"""
    fc = flowchart
    
    # Add to library (assuming template loaded)
    sg1 = fc.instantiateSubgraphFromLibrary('TestTemplate', pos=[0, 0])
    sg2 = fc.instantiateSubgraphFromLibrary('TestTemplate', pos=[100, 100])
    
    assert sg1 != sg2
    assert sg1 in fc._subgraphs
    assert sg2 in fc._subgraphs
```

### Integration Tests

1. **Full workflow test:**
   - Create flowchart with nodes
   - Make subgraph
   - Export to file
   - Clear flowchart
   - Import from file
   - Verify functionality

2. **Library persistence test:**
   - Load subgraphs to library
   - Save flowchart
   - Reload flowchart
   - Verify library restored

3. **Drag-and-drop test:**
   - Load library
   - Simulate drag from tree to flowchart
   - Verify instance created at correct position

### Manual Testing Checklist

- [ ] Export `subgraph.fc` subgraph to file
- [ ] Open new flowchart, import the exported file
- [ ] Verify unconnected inputs auto-exposed
- [ ] Manually add output terminals via context menu
- [ ] Add exported file to library via "Manage Subgraph Library"
- [ ] Drag 3 instances from library
- [ ] Verify each has unique names (e.g., `ROI.0`, `ROI.1`, `ROI.2`)
- [ ] Connect instances together in complex graph
- [ ] Save and reload flowchart
- [ ] Verify library paths restored
- [ ] Test importing flowchart with existing subgraphs (verify warning)
- [ ] Test with flowchart containing source nodes
- [ ] Test name conflict resolution

---

## File Structure Summary

```
ami/flowchart/
├── SubgraphLibrary.py          # NEW: Subgraph library class
├── Flowchart.py                # MODIFY: Add export/import methods
├── Editor.py                   # MODIFY: Add SubgraphLibraryEditor + tree
├── FlowchartGraphicsView.py    # MODIFY: Handle subgraph drops
└── SubgraphNode.py             # MODIFY: Add export context menu action
```

---

## Open Questions for Future Iteration

1. **Nested subgraphs**: How to support importing flowcharts that contain subgraphs?
   - Current: Flatten (warn user)
   - Future: Preserve nesting (requires recursive handling)
   
2. **Library organization**: Should library support folders/categories?
   - Current: Single flat list
   - Future: Tree with custom categories
   
3. **Subgraph versioning**: Track versions of subgraph templates?
   - Current: No versioning
   - Future: Version tracking with update notifications
   
4. **Output auto-detection**: Should we add smart detection for outputs?
   - Current: Manual only
   - Future: Auto-expose viewed/exported node inputs
   
5. **Rename after instantiation**: Allow renaming subgraph instances?
   - Current: Rename placeholder node name only
   - Future: Special handling for internal view names

6. **Relative vs absolute paths**: How to handle library file paths?
   - Current: Store as provided
   - Future: Option for relative paths in saved flowcharts

---

## Implementation Notes

### Current Behavior to Preserve

- Auto-rename on node name conflicts (lines 141-147 in `createNode`)
- Visual-only nodes skip `self._graph` (line 178 in `addNode`)
- Boundary detection for selected nodes (lines 235-307 in `makeSubgraphFromSelection`)
- Existing drag-and-drop from node/source libraries

### Edge Cases to Handle

1. **Corrupted .fc files**: Wrap JSON parsing in try-except
2. **Missing node types**: Skip nodes with undefined classes, warn user
3. **Type checking failures**: Handle mypy type check errors during connection restore
4. **Empty subgraphs**: Prevent export of subgraphs with no nodes
5. **Circular references**: Not possible with current DAG structure, but document assumption

### Performance Considerations

- Large flowcharts (100+ nodes): May need progress dialog for import
- Library with many items (50+ subgraphs): Tree search becomes important
- Memory: Each template stores full node state (acceptable for reasonable library sizes)

---

## Success Criteria

The implementation will be considered successful when:

1. ✅ User can export existing subgraph to `.fc` file with custom name/description
2. ✅ User can import any `.fc` file as a subgraph into current flowchart
3. ✅ Unconnected inputs are automatically exposed on import
4. ✅ User can add subgraphs to library via "Manage Subgraph Library"
5. ✅ Subgraphs appear in searchable tree in left dock
6. ✅ User can drag-and-drop from library to create instances
7. ✅ Multiple instances have independent state and unique names
8. ✅ Library paths persist across save/reload
9. ✅ Warning shown for flowcharts with nested subgraphs
10. ✅ All existing subgraph functionality continues to work

---

## Timeline Estimate

- **Phase 1 (Core)**: 2-3 hours
- **Phase 2 (Export)**: 2-3 hours  
- **Phase 3 (Import)**: 4-5 hours
- **Phase 4 (Library UI)**: 3-4 hours
- **Phase 5 (Drag-drop)**: 2-3 hours
- **Phase 6 (Persistence)**: 2-3 hours
- **Phase 7 (Polish)**: 3-4 hours

**Total estimated time**: 18-25 hours

Note: This is an iterative plan. We expect to refine and adjust as we encounter edge cases during implementation.
