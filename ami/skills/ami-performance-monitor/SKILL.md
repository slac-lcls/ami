---
name: ami-performance-monitor
description: Diagnose AMI performance using Grafana MCP tools (Prometheus metrics + Tempo traces). Load when investigating latency, pruning, worker starvation, GUI update lag, or asked to check system health.
---

# AMI Performance Monitor

You are diagnosing performance of AMI (LCLS-II online analysis system) using Grafana
MCP tools. You query Prometheus for metrics and Tempo for distributed traces. You do
NOT manipulate graphs — load the `ami-graph-builder` skill for that.

## Discovery (always start here)

1. `grafana_list_datasources` — find Prometheus and Tempo datasource UIDs
2. `grafana_list_prometheus_metric_names(datasourceUid=..., regex="ami_")` — confirm AMI metrics are flowing
3. `grafana_search_dashboards(query="AMI")` — find pre-built dashboard (importable from `examples/grafana.json`)

---

## Diagnosis Hierarchy

Work top-to-bottom. Start with phase breakdown — it is the primary diagnostic signal.

### 1. Phase Breakdown — "Where is the time going?" (PRIMARY)

`ami_heartbeat_phase_pct` shows what fraction of each heartbeat interval is spent in
each phase. Values always sum to 100% and are independent of heartbeat rate.

```
grafana_query_prometheus(
    datasourceUid=<prometheus_uid>,
    expr='ami_heartbeat_phase_pct',
    queryType="instant",
    endTime="now"
)
```

| Phase | Meaning | Problem threshold |
|-------|---------|-------------------|
| `Idle` | Waiting for input (source data for workers; contributions for collectors) | >70% = starved |
| `Datagram` | Executing graph computations | >70% = graph bottleneck |
| `Send` | Sending results downstream | >20% = backpressure |
| `Overhead` | ZMQ polling, metrics, GC | >20% = system overhead |

Filter by component to isolate where the problem is:
```
# Workers only
expr='ami_heartbeat_phase_pct{process=~"worker.*"}'

# Collectors only
expr='ami_heartbeat_phase_pct{process=~".*[Cc]ollector.*"}'
```

### 2. Heartbeat Health — "Is the heartbeat rate healthy?"

`ami_heartbeat_duration_seconds` measures the wall clock time for each full heartbeat
interval. A growing p95 means the system is slowing down; a value consistently above
the configured heartbeat period means it's falling behind.

```
grafana_query_prometheus_histogram(
    datasourceUid=<prometheus_uid>,
    metric="ami_heartbeat_duration_seconds",
    percentile=95
)
```

Also check the heartbeat rate is matching configuration (~1 Hz default):
```
grafana_query_prometheus(
    datasourceUid=<prometheus_uid>,
    expr='rate(ami_event_count{type="Heartbeat"}[1m])',
    queryType="instant",
    endTime="now"
)
```

### 3. Trace Deep Dive — "Pinpoint the exact bottleneck"

Use Tempo when metrics point to a problem but you need to know WHICH worker or heartbeat
is responsible.

```
# Find traces — filter by span name and attributes
grafana_tempo_traceql-search(
    datasourceUid=<tempo_uid>,
    query='{ name="worker.heartbeat" }',
    start=<rfc3339>,
    end=<rfc3339>
)

# Fetch full span waterfall for a specific trace
grafana_tempo_get-trace(
    datasourceUid=<tempo_uid>,
    trace_id="<id>"
)
```

Trace spans flow: `worker.heartbeat` → `localCollector.heartbeat` → `globalCollector.heartbeat` → `manager.heartbeat`

---

## The 4 Key Diagnosis Questions

### A. Are workers starved for data?

Workers are idle when the data source is not providing events fast enough.

**Metric check:**
```
# Step 1: confirm workers are idle
grafana_query_prometheus(
    expr='ami_heartbeat_phase_pct{type="Idle", process=~"worker.*"}',
    queryType="instant", endTime="now"
)

# Step 2 (follow-up): check if data is also arriving stale
grafana_query_prometheus(
    expr='ami_event_latency_secs{process=~"worker.*"}',
    queryType="instant", endTime="now"
)
```
High `Idle%` (>50%) on workers = source starvation.

If `Idle%` is high but `ami_event_latency_secs` is low, data is infrequent (source rate
issue). If both are high, data is both infrequent AND stale (network/upstream issue).

**Trace check:**
```
grafana_tempo_traceql-search(
    query='{ name="worker.heartbeat" && span.worker.pct_idle > 50 }'
)
```
Look at `worker.pct_idle` attribute on the `worker.heartbeat` span. A visible gap before
`worker.graph_exec` in the waterfall confirms idle time at the start of the interval.

**Action:** Check data source rate, network bandwidth, or upstream bottlenecks.

---

### B. Is a collector pruning?

Pruning occurs when not all workers contribute to a heartbeat before the event builder
moves on. Pruned heartbeats appear as ERROR spans named `{color}.prune`.

**Trace check:**
```
# Find prune events
grafana_tempo_traceql-search(
    query='{ name=~".*\\.prune" && status=error }'
)

# Check prune rate
grafana_tempo_traceql-metrics-instant(
    query='{ name=~".*\\.prune" } | rate()'
)
```

Key attributes on prune spans:
- `collector.missing_workers` — which worker(s) didn't contribute in time
- `collector.contrib_ratio` — fraction of expected contributions that arrived
- `collector.prune_age` — how many heartbeats behind this one was when pruned

**Action:** Look at the identified slow workers using question A. If pruning is
widespread, the system may be overloaded.

---

### C. Is the graph too expensive?

High graph execution time means the computation graph is consuming most of the
heartbeat interval budget.

**Metric check:**
```
# Absolute graph execution time
grafana_query_prometheus(
    expr='ami_event_time_secs{type="Datagram"}',
    queryType="instant", endTime="now"
)

# As fraction of heartbeat interval
grafana_query_prometheus(
    expr='ami_heartbeat_phase_pct{type="Datagram"}',
    queryType="instant", endTime="now"
)
```

**Trace check:**
```
grafana_tempo_traceql-search(
    query='{ name="worker.graph_exec" } | duration > 50ms'
)
```
Compare `worker.graph_exec` duration across workers — uneven durations suggest one
worker has more data or a more expensive operation.

**Action:** Simplify graph, remove expensive nodes, optimize PythonEditor code, or
reduce per-event data size feeding into expensive operations.

---

### D. Is send causing backpressure?

High send time indicates the network or downstream is a bottleneck — workers are
serializing and transmitting large payloads.

**Metric check:**
```
# Send as fraction of heartbeat interval
grafana_query_prometheus(
    expr='ami_heartbeat_phase_pct{type="Send"}',
    queryType="instant", endTime="now"
)

# Payload size
grafana_query_prometheus(
    expr='ami_event_size_bytes',
    queryType="instant", endTime="now"
)
```

**Trace check:**
```
grafana_tempo_traceql-search(
    query='{ name="worker.send" } | duration > 50ms'
)
```

**Action:** Reduce data size (downsample, crop, ROI before sending), increase ZMQ HWM,
optimize serialization.

---

### E. Is the GUI display lagging?

**When to check:** user reports plots are slow to update, or pipeline metrics look
healthy but display feels unresponsive.

**Metric check:**
```python
grafana_query_prometheus(
    expr='ami_plot_latency_secs{hutch="$hutch"}',
    queryType="instant", endTime="now"
)
grafana_query_prometheus(
    expr='ami_plot_memory_mb{hutch="$hutch"}',
    queryType="instant", endTime="now"
)
```

**Interpretation:**
- High `ami_plot_latency_secs` with healthy `ami_heartbeat_phase_pct` → bottleneck is
  client-side, not the pipeline
- High `ami_plot_memory_mb` alongside slow plot updates → large arrays being held in
  display nodes

**Action:** Reduce plot complexity, downsample or crop data before display nodes, check
for accumulator nodes with unbounded growth.

---

## Exemplar Correlation (Metric Spike → Trace)

The `ami_heartbeat_duration_seconds` histogram supports Prometheus exemplars with
TraceID. When tracing is enabled, each histogram observation includes a `TraceID`
exemplar for direct correlation in Grafana.

Pattern for investigating a heartbeat duration spike:

1. Find the time window when heartbeat duration spiked:
```
grafana_query_prometheus_histogram(
    datasourceUid=<prometheus_uid>,
    metric="ami_heartbeat_duration_seconds",
    percentile=99,
    startTime="now-15m", endTime="now"
)
```

2. Search for slow traces in that window:
```
grafana_tempo_traceql-search(
    datasourceUid=<tempo_uid>,
    query='{ name="worker.heartbeat" } | duration > 200ms',
    start=<spike_start_rfc3339>,
    end=<spike_end_rfc3339>
)
```

3. Fetch the full waterfall for a slow trace:
```
grafana_tempo_get-trace(
    datasourceUid=<tempo_uid>,
    trace_id="<id from search>"
)
```

The waterfall shows all spans across workers, collectors, and manager for that single
heartbeat — making it clear where time was lost.

---

## Metrics Reference

| Metric | Type | Labels | What it measures |
|--------|------|--------|-----------------|
| `ami_event_count` | Counter | hutch, type, process | Events by type (Heartbeat, Datagram, Partial, Transition) |
| `ami_event_time_secs` | Gauge | hutch, type, process | Time in seconds (Heartbeat, Idle, Datagram, Send) |
| `ami_event_size_bytes` | Gauge | hutch, process | Payload size of last heartbeat |
| `ami_event_latency_secs` | Gauge | hutch, sender, process | Per-hop data latency (source→worker, worker→collector) |
| `ami_heartbeat_duration_seconds` | Histogram | hutch, process | Full heartbeat interval wall clock time |
| `ami_heartbeat_phase_pct` | Gauge | hutch, type, process | Phase % (Idle, Datagram, Send, Overhead — sum to 100%) |
| `ami_plot_latency_secs` | Gauge | hutch, process | Client-side plot update latency |
| `ami_plot_memory_mb` | Gauge | hutch, process | Client-side memory used by display nodes |

**Notes:**
- Heartbeat rate ranges 1–10 Hz depending on configuration
- All metrics are batched at heartbeat rate (~10 updates/sec max) to minimize overhead
- `hutch` label identifies the experimental hutch (e.g., "rix", "tmo", "cxi")
- `process` label identifies the specific worker or collector instance

---

## Trace Span Reference

| Span | Service | Key Attributes | Problem Indicators |
|------|---------|----------------|-------------------|
| `worker.heartbeat` | worker | `pct_idle`, `pct_graph_exec`, `pct_send`, `pct_overhead`, `num_datagrams`, `data_size_bytes` | Any pct >70% |
| `worker.idle` | worker | (duration = total idle time) | Long duration = source starvation |
| `worker.graph_exec` | worker | `graph_exec_secs`, `num_datagrams` | Long = expensive graph |
| `worker.send` | worker | `send_secs`, `data_size_bytes` | Long = backpressure |
| `worker.overhead` | worker | (fills remaining interval) | Long = GC/ZMQ pressure |
| `{color}.heartbeat` | collector | `pct_idle`, `pct_graph_exec`, `pct_send`, `num_contribs`, `data_size_bytes` | High pct values |
| `{color}.prune` | collector | `missing_workers`, `contrib_ratio`, `prune_age`, `num_present`, `num_contribs` | ERROR status = data loss |
| `collector.wait` | collector | `wait_secs` | Long = slow workers upstream |
| `collector.graph_exec` | collector | `graph_exec_secs` | Long = expensive reduction |
| `collector.send` | collector | `data_size_bytes` | Long = downstream backpressure |
| `manager.heartbeat` | manager | `heartbeat`, `manager.graph` | — |

**Worker child spans use sequential stacking** (placed back-to-back using cumulative
durations, not real wall clock). Collector child spans use real wall clock timestamps.

---

## Tuning Recommendations

After diagnosis, tell the user:

| Finding | Recommendation |
|---------|---------------|
| High `Idle%` on workers | Check data source rate, psana configuration, network |
| High `Datagram%` | Simplify graph, remove expensive nodes, optimize PythonEditor |
| High `Send%` | Reduce data size (downsample/crop/ROI), increase ZMQ HWM |
| High `Overhead%` | Check for GC pressure, reduce Python object allocation in graph |
| Frequent collector pruning | Investigate slow workers in `missing_workers`; if systemic, system is overloaded |
| Growing end-to-end latency | Work through phase breakdown to find the bottleneck |
| Uneven worker performance | Compare `pct_graph_exec` across workers; check if one has heavier data |
| High plot latency | Reduce display node complexity, downsample before plotting, check accumulator growth |

---

## Dashboard & Visualization

```
# Find the pre-built AMI dashboard
grafana_search_dashboards(query="AMI")

# Render a panel as an image
grafana_get_panel_image(
    dashboardUid=<uid>,
    panelId=<id>,
    timeRange={"from": "now-15m", "to": "now"}
)

# Generate a shareable link
grafana_generate_deeplink(
    resourceType="dashboard",
    dashboardUid=<uid>,
    timeRange={"from": "now-15m", "to": "now"}
)
```

An example dashboard is provided at `examples/grafana.json` — import it into Grafana
and configure the Prometheus and Tempo data sources to use it.
