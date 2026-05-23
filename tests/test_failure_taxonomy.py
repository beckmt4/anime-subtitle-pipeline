"""Tests for canonical translation failure taxonomy handling."""

from __future__ import annotations

from core.quality import (
    aggregate_failure_codes,
    is_registered_failure_code,
    normalize_failure_code,
)


def test_aliases_normalize_to_canonical_codes() -> None:
    assert normalize_failure_code("possible_added_meaning") == "added_meaning"
    assert normalize_failure_code("non_english_leakage") == "cjk_leakage"
    assert normalize_failure_code("final_literal_entity_drift") == "wrong_meaning"


def test_unknown_codes_fallback_to_needs_human_review() -> None:
    assert not is_registered_failure_code("unknown_code_xyz")
    assert normalize_failure_code("unknown_code_xyz") == "needs_human_review"


def test_aggregate_failure_codes_uses_canonical_keys() -> None:
    summary = aggregate_failure_codes(
        [
            {"code": "possible_added_meaning", "severity": "warning"},
            {"code": "added_meaning", "severity": "warning"},
            {"code": "unknown_code_xyz", "severity": "warning"},
        ]
    )
    assert summary["by_code"]["added_meaning"] == 2
    assert summary["by_code"]["needs_human_review"] == 1
    assert "unknown_code_xyz" not in summary["by_code"]
