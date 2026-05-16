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


def ocr_subtitle_track(
    video_path: str,
    stream_index: int,
    backend: OCRBackend,
    *,
    language_hint: str | None = None,
    low_confidence_threshold: float = 0.70,
) -> SubtitleCandidate:
    """Extract a bitmap subtitle stream via a swappable OCR backend."""
    candidate = backend.extract(video_path, stream_index, language_hint=language_hint)
    if not isinstance(candidate, SubtitleCandidate):
        raise TypeError("OCR backend must return SubtitleCandidate")

    low_confidence_count = 0
    confidence_values: list[float] = []

    for seg in candidate.segments:
        raw = seg.meta.get("ocr_confidence")
        if raw is None:
            raw = candidate.meta.get("ocr_confidence")
        try:
            conf = float(raw)
        except (TypeError, ValueError):
            conf = 0.0
        seg.meta["ocr_confidence"] = conf
        confidence_values.append(conf)
        if conf < low_confidence_threshold:
            low_confidence_count += 1

    seg_count = len(candidate.segments)
    avg_confidence = round(sum(confidence_values) / seg_count, 4) if seg_count else 0.0
    low_ratio = round(low_confidence_count / seg_count, 4) if seg_count else 0.0

    candidate.meta.setdefault("ocr", {})
    candidate.meta["ocr"].update({
        "segment_count": seg_count,
        "low_confidence_threshold": low_confidence_threshold,
        "low_confidence_segment_count": low_confidence_count,
        "low_confidence_ratio": low_ratio,
        "average_confidence": avg_confidence,
    })
    candidate.meta["ocr_average_confidence"] = avg_confidence
    candidate.meta["ocr_low_confidence_segment_count"] = low_confidence_count

    return candidate


__all__ = ["OCRBackend", "ocr_subtitle_track"]
