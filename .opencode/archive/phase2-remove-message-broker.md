# Phase 2: Remove MessageBroker - Architecture Simplification

**Status**: Design Phase (to be implemented after Phase 1)  
**Timeline**: 2 weeks  
**Dependencies**: Phase 1 (Shared Memory State Management) must be complete  
**Goal**: Simplify AMI's process architecture by eliminating the MessageBroker intermediary  

---

## Table of Contents

1. [Overview](#overview)
2. [Current vs Proposed Architecture](#current-vs-proposed-architecture)
3. [Why Remove MessageBroker?](#why-remove-messagebroker)
4. [Design Details](#design-details)
5. [Implementation Plan](#implementation-plan)
6. [Crash Recovery Design](#crash-recovery-design)
7. [Migration Strategy](#migration-strategy)
8. [Testing Strategy](#testing-strategy)
9. [Risks & Mitigation](#risks--mitigation)

---

## Overview

### Current State (After Phase 1)

After Phase 1, AMI has:
- ✅ Shared memory for state management
- ✅ Reduced dependency on ZMQ messages (no checkpoint messages)
- ⚠️ Still has 3-layer process architecture with MessageBroker

### Goal State (After Phase 2)

Phase 2 will:
- ✅ Eliminate MessageBroker process entirely
- ✅ Make Editor/Flowchart the main process
- ✅ Use direct process management (no ZMQ broker)
- ✅ Maintain all functionality (crash recovery, etc.)

---

## Current vs Proposed Architecture

### Current (3-Layer, After Phase 1)

```
┌─────────────────────────────────────────┐
│  Main CLI Process (run_client)          │
│  - Starts MessageBroker                 │
│  - Waits for editor exit                │
└──────────────┬──────────────────────────┘
               │ spawns
               ▼
┌─────────────────────────────────────────┐
│  MessageBroker Process                  │
│  - Manages process lifecycle            │
│  - Routes ZMQ messages                  │
│  - Crash recovery monitoring            │
│  - Spawns Editor + NodeProcesses        │
└──────┬──────────────────┬───────────────┘
       │ spawns           │ spawns
       ▼                  ▼
┌─────────────┐    ┌─────────────────┐
│ Editor/     │    │ NodeProcess 1   │
│ Flowchart   │    │ NodeProcess 2   │
│             │    │ NodeProcess 3   │
│ (GUI)       │    │ ...             │
└─────────────┘    └─────────────────┘
```

**Communication**:
- Editor → MessageBroker → NodeProcess: ZMQ pub/sub
- NodeProcess → Flowchart: Shared memory (state)

---

### Proposed (2-Layer, After Phase 2)

```
┌─────────────────────────────────────────┐
│  Editor/Flowchart Process (MAIN)        │
│  - Direct process management            │
│  - Crash recovery monitoring            │
│  - Spawns NodeProcesses directly        │
│  - GUI event loop                       │
└──────────────┬──────────────────────────┘
               │ spawns directly
               ▼
        ┌─────────────────┐
        │ NodeProcess 1   │
        │ NodeProcess 2   │
        │ NodeProcess 3   │
        │ ...             │
        └─────────────────┘
```

**Communication**:
- Editor → NodeProcess: `multiprocessing.Queue` (control commands)
- NodeProcess → Editor: Shared memory (state)
- Direct parent-child process relationship

---

## Why Remove MessageBroker?

### Problems with Current Architecture

1. **Extra process layer** - adds complexity
2. **ZMQ dependency** - needed only for message routing
3. **Indirect process management** - Flowchart can't directly control its NodeProcesses
4. **Harder debugging** - messages routed through broker, not direct
5. **Startup complexity** - 3 processes to start instead of 1

### Benefits of Removal

| Benefit | Impact |
|---------|--------|
| **Simpler architecture** | 2 process layers instead of 3 |
| **Direct control** | Flowchart directly spawns/terminates NodeProcesses |
| **Easier debugging** | Direct communication, no broker routing |
| **Faster startup** | One less process to spawn |
| **Less overhead** | No ZMQ routing, direct Queue communication |
| **Clearer ownership** | Flowchart clearly owns its NodeProcesses |

### What We Keep

- ✅ **Process isolation** - NodeProcesses still separate for pyqtgraph performance
- ✅ **Crash recovery** - moved to Flowchart process
- ✅ **Shared memory** - state management unchanged
- ✅ **All functionality** - no features lost

---

## Design Details

### Process Management in Flowchart

**File**: `ami/flowchart/Flowchart.py`

**New attributes**:
```python
class Flowchart:
    def __init__(self, ...):
        # ... existing attributes ...
        
        # NEW: Direct process management
        self.node_processes = {}      # {node_name: multiprocessing.Process}
        self.control_queues = {}      # {node_name: multiprocessing.Queue}
        self.process_monitor_task = None
```

---

### Creating Nodes

**Current (Phase 1)**:
```python
# Flowchart sends message to MessageBroker
msg = fcMsgs.CreateNode(node.name(), node.__class__.__name__, state)
await self.broker.send_string(node.name(), zmq.SNDMORE)
await self.broker.send_pyobj(msg)

# MessageBroker spawns process
proc = mp.Process(target=NodeProcess, args=(...))
proc.start()
```

**Proposed (Phase 2)**:
```python
# Flowchart spawns process directly
def createNode(self, nodeType, name, pos=None):
    # Create node object in Flowchart process
    node = self.library.getNodeType(nodeType)(name)
    self.addNode(node, pos)
    
    # Create control queue
    control_queue = mp.Queue()
    
    # Spawn NodeProcess directly
    state = node.saveState()
    proc = mp.Process(
        target=run_node_process,
        name=node.name(),
        args=(
            node.name(),
            node.__class__.__name__,
            state,
            control_queue,
            self.graphmgr_addr,
            self.prometheus_dir,
            self.prometheus_port,
            self.hutch
        ),
        daemon=True
    )
    proc.start()
    
    # Track process
    self.node_processes[node.name()] = proc
    self.control_queues[node.name()] = control_queue
    
    logger.info(f"Spawned NodeProcess {node.name()} (pid: {proc.pid})")
    
    return node
```

---

### Communication: Queue-Based Messages

**Replace ZMQ with multiprocessing.Queue**

**Control message structure**:
```python
# Message types
{
    'cmd': 'display',
    'topics': {...},
    'terms': {...},
    'state': {...},
    'units': {...},
    'geometry': ...,
    'label': ...
}

{
    'cmd': 'close'
}

{
    'cmd': 'reload_library',
    'modules': [...]
}

{
    'cmd': 'terminal_added',
    'term': 'In',
    'state': {...}
}

{
    'cmd': 'terminal_removed',
    'term': 'In'
}

{
    'cmd': 'label_changed',
    'label': 'My Node'
}
```

**Sending from Flowchart**:
```python
async def displayNode(self, node, topics, terms, ...):
    """Send display command to NodeProcess"""
    queue = self.control_queues[node.name()]
    
    msg = {
        'cmd': 'display',
        'topics': topics,
        'terms': terms,
        'state': node.saveState(),
        'units': units,
        'geometry': node.geometry,
        'label': node.label()
    }
    
    # Queue.put is blocking, run in thread pool
    await asyncio.to_thread(queue.put, msg)
```

**Receiving in NodeProcess**:
```python
class NodeProcess:
    def __init__(self, node_name, node_type, state, control_queue, ...):
        self.control_queue = control_queue
        # ... rest of init ...
        
    async def process(self):
        """Main message loop"""
        while True:
            # Queue.get is blocking, run in thread pool
            msg = await asyncio.to_thread(self.control_queue.get)
            
            if msg['cmd'] == 'display':
                self.display(msg)
            elif msg['cmd'] == 'close':
                return  # Exit process
            elif msg['cmd'] == 'reload_library':
                self.reloadLibrary(msg)
            elif msg['cmd'] == 'terminal_added':
                self.node.addTerminal(msg['term'], **msg['state'])
            elif msg['cmd'] == 'terminal_removed':
                self.node.removeTerminal(msg['term'])
            elif msg['cmd'] == 'label_changed':
                self.updateWindowTitle(msg['label'])
```

---

### Closing Nodes

**Proposed**:
```python
async def nodeCloseRequested(self, node):
    """User closed a node"""
    name = node.name()
    
    # Send close command
    if name in self.control_queues:
        queue = self.control_queues[name]
        await asyncio.to_thread(queue.put, {'cmd': 'close'})
    
    # Wait for process to exit gracefully (with timeout)
    if name in self.node_processes:
        proc = self.node_processes[name]
        
        # Give it 2 seconds to exit gracefully
        await asyncio.to_thread(proc.join, timeout=2.0)
        
        # Force terminate if still alive
        if proc.is_alive():
            logger.warning(f"NodeProcess {name} didn't exit, terminating")
            proc.terminate()
            proc.join()
        
        # Cleanup
        del self.node_processes[name]
        del self.control_queues[name]
    
    # Rest of cleanup (remove from graph, etc.)
    # ... existing code ...
```

---

### Crash Recovery Monitoring

**Replace MessageBroker's crash monitoring with Flowchart monitoring**

**File**: `ami/flowchart/Flowchart.py`

```python
async def monitor_node_processes(self):
    """
    Monitor NodeProcesses for crashes and respawn if needed.
    Replaces MessageBroker.monitor_processes()
    """
    while True:
        await asyncio.sleep(1.0)  # Check every second
        
        for name, proc in list(self.node_processes.items()):
            # Check if process died unexpectedly
            if not proc.is_alive():
                exitcode = proc.exitcode
                
                # 0 = clean exit (user closed)
                # None = still running
                # negative = killed by signal
                # positive = error exit
                
                if exitcode != 0:
                    logger.error(f"NodeProcess {name} crashed (exit code: {exitcode})")
                    
                    # Respawn the process
                    await self.respawn_node_process(name)

async def respawn_node_process(self, name):
    """
    Respawn a crashed NodeProcess.
    State is preserved in shared memory!
    """
    logger.info(f"Respawning NodeProcess {name}")
    
    # Get node from graph
    if name not in self._graph.nodes:
        logger.error(f"Can't respawn {name} - not in graph")
        return
    
    node = self._graph.nodes[name]['node']
    
    # State is safe in shared memory!
    state = node.saveState()
    
    # Create new control queue
    control_queue = mp.Queue()
    
    # Spawn new process
    proc = mp.Process(
        target=run_node_process,
        name=name,
        args=(
            name,
            node.__class__.__name__,
            state,
            control_queue,
            self.graphmgr_addr,
            self.prometheus_dir,
            self.prometheus_port,
            self.hutch
        ),
        daemon=True
    )
    proc.start()
    
    # Update tracking
    self.node_processes[name] = proc
    self.control_queues[name] = control_queue
    
    logger.info(f"Respawned {name} (new pid: {proc.pid})")
    
    # If it was being displayed, redisplay
    if node.viewed:
        # Send display command to new process
        await self.displayNode(node, ...)
```

**Key insight**: Because state lives in shared memory, crashed processes can be respawned with full state recovery!

---

### Entry Point Changes

**Current (Phase 1)**:
```python
# ami/client/flowchart.py
def run_client(...):
    with MessageBroker(...) as mb:
        mb.launch_editor_window()  # ← Editor is spawned process
        mb.wait_editor_exit()
```

**Proposed (Phase 2)**:
```python
# ami/client/flowchart.py
def run_client(...):
    # Editor IS the main process now!
    run_editor_window(
        graphmgr_addr=graphmgr_addr,
        load=load,
        prometheus_dir=prometheus_dir,
        prometheus_port=prometheus_port,
        hutch=hutch,
        configure=configure,
        save_dir=save_dir
    )
    # No MessageBroker!
```

---

## Implementation Plan

### Week 1: Core Refactoring

#### **Day 1-2: Process Management**

**Tasks**:
1. Add `node_processes` and `control_queues` to Flowchart
2. Implement `createNode()` direct spawning
3. Implement `closeNode()` process termination
4. Replace `run_client()` to make Editor main process

**Files**:
- `ami/flowchart/Flowchart.py` - add process management (~150 lines)
- `ami/client/flowchart.py` - remove MessageBroker (~250 lines removed)

---

#### **Day 3-4: Queue-Based Communication**

**Tasks**:
1. Create `run_node_process()` function (replaces `NodeProcess.__init__`)
2. Implement Queue message handling in NodeProcess
3. Update all message sending in Flowchart to use Queues
4. Remove ZMQ broker code

**Files**:
- `ami/client/flowchart.py` - Queue-based NodeProcess (~100 lines)
- `ami/flowchart/Flowchart.py` - Queue message sending (~80 lines)

---

#### **Day 5: Crash Recovery**

**Tasks**:
1. Implement `monitor_node_processes()`
2. Implement `respawn_node_process()`
3. Start monitoring task in Flowchart init

**Files**:
- `ami/flowchart/Flowchart.py` - crash recovery (~80 lines)

---

### Week 2: Testing & Cleanup

#### **Day 6-7: Integration Testing**

**Tests**:
1. Create new nodes → verify processes spawned
2. Close nodes → verify processes terminated
3. Crash nodes (kill -9) → verify respawned with state intact
4. Load complex flowcharts → verify all nodes work
5. Replace source nodes → verify auto-replace still works

**Files**:
- `tests/test_process_management.py` (new, ~200 lines)

---

#### **Day 8-9: Cleanup**

**Tasks**:
1. Remove all MessageBroker code
2. Remove unused ZMQ imports
3. Update documentation
4. Remove `fcMsgs.NodeCheckpoint` (no longer used)

**Files**:
- Remove `MessageBroker` class from `ami/client/flowchart.py`
- Clean up `ami/client/flowchart_messages.py`

---

#### **Day 10: Final Testing**

**Tasks**:
1. Full regression testing
2. Performance comparison (startup time, memory usage)
3. Stress testing (100 nodes, rapid create/close)
4. User acceptance testing

---

## Crash Recovery Design

### How It Works

**Detection**:
```python
# Check every second
for name, proc in self.node_processes.items():
    if not proc.is_alive() and proc.exitcode != 0:
        # Crashed!
        await self.respawn_node_process(name)
```

**Recovery**:
```python
# 1. State is safe in shared memory
state = node.saveState()  # Reads from shared memory

# 2. Spawn new process
new_proc = mp.Process(target=run_node_process, args=(name, state, ...))
new_proc.start()

# 3. If window was open, reopen it
if node.viewed:
    await self.displayNode(node, ...)
```

**Result**: User sees window flicker and reappear, but all state preserved!

---

### Crash Types Handled

| Crash Type | Detection | Recovery |
|------------|-----------|----------|
| **Segfault** | `exitcode < 0` | Respawn with state from shared memory |
| **Python exception** | `exitcode > 0` | Respawn with state from shared memory |
| **Kill signal** | `exitcode < 0` | Respawn with state from shared memory |
| **Memory error** | `exitcode != 0` | Respawn with state from shared memory |

**Not handled**: Shared memory corruption (should be rare, needs investigation)

---

## Migration Strategy

### Backward Compatibility

**Good news**: This is purely an internal refactoring!

- ✅ `.fcf` files unchanged (state format same)
- ✅ User workflow unchanged
- ✅ Node API unchanged
- ✅ All features preserved

**Users won't notice** except:
- ⚡ Faster startup (one less process)
- 🐛 Easier bug reports (simpler process tree)

---

### Deployment

**Stages**:
1. **Development**: Test on dev instance
2. **Alpha**: Deploy to test users
3. **Beta**: Gradual rollout
4. **Production**: Full deployment

**Rollback plan**: Revert to Phase 1 (MessageBroker still in codebase until Phase 2 proven stable)

---

## Testing Strategy

### Unit Tests

**File**: `tests/test_process_management.py`

**Tests**:
```python
def test_create_node_spawns_process():
    """Verify createNode() spawns a process"""
    fc = Flowchart(...)
    node = fc.createNode('Binning', 'Binning.1')
    
    assert node.name() in fc.node_processes
    proc = fc.node_processes[node.name()]
    assert proc.is_alive()

def test_close_node_terminates_process():
    """Verify closeNode() terminates process"""
    fc = Flowchart(...)
    node = fc.createNode('Binning', 'Binning.1')
    
    await fc.nodeCloseRequested(node)
    
    assert node.name() not in fc.node_processes

def test_crash_recovery():
    """Verify crashed process respawns"""
    fc = Flowchart(...)
    node = fc.createNode('Binning', 'Binning.1')
    
    # Kill the process
    proc = fc.node_processes[node.name()]
    proc.kill()
    
    # Wait for monitor to detect and respawn
    await asyncio.sleep(2)
    
    # Should have new process
    new_proc = fc.node_processes[node.name()]
    assert new_proc.is_alive()
    assert new_proc.pid != proc.pid

def test_state_preserved_after_crash():
    """Verify state survives crash"""
    fc = Flowchart(...)
    node = fc.createNode('Binning', 'Binning.1')
    
    # Set some state
    node.shared_state.write({'ctrl': {'bins': 42}})
    
    # Kill process
    fc.node_processes[node.name()].kill()
    await asyncio.sleep(2)
    
    # State should still be there
    state = node.shared_state.read()
    assert state['ctrl']['bins'] == 42
```

---

### Integration Tests

**Tests**:
1. Load complex flowchart (20+ nodes)
2. Open multiple widget windows
3. Simulate crashes during operation
4. Rapid create/close cycles
5. Auto-replace with process respawning

---

### Performance Tests

**Metrics**:
- Startup time (should be faster without MessageBroker)
- Memory usage (one less process)
- Message latency (Queue vs ZMQ)
- Crash recovery time

**Baseline** (Phase 1):
- Startup: ~2 seconds
- Memory: ~150MB (3 processes)
- Message latency: ~1ms (ZMQ)

**Target** (Phase 2):
- Startup: <1.5 seconds (25% faster)
- Memory: ~100MB (2 process layers)
- Message latency: <0.5ms (Queue should be faster)

---

## Risks & Mitigation

### Risk 1: Queue Blocking Issues

**Risk**: `Queue.put()` could block if queue is full

**Mitigation**:
- Use `asyncio.to_thread()` for all Queue operations
- Set reasonable queue size limits
- Monitor queue depths

---

### Risk 2: Process Orphaning

**Risk**: If Flowchart crashes, NodeProcesses become orphans

**Mitigation**:
- Use `daemon=True` for NodeProcesses (auto-killed when parent dies)
- Add cleanup signal handlers in Flowchart
- Shared memory cleanup on startup (detect orphaned segments)

---

### Risk 3: Race Conditions

**Risk**: Process could crash during respawn

**Mitigation**:
- Lock around respawn logic
- Retry with exponential backoff
- Limit respawn attempts (max 3 tries)

---

### Risk 4: State Corruption During Crash

**Risk**: Shared memory could be corrupted mid-write when process crashes

**Mitigation**:
- Atomic writes (write to temp, rename)
- State versioning (detect corruption)
- Keep last-known-good state as backup

---

## Success Criteria

Phase 2 is successful when:

✅ **All Phase 1 tests pass** - no regression  
✅ **Crash recovery works** - processes respawn with state intact  
✅ **No MessageBroker code** - fully removed  
✅ **Startup faster** - measurable improvement  
✅ **User workflow unchanged** - transparent to users  
✅ **Stable for 1 month** - no new crash patterns  

---

## Code Removal

### Files to Remove/Modify

**Remove entirely**:
- None (MessageBroker is a class, not a file)

**Heavy modification**:
- `ami/client/flowchart.py`:
  - Remove `MessageBroker` class (~250 lines removed)
  - Simplify `run_client()` (~20 lines removed)
  - Simplify `NodeProcess` to use Queue (~50 lines changed)

- `ami/flowchart/Flowchart.py`:
  - Add process management (~150 lines added)
  - Add crash recovery (~80 lines added)
  - Remove ZMQ broker references (~30 lines removed)

**Net change**: ~+150 lines (simpler despite adding features)

---

## Questions & Answers

### Q: Why keep NodeProcesses separate at all?

**A**: Performance for pyqtgraph plotting. Separate processes prevent heavy plotting from blocking the GUI.

---

### Q: What happens to in-flight messages during crash?

**A**: Messages in the Queue are lost, but state is safe in shared memory. When process respawns, it reads current state.

---

### Q: Can we support remote NodeProcesses in the future?

**A**: Not with this design (Queue is local-only). Would need to add network layer. But current AMI doesn't support remote processes anyway.

---

### Q: What if shared memory is corrupted?

**A**: Phase 2 doesn't change this risk (same as Phase 1). Need to add corruption detection + recovery in future work.

---

## Future Work (Beyond Phase 2)

### Potential Enhancements

1. **State corruption detection**:
   - Add checksums to shared memory
   - Detect and recover from corruption

2. **Better crash diagnostics**:
   - Capture stack traces before crash
   - Store in shared memory for debugging

3. **Graceful degradation**:
   - If process crashes repeatedly, disable auto-respawn
   - Show user notification

4. **Process pooling**:
   - Pre-spawn NodeProcesses for faster node creation
   - Reuse processes for same node types

---

## Conclusion

Phase 2 removes the MessageBroker intermediary, simplifying AMI's architecture from 3 process layers to 2. This makes the codebase easier to understand, debug, and maintain while preserving all functionality including crash recovery.

The key enabler is **shared memory from Phase 1** - state persistence allows processes to crash and respawn without data loss, making the MessageBroker's coordination role unnecessary.

**Timeline**: 2 weeks  
**Risk**: Medium (changes process architecture)  
**Benefit**: High (simpler, clearer, more maintainable)  

**Prerequisites**: Phase 1 must be complete and stable

---

**End of Phase 2 Design Document**
