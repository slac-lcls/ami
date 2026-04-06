# Heartbeat Event Builder - Architecture Documentation

## Overview

The **Heartbeat Event Builder** is the core synchronization mechanism in AMI's distributed architecture. It coordinates data collection across multiple workers, collectors, and the manager by assembling partial results from distributed sources into complete "events" before processing them through the computation graph.

Unlike traditional event builders that simply aggregate data, AMI's event builder also **executes computation graphs** during the aggregation process, enabling true distributed map-reduce computation while maintaining event consistency across the system.

This document explains the event builder's architecture, design principles, and key mechanisms that enable AMI's distributed real-time analysis.

---

## Key Concepts

### What is a Heartbeat?

A **heartbeat** is AMI's fundamental unit of synchronization - it represents a single logical "event" distributed across multiple workers.

**Data Structure** (`ami/data.py:80-118`):
```python
@dataclass(frozen=True)
class Heartbeat:
    identity: int = 0      # Unique sequential ID number
    timestamp: float = 0.0  # Unix timestamp when created
```

**Properties**:
- **Immutable** (frozen dataclass) - cannot be modified after creation
- **Hashable** - can be used as dictionary key
- **Comparable to integers** - implements `__lt__`, `__eq__`, etc. for easy comparison
- **Sequential** - identity values increase monotonically

**Example**: Heartbeat 4576354907 represents a single experimental event that all 30 workers must process independently, then aggregate their results.

---

### The Event Builder Pattern

AMI uses a **tree-structured map-reduce architecture** where each level synchronizes contributions from the level below:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    AMI Distributed System                            │
│                   (Map-Reduce with Heartbeats)                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Worker 0 ──┐                                                        │
│  Worker 1 ──┤                                                        │
│  Worker 2 ──┤──> Local Collector 0 ──┐                              │
│     ...     │    (GraphBuilder:       │                              │
│  Worker 9 ──┘     num_contribs=10)   │                              │
│                                        │                              │
│  Worker 10 ─┐                         │                              │
│  Worker 11 ─┤                         ├──> Global Collector          │
│  Worker 12 ─┤──> Local Collector 1 ──┘    (GraphBuilder:            │
│     ...     │                               num_contribs=3)          │
│  Worker 19 ─┘                               │                        │
│                                              │                        │
│  Worker 20 ─┐                               ├──> Manager             │
│  Worker 21 ─┤                               │    (GraphBuilder:      │
│  Worker 22 ─┤──> Local Collector 2 ────────┘     num_contribs=1)    │
│     ...     │                                                         │
│  Worker 29 ─┘                                                         │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘

Each level uses GraphBuilder to:
  1. Wait for contributions from N sources
  2. Execute computation graph when complete OR depth exceeded
  3. Send aggregated results to next level
```

**Key Insight**: Each arrow represents contributions for a single heartbeat. The event builder at each level waits for all expected contributions before processing, ensuring data consistency.

---

## Core Classes

### ContributionBuilder (Base Class)

**Location**: `ami/comm.py:563-612`

Abstract base class for tracking contributions from N sources using an efficient bitmask mechanism.

**Key Data Structures**:
```python
class ContributionBuilder:
    def __init__(self, num_contribs):
        self.num_contribs = num_contribs  # Expected number of contributors
        self.pending = {}                  # {eb_key : payload}
        self.contribs = {}                 # {eb_key : bitmask}
```

**The Bitmask Tracking Mechanism**:

Instead of tracking each contributor in an array, AMI uses a single integer bitmask where each bit represents one contributor:

```
Bitmask Contribution Tracking (4 workers example):

Initial:     contribs[heartbeat] = 0b0000  (no contributions)
Worker 0:    contribs[heartbeat] = 0b0001  (worker 0 arrived)
Worker 1:    contribs[heartbeat] = 0b0011  (workers 0,1 arrived)
Worker 2:    contribs[heartbeat] = 0b0111  (workers 0,1,2 arrived)
Worker 3:    contribs[heartbeat] = 0b1111  (ALL arrived - READY!)

Check ready: (1 << num_contribs) - 1 == contribs[heartbeat]
             (1 << 4) - 1 == 0b1111 ✓
```

**Implementation**:
```python
def mark(self, eb_key, eb_id):
    """Set bit for contributor eb_id."""
    if eb_key not in self.contribs:
        self.contribs[eb_key] = 0
    self.contribs[eb_key] |= 1 << eb_id

def ready(self, eb_key):
    """Check if all contributors have sent data."""
    if eb_key not in self.contribs:
        return False
    return ((1 << self.num_contribs) - 1) == self.contribs[eb_key]
```

**Efficiency**:
- O(1) operations for mark and ready check
- 4-8 bytes per heartbeat vs 30+ bytes for an array
- Fast bitwise operations

**Key Methods**:
- `mark(eb_key, eb_id)` - Set bit for contributor eb_id
- `ready(eb_key)` - Check if all bits set (all contributors arrived)
- `update(eb_key, eb_id, data)` - Add contribution and mark as received
- `complete(eb_key, identity, drop)` - Process complete heartbeat

---

### GraphBuilder (Computation + Event Building)

**Location**: `ami/comm.py:614-833`

Extends ContributionBuilder to not only track contributions but also **execute computation graphs** on complete or pruned heartbeats.

**Key Data Structures**:
```python
class GraphBuilder(ContributionBuilder):
    def __init__(self, num_contribs, depth, color, completion):
        super().__init__(num_contribs)
        self.depth = depth                      # Max pending heartbeats
        self.graph = None                       # Computation graph
        self.pending = {}                       # {eb_key : Store}
        self.latest = Heartbeat(0, 0)          # Most recent heartbeat
```

**Critical Parameters**:

- **`num_contribs`**: How many sources to wait for
  - Local collector: 10 workers
  - Global collector: 3 local collectors  
  - Manager: 1 global collector

- **`depth`**: Maximum pending heartbeats before pruning (memory management)
  - Default: 1 (aggressive - only keep latest heartbeat)
  - Higher depth: More memory, less data loss
  - Lower depth: Less memory, more pruning

- **`color`**: Component type (Worker, LocalCollector, GlobalCollector)
  - Used for logging and metrics
  - Determines graph execution context

---

## Pruning Mechanisms

AMI has **TWO independent pruning mechanisms** that can work together or separately:

1. **Depth-based pruning** - Triggered when pending queue exceeds depth limit
2. **Timeout-based pruning** - Triggered when no messages arrive within timeout period

Both mechanisms call the same `GraphBuilder.prune()` method to process incomplete heartbeats.

### Why Pruning Exists

With 30 asynchronous workers, contributions arrive at different times. Without pruning, memory would grow unbounded as incomplete heartbeats accumulate. Pruning removes old heartbeats to manage memory and ensure forward progress.

### 1. Depth-Based Pruning (Always Active)

**Location**: `ami/comm.py:644-684`

```python
def prune(self, identity, prune_key=None, drop=False):
    """Remove old heartbeats that exceeded depth limit."""
    
    # Calculate how many heartbeats to keep
    if prune_key is None:
        depth = self.depth
    else:
        depth = self.latest.identity - prune_key.identity
    
    # If we have more than 'depth' pending heartbeats, prune oldest
    if len(self.pending) > depth:
        for eb_key in reversed(sorted(self.pending.keys())[depth:]):
            # Complete this heartbeat (even if incomplete)
            times, size = self.complete(eb_key, identity, drop)
```

**Trigger**: `len(self.pending) > depth`

When a new heartbeat arrives and the number of pending heartbeats exceeds the depth limit, the oldest heartbeats are pruned.

### The `drop` Parameter

- **`drop=False`**: Send incomplete data upstream (partial contributions)
  - Allows partial results to be used
  - Better than losing all data
  
- **`drop=True`**: Discard incomplete data (lose stragglers)
  - Ensures only complete data is processed
  - Used during transitions

**Example Timeline** (30 workers, depth=1):

```
Time 0:   Workers 0-9 send heartbeat 100
          → pending[100] has 10/30 workers

Time 1:   Workers 0-29 send heartbeat 101
          → pending = {100: 10/30, 101: 30/30}
          → len(pending) = 2, depth = 1
          → PRUNE heartbeat 100 with drop=False
          → Send incomplete data (10/30 workers) upstream
          
Time 2:   Workers 10-29 complete heartbeat 101
          → Heartbeat 101 is complete, sent upstream
```

### 2. Timeout-Based Pruning (Optional)

**Purpose**: Prune heartbeats when the system has been idle (no messages) for a specified duration. This is particularly useful for **low event rate systems with many workers** where workers may take a long time to process events.

**When It Triggers**:
- ZMQ `poll()` times out with no messages received for the specified duration
- Timeout duration specified by `--timeout` CLI flag (in milliseconds)
- Default: `None` (disabled)

**Implementation**: `ami/collector.py:120-125, ami/comm.py:1287-1305`

**How It Works**:
```python
# Main poll loop waits for messages with timeout
for sock, flag in self.poller.poll(timeout=self.timeout):
    # Process messages from workers/collectors
    received = True

# If poll() returned empty (timed out), prune all pending heartbeats
if not received and self.timeout:
    self.poll_timeout()  # Prunes ALL graphs
```

**Key Differences from Depth-Based Pruning**:

| Aspect | Depth-Based | Timeout-Based |
|--------|------------|---------------|
| **Trigger** | `len(pending) > depth` | No messages for `timeout` ms |
| **What gets pruned** | Oldest heartbeats exceeding depth | ALL pending heartbeats in ALL graphs |
| **When** | After receiving new heartbeat | When system is idle |
| **Controlled by** | `--eb-depth N` flag | `--timeout N` flag |
| **Default** | depth=1 (active) | None (disabled) |

**Configuration**:
```bash
# Enable timeout-based pruning with 100ms timeout
ami-node --timeout 100 ...

# Both mechanisms active
ami-node --eb-depth 5 --timeout 50 ...

# Only depth-based (default - timeout disabled)
ami-node --eb-depth 1 ...
```

**Use Cases**:

**Timeout-based pruning is designed for LOW RATE systems**:
- Event rate: 1-10 Hz (low)
- Worker count: Many (10-100+)
- Problem: Workers finish processing but system waits indefinitely for stragglers
- Solution: Timeout prunes after N milliseconds of no activity
- Example: `--timeout 100` means "if no worker sends data for 100ms, prune and move on"

**Depth-based pruning is designed for HIGH RATE systems**:
- Event rate: 100+ Hz (high)
- Worker count: Any
- Problem: Memory fills with pending heartbeats faster than they can be processed
- Solution: Depth limit controls maximum queue size
- Example: `--eb-depth 1` means "only keep latest heartbeat, prune everything else immediately"

**Why this matters**: At low event rates, depth-based pruning may never trigger (queue never fills), so incomplete heartbeats wait forever. Timeout-based pruning ensures forward progress even when events arrive slowly.

---

## Event Builder Lifecycle

### Complete Heartbeat Path

When all expected contributions arrive:

```
1. Worker 0 sends data for heartbeat 100
   → GraphBuilder.update(eb_key=100, eb_id=0, data=...)
   → self.contribs[100] |= 1 << 0  (mark worker 0)
   → self.pending[100].put(0, data)

2. Workers 1-29 send data
   → GraphBuilder.update(...) for each
   → self.contribs[100] grows: 0b00...001 → 0b11...111

3. Worker 29 completes the heartbeat
   → GraphBuilder.ready(100) returns True
   → GraphBuilder.complete(100, ...) called
   → GraphBuilder._complete() executes graph
   → Results sent to next level

4. Cleanup
   → del self.pending[100]
   → del self.contribs[100]
```

### Incomplete Heartbeat Path (Pruned)

When depth is exceeded before all contributions arrive:

```
1. Workers 0-9 send data for heartbeat 100
   → self.contribs[100] = 0b00...1111111111 (10 bits set)
   → pending[100] has partial data

2. All workers send heartbeat 101
   → len(self.pending) = 2, depth = 1
   → prune(identity=101) triggered

3. Pruning logic
   → eb_key = 100 is oldest
   → GraphBuilder.complete(100, drop=False)
   → Graph executes with 10/30 workers
   → Partial results sent upstream

4. Cleanup
   → del self.pending[100]
   → del self.contribs[100]
```

---

## Design Insights

### 1. Event Builder is Not Just Synchronization

Unlike typical event builders that only aggregate data, AMI's GraphBuilder also **executes the computation graph** at collector levels. This enables true distributed map-reduce computation but requires careful handling of stateful operations.

### 2. Graph Execution Semantics Matter

GraphBuilder assumes: Running graph N times on N partial contributions = running once on merged data

**True for**: Pure aggregations (sum, max, histogram merge)  
**False for**: Stateful transformations (RollingBuffer, Accumulator)

This assumption holds for most AMI graph operations, enabling efficient distributed computation.

### 3. Bitmask Efficiency

Using a single integer to track 30 contributors is elegant:
- O(1) check if all contributors arrived
- 4-8 bytes per heartbeat vs 30+ bytes for array
- Fast bitwise operations (OR, comparison)

### 4. Depth is a Critical Tuning Parameter

- **depth=1**: Aggressive, low memory, high pruning frequency
  - Good for: Low-latency systems, high event rates
  - Risk: Frequent incomplete data with async workers
  
- **depth=10**: Moderate, balanced
  - Good for: Most production systems
  
- **depth=100**: Conservative, high memory, rare pruning
  - Good for: Systems with highly variable worker latency

### 5. Depth vs Timeout: Choosing the Right Pruning Strategy

**For HIGH event rate systems (100+ Hz)**:
- Use **depth-based pruning only** (default)
- Set `--eb-depth 1` for lowest latency
- New heartbeats arrive frequently, naturally triggering pruning
- Timeout not needed (system never idle)

**For LOW event rate systems (1-10 Hz)**:
- Use **timeout-based pruning** (enable with `--timeout`)
- Set `--timeout 50-100` milliseconds
- Depth-based pruning may never trigger (queue doesn't fill)
- Timeout ensures incomplete heartbeats don't wait forever

**Hybrid approach** (both enabled):
- Useful when event rate varies significantly
- Depth controls memory usage during high-rate bursts
- Timeout ensures progress during low-rate periods
- Example: `--eb-depth 10 --timeout 100`

**Latency considerations**:
- Lower depth = lower latency (data sent sooner)
- Higher depth = better completeness (wait for more workers)
- Timeout adds fixed latency overhead (wait time when idle)
- For lowest latency: `--eb-depth 1` with no timeout (default)

---

## Empirical Observations: Depth and GUI Update Rate

Users may observe that GUI update rates decrease significantly when `depth > 1` is used with many distributed workers. This section presents empirical observations from testing at depth=1, 2, and 4 with 30 distributed workers, which help explain how distributed aggregation interacts with depth-based pruning.

**Note**: These observations are from preliminary testing and would benefit from additional validation to confirm the pattern across different configurations and workloads.

### Test Configuration

The following tests were conducted to measure the impact of depth on GUI update frequency:

```
Test Setup:
- Workers: 30 (distributed across local + global collectors)
- Event Rate: ~100 Hz (random source)
- Test Duration: ~110-125 seconds per depth
- GUI polling rate: Every 100ms
```

### Results

| Depth | Heartbeats Processed | Heartbeats Sent | Completion Rate | Update Interval | Visual Appearance |
|-------|---------------------|-----------------|-----------------|-----------------|-------------------|
| 1     | ~57,303             | ~725            | ~1.3%           | ~100ms          | Smooth            |
| 2     | 2,282               | 36              | 1.58%           | ~3.5s           | Sporadic          |
| 4     | 1,102               | 20              | 1.81%           | ~5.5s           | Very sporadic     |

*Preliminary observations from single test run.*

**Key Observations**:

The data shows that completion rate (the percentage of heartbeats that produce complete results sent upstream) remains relatively low (~1.5-1.8%) across all tested depths. However, the update interval—how frequently the GUI receives new data—increases significantly with depth: from ~100ms at depth=1 to ~3.5s at depth=2 and ~5.5s at depth=4. With 30 asynchronous workers processing events at ~100 Hz, heartbeats accumulate in the event builder faster than full aggregations can complete.

This occurs because the local collector waits for contributions from all 30 workers before executing the computation graph and sending results upstream. In practice, most pruning events occur when only a subset of workers have contributed their results. These incomplete heartbeats don't produce graph results that get sent to the next level. At higher depths, the system waits longer for more complete data, but with many asynchronous workers operating independently, fully complete data rarely arrives within the pruning window.

The user-visible impact is substantial. At depth=1, the GUI receives new data approximately every 100ms, creating smooth, real-time updates. At depth=2, new data arrives only every ~3.5 seconds, with the Manager serving cached data for the intervening GUI requests. At depth=4, the situation worsens further, with new data every ~5.5 seconds and most GUI requests returning stale cached values. This creates a "sporadic" or "frozen" visual appearance where the display seems to pause and then jump to new values.

### Atomic Batch Fetching in AsyncFetcher

During the depth investigation, the AsyncFetcher component (used by multi-terminal display widgets like scatter plots) was modified to use atomic batch fetching. Previously, features were requested sequentially; now all features for a widget are requested in a single REQ/REP exchange with the Manager. This ensures that all features (such as X and Y coordinates for a scatter plot) are fetched from the same Manager state, corresponding to the same heartbeat. Testing confirmed this mechanism works correctly at all tested depths, with no data inconsistencies observed. The implementation can be found in `ami/flowchart/library/DisplayWidgets.py:116-183` (AsyncFetcher.run method) and `ami/manager.py:685-728` (view_request method).

---

## Code Locations

**Core Classes**:
- ContributionBuilder: `ami/comm.py:563-612`
- GraphBuilder: `ami/comm.py:614-833`
- Heartbeat: `ami/data.py:80-118`

**Usage**:
- Depth-based pruning trigger: `ami/collector.py:183`
- Timeout-based pruning: `ami/collector.py:120-125, ami/comm.py:1287-1305`
- EventBuilder wrapper: `ami/comm.py` (search for `EventBuilder`)

**Related**:
- Store: `ami/comm.py:461-560` (manages namespaced feature data)
- RollingBuffer: `ami/graph_nodes.py:383-429` (stateful transformation example)

---

## Related Documentation

- [AMI Architecture Guide](../AGENTS.md) - Overall system architecture
- Worker documentation: `ami/worker.py` - Data source and graph execution
- Collector documentation: `ami/collector.py` - Event building in production use
