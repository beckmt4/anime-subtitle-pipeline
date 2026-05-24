"""llm_polish — re-exported from core.polish."""

from core.polish import (  # noqa: F401
    LLMPolisher,
    PolishStats,
    _CJK_RE,
    _is_stock_phrase_collapse,
    _recover_leading_english,
    adapt_candidate_from_literal,
    polish_candidate_with_llm,
    enforce_constraints_on_candidate,
)

__all__ = [
    "LLMPolisher",
    "PolishStats",
    "_CJK_RE",
    "_is_stock_phrase_collapse",
    "_recover_leading_english",
    "adapt_candidate_from_literal",
    "polish_candidate_with_llm",
    "enforce_constraints_on_candidate",
]
