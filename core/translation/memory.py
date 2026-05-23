"""Local translation memory for approved subtitle corrections."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ApprovedCorrectionRecord:
    """One approved correction entry stored in local translation memory."""

    source_lang: str
    target_lang: str
    domain: Optional[str]
    source_text: str
    bad_translation: str
    approved_translation: str
    previous_context: str = ""
    next_context: str = ""
    speaker: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    language_pack: Optional[str] = None
    created_at: Optional[str] = None


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_tags(raw_tags: Any) -> List[str]:
    if not isinstance(raw_tags, list):
        return []
    tags = [_normalize_text(tag) for tag in raw_tags if _normalize_text(tag)]
    return sorted(dict.fromkeys(tags))


def _record_from_payload(payload: Dict[str, Any]) -> ApprovedCorrectionRecord:
    return ApprovedCorrectionRecord(
        source_lang=_normalize_text(payload.get("source_lang") or "ja").lower(),
        target_lang=_normalize_text(payload.get("target_lang") or "en").lower(),
        domain=_normalize_text(payload.get("domain")) or None,
        source_text=_normalize_text(payload.get("source_text")),
        bad_translation=_normalize_text(payload.get("bad_translation")),
        approved_translation=_normalize_text(payload.get("approved_translation")),
        previous_context=_normalize_text(payload.get("previous_context")),
        next_context=_normalize_text(payload.get("next_context")),
        speaker=_normalize_text(payload.get("speaker")) or None,
        tags=_normalize_tags(payload.get("tags")),
        notes=_normalize_text(payload.get("notes")),
        language_pack=_normalize_text(payload.get("language_pack")) or None,
        created_at=_normalize_text(payload.get("created_at")) or None,
    )


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return set()
    if len(normalized) <= n:
        return {normalized}
    return {normalized[i : i + n] for i in range(0, len(normalized) - n + 1)}


def _source_similarity(query_source: str, memory_source: str) -> float:
    query = _normalize_text(query_source)
    memory = _normalize_text(memory_source)
    if not query or not memory:
        return 0.0
    if query == memory:
        return 1.0
    if memory in query or query in memory:
        short = min(len(query), len(memory))
        long = max(len(query), len(memory))
        return short / long
    q_grams = _char_ngrams(query)
    m_grams = _char_ngrams(memory)
    if not q_grams or not m_grams:
        return 0.0
    overlap = q_grams & m_grams
    union = q_grams | m_grams
    if not union:
        return 0.0
    return len(overlap) / len(union)


class TranslationMemoryStore:
    """JSONL-backed local store for approved subtitle corrections."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _read_records(self) -> List[ApprovedCorrectionRecord]:
        records: List[ApprovedCorrectionRecord] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                records.append(_record_from_payload(payload))
        return records

    @staticmethod
    def _serialize_record(record: ApprovedCorrectionRecord) -> Dict[str, Any]:
        return asdict(record)

    def add(self, payload: ApprovedCorrectionRecord | Dict[str, Any]) -> ApprovedCorrectionRecord:
        """Add one approved correction record to local JSONL storage."""
        if isinstance(payload, ApprovedCorrectionRecord):
            record = _record_from_payload(asdict(payload))
        else:
            record = _record_from_payload(payload)
        if not record.source_text or not record.approved_translation:
            raise ValueError("source_text and approved_translation are required")
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(self._serialize_record(record), handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
        return record

    def query(
        self,
        *,
        source_text: str,
        source_lang: str = "ja",
        target_lang: str = "en",
        domain: Optional[str] = None,
        language_pack: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Query relevant memory entries by source text with optional filters."""
        query_source = _normalize_text(source_text)
        if not query_source:
            return []
        q_source_lang = _normalize_text(source_lang).lower() or "ja"
        q_target_lang = _normalize_text(target_lang).lower() or "en"
        q_domain = _normalize_text(domain) or None
        q_language_pack = _normalize_text(language_pack) or None
        scored: List[tuple[float, int, Dict[str, Any]]] = []
        for idx, record in enumerate(self._read_records()):
            if record.source_lang != q_source_lang or record.target_lang != q_target_lang:
                continue
            if q_domain is not None and record.domain != q_domain:
                continue
            if q_language_pack is not None and record.language_pack != q_language_pack:
                continue
            score = _source_similarity(query_source, record.source_text)
            if score <= 0:
                continue
            scored.append((score, idx, self._serialize_record(record)))
        scored.sort(
            key=lambda item: (
                -item[0],
                -(item[2]["source_text"] == query_source),
                item[1],
            )
        )
        return [payload for _, _, payload in scored[: max(0, int(limit))]]

    def export_jsonl(
        self,
        output_path: str | Path,
        *,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> int:
        """Export records as JSONL, optionally filtered by language/domain."""
        out_path = Path(output_path).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        filters = {
            "source_lang": _normalize_text(source_lang).lower() if source_lang else None,
            "target_lang": _normalize_text(target_lang).lower() if target_lang else None,
            "domain": _normalize_text(domain) if domain else None,
        }
        count = 0
        with out_path.open("w", encoding="utf-8") as handle:
            for record in self._read_records():
                if filters["source_lang"] and record.source_lang != filters["source_lang"]:
                    continue
                if filters["target_lang"] and record.target_lang != filters["target_lang"]:
                    continue
                if filters["domain"] and record.domain != filters["domain"]:
                    continue
                json.dump(self._serialize_record(record), handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                count += 1
        return count

    def list_records(
        self,
        *,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return serialized records, optionally filtered by language/domain."""
        filters = {
            "source_lang": _normalize_text(source_lang).lower() if source_lang else None,
            "target_lang": _normalize_text(target_lang).lower() if target_lang else None,
            "domain": _normalize_text(domain) if domain else None,
        }
        records: List[Dict[str, Any]] = []
        for record in self._read_records():
            if filters["source_lang"] and record.source_lang != filters["source_lang"]:
                continue
            if filters["target_lang"] and record.target_lang != filters["target_lang"]:
                continue
            if filters["domain"] and record.domain != filters["domain"]:
                continue
            records.append(self._serialize_record(record))
        return records


def build_prompt_memory_block(memory_entries: List[Dict[str, Any]], *, max_entries: int = 3) -> str:
    """Build deterministic prompt block from queried approved correction entries."""
    if not memory_entries:
        return ""
    lines = ["Approved translation memory (reuse when applicable):"]
    for entry in memory_entries[: max(0, int(max_entries))]:
        source = _normalize_text(entry.get("source_text"))
        approved = _normalize_text(entry.get("approved_translation"))
        bad = _normalize_text(entry.get("bad_translation"))
        if not source or not approved:
            continue
        lines.append(f"- Source: {source}")
        lines.append(f"  Approved: {approved}")
        if bad:
            lines.append(f"  Avoid: {bad}")
    return "\n".join(lines)


__all__ = [
    "ApprovedCorrectionRecord",
    "TranslationMemoryStore",
    "build_prompt_memory_block",
]
