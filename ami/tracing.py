"""
Optional distributed tracing for AMI using OpenTelemetry.

Install with: pip install ami[tracing]
Enable with: --tracing-endpoint <host:port> or --tracing-endpoint console
"""

import hashlib
import logging
import os
import random

logger = logging.getLogger(__name__)

# Module-level state
_enabled = False
_tracer = None
_id_generator = None

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

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


def setup_tracing(service_name, endpoint=None):
    """
    Initialize OpenTelemetry tracing for AMI.

    Args:
        service_name: Name of the service (e.g. "ami-worker-0", "ami-manager")
        endpoint: OTLP endpoint (host:port) or "console" for stdout.
                  If None, checks AMI_TRACING_ENDPOINT environment variable.
    """
    global _enabled, _tracer, _id_generator

    if not _OTEL_AVAILABLE:
        logger.info("OpenTelemetry not installed. Install with: pip install ami[tracing]")
        return

    # Check environment variable if endpoint not provided
    if endpoint is None:
        endpoint = os.environ.get("AMI_TRACING_ENDPOINT")

    if not endpoint:
        return

    # Initialize TracerProvider with custom IdGenerator and Resource
    _id_generator = DeterministicTraceIdGenerator()
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource, id_generator=_id_generator)

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
    Set the deterministic trace ID for the current heartbeat on the IdGenerator.
    Call this before start_span() to ensure the correct trace_id is used.

    Args:
        heartbeat_identity: The heartbeat identity (int or str)

    Returns:
        The computed trace_id (int) or None if tracing is disabled.
    """
    if not _enabled or _id_generator is None:
        return None

    # Generate deterministic trace ID from heartbeat identity
    hash_input = f"ami-heartbeat-{heartbeat_identity}".encode()
    digest = hashlib.sha256(hash_input).digest()

    # Use first 16 bytes for trace_id (128 bits)
    trace_id = int.from_bytes(digest[:16], byteorder="big")

    # Ensure non-zero (OTel requirement)
    if trace_id == 0:
        trace_id = 1

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

    # Set deterministic trace ID on the generator
    heartbeat_context(heartbeat_identity)

    # Start span WITHOUT parent context — makes it a true root span
    # The IdGenerator will supply our deterministic trace_id
    span = _tracer.start_span(
        name,
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


def mark_span_error(span, message):
    """Mark a span with ERROR status for visual highlighting in Grafana.

    Args:
        span: The span to mark as error
        message: Error message to attach to the span
    """
    if not _enabled or span is None:
        return

    from opentelemetry.trace import StatusCode

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
    digest = hashlib.sha256(f"ami-heartbeat-{heartbeat_identity}".encode()).digest()
    trace_id = int.from_bytes(digest[:16], byteorder="big")
    if trace_id == 0:
        trace_id = 1
    return format(trace_id, "032x")
