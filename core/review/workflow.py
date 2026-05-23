"""Review queue backend and local HTML review UI helpers."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from core.artifacts import (
    ARTIFACT_TYPE_SRT,
    CANDIDATE_STATUS_ACCEPTED,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_PENDING,
    ArtifactRecord,
    ArtifactRegistry,
    ReviewTaskRecord,
    SubtitleCandidateRecord,
)
from core.translation import TranslationMemoryStore


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_timestamp_srt(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _append_history(
    registry: ArtifactRegistry,
    task_id: int,
    *,
    action: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    registry.append_review_task_history(
        task_id,
        {
            "timestamp": _utcnow_iso(),
            "action": action,
            "details": details or {},
        },
    )


def _find_existing_pending_task(
    registry: ArtifactRegistry,
    *,
    media_hash: str,
    candidate_id: int,
) -> Optional[ReviewTaskRecord]:
    for task in registry.list_review_tasks(media_hash=media_hash, status=REVIEW_STATUS_PENDING):
        if task.candidate_id == candidate_id:
            return task
    return None


def create_review_task_from_generate_output(
    registry: Optional[ArtifactRegistry],
    *,
    media_hash: Optional[str],
    candidate_db_id: Optional[int],
    routing: Mapping[str, Any],
) -> Optional[ReviewTaskRecord]:
    """Create a pending review task from generate-mode routing output."""
    if registry is None or not media_hash or candidate_db_id is None:
        return None
    review_task = routing.get("review_task")
    if not isinstance(review_task, dict):
        return None
    existing = _find_existing_pending_task(
        registry,
        media_hash=media_hash,
        candidate_id=candidate_db_id,
    )
    if existing is not None:
        return existing
    reason_codes = routing.get("reason_codes", [])
    created = registry.create_review_task(
        ReviewTaskRecord(
            media_hash=media_hash,
            candidate_id=candidate_db_id,
            status=REVIEW_STATUS_PENDING,
            reviewer_notes="auto-created from generate routing",
        )
    )
    _append_history(
        registry,
        created.id,
        action="task_created",
        details={"mode": "generate", "reason_codes": list(reason_codes)},
    )
    return registry.get_review_task(created.id)


def _resolve_benchmark_candidate_id(
    registry: ArtifactRegistry,
    *,
    media_hash: str,
    routing: Mapping[str, Any],
    results: Mapping[str, Any],
) -> Optional[int]:
    candidates = registry.list_candidates(media_hash)
    by_source_id = {cand.source_id: cand.id for cand in candidates}

    preferred_source_ids: List[str] = []
    review_task = routing.get("review_task")
    if isinstance(review_task, dict):
        evidence = review_task.get("evidence", {})
        if isinstance(evidence, dict):
            for weak in evidence.get("weak_comparisons", []):
                if isinstance(weak, dict) and weak.get("cand_id"):
                    preferred_source_ids.append(str(weak["cand_id"]))
            if review_task.get("reference_id"):
                preferred_source_ids.append(str(review_task["reference_id"]))

    for scorecard in results.get("scorecards", []):
        if not isinstance(scorecard, dict):
            continue
        sid = scorecard.get("id")
        if sid:
            preferred_source_ids.append(str(sid))

    for sid in preferred_source_ids:
        if sid in by_source_id:
            return by_source_id[sid]
    return candidates[-1].id if candidates else None


def create_review_task_from_benchmark_output(
    registry: Optional[ArtifactRegistry],
    *,
    media_hash: Optional[str],
    routing: Mapping[str, Any],
    results: Mapping[str, Any],
) -> Optional[ReviewTaskRecord]:
    """Create a pending review task from benchmark-mode routing output."""
    if registry is None or not media_hash:
        return None
    if not isinstance(routing.get("review_task"), dict):
        return None
    candidate_id = _resolve_benchmark_candidate_id(
        registry,
        media_hash=media_hash,
        routing=routing,
        results=results,
    )
    if candidate_id is None:
        return None
    existing = _find_existing_pending_task(
        registry,
        media_hash=media_hash,
        candidate_id=candidate_id,
    )
    if existing is not None:
        return existing
    reason_codes = routing.get("reason_codes", [])
    created = registry.create_review_task(
        ReviewTaskRecord(
            media_hash=media_hash,
            candidate_id=candidate_id,
            status=REVIEW_STATUS_PENDING,
            reviewer_notes="auto-created from benchmark routing",
        )
    )
    _append_history(
        registry,
        created.id,
        action="task_created",
        details={"mode": "benchmark", "reason_codes": list(reason_codes)},
    )
    return registry.get_review_task(created.id)


def list_review_queue(registry: ArtifactRegistry, *, status: str = REVIEW_STATUS_PENDING) -> List[ReviewTaskRecord]:
    """Return review tasks in queue order (oldest first)."""
    return registry.list_review_tasks(status=status)


def build_review_comparison(
    registry: ArtifactRegistry,
    *,
    task_id: int,
    compare_candidate_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Build side-by-side data for a review task."""
    task = registry.get_review_task(task_id)
    if task is None:
        raise LookupError(f"No review task with id={task_id}")
    candidate = registry.get_candidate(task.candidate_id)
    if candidate is None:
        raise LookupError(f"No subtitle candidate with id={task.candidate_id}")

    compare_candidate = None
    if compare_candidate_id is not None:
        compare_candidate = registry.get_candidate(compare_candidate_id)
    if compare_candidate is None and candidate.parent_candidate_id is not None:
        compare_candidate = registry.get_candidate(candidate.parent_candidate_id)
    if compare_candidate is None:
        siblings = [
            c for c in registry.list_candidates(task.media_hash)
            if c.id != candidate.id
        ]
        compare_candidate = siblings[-1] if siblings else None

    candidate_segments = list(candidate.segments or [])
    compare_segments = list((compare_candidate.segments if compare_candidate else []) or [])
    total = max(len(candidate_segments), len(compare_segments))
    rows = []
    for idx in range(total):
        cand_seg = candidate_segments[idx] if idx < len(candidate_segments) else {}
        cmp_seg = compare_segments[idx] if idx < len(compare_segments) else {}
        start = cand_seg.get("start", cmp_seg.get("start", 0.0))
        end = cand_seg.get("end", cmp_seg.get("end", 0.0))
        rows.append(
            {
                "index": idx,
                "start": float(start or 0.0),
                "end": float(end or 0.0),
                "candidate_text": str(cand_seg.get("text", "")),
                "compare_text": str(cmp_seg.get("text", "")),
            }
        )
    return {
        "task": task,
        "candidate": candidate,
        "compare_candidate": compare_candidate,
        "rows": rows,
    }


def render_local_review_ui(
    registry: ArtifactRegistry,
    *,
    task_id: int,
    output_path: str,
    compare_candidate_id: Optional[int] = None,
) -> Path:
    """Render a self-contained local HTML review UI."""
    model = build_review_comparison(
        registry,
        task_id=task_id,
        compare_candidate_id=compare_candidate_id,
    )
    task = model["task"]
    candidate = model["candidate"]
    compare_candidate = model["compare_candidate"]
    rows = model["rows"]

    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>"
            f"<td>{row['index'] + 1}</td>"
            f"<td>{_format_timestamp_srt(row['start'])}<br>{_format_timestamp_srt(row['end'])}</td>"
            f"<td>{html.escape(row['compare_text'])}</td>"
            "<td>"
            f"<textarea data-index=\"{row['index']}\" data-original=\"{html.escape(row['candidate_text'])}\">"
            f"{html.escape(row['candidate_text'])}</textarea>"
            "</td>"
            "</tr>"
        )

    compare_name = compare_candidate.source_id if compare_candidate else "none"
    html_doc = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Review Task {task.id}</title>"
        "<style>"
        "body{font-family:Arial,sans-serif;padding:16px;background:#f7f7f7;color:#222}"
        "table{border-collapse:collapse;width:100%;background:#fff}"
        "th,td{border:1px solid #ddd;padding:8px;vertical-align:top}"
        "th{background:#2c3e50;color:#fff}"
        "textarea{width:100%;min-height:48px;font-family:inherit}"
        ".meta{margin-bottom:12px}.meta code{background:#eee;padding:2px 5px}"
        ".toolbar{margin:12px 0}.json-out{width:100%;min-height:120px}"
        "</style></head><body>"
        f"<h1>Review Task #{task.id}</h1>"
        "<div class='meta'>"
        f"Media: <code>{html.escape(task.media_hash)}</code> | "
        f"Candidate: <code>{html.escape(candidate.source_id)}</code> | "
        f"Compare: <code>{html.escape(compare_name)}</code>"
        "</div>"
        "<div class='toolbar'><button onclick='exportEdits()'>Export edits JSON</button></div>"
        "<table><thead><tr><th>#</th><th>Timing</th><th>Compare</th><th>Editable candidate</th></tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
        "<h3>edits.json payload</h3><textarea id='json-out' class='json-out' readonly></textarea>"
        "<script>"
        "function exportEdits(){"
        "const edits={};"
        "document.querySelectorAll('textarea[data-index]').forEach((ta)=>{"
        "if(ta.value!==ta.dataset.original){edits[ta.dataset.index]=ta.value;}"
        "});"
        "document.getElementById('json-out').value=JSON.stringify(edits,null,2);"
        "}"
        "</script></body></html>"
    )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_doc, encoding="utf-8")
    return out


def _normalise_edits(edited_segments: Optional[Mapping[int, str] | Mapping[str, str]]) -> Dict[int, str]:
    if not edited_segments:
        return {}
    normalised: Dict[int, str] = {}
    for idx, text in edited_segments.items():
        normalised[int(idx)] = str(text)
    return normalised


def _write_simple_srt(segments: List[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    for idx, seg in enumerate(segments, start=1):
        start = _format_timestamp_srt(float(seg.get("start", 0.0)))
        end = _format_timestamp_srt(float(seg.get("end", 0.0)))
        text = str(seg.get("text", "")).strip()
        lines.extend([str(idx), f"{start} --> {end}", text, ""])
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _source_context_text(segment: Dict[str, Any]) -> str:
    meta = segment.get("meta", {}) if isinstance(segment, dict) else {}
    if isinstance(meta, dict):
        source_text = str(meta.get("source_text_ja", "")).strip()
        if source_text:
            return source_text
    return str(segment.get("text", "")).strip() if isinstance(segment, dict) else ""


def _store_approved_corrections(
    *,
    translation_memory: TranslationMemoryStore,
    candidate: SubtitleCandidateRecord,
    updated_segments: List[Dict[str, Any]],
    edits: Dict[int, str],
    reviewer_notes: str,
) -> int:
    stored_count = 0
    domain = str(candidate.meta.get("domain_pack", "")).strip() or None
    language_pack = str(candidate.meta.get("language_pack", "")).strip() or None
    for idx in sorted(edits):
        if idx < 0 or idx >= len(updated_segments):
            continue
        before = str((candidate.segments[idx] or {}).get("text", "")).strip()
        after = str((updated_segments[idx] or {}).get("text", "")).strip()
        if not before or not after or before == after:
            continue
        current_segment = updated_segments[idx] or {}
        source_text = _source_context_text(current_segment)
        previous_context = _source_context_text(updated_segments[idx - 1]) if idx > 0 else ""
        next_context = _source_context_text(updated_segments[idx + 1]) if idx + 1 < len(updated_segments) else ""
        if not source_text:
            continue
        translation_memory.add(
            {
                "source_lang": str(candidate.meta.get("source_language", "ja")),
                "target_lang": str(candidate.language or "en"),
                "domain": domain,
                "source_text": source_text,
                "bad_translation": before,
                "approved_translation": after,
                "previous_context": previous_context,
                "next_context": next_context,
                "speaker": None,
                "tags": ["review_approved_edit"],
                "notes": reviewer_notes,
                "language_pack": language_pack,
            }
        )
        stored_count += 1
    return stored_count


def approve_review_task(
    registry: ArtifactRegistry,
    *,
    task_id: int,
    edited_segments: Optional[Mapping[int, str] | Mapping[str, str]] = None,
    reviewer_notes: Optional[str] = None,
    output_srt_path: Optional[str] = None,
    translation_memory: Optional[TranslationMemoryStore] = None,
) -> Dict[str, Any]:
    """Apply optional edits, approve a task, and persist an approved output."""
    task = registry.get_review_task(task_id)
    if task is None:
        raise LookupError(f"No review task with id={task_id}")
    candidate = registry.get_candidate(task.candidate_id)
    if candidate is None:
        raise LookupError(f"No subtitle candidate with id={task.candidate_id}")

    edits = _normalise_edits(edited_segments)
    updated_segments = [dict(seg) for seg in (candidate.segments or [])]
    for idx, text in edits.items():
        if idx < 0 or idx >= len(updated_segments):
            raise IndexError(f"Segment index out of range: {idx}")
        updated_segments[idx]["text"] = text

    approved = registry.store_candidate(
        SubtitleCandidateRecord(
            media_hash=candidate.media_hash,
            source_id=f"{candidate.source_id}.review_t{task_id}",
            language=candidate.language,
            source=candidate.source,
            origin_stream=candidate.origin_stream,
            model_version=candidate.model_version,
            segments=updated_segments,
            meta={
                **candidate.meta,
                "review_task_id": task.id,
                "review_parent_candidate_id": candidate.id,
                "review_edits_count": len(edits),
            },
            status=CANDIDATE_STATUS_ACCEPTED,
            parent_candidate_id=candidate.id,
        )
    )

    note = reviewer_notes or task.reviewer_notes
    registry.update_review_task(task_id, status=REVIEW_STATUS_APPROVED, reviewer_notes=note)
    _append_history(
        registry,
        task_id,
        action="task_approved",
        details={
            "approved_candidate_id": approved.id,
            "edit_count": len(edits),
            "reviewer_notes": note or "",
        },
    )

    stored_corrections = 0
    if translation_memory is not None:
        try:
            stored_corrections = _store_approved_corrections(
                translation_memory=translation_memory,
                candidate=candidate,
                updated_segments=updated_segments,
                edits=edits,
                reviewer_notes=note or "",
            )
        except Exception as exc:
            _append_history(
                registry,
                task_id,
                action="translation_memory_store_failed",
                details={"error": str(exc)},
            )

    output_path_value = None
    if output_srt_path:
        output_path = Path(output_srt_path)
        _write_simple_srt(updated_segments, output_path)
        artifact = registry.store_artifact(
            ArtifactRecord(
                media_hash=task.media_hash,
                artifact_type=ARTIFACT_TYPE_SRT,
                file_path=str(output_path),
                candidate_id=approved.id,
            )
        )
        output_path_value = artifact.file_path

    refreshed = registry.get_review_task(task_id)
    return {
        "task_id": task_id,
        "approved_candidate_id": approved.id,
        "output_srt_path": output_path_value,
        "stored_corrections": stored_corrections,
        "history": list(refreshed.history if refreshed else []),
    }


def list_review_history(registry: ArtifactRegistry, *, task_id: int) -> List[Dict[str, Any]]:
    """Return structured history events for a review task."""
    task = registry.get_review_task(task_id)
    if task is None:
        raise LookupError(f"No review task with id={task_id}")
    return list(task.history)


__all__ = [
    "create_review_task_from_generate_output",
    "create_review_task_from_benchmark_output",
    "list_review_queue",
    "build_review_comparison",
    "render_local_review_ui",
    "approve_review_task",
    "list_review_history",
]
