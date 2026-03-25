# Plan: Removing Asyncio from Flowchart GUI

**Date:** 2026-03-25  
**Goal:** Remove asyncio from flowchart GUI components while keeping MessageBroker async  
**Strategy:** Minimal changes, high compatibility - use QSocketNotifier for ZMQ, synchronous GraphCommHandler

---

## Summary of Changes

**What stays async:**
- `MessageBroker` in `ami/client/flowchart.py` (separate process with its own event loop)
- `BrokerHelper` test fixture (supports MessageBroker)

**What becomes synchronous:**
- `Flowchart` class ZMQ communication
- `FlowchartCtrlWidget` and all its methods
- `Features` class
- `FlowchartWidget.build_views()` and related methods
- Test fixtures and test methods

---

## Architecture Changes

### Before:
```
Main Process:
  QEventLoop (qasync) integrating Qt + asyncio
    ├─ Flowchart (zmq.asyncio.Context)
    │   └─ async ZMQ send/recv
    └─ FlowchartCtrlWidget
        └─ AsyncGraphCommHandler (async methods)

MessageBroker Process:
  asyncio event loop
    └─ ZMQ broker sockets (async)
```

### After:
```
Main Process:
  Qt Event Loop (native)
    ├─ Flowchart (zmq.Context)
    │   ├─ QSocketNotifier for ZMQ sockets
    │   └─ sync ZMQ send/recv
    └─ FlowchartCtrlWidget
        └─ GraphCommHandler (sync methods)

MessageBroker Process:
  asyncio event loop (unchanged)
    └─ ZMQ broker sockets (async)
```

---

## Phase 1: Replace AsyncGraphCommHandler with GraphCommHandler

### File: `ami/flowchart/Flowchart.py`

#### 1.1 Update imports
- Keep: `from ami.comm import AsyncGraphCommHandler, GraphCommHandler` (for now)
- Remove eventually: `import asyncio`, `import zmq.asyncio`, `from ami.asyncqt import asyncSlot`
- Add: `import threading` (for Features class)
- Add: `from qtpy.QtCore import QSocketNotifier, QTimer`

#### 1.2 FlowchartCtrlWidget.__init__() (line 748)
**Change:**
```python
# Line 752 - Replace AsyncGraphCommHandler with GraphCommHandler
self.graphCommHandler = GraphCommHandler(graphmgr_addr.name, graphmgr_addr.comm)
```

#### 1.3 Convert all `@asyncSlot` methods to regular slots

**Methods to convert (remove `@asyncSlot`, remove `async`, remove `await`):**

1. **`applyClicked()` (line 800-912)**
   - Remove `@asyncSlot()` decorator
   - Change `async def applyClicked` → `def applyClicked`
   - Replace all `await self.graphCommHandler.X` → `self.graphCommHandler.X`
   - Replace all `await self.features.X` → `self.features.X`
   - Replace all `await self.chartWidget.build_views` → `self.chartWidget.build_views`
   - Replace `await self.graphCommHandler.updatePlots` → `self.graphCommHandler.updatePlots`

2. **`resetClicked()` (line 994-1002)**
   - Remove `@asyncSlot()` decorator
   - Change `async def resetClicked` → `def resetClicked`
   - Replace `await self.graphCommHandler.destroy()` → `self.graphCommHandler.destroy()`
   - Replace `await self.applyClicked()` → `self.applyClicked()`

3. **`clear()` (line 1014-1022)**
   - Remove `@asyncSlot()` decorator
   - Change `async def clear` → `def clear`
   - Replace `await self.graphCommHandler.destroy()` → `self.graphCommHandler.destroy()`
   - Replace `await self.chart.clear()` → `self.chart.clear()`
   - Replace `await self.graphCommHandler.updatePlots` → `self.graphCommHandler.updatePlots`

4. **`configureApply()` (line 1058-1071)**
   - Remove `@asyncSlot(object)` decorator  
   - Change `async def configureApply` → `def configureApply`
   - Replace `await self.graphCommHandler.updateSources` → `self.graphCommHandler.updateSources`

5. **`libraryUpdated()` (line 1073-1080)**
   - Remove `@asyncSlot()` decorator
   - Change `async def libraryUpdated` → `def libraryUpdated`
   - Replace `await self.chart.broker.send_string` → `self.chart.broker.send_string`
   - Replace `await self.chart.broker.send_pyobj` → `self.chart.broker.send_pyobj`
   - Replace `await self.graphCommHandler.updatePath` → `self.graphCommHandler.updatePath`

6. **`libraryReloaded()` (line 1084-1093)**
   - Remove `@asyncSlot(object)` decorator
   - Change `async def libraryReloaded` → `def libraryReloaded`
   - Replace `await self.chart.broker.send_string` → `self.chart.broker.send_string`
   - Replace `await self.chart.broker.send_pyobj` → `self.chart.broker.send_pyobj`

#### 1.4 FlowchartWidget methods

**Methods to convert:**

1. **`selectionChanged()` (line 1194-1240)**
   - Remove `@asyncSlot()` decorator
   - Change `async def selectionChanged` → `def selectionChanged`
   - Replace `await self.build_views` → `self.build_views`
   - Replace `await self.ctrl.graphCommHandler.metadata` → `self.ctrl.graphCommHandler.metadata`

2. **`build_views()` (line 1242-1339)**
   - Remove `@asyncSlot` decorator (if present)
   - Change `async def build_views` → `def build_views`
   - Replace `await self.ctrl.features.get` → `self.ctrl.features.get`
   - Replace `await self.ctrl.features.discard` → `self.ctrl.features.discard`
   - Replace `await self.ctrl.graphCommHandler.export` → `self.ctrl.graphCommHandler.export`
   - Replace `await self.chart.broker.send_string` → `self.chart.broker.send_string`
   - Replace `await self.chart.broker.send_pyobj` → `self.chart.broker.send_pyobj`
   - Replace `await self.ctrl.graphCommHandler.view` → `self.ctrl.graphCommHandler.view`
   - Replace `await self.ctrl.graphCommHandler.updatePlots` → `self.ctrl.graphCommHandler.updatePlots`

#### 1.5 Features class (line 1461-1512)

**Changes:**
```python
class Features(object):
    def __init__(self, graphCommHandler):
        self.features_count = collections.defaultdict(set)
        self.features = {}
        self.plots = {}
        self.graphCommHandler = graphCommHandler
        self.lock = threading.Lock()  # Change from asyncio.Lock()

    def get(self, name, in_var):  # Remove async
        with self.lock:  # Change from async with
            if in_var in self.features:
                topic = self.features[in_var]
                new = False
            else:
                topic = self.graphCommHandler.auto(in_var)
                self.features[in_var] = topic
                new = True

            self.features_count[in_var].add(name)
            return new, topic

    def discard(self, name, in_var=None):  # Remove async
        with self.lock:  # Change from async with
            if in_var and in_var in self.features_count:
                self.features_count[in_var].discard(name)
                if not self.features_count[in_var]:
                    del self.features[in_var]
                    del self.features_count[in_var]
                    self.plots.pop(name, None)
                return True
            else:
                for in_var, viewers in self.features_count.items():
                    viewers.discard(name)
                    if not viewers and name in self.features:
                        del self.features[name]
                        self.plots.pop(name, None)
                return True

        return False

    # add_plot and remove_plot stay the same

    def reset(self):  # Remove async
        with self.lock:  # Change from async with
            self.features = {}
            self.features_count = collections.defaultdict(set)
            self.plots = {}
```

---

## Phase 2: Convert Flowchart class ZMQ communication

### File: `ami/flowchart/Flowchart.py`

#### 2.1 Flowchart.__init__() (line 57-95)

**Change context:**
```python
# Line 66 - Replace zmq.asyncio.Context with zmq.Context
self.ctx = zmq.Context()
```

**Add QSocketNotifiers for ZMQ sockets:**
```python
# After creating sockets, add QSocketNotifiers
# These will be initialized when widget is created
self._broker_notifier = None
self._graphinfo_notifier = None  
self._checkpoint_notifier = None
```

#### 2.2 Create socket notification handlers

**Add new methods to Flowchart class:**

```python
def setup_socket_notifiers(self):
    """Setup QSocketNotifiers for ZMQ sockets after Qt app is running."""
    from qtpy.QtCore import QSocketNotifier
    
    # Broker socket notifier (for sending to node processes)
    # Typically we only send, so may not need read notifier
    
    # Graphinfo socket notifier (receives source updates)
    fd = self.graphinfo.get(zmq.FD)
    self._graphinfo_notifier = QSocketNotifier(fd, QSocketNotifier.Read)
    self._graphinfo_notifier.activated.connect(self._handle_graphinfo)
    
    # Checkpoint socket notifier (receives ctrlnode updates)
    fd = self.checkpoint.get(zmq.FD)
    self._checkpoint_notifier = QSocketNotifier(fd, QSocketNotifier.Read)
    self._checkpoint_notifier.activated.connect(self._handle_checkpoint)

def _handle_graphinfo(self):
    """Handle readable graphinfo socket."""
    # Check if socket is actually readable
    events = self.graphinfo.get(zmq.EVENTS)
    if events & zmq.POLLIN:
        try:
            topic = self.graphinfo.recv_string(zmq.NOBLOCK)
            source = self.graphinfo.recv_string(zmq.NOBLOCK)
            msg = self.graphinfo.recv_pyobj(zmq.NOBLOCK)
            # Process message (code from updateSources)
            self._process_source_update(topic, source, msg)
        except zmq.Again:
            pass  # No message available

def _handle_checkpoint(self):
    """Handle readable checkpoint socket."""
    events = self.checkpoint.get(zmq.EVENTS)
    if events & zmq.POLLIN:
        try:
            topic = self.checkpoint.recv_string(zmq.NOBLOCK)
            msg = self.checkpoint.recv_pyobj(zmq.NOBLOCK)
            # Process message (code from updateState)
            self._process_checkpoint_update(topic, msg)
        except zmq.Again:
            pass

def _process_source_update(self, topic, source, msg):
    """Process source update message (extracted from updateSources)."""
    # Move the body of updateSources() here
    # Lines 645-726 logic

def _process_checkpoint_update(self, topic, msg):
    """Process checkpoint update message (extracted from updateState)."""
    # Move the body of updateState() here
    # Lines 605-639 logic
```

#### 2.3 Convert async ZMQ send methods to sync

**Methods to convert:**

1. **`send_requested_data()` (line 198-200)**
   ```python
   def send_requested_data(self, requested_data):  # Remove async
       ctrl = self.widget()
       ctrl.graphCommHandler.update_requested_data(requested_data)  # Remove await
   ```

2. **`nodeClosed()` (line 203-233)** - Remove `@asyncSlot(object, object)`, remove `async`, remove all `await`

3. **`nodeTermAdded()` (line 237-242)** - Remove async and @asyncSlot, remove await from sends

4. **`nodeTermRemoved()` (line 245-249)** - Remove async and @asyncSlot, remove await from sends

5. **`nodeTermConnected()` (line 252-280)** - Remove async and @asyncSlot, remove await from sends

6. **`nodeTermDisconnected()` (line 285-312)** - Remove async and @asyncSlot, remove await from sends

7. **`nodeLabelChanged()` (line 325-330)** - Remove async and @asyncSlot, remove await from sends

8. **`nodeEnabled()` (line 333-362)** - Remove async and @asyncSlot, remove all await keywords

#### 2.4 Replace run() method with initialize()

**Current run() method (line 727-734):**
```python
async def run(self, load=None):
    tasks = [asyncio.create_task(self.updateState()),
             asyncio.create_task(self.updateSources())]

    if load:
        await self.loadFile(load)

    await asyncio.gather(*tasks)
```

**New approach:**
```python
def initialize(self, load=None):
    """Initialize flowchart, setup socket notifiers, optionally load file."""
    # Setup socket notifiers to handle updates
    self.setup_socket_notifiers()
    
    # Initial source update (blocking)
    self.updateSources(init=True)
    
    # Load file if specified
    if load:
        self.loadFile(load)
```

#### 2.5 Convert file operations

**`loadFile()` (line 533-559)** - Remove `async`, remove all `await` keywords

**`clear()` (line 591-600)** - Remove `async`, remove all `await` keywords

**`updateSources()` (line 641-726)** - Convert to handle both init and notifier cases:
```python
def updateSources(self, init=False):  # Remove async
    """Update sources from graphinfo socket (called by notifier or during init)."""
    if init:
        # Blocking initial update
        # Keep trying until we get source info
        while True:
            events = self.graphinfo.get(zmq.EVENTS)
            if events & zmq.POLLIN:
                topic = self.graphinfo.recv_string()
                source = self.graphinfo.recv_string()
                msg = self.graphinfo.recv_pyobj()
                self._process_source_update(topic, source, msg)
                break
            else:
                import time
                time.sleep(0.01)  # Brief sleep before retry
    else:
        # Called by notifier - already checked POLLIN
        pass  # _handle_graphinfo already called _process_source_update
```

**`updateState()` (line 603-639)** - Can be removed entirely, replaced by `_handle_checkpoint()`

---

## Phase 3: Update Client Entry Point

### File: `ami/client/flowchart.py`

#### 3.1 run_editor_window() function (line 40-120)

**Changes:**
```python
def run_editor_window(broker_addr, graphmgr_addr, checkpoint_addr, load=None, prometheus_dir=None,
                      prometheus_port=None, hutch=None, configure=False, save_dir=None):
    # dmypy setup stays the same (lines 42-56)
    
    app = QtWidgets.QApplication([])

    if THEME:
        qdarktheme.setup_theme(THEME)

    # REMOVE these lines:
    # loop = QEventLoop(app)
    # asyncio.set_event_loop(loop)

    # Create main window (lines 66-96 stay the same)
    
    # Create flowchart...
    
    # REMOVE this:
    # with loop:
    #     loop.run_until_complete(fc.updateSources(init=True))

    # REPLACE with:
    fc.initialize(load=load)  # Sync initialization with socket notifier setup
    
    # Rest of function stays the same
    # Start Qt event loop normally
    app.exec_()
```

#### 3.2 Keep MessageBroker unchanged

**No changes to MessageBroker class** - it runs in separate process with its own asyncio event loop.

#### 3.3 run_client() function (line 599-616)

**Changes:**
```python
def run_client(graphmgr_addr, load, prometheus_dir, prometheus_port, hutch, use_opengl, use_numba,
               configure, save_dir):
    # Lines 600-606 stay the same
    
    # MessageBroker still needs asyncio
    # Run it in a separate thread with its own event loop
    def run_broker():
        asyncio.run(mb.run())
    
    import threading
    broker_thread = threading.Thread(target=run_broker, daemon=True)
    broker_thread.start()
    
    # Wait for editor to exit (blocking)
    mb.wait_editor_exit()
    
    # Cleanup happens when context manager exits
```

---

## Phase 4: Update Test Fixtures

### File: `tests/conftest.py`

#### 4.1 qevent_loop fixtures (lines 237-252)

Keep for backward compatibility but simplify:
```python
@pytest.fixture(scope='session')
def qevent_loop_gbl(qapp):
    # Keep for other async tests if any
    from ami.asyncqt import QEventLoop
    with QEventLoop(qapp) as loop:
        yield loop

@pytest.fixture(scope='function')  
def qevent_loop(qevent_loop_gbl):
    # Simplified - no asyncio.set_event_loop needed for flowchart
    yield qevent_loop_gbl
```

### File: `tests/test_gui.py`

#### 4.2 Remove event_loop fixture override (lines 66-74)

Remove this fixture entirely - not needed if tests aren't async anymore.

#### 4.3 Update flowchart fixture (lines 141-192)

**Changes:**
```python
@pytest.fixture(scope='function')
def flowchart(request, workerjson, broker, ipc_dir, graphmgr_addr, dmypy):  # Remove qevent_loop
    # Lines 142-165 stay the same
    
    # Create flowchart
    with Flowchart(broker_addr=broker.broker_sub_addr,
                   graphmgr_addr=graphmgr_addr,
                   checkpoint_addr=broker.checkpoint_pub_addr) as fc:

        # REMOVE: qevent_loop.run_until_complete(fc.updateSources(init=True))
        # REPLACE with:
        fc.initialize()  # Sync initialization
        
        yield (fc, broker)
    
    # Rest stays the same
```

#### 4.4 Update flowchart_hdf fixture (lines 195-261)

Same changes as flowchart fixture - remove qevent_loop, call fc.initialize()

#### 4.5 Update test_editor (lines 326-361)

**Changes:**
```python
# REMOVE @pytest.mark.asyncio decorator
# Change async def to regular def
def test_editor(qtbot, flowchart, tmp_path):
    flowchart, broker = flowchart

    qtbot.addWidget(flowchart.widget())

    flowchart.createNode('Roi2D')
    roi_node = flowchart.nodes(data='node')['Roi2D.0']

    node_name = 'cspad'
    node_type = flowchart.source_library.getSourceType(node_name)
    node = SourceNode(name=node_name, terminals={'Out': {'io': 'out', 'ttype': node_type}})

    flowchart.addNode(node=node)
    cspad_node = flowchart.nodes(data='node')['cspad']

    cspad_out = cspad_node._outputs['Out']
    roi_in = roi_node._inputs['In']

    cspad_out().connectTo(roi_in())
    
    # REMOVE: await asyncio.sleep(0.1)
    # REPLACE with Qt test wait:
    qtbot.wait(100)  # Wait 100ms for nodeTermConnected slot to execute
    
    assert len(flowchart._graph.edges()) == 1

    widget = flowchart.widget()

    pth = os.path.join(tmp_path, 'graph.fc')
    widget.setCurrentFile(pth)
    widget.saveClicked()

    # REMOVE await
    widget.clear()
    assert len(flowchart._graph.edges()) == 0

    # REMOVE await
    flowchart.loadFile(pth)
    assert len(flowchart._graph.edges()) == 1
```

---

## Phase 5: Cleanup

### 5.1 Remove unused imports

After all conversions, remove from `ami/flowchart/Flowchart.py`:
- `import asyncio` (if no longer used)
- `import zmq.asyncio` (if no longer used)
- `from ami.asyncqt import asyncSlot` (if no longer used)

Keep `from ami.comm import GraphCommHandler` (remove `AsyncGraphCommHandler` from import if not used elsewhere).

### 5.2 Verify signal connections

Ensure all signal connections work without async:
- Button clicks connect to regular methods (not async slots)
- Qt calls them synchronously on main thread
- ZMQ operations through QSocketNotifier also run on main thread

---

## Implementation Checklist

### Phase 1: GraphCommHandler
- [ ] FlowchartCtrlWidget: Change to GraphCommHandler
- [ ] Features class: Replace asyncio.Lock with threading.Lock
- [ ] Features.get(): Remove async/await
- [ ] Features.discard(): Remove async/await
- [ ] Features.reset(): Remove async/await
- [ ] applyClicked(): Remove async/await
- [ ] resetClicked(): Remove async/await
- [ ] clear(): Remove async/await
- [ ] configureApply(): Remove async/await
- [ ] libraryUpdated(): Remove async/await
- [ ] libraryReloaded(): Remove async/await
- [ ] FlowchartWidget.selectionChanged(): Remove async/await
- [ ] FlowchartWidget.build_views(): Remove async/await

### Phase 2: Flowchart ZMQ
- [ ] Flowchart.__init__(): Change to zmq.Context
- [ ] Add setup_socket_notifiers() method
- [ ] Add _handle_graphinfo() method
- [ ] Add _handle_checkpoint() method
- [ ] Add _process_source_update() method
- [ ] Add _process_checkpoint_update() method
- [ ] Convert send_requested_data()
- [ ] Convert nodeClosed()
- [ ] Convert nodeTermAdded()
- [ ] Convert nodeTermRemoved()
- [ ] Convert nodeTermConnected()
- [ ] Convert nodeTermDisconnected()
- [ ] Convert nodeLabelChanged()
- [ ] Convert nodeEnabled()
- [ ] Replace run() with initialize()
- [ ] Convert loadFile()
- [ ] Convert clear()
- [ ] Convert/refactor updateSources()
- [ ] Remove/refactor updateState()

### Phase 3: Client
- [ ] run_editor_window(): Remove QEventLoop, use fc.initialize()
- [ ] run_client(): Keep MessageBroker async, run in thread

### Phase 4: Tests
- [ ] Update/simplify qevent_loop fixtures
- [ ] Remove event_loop fixture override
- [ ] Update flowchart fixture
- [ ] Update flowchart_hdf fixture
- [ ] Update test_editor test
- [ ] Update any other async tests

### Phase 5: Cleanup
- [ ] Remove unused imports
- [ ] Verify all tests pass
- [ ] Manual testing of GUI operations
- [ ] Update documentation if needed

---

## Testing Strategy

### Unit Tests
1. Run existing test suite: `pytest tests/test_gui.py`
2. Verify all tests pass after conversion
3. Check for any deprecation warnings

### Manual GUI Testing
1. **Basic operations:**
   - Launch AMI client
   - Load/save flowcharts
   - Add/remove nodes
   - Connect/disconnect terminals
   
2. **Apply operations:**
   - Create simple graph
   - Click Apply button
   - Verify graph is submitted to manager
   - Check for errors in status bar

3. **View operations:**
   - Create plot nodes
   - View plots
   - Verify data updates

4. **Advanced:**
   - Source configuration
   - Library reload
   - Reset graph
   - IPython console (uses sync GraphCommHandler already)

### Performance Testing
- Compare GUI responsiveness before/after
- Check for any blocking operations that freeze GUI
- Monitor ZMQ socket message handling

---

## Risk Mitigation

### Risk 1: Blocking GUI Thread
**Concern:** Synchronous GraphCommHandler calls might block GUI

**Mitigation:**
- GraphCommHandler operations are already fast (REQ/REP pattern)
- If needed, can show progress dialog for long operations
- Most operations complete in milliseconds

### Risk 2: Missing ZMQ Messages
**Concern:** QSocketNotifier might miss messages

**Mitigation:**
- QSocketNotifier is event-driven, won't miss messages
- ZMQ FD triggers when messages available
- Can add message queue if needed

### Risk 3: Thread Safety
**Concern:** ZMQ sockets not thread-safe

**Mitigation:**
- All ZMQ operations stay on main Qt thread
- QSocketNotifiers run on main thread
- threading.Lock in Features class protects shared state

### Risk 4: Test Failures
**Concern:** Tests might fail after conversion

**Mitigation:**
- Convert tests incrementally
- Use qtbot.wait() instead of asyncio.sleep()
- Keep test coverage high

---

## Open Questions

### 1. Initialization Approach

**Question:** How should we handle `fc.updateSources(init=True)` during startup?

**Recommendation:** Blocking call before Qt event loop starts - simpler and matches current behavior
```python
fc.initialize()  # Blocks until sources received
app.exec_()
```

### 2. Error Handling

**Question:** Should we preserve all existing error handling patterns?

**Recommendation:** Keep existing error handling, add dialogs where user needs feedback

### 3. MessageBroker Thread vs Process

**Question:** MessageBroker currently runs in separate process. Keep as-is?

**Recommendation:** Keep as separate process - less refactoring needed

---

## Summary

This plan converts the flowchart GUI from async/await to synchronous Qt patterns while keeping the MessageBroker async. Key insights:

1. **GraphCommHandler already has sync version** - just switch to it
2. **QSocketNotifier integrates ZMQ with Qt** - event-driven, no polling needed
3. **MessageBroker stays async** - it's isolated in separate process
4. **Tests need qtbot.wait()** - instead of asyncio.sleep()

The conversion is straightforward because:
- Most async operations were just wrapping synchronous ZMQ calls
- GraphCommHandler is request/reply (inherently synchronous)
- Qt event loop can handle ZMQ sockets natively via QSocketNotifier

**Estimated effort:** ~10-12 hours of focused work
- Phase 1: 2-3 hours (straightforward find/replace)
- Phase 2: 3-4 hours (requires careful socket notifier setup)
- Phase 3: 1 hour (minimal changes)
- Phase 4: 2-3 hours (test updates)
- Phase 5: 1 hour (cleanup, testing)
