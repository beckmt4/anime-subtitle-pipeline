"""packs.language.ja_en — Japanese source → English target language pack.

This pack supplies all Japanese-specific and ja→en translation-specific
logic that must not live in ``core``.

Modules
-------
aliases     Language tag alias normalisation for Japanese container tags.
prompts     LLM prompt templates for natural and literal ja→en polish.
cjk_filter  CJK character leak detection and recovery (qwen2.5 artefact).

Pack metadata
-------------
SOURCE_LANG = "ja"
TARGET_LANG = "en"
"""

from __future__ import annotations

SOURCE_LANG: str = "ja"
TARGET_LANG: str = "en"

PACK_ID: str = f"{SOURCE_LANG}_{TARGET_LANG}"

__all__ = ["SOURCE_LANG", "TARGET_LANG", "PACK_ID"]
