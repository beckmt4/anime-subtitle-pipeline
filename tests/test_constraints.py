"""Unit tests for subtitle constraint enforcement in llm_polish."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.polish import (
    LLMPolisher,
    _CJK_RE,
    _recover_leading_english,
    enforce_constraints_on_candidate,
)
from core.subtitles import Segment, SubtitleCandidate


def make_polisher() -> LLMPolisher:
    cfg = MagicMock()
    cfg.llm_base_url = "http://localhost:11434"
    cfg.llm_model_name = "test-model"
    cfg.llm_style = "natural"
    cfg.llm_timeout = 30
    cfg.llm_max_lines = 2
    cfg.llm_max_chars_per_line = 42
    return LLMPolisher(cfg)


def make_candidate(segs: list) -> SubtitleCandidate:
    return SubtitleCandidate(
        id="test-cand",
        language="en",
        source="mt",
        origin_stream="audio:0",
        segments=[Segment(s, e, t) for s, e, t in segs],
    )


# ---------------------------------------------------------------------------
# LLMPolisher._enforce_constraints
# ---------------------------------------------------------------------------

class TestEnforceConstraints:
    def setup_method(self):
        self.p = make_polisher()

    def test_empty_string_returns_empty(self):
        assert self.p._enforce_constraints("") == ""

    def test_preserves_normal_text(self):
        assert self.p._enforce_constraints("This is fine.") == "This is fine."

    def test_collapses_multiple_spaces(self):
        assert self.p._enforce_constraints("hello   world") == "hello world"

    def test_collapses_newlines_to_single_space(self):
        assert self.p._enforce_constraints("hello\nworld") == "hello world"

    def test_collapses_carriage_return_newline(self):
        assert self.p._enforce_constraints("hello\r\nworld") == "hello world"

    def test_strips_leading_and_trailing_whitespace(self):
        assert self.p._enforce_constraints("  hello  ") == "hello"

    def test_mixed_whitespace_all_collapsed(self):
        result = self.p._enforce_constraints("  hello \n  there \r\n world  ")
        assert result == "hello there world"

    def test_tab_characters_collapsed(self):
        assert self.p._enforce_constraints("hello\tworld") == "hello world"


# ---------------------------------------------------------------------------
# enforce_constraints_on_candidate
# ---------------------------------------------------------------------------

class TestEnforceConstraintsOnCandidate:
    def _make_cfg(self) -> MagicMock:
        cfg = MagicMock()
        cfg.llm_base_url = "http://localhost:11434"
        cfg.llm_model_name = "test-model"
        cfg.llm_style = "natural"
        cfg.llm_timeout = 30
        cfg.llm_max_lines = 2
        cfg.llm_max_chars_per_line = 42
        return cfg

    def test_whitespace_normalized_in_segments(self):
        cand = make_candidate([(0.0, 1.0, "hello  world"), (1.0, 2.0, "fine\ntext")])
        result = enforce_constraints_on_candidate(cand, self._make_cfg())
        assert result.segments[0].text == "hello world"
        assert result.segments[1].text == "fine text"

    def test_returns_new_candidate_with_same_id(self):
        cand = make_candidate([(0.0, 1.0, "hello")])
        result = enforce_constraints_on_candidate(cand, self._make_cfg())
        assert result.id == cand.id

    def test_preserves_timing(self):
        cand = make_candidate([(1.5, 3.2, "test text")])
        result = enforce_constraints_on_candidate(cand, self._make_cfg())
        assert result.segments[0].start == pytest.approx(1.5)
        assert result.segments[0].end == pytest.approx(3.2)

    def test_constraints_enforced_flag_in_meta(self):
        cand = make_candidate([(0.0, 1.0, "text")])
        result = enforce_constraints_on_candidate(cand, self._make_cfg())
        assert result.meta.get("constraints_enforced") is True

    def test_empty_candidate_returns_empty_candidate(self):
        cand = make_candidate([])
        result = enforce_constraints_on_candidate(cand, self._make_cfg())
        assert result.segments == []


# ---------------------------------------------------------------------------
# _CJK_RE regex
# ---------------------------------------------------------------------------

class TestCJKRegex:
    @pytest.mark.parametrize("text", [
        "こんにちは",    # Hiragana
        "カタカナ",      # Katakana
        "漢字",          # CJK Unified Ideographs
        "你好世界",      # Chinese
        "안녕하세요",    # Korean
        "（括弧）",      # Fullwidth brackets
        "，。？！",      # Fullwidth punctuation
    ])
    def test_detects_cjk_characters(self, text):
        assert _CJK_RE.search(text) is not None

    @pytest.mark.parametrize("text", [
        "Hello world!",
        "résumé naïve",      # Latin extended
        "123 + 456",
        "Don't push me.",
        "It's a great day.",
    ])
    def test_does_not_match_latin_or_ascii(self, text):
        assert _CJK_RE.search(text) is None


# ---------------------------------------------------------------------------
# _recover_leading_english
# ---------------------------------------------------------------------------

class TestRecoverLeadingEnglish:
    def test_recovers_english_before_appended_cjk(self):
        # Good English sentence followed by CJK appendage
        text = "You've got to be kidding me. 三次元ならすぐ治る"
        result = _recover_leading_english(text)
        assert result == "You've got to be kidding me."

    def test_returns_none_when_no_cjk(self):
        assert _recover_leading_english("Hello world.") is None

    def test_returns_none_when_prefix_is_single_word(self):
        # "Oh" is only 1 word — below the ≥2 word requirement
        text = "Oh" + "日本語はこれ以降"
        assert _recover_leading_english(text) is None

    def test_returns_none_when_cjk_appears_too_early(self):
        # CJK within the first 40% of the string → interspersed, not appended
        text = "あHello world this is english."
        assert _recover_leading_english(text) is None

    def test_recovers_multi_word_prefix_without_terminal_punctuation(self):
        # ≥4 words without terminal punctuation should still be accepted
        text = "This is a complete thought" + "です。" * 5
        result = _recover_leading_english(text)
        assert result == "This is a complete thought"
