"""core.media — stream inspection and source discovery.

Wraps ffprobe to parse media containers into structured metadata.
All language-code normalization here is protocol-level (ISO-639 mapping)
and must not contain language-pack-specific aliases.
Implementation lives in ``core.media.media_inspect``.
The root-level ``media_inspect.py`` is a re-export shim pointing here.

Public API
----------
inspect_media(path)           → MediaInfo
MediaInfo                     Parsed container info with stream lists.
AudioStream                   Single audio stream descriptor.
SubtitleStream                Single subtitle stream descriptor.
choose_audio_track(media, …)  → int   priority-list-based selection
"""

import subprocess  # noqa: F401 — kept so patch("core.media.subprocess.run") works

from core.media.media_inspect import (  # noqa: F401
    MediaInfo,
    AudioStream,
    SubtitleStream,
    StreamBase,
    inspect_media,
    choose_audio_track,
    LANG_MAP,
    _norm_lang,
)

__all__ = [
    "MediaInfo",
    "AudioStream",
    "SubtitleStream",
    "StreamBase",
    "inspect_media",
    "choose_audio_track",
    "LANG_MAP",
    "_norm_lang",
]
