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
- **Technology**: PyQt-based graphical interface

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
- **AutoExport**: Manages automatic data export
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
   - Wraps graphkit library for computation graph execution
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

1. **Workers**: `ami-worker -n 3 psana://exp=rix101331225,run=156`
   - Starts 3 worker processes
   - Connects to specified data source

2. **Manager**: `ami-manager`
   - Starts the manager process
   - Waits for worker connections

3. **Client**: `ami-client`
   - Launches GUI
   - Connects to manager

4. **Local mode**: 
   - Random source: `ami-local -n 3 random://examples/worker.json`
   - Psana offline run (single worker): `ami-local -f interval=1 -b 1 psana://exp=rix101331225,run=156`
   - Psana with multiple workers: `ami-mpi -n 4 psana://exp=rix101345725,run=67` (ami-local does not support multiple workers with psana)
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
- Executed by graphkit

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
- Example configurations in `examples/`
- Test files in `tests/`
- `.fc` files are saved flowchart configurations

## Important Configuration Files

- `examples/worker.json`: Worker configuration
- `*.fc` files: Saved flowchart configurations
- `setup_env.sh`: Environment setup for LCLS-II
- `setup_env_lcls1.sh`: Environment setup for LCLS-I

## Communication Patterns

### ZeroMQ Sockets
- **PUB/SUB**: 
  - Manager → Workers/Collectors: Graph updates and configuration changes
  - Manager → Clients: Heartbeats and event notifications
- **PUSH/PULL**: Workers → Collectors → Manager (result collection)
- **REQ/REP**: Clients → Manager (on-demand requests for specific feature/plot data)

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
