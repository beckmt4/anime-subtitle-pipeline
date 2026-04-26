"""core.policy — quality threshold routing decisions.

Centralises configurable quality thresholds and routing decisions for the
generate-mode pipeline.

Responsibilities
----------------
- Define when a low-confidence result should route to review vs. pass through.
- Define what constitutes a "pass" vs. "review" vs. "reject" outcome.
- Accept configuration-supplied threshold overrides.

Public API
----------
RoutingDecision           Enum: PASS | REVIEW | REJECT
PolicyEngine              Evaluates routing decisions against thresholds.
PolicyEngine.route(candidate_score, selection_report) → routing dict

Threshold defaults (overridable via config.yaml ``policy.routing``)
--------------------------------------------------------------------
- ``review_score_threshold`` (default 60): candidates scoring below this are
  routed to REVIEW unless they fall below ``reject_score_threshold``.
- ``reject_score_threshold`` (default 20): candidates scoring below this are
  routed to REJECT.

In addition, any strategy whose ``selection_report`` carries
``review_recommended=True`` (i.e. machine-translation or untagged-audio
fallback paths) is always routed to REVIEW regardless of score, because
machine-translated output cannot be automatically trusted.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List

__all__ = ["RoutingDecision", "PolicyEngine"]


class RoutingDecision(str, Enum):
    """Routing outcome for a generate-mode candidate."""

    PASS = "pass"
    REVIEW = "review"
    REJECT = "reject"


class PolicyEngine:
    """Evaluates routing decisions for generate-mode outputs.

    Args:
        cfg: Optional ``Config`` instance.  When provided, threshold values are
             read from ``policy.routing.review_score_threshold`` and
             ``policy.routing.reject_score_threshold``.  When ``None``,
             built-in defaults are used.
    """

    _DEFAULT_REVIEW_THRESHOLD: int = 60
    _DEFAULT_REJECT_THRESHOLD: int = 20

    def __init__(self, cfg=None) -> None:
        if cfg is not None:
            self._review_threshold: int = cfg.get(
                "policy", "routing", "review_score_threshold",
                default=self._DEFAULT_REVIEW_THRESHOLD,
            )
            self._reject_threshold: int = cfg.get(
                "policy", "routing", "reject_score_threshold",
                default=self._DEFAULT_REJECT_THRESHOLD,
            )
        else:
            self._review_threshold = self._DEFAULT_REVIEW_THRESHOLD
            self._reject_threshold = self._DEFAULT_REJECT_THRESHOLD

    def route(
        self,
        candidate_score: Dict[str, Any],
        selection_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Determine the routing decision for a generate-mode output.

        Args:
            candidate_score: Score dict returned by
                ``orchestrator.score_candidate`` — must include a
                ``total_score`` float in [0, 100].
            selection_report: Selection report dict returned by
                ``orchestrator._build_selection_report`` — must include a
                ``review_recommended`` bool and an optional ``review_reason``
                string.

        Returns:
            A JSON-serialisable dict with keys:

            - ``decision``: ``"pass"`` | ``"review"`` | ``"reject"``
            - ``reasons``: list of human-readable reason strings (empty for
              PASS)
            - ``triggered_by``: list of factor names that drove the decision
              (one or more of ``"score_below_reject_threshold"``,
              ``"score_below_review_threshold"``, ``"review_recommended"``)
        """
        total_score: float = candidate_score.get("total_score", 0.0)
        review_recommended: bool = selection_report.get("review_recommended", False)
        review_reason: str | None = selection_report.get("review_reason")

        reasons: List[str] = []
        triggered_by: List[str] = []

        if total_score < self._reject_threshold:
            decision = RoutingDecision.REJECT
            reasons.append(
                f"Score {total_score:.1f} is below the reject threshold "
                f"({self._reject_threshold})"
            )
            triggered_by.append("score_below_reject_threshold")
        elif total_score < self._review_threshold or review_recommended:
            decision = RoutingDecision.REVIEW
            if total_score < self._review_threshold:
                reasons.append(
                    f"Score {total_score:.1f} is below the review threshold "
                    f"({self._review_threshold})"
                )
                triggered_by.append("score_below_review_threshold")
            if review_recommended:
                reasons.append(
                    review_reason
                    or "Strategy requires human review"
                )
                triggered_by.append("review_recommended")
        else:
            decision = RoutingDecision.PASS

        return {
            "decision": decision.value,
            "reasons": reasons,
            "triggered_by": triggered_by,
        }
