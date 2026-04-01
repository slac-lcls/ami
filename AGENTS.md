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

---

## Plan Organization Standards

### CRITICAL: Plan File Organization Convention

All OpenCode agents MUST follow this directory structure when creating or organizing plans in `.opencode/plans/`.

### Directory Structure

```
.opencode/plans/
├── README.md                          # Main index listing all feature areas
├── [general-plans].md                 # Single-file plans (e.g., gui-test-refactoring.md)
└── [feature-name]/                    # Feature-specific directory
    ├── README.md                      # Feature overview, current status, blockers
    ├── 00-PRIORITY-ORDER.md          # Execution order and dependencies
    ├── active/                        # Plans ready to execute NOW
    │   ├── 01-[plan-name].md         # Highest priority (execute first)
    │   ├── 02-[plan-name].md         # Second priority
    │   ├── 03-[plan-name].md         # Third priority
    │   └── ...
    ├── completed/                     # Successfully implemented plans
    │   └── [plan-name].md            # Keep for reference/learning
    └── research/                      # Analysis, investigation, failed approaches
        └── [analysis-name].md        # Architecture decisions, performance analysis
```

### When to Create a Feature Directory

Create a feature subdirectory when ANY of these conditions are met:

1. **Multiple related plans** - 3+ plans for the same feature area
2. **Complex feature** - Requires phased implementation with dependencies
3. **Active development** - Feature has both active and completed plans
4. **Long-term effort** - Feature will have ongoing work over multiple sessions

**Examples:**
- ✅ `ai-graph-builder/` - 4+ plans, complex feature, multiple phases
- ✅ `worker-json-generation/` - Multiple iterations, research + active plans
- ❌ `gui-test-refactoring.md` - Single plan, no subdirectory needed

### Naming Conventions

#### Active Plans (Numbered Priority)
```
01-implement-core-api.md           # Execute first (critical blocker)
02-fix-display-issues.md           # Execute second (depends on 01)
03-update-documentation.md         # Execute third (polish)
04-add-advanced-features.md        # Execute fourth (nice-to-have)
```

**Rules:**
- Use `01-`, `02-`, `03-` prefixes to indicate execution order
- Use descriptive kebab-case names
- Name describes WHAT gets done, not implementation details
- Keep names under 40 characters

#### Special Files
```
00-PRIORITY-ORDER.md               # Always numbered 00, describes execution strategy
README.md                          # Feature overview and quick start guide
```

#### Completed/Research Plans (No Numbers)
```
completed/show-agent-text-plan.md     # Original name preserved
research/qtconsole-failure-analysis.md # Descriptive analysis name
```

### Required Documentation

Every feature directory MUST contain:

#### 1. `README.md` - Feature Overview
```markdown
# [Feature Name]

[1-2 sentence description of what this feature does]

## Current Status: [BLOCKED/IN PROGRESS/READY TO TEST/etc.]

[1-3 sentences describing current state and any blockers]

## Quick Start

**Start here**: `active/01-[plan-name].md`

[Brief explanation of why this is the starting point]

## Execution Order

1. ✅/❌ `01-plan-name.md` - [Brief description] (~X hours)
2. ❌ `02-plan-name.md` - [Brief description] (~X hours)
3. ❌ `03-plan-name.md` - [Brief description] (~X hours)

## Related Documentation

- `[project-root]/STATUS_FILE.md` - Comprehensive status
- `[project-root]/DESIGN_FILE.md` - Original design/proposal
- `skills/[skill-name]/SKILL.md` - AI agent skill (if applicable)
```

#### 2. `00-PRIORITY-ORDER.md` - Execution Strategy
```markdown
# Execution Priority Order

## Start Here: 01-[plan-name].md

**WHY THIS FIRST**: [1-2 sentences explaining why this is the critical blocker]

## Then Execute In Order:

1. ✅ **01-[plan-name].md** (CRITICAL - BLOCKING)
   - [What it does]
   - ~X hours
   - Unblocks: [what depends on this]

2. **02-[plan-name].md** (High priority - [category])
   - [What it does]
   - ~X hours
   - Depends on: 01

3. **03-[plan-name].md** (Medium priority - [category])
   - [What it does]
   - ~X hours

## Total Estimated Time: X-Y hours

## Dependencies Graph
[Optional: ASCII diagram showing dependencies if complex]
```

### Plan Lifecycle Management

#### Creating New Plans

1. **Assess scope**: Single file or feature directory?
2. **If feature directory needed**:
   - Create `[feature-name]/` directory
   - Create `README.md` and `00-PRIORITY-ORDER.md`
   - Create `active/`, `completed/`, `research/` subdirs
3. **Place plan in `active/`** with numbered prefix
4. **Update parent README.md** to reference the new feature

#### Moving Plans Through Lifecycle

```
active/01-implement-api.md
  ↓ (implementation complete)
completed/implement-api.md

active/02-try-async-approach.md
  ↓ (approach failed, documented why)
research/async-approach-failure-analysis.md
```

**Rules:**
- Remove number prefix when moving to `completed/` or `research/`
- Preserve original filename otherwise
- Add date/status to plan header before moving
- Update `README.md` and `00-PRIORITY-ORDER.md` to reflect completion

#### Archiving Entire Features

When a feature is 100% complete:
```
.opencode/plans/feature-name/
  ↓ (all work done, no future plans)
.opencode/archive/feature-name/
```

Update main plans `README.md` to reference the archive location.

### Examples

#### Example 1: AI Graph Builder (Complex Feature)
```
.opencode/plans/ai-graph-builder/
├── README.md                                    # "Natural language graph building interface"
├── 00-PRIORITY-ORDER.md                        # "Start with 01-api-mismatch (BLOCKING)"
├── active/
│   ├── 01-api-mismatch-analysis.md            # MUST FIX FIRST - no API methods
│   ├── 02-fix-chat-widget-issues.md           # Fix UX after API works
│   ├── 03-update-skill-for-chat-mode.md       # Remove dead code
│   └── 04-add-code-toggle.md                  # Polish
├── completed/
│   ├── show-agent-text-plan.md                # Implemented in Phase 4
│   └── create-node-with-labels.md             # Label feature added
└── research/
    ├── qtconsole-failure-analysis.md          # Why QtConsole approach failed
    ├── performance-timing-guide.md            # OpenCode server warmup analysis
    └── rest-api-vs-subprocess-analysis.md     # Architecture decision doc
```

#### Example 2: Worker JSON Generation (Simple Feature)
```
.opencode/plans/worker-json-generation/
├── README.md
├── 00-PRIORITY-ORDER.md
├── active/
│   └── 01-reimplement-worker-json.md
└── completed/
    └── auto-generate-worker-json-plan.md      # Original implementation
```

#### Example 3: Single Plan (No Directory)
```
.opencode/plans/
└── gui-test-refactoring.md                     # Standalone plan
```

### Plan Content Standards

Every plan file MUST have this header:
```markdown
# [Plan Title]

**Date:** [YYYY-MM-DD]  
**Status:** [Planning/Ready to Implement/In Progress/Completed/Abandoned]  
**Priority:** [CRITICAL/High/Medium/Low]  
**Estimated Time:** [X-Y hours]

---

## Executive Summary

[2-3 sentences: What problem does this solve? What's the solution?]

## [Rest of plan content...]
```

### Integration with Main Plans README

The main `.opencode/plans/README.md` should list:
- All standalone plans (with status)
- All feature directories (with brief description + link to feature README)

Example:
```markdown
## Active Plans

### Standalone Plans
- `gui-test-refactoring.md` - ✅ COMPLETED - 2.6x performance improvement

### Feature Development
- **AI Graph Builder** (`ai-graph-builder/`) - 🚧 IN PROGRESS - Natural language graph interface
  - Status: BLOCKED - Missing API implementation
  - Start: `ai-graph-builder/active/01-api-mismatch-analysis.md`
  
- **Worker JSON Generation** (`worker-json-generation/`) - 🔄 NEEDS WORK - Auto-generate configs
  - Status: Needs reimplementation
  - Start: `worker-json-generation/active/01-reimplement-worker-json.md`
```

### Why This Structure?

1. **Discoverability**: New developers/agents know exactly where to start
2. **Priority clarity**: Numbered prefixes show execution order
3. **Context preservation**: Completed/research plans provide learning
4. **Scalability**: Works for simple single plans AND complex multi-phase features
5. **Maintenance**: Clear lifecycle prevents stale/abandoned plans
6. **Team alignment**: Everyone sees current status and next steps

### Agent Responsibilities

When working with plans, OpenCode agents MUST:

1. **Check for existing feature directory** before creating new plans
2. **Follow numbering convention** for active plans (01-, 02-, etc.)
3. **Update README.md files** when adding/completing plans
4. **Move completed plans** to `completed/` directory
5. **Document failed approaches** in `research/` with analysis
6. **Create 00-PRIORITY-ORDER.md** for multi-plan features
7. **Ask user** before reorganizing existing plans

### Questions to Ask Users

When organizing plans, agents should ask:

- "This feature has 4+ related plans. Should I create a feature directory?"
- "Which plan should be executed first? (This becomes 01-)"
- "Are there any hard dependencies between these plans?"
- "Should I move old completed plans to completed/ or archive them?"
