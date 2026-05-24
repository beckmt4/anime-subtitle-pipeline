"""Direct Japanese→English translation using a local Ollama-compatible LLM."""

from __future__ import annotations

from typing import Optional

from config import Config
from core.subtitles import SubtitleCandidate
from core.mt import LLMDirectTranslator


class LLMTranslator(LLMDirectTranslator):
    """Compatibility alias for the direct LLM translation engine."""


def translate_candidate(
    candidate: SubtitleCandidate,
    config: Config,
    *,
    target_language: str = "en",
    baseline_candidate: Optional[SubtitleCandidate] = None,
    engine_name: str = "llm_direct",
) -> SubtitleCandidate:
    """Translate a Japanese subtitle candidate directly with the configured LLM."""
    return LLMDirectTranslator(config).translate_candidate(
        candidate,
        target_language=target_language,
        baseline_candidate=baseline_candidate,
        engine_name=engine_name,
    )


__all__ = ["LLMDirectTranslator", "LLMTranslator", "translate_candidate"]
