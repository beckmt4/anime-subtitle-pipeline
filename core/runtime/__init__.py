"""core.runtime — config, orchestration, CLI entry point, tracing.

Integration layer that wires all other core modules together.

Public API (populated as files migrate from root — Phase 4a)
------------------------------------------------------------
setup_tracing(service_name)   OpenTelemetry initialisation.
start_span(name)              Context-manager span helper.
Config                        YAML config loader (Phase 4a).
run_generate(media, cfg)      Production generation flow (Phase 4a).
"""

from __future__ import annotations

from core.runtime.tracing import setup_tracing, start_span  # noqa: F401

__all__ = [
    "setup_tracing",
    "start_span",
]
