"""Core in-memory subtitle data structures.

This unified module defines the generic subtitle containers used for
multi-track / multi-language processing. It replaces earlier duplicated
definitions that could cause import ambiguity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Segment:
    """A language-agnostic subtitle segment."""
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start

    def __repr__(self) -> str:  # compact debugging aid
        preview = self.text[:30] + ("..." if len(self.text) > 30 else "")
        return f"Segment({self.start:.2f}-{self.end:.2f}s '{preview}')"


@dataclass
class SubtitleCandidate:
    """A complete subtitle track candidate from a single source.

    Attributes:
        id: Unique identifier (e.g. 'asr_ja', 'embedded_en_s0').
        language: ISO 639-1 language code (e.g. 'ja', 'en', 'und').
        source: Origin type ('asr', 'embedded', 'mt', 'mt_llm').
        origin_stream: Stream identifier ('audio:1', 'sub:0', filename).
        segments: Collected segments for this candidate.
        meta: Additional metadata such as models/parameters.
    """
    id: str
    language: str
    source: str
    origin_stream: str
    segments: List[Segment] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def add_segment(self, seg: Segment) -> None:
        self.segments.append(seg)

    def __repr__(self) -> str:
        return (
            f"SubtitleCandidate(id='{self.id}', lang='{self.language}', "
            f"source='{self.source}', segments={len(self.segments)})"
        )

    # Primary property names
    @property
    def segment_count(self) -> int:
        return len(self.segments)

    @property
    def total_duration(self) -> float:
        return sum(s.duration for s in self.segments) if self.segments else 0.0

    # Backwards-compatible aliases (legacy expectations in test / older code)
    @property
    def count(self) -> int:  # alias
        return self.segment_count

    @property
    def duration(self) -> float:  # alias
        return self.total_duration


__all__ = ["Segment", "SubtitleCandidate"]
