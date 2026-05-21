"""JAV filename and media ID parsing helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

_GENERIC_STOPWORDS = frozenset({
    "AAC",
    "AVC",
    "BD",
    "BDrip".upper(),
    "FHD",
    "H264",
    "H265",
    "HEVC",
    "UHD",
    "WEB",
    "WEBDL",
    "X264",
    "X265",
})

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fc2_ppv", re.compile(r"(?<![A-Z0-9])(FC2)[-_ ]?(PPV)[-_ ]?(\d{6,8})(?!\d)", re.IGNORECASE)),
    (
        "caribbean",
        re.compile(r"(?<![A-Z0-9])(CARIB(?:BEANCOM)?)[-_ ]?(\d{6})[-_ ]?(\d{3})(?!\d)", re.IGNORECASE),
    ),
    ("heyzo", re.compile(r"(?<![A-Z0-9])(HEYZO)[-_ ]?(\d{4})(?!\d)", re.IGNORECASE)),
    ("studio_serial", re.compile(r"(?<![A-Z0-9])([A-Z]{2,10})[-_ ]?0*(\d{2,5})(?!\d)", re.IGNORECASE)),
)


def parse_jav_filename(name: str) -> Dict[str, Any]:
    """Parse a representative JAV filename into a canonical media ID."""
    stem = Path(name).stem.upper()
    normalized = re.sub(r"[\[\]\(\)\.]+", " ", stem)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    for family, pattern in _PATTERNS:
        match = pattern.search(normalized)
        if match is None:
            continue
        groups = tuple(part.upper() for part in match.groups())
        if family == "fc2_ppv":
            canonical = f"{groups[0]}-{groups[1]}-{groups[2]}"
        elif family == "caribbean":
            canonical = f"{groups[0]}-{groups[1]}-{groups[2]}"
        elif family == "heyzo":
            canonical = f"{groups[0]}-{groups[1]}"
        else:
            if groups[0] in _GENERIC_STOPWORDS:
                continue
            canonical = f"{groups[0]}-{groups[1]}"
        return {
            "matched": True,
            "canonical_id": canonical,
            "id_family": family,
            "raw_match": match.group(0),
        }

    return {
        "matched": False,
        "canonical_id": None,
        "id_family": None,
        "raw_match": None,
    }


def extract_jav_id(name: str) -> str | None:
    """Extract the canonical JAV media ID from *name* when one is present."""
    parsed = parse_jav_filename(name)
    return parsed["canonical_id"] if parsed["matched"] else None


__all__ = ["extract_jav_id", "parse_jav_filename"]
