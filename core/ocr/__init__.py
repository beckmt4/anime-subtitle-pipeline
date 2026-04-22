"""core.ocr — bitmap subtitle → text.

Converts bitmap subtitle tracks (PGS, VOBSUB, XSUB) to timed text segments.

Status: **not yet implemented**.  ``subtitle_utils.extract_subtitle_track``
currently raises ``RuntimeError`` for bitmap codecs.  That is the correct
stopgap behaviour; it must not be silently swallowed.

Planned public API
------------------
OCRBackend       Abstract base class for OCR engine adapters.
ocr_subtitle_track(path, stream_index, backend) → SubtitleCandidate

Design notes
------------
- The OCR engine must be swappable via the ``OCRBackend`` interface.
- Confidence scores must be surfaced per segment so ``core.policy`` can
  route low-confidence results to ``core.review``.
- Language-specific OCR model selection belongs in language packs, not here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.subtitles import SubtitleCandidate


class OCRBackend(ABC):
    """Abstract base class for bitmap subtitle OCR engines.

    Implementors live in language packs or external plugins, not in ``core``.
    """

    @abstractmethod
    def extract(
        self,
        video_path: str,
        stream_index: int,
        language_hint: str | None = None,
    ) -> "SubtitleCandidate":
        """Convert a bitmap subtitle stream to a SubtitleCandidate.

        Parameters
        ----------
        video_path:
            Absolute path to the source video file.
        stream_index:
            Stream index of the bitmap subtitle track inside the container.
        language_hint:
            Optional ISO-639-1 source language code to guide the OCR model.

        Returns
        -------
        SubtitleCandidate
            Extracted segments with ``meta["ocr_confidence"]`` set per segment.
        """


__all__ = ["OCRBackend"]
