"""OpenTelemetry tracing utilities for the subtitle pipeline.

Enable with environment variables:
  TRACING_ENABLED=1
  TRACING_EXPORTER=console   (or "otlp")
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
"""

from contextlib import contextmanager
import logging
import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    return os.getenv("TRACING_ENABLED", "0").lower() in ("1", "true", "yes", "on")


def _create_span_processor():
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    exporter_kind = os.getenv("TRACING_EXPORTER", "otlp" if otlp_endpoint else "console").lower()

    if exporter_kind == "otlp" and otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        logger.info(f"Tracing: OTLP exporter -> {otlp_endpoint}")
        return BatchSpanProcessor(exporter)

    if exporter_kind != "console":
        logger.warning("Tracing enabled but no exporter configured; defaulting to console")
    else:
        logger.info("Tracing: Console exporter enabled")

    return SimpleSpanProcessor(ConsoleSpanExporter())


def setup_tracing(service_name: str = "anime-subtitle-pipeline") -> None:
    """Initialize OpenTelemetry tracing if enabled by env var."""
    if not _is_enabled():
        logger.debug("Tracing disabled (TRACING_ENABLED not set)")
        return

    if isinstance(trace.get_tracer_provider(), TracerProvider):
        return  # already initialized

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(_create_span_processor())
    trace.set_tracer_provider(provider)

    try:
        RequestsInstrumentor().instrument()
    except Exception as e:
        logger.debug(f"Requests instrumentation skipped: {e}")

    try:
        LoggingInstrumentor().instrument(set_logging_format=False)
    except Exception as e:
        logger.debug(f"Logging instrumentation skipped: {e}")


@contextmanager
def start_span(name: str, **attributes):
    """Context manager that starts a named span and sets keyword attributes."""
    tracer = trace.get_tracer("anime-subtitle-pipeline")
    with tracer.start_as_current_span(name) as span:
        for k, v in attributes.items():
            try:
                span.set_attribute(str(k), v)
            except (TypeError, ValueError):
                span.set_attribute(str(k), str(v))
        yield span
