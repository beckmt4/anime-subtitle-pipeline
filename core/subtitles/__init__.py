"""core.subtitles — shared data model and SRT formatting.

Authoritative home for ``Segment`` and ``SubtitleCandidate``.
Implementation lives in ``core.subtitles.models``.
The root-level ``models.py`` is a re-export shim pointing here.

Public API
----------
Segment              Language-agnostic timed text unit.
SubtitleCandidate    A complete subtitle track from a single source.
"""

from core.subtitles.models import Segment, SubtitleCandidate  # noqa: F401

__all__ = ["Segment", "SubtitleCandidate"]
