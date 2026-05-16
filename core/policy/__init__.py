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
    _DEFAULT_ASR_WARNING_REVIEW_DENSITY: float = 0.10
    _DEFAULT_OCR_WARNING_REVIEW_DENSITY: float = 0.30
    _DEFAULT_TRANSLATION_QC_REVIEW_STATUSES: tuple[str, ...] = ("warn",)
    _DEFAULT_TRANSLATION_QC_REJECT_STATUSES: tuple[str, ...] = ("fail",)
    _DEFAULT_TRANSLATION_QC_WARN_REVIEW_MIN_COUNT: int = 1
    _DEFAULT_TRANSLATION_QC_FAIL_REJECT_MIN_COUNT: int = 1

    def __init__(self, cfg=None) -> None:
        def _to_status_set(value: Any, default_values: tuple[str, ...]) -> set[str]:
            if value is None:
                return set(default_values)
            if isinstance(value, str):
                return {value.lower()}
            if isinstance(value, (list, tuple, set)):
                return {str(item).lower() for item in value}
            return set(default_values)

        if cfg is not None:
            self._review_threshold: int = cfg.get(
                "policy", "routing", "review_score_threshold",
                default=self._DEFAULT_REVIEW_THRESHOLD,
            )
            self._reject_threshold: int = cfg.get(
                "policy", "routing", "reject_score_threshold",
                default=self._DEFAULT_REJECT_THRESHOLD,
            )
            self._asr_warning_review_density: float = cfg.get(
                "policy", "routing", "asr_warning_review_density",
                default=self._DEFAULT_ASR_WARNING_REVIEW_DENSITY,
            )
            self._ocr_warning_review_density: float = cfg.get(
                "policy", "routing", "ocr_warning_review_density",
                default=self._DEFAULT_OCR_WARNING_REVIEW_DENSITY,
            )
            self._translation_qc_review_statuses = _to_status_set(
                cfg.get("policy", "routing", "translation_qc_review_statuses", default=None),
                self._DEFAULT_TRANSLATION_QC_REVIEW_STATUSES,
            )
            self._translation_qc_reject_statuses = _to_status_set(
                cfg.get("policy", "routing", "translation_qc_reject_statuses", default=None),
                self._DEFAULT_TRANSLATION_QC_REJECT_STATUSES,
            )
            self._translation_qc_warn_review_min_count: int = int(
                cfg.get(
                    "policy", "routing", "translation_qc_warn_review_min_count",
                    default=self._DEFAULT_TRANSLATION_QC_WARN_REVIEW_MIN_COUNT,
                )
            )
            self._translation_qc_fail_reject_min_count: int = int(
                cfg.get(
                    "policy", "routing", "translation_qc_fail_reject_min_count",
                    default=self._DEFAULT_TRANSLATION_QC_FAIL_REJECT_MIN_COUNT,
                )
            )
        else:
            self._review_threshold = self._DEFAULT_REVIEW_THRESHOLD
            self._reject_threshold = self._DEFAULT_REJECT_THRESHOLD
            self._asr_warning_review_density = self._DEFAULT_ASR_WARNING_REVIEW_DENSITY
            self._ocr_warning_review_density = self._DEFAULT_OCR_WARNING_REVIEW_DENSITY
            self._translation_qc_review_statuses = set(self._DEFAULT_TRANSLATION_QC_REVIEW_STATUSES)
            self._translation_qc_reject_statuses = set(self._DEFAULT_TRANSLATION_QC_REJECT_STATUSES)
            self._translation_qc_warn_review_min_count = self._DEFAULT_TRANSLATION_QC_WARN_REVIEW_MIN_COUNT
            self._translation_qc_fail_reject_min_count = self._DEFAULT_TRANSLATION_QC_FAIL_REJECT_MIN_COUNT

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
              ``"score_below_review_threshold"``, ``"review_recommended"``,
              ``"translation_qc_warn"``, ``"translation_qc_fail"``)
        """
        total_score: float = candidate_score.get("total_score", 0.0)
        asr_warning_density: float = candidate_score.get("asr_warning_density", 0.0)
        ocr_warning_density: float = candidate_score.get("ocr_warning_density", 0.0)
        translation_qc_status: str = str(candidate_score.get("translation_qc_status", "pass")).lower()
        translation_qc_warning_count: int = int(candidate_score.get("translation_qc_warning_count", 0) or 0)
        translation_qc_fail_count: int = int(candidate_score.get("translation_qc_fail_count", 0) or 0)
        review_recommended: bool = selection_report.get("review_recommended", False)
        review_reason: str | None = selection_report.get("review_reason")

        translation_qc_reject = (
            translation_qc_status in self._translation_qc_reject_statuses
            and translation_qc_fail_count >= self._translation_qc_fail_reject_min_count
        )
        translation_qc_review = (
            translation_qc_status in self._translation_qc_review_statuses
            and translation_qc_warning_count >= self._translation_qc_warn_review_min_count
        )

        reasons: List[str] = []
        triggered_by: List[str] = []

        if total_score < self._reject_threshold or translation_qc_reject:
            decision = RoutingDecision.REJECT
            if total_score < self._reject_threshold:
                reasons.append(
                    f"Score {total_score:.1f} is below the reject threshold "
                    f"({self._reject_threshold})"
                )
                triggered_by.append("score_below_reject_threshold")
            if translation_qc_reject:
                reasons.append(
                    "Translation QC status is fail "
                    f"(fail_count={translation_qc_fail_count}, "
                    f"threshold={self._translation_qc_fail_reject_min_count})"
                )
                triggered_by.append("translation_qc_fail")
        elif (
            total_score < self._review_threshold
            or review_recommended
            or asr_warning_density >= self._asr_warning_review_density
            or ocr_warning_density >= self._ocr_warning_review_density
            or translation_qc_review
        ):
            decision = RoutingDecision.REVIEW
            if total_score < self._review_threshold:
                reasons.append(
                    f"Score {total_score:.1f} is below the review threshold "
                    f"({self._review_threshold})"
                )
                triggered_by.append("score_below_review_threshold")
            if asr_warning_density >= self._asr_warning_review_density:
                reasons.append(
                    f"ASR warning density {asr_warning_density:.1%} is at or above "
                    f"the review threshold ({self._asr_warning_review_density:.1%})"
                )
                triggered_by.append("asr_warning_density")
            if ocr_warning_density >= self._ocr_warning_review_density:
                reasons.append(
                    f"OCR warning density {ocr_warning_density:.1%} is at or above "
                    f"the review threshold ({self._ocr_warning_review_density:.1%})"
                )
                triggered_by.append("ocr_warning_density")
            if review_recommended:
                reasons.append(
                    review_reason
                    or "Strategy requires human review"
                )
                triggered_by.append("review_recommended")
            if translation_qc_review:
                reasons.append(
                    "Translation QC status is warn "
                    f"(warning_count={translation_qc_warning_count}, "
                    f"threshold={self._translation_qc_warn_review_min_count})"
                )
                triggered_by.append("translation_qc_warn")
        else:
            decision = RoutingDecision.PASS

        return {
            "decision": decision.value,
            "reasons": reasons,
            "triggered_by": triggered_by,
        }
