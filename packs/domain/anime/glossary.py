"""Anime domain glossary helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml


def load_glossary_terms(
    glossary_path: str | Path | None = None,
    overrides: List[Dict[str, str]] | None = None,
) -> List[Dict[str, str]]:
    """Load anime glossary terms from YAML and append optional overrides."""
    path = Path(glossary_path) if glossary_path else Path(__file__).with_name("glossary.yaml")
    data: Dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    terms: List[Dict[str, str]] = []
    for item in data.get("terms", []):
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        if source and target:
            terms.append({"source": source, "target": target})
    for item in overrides or []:
        source = str(item.get("source", "")).strip()
        target = str(item.get("target", "")).strip()
        if source and target:
            terms.append({"source": source, "target": target})
    return terms


__all__ = ["load_glossary_terms"]
