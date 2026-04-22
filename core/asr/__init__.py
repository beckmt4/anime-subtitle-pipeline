"""core.asr — speech → text backend abstraction.

Converts a WAV audio file to a timestamped SubtitleCandidate.

The abstract ``ASRBackend`` interface allows the runtime to swap engines
(e.g., Faster-Whisper, whisper.cpp, AssemblyAI) without touching pipeline
logic.  Language-specific segmentation post-processing and vocabulary hints
belong in language packs, not here.

Public API
----------
ASRBackend                            Abstract base class.
FasterWhisperASR                      Concrete Faster-Whisper implementation
                                      (lives in root ``asr.py`` during migration).
build_candidate_from_segments(…)      Helper — wraps raw ASR output.
transcribe_audio_to_candidate(…)      One-shot convenience function.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.subtitles import SubtitleCandidate


class ASRBackend(ABC):
    """Abstract interface for all ASR engine adapters.

    Concrete implementations live in root ``asr.py`` (during migration) or in
    language pack–specific modules.  Core orchestration code must only depend
    on this interface.
    """

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> "SubtitleCandidate":
        """Transcribe audio to a SubtitleCandidate.

        Parameters
        ----------
        audio_path:
            Absolute path to a WAV file (16 kHz, mono recommended).
        language:
            Optional ISO-639-1 hint.  ``None`` means auto-detect.

        Returns
        -------
        SubtitleCandidate
            Transcribed segments.  ``candidate.language`` is set to the
            detected or supplied language code.
        """

    @abstractmethod
    def load(self) -> None:
        """Pre-load model weights into memory."""

    @abstractmethod
    def unload(self) -> None:
        """Release model weights from memory."""


# Forward-import concrete implementation during migration period.
from asr import FasterWhisperASR, build_candidate_from_segments  # noqa: F401, E402

__all__ = [
    "ASRBackend",
    "FasterWhisperASR",
    "build_candidate_from_segments",
]
