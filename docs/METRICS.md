# AMI Prometheus Metrics

## Overview

AMI exports Prometheus metrics from workers, collectors, and the manager for monitoring system health and performance. Metrics are updated at heartbeat rate (configurable via `-b`, default 1 Hz) rather than per-event to minimize overhead at high data rates.

## Exported Metrics

| Metric | Type | Labels | Components | Description |
|--------|------|--------|------------|-------------|
| `ami_event_count` | Counter | hutch, type, process | Workers, Collectors | Counts events by type |
| `ami_event_time_secs` | Gauge | hutch, type, process | Workers, Collectors | Time measurements in seconds |
| `ami_event_size_bytes` | Gauge | hutch, process | Workers, Collectors | Size of last heartbeat payload |
| `ami_event_latency_secs` | Gauge | hutch, sender, process | Workers, Collectors | Data latency from source/sender |
| `ami_heartbeat_duration_seconds` | Histogram | hutch, process | Workers, Collectors | Full heartbeat interval (wall clock) |

### Event Count Types

| Type | Description |
|------|-------------|
| `Heartbeat` | Heartbeat messages processed |
| `Datagram` | Data events processed (incremented by batch count per heartbeat) |
| `Partial` | Events with missing/None data fields |
| `Transition` | State transition messages (Configure, Unconfigure, etc.) |
| `Other` | Unclassified messages |

### Event Time Types

| Type | Description | Workers | Collectors |
|------|-------------|---------|------------|
| `Heartbeat` | Total heartbeat interval wall clock time — the sum of Idle, Datagram, Send, and Overhead phases. At 1 Hz this should be approximately 1 second. | ✓ | ✓ |
| `Idle` | Time spent waiting for input (source data for workers, contributions for collectors) | ✓ | ✓ |
| `Datagram` | Total graph execution time across all events in the heartbeat interval | ✓ | ✓ |
| `Send` | Time spent sending results downstream | ✓ | ✓ |
| `Overhead` | Heartbeat interval time not accounted for by Idle, Datagram, or Send — Python loop overhead, metric publishing, message deserialization, tracing. | ✓ | ✓ |

### Heartbeat Phase Percentages

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ami_heartbeat_phase_pct` | Gauge | hutch, type, process | Percentage of heartbeat interval spent in each phase (sums to 100%) |

| Type | Description |
|------|-------------|
| `Idle` | Waiting for input (source data for workers, contributions for collectors) |
| `Datagram` | Executing graph computations |
| `Send` | Sending results downstream |
| `Overhead` | Remainder (ZMQ polling, metrics, GC) |

### Heartbeat Duration Histogram

The `ami_heartbeat_duration_seconds` histogram measures the full wall clock time between heartbeats (the complete heartbeat interval). This represents the inverse of the actual heartbeat rate. At the default 1 Hz, values should be ~1s.

Buckets: 1ms, 5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s

The histogram supports exemplars linking to trace IDs when tracing is enabled.

## Labels

- **hutch**: The experimental hutch identifier (e.g., "rix", "tmo", "cxi")
- **type**: Sub-category for the metric (see tables above)
- **process**: Worker process name identifier
- **sender**: Source identifier for latency measurements

## Grafana Integration

### Recommended Panels

1. **Event Rate**: `rate(ami_event_count{type="Datagram"}[1m])` — Events processed per second
2. **Idle Time**: `ami_event_time_secs{type="Idle"}` — Time waiting for input (workers: source data, collectors: contributions)
3. **Graph Execution Time**: `ami_event_time_secs{type="Datagram"}` — Total graph execution time across all events in the heartbeat. Directly comparable to the Datagram% in `ami_heartbeat_phase_pct`.
4. **Send Time**: `ami_event_time_secs{type="Send"}` — Time sending results downstream (indicates backpressure)
5. **Heartbeat Interval**: `histogram_quantile(0.95, rate(ami_heartbeat_duration_seconds_bucket[1m]))` — p95 heartbeat interval
6. **Input Latency**: `ami_event_latency_secs` — Time between event creation and processing
7. **Heartbeat Rate**: `rate(ami_event_count{type="Heartbeat"}[1m])` — Heartbeats per second (should match configured rate, default ~1)

### Exemplars

The heartbeat duration histogram supports exemplars linking to distributed traces. When tracing is enabled, each histogram observation includes a `TraceID` exemplar for correlation in Grafana.

To use exemplars in Grafana:
1. Add Tempo as a data source
2. In Prometheus queries, enable "Exemplars" toggle
3. Click exemplar dots to jump directly to the corresponding trace

### Dashboard

An example Grafana dashboard is provided at `examples/grafana.json`. Import it into your Grafana instance and configure the Prometheus and Tempo data sources.

## Performance Notes

All metric updates are batched to heartbeat rate (once per heartbeat interval, regardless of event count). This means:
- At 100K events/heartbeat, we make one set of metric calls per heartbeat instead of per-event
- Gauges show the last value or cumulative total for the heartbeat interval
- Counters are incremented by the batch total

This design ensures Prometheus instrumentation adds negligible overhead even at maximum data rates.
