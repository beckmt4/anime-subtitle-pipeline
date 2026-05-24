"""Language tag alias normalisation for Chinese → English routing."""

from __future__ import annotations

ZH_ALIASES: frozenset[str] = frozenset({
    "zh",
    "zho",
    "chi",
    "zh-cn",
    "zh-tw",
    "chinese",
    "cmn",
})

EN_ALIASES: frozenset[str] = frozenset({
    "en",
    "eng",
    "en-us",
    "en-gb",
    "english",
})

LANG_ALIASES: dict[str, frozenset[str]] = {
    "zh": ZH_ALIASES,
    "en": EN_ALIASES,
}


def normalise(raw_tag: str) -> str:
    tag = raw_tag.strip().lower()
    for canonical, aliases in LANG_ALIASES.items():
        if tag in aliases:
            return canonical
    return raw_tag


__all__ = ["ZH_ALIASES", "EN_ALIASES", "LANG_ALIASES", "normalise"]
