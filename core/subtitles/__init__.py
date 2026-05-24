"""core.subtitles — shared data model and SRT formatting."""

from core.subtitles.models import Segment, SubtitleCandidate  # noqa: F401
from core.subtitles.srt_writer import (  # noqa: F401
    SRTWriter,
    format_timestamp_srt,
    write_candidate_srt,
    read_srt_file,
)

__all__ = [
    "Segment",
    "SubtitleCandidate",
    "SRTWriter",
    "format_timestamp_srt",
    "write_candidate_srt",
    "read_srt_file",
]
