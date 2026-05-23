"""Canonical translation-failure taxonomy utilities."""

from __future__ import annotations

from .failure_taxonomy import (
    CANONICAL_FAILURE_CODES,
    DEFAULT_FALLBACK_CODE,
    aggregate_failure_codes,
    get_failure_code_definition,
    is_registered_failure_code,
    normalize_failure_code,
    normalize_failure_severity,
)

__all__ = [
    "CANONICAL_FAILURE_CODES",
    "DEFAULT_FALLBACK_CODE",
    "get_failure_code_definition",
    "is_registered_failure_code",
    "normalize_failure_code",
    "normalize_failure_severity",
    "aggregate_failure_codes",
]
