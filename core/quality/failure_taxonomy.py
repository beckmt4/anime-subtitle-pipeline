"""Canonical taxonomy for translation failure tagging."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable

CANONICAL_FAILURE_CODES: Dict[str, Dict[str, str]] = {
    "wrong_meaning": {
        "default_severity": "fail",
        "description": "The line changes or distorts the source meaning.",
    },
    "possible_omission": {
        "default_severity": "warning",
        "description": "Part of the source meaning may be missing.",
    },
    "added_meaning": {
        "default_severity": "warning",
        "description": "The line may add unsupported meaning.",
    },
    "hallucination": {
        "default_severity": "fail",
        "description": "The output invents unsupported content.",
    },
    "bad_name": {
        "default_severity": "warning",
        "description": "A person/place/entity name is incorrect or inconsistent.",
    },
    "bad_honorific": {
        "default_severity": "warning",
        "description": "Honorific handling is incorrect for context.",
    },
    "wrong_pronoun_or_relationship": {
        "default_severity": "warning",
        "description": "Pronoun or relationship terms are incorrect.",
    },
    "too_literal": {
        "default_severity": "warning",
        "description": "Translation is overly literal and unnatural.",
    },
    "too_wordy": {
        "default_severity": "warning",
        "description": "The line is too verbose for subtitle use.",
    },
    "register_softened": {
        "default_severity": "warning",
        "description": "Tone/register was softened relative to source intent.",
    },
    "censored_or_refused": {
        "default_severity": "fail",
        "description": "Model refused/censored content instead of translating.",
    },
    "cjk_leakage": {
        "default_severity": "warning",
        "description": "CJK source text leaked into the English output.",
    },
    "subtitle_constraint_violation": {
        "default_severity": "warning",
        "description": "Subtitle formatting constraints appear violated.",
    },
    "bad_asr_source": {
        "default_severity": "warning",
        "description": "Source ASR quality likely caused translation issues.",
    },
    "bad_ocr_source": {
        "default_severity": "warning",
        "description": "Source OCR quality likely caused translation issues.",
    },
    "timing_unreadable": {
        "default_severity": "warning",
        "description": "Timing/readability constraints likely harmed meaning.",
    },
    "needs_human_review": {
        "default_severity": "warning",
        "description": "Insufficient confidence; requires manual review.",
    },
}

DEFAULT_FALLBACK_CODE = "needs_human_review"

_ALIASES = {
    "missing_final_line": "possible_omission",
    "non_english_leakage": "cjk_leakage",
    "possible_added_meaning": "added_meaning",
    "final_literal_entity_drift": "wrong_meaning",
    "possible_context_hallucination": "hallucination",
    "llm_judge_review": DEFAULT_FALLBACK_CODE,
    "llm_judge_unavailable": DEFAULT_FALLBACK_CODE,
}


def is_registered_failure_code(code: str) -> bool:
    """Return True when *code* is canonical or a supported alias."""
    normalized = str(code or "").strip().lower()
    return normalized in CANONICAL_FAILURE_CODES or normalized in _ALIASES


def normalize_failure_code(code: str) -> str:
    """Map *code* to canonical taxonomy code."""
    normalized = str(code or "").strip().lower()
    if normalized in CANONICAL_FAILURE_CODES:
        return normalized
    return _ALIASES.get(normalized, DEFAULT_FALLBACK_CODE)


def get_failure_code_definition(code: str) -> Dict[str, str]:
    """Return canonical code definition for *code*."""
    canonical = normalize_failure_code(code)
    return CANONICAL_FAILURE_CODES[canonical]


def normalize_failure_severity(code: str, severity: str) -> str:
    """Normalize arbitrary severities to warning|fail using taxonomy defaults."""
    raw = str(severity or "").strip().lower()
    if raw in {"fail", "warning"}:
        return raw
    return get_failure_code_definition(code)["default_severity"]


def aggregate_failure_codes(findings: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate canonical failure counts from structured findings."""
    by_code = Counter()
    by_severity = Counter()
    for finding in findings:
        canonical = normalize_failure_code(str(finding.get("code", "")))
        severity = normalize_failure_severity(canonical, str(finding.get("severity", "")))
        by_code[canonical] += 1
        by_severity[severity] += 1
    return {
        "total": int(sum(by_code.values())),
        "by_code": dict(sorted(by_code.items())),
        "by_severity": {
            "warning": int(by_severity.get("warning", 0)),
            "fail": int(by_severity.get("fail", 0)),
        },
    }

