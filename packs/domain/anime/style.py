"""Anime-specific subtitle style policy.

Defines how the anime domain pack handles:
- Honorifics (san, kun, chan, senpai, sensei, etc.)
- OP/ED (opening/ending) sequence treatment.
- On-screen signs and text overlays.
- Character name handling.

This module is imported by ``core.runtime`` when the active domain pack is
``anime`` and injected into the polish and formatting pipelines as a style
configuration dict.

Usage
-----
>>> from packs.domain.anime.style import get_style_config
>>> cfg = get_style_config()
>>> cfg["preserve_honorifics"]
True
"""

from __future__ import annotations

from typing import Any, Dict

#: Default anime style configuration.
_DEFAULT_STYLE: Dict[str, Any] = {
    # Honorifics: keep Japanese honorifics in the English output.
    "preserve_honorifics": True,
    "honorific_list": [
        "san", "kun", "chan", "sama", "senpai", "sensei",
        "dono", "shi", "hakase",
    ],

    # OP/ED handling: pass through without polishing (lyrics are intentional).
    "skip_op_ed_segments": True,

    # On-screen text: include translated signs as subtitle cues.
    "translate_on_screen_text": True,

    # Character limit per line (anime typically allows slightly shorter lines).
    "max_chars_per_line": 42,
    "max_lines_per_segment": 2,

    # LLM style profile for the ja_en language pack prompts.
    "llm_style": "natural",
}


def get_style_config() -> Dict[str, Any]:
    """Return the default anime domain style configuration dict.

    Returns
    -------
    dict
        Style configuration suitable for injection into ``core.polish`` and
        ``core.subtitles`` formatting utilities.
    """
    return dict(_DEFAULT_STYLE)


__all__ = ["get_style_config"]
