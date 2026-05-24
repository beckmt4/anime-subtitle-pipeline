"""LLM prompt templates for Chinese → English subtitle polishing."""

from __future__ import annotations

from typing import Literal

StyleProfile = Literal["natural", "literal"]

_SYSTEM_PROMPTS: dict[str, str] = {
    "natural": (
        "You are a professional subtitle editor. Improve machine-translated "
        "English subtitles from Chinese while preserving meaning.\n\n"
        "Rules:\n"
        "1. Do not change meaning or add content.\n"
        "2. Keep output concise and subtitle-ready.\n"
        "3. Return only the improved English subtitle text."
    ),
    "literal": (
        "You are a professional subtitle editor. Clean up machine-translated "
        "English subtitles from Chinese while staying close to source phrasing.\n\n"
        "Rules:\n"
        "1. Do not change meaning or add content.\n"
        "2. Preserve key names and cultural terms.\n"
        "3. Return only the improved English subtitle text."
    ),
}

_USER_PROMPT_TEMPLATE: str = "Improve the following subtitle line:\n\n{text}"


def get_system_prompt(style: StyleProfile = "natural") -> str:
    if style not in _SYSTEM_PROMPTS:
        raise ValueError(f"Unknown style profile '{style}'. Valid options: {list(_SYSTEM_PROMPTS)}")
    return _SYSTEM_PROMPTS[style]


def get_user_prompt(text: str) -> str:
    return _USER_PROMPT_TEMPLATE.format(text=text)


__all__ = ["StyleProfile", "get_system_prompt", "get_user_prompt"]
