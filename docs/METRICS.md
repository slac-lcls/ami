# AMI Prometheus Metrics

## Overview

AMI exports Prometheus metrics from workers, collectors, and the manager for monitoring system health and performance. Metrics are updated at heartbeat rate (configurable via `-b`, default 1 Hz) rather than per-event to minimize overhead at high data rates.

## Exported Metrics

| Metric | Type | Labels | Components | Description |
|--------|------|--------|------------|-------------|
| `ami_event_count` | Counter | hutch, type, process | Workers, Collectors | Counts events by type. Exposed as `ami_event_count_total`. |
| `ami_event_time_seconds` | Counter | hutch, type, process | Workers, Collectors, Manager | Cumulative time in each phase (seconds). Exposed as `ami_event_time_seconds_total`. Use `rate()` to get per-second values. |
| `ami_event_size_bytes` | Counter | hutch, process | Workers, Collectors, Manager | Cumulative bytes processed. Exposed as `ami_event_size_bytes_total`. Use `rate()` to get throughput. |
| `ami_event_latency_seconds` | Histogram | hutch, sender, process | Workers, Collectors, Manager | Data latency from source/sender. Use `rate(_sum)/rate(_count)` for average latency. |
| `ami_heartbeat_duration_seconds` | Histogram | hutch, process | Workers, Collectors | Full heartbeat interval (wall clock). Supports exemplars for Tempo trace correlation. |

### Event Count Types

| Type | Description |
|------|-------------|
| `Heartbeat` | Heartbeat messages processed |
| `Datagram` | Data events processed (incremented by batch count per heartbeat) |
| `Partial` | Events with missing/None data fields |
| `Transition` | State transition messages (Configure, Unconfigure, etc.) |
| `Other` | Unclassified messages |

### Event Time Types

| Type | Description | Workers | Collectors | Manager |
|------|-------------|---------|------------|---------|
| `Heartbeat` | Total heartbeat interval wall clock time — the sum of Idle, Datagram, Send, and Overhead phases. At 1 Hz this should be approximately 1 second. | ✓ | ✓ | ✓ |
| `Idle` | Time spent waiting for input (source data for workers, contributions for collectors) | ✓ | ✓ | ✓ |
| `Datagram` | Total graph execution time across all events in the heartbeat interval | ✓ | ✓ | |
| `Send` | Time spent sending results downstream | ✓ | ✓ | |
| `Overhead` | Heartbeat interval time not accounted for by Idle, Datagram, or Send — Python loop overhead, metric publishing, message deserialization, tracing. | ✓ | ✓ | |

### Heartbeat Duration Histogram

The `ami_heartbeat_duration_seconds` histogram measures the full wall clock time between heartbeats (the complete heartbeat interval). This represents the inverse of the actual heartbeat rate. At the default 1 Hz, values should be ~1s.

Histogram buckets are hardcoded: `[0.05, 0.1, 0.15, 0.2, 0.25, 0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0, 5.0]` seconds.

The histogram supports exemplars linking to trace IDs when tracing is enabled.

The `ami_event_latency_seconds` histogram uses the same bucket set.

## Labels

- **hutch**: The experimental hutch identifier (e.g., "rix", "tmo", "cxi")
- **type**: Sub-category for the metric (see tables above)
- **process**: Worker process name identifier
- **sender**: Source identifier for latency measurements

## Grafana Integration

### Recommended PromQL Queries

1. **Event Rate**: `rate(ami_event_count_total{type="Datagram"}[30s])` — Events processed per second
2. **Idle Time**: `rate(ami_event_time_seconds_total{type="Idle"}[30s])` — Seconds of idle time accumulated per second
3. **Graph Execution Time**: `rate(ami_event_time_seconds_total{type="Datagram"}[30s])` — Total graph execution time per second
4. **Send Time**: `rate(ami_event_time_seconds_total{type="Send"}[30s])` — Time sending results downstream per second
5. **Heartbeat Interval (p95)**: `histogram_quantile(0.95, rate(ami_heartbeat_duration_seconds_bucket[30s]))` — p95 heartbeat interval
6. **Input Latency (average)**: `rate(ami_event_latency_seconds_sum[30s]) / rate(ami_event_latency_seconds_count[30s])` — Average data latency from source/sender
7. **Heartbeat Rate**: `rate(ami_event_count_total{type="Heartbeat"}[30s])` — Heartbeats per second (should match configured rate, default ~1)
8. **Phase Percentage**: `rate(ami_event_time_seconds_total{type="Idle"}[30s]) / ignoring(type) rate(ami_event_time_seconds_total{type="Heartbeat"}[30s]) * 100` — Percentage of heartbeat interval in Idle phase (replace `Idle` with `Datagram`, `Send`, or `Overhead` for other phases)
9. **Throughput**: `rate(ami_event_size_bytes_total[30s])` — Bytes processed per second

### Why Counters Instead of Gauges

The timing and size metrics are Counters (not Gauges) so that `rate()` gives accurate per-second values regardless of the Prometheus scrape interval. With Gauges, a slow scrape interval could miss multiple heartbeat updates, losing data. With Counters, all increments are accumulated and `rate()` accurately reports the rate over any window ≥ one scrape interval.

Phase percentages are derived in PromQL by dividing the phase Counter rate by the Heartbeat Counter rate, then multiplying by 100. This gives the fraction of each heartbeat interval spent in each phase, equivalent to what a Gauge would report but computed accurately from monotonic counters.

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
- Counters are incremented by the batch total each heartbeat
- `rate()` over a window of at least one heartbeat period gives accurate per-second values

This design ensures Prometheus instrumentation adds negligible overhead even at maximum data rates.
