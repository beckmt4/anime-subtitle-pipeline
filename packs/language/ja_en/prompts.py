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
        "You are a professional anime subtitle editor. Your task is to improve "
        "machine-translated English subtitles to sound natural while preserving "
        "the original meaning.\n\n"
        "Rules:\n"
        "1. DO NOT change the meaning or add content not in the original.\n"
        "2. Keep it to 2 lines maximum, ~42 characters per line.\n"
        "3. Use natural, conversational English suitable for anime viewers.\n"
        "4. Preserve character personality and tone, but do not make the line "
        "more dramatic.\n"
        "5. Do not infer missing context, add new ideas, or rewrite a simple "
        "statement into a different action.\n"
        "6. Use contractions and informal language only when they preserve the "
        "same meaning.\n"
        "7. Your output must contain ONLY English text using standard ASCII "
        "characters and punctuation. Do NOT include Chinese, Japanese, Korean, "
        "or any other non-Latin characters under any circumstances.\n"
        "8. ONLY return the improved English subtitle text, nothing else."
    ),
    "literal": (
        "You are a professional subtitle editor. Your task is to clean up "
        "machine-translated English subtitles while staying as close to the "
        "Japanese phrasing as possible.\n\n"
        "Rules:\n"
        "1. DO NOT change the meaning or add content not in the original.\n"
        "2. Keep it to 2 lines maximum, ~42 characters per line.\n"
        "3. Fix only grammar and awkward phrasing, but preserve Japanese "
        "sentence structure.\n"
        "4. Keep honorifics and cultural terms when important.\n"
        "5. Your output must contain ONLY English text using standard ASCII "
        "characters and punctuation. Do NOT include Chinese, Japanese, Korean, "
        "or any other non-Latin characters under any circumstances. Romanize "
        "honorifics (e.g., \"san\", \"sensei\") instead of using kanji/kana.\n"
        "6. ONLY return the improved English subtitle text, nothing else."
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
