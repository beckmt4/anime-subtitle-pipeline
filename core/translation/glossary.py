"""Pack-aware glossary loading, prompt injection, and drift validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import yaml


def _cfg_get(config: Any, *keys: str, default: Any) -> Any:
    getter = getattr(config, "get", None)
    if callable(getter):
        return getter(*keys, default=default)
    return default


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_entries(
    raw_entries: Any,
    *,
    kind: str,
    scope: str,
    required_default: bool,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    if not isinstance(raw_entries, list):
        return entries
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        if not source or not target:
            continue
        required = _to_bool(item.get("required"), default=required_default)
        entries.append(
            {
                "kind": kind,
                "scope": scope,
                "source": source,
                "target": target,
                "required": required,
                "source_norm": source.casefold(),
                "target_norm": target.casefold(),
            }
        )
    return entries


def _merge_with_precedence(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[tuple[str, str], Dict[str, Any]] = {}
    for entry in entries:
        key = (entry["kind"], entry["source_norm"])
        merged[key] = entry
    return list(merged.values())


def _active_language_pack(config: Any) -> str:
    source = str(_cfg_get(config, "asr", "language", default="ja")).strip().lower() or "ja"
    source = source.split("-")[0]
    target = str(_cfg_get(config, "translation", "target_language", default="en")).strip().lower() or "en"
    target = target.split("-")[0]
    pack = f"{source}_{target}"
    pack_dir = _repo_root() / "packs" / "language" / pack
    return pack if pack_dir.exists() else "ja_en"


def _active_domain_pack(config: Any) -> str | None:
    domain_pack = getattr(config, "domain_pack", None)
    if domain_pack:
        return str(domain_pack)
    raw = _cfg_get(config, "domain", "pack", default=None)
    return str(raw) if raw else None


def load_active_glossary_data(config: Any) -> Dict[str, Any]:
    """Load normalized glossary/name/style data for active language/domain packs."""
    root = _repo_root()
    language_pack = _active_language_pack(config)
    domain_pack = _active_domain_pack(config)

    lang_dir = root / "packs" / "language" / language_pack
    domain_dir = root / "packs" / "domain" / domain_pack if domain_pack else None

    lang_glossary = _load_yaml(lang_dir / "glossary.yml")
    lang_names = _load_yaml(lang_dir / "names.yml")
    lang_style = _load_yaml(lang_dir / "style.yml")

    entries: List[Dict[str, Any]] = []
    entries.extend(
        _normalize_entries(lang_glossary.get("terms"), kind="term", scope="language", required_default=False)
    )
    entries.extend(
        _normalize_entries(lang_names.get("names"), kind="name", scope="language", required_default=True)
    )
    entries.extend(
        _normalize_entries(lang_names.get("honorifics"), kind="honorific", scope="language", required_default=True)
    )

    domain_glossary: Dict[str, Any] = {}
    domain_style: Dict[str, Any] = {}
    if domain_dir:
        domain_glossary_path = domain_dir / "glossary.yml"
        if domain_pack == "anime":
            configured_path = _cfg_get(config, "domain", "anime", "glossary_path", default=None)
            if configured_path:
                domain_glossary_path = Path(str(configured_path))
                if not domain_glossary_path.is_absolute():
                    domain_glossary_path = root / domain_glossary_path
        domain_glossary = _load_yaml(domain_glossary_path)
        domain_style = _load_yaml(domain_dir / "style.yml")
        entries.extend(
            _normalize_entries(
                domain_glossary.get("terms"),
                kind="term",
                scope="domain",
                required_default=False,
            )
        )
        entries.extend(
            _normalize_entries(
                domain_glossary.get("names"),
                kind="name",
                scope="domain",
                required_default=True,
            )
        )
        entries.extend(
            _normalize_entries(
                domain_glossary.get("honorifics"),
                kind="honorific",
                scope="domain",
                required_default=True,
            )
        )
        if domain_pack == "anime":
            entries.extend(
                _normalize_entries(
                    _cfg_get(config, "domain", "anime", "glossary_overrides", default=[]),
                    kind="term",
                    scope="domain",
                    required_default=False,
                )
            )

    merged_entries = _merge_with_precedence(entries)
    return {
        "language_pack": language_pack,
        "domain_pack": domain_pack,
        "entries": merged_entries,
        "style": {
            "language": lang_style,
            "domain": domain_style,
        },
    }


def _relevant_entries(source_text: str, glossary_data: Dict[str, Any], max_terms: int) -> List[Dict[str, Any]]:
    if not source_text:
        return []
    entries = glossary_data.get("entries", [])
    if not isinstance(entries, list):
        return []
    matches = [entry for entry in entries if str(entry.get("source", "")) in source_text]
    matches.sort(
        key=lambda e: (
            not bool(e.get("required")),
            {"name": 0, "honorific": 1, "term": 2}.get(str(e.get("kind")), 3),
            -len(str(e.get("source", ""))),
        )
    )
    return matches[:max_terms]


def build_prompt_glossary_block(
    source_text: str,
    glossary_data: Dict[str, Any],
    *,
    max_terms: int = 6,
) -> str:
    """Build a prompt block of relevant glossary/name rules for one source cue."""
    relevant = _relevant_entries(source_text, glossary_data, max_terms=max_terms)
    if not relevant:
        return ""
    lines = ["Glossary enforcement (must follow for this cue):"]
    for entry in relevant:
        required_label = "required" if entry.get("required") else "preferred"
        lines.append(
            f"- {entry['source']} -> {entry['target']} "
            f"({entry.get('kind', 'term')}, {required_label})"
        )
    return "\n".join(lines)


def _target_in_text(target: str, text: str) -> bool:
    if not target or not text:
        return False
    normalized_text = text.casefold()
    normalized_target = target.casefold()
    if re.fullmatch(r"[a-z0-9][a-z0-9 '\-]*", normalized_target):
        pattern = rf"\b{re.escape(normalized_target)}\b"
        return re.search(pattern, normalized_text, flags=re.IGNORECASE) is not None
    return normalized_target in normalized_text


def validate_required_term_drift(
    *,
    source_text: str,
    final_text: str,
    glossary_data: Dict[str, Any],
    literal_text: str = "",
) -> List[Dict[str, Any]]:
    """Return structured warnings when required names/terms drift."""
    findings: List[Dict[str, Any]] = []
    if not final_text:
        return findings
    for entry in _relevant_entries(source_text, glossary_data, max_terms=50):
        if not entry.get("required"):
            continue
        target = str(entry.get("target", "")).strip()
        if not target:
            continue
        if _target_in_text(target, final_text):
            continue
        if literal_text and _target_in_text(target, literal_text) and _target_in_text(target, final_text):
            continue
        kind = str(entry.get("kind", "term"))
        code = "wrong_meaning"
        if kind == "name":
            code = "bad_name"
        elif kind == "honorific":
            code = "bad_honorific"
        findings.append(
            {
                "severity": "warning",
                "code": code,
                "message": (
                    f"Required {kind} missing/changed: expected '{target}' for source '{entry['source']}'"
                ),
                "term_kind": kind,
                "source_term": entry["source"],
                "expected_target": target,
                "pack_scope": entry.get("scope", "language"),
            }
        )
    return findings


__all__ = [
    "build_prompt_glossary_block",
    "load_active_glossary_data",
    "validate_required_term_drift",
]
