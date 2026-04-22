"""core.subtitles — shared data model and SRT formatting.

This is the authoritative home for ``Segment`` and ``SubtitleCandidate``.
During the migration period the root-level ``models.py`` re-exports these
symbols for backward compatibility.

Public API
----------
Segment              Language-agnostic timed text unit.
SubtitleCandidate    A complete subtitle track from a single source.
"""

from __future__ import annotations

from models import Segment, SubtitleCandidate  # noqa: F401 — re-export

__all__ = ["Segment", "SubtitleCandidate"]
