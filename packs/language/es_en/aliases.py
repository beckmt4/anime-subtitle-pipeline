"""Language tag alias normalisation for Spanish → English routing."""

from __future__ import annotations

ES_ALIASES: frozenset[str] = frozenset({
    "es",
    "spa",
    "es-es",
    "es-mx",
    "spanish",
})

EN_ALIASES: frozenset[str] = frozenset({
    "en",
    "eng",
    "en-us",
    "en-gb",
    "english",
})

LANG_ALIASES: dict[str, frozenset[str]] = {
    "es": ES_ALIASES,
    "en": EN_ALIASES,
}


def normalise(raw_tag: str) -> str:
    tag = raw_tag.strip().lower()
    for canonical, aliases in LANG_ALIASES.items():
        if tag in aliases:
            return canonical
    return raw_tag


__all__ = ["ES_ALIASES", "EN_ALIASES", "LANG_ALIASES", "normalise"]
