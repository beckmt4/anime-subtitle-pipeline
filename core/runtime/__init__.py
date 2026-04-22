"""core.runtime — config, orchestration, CLI entry point, tracing.

Integration layer that wires all other core modules together and provides the
CLI entry point.

Public API (target — populated as files migrate from root)
----------------------------------------------------------
Config                   YAML config loader with profile merging.
run_generate(media, cfg) → dict   Production subtitle generation flow.
run_benchmark(media, cfg) → dict  Multi-source benchmark flow.
setup_tracing(cfg)                OpenTelemetry initialisation.
start_span(name)                  Context-manager span helper.

During the migration period the root-level ``config.py``, ``orchestrator.py``,
``tracing.py``, ``batch_process.py``, and ``main.py`` own the implementation.
Import from there until the migration is complete.
"""

from __future__ import annotations

from config import Config  # noqa: F401 — re-export
from orchestrator import run_generate  # noqa: F401 — re-export
from tracing import setup_tracing, start_span  # noqa: F401 — re-export

__all__ = [
    "Config",
    "run_generate",
    "setup_tracing",
    "start_span",
]
