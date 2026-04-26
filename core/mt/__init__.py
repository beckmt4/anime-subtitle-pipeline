"""core.mt — machine translation backend abstraction.

Translates a SubtitleCandidate from one language to another.

The abstract ``MTBackend`` interface allows the runtime to swap translation
engines (e.g., MarianMT, DeepL-local, NLLB) without touching pipeline logic.
The source→target language pair is supplied by the caller (language pack or
runtime config); it is never hardcoded here.

Public API
----------
MTBackend                     Abstract base class.
MarianTranslator              Concrete MarianMT implementation
LLMDirectTranslator           Ollama-compatible direct translation backend
                              (both live in root ``mt.py`` during migration).
translate_candidate(…)        Direction-agnostic translation helper.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.subtitles import SubtitleCandidate


class MTBackend(ABC):
    """Abstract interface for all machine translation engine adapters.

    Language direction (source_lang → target_lang) is supplied as parameters,
    never inferred from hardcoded assumptions.
    """

    @abstractmethod
    def translate(
        self,
        candidate: "SubtitleCandidate",
        source_lang: str,
        target_lang: str,
    ) -> "SubtitleCandidate":
        """Translate all segments in *candidate* from source to target language.

        Parameters
        ----------
        candidate:
            Input SubtitleCandidate whose ``segments`` hold the source text.
        source_lang:
            ISO-639-1 code for the source language (e.g. ``"ja"``).
        target_lang:
            ISO-639-1 code for the target language (e.g. ``"en"``).

        Returns
        -------
        SubtitleCandidate
            New candidate with translated segment text.  Original timestamps
            are preserved.  ``candidate.language`` is set to *target_lang*.
        """

    @abstractmethod
    def load(self) -> None:
        """Pre-load model weights into memory."""

    @abstractmethod
    def unload(self) -> None:
        """Release model weights from memory."""


# Forward-import concrete implementation during migration period.
from mt import LLMDirectTranslator, MarianTranslator, translate_candidate  # noqa: F401, E402

__all__ = [
    "LLMDirectTranslator",
    "MTBackend",
    "MarianTranslator",
    "translate_candidate",
]
