"""Export approved correction records to benchmark/training JSONL datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from core.translation.memory import TranslationMemoryStore

SFT_SYSTEM_PROMPT = "You translate Japanese subtitles into natural English subtitles."


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_tags(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    tags = [_normalize_text(item) for item in value if _normalize_text(item)]
    return sorted(dict.fromkeys(tags))


def _normalize_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "source_lang": _normalize_text(record.get("source_lang") or "ja").lower(),
        "target_lang": _normalize_text(record.get("target_lang") or "en").lower(),
        "domain": _normalize_text(record.get("domain")),
        "source_text": _normalize_text(record.get("source_text")),
        "bad_translation": _normalize_text(record.get("bad_translation")),
        "approved_translation": _normalize_text(record.get("approved_translation")),
        "previous_context": _normalize_text(record.get("previous_context")),
        "next_context": _normalize_text(record.get("next_context")),
        "tags": _normalize_tags(record.get("tags")),
        "language_pack": _normalize_text(record.get("language_pack")),
        "notes": _normalize_text(record.get("notes")),
    }


def _iter_valid_records(
    records: Iterable[Mapping[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    valid: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for idx, raw_record in enumerate(records):
        record = _normalize_record(raw_record)
        missing = [
            field
            for field in ("source_text", "approved_translation", "source_lang", "target_lang")
            if not record.get(field)
        ]
        if missing:
            skipped.append({"index": idx, "reason": f"missing_required_fields:{','.join(missing)}"})
            continue
        valid.append(record)
    return valid, skipped


def _write_jsonl(path: str | Path, rows: Iterable[Dict[str, Any]]) -> int:
    output_path = Path(path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            json.dump(row, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            count += 1
    return count


def export_approved_corrections_jsonl(
    records: Iterable[Mapping[str, Any]],
    output_path: str | Path,
) -> Dict[str, Any]:
    """Export normalized approved correction records as JSONL."""
    valid, skipped = _iter_valid_records(records)
    written = _write_jsonl(output_path, valid)
    return {"written": written, "skipped": len(skipped), "skipped_records": skipped}


def export_benchmark_reference_jsonl(
    records: Iterable[Mapping[str, Any]],
    output_path: str | Path,
) -> Dict[str, Any]:
    """Export benchmark-ready reference rows from approved correction records."""
    valid, skipped = _iter_valid_records(records)
    rows = [
        {
            "source_text": record["source_text"],
            "reference_translation": record["approved_translation"],
            "previous_context": record["previous_context"],
            "next_context": record["next_context"],
            "source_lang": record["source_lang"],
            "target_lang": record["target_lang"],
            "domain": record["domain"],
            "tags": record["tags"],
        }
        for record in valid
    ]
    written = _write_jsonl(output_path, rows)
    return {"written": written, "skipped": len(skipped), "skipped_records": skipped}


def export_sft_dataset_jsonl(
    records: Iterable[Mapping[str, Any]],
    output_path: str | Path,
    *,
    system_prompt: str = SFT_SYSTEM_PROMPT,
) -> Dict[str, Any]:
    """Export SFT/message-format JSONL rows from approved correction records."""
    valid, skipped = _iter_valid_records(records)
    rows = []
    for record in valid:
        user_content = (
            f"Context before: {record['previous_context']}\n"
            f"Source: {record['source_text']}\n"
            f"Context after: {record['next_context']}"
        )
        rows.append(
            {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": record["approved_translation"]},
                ],
                "metadata": {
                    "source_lang": record["source_lang"],
                    "target_lang": record["target_lang"],
                    "domain": record["domain"],
                    "tags": record["tags"],
                    "language_pack": record["language_pack"],
                },
            }
        )
    written = _write_jsonl(output_path, rows)
    return {"written": written, "skipped": len(skipped), "skipped_records": skipped}


def export_preference_pairs_jsonl(
    records: Iterable[Mapping[str, Any]],
    output_path: str | Path,
) -> Dict[str, Any]:
    """Export preference pairs from approved correction records with bad outputs."""
    valid, skipped = _iter_valid_records(records)
    rows: List[Dict[str, Any]] = []
    for idx, record in enumerate(valid):
        if not record["bad_translation"]:
            skipped.append({"index": idx, "reason": "missing_required_fields:bad_translation"})
            continue
        rows.append(
            {
                "source_text": record["source_text"],
                "rejected_translation": record["bad_translation"],
                "chosen_translation": record["approved_translation"],
                "reason": "approved human correction preserves meaning better",
                "source_lang": record["source_lang"],
                "target_lang": record["target_lang"],
                "domain": record["domain"],
                "tags": record["tags"],
            }
        )
    written = _write_jsonl(output_path, rows)
    return {"written": written, "skipped": len(skipped), "skipped_records": skipped}


def export_translation_memory_datasets(
    translation_memory: TranslationMemoryStore,
    *,
    approved_output_path: str | Path,
    benchmark_output_path: Optional[str | Path] = None,
    sft_output_path: Optional[str | Path] = None,
    preference_output_path: Optional[str | Path] = None,
    source_lang: Optional[str] = None,
    target_lang: Optional[str] = None,
    domain: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Export one or more JSONL datasets from translation-memory records."""
    records = translation_memory.list_records(
        source_lang=source_lang,
        target_lang=target_lang,
        domain=domain,
    )
    summary = {"approved_corrections": export_approved_corrections_jsonl(records, approved_output_path)}
    if benchmark_output_path:
        summary["benchmark"] = export_benchmark_reference_jsonl(records, benchmark_output_path)
    if sft_output_path:
        summary["sft"] = export_sft_dataset_jsonl(records, sft_output_path)
    if preference_output_path:
        summary["preference_pairs"] = export_preference_pairs_jsonl(records, preference_output_path)
    return summary


__all__ = [
    "SFT_SYSTEM_PROMPT",
    "export_approved_corrections_jsonl",
    "export_benchmark_reference_jsonl",
    "export_sft_dataset_jsonl",
    "export_preference_pairs_jsonl",
    "export_translation_memory_datasets",
]
