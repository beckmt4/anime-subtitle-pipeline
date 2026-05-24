"""packs.language — language pack sub-packages.

A language pack covers exactly one source→target translation direction.
It supplies:

- Language tag alias normalisation (ISO-639 variants → canonical code).
- LLM prompt templates (system prompt + per-segment prompt skeleton).
- Language-specific post-processing hooks (e.g. CJK leak remediation).
- Model defaults (preferred ASR model, preferred MT model).
- Quality thresholds specific to this language pair.
- Generate-path routing hooks for translation and untagged-audio fallback.

Available packs
---------------
ja_en   Japanese source → English target.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Callable, Mapping

if TYPE_CHECKING:
    from config import Config
    from models import SubtitleCandidate


@dataclass(frozen=True)
class LanguageRoutingHooks:
    """Language-pack routing hooks consumed by generate orchestration."""

    pack_id: str
    source_language: str
    target_language: str
    lang_aliases: Mapping[str, frozenset[str]]
    untagged_audio_fallback_source_language: str
    translate_candidate: Callable[
        ["SubtitleCandidate", "Config", "SubtitleCandidate | None"],
        "SubtitleCandidate",
    ]


def load_language_routing_hooks(
    source_language: str = "ja",
    target_language: str = "en",
) -> LanguageRoutingHooks:
    """Load routing hooks for a language pack.

    The first implementation stays intentionally small: it loads the existing
    pack package, its alias map, and the pack-owned routing module that
    delegates translation and fallback policy decisions.
    """

    pack_name = f"{source_language}_{target_language}"
    try:
        pack_module = import_module(f"packs.language.{pack_name}")
        aliases_module = import_module(f"packs.language.{pack_name}.aliases")
        routing_module = import_module(f"packs.language.{pack_name}.routing")
    except ModuleNotFoundError as exc:
        raise ValueError(
            f"No language-pack routing hooks available for {source_language!r} → {target_language!r}"
        ) from exc

    return LanguageRoutingHooks(
        pack_id=pack_module.PACK_ID,
        source_language=pack_module.SOURCE_LANG,
        target_language=pack_module.TARGET_LANG,
        lang_aliases=aliases_module.LANG_ALIASES,
        untagged_audio_fallback_source_language=(
            routing_module.UNTAGGED_AUDIO_FALLBACK_SOURCE_LANGUAGE
        ),
        translate_candidate=routing_module.translate_candidate,
    )


__all__ = ["LanguageRoutingHooks", "load_language_routing_hooks"]
