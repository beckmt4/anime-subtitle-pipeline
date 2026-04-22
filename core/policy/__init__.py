"""core.policy — quality threshold routing decisions.

Status: **not yet implemented**.

Centralises configurable quality thresholds, routing decisions, and content
gates.  Today these are scattered across ``orchestrator.py``,
``llm_polish.py``, and ``config.yaml``.

Planned responsibilities
------------------------
- Define when a low-confidence result should route to review vs. pass through.
- Define what constitutes a "pass" on a benchmark comparison.
- Accept pack-supplied threshold overrides (language packs / domain packs).
- Gate adult-content workflows (requires explicit opt-in; default off).

Planned public API
------------------
PolicyEngine              Evaluates routing decisions against thresholds.
RoutingDecision           Enum: PASS | REVIEW | REJECT
route(candidate, metrics) → RoutingDecision
"""

from __future__ import annotations

__all__: list = []  # Empty until implemented.
