"""core.media — stream inspection and source discovery.

Wraps ffprobe to parse media containers into structured metadata.
All language-code normalization here is protocol-level (ISO-639 mapping)
and must not contain language-pack-specific aliases.

Public API (target — populated as files migrate from root)
----------------------------------------------------------
inspect_media(path)          → MediaInfo
MediaInfo                    Parsed container info with stream lists.
AudioStream                  Single audio stream descriptor.
SubtitleStream               Single subtitle stream descriptor.
choose_audio_track(media, …) → int | None   (priority-list-based selection)

During the migration period the root-level ``media_inspect.py`` owns the
implementation.  Import from there until the migration is complete.
"""

from __future__ import annotations

# Forward-import from root module during migration period.
from media_inspect import (  # noqa: F401 — re-export
    MediaInfo,
    AudioStream,
    SubtitleStream,
    inspect_media,
    choose_audio_track,
)

__all__ = [
    "MediaInfo",
    "AudioStream",
    "SubtitleStream",
    "inspect_media",
    "choose_audio_track",
]
