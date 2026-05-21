"""Deterministic review-task generation rules for generate and benchmark runs."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

REVIEW_STATUS_OK = "ok"
REVIEW_STATUS_WARNING = "warning"
REVIEW_STATUS_REVIEW_REQUIRED = "review_required"
REVIEW_STATUS_FAILED = "failed"

_STATUS_PRIORITY = {
    REVIEW_STATUS_OK: 0,
    REVIEW_STATUS_WARNING: 1,
    REVIEW_STATUS_REVIEW_REQUIRED: 2,
    REVIEW_STATUS_FAILED: 3,
}

_DEFAULT_GENERATE_RULES = {
    "review_high_cps_min_count": 3,
    "review_duration_violation_min_count": 2,
    "review_readability_violation_min_count": 3,
    "review_polish_change_rate_threshold": 0.35,
}

_DEFAULT_BENCHMARK_RULES = {
    "wer_max": 0.45,
    "bleu_min": 25.0,
    "chrf_min": 45.0,
    "review_min_weak_comparisons": 1,
}


def _bump_status(current: str, candidate: str) -> str:
    if _STATUS_PRIORITY[candidate] > _STATUS_PRIORITY[current]:
        return candidate
    return current


def _safe_cfg_get(cfg: Any, *keys: str, default: Any) -> Any:
    if cfg is None:
        return default
    getter = getattr(cfg, "get", None)
    if callable(getter):
        return getter(*keys, default=default)
    return default


def route_generate_review_task(
    *,
    video: str,
    candidate_id: str,
    strategy: str,
    qc_summary: Dict[str, Any],
    candidate_score: Dict[str, Any] | None = None,
    selection_report: Dict[str, Any] | None = None,
    routing_decision: Dict[str, Any] | None = None,
    polish_change_rate: float | None = None,
    cfg: Any = None,
) -> Dict[str, Any]:
    """Route generate-mode output to ok/warning/review_required/failed."""
    rules = {
        key: _safe_cfg_get(cfg, "policy", "review_task", "generate", key, default=value)
        for key, value in _DEFAULT_GENERATE_RULES.items()
    }
    status = REVIEW_STATUS_OK
    reason_codes: List[str] = []
    violations = qc_summary.get("violations", []) if isinstance(qc_summary, dict) else []
    typed = Counter(str(v.get("type")) for v in violations)
    typed_error = Counter(
        str(v.get("type"))
        for v in violations
        if str(v.get("severity")) == "error"
    )
    typed_warning = Counter(
        str(v.get("type"))
        for v in violations
        if str(v.get("severity")) == "warning"
    )

    parsed_ok = bool(qc_summary.get("parsed_ok", False))
    cue_count = int(qc_summary.get("cue_count", 0) or 0)
    if (not parsed_ok) or cue_count <= 0:
        status = _bump_status(status, REVIEW_STATUS_FAILED)
        reason_codes.append("generate.invalid_or_zero_cues")

    if routing_decision is not None:
        decision = str(routing_decision.get("decision", "pass"))
        if decision == "reject":
            status = _bump_status(status, REVIEW_STATUS_FAILED)
            reason_codes.append("generate.policy_reject")
        elif decision == "review":
            status = _bump_status(status, REVIEW_STATUS_REVIEW_REQUIRED)
            reason_codes.append("generate.policy_review")

    if selection_report and bool(selection_report.get("review_recommended", False)):
        status = _bump_status(status, REVIEW_STATUS_REVIEW_REQUIRED)
        reason_codes.append("generate.low_confidence_strategy")

    if typed["overlap"] > 0:
        status = _bump_status(status, REVIEW_STATUS_REVIEW_REQUIRED)
        reason_codes.append("generate.timing_overlap")
    if typed["out_of_order"] > 0:
        status = _bump_status(status, REVIEW_STATUS_REVIEW_REQUIRED)
        reason_codes.append("generate.timing_out_of_order")

    duration_count = typed["duration_too_short"] + typed["duration_too_long"]
    if duration_count >= int(rules["review_duration_violation_min_count"]):
        status = _bump_status(status, REVIEW_STATUS_REVIEW_REQUIRED)
        reason_codes.append("generate.duration_violations_repeated")
    elif duration_count > 0:
        status = _bump_status(status, REVIEW_STATUS_WARNING)
        reason_codes.append("generate.duration_violations_minor")

    cps_count = typed["high_cps"]
    if cps_count >= int(rules["review_high_cps_min_count"]):
        status = _bump_status(status, REVIEW_STATUS_REVIEW_REQUIRED)
        reason_codes.append("generate.high_cps_repeated")
    elif cps_count > 0:
        status = _bump_status(status, REVIEW_STATUS_WARNING)
        reason_codes.append("generate.high_cps_minor")

    readability_count = typed["line_too_long"] + typed["too_many_lines"]
    if readability_count >= int(rules["review_readability_violation_min_count"]):
        status = _bump_status(status, REVIEW_STATUS_REVIEW_REQUIRED)
        reason_codes.append("generate.readability_violations_repeated")
    elif readability_count > 0:
        status = _bump_status(status, REVIEW_STATUS_WARNING)
        reason_codes.append("generate.readability_violations_minor")

    if typed_error["formatting_artifact"] > 0:
        status = _bump_status(status, REVIEW_STATUS_REVIEW_REQUIRED)
        reason_codes.append("generate.formatting_artifact_unresolved")
    elif typed_warning["formatting_artifact"] > 0:
        status = _bump_status(status, REVIEW_STATUS_WARNING)
        reason_codes.append("generate.formatting_artifact_warning")

    if polish_change_rate is not None:
        if float(polish_change_rate) >= float(rules["review_polish_change_rate_threshold"]):
            status = _bump_status(status, REVIEW_STATUS_REVIEW_REQUIRED)
            reason_codes.append("generate.high_polish_change_rate")

    reason_codes = list(dict.fromkeys(reason_codes))
    review_task = None
    if status in {REVIEW_STATUS_REVIEW_REQUIRED, REVIEW_STATUS_FAILED}:
        review_task = {
            "schema_version": 1,
            "task_type": "subtitle_review",
            "mode": "generate",
            "status": status,
            "video": video,
            "candidate_id": candidate_id,
            "strategy": strategy,
            "reason_codes": reason_codes,
            "evidence": {
                "cue_count": cue_count,
                "error_count": int(qc_summary.get("error_count", 0) or 0),
                "warning_count": int(qc_summary.get("warning_count", 0) or 0),
                "routing_decision": (routing_decision or {}).get("decision"),
                "total_score": (candidate_score or {}).get("total_score"),
            },
        }
    return {
        "status": status,
        "reason_codes": reason_codes,
        "review_task": review_task,
    }


def route_benchmark_review_task(
    *,
    video: str,
    results: Dict[str, Any],
    cfg: Any = None,
) -> Dict[str, Any]:
    """Route benchmark-mode output to ok/warning/review_required."""
    rules = {
        key: _safe_cfg_get(cfg, "policy", "review_task", "benchmark", key, default=value)
        for key, value in _DEFAULT_BENCHMARK_RULES.items()
    }
    status = REVIEW_STATUS_OK
    reason_codes: List[str] = []
    weak_comparisons: List[Dict[str, Any]] = []
    comparisons = list(results.get("comparisons", []))

    if str(results.get("status")) == "single_candidate_only":
        status = _bump_status(status, REVIEW_STATUS_WARNING)
        reason_codes.append("benchmark.single_candidate_only")
    if not comparisons:
        status = _bump_status(status, REVIEW_STATUS_WARNING)
        reason_codes.append("benchmark.no_comparisons")

    wer_max = float(rules["wer_max"])
    bleu_min = float(rules["bleu_min"])
    chrf_min = float(rules["chrf_min"])
    for comp in comparisons:
        metrics = comp.get("metrics", {})
        wer = metrics.get("wer")
        bleu = metrics.get("bleu")
        chrf = metrics.get("chrf")
        if wer is None or bleu is None or chrf is None:
            continue
        if float(wer) > wer_max or float(bleu) < bleu_min or float(chrf) < chrf_min:
            weak_comparisons.append(
                {
                    "ref_id": comp.get("ref_id"),
                    "cand_id": comp.get("cand_id"),
                    "wer": float(wer),
                    "bleu": float(bleu),
                    "chrf": float(chrf),
                }
            )

    if len(weak_comparisons) >= int(rules["review_min_weak_comparisons"]):
        status = _bump_status(status, REVIEW_STATUS_REVIEW_REQUIRED)
        reason_codes.append("benchmark.quality_below_threshold")
    elif weak_comparisons:
        status = _bump_status(status, REVIEW_STATUS_WARNING)
        reason_codes.append("benchmark.quality_borderline")

    reason_codes = list(dict.fromkeys(reason_codes))
    review_task = None
    if status == REVIEW_STATUS_REVIEW_REQUIRED:
        review_task = {
            "schema_version": 1,
            "task_type": "benchmark_review",
            "mode": "benchmark",
            "status": status,
            "video": video,
            "run_id": results.get("run_id"),
            "reference_id": results.get("reference_id"),
            "reason_codes": reason_codes,
            "evidence": {
                "comparison_count": len(comparisons),
                "weak_comparison_count": len(weak_comparisons),
                "thresholds": {
                    "wer_max": wer_max,
                    "bleu_min": bleu_min,
                    "chrf_min": chrf_min,
                },
                "weak_comparisons": weak_comparisons,
            },
        }
    return {
        "status": status,
        "reason_codes": reason_codes,
        "review_task": review_task,
    }


__all__ = [
    "REVIEW_STATUS_OK",
    "REVIEW_STATUS_WARNING",
    "REVIEW_STATUS_REVIEW_REQUIRED",
    "REVIEW_STATUS_FAILED",
    "route_generate_review_task",
    "route_benchmark_review_task",
]
