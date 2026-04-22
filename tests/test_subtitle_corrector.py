"""Unit tests for subtitle_corrector drift detection logic."""

import json
import os

import pytest

from subtitle_corrector import _extract_nouns, check_drift


# ---------------------------------------------------------------------------
# _extract_nouns
# ---------------------------------------------------------------------------

class TestExtractNouns:
    def test_capitalized_words(self):
        result = _extract_nouns("Shinji opened the door")
        assert "Shinji" in result

    def test_quoted_terms(self):
        result = _extract_nouns('he held the "Spear of Longinus"')
        assert "Spear of Longinus" in result

    def test_mixed(self):
        result = _extract_nouns('Rei used the "Lance" to fight')
        assert "Rei" in result
        assert "Lance" in result

    def test_empty_input(self):
        assert _extract_nouns("") == set()

    def test_no_nouns(self):
        result = _extract_nouns("this is all lowercase text")
        assert result == set()

    def test_single_char_capitals_excluded(self):
        # regex requires 2+ chars
        result = _extract_nouns("I went to A place")
        assert "I" not in result
        assert "A" not in result

    def test_single_quotes(self):
        result = _extract_nouns("the 'Eva Unit' activated")
        assert "Eva Unit" in result

    def test_returns_set(self):
        result = _extract_nouns("Tokyo Tokyo Tokyo")
        assert isinstance(result, set)
        assert result == {"Tokyo"}


# ---------------------------------------------------------------------------
# check_drift — identical input
# ---------------------------------------------------------------------------

class TestCheckDriftIdentical:
    def test_no_drift_on_identical(self):
        is_drift, reason, detail = check_drift("Hello world", "Hello world")
        assert is_drift is False
        assert reason == ""
        assert detail == ""


# ---------------------------------------------------------------------------
# check_drift — noun change detection
# ---------------------------------------------------------------------------

class TestCheckDriftNounChange:
    def test_noun_missing_from_corrected(self):
        is_drift, reason, detail = check_drift(
            "Shinji got into the Eva",
            "he got into the robot",
        )
        assert is_drift is True
        assert reason == "noun_change"
        assert detail in ("Shinji", "Eva")

    def test_noun_preserved_no_drift(self):
        is_drift, reason, detail = check_drift(
            "Shinji got into the Eva",
            "Shinji climbed into the Eva",
        )
        assert is_drift is False

    def test_noun_check_before_length(self):
        # also triggers length ratio — but noun check must fire first
        raw = "Rei activated Unit Zero"
        llm = "she turned on the robot unit and it powered up and started the sequence"
        is_drift, reason, detail = check_drift(raw, llm)
        assert is_drift is True
        assert reason == "noun_change"

    def test_quoted_term_missing_from_corrected(self):
        is_drift, reason, detail = check_drift(
            'he pulled out the "Progressive Knife"',
            "he pulled out the knife",
        )
        assert is_drift is True
        assert reason == "noun_change"
        # detail will be whichever extracted noun is missing first (set order);
        # "Progressive" and "Knife" are both extracted as capitalized words too
        assert detail in ("Progressive", "Knife", "Progressive Knife")

    def test_quoted_term_preserved(self):
        is_drift, reason, detail = check_drift(
            'she used the "AT Field" to block it',
            'she deployed the "AT Field" to block the attack',
        )
        assert is_drift is False


# ---------------------------------------------------------------------------
# check_drift — length ratio
# ---------------------------------------------------------------------------

class TestCheckDriftLengthRatio:
    def test_too_long(self):
        # llm adds many words — ratio > 1.4
        # Use a raw whose sentence-initial capital ("Go") IS present in llm so noun check passes
        raw = "Go now"
        llm = "Go right now before it is too late and everything falls apart completely"
        is_drift, reason, detail = check_drift(raw, llm)
        assert is_drift is True
        assert reason == "length_ratio"
        ratio = float(detail)
        assert ratio > 1.4

    def test_too_short(self):
        # llm drops most words — ratio < 0.6
        # "We" is preserved in both sides so noun check passes; ratio then fires
        raw = "We need to get out of here right now before it is too late for everyone"
        llm = "We run"
        is_drift, reason, detail = check_drift(raw, llm)
        assert is_drift is True
        assert reason == "length_ratio"
        ratio = float(detail)
        assert ratio < 0.6

    def test_within_acceptable_range(self):
        raw = "I cannot do this alone"
        llm = "I cannot do this by myself"
        is_drift, reason, detail = check_drift(raw, llm)
        assert is_drift is False

    def test_zero_word_raw_skips_length_check(self):
        # raw has no words — divide-by-zero guard; no noun, no length check possible
        is_drift, reason, detail = check_drift("", "something added")
        assert is_drift is False
