"""Language tag alias normalisation for Korean → English routing."""

from __future__ import annotations

KO_ALIASES: frozenset[str] = frozenset({
    "ko",
    "kor",
    "ko-kr",
    "korean",
})

EN_ALIASES: frozenset[str] = frozenset({
    "en",
    "eng",
    "en-us",
    "en-gb",
    "english",
})

LANG_ALIASES: dict[str, frozenset[str]] = {
    "ko": KO_ALIASES,
    "en": EN_ALIASES,
}


def normalise(raw_tag: str) -> str:
    tag = raw_tag.strip().lower()
    for canonical, aliases in LANG_ALIASES.items():
        if tag in aliases:
            return canonical
    return raw_tag


__all__ = ["KO_ALIASES", "EN_ALIASES", "LANG_ALIASES", "normalise"]
