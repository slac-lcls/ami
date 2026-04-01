# Phase 1: Shared Memory Widget State Management

**Status**: Ready to Implement  
**Timeline**: 7 weeks  
**Goal**: Replace async checkpoint messages with shared memory for all node state  
**Dependencies**: None (foundational work)  

---

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [Architecture Design](#architecture-design)
4. [Design Decisions](#design-decisions)
5. [Implementation Plan](#implementation-plan)
6. [Testing Strategy](#testing-strategy)
7. [Success Criteria](#success-criteria)
8. [Migration & Compatibility](#migration--compatibility)

---

## Overview

### Current Problem (From Lessons Learned)

When a user replaces a source node (e.g., `cspad` → `waveform2`):
- ❌ Filter conditions still show old source name
- ❌ If widget window is closed, state is lost
- ❌ Reopening window shows stale or missing data

**Root Cause**: State lives in NodeProcess (separate process), only synced via async checkpoint messages. When widget is closed, state can't be updated.

---

### Solution: Shared Memory State

Store **ALL node state** in shared memory accessible from both:
- **Flowchart Process** (can read/write anytime, even when widget closed)
- **NodeProcess** (reads on startup, writes on changes)

**Result**: 
- ✅ Auto-replace works even when widget closed
- ✅ State always available (no waiting for checkpoints)
- ✅ Crash recovery (state persists in memory)

---

## Problem Statement

### Current Architecture Issues

```
Flowchart Process              NodeProcess (separate)
┌──────────────┐              ┌──────────────────┐
│ Node         │              │ Node instance    │
│ (structure)  │              │ ctrlWidget       │
│              │  ◄─ZMQ msg──│ widget           │
│              │  checkpoint  │                  │
└──────────────┘              └──────────────────┘
```

**Problems**:
1. **Async checkpoints**: State updates sent via ZMQ messages (can be lost)
2. **Widget-dependent**: Can't get state when widget closed
3. **No auto-replace**: Can't update state when widget closed
4. **Complex**: Two-way message passing for state sync

---

### Proposed Architecture

```
Flowchart Process              Shared Memory              NodeProcess
┌──────────────┐              ┌──────────────┐           ┌──────────────┐
│ Node         │              │ State Dict   │           │ Node         │
│              │──read/write──│              │──read/────│ ctrlWidget   │
│              │              │ {            │     write │ widget       │
└──────────────┘              │   'ctrl': {} │           └──────────────┘
                              │   'widget':{}│
                              │ }            │
                              └──────────────┘
```

**Benefits**:
1. **Synchronous access**: Direct memory read/write (no async messages)
2. **Always available**: State persists even when widget closed
3. **Auto-replace works**: Update shared memory from Flowchart process
4. **Simpler**: Single source of truth

---

## Architecture Design

### Key Insight: ALL State Goes in Shared Memory

**Both** `ctrl` (uiTemplate controls) **and** `widget` (custom display widgets) state:

```python
{
    # Node parameters from uiTemplate (spinboxes, checkboxes)
    'ctrl': {
        'bins': 10,
        'auto range': False,
        'range min': 1.0,
        'range max': 100.0
    },
    
    # Custom display widget state
    'widget': {
        'inputs': {'In': 'cspad'},           # For Filter/Calculator
        'conditions': {'If': {...}},          # For Filter
        'plot_config': {...},                 # For display widgets
        'roi_coords': {...}                   # For ROI widgets
    },
    
    # Full terminal metadata
    'terminals': {
        'In': {'io': 'in', 'ttype': 'Array2d', 'optional': False},
        'Out': {'io': 'out', 'ttype': 'Array2d'}
    }
}
```

---

### Why Both ctrl AND widget?

**Discovery**: Every node runs in a separate NodeProcess!
- **ctrlWidget** (uiTemplate spinboxes) lives in NodeProcess
- **Custom widget** (FilterWidget, etc.) lives in NodeProcess
- **Both** need to persist when process crashes or window closes

---

### SharedWidgetState Class

**File**: `ami/flowchart/SharedState.py` (new)

**Purpose**: Manage shared memory segment for a single node

**Interface**:
```python
class SharedWidgetState:
    def __init__(self, node_name, create=True, size=4096):
        """
        Create or attach to shared memory segment.
        
        Args:
            node_name: Node name (used for segment name)
            create: True to create, False to attach (NodeProcess)
            size: Size in bytes (default 4KB, auto-expand if needed)
        """
        
    def read() -> dict:
        """Read entire state dict from shared memory"""
        
    def write(state: dict):
        """Write entire state dict to shared memory"""
        
    def apply_input_replacement(old_input: str, new_input: str):
        """Auto-replace inputs (override in subclasses)"""
        
    def close():
        """Close shared memory handle"""
        
    def unlink():
        """Delete shared memory segment"""
```

**Implementation Details**:
- Uses `multiprocessing.shared_memory.SharedMemory`
- Pickle-based serialization (simple, works with any dict)
- Thread-safe with locks
- Segment name: `ami_widget_{node_name}`

---

## Design Decisions

### 1. What Goes in Shared Memory?

**Decision**: Both `ctrl` and `widget` state

**Rationale**: Both live in NodeProcess, both need persistence

---

### 2. Nested Key Updates?

**Decision**: NO - use simple read-modify-write

**Example**:
```python
# Simple approach (chosen)
state = shared_state.read()
state['inputs']['In'] = 'cspad'
shared_state.write(state)

# Complex approach (rejected)
shared_state.update({'inputs.In': 'cspad'})  # ❌ Not needed
```

**Rationale**: Simpler code, fewer lines, easier to understand

---

### 3. Disconnected Terminals?

**Decision**: Remove key from `inputs` dict (not set to None)

**Example**:
```python
# Before disconnect:
state['widget']['inputs'] = {'In': 'cspad', 'In2': 'waveform'}

# After disconnecting 'In':
state['widget']['inputs'] = {'In2': 'waveform'}  # 'In' key removed
```

**Rationale**: 
- Cleaner GUI (no spurious `[None]` buttons)
- Clear semantics: `if term in inputs` means "is connected?"
- Smaller state size

---

### 4. Store Full Terminal State?

**Decision**: YES - store full `term.saveState()`

**Rationale**: Needed for proper restoration of terminal metadata (type, optional, etc.)

---

### 5. Widget Refresh Frequency?

**Decision**: Refresh on every terminal event (for Filter/Calculator)

**Rationale**: Immediate UI consistency, simple logic

---

### 6. Platform?

**Decision**: Linux only (no platform compatibility needed)

**Rationale**: Simplifies implementation, matches production environment

---

### 7. Fallback to ZMQ?

**Decision**: NO - shared memory required

**Rationale**: Simpler code, clear requirements

---

## Implementation Plan

### Week 1: Core Infrastructure

#### **Files Modified/Created**:
- `ami/flowchart/SharedState.py` (new, +200 lines)
- `ami/flowchart/library/common.py` (modify, +200 lines)
- `ami/client/flowchart_messages.py` (modify, +10 lines)

---

#### **1.1 SharedWidgetState Class**

**File**: `ami/flowchart/SharedState.py`

**Implementation**:
```python
from multiprocessing import shared_memory
import pickle
import threading

class SharedWidgetState:
    """Widget state stored in shared memory"""
    
    def __init__(self, node_name, create=True, size=4096):
        self.node_name = node_name
        self.shm_name = f"ami_widget_{node_name}"
        self.lock = threading.Lock()
        
        if create:
            self.shm = shared_memory.SharedMemory(
                name=self.shm_name,
                create=True,
                size=size
            )
            # Initialize with empty state
            self.write({'ctrl': {}, 'widget': {}, 'terminals': {}})
        else:
            self.shm = shared_memory.SharedMemory(
                name=self.shm_name,
                create=False
            )
    
    def read(self):
        """Read state from shared memory"""
        with self.lock:
            # First 4 bytes = data length
            length = int.from_bytes(self.shm.buf[:4], 'little')
            data = bytes(self.shm.buf[4:4+length])
            return pickle.loads(data)
    
    def write(self, state):
        """Write state to shared memory"""
        with self.lock:
            data = pickle.dumps(state)
            length = len(data)
            
            # Check if we need to expand
            if 4 + length > self.shm.size:
                # Need to expand (rare case)
                self._expand(4 + length)
            
            self.shm.buf[:4] = length.to_bytes(4, 'little')
            self.shm.buf[4:4+length] = data
    
    def apply_input_replacement(self, old_input, new_input):
        """
        Auto-replace old input with new input.
        Override in subclasses for custom logic.
        """
        # Base implementation: no-op
        pass
    
    def close(self):
        """Close shared memory handle"""
        self.shm.close()
    
    def unlink(self):
        """Delete shared memory segment"""
        try:
            self.shm.unlink()
        except FileNotFoundError:
            pass  # Already deleted
    
    def _expand(self, new_size):
        """Expand shared memory (rare case)"""
        # Save current state
        old_state = self.read()
        
        # Close old segment
        old_name = self.shm_name
        self.shm.close()
        self.shm.unlink()
        
        # Create larger segment
        self.shm = shared_memory.SharedMemory(
            name=old_name,
            create=True,
            size=new_size * 2  # Double it
        )
        
        # Restore state
        self.write(old_state)
```

**Lines**: ~200

---

#### **1.2 Update CtrlNode**

**File**: `ami/flowchart/library/common.py`

**Changes**:

**Add to `__init__()`**:
```python
def __init__(self, name, ui=None, terminals={}, **kwargs):
    self.widget = None
    self.geometry = None
    
    # NEW: Create shared memory state
    self.shared_state = self._create_widget_state()
    
    super().__init__(name=name, terminals=terminals, **kwargs)
    
    # ... existing uiTemplate code ...

def _create_widget_state(self):
    """Override in subclasses for custom SharedWidgetState"""
    from ami.flowchart.SharedState import SharedWidgetState
    return SharedWidgetState(self.name())
```

**Update `saveState()`**:
```python
def saveState(self):
    state = super().saveState()
    
    # NEW: Read EVERYTHING from shared memory
    shared = self.shared_state.read()
    
    # Both ctrl and widget come from shared memory
    state['ctrl'] = shared.get('ctrl', {})
    state['widget'] = shared.get('widget', {})
    
    if self.geometry:
        state['geometry'] = bytes(self.geometry.toHex()).decode('ascii')
    
    return state
```

**Update `restoreState()`**:
```python
def restoreState(self, state):
    super().restoreState(state)
    
    # Build shared state dict
    shared_state = {}
    
    # Ctrl state
    if 'ctrl' in state:
        shared_state['ctrl'] = state['ctrl']
    
    # Widget state (with migration)
    if 'widget' in state:
        widget_state = state['widget']
        if self._needs_migration(widget_state):
            widget_state = self._migrate_widget_state(widget_state)
        shared_state['widget'] = widget_state
    
    # Write to shared memory
    self.shared_state.write(shared_state)
    
    # Update stateGroup if it exists (in NodeProcess)
    if self.stateGroup is not None:
        self.stateGroup.setState(shared_state.get('ctrl', {}))
    
    # Update widget if it exists
    if self.widget and hasattr(self.widget, 'refresh'):
        self.widget.refresh(shared_state.get('widget', {}))
    
    if 'geometry' in state:
        self.geometry = QtCore.QByteArray.fromHex(bytes(state['geometry'], 'ascii'))

def _needs_migration(self, state):
    """Detect old format (no version marker)"""
    return '_version' not in state

def _migrate_widget_state(self, state):
    """Override in subclasses for widget-specific migration"""
    state['_version'] = 1
    return state
```

**Add terminal lifecycle methods**:
```python
def addTerminal(self, *args, **kwargs):
    term = super().addTerminal(*args, **kwargs)
    
    # Update shared memory
    state = self.shared_state.read()
    if 'terminals' not in state:
        state['terminals'] = {}
    state['terminals'][term.name()] = term.saveState()
    self.shared_state.write(state)
    
    # Notify widget if exists
    if self.widget and hasattr(self.widget, 'terminalAdded'):
        self.widget.terminalAdded(term)
    
    return term

def removeTerminal(self, term):
    if isinstance(term, str):
        if term not in self.terminals:
            return
        term = self.terminals[term]
    
    term_name = term.name()
    
    # Update shared memory (remove from terminals and inputs)
    state = self.shared_state.read()
    state.get('terminals', {}).pop(term_name, None)
    
    widget_state = state.get('widget', {})
    widget_state.get('inputs', {}).pop(term_name, None)
    
    self.shared_state.write(state)
    
    # Notify widget if exists
    if self.widget and hasattr(self.widget, 'terminalRemoved'):
        self.widget.terminalRemoved(term)
    
    super().removeTerminal(term)

def terminalConnected(self, nodeTermConnected):
    # Update shared memory (ALWAYS, even if widget closed)
    if nodeTermConnected.localTermState['io'] == 'in':
        term = nodeTermConnected.localTerm
        
        if nodeTermConnected.remoteNodeIsSource:
            new_input = nodeTermConnected.remoteNode
        else:
            new_input = f"{nodeTermConnected.remoteNode}.{nodeTermConnected.remoteTerm}"
        
        state = self.shared_state.read()
        widget_state = state.get('widget', {})
        if 'inputs' not in widget_state:
            widget_state['inputs'] = {}
        widget_state['inputs'][term] = new_input
        state['widget'] = widget_state
        self.shared_state.write(state)
    
    # Notify widget if exists
    if self.widget and hasattr(self.widget, "terminalConnected"):
        self.widget.terminalConnected(nodeTermConnected)

def terminalDisconnected(self, nodeTermDisconnected):
    # Update shared memory (remove key entirely)
    if nodeTermDisconnected.localTermState['io'] == 'in':
        term = nodeTermDisconnected.localTerm
        
        state = self.shared_state.read()
        widget_state = state.get('widget', {})
        inputs = widget_state.get('inputs', {})
        
        # Remove key entirely (not set to None)
        if term in inputs:
            del inputs[term]
        
        self.shared_state.write(state)
    
    # Notify widget if exists
    if self.widget and hasattr(self.widget, "terminalDisconnected"):
        self.widget.terminalDisconnected(nodeTermDisconnected)

def sourceInputReplaced(self, old_input, new_input):
    """NEW: Auto-replace when source node replaced"""
    # Update shared memory (works even when widget closed!)
    self.shared_state.apply_input_replacement(old_input, new_input)
    
    # Notify widget if exists
    if self.widget and hasattr(self.widget, 'refresh'):
        state = self.shared_state.read()
        self.widget.refresh(state.get('widget', {}))
```

**Update `close()`**:
```python
def close(self, emit=True):
    super().close(emit)
    
    if self.widget:
        self.widget.close()
    self.widget = None
    
    # Clean up shared memory
    self.shared_state.close()
    self.shared_state.unlink()
```

**Lines**: +200

---

#### **1.3 Add Message Type**

**File**: `ami/client/flowchart_messages.py`

```python
class WidgetRefresh(NodeMsg):
    """Lightweight notification to refresh widget from shared memory"""
    def __init__(self, node_name):
        super().__init__(node_name)
```

**Lines**: +10

---

### Week 2: Flowchart & NodeProcess Integration

#### **Files Modified**:
- `ami/client/flowchart.py` (+80 lines)
- `ami/flowchart/Flowchart.py` (+20 lines)

---

#### **2.1 Update NodeProcess**

**File**: `ami/client/flowchart.py`

**Changes in `__init__()`**:
```python
def __init__(self, msg, broker_addr, ...):
    # ... existing setup ...
    
    # Attach to shared memory (don't create, Flowchart already created it)
    from ami.flowchart.SharedState import SharedWidgetState
    self.shared_state = SharedWidgetState(msg.name, create=False)
    
    # ... rest of init ...
    
    # Connect stateGroup changes to shared memory
    if self.node.stateGroup:
        self.node.stateGroup.sigChanged.connect(self.save_ctrl_to_shared_memory)
    
    self.node.sigStateChanged.connect(self.save_to_shared_memory)
```

**New method**:
```python
def save_ctrl_to_shared_memory(self, name, group, val):
    """When user changes a uiTemplate control, save to shared memory"""
    state = self.shared_state.read()
    
    # Update ctrl state
    if 'ctrl' not in state:
        state['ctrl'] = {}
    
    if group:
        if group not in state['ctrl']:
            state['ctrl'][group] = {}
        state['ctrl'][group][name] = val
    else:
        state['ctrl'][name] = val
    
    self.shared_state.write(state)

@asyncSlot(object)
async def save_to_shared_memory(self, node):
    """Save both ctrl and widget state to shared memory"""
    state = self.shared_state.read()
    
    # Save ctrl state
    if node.stateGroup:
        state['ctrl'] = node.stateGroup.state()
    
    # Save widget state
    if node.widget and hasattr(node.widget, 'saveState'):
        state['widget'] = node.widget.saveState()
    
    self.shared_state.write(state)
    
    # Still send checkpoint for backwards compatibility / monitoring
    await self.send_checkpoint(node)
```

**Message handling**:
```python
async def process(self):
    while True:
        await self.broker.recv_string()
        msg = await self.broker.recv_pyobj()
        
        # ... existing handlers ...
        
        elif isinstance(msg, fcMsgs.WidgetRefresh):
            # Refresh both ctrlWidget and custom widget
            state = self.shared_state.read()
            
            if self.node.stateGroup:
                self.node.stateGroup.setState(state.get('ctrl', {}))
            
            if self.widget and hasattr(self.widget, 'refresh'):
                self.widget.refresh(state.get('widget', {}))
```

**Lines**: +80

---

#### **2.2 Update Flowchart Auto-Replace**

**File**: `ami/flowchart/Flowchart.py`

**Modify `replaceSourceNode()`**:
```python
async def replaceSourceNode(self, old_node, new_node):
    # ... existing connection transfer logic ...
    
    # NEW: After transferring connections, update downstream nodes
    for remote_term in connections_to_transfer:
        remote_node = remote_term.node()
        
        # Update shared memory (in Flowchart process)
        if hasattr(remote_node, 'sourceInputReplaced'):
            remote_node.sourceInputReplaced(old_node.name(), new_node.name())
        
        # Send refresh message to NodeProcess
        msg = fcMsgs.WidgetRefresh(remote_node.name())
        await self.broker.send_string(remote_node.name(), zmq.SNDMORE)
        await self.broker.send_pyobj(msg)
```

**Lines**: +20

---

### Week 3-4: Filter & Calculator Widgets

#### **Files Modified/Created**:
- `ami/flowchart/library/CalculatorWidget.py` (+510 lines)
- `ami/flowchart/library/Operators.py` (+30 lines)

---

#### **3.1 FilterWidgetState**

**File**: `ami/flowchart/library/CalculatorWidget.py`

```python
from ami.flowchart.SharedState import SharedWidgetState
import re

class FilterWidgetState(SharedWidgetState):
    """Custom state for Filter nodes with auto-replace logic"""
    
    def apply_input_replacement(self, old_input, new_input):
        """Auto-replace old input with new input in conditions"""
        state = self.read()
        widget_state = state.get('widget', {})
        
        # Update inputs dict
        inputs = widget_state.get('inputs', {})
        for term, input_name in inputs.items():
            if input_name == old_input:
                inputs[term] = new_input
        
        # Update conditions (regex replace)
        conditions = widget_state.get('conditions', {})
        for name, condition in conditions.items():
            if 'condition' in condition:
                pattern = r'\b' + re.escape(old_input) + r'\b'
                condition['condition'] = re.sub(pattern, new_input, condition['condition'])
            
            # Update combo box selections
            for output in condition.keys():
                if output != 'condition' and condition[output] == old_input:
                    condition[output] = new_input
        
        state['widget'] = widget_state
        self.write(state)


class CalculatorWidgetState(SharedWidgetState):
    """Custom state for Calculator nodes"""
    
    def apply_input_replacement(self, old_input, new_input):
        """Auto-replace in calculator operation string"""
        import re
        
        state = self.read()
        widget_state = state.get('widget', {})
        
        if 'operation' in widget_state:
            pattern = r'\b' + re.escape(old_input) + r'\b'
            widget_state['operation'] = re.sub(pattern, new_input, widget_state['operation'])
        
        # Update inputs
        inputs = widget_state.get('inputs', {})
        for term, input_name in inputs.items():
            if input_name == old_input:
                inputs[term] = new_input
        
        state['widget'] = widget_state
        self.write(state)
```

**Lines**: +80

---

#### **3.2 Refactor FilterWidget**

**File**: `ami/flowchart/library/CalculatorWidget.py`

**Major changes**:

1. **Accept `shared_state` in `__init__()`**
2. **Implement `refresh(state)` method**
3. **Simplify `terminalConnected/Disconnected()` - just refresh**
4. **Keep `saveState()/restoreState()` for compatibility**

**Key methods**:
```python
class FilterWidget(QtWidgets.QWidget):
    def __init__(self, shared_state, outputs=[], node=None, parent=None):
        super().__init__(parent)
        self.shared_state = shared_state
        self.node = node
        
        # Read initial state
        state = shared_state.read()
        widget_state = state.get('widget', {})
        
        self.outputs = widget_state.get('outputs', outputs)
        
        self._setup_ui()
        self.refresh(widget_state)
    
    def refresh(self, widget_state):
        """Update entire UI from widget state dict"""
        inputs = widget_state.get('inputs', {})
        self._update_variable_buttons(inputs)
        
        conditions = widget_state.get('conditions', {})
        self._update_conditions(conditions)
        
        self._update_combo_boxes(inputs)
    
    def terminalConnected(self, nodeTermConnected):
        """State already updated by Node, just refresh UI"""
        state = self.shared_state.read()
        self.refresh(state.get('widget', {}))
    
    def terminalDisconnected(self, nodeTermDisconnected):
        """State already updated by Node, just refresh UI"""
        state = self.shared_state.read()
        self.refresh(state.get('widget', {}))
    
    def saveState(self):
        """Read from shared memory"""
        state = self.shared_state.read()
        return state.get('widget', {})
    
    def restoreState(self, state):
        """Write to shared memory and refresh"""
        shared = self.shared_state.read()
        shared['widget'] = state
        self.shared_state.write(shared)
        self.refresh(state)
```

**Lines**: +250

---

#### **3.3 Similar for CalculatorWidget**

**Lines**: +180

---

#### **3.4 Update Filter/Calculator Nodes**

**File**: `ami/flowchart/library/Operators.py`

```python
class Filter(CtrlNode):
    def _create_widget_state(self):
        """Use FilterWidgetState for auto-replace"""
        from ami.flowchart.library.CalculatorWidget import FilterWidgetState
        return FilterWidgetState(self.name())
    
    def display(self, topics, terms, addr, win, **kwargs):
        if self.widget is None:
            from ami.flowchart.library.CalculatorWidget import FilterWidget
            
            self.widget = FilterWidget(
                shared_state=self.shared_state,
                outputs=self.output_vars(),
                node=self,
                parent=win
            )
        
        return self.widget

class Calculator(CtrlNode):
    def _create_widget_state(self):
        from ami.flowchart.library.CalculatorWidget import CalculatorWidgetState
        return CalculatorWidgetState(self.name())
    
    def display(self, topics, terms, addr, win, **kwargs):
        if self.widget is None:
            from ami.flowchart.library.CalculatorWidget import CalculatorWidget
            
            self.widget = CalculatorWidget(
                shared_state=self.shared_state,
                terms=terms or self.input_vars(),
                parent=win,
                operation=self.values.get('operation', '')
            )
        
        return self.widget
```

**Lines**: +30

---

### Week 5: Display Widgets

#### **Files Modified**:
- `ami/flowchart/library/Display.py` (+200 lines)
- `ami/flowchart/library/DisplayWidgets.py` (+300 lines)

**Strategy**: Minimal changes - these widgets don't track connections

**Example** (ImageWidget):
```python
def __init__(self, topics, terms, addr, parent=None, shared_state=None, **kwargs):
    super().__init__(topics, terms, addr, parent, **kwargs)
    self.shared_state = shared_state
    
    # Restore plot config from shared memory
    if shared_state:
        state = shared_state.read()
        widget_state = state.get('widget', {})
        if 'plot_config' in widget_state:
            self.apply_plot_config(widget_state['plot_config'])

def saveState(self):
    state = super().saveState()
    
    if self.shared_state:
        shared = self.shared_state.read()
        shared['widget'] = {'plot_config': state}
        self.shared_state.write(shared)
    
    return state
```

**Affected widgets**: ~15 display widgets  
**Lines per widget**: ~30-40  
**Total**: ~500 lines

---

### Week 6: ROI Widgets

#### **Files Modified**:
- `ami/flowchart/library/Roi.py` (+200 lines)

**Similar to display widgets** - store ROI coordinates/selections

---

### Week 7: Testing & Migration

#### **Files Created**:
- `tests/test_shared_widget_state.py` (+500 lines)

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_shared_widget_state.py`

#### **SharedWidgetState Tests**
```python
def test_create_shared_memory():
    """Verify shared memory creation"""
    state = SharedWidgetState('test_node', create=True)
    assert state.shm_name == 'ami_widget_test_node'
    state.close()
    state.unlink()

def test_read_write():
    """Verify read/write operations"""
    state = SharedWidgetState('test_node', create=True)
    
    test_data = {'ctrl': {'bins': 10}, 'widget': {'inputs': {}}}
    state.write(test_data)
    
    result = state.read()
    assert result == test_data
    
    state.close()
    state.unlink()

def test_concurrent_access():
    """Verify thread safety"""
    # Test multiple threads reading/writing
    pass
```

---

#### **Terminal Lifecycle Tests**
```python
def test_terminal_connected_updates_shared_memory():
    """Verify terminalConnected updates shared memory even when widget closed"""
    filter_node = Filter('Filter.1')
    
    # Widget is closed (None)
    assert filter_node.widget is None
    
    # Connect terminal
    source = SourceNode('cspad')
    msg = NodeTermConnected(...)
    filter_node.terminalConnected(msg)
    
    # Shared memory should be updated
    state = filter_node.shared_state.read()
    assert state['widget']['inputs']['In'] == 'cspad'

def test_terminal_disconnected_removes_key():
    """Verify key is removed (not set to None)"""
    filter_node = Filter('Filter.1')
    
    # Setup
    filter_node.shared_state.write({
        'widget': {'inputs': {'In': 'cspad', 'In2': 'waveform'}}
    })
    
    # Disconnect
    msg = NodeTermDisconnected(...)
    filter_node.terminalDisconnected(msg)
    
    # Key should be removed
    state = filter_node.shared_state.read()
    assert 'In' not in state['widget']['inputs']
    assert state['widget']['inputs'] == {'In2': 'waveform'}
```

---

#### **Auto-Replace Test (THE CRITICAL TEST)**
```python
def test_replace_source_widget_closed():
    """
    The scenario from lessons learned document.
    This is THE test that validates the entire design.
    """
    # Create filter with condition referencing 'cspad'
    filter_node = Filter('Filter.1')
    filter_node.shared_state.write({
        'widget': {
            'inputs': {'In': 'cspad'},
            'conditions': {
                'If': {
                    'condition': 'cspad > 100',
                    'Out': 'cspad'
                }
            },
            'outputs': ['Out']
        }
    })
    
    # Close widget (simulate window closed)
    filter_node.widget = None
    
    # Replace source: cspad → waveform2
    old_source = SourceNode('cspad')
    new_source = SourceNode('waveform2')
    
    # Disconnect old
    old_source['Out'].disconnectFrom(filter_node['In'])
    
    # Connect new
    new_source['Out'].connectTo(filter_node['In'])
    
    # Auto-replace
    filter_node.sourceInputReplaced('cspad', 'waveform2')
    
    # Verify shared memory updated correctly
    state = filter_node.shared_state.read()
    widget_state = state['widget']
    
    # Input updated
    assert widget_state['inputs']['In'] == 'waveform2'
    
    # Condition text updated
    assert 'waveform2 > 100' in widget_state['conditions']['If']['condition']
    assert 'cspad' not in widget_state['conditions']['If']['condition']
    
    # Combo box selection updated
    assert widget_state['conditions']['If']['Out'] == 'waveform2'
    
    # Now reopen widget
    from ami.flowchart.library.CalculatorWidget import FilterWidget
    filter_node.widget = FilterWidget(
        shared_state=filter_node.shared_state,
        outputs=['Out'],
        node=filter_node
    )
    
    # Verify UI shows correct state
    assert filter_node.widget.inputs['In'] == 'waveform2'
    # Check that condition text widget shows 'waveform2 > 100'
    # (exact assertion depends on UI structure)
    
    print("✅ AUTO-REPLACE WORKS WITH WIDGET CLOSED!")
```

---

#### **Ctrl State Tests**
```python
def test_ctrl_state_in_shared_memory():
    """Verify uiTemplate controls save to shared memory"""
    binning_node = Binning('Binning.1')
    
    # Simulate user changing spinbox (in NodeProcess)
    # This would normally come through stateGroup.sigChanged
    state = binning_node.shared_state.read()
    state['ctrl'] = {'bins': 42, 'auto range': True}
    binning_node.shared_state.write(state)
    
    # Save node state (in Flowchart process)
    saved_state = binning_node.saveState()
    
    # Ctrl state should be from shared memory
    assert saved_state['ctrl']['bins'] == 42
    assert saved_state['ctrl']['auto range'] == True
```

---

#### **Backward Compatibility Tests**
```python
def test_load_old_flowchart():
    """Verify old .fcf files load correctly"""
    # Load old format state
    old_state = {
        'ctrl': {'bins': 10},
        'widget': {
            'inputs': {'In': 'cspad'},
            # No '_version' key (old format)
        }
    }
    
    node = Filter('Filter.1')
    node.restoreState(old_state)
    
    # Should migrate and work
    state = node.shared_state.read()
    assert state['widget']['_version'] == 1
    assert state['widget']['inputs']['In'] == 'cspad'
```

---

#### **Memory Leak Tests**
```python
def test_no_memory_leak():
    """Verify no memory leaks after many open/close cycles"""
    import psutil
    import gc
    
    process = psutil.Process()
    initial_memory = process.memory_info().rss
    
    # Create/destroy 1000 nodes
    for i in range(1000):
        node = Filter(f'Filter.{i}')
        state = node.saveState()
        node.close()
        gc.collect()
    
    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory
    
    # Should be < 10MB increase
    assert memory_increase < 10 * 1024 * 1024
```

---

### Integration Tests

1. **Full workflow**: Create → Connect → Replace → Save → Load
2. **Multiple nodes**: 20 nodes simultaneously
3. **Complex flowcharts**: Load real user flowcharts
4. **Stress testing**: Rapid create/close cycles

---

## Success Criteria

Phase 1 is successful when:

✅ **Auto-replace works when widget closed** - the critical test passes  
✅ **All existing flowcharts load** - 100% backward compatibility  
✅ **State persists across widget close/reopen** - no data loss  
✅ **No memory leaks** - stable after 1000 cycles  
✅ **Both ctrl and widget state always available** - read anytime  
✅ **Terminal lifecycle updates shared memory** - even when widget closed  
✅ **All existing tests still pass** - no regressions  

---

## Migration & Compatibility

### Backward Compatibility

**Existing flowcharts (.fcf files) must work unchanged!**

**Migration strategy**:
```python
def _needs_migration(self, state):
    """Detect old format"""
    return '_version' not in state

def _migrate_widget_state(self, state):
    """Migrate old format to new"""
    # Add version marker
    state['_version'] = 1
    
    # Override in subclasses for widget-specific migration
    return state
```

**On load**:
1. Detect old format (no `_version` key)
2. Migrate to new format
3. Write to shared memory
4. Continue normally

**On save**:
1. Always save new format (with `_version`)
2. Old AMI versions will ignore `_version` key (forward compatible)

---

### File Format Changes

**Before (Phase 0)**:
```python
{
    'pos': [100, 200],
    'terminals': {...},
    'ctrl': {'bins': 10},
    'widget': {'inputs': {'In': 'cspad'}}  # May be missing if widget closed!
}
```

**After (Phase 1)**:
```python
{
    'pos': [100, 200],
    'terminals': {...},
    'ctrl': {'bins': 10},  # Always present (from shared memory)
    'widget': {            # Always present (from shared memory)
        '_version': 1,
        'inputs': {'In': 'cspad'},
        'conditions': {...}
    }
}
```

**Key difference**: `widget` state is **always present** (even if window was closed when saved)

---

## File Summary

| File | Type | Lines | Complexity |
|------|------|-------|------------|
| `ami/flowchart/SharedState.py` | New | +200 | Medium |
| `ami/flowchart/library/common.py` | Modify | +200 | High |
| `ami/client/flowchart.py` | Modify | +80 | Medium |
| `ami/flowchart/Flowchart.py` | Modify | +20 | Low |
| `ami/client/flowchart_messages.py` | Modify | +10 | Low |
| `ami/flowchart/library/CalculatorWidget.py` | Modify | +510 | High |
| `ami/flowchart/library/Operators.py` | Modify | +30 | Low |
| `ami/flowchart/library/Display.py` | Modify | +200 | Low |
| `ami/flowchart/library/DisplayWidgets.py` | Modify | +300 | Medium |
| `ami/flowchart/library/Roi.py` | Modify | +200 | Medium |
| `tests/test_shared_widget_state.py` | New | +500 | Medium |
| **TOTAL** | | **~2,250 lines** | |

---

## Timeline

| Week | Phase | Deliverable | Status |
|------|-------|-------------|--------|
| 1 | Core Infrastructure | SharedWidgetState + CtrlNode | Not Started |
| 2 | Integration | Auto-replace working | Not Started |
| 3-4 | Filter & Calculator | Complex widgets | Not Started |
| 5 | Display Widgets | Plot configuration | Not Started |
| 6 | ROI Widgets | ROI state | Not Started |
| 7 | Testing & Migration | All tests passing | Not Started |

**Total**: 7 weeks

---

## Next Steps

**Ready to start?**

1. Create feature branch: `git checkout -b feature/shared-memory-state`
2. Start with `SharedWidgetState` class
3. Incremental commits with tests
4. Regular reviews

---

## References

- [Lessons Learned: Widget State Management](../../LESSONS_LEARNED_WIDGET_STATE_MANAGEMENT.md)
- [Phase 2: Remove MessageBroker](./phase2-remove-message-broker.md)

---

**End of Phase 1 Plan**
