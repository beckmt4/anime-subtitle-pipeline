"""Language tag alias normalisation for Japanese container tags.

Container files use a wide range of tag variants to denote Japanese audio or
subtitle streams.  This module maps all known variants to the canonical
ISO-639-1 code ``"ja"`` so that core stream-selection logic can work with a
single, normalised value.

This is a language-pack concern because the alias set changes when support for
a new language is added.  It must not live in ``core/media``.

Usage
-----
>>> from packs.language.ja_en.aliases import normalise
>>> normalise("jpn")
'ja'
>>> normalise("ja-jp")
'ja'
>>> normalise("unknown")
'unknown'
"""

from __future__ import annotations

#: All known container-level tag variants that represent Japanese.
JA_ALIASES: frozenset[str] = frozenset({
    "ja",
    "jpn",
    "jp",
    "ja-jp",
    "japanese",
})

#: All known container-level tag variants that represent English (target lang).
EN_ALIASES: frozenset[str] = frozenset({
    "en",
    "eng",
    "en-us",
    "en-gb",
    "english",
})

#: Complete alias map for this language pack (source + target).
LANG_ALIASES: dict[str, frozenset[str]] = {
    "ja": JA_ALIASES,
    "en": EN_ALIASES,
}


def normalise(raw_tag: str) -> str:
    """Return the canonical ISO-639-1 code for *raw_tag*, or *raw_tag* if
    no alias matches.

    Parameters
    ----------
    raw_tag:
        Raw language tag as found in the media container.

    Returns
    -------
    str
        Canonical ISO-639-1 code (``"ja"``, ``"en"``) or the original tag
        unchanged.
    """
    tag = raw_tag.strip().lower()
    for canonical, aliases in LANG_ALIASES.items():
        if tag in aliases:
            return canonical
    return raw_tag


__all__ = ["JA_ALIASES", "EN_ALIASES", "LANG_ALIASES", "normalise"]
