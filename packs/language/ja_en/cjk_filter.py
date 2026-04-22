"""CJK character leak detection and recovery for Japanese → English output.

When qwen2.5:7b (or similar models) polish Japanese→English subtitles, the
output occasionally starts with residual CJK characters before the English
text begins.  This is a model-specific artefact of the Japanese source language
and does NOT belong in ``core/polish``.

This module provides pure-Python utilities to detect and remediate such leaks.
It is intended to be used as a post-processor hook injected into the polish
pipeline by the ``ja_en`` language pack.

Usage
-----
>>> from packs.language.ja_en.cjk_filter import recover_leading_english
>>> recover_leading_english("こんにちはHello there")
'Hello there'
>>> recover_leading_english("Hello there")
'Hello there'
"""

from __future__ import annotations

import re

#: Matches any CJK Unified Ideograph, Hiragana, Katakana, or CJK punctuation.
_CJK_RE: re.Pattern[str] = re.compile(
    r"[\u3000-\u303f"    # CJK symbols and punctuation
    r"\u3040-\u309f"    # Hiragana
    r"\u30a0-\u30ff"    # Katakana
    r"\u4e00-\u9fff"    # CJK Unified Ideographs (common)
    r"\uff00-\uffef]+"  # Halfwidth and Fullwidth Forms
)


def has_cjk_leak(text: str) -> bool:
    """Return True if *text* contains any CJK characters.

    Parameters
    ----------
    text:
        The subtitle text to inspect.

    Returns
    -------
    bool
        ``True`` when at least one CJK character is present.
    """
    return bool(_CJK_RE.search(text))


def recover_leading_english(text: str) -> str:
    """Strip leading CJK characters and return the first English portion.

    If the text begins with CJK characters followed by English text, the CJK
    prefix is stripped.  If no English portion can be found, the original text
    is returned unchanged so downstream code is never handed an empty string.

    Parameters
    ----------
    text:
        Raw LLM output that may start with CJK characters.

    Returns
    -------
    str
        Cleaned text with leading CJK characters removed.
    """
    cleaned = _CJK_RE.sub("", text).strip()
    return cleaned if cleaned else text


def filter_candidate_cjk(segments_text: list[str]) -> list[str]:
    """Apply CJK leak recovery to a list of segment texts.

    Parameters
    ----------
    segments_text:
        List of raw subtitle strings (one per segment).

    Returns
    -------
    list[str]
        Cleaned strings in the same order.
    """
    return [recover_leading_english(t) if has_cjk_leak(t) else t
            for t in segments_text]


__all__ = [
    "has_cjk_leak",
    "recover_leading_english",
    "filter_candidate_cjk",
]
