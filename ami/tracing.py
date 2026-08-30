"""
Optional distributed tracing for AMI using OpenTelemetry.

Install with: pip install ami[tracing]
Enable with: --tracing-endpoint <host:port> or --tracing-endpoint console
"""

import hashlib
import logging
import random

logger = logging.getLogger(__name__)

# Module-level state
_enabled = False
_tracer = None
_id_generator = None
_session_id = ""
_trace_id_cache: tuple = (None, None)  # (key_str, trace_id_int)
_sample_rate = 10

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
    from opentelemetry.trace import StatusCode

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


class DeterministicTraceIdGenerator:
    """
    Custom OTel IdGenerator that returns a deterministic trace_id
    set by the caller, making spans true root spans while sharing
    a trace_id across processes.
    """

    def __init__(self):
        self._current_trace_id = None

    def set_trace_id(self, trace_id):
        self._current_trace_id = trace_id

    def generate_span_id(self) -> int:
        return random.getrandbits(64)

    def generate_trace_id(self) -> int:
        if self._current_trace_id is not None:
            return self._current_trace_id
        return random.getrandbits(128)


def setup_tracing(service_name, endpoint=None, session_id=None, sample_rate=10):
    """
    Initialize OpenTelemetry tracing for AMI.

    Args:
        service_name: Name of the service (e.g. "ami-worker-0", "ami-manager")
        endpoint: OTLP endpoint (host:port) or "console" for stdout.
        session_id: Unique session identifier for trace correlation.
        sample_rate: Trace every Nth heartbeat (default: 10).
    """
    global _enabled, _tracer, _id_generator, _session_id, _sample_rate

    if not _OTEL_AVAILABLE:
        logger.info("OpenTelemetry not installed. Install with: pip install ami[tracing]")
        return

    if not endpoint:
        return

    _session_id = session_id or ""
    _sample_rate = max(1, int(sample_rate))

    # Initialize TracerProvider with custom IdGenerator and Resource
    _id_generator = DeterministicTraceIdGenerator()
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource, id_generator=_id_generator)

    # Configure exporter and processor based on endpoint
    if endpoint == "console":
        exporter = ConsoleSpanExporter()
        processor = SimpleSpanProcessor(exporter)
    else:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        processor = BatchSpanProcessor(
            exporter,
            max_queue_size=2048,
            schedule_delay_millis=1000,
            max_export_batch_size=512,
        )
    provider.add_span_processor(processor)

    # Set as global provider
    trace.set_tracer_provider(provider)

    # Get tracer for this service
    _tracer = trace.get_tracer(service_name)
    _enabled = True

    logger.info(f"Tracing enabled for {service_name} (endpoint: {endpoint})")


def _compute_trace_id(heartbeat_identity) -> int:
    """Compute deterministic trace ID with single-entry cache to avoid redundant SHA-256."""
    global _trace_id_cache
    key = f"ami-heartbeat-{_session_id}-{heartbeat_identity}"
    if _trace_id_cache[0] == key:
        return _trace_id_cache[1]
    digest = hashlib.sha256(key.encode()).digest()
    trace_id = int.from_bytes(digest[:16], byteorder="big") or 1
    _trace_id_cache = (key, trace_id)
    return trace_id


def should_trace(heartbeat_identity) -> bool:
    """Return True if this heartbeat should be traced."""
    if not _enabled:
        return False
    return int(heartbeat_identity) % _sample_rate == 0


def heartbeat_context(heartbeat_identity):
    """
    Set the deterministic trace ID for the current heartbeat on the IdGenerator.
    Call this before start_span() to ensure the correct trace_id is used.

    Args:
        heartbeat_identity: The heartbeat identity (int or str)

    Returns:
        The computed trace_id (int) or None if tracing is disabled.
    """
    if not _enabled or _id_generator is None:
        return None

    trace_id = _compute_trace_id(heartbeat_identity)
    _id_generator.set_trace_id(trace_id)
    return trace_id


def start_span(name, heartbeat_identity, start_time_ns=None, attributes=None):
    """
    Start a span with a deterministic trace ID for the given heartbeat.

    The span is a true root span (no parent_span_id) but shares the
    deterministic trace_id with all other spans for this heartbeat
    across all processes.

    Args:
        name: Span name (e.g. "worker.heartbeat", "localCollector.prune")
        heartbeat_identity: The heartbeat identity to generate trace ID from
        start_time_ns: Optional start time in nanoseconds (int)
        attributes: Optional dict of span attributes

    Returns:
        Span object if tracing is enabled, None otherwise.
        Caller must call span.end() when done.
    """
    if not _enabled or _tracer is None:
        return None

    if not should_trace(heartbeat_identity):
        return None

    # Set deterministic trace ID on the generator
    heartbeat_context(heartbeat_identity)

    # Merge heartbeat attribute with any caller-provided attributes
    merged_attributes = {"heartbeat": int(heartbeat_identity)}
    if attributes:
        merged_attributes.update(attributes)

    # Start span WITHOUT parent context — makes it a true root span
    # The IdGenerator will supply our deterministic trace_id
    span = _tracer.start_span(
        name,
        start_time=start_time_ns,
        attributes=merged_attributes,
    )

    return span


def start_child_span(parent_span, name, start_time_ns=None, attributes=None):
    """Start a child span under the given parent span.

    Args:
        parent_span: The parent span to create a child of
        name: Span name
        start_time_ns: Optional start time in nanoseconds
        attributes: Optional dict of span attributes

    Returns:
        Span object if tracing is enabled, None otherwise.
        Caller must call span.end() when done.
    """
    if not _enabled or _tracer is None or parent_span is None:
        return None
    parent_ctx = trace.set_span_in_context(parent_span)
    return _tracer.start_span(
        name,
        context=parent_ctx,
        start_time=start_time_ns,
        attributes=attributes,
    )


def create_graph_node_spans(parent_span, node_times, metadata, start_time_ns=None, graph_name=None):
    """Create child spans under parent_span for each graph node in node_times.

    Args:
        parent_span: The parent span to create children under
        node_times: Dict of {node_name: duration_secs} from graph.times()
        metadata: Dict of {node_name: {"parent": ami_name, "type": node_type}} from graph.metadata()
        start_time_ns: Start time in nanoseconds for the first child span
        graph_name: Optional graph name to include as the ``ami.graph`` attribute on each span
    """
    if not _enabled or parent_span is None or not node_times:
        return

    cursor_ns = start_time_ns if start_time_ns is not None else 0
    for node_name, duration in node_times.items():
        if not isinstance(duration, (int, float)):
            continue
        if duration <= 0:
            continue
        node_meta = metadata.get(node_name, {})
        ami_name = node_meta.get("parent", node_name)
        node_type = node_meta.get("type", "Unknown")
        duration_ns = int(duration * 1e9)
        child = start_child_span(
            parent_span,
            ami_name,
            start_time_ns=cursor_ns,
            attributes={
                "ami.node": ami_name,
                "ami.node_type": node_type,
                "ami.duration_secs": float(duration),
                "ami.graph": graph_name or "",
            },
        )
        if child:
            child.end(end_time=cursor_ns + duration_ns)
        cursor_ns += duration_ns


def is_enabled():
    """Returns whether tracing is currently enabled."""
    return _enabled


def mark_span_error(span, message):
    """Mark a span with ERROR status for visual highlighting in Grafana.

    Args:
        span: The span to mark as error
        message: Error message to attach to the span
    """
    if not _enabled or span is None:
        return

    span.set_status(StatusCode.ERROR, message)


def get_trace_id(heartbeat_identity):
    """Return the deterministic trace ID as a hex string for use as a Prometheus exemplar.

    Args:
        heartbeat_identity: The heartbeat identity (int)

    Returns:
        32-character hex string trace ID, or None if tracing is disabled.
    """
    if not _enabled:
        return None
    if not should_trace(heartbeat_identity):
        return None
    return format(_compute_trace_id(heartbeat_identity), "032x")
