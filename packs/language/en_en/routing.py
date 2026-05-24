"""Generate-path routing hooks for the ``en_en`` language pack."""

from __future__ import annotations

import copy

from core.runtime.config import Config
from core.subtitles import SubtitleCandidate

from . import SOURCE_LANG, TARGET_LANG

UNTAGGED_AUDIO_FALLBACK_SOURCE_LANGUAGE: str = SOURCE_LANG


def translate_candidate(
    candidate: SubtitleCandidate,
    cfg: Config,
    source_candidate: SubtitleCandidate | None = None,
) -> SubtitleCandidate:
    """Transcription-only workflow: no translation; pass English through."""
    _ = cfg
    _ = source_candidate
    passthrough = copy.deepcopy(candidate)
    passthrough.language = TARGET_LANG
    passthrough.id = f"{candidate.id}_transcription_only"
    passthrough.meta.setdefault("translation_workflow", "transcription_only")
    passthrough.meta.setdefault("translation_engine", "none")
    passthrough.meta.setdefault("translation_skipped", True)
    return passthrough


__all__ = ["UNTAGGED_AUDIO_FALLBACK_SOURCE_LANGUAGE", "translate_candidate"]
