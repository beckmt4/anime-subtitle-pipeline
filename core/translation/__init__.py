"""core.translation — pack-aware glossary and terminology enforcement helpers."""

from __future__ import annotations

from core.translation.glossary import (  # noqa: F401
    build_prompt_glossary_block,
    load_active_glossary_data,
    validate_required_term_drift,
)

__all__ = [
    "load_active_glossary_data",
    "build_prompt_glossary_block",
    "validate_required_term_drift",
]
