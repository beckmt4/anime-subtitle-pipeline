"""Language tag alias normalisation for English transcription-only routing."""

from __future__ import annotations

EN_ALIASES: frozenset[str] = frozenset({
    "en",
    "eng",
    "en-us",
    "en-gb",
    "english",
})

LANG_ALIASES: dict[str, frozenset[str]] = {
    "en": EN_ALIASES,
}


def normalise(raw_tag: str) -> str:
    tag = raw_tag.strip().lower()
    for canonical, aliases in LANG_ALIASES.items():
        if tag in aliases:
            return canonical
    return raw_tag


__all__ = ["EN_ALIASES", "LANG_ALIASES", "normalise"]
