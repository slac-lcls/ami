# AMI Architecture Guide for AI Agents

This document provides a high-level overview of the AMI (Analysis Monitoring Interface) codebase to help AI agents navigate and understand the architecture.

## What is AMI?

AMI is the LCLS-II online graphical analysis monitoring package. It's a distributed system that processes data from LCLS experiments in real-time using a computation graph model.

## Core Architecture

AMI follows a distributed tree architecture with three main components:

### 1. Workers (`ami/worker.py`)
- **Purpose**: Process events from data sources and execute graph computations
- **Key responsibilities**:
  - Read events from data sources (psana, random, etc.)
  - Execute graph operations on events
  - Send results to collectors
  - Handle graph updates and source configuration
- **Important classes**: `Worker` (extends `Node`)
- **Communication**: Connects to collectors, graph service, and export service

### 2. Collectors (`ami/collector.py`)
- **Purpose**: Intermediate collection nodes that aggregate results in a map-reduce architecture
- **Key responsibilities**:
  - Collect results from workers or other collectors
  - Build complete events from partial results
  - Forward aggregated data upstream
  - Forward transitions from workers upstream
- **Important classes**: `GraphCollector` (extends both `Node` and `Collector`)
- **Types**: 
  - **Local collectors**: Do reductions across workers within a single compute node
  - **Global collectors**: Do reductions across local collectors in a cluster

### 3. Manager (`ami/manager.py`)
- **Purpose**: The control point and final collection node for the entire system
- **Key responsibilities**:
  - Final aggregation of all results
  - Broadcast heartbeats and handle data requests from clients (GUIs)
  - Handle configuration changes to the graph
  - Manage worker connections and heartbeats
  - Coordinate transitions across the system
- **Important classes**: `Manager` (extends `Collector`)
- **Communication**: Publishes to clients, receives from collectors

### 4. Client (`ami/client/`)
- **Purpose**: GUI interface for visualizing data and configuring graphs
- **Key files**:
  - `flowchart.py`: Contains the MessageBroker responsible for spawning GUI windows for Node instances
  - `flowchart_messages.py`: Defines message types that the Flowchart class in `ami/flowchart/Flowchart.py` sends to the MessageBroker over ZMQ
- **Technology**: Qt-based graphical interface implemented using qtpy and pyqtgraph

## Key Supporting Components

### Data Flow (`ami/data.py`)
- Defines message types (`MsgTypes`)
- Source abstractions (`Source`)
- Transition states (`Transitions`)
- `RequestedData`: Handles data request configuration

### Communication (`ami/comm.py`)
- **Port definitions** (`Ports`): Standard port assignments for different services
- **Node**: Base class for all network-connected components
- **Collector**: Base class for result collection
- **ResultStore**: Handles sending results to collectors
- **AutoName**: Manages automatic data export
- Uses ZeroMQ for all network communication

### Graph Representations

AMI uses three different graph representations:

1. **GUI Graph (`ami/flowchart/Flowchart.py`)**: 
   - The top layer visualization in `self._graph`
   - Contains `Node` instances for the graphical representation
   - Each `Node` has a `to_operation()` method

2. **Operation Graph (`ami/graph_nodes.py`)**:
   - Middle layer returned by `to_operation()` methods
   - Defines the actual computation being performed
   - Contains operation node implementations

3. **Execution Graph (`ami/graphkit_wrapper.py`)**:
   - Bottom layer using NetworkX nodes
   - Operation nodes are compiled down to NetworkX representation
   - Wraps networkfox library for computation graph execution
   - Handles dependency resolution and execution

### Flowchart (`ami/flowchart/`)
- **Flowchart.py**: Core flowchart data structure and editor
- **Node.py**: Flowchart node abstractions
- **Terminal.py**: Input/output terminals for nodes
- **Editor.py**: Editor GUI components
- **library/**: Node library definitions

### Data Sources

#### Psana Integration (`ami/psana/`)
- **detector.py**: Detector interface wrapper
- **event.py**: Event data handling
- **scan.py**: Scan control integration
- **utils.py**: Psana utility functions
- Provides access to LCLS experimental data

### Export (`ami/export/`)
- Data export functionality
- Support for various export formats and destinations

### Multi-processing (`ami/multiproc.py`, `ami/sync.py`)
- Process management utilities
- Synchronization primitives for distributed execution

## Common Workflows

### Starting AMI

1. **Local mode**: 
   - Random source: `ami-local -n 3 random://examples/worker.json`
   - Psana offline run (single worker): `ami-local -f interval=1 -b 1 psana://exp=rix101331225,run=156`
   - Note: cannot run psana with multiple workers using ami-local due to psana limitation. Need MPI to distribute events otherwise every worker sees all events
   - Runs all components on single node for testing

### Loading a Graph

- Use `-l` flag: `ami-local -l examples/basic.ami`
- Load through GUI interface

## File Organization

```
ami/
├── worker.py              # Worker process implementation
├── manager.py             # Manager process implementation
├── collector.py           # Collector implementation
├── comm.py                # Communication primitives
├── data.py                # Data structures and types
├── graph_nodes.py         # Available graph node types
├── graphkit_wrapper.py    # Graph execution engine
├── client/                # GUI client code
│   ├── flowchart.py
│   └── flowchart_messages.py
├── flowchart/             # Flowchart library
│   ├── Flowchart.py
│   ├── Node.py
│   ├── Terminal.py
│   ├── Editor.py
│   └── library/           # Node type definitions
├── psana/                 # Psana data source integration
│   ├── detector.py
│   ├── event.py
│   └── scan.py
├── export/                # Export functionality
├── pyalgos/               # Algorithm utilities
└── multiproc.py           # Multi-process utilities
```

## Key Concepts

### Computation Graph
- Directed acyclic graph (DAG) of operations
- Nodes perform computations
- Edges represent data flow
- Executed by networkfox

### Transitions
- State changes in the system (Allocate, Configure, Unconfigure, BeginStep, EndStep, Enable, Disable)
- Come from data sources in `ami/data.py`
- Handled by workers which forward them to collectors
- Coordinated across the distributed system

### Result Collection
- Results flow from workers → collectors → manager
- Manager stores aggregated results and broadcasts heartbeat notifications
- Clients request specific feature/plot data on-demand via REQ/REP
- Uses ZeroMQ push/pull patterns for result collection
- Event building reassembles distributed results

### High Water Mark (HWM)
- ZeroMQ parameter controlling queue sizes
- Prevents memory overflow in high-rate scenarios

## Development Tips

### Adding New Graph Nodes
1. **GUI Layer**: Create a class in `ami/flowchart/library/` that subclasses either `Node` or `CtrlNode`
   - To define a node with a GUI, add a class variable `uiTemplate` that is parsed by `generateUi` in `WidgetGroup.py`
   - For custom widgets (e.g., plots), override the `display` method
2. **Operation Layer**: Implement the `to_operation()` method to return an operation node from `ami/graph_nodes.py`
3. **Testing**: Test with simple graph configuration

### Debugging
- Use `ami/forkedpdb.py` for multiprocess debugging
- Check logs from worker, manager, and collector
- Monitor Prometheus metrics if enabled

### Testing

#### Test Organization
- **Unit tests**: `tests/test_*.py` - Test individual components
- **GUI tests**: `tests/test_gui.py` - Test flowchart GUI functionality
- **Integration tests**: Use `ami-local` with example configurations
- **Example configurations**: `examples/` directory
- **Test graphs**: `tests/graphs/*.fc` - Saved flowchart configurations for testing

#### Regression Testing Strategy

**When making changes to AMI, always run regression tests to ensure existing functionality still works.**

##### Quick Regression Test (5 minutes)
Run this before any commit to catch major breakages:

```bash
# 1. Run unit tests
pytest tests/ -v

# 2. Test ami-local with random source and example graph
ami-local -n 3 -l examples/basic.ami

# 3. Verify GUI loads and basic operations work
# - Load a graph
# - Add a node
# - Connect nodes
# - Save graph
```

##### Full Regression Test Suite (15-30 minutes)
Run this before submitting a PR or merging to master:

```bash
# 1. Run all unit tests with coverage
pytest tests/ -v --cov=ami --cov-report=term-missing

# 2. Test all data source types
ami-local -n 3 random://examples/worker.json -l examples/basic.ami
ami-local -n 1 psana://exp=xcsdaq13:run=14 -l examples/basic.ami  # If psana available

# 3. Test auto-generation feature (if applicable)
ami-local -n 3 -l tests/graphs/ATM_crix_new.fc
ami-local -n 3 -l tests/graphs/ATM_crix_new.fc --source-type static

# 4. Test flowchart operations
# - Load multiple .fc files from tests/graphs/
# - Test save/load cycle
# - Test node library (add various node types)
# - Test subgraph operations (if available)

# 5. Test multi-worker scenarios
ami-local -n 1 random://examples/worker.json -l examples/basic.ami
ami-local -n 3 random://examples/worker.json -l examples/basic.ami
ami-local -n 8 random://examples/worker.json -l examples/basic.ami

# 6. Test console mode (headless)
ami-local -n 3 random://examples/worker.json -l examples/basic.ami --console
ami-local -n 3 random://examples/worker.json -l examples/basic.ami --headless

# 7. Check for resource leaks (run multiple times)
for i in {1..5}; do
  ami-local -n 3 random://examples/worker.json -l examples/basic.ami &
  PID=$!
  sleep 10
  kill $PID
  sleep 2
done
```

##### Critical Areas to Test After Changes

**If you modified `ami/flowchart/Flowchart.py`:**
- Test loading and saving .fc files
- Test adding/removing/connecting nodes
- Test Qt event handling and cleanup
- Run `pytest tests/test_gui.py -v`

**If you modified `ami/worker.py` or `ami/data.py`:**
- Test all data source types (static, random, psana)
- Test event processing with various event counts
- Test heartbeat handling and timeouts
- Test transition states (Configure, Unconfigure, etc.)

**If you modified `ami/collector.py` or `ami/manager.py`:**
- Test with various worker counts (1, 3, 8)
- Test result aggregation and event building
- Test client connections and disconnections

**If you modified `ami/local.py`:**
- Test all command-line argument combinations
- Test auto-generation of worker config (if applicable)
- Test IPC vs TCP communication modes
- Test Prometheus integration

**If you modified graph nodes in `ami/flowchart/library/`:**
- Test the specific node type in isolation
- Test connections to/from the node
- Test with real data flowing through
- Check for memory leaks in display widgets

##### Automated Testing with pytest

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_gui.py -v

# Run specific test function
pytest tests/test_gui.py::test_flowchart_from_file -v

# Run with coverage
pytest tests/ --cov=ami --cov-report=html

# Run tests in parallel (faster)
pytest tests/ -n auto

# Run tests with output capture disabled (see print statements)
pytest tests/ -v -s
```

##### GUI Testing Considerations

**Qt GUI tests require special handling:**
- Must run in main thread (use `pytest-qt` fixtures)
- Need proper cleanup of Qt resources (QSocketNotifiers, widgets)
- Mock ZMQ sockets to avoid actual network communication
- Use `qtbot.waitSignal()` for async operations

**Common pitfalls:**
- Forgetting to close/cleanup QSocketNotifiers before closing ZMQ sockets
- Not calling `deleteLater()` on Qt objects
- Resource leaks from Prometheus metrics (need to unregister)
- File descriptor leaks from unclosed sockets

**Best practices:**
- Always use fixtures that properly clean up resources
- Mock external dependencies (ZMQ, network)
- Test cleanup explicitly (create/destroy multiple times)
- Use `qtbot.wait()` to allow Qt event loop to process events

##### Example Test Workflow

```bash
# Before starting work
git checkout -b feature/my-feature
pytest tests/ -v  # Ensure all tests pass before changes

# During development
# Make changes...
pytest tests/test_gui.py::test_specific_feature -v  # Test specific feature

# Before committing
pytest tests/ -v  # Run all tests
ami-local -n 3 -l examples/basic.ami  # Manual smoke test

# Before PR
pytest tests/ --cov=ami --cov-report=html  # Check coverage
# Run full regression test suite
# Review coverage report in htmlcov/index.html
```

##### Regression Test Checklist

Before committing changes, verify:
- [ ] All existing pytest tests pass
- [ ] `ami-local` starts successfully with example configs
- [ ] GUI loads and basic operations work (if GUI changes)
- [ ] No new warnings or errors in logs
- [ ] No resource leaks (file descriptors, memory)
- [ ] Backward compatibility maintained (if applicable)
- [ ] Documentation updated (if API changes)

Before submitting PR:
- [ ] Full regression test suite passes
- [ ] Code coverage hasn't decreased significantly
- [ ] All critical areas tested based on changes
- [ ] Manual testing performed on real use cases
- [ ] Performance hasn't degraded noticeably

## Important Configuration Files

- `examples/worker.json`: Worker configuration
- `*.fc` files: Saved flowchart configurations
- `setup_env.sh`: Environment setup for LCLS-II
- `setup_env_lcls1.sh`: Environment setup for LCLS-I

## Communication Patterns

### ZeroMQ Sockets
- **XPUB/XSUB**: 
  - Manager → Workers/Collectors: Graph updates and configuration changes
  - Manager → Clients: Heartbeats and event notifications
- **PUSH/PULL**: Workers → Collectors → Manager (result collection)
- **REQ/REP**: Clients → Manager (command/control requests, e.g., get_graph, add_graph, set_graph)
- **ROUTER/DEALER**: 
  - Manager internal proxy for view requests (plot/feature data)
  - ROUTER socket (frontend) receives view requests from multiple clients
  - DEALER socket (backend) queues requests to REP socket for processing
  - Enables concurrent handling of multiple client view requests

### Message Types
- Results: Computed graph outputs (PUSH/PULL)
- Transitions: State changes (PUSH/PULL from workers)
- Heartbeats: Keep-alive and event notifications (PUB/SUB)
- Graph updates: Configuration changes (PUB/SUB)
- View requests: On-demand plot/feature data requests (REQ/REP)

## When You Need Help

- For psana integration questions: Check `ami/psana/`
- For GUI/flowchart issues: Check `ami/client/` and `ami/flowchart/`
- For node operations: Check `ami/graph_nodes.py`
- For communication issues: Check `ami/comm.py`
- For graph execution: Check `ami/graphkit_wrapper.py`
