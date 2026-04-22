"""LLM prompt templates for Japanese → English subtitle polishing.

Two style profiles are defined:

natural
    More localised, conversational English.  Uses contractions and informal
    register.  Preferred for entertainment / anime.

literal
    Closer to Japanese phrasing.  Preserves honorifics and cultural terms.
    Preferred for educational or reference content.

Usage
-----
>>> from packs.language.ja_en.prompts import get_system_prompt
>>> prompt = get_system_prompt("natural")
"""

from __future__ import annotations

from typing import Literal

StyleProfile = Literal["natural", "literal"]

_SYSTEM_PROMPTS: dict[str, str] = {
    "natural": (
        "You are a professional subtitle editor specialising in Japanese anime "
        "and entertainment media. Your task is to improve machine-translated "
        "Japanese→English subtitles so they read naturally in English while "
        "preserving the speaker's meaning and emotional tone.\n\n"
        "Rules:\n"
        "- Use natural, conversational English with contractions where appropriate.\n"
        "- Keep each subtitle to 1–2 lines, max 42 characters per line.\n"
        "- Do NOT translate character names or proper nouns.\n"
        "- Do NOT add or remove content — only improve fluency.\n"
        "- Return ONLY the improved subtitle text, nothing else."
    ),
    "literal": (
        "You are a professional subtitle editor specialising in Japanese anime "
        "and reference media. Your task is to improve machine-translated "
        "Japanese→English subtitles while staying close to the original phrasing.\n\n"
        "Rules:\n"
        "- Preserve Japanese speech patterns where they can be rendered naturally.\n"
        "- Retain honorifics (san, kun, chan, senpai) as-is.\n"
        "- Keep each subtitle to 1–2 lines, max 42 characters per line.\n"
        "- Do NOT add or remove content.\n"
        "- Return ONLY the improved subtitle text, nothing else."
    ),
}

_USER_PROMPT_TEMPLATE: str = (
    "Improve the following subtitle line:\n\n{text}"
)


def get_system_prompt(style: StyleProfile = "natural") -> str:
    """Return the system prompt for the given style profile.

    Parameters
    ----------
    style:
        ``"natural"`` (default) or ``"literal"``.

    Returns
    -------
    str
        System prompt string suitable for the Ollama chat API.
    """
    if style not in _SYSTEM_PROMPTS:
        raise ValueError(
            f"Unknown style profile '{style}'. "
            f"Valid options: {list(_SYSTEM_PROMPTS)}"
        )
    return _SYSTEM_PROMPTS[style]


def get_user_prompt(text: str) -> str:
    """Format the per-segment user prompt.

    Parameters
    ----------
    text:
        Raw (machine-translated) subtitle text for a single segment.

    Returns
    -------
    str
        User prompt string suitable for the Ollama chat API.
    """
    return _USER_PROMPT_TEMPLATE.format(text=text)


__all__ = [
    "StyleProfile",
    "get_system_prompt",
    "get_user_prompt",
]
