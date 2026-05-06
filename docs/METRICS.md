# AMI Prometheus Metrics

## Overview

AMI exports Prometheus metrics from workers for monitoring system health and performance. Metrics are updated at heartbeat rate (~10 Hz) rather than per-event to minimize overhead at high data rates.

## Worker Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ami_event_count` | Counter | hutch, type, process | Counts events by type |
| `ami_event_time_secs` | Gauge | hutch, type, process | Time measurements in seconds |
| `ami_event_size_bytes` | Gauge | hutch, process | Size of last heartbeat payload |
| `ami_event_latency_secs` | Gauge | hutch, sender, process | Data latency from source |
| `ami_heartbeat_duration_seconds` | Histogram | hutch, process | Full heartbeat interval (wall clock) |

### Event Count Types

| Type | Description |
|------|-------------|
| `Heartbeat` | Heartbeat messages processed |
| `Datagram` | Data events processed (incremented by batch count per heartbeat) |
| `Partial` | Events with missing/None data fields |
| `Transition` | State transition messages (Configure, Unconfigure, etc.) |
| `Other` | Unclassified messages |

### Event Time Types

| Type | Description |
|------|-------------|
| `Heartbeat` | Total non-idle processing time (datagrams + heartbeat handling) |
| `Idle` | Cumulative idle time waiting for data within the heartbeat interval |
| `Datagram` | Average graph execution time per datagram |

### Heartbeat Duration Histogram

The `ami_heartbeat_duration_seconds` histogram measures the full wall clock time between heartbeats (the complete heartbeat interval). This represents the inverse of the actual heartbeat rate. At 10 Hz, values should be ~0.1s.

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
2. **Idle Fraction**: `ami_event_time_secs{type="Idle"} / ami_heartbeat_duration_seconds` — Fraction of time idle
3. **Heartbeat Interval**: `histogram_quantile(0.95, rate(ami_heartbeat_duration_seconds_bucket[1m]))` — p95 heartbeat interval
4. **Input Latency**: `ami_event_latency_secs` — Time between event creation and processing
5. **Heartbeat Rate**: `rate(ami_event_count{type="Heartbeat"}[1m])` — Heartbeats per second (should be ~10)

### Exemplars

The heartbeat duration histogram supports exemplars linking to distributed traces. When tracing is enabled, each histogram observation includes a `TraceID` exemplar for correlation in Grafana.

To use exemplars in Grafana:
1. Add Tempo as a data source
2. In Prometheus queries, enable "Exemplars" toggle
3. Click exemplar dots to jump directly to the corresponding trace

### Dashboard

An example Grafana dashboard is provided at `examples/grafana.json`. Import it into your Grafana instance and configure the Prometheus and Tempo data sources.

## Performance Notes

All metric updates are batched to heartbeat rate (~10 Hz). This means:
- At 100K events/heartbeat, we make ~10 metric calls/second instead of ~1M
- Gauges show the last value or average for the heartbeat interval
- Counters are incremented by the batch total

This design ensures Prometheus instrumentation adds negligible overhead even at maximum data rates.
