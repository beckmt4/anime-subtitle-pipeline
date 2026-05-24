"""Generate-path routing hooks for the ``es_en`` language pack."""

from __future__ import annotations

import logging

from core.mt import VALID_TRANSLATION_WORKFLOWS, run_two_pass_translation, translate_candidate as _translate_candidate
from core.runtime.config import Config
from core.subtitles import SubtitleCandidate

from . import SOURCE_LANG, TARGET_LANG

logger = logging.getLogger(__name__)

UNTAGGED_AUDIO_FALLBACK_SOURCE_LANGUAGE: str = SOURCE_LANG


def translate_candidate(
    candidate: SubtitleCandidate,
    cfg: Config,
    source_candidate: SubtitleCandidate | None = None,
) -> SubtitleCandidate:
    """Translate through the pack-owned ES→EN workflow selector."""
    workflow = str(cfg.get("translation", "workflow", default="single_pass")).strip().lower()
    if workflow not in VALID_TRANSLATION_WORKFLOWS:
        logger.warning(
            "Unknown translation.workflow=%r; expected one of %s. Falling back to single_pass.",
            workflow,
            ", ".join(sorted(VALID_TRANSLATION_WORKFLOWS)),
        )
        workflow = "single_pass"

    if workflow == "literal_then_natural":
        return run_two_pass_translation(
            candidate,
            cfg,
            ja_candidate=source_candidate or candidate,
            target_language=TARGET_LANG,
        )

    translated = _translate_candidate(candidate, cfg, target_language=TARGET_LANG)
    translated.meta.setdefault("translation_workflow", "single_pass")
    return translated


__all__ = ["UNTAGGED_AUDIO_FALLBACK_SOURCE_LANGUAGE", "translate_candidate"]
