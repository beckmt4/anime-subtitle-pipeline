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

from core.runtime.config import Config, get_config, set_config  # noqa: F401
from core.runtime.tracing import setup_tracing, start_span  # noqa: F401


def run_generate(*args, **kwargs):
    from core.runtime.orchestrator import run_generate as _run_generate

    return _run_generate(*args, **kwargs)

__all__ = [
    "Config",
    "get_config",
    "set_config",
    "run_generate",
    "setup_tracing",
    "start_span",
]
