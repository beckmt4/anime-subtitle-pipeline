"""core.extract — audio extraction, subtitle demux and mux.

Wraps ffmpeg for:
- WAV extraction from a video container.
- Text subtitle demux (SRT/ASS/SSA) into SubtitleCandidate.
- SRT mux back into a video container.
- Bitmap subtitle detection (routes to core.ocr when implemented).

Public API (target — populated as files migrate from root)
----------------------------------------------------------
extract_audio_with_ffmpeg(path, …) → str    WAV output path
extract_subtitle_track(path, …)    → SubtitleCandidate
mux_subtitle_to_video(video, srt)  → str    output video path

During the migration period the root-level ``audio_utils.py`` and
``subtitle_utils.py`` own the implementation.  Import from there until the
migration is complete.
"""

from __future__ import annotations

from audio_utils import extract_audio_with_ffmpeg  # noqa: F401 — re-export
from subtitle_utils import extract_subtitle_track  # noqa: F401 — re-export

__all__ = [
    "extract_audio_with_ffmpeg",
    "extract_subtitle_track",
]
