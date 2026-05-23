"""core.translation — pack-aware glossary and terminology enforcement helpers."""

from __future__ import annotations

from core.translation.glossary import (  # noqa: F401
    build_prompt_glossary_block,
    load_active_glossary_data,
    validate_required_term_drift,
)
from core.translation.memory import (  # noqa: F401
    ApprovedCorrectionRecord,
    TranslationMemoryStore,
    build_prompt_memory_block,
)

__all__ = [
    "load_active_glossary_data",
    "build_prompt_glossary_block",
    "validate_required_term_drift",
    "ApprovedCorrectionRecord",
    "TranslationMemoryStore",
    "build_prompt_memory_block",
]
