"""OpenTelemetry tracing utilities — re-exported from core.runtime.tracing."""

from core.runtime.tracing import setup_tracing, start_span  # noqa: F401

__all__ = ["setup_tracing", "start_span"]
