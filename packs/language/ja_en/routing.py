"""Generate-path routing hooks for the ``ja_en`` language pack."""

from __future__ import annotations

from config import Config
from core.subtitles import SubtitleCandidate
from core.mt import translate_candidate_jp_to_en_workflow

from . import SOURCE_LANG


UNTAGGED_AUDIO_FALLBACK_SOURCE_LANGUAGE: str = SOURCE_LANG


def translate_candidate(
    candidate: SubtitleCandidate,
    cfg: Config,
    source_candidate: SubtitleCandidate | None = None,
) -> SubtitleCandidate:
    """Translate through the pack-owned ja→en workflow."""

    return translate_candidate_jp_to_en_workflow(
        candidate,
        cfg,
        ja_candidate=source_candidate or candidate,
    )


__all__ = ["UNTAGGED_AUDIO_FALLBACK_SOURCE_LANGUAGE", "translate_candidate"]
