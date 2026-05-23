"""Translation-focused QC checks for JP→EN subtitle candidates."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

import requests

from core.translation import load_active_glossary_data, validate_required_term_drift
from core.quality import (
    aggregate_failure_codes,
    normalize_failure_code,
    normalize_failure_severity,
)
from models import SubtitleCandidate

_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
_EN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")

_STOPWORDS = {
    "the", "and", "that", "this", "with", "from", "have", "your", "just",
    "really", "there", "they", "them", "what", "when", "where", "which",
    "will", "would", "could", "should", "about", "into", "only", "been",
    "were", "because", "then", "than", "here", "also", "their", "while",
}

_JA_EXPLICIT_MARKERS = (
    "セックス", "チン", "まんこ", "乳首", "フェラ", "中出し", "挿入", "勃起", "射精", "犯す",
)
_EN_EXPLICIT_MARKERS = (
    "sex", "fuck", "fucking", "cock", "dick", "pussy", "cum", "blowjob",
    "masturbat", "penetrat", "rape",
)
_SOFTENING_MARKERS = (
    "do that", "be together", "hook up", "get close", "intimate",
)


def _cfg_get(config: Any, *keys: str, default: Any) -> Any:
    if config is None:
        return default
    getter = getattr(config, "get", None)
    if callable(getter):
        return getter(*keys, default=default)
    return default


def _thresholds(config: Any) -> Dict[str, Any]:
    return {
        "warn_min_ratio": float(_cfg_get(config, "translation_qc", "warn_min_ratio", default=0.45)),
        "fail_min_ratio": float(_cfg_get(config, "translation_qc", "fail_min_ratio", default=0.25)),
        "warn_max_ratio": float(_cfg_get(config, "translation_qc", "warn_max_ratio", default=1.8)),
        "fail_max_ratio": float(_cfg_get(config, "translation_qc", "fail_max_ratio", default=2.8)),
        "warn_missing_keywords": int(
            _cfg_get(config, "translation_qc", "warn_missing_keywords", default=1)
        ),
        "fail_missing_keywords": int(
            _cfg_get(config, "translation_qc", "fail_missing_keywords", default=2)
        ),
        "warn_score_below": float(
            _cfg_get(config, "translation_qc", "warn_score_below", default=0.80)
        ),
        "fail_score_below": float(
            _cfg_get(config, "translation_qc", "fail_score_below", default=0.55)
        ),
        "llm_enabled": bool(
            _cfg_get(config, "translation_qc", "llm_judge", "enabled", default=False)
        ),
    }


def _extract_keywords(text: str) -> List[str]:
    words = _EN_TOKEN_RE.findall(text)
    keep: List[str] = []
    for word in words:
        lowered = word.lower()
        if lowered in _STOPWORDS:
            continue
        if word[0].isupper() or len(word) >= 5:
            keep.append(lowered)
    return keep


def _make_finding(
    *,
    segment_index: int,
    severity: str,
    code: str,
    message: str,
    source_text: str,
    literal_text: str,
    final_text: str,
) -> Dict[str, Any]:
    canonical_code = normalize_failure_code(code)
    normalized_severity = normalize_failure_severity(canonical_code, severity)
    finding = {
        "segment_index": segment_index,
        "severity": normalized_severity,
        "code": canonical_code,
        "message": message,
        "source_text": source_text,
        "literal_text": literal_text,
        "final_text": final_text,
    }
    if canonical_code != str(code).strip().lower():
        finding["raw_code"] = str(code or "")
    return finding


def _call_local_llm_judge(config: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    base_url = str(_cfg_get(config, "llm", "base_url", default="http://localhost:11434")).rstrip("/")
    model = str(_cfg_get(config, "llm", "model_name", default="qwen2.5:7b"))
    timeout = int(_cfg_get(config, "translation_qc", "llm_judge", "timeout", default=30))
    prompt = (
        "Assess translation faithfulness. Return strict JSON with key 'findings'. "
        "Each finding must include segment_index, severity (warning|fail), code, message.\n"
        f"{payload}"
    )
    response = requests.post(
        f"{base_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    text = str(data.get("response", "")).strip()
    if not text:
        return {"findings": []}
    import json
    return json.loads(text)


def run_translation_qc(
    final_candidate: SubtitleCandidate,
    *,
    source_candidate: Optional[SubtitleCandidate] = None,
    literal_candidate: Optional[SubtitleCandidate] = None,
    candidate_metadata: Optional[Dict[str, Any]] = None,
    config: Any = None,
    llm_judge: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run translation-faithfulness QC and return structured findings."""
    cfg = _thresholds(config)
    glossary_data = load_active_glossary_data(config)
    findings: List[Dict[str, Any]] = []
    segment_results: List[Dict[str, Any]] = []
    candidate_metadata = candidate_metadata or final_candidate.meta or {}

    for idx, final_seg in enumerate(final_candidate.segments, start=1):
        final_text = final_seg.text.strip()
        source_text = ""
        literal_text = ""
        if source_candidate and idx <= len(source_candidate.segments):
            source_text = source_candidate.segments[idx - 1].text.strip()
        elif isinstance(final_seg.meta, dict):
            source_text = str(
                final_seg.meta.get("source_text_ja") or final_seg.meta.get("source_text") or ""
            ).strip()

        if literal_candidate and idx <= len(literal_candidate.segments):
            literal_text = literal_candidate.segments[idx - 1].text.strip()
        elif isinstance(final_seg.meta, dict):
            literal_text = str(final_seg.meta.get("literal_text") or "").strip()

        seg_findings: List[Dict[str, Any]] = []
        if not final_text:
            seg_findings.append(
                _make_finding(
                    segment_index=idx,
                    severity="fail",
                    code="possible_omission",
                    message="Final subtitle line is empty",
                    source_text=source_text,
                    literal_text=literal_text,
                    final_text=final_text,
                )
            )
        elif _CJK_RE.search(final_text):
            seg_findings.append(
                _make_finding(
                    segment_index=idx,
                    severity="warning",
                    code="cjk_leakage",
                    message="Final subtitle contains CJK characters",
                    source_text=source_text,
                    literal_text=literal_text,
                    final_text=final_text,
                )
            )

        baseline = literal_text or source_text
        if baseline and final_text:
            ratio = len(final_text) / max(len(baseline), 1)
            if ratio <= cfg["fail_min_ratio"]:
                seg_findings.append(
                    _make_finding(
                        segment_index=idx,
                        severity="fail",
                        code="possible_omission",
                        message=f"Final subtitle is much shorter than baseline (ratio={ratio:.2f})",
                        source_text=source_text,
                        literal_text=literal_text,
                        final_text=final_text,
                    )
                )
            elif ratio <= cfg["warn_min_ratio"]:
                seg_findings.append(
                    _make_finding(
                        segment_index=idx,
                        severity="warning",
                        code="possible_omission",
                        message=f"Final subtitle may omit baseline meaning (ratio={ratio:.2f})",
                        source_text=source_text,
                        literal_text=literal_text,
                        final_text=final_text,
                    )
                )
            elif ratio >= cfg["fail_max_ratio"]:
                seg_findings.append(
                    _make_finding(
                        segment_index=idx,
                        severity="fail",
                        code="added_meaning",
                        message=f"Final subtitle is much longer than baseline (ratio={ratio:.2f})",
                        source_text=source_text,
                        literal_text=literal_text,
                        final_text=final_text,
                    )
                )
            elif ratio >= cfg["warn_max_ratio"]:
                seg_findings.append(
                    _make_finding(
                        segment_index=idx,
                        severity="warning",
                        code="added_meaning",
                        message=f"Final subtitle may add unsupported meaning (ratio={ratio:.2f})",
                        source_text=source_text,
                        literal_text=literal_text,
                        final_text=final_text,
                    )
                )

        if literal_text and final_text:
            literal_keywords = _extract_keywords(literal_text)
            final_tokens = set(word.lower() for word in _EN_TOKEN_RE.findall(final_text))
            missing = [kw for kw in literal_keywords if kw not in final_tokens]
            if len(missing) >= cfg["fail_missing_keywords"]:
                seg_findings.append(
                    _make_finding(
                        segment_index=idx,
                        severity="fail",
                        code="wrong_meaning",
                        message=f"Final subtitle dropped key terms: {', '.join(missing[:3])}",
                        source_text=source_text,
                        literal_text=literal_text,
                        final_text=final_text,
                    )
                )
            elif len(missing) >= cfg["warn_missing_keywords"]:
                seg_findings.append(
                    _make_finding(
                        segment_index=idx,
                        severity="warning",
                        code="wrong_meaning",
                        message=f"Final subtitle may drift from literal terms: {', '.join(missing[:3])}",
                        source_text=source_text,
                        literal_text=literal_text,
                        final_text=final_text,
                    )
                )

        source_for_register = f"{source_text}\n{literal_text}".lower()
        final_lower = final_text.lower()
        has_strong = any(tok in source_for_register for tok in _JA_EXPLICIT_MARKERS) or any(
            tok in source_for_register for tok in _EN_EXPLICIT_MARKERS
        )
        if has_strong and final_text:
            has_explicit_final = any(tok in final_lower for tok in _EN_EXPLICIT_MARKERS)
            has_softened = any(tok in final_lower for tok in _SOFTENING_MARKERS)
            if not has_explicit_final and has_softened:
                seg_findings.append(
                    _make_finding(
                        segment_index=idx,
                        severity="warning",
                        code="register_softened",
                        message="Final subtitle appears softer than source/literal register",
                        source_text=source_text,
                        literal_text=literal_text,
                        final_text=final_text,
                    )
                )

        drift_findings = validate_required_term_drift(
            source_text=source_text,
            final_text=final_text,
            glossary_data=glossary_data,
            literal_text=literal_text,
        )
        for raw in drift_findings:
            finding = _make_finding(
                segment_index=idx,
                severity=str(raw.get("severity", "warning")),
                code=str(raw.get("code", "wrong_meaning")),
                message=str(raw.get("message", "Required term drift detected")),
                source_text=source_text,
                literal_text=literal_text,
                final_text=final_text,
            )
            for key in ("term_kind", "source_term", "expected_target", "pack_scope"):
                if raw.get(key):
                    finding[key] = raw[key]
            seg_findings.append(finding)

        findings.extend(seg_findings)
        segment_results.append(
            {
                "segment_index": idx,
                "review_required": bool(seg_findings),
                "status": (
                    "fail" if any(f["severity"] == "fail" for f in seg_findings)
                    else "warn" if seg_findings else "pass"
                ),
                "finding_count": len(seg_findings),
                "failure_codes": list(dict.fromkeys(str(f["code"]) for f in seg_findings)),
            }
        )

    if cfg["llm_enabled"]:
        judge = llm_judge or (lambda payload: _call_local_llm_judge(config, payload))
        payload = {
            "candidate_id": final_candidate.id,
            "meta": candidate_metadata,
            "segments": [
                {
                    "segment_index": i + 1,
                    "source_text": (source_candidate.segments[i].text if source_candidate and i < len(source_candidate.segments) else ""),
                    "literal_text": (
                        literal_candidate.segments[i].text
                        if literal_candidate and i < len(literal_candidate.segments)
                        else str(final_candidate.segments[i].meta.get("literal_text", ""))
                    ),
                    "final_text": final_candidate.segments[i].text,
                }
                for i in range(len(final_candidate.segments))
            ],
        }
        try:
            llm_result = judge(payload) or {}
            for raw in llm_result.get("findings", []):
                seg_idx = int(raw.get("segment_index", -1))
                raw_code = str(raw.get("code", "llm_judge_review"))
                findings.append(
                    _make_finding(
                        segment_index=seg_idx,
                        severity=str(raw.get("severity", "warning")),
                        code=raw_code,
                        message=str(raw.get("message", "LLM judge requested review")),
                        source_text=str(raw.get("source_text", "")),
                        literal_text=str(raw.get("literal_text", "")),
                        final_text=str(raw.get("final_text", "")),
                    )
                )
                severity = findings[-1]["severity"]
                code = str(findings[-1]["code"])
                if 1 <= seg_idx <= len(segment_results):
                    segment_results[seg_idx - 1]["review_required"] = True
                    if severity == "fail":
                        segment_results[seg_idx - 1]["status"] = "fail"
                    elif segment_results[seg_idx - 1]["status"] == "pass":
                        segment_results[seg_idx - 1]["status"] = "warn"
                    segment_results[seg_idx - 1]["failure_codes"] = list(
                        dict.fromkeys(segment_results[seg_idx - 1]["failure_codes"] + [code])
                    )
        except Exception as exc:
            findings.append(
                _make_finding(
                    segment_index=-1,
                    severity="warning",
                    code="needs_human_review",
                    message=f"Local LLM judge failed: {exc}",
                    source_text="",
                    literal_text="",
                    final_text="",
                )
            )

    warning_count = sum(1 for f in findings if f["severity"] == "warning")
    fail_count = sum(1 for f in findings if f["severity"] == "fail")
    taxonomy_summary = aggregate_failure_codes(findings)
    taxonomy_codes = list(taxonomy_summary["by_code"].keys())
    score = 1.0 - warning_count * 0.08 - fail_count * 0.20
    score = max(0.0, min(1.0, score))

    if fail_count > 0 or score < cfg["fail_score_below"]:
        qc_status = "fail"
    elif warning_count > 0 or score < cfg["warn_score_below"]:
        qc_status = "warn"
    else:
        qc_status = "pass"

    return {
        "candidate_id": final_candidate.id,
        "qc_status": qc_status,
        "score": round(score, 3),
        "findings": findings,
        "taxonomy_codes": taxonomy_codes,
        "taxonomy_summary": taxonomy_summary,
        "segment_results": segment_results,
        "summary": {
            "warning_count": warning_count,
            "fail_count": fail_count,
            "review_required_segments": sum(1 for s in segment_results if s["review_required"]),
        },
    }


__all__ = ["run_translation_qc"]
