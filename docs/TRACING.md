# AMI Distributed Tracing

## Overview

AMI uses OpenTelemetry distributed tracing to provide end-to-end visibility into heartbeat processing across the distributed system. Traces connect spans from workers, collectors, and the manager using deterministic trace IDs computed via SHA-256 hashing of the heartbeat identity. This means all processes (workers, collectors, manager) independently compute the same trace ID for a given heartbeat, allowing their spans to be grouped together in the same trace without any coordination.

### Enabling Tracing

1. **Install tracing dependencies:**
   ```bash
   pip install ami[tracing]
   ```

2. **Enable tracing with OTLP endpoint:**
   ```bash
   ami-local --tracing-endpoint localhost:4317 random://examples/worker.json
   ```

   Or use environment variable:
   ```bash
   export AMI_TRACING_ENDPOINT=localhost:4317
   ami-local random://examples/worker.json
   ```

3. **Console output for debugging:**
   ```bash
   ami-local --tracing-endpoint console random://examples/worker.json
   ```

### Deterministic Trace IDs

All processes compute the same trace ID for a given heartbeat using:
```python
hash_input = f"ami-heartbeat-{session_id}-{heartbeat_identity}".encode()
digest = hashlib.sha256(hash_input).digest()
trace_id = int.from_bytes(digest[:16], byteorder="big")
```

This allows spans from different processes to share the same trace without requiring coordination or context propagation between processes.

### Session ID

**Why Session IDs are Needed:**

When AMI restarts, the heartbeat counter resets to the same sequence (0, 1, 2, ...). Without session IDs, restarted sessions would produce identical trace IDs for the same heartbeat numbers, causing Tempo/Jaeger to incorrectly merge spans from different AMI sessions into the same trace. The session ID ensures each AMI deployment produces unique trace IDs.

**How It Works:**

The session ID is included in the SHA-256 hash used to compute deterministic trace IDs. The `AMI_TRACING_SESSION_ID` environment variable is read by `setup_tracing()` and incorporated into the hash:

```python
hash_input = f"ami-heartbeat-{session_id}-{heartbeat_identity}".encode()
```

**For `ami-local` (Development/Testing):**

Session IDs are auto-generated. When you enable tracing with `--tracing-endpoint`, a UUID session ID is automatically created:

```bash
ami-local --tracing-endpoint localhost:4317 random://examples/worker.json
# Session ID is auto-generated internally
```

No action needed — session IDs are handled transparently.

**For Production (`ami-node`, `ami-global`, `ami-manager`):**

All processes in a deployment must share the same session ID. Generate one session ID and pass it to all processes:

```bash
# Generate a shared session ID (once per deployment)
export AMI_TRACING_SESSION_ID=$(uuidgen)
export AMI_TRACING_ENDPOINT=tempo.example.com:4317

# Start all processes with the same session ID
ami-manager --tracing-endpoint $AMI_TRACING_ENDPOINT --tracing-session-id $AMI_TRACING_SESSION_ID &
ami-node    --tracing-endpoint $AMI_TRACING_ENDPOINT --tracing-session-id $AMI_TRACING_SESSION_ID worker psana://... &
ami-global  --tracing-endpoint $AMI_TRACING_ENDPOINT --tracing-session-id $AMI_TRACING_SESSION_ID &
```

**Alternative: Using Environment Variables Only:**

If the environment variables are already set (e.g., by SLURM or deployment scripts), CLI args are optional:

```bash
export AMI_TRACING_ENDPOINT=tempo.example.com:4317
export AMI_TRACING_SESSION_ID=$(uuidgen)

# CLI args are optional when env vars are set
ami-manager &
ami-node worker psana://... &
ami-global &
```

**Note:** CLI arguments override environment variables if both are provided.

## Span Reference

| Span Name | Type | Service | Description | Key Attributes |
|-----------|------|---------|-------------|----------------|
| `worker.heartbeat` | root | worker | Full heartbeat interval from start of event processing to heartbeat completion | `heartbeat`, `worker.id`, `worker.num_datagrams`, `worker.data_size_bytes`, `worker.source_idle_secs`, `worker.pct_idle`, `worker.pct_graph_exec`, `worker.pct_collect` |
| `worker.graph_exec` | child | worker | Consolidated graph execution time across all datagrams (real wall clock: first graph exec start to last graph exec end) | `worker.graph_exec_secs`, `worker.num_datagrams` |
| `worker.collect` | child | worker | Serialize and send results to collector (real wall clock timestamps) | `worker.send_secs`, `worker.data_size_bytes` |
| `{color}.heartbeat` | root | collector | Completed heartbeat at collector (color = localCollector or globalCollector) | `heartbeat`, `collector.pruned`, `collector.num_contribs`, `collector.data_size_bytes`, `collector.pct_wait`, `collector.pct_graph_exec`, `collector.pct_send`, `collector.pct_idle` |
| `{color}.prune` | root | collector | Pruned incomplete heartbeat due to timeout or missing contributions (marked as ERROR, includes child spans) | `heartbeat`, `collector.pruned`, `collector.contrib_ratio`, `collector.num_present`, `collector.num_contribs`, `collector.prune_age`, `collector.missing_workers`, `collector.data_size_bytes`, `collector.pct_wait`, `collector.pct_graph_exec`, `collector.pct_send`, `collector.pct_idle` |
| `collector.wait` | child | collector | Waiting for all contributions from downstream workers/collectors (real wall clock timestamps, present in both normal and prune spans) | `collector.wait_secs` |
| `collector.graph_exec` | child | collector | Executing reduction graph on aggregated data (real wall clock timestamps, present in both normal and prune spans) | `collector.graph_exec_secs` |
| `collector.send` | child | collector | Sending aggregated results upstream to next collector or manager (real wall clock timestamps, present in both normal and prune spans) | `collector.data_size_bytes` |
| `manager.heartbeat` | root | manager | Manager processed heartbeat and broadcast notification to clients | `heartbeat`, `manager.graph` |

## Trace Structure

A typical trace for a single heartbeat shows spans from all processes involved:

```
worker.heartbeat ─────────────────────────────────────────────
  [visual gap = idle time]
  ├─ worker.graph_exec ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  └─ worker.collect                                 ━━━

localCollector.heartbeat ─────────────────────────────────────
  ├─ collector.wait ━━━━━━━━━━━━━━━
  ├─ collector.graph_exec          ━━━━━━━━━
  └─ collector.send                         ━━

globalCollector.heartbeat ────────────────────────────────────
  ├─ collector.wait ━━━━━━━━━━━━━━━━━
  ├─ collector.graph_exec            ━━━━━
  └─ collector.send                       ━━

manager.heartbeat ━━
```

**Notes:**
- All spans in a trace share the same deterministic trace ID based on the heartbeat identity
- Each process creates root spans (not child spans of remote parents) but they appear grouped in the trace
- **Child spans use real wall clock timestamps** to show actual timing and cross-process causal flow
  - Visual gaps before the first child span indicate idle/wait time
  - For workers: gap before `worker.graph_exec` shows idle time waiting for data from the source
  - For collectors: gap before `collector.wait` shows unaccounted overhead time
  - Overlapping spans across processes show parallelism; sequential spans show dependencies
- `worker.pct_idle` represents cumulative idle time across the heartbeat interval (including micro-gaps between datagrams), not just the initial gap visible in the waterfall
- `collector.pct_idle` represents unaccounted time (e.g., ZMQ overhead, Python overhead, time gaps between activities)
- Multiple worker spans may exist in the same trace if multiple workers process events for the same heartbeat

### Percentage Attributes

All percentage attributes use the **full parent span duration** as the denominator:

**Worker percentages** (denominator = full heartbeat interval):
- `worker.pct_idle` — percentage of time spent idle waiting for data (total idle across the interval, including micro-gaps between datagrams)
- `worker.pct_graph_exec` — percentage of time executing graph computations
- `worker.pct_collect` — percentage of time serializing and sending results

**Collector percentages** (denominator = total processing time from arrival to completion):
- `collector.pct_idle` — percentage of unaccounted/overhead time
- `collector.pct_wait` — percentage of time waiting for contributions
- `collector.pct_graph_exec` — percentage of time executing graph computations
- `collector.pct_send` — percentage of time sending results upstream

These percentages should sum to approximately 100% (minor variations due to rounding or timing precision).

## Reading a Trace

Traces provide end-to-end visibility to diagnose performance issues. Here are the four key questions to answer:

### 1. Are workers waiting for events?

**Look for:**
- Visual gap before `worker.graph_exec` child span in the waterfall
- `worker.pct_idle` attribute (hover over `worker.heartbeat` span)
- High `worker.pct_idle` (>50%) indicates source starvation

**Example diagnosis:**
- Gap visible: worker is idle at the START of the heartbeat interval waiting for first event
- `worker.pct_idle = 73.2`: worker spent 73% of the interval waiting for data
- **Action:** Check data source rate, network bandwidth, or upstream bottlenecks

**Note:** `worker.pct_idle` includes ALL idle time across the heartbeat interval (including micro-gaps between individual datagrams), not just the visible gap before the first graph execution in the waterfall.

### 2. Is a collector pruning because one worker is slow?

**Look for:**
- Red ERROR span named `{color}.prune` (e.g., `localCollector.prune`)
- `collector.missing_workers` attribute showing which worker(s) didn't contribute in time
- Compare `worker.collect` end times across workers — the late one will finish after the prune event

**Example diagnosis:**
- `localCollector.prune` span with `collector.missing_workers = [2]`
- Worker 2's `worker.collect` span ends AFTER the prune span
- **Action:** Investigate worker 2 — check `worker.pct_graph_exec` (slow graph?) or `worker.pct_idle` (starved?)

**Investigating prune execution breakdown:**
- **Expand the prune span** to see child spans (collector.wait, collector.graph_exec, collector.send)
- This reveals whether graph execution on partial data or the send phase contributed to latency
- Check percentage attributes (`pct_wait`, `pct_graph_exec`, `pct_send`, `pct_idle`) to see where time was spent during the prune
- Even though data was incomplete, the collector still executed the graph on whatever contributions it received — child spans show this breakdown

### Understanding `collector.wait` Span Semantics

The `collector.wait` span has different meanings depending on whether the heartbeat completed normally or was pruned:

**Normal completion:**
- **Start:** First worker contribution arrives at the collector
- **End:** ALL workers have contributed (event builder bitmask is complete)
- **Meaning:** Time spent waiting for stragglers (slowest workers to send their results)
- **Diagnosis:** A long `collector.wait` means one or more workers are slow — cross-reference by looking at which `worker.collect` span ends last

**Prune (ERROR span):**
- **Start:** First worker contribution arrives at the collector
- **End:** Prune decision is triggered (newer heartbeat completes and depth limit is exceeded)
- **Meaning:** How long the system held onto incomplete data before giving up
- **Diagnosis:** Combined with `collector.missing_workers` attribute, shows which workers never contributed and how long the collector waited before pruning
- **Additional context:** Check `collector.prune_age` to see how many heartbeats behind this one was when it got pruned

### 3. Is the graph taking long?

**Look for:**
- Duration of `worker.graph_exec` and `collector.graph_exec` spans
- Compare across workers and collectors to find hot spots
- `worker.pct_graph_exec` and `collector.pct_graph_exec` percentages

**Example diagnosis:**
- `worker.graph_exec` spans are 200ms each (most of the heartbeat interval)
- `worker.pct_graph_exec = 85%` confirms graph execution is the bottleneck
- **Action:** Profile graph operations, optimize algorithms, reduce computation complexity

### 4. Are we blocked on sends?

**Look for:**
- Duration of `worker.collect` and `collector.send` spans
- `worker.pct_collect` and `collector.pct_send` percentages
- High percentage indicates network or serialization bottleneck

**Example diagnosis:**
- `worker.collect` spans are 150ms each
- `worker.pct_collect = 60%` indicates majority of time spent sending
- **Action:** Check network bandwidth, reduce data size, optimize serialization, or increase ZMQ high water mark (HWM)

### Waterfall Reading Tips

- **Horizontal alignment:** Spans at the same horizontal position happened at the same wall clock time
- **Causal flow:** Trace from top to bottom (worker → localCollector → globalCollector → manager)
- **Gaps indicate waiting:** Visual gap between child spans shows idle/wait time
- **Overlapping spans show parallelism:** Multiple workers processing in parallel
- **Sequential spans show dependencies:** Collector can't start graph_exec until wait completes

## Prometheus Exemplars

Trace IDs are attached as exemplars to the following Prometheus metrics:
- `heartbeat_duration` (histogram) — time to process a heartbeat
- `heartbeat_latency` (histogram) — age of heartbeat when completed

This enables Grafana to provide direct links from metric spikes to corresponding traces, making it easy to investigate performance issues.

Example Prometheus scrape output:
```
heartbeat_duration_bucket{le="0.5"} 42 # {TraceID="a1b2c3d4e5f6..."} 0.234
```

## Setup Instructions

### Local Development with Jaeger

Run Jaeger all-in-one for local testing:
```bash
docker run -d --name jaeger \
  -p 4317:4317 \
  -p 16686:16686 \
  jaegertracing/all-in-one:latest
```

Then access the Jaeger UI at http://localhost:16686

Enable tracing in AMI:
```bash
ami-local --tracing-endpoint localhost:4317 random://examples/worker.json
```

### Production with Grafana Tempo

For production deployments, configure Grafana Tempo as the OTLP receiver:

1. **Tempo configuration** (`tempo.yaml`):
   ```yaml
   server:
     http_listen_port: 3200

   distributor:
     receivers:
       otlp:
         protocols:
           grpc:
             endpoint: 0.0.0.0:4317

   storage:
     trace:
       backend: local
       local:
         path: /tmp/tempo/traces
   ```

2. **Run Tempo:**
   ```bash
   docker run -d --name tempo \
     -p 3200:3200 \
     -p 4317:4317 \
     -v $(pwd)/tempo.yaml:/etc/tempo.yaml \
     grafana/tempo:latest \
     -config.file=/etc/tempo.yaml
   ```

3. **Configure Grafana data source:**
   - Add Tempo data source pointing to `http://localhost:3200`
   - Enable trace-to-metrics correlation with Prometheus

4. **Enable tracing in AMI:**
   ```bash
   ami-manager --tracing-endpoint tempo-host:4317
   ami-collector --tracing-endpoint tempo-host:4317
   ami-worker --tracing-endpoint tempo-host:4317
   ```

### Environment Variable Configuration

For production deployments, use the environment variable to avoid passing flags to every command:
```bash
export AMI_TRACING_ENDPOINT=tempo-host:4317
```

All AMI processes will automatically pick up this configuration.
