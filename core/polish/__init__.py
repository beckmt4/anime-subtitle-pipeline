"""core.polish — LLM quality improvement backend abstraction.

Improves subtitle quality using a locally-hosted language model.

The abstract ``PolishBackend`` interface allows swapping polish engines
(e.g., Ollama/Qwen, llama.cpp, llm-studio) without touching pipeline logic.

CJK character leak detection and ``_recover_leading_english`` are
**language-pack concerns** (Japanese-output artefacts from qwen2.5:7b).
They belong in ``packs/language/ja_en/cjk_filter.py``, not here.

Public API
----------
PolishBackend                 Abstract base class.
LLMPolisher                   Concrete Ollama implementation
                              (lives in root ``llm_polish.py`` during migration).
polish_candidate_with_llm(…)  One-shot convenience wrapper.
enforce_constraints_on_candidate(…)  Timing / line-length normalisation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from core.subtitles import SubtitleCandidate


class PolishBackend(ABC):
    """Abstract interface for LLM polish engine adapters.

    Style hints (natural vs. literal, honorific handling, domain glossary) are
    supplied as ``style_config`` from the active domain/language pack.  Core
    never embeds style choices directly.
    """

    @abstractmethod
    def polish(
        self,
        candidate: "SubtitleCandidate",
        style_config: Dict[str, Any] | None = None,
    ) -> "SubtitleCandidate":
        """Improve subtitle quality using an LLM.

        Parameters
        ----------
        candidate:
            Input SubtitleCandidate to improve.
        style_config:
            Optional dict of style parameters supplied by the active
            language/domain pack (e.g. ``{"style": "natural"}``).

        Returns
        -------
        SubtitleCandidate
            Improved candidate.  Original timestamps are preserved.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the LLM backend is reachable and ready."""


# Forward-import concrete implementations during migration period.
from llm_polish import (  # noqa: F401, E402
    LLMPolisher,
    polish_candidate_with_llm,
    enforce_constraints_on_candidate,
)

__all__ = [
    "PolishBackend",
    "LLMPolisher",
    "polish_candidate_with_llm",
    "enforce_constraints_on_candidate",
]
