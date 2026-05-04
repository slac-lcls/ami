"""
Optional distributed tracing for AMI using OpenTelemetry.

Install with: pip install ami[tracing]
Enable with: --tracing-endpoint <host:port> or --tracing-endpoint console
"""

import hashlib
import logging
import os

logger = logging.getLogger(__name__)

# Module-level state
_enabled = False
_tracer = None

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


def setup_tracing(service_name, endpoint=None):
    """
    Initialize OpenTelemetry tracing for AMI.

    Args:
        service_name: Name of the service (e.g. "ami-worker-0", "ami-manager")
        endpoint: OTLP endpoint (host:port) or "console" for stdout.
                  If None, checks AMI_TRACING_ENDPOINT environment variable.
    """
    global _enabled, _tracer

    if not _OTEL_AVAILABLE:
        logger.info("OpenTelemetry not installed. Install with: pip install ami[tracing]")
        return

    # Check environment variable if endpoint not provided
    if endpoint is None:
        endpoint = os.environ.get("AMI_TRACING_ENDPOINT")

    if not endpoint:
        return

    # Initialize TracerProvider
    provider = TracerProvider()

    # Configure exporter based on endpoint
    if endpoint == "console":
        exporter = ConsoleSpanExporter()
    else:
        exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)

    # Add span processor
    processor = SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)

    # Set as global provider
    trace.set_tracer_provider(provider)

    # Get tracer for this service
    _tracer = trace.get_tracer(service_name)
    _enabled = True

    logger.info(f"Tracing enabled for {service_name} (endpoint: {endpoint})")


def heartbeat_context(heartbeat_identity):
    """
    Create an OpenTelemetry Context with a deterministic trace ID for a heartbeat.

    All processes independently compute the same trace ID for the same heartbeat,
    so spans from different processes appear in the same trace in Jaeger.

    Args:
        heartbeat_identity: The heartbeat identity (int or str)

    Returns:
        OpenTelemetry Context with the deterministic trace ID
    """
    if not _enabled:
        return None

    # Generate deterministic trace ID from heartbeat identity
    hash_input = f"ami-heartbeat-{heartbeat_identity}".encode()
    digest = hashlib.sha256(hash_input).digest()

    # Use first 16 bytes for trace_id (128 bits)
    trace_id_bytes = digest[:16]
    trace_id = int.from_bytes(trace_id_bytes, byteorder="big")

    # Use bytes 16-24 for synthetic parent span_id (64 bits)
    span_id_bytes = digest[16:24]
    span_id = int.from_bytes(span_id_bytes, byteorder="big")

    # Ensure non-zero (OTel requirement)
    if trace_id == 0:
        trace_id = 1
    if span_id == 0:
        span_id = 1

    # Create a NonRecordingSpan with this SpanContext
    span_context = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=False,
        trace_flags=TraceFlags(0x01),  # Sampled
    )
    parent_span = NonRecordingSpan(span_context)

    # Return context with this span set
    return trace.set_span_in_context(parent_span)


def start_span(name, heartbeat_identity, start_time_ns=None, attributes=None):
    """
    Start a span with a deterministic trace ID for the given heartbeat.

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

    # Get context with deterministic trace ID
    context = heartbeat_context(heartbeat_identity)
    if context is None:
        return None

    # Start span with this context
    span = _tracer.start_span(
        name,
        context=context,
        start_time=start_time_ns,
        attributes=attributes,
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


def is_enabled():
    """Returns whether tracing is currently enabled."""
    return _enabled
