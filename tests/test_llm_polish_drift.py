"""Regression tests for llm_polish drift detection and stock-phrase collapse guard.

Issue: beckmt4/anime-subtitle-pipeline — bug: llm_polish can collapse unrelated
lines into stock phrases and semantic drift because candidate polish lacks
source-context validation.

These tests cover:
- Stock-phrase collapse guard (_is_stock_phrase_collapse)
- PolishStats named tuple
- Per-segment drift detection inside polish_candidate() / polish_segments()
- Source-context (ja_candidate) wiring through polish_candidate()
- Named-term preservation (Alan Elburn, Mizmelis, etc.)
- Raw MT survives when polish is worse (drift reverted)
"""

from __future__ import annotations

from typing import List
from unittest.mock import MagicMock, patch

import pytest

from models import Segment as GenericSegment, SubtitleCandidate
from llm_polish import (
    LLMPolisher,
    PolishStats,
    _is_stock_phrase_collapse,
    polish_candidate_with_llm,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidate(texts: List[str], id: str = "mt_en") -> SubtitleCandidate:
    """Build a synthetic English MT candidate from a list of text strings."""
    segments = [
        GenericSegment(start=float(i), end=float(i) + 1.0, text=t)
        for i, t in enumerate(texts)
    ]
    return SubtitleCandidate(
        id=id,
        language="en",
        source="mt",
        origin_stream="sub:0",
        segments=segments,
    )


def _make_ja_candidate(texts: List[str], id: str = "asr_ja") -> SubtitleCandidate:
    """Build a synthetic Japanese ASR candidate from a list of text strings."""
    segments = [
        GenericSegment(start=float(i), end=float(i) + 1.0, text=t)
        for i, t in enumerate(texts)
    ]
    return SubtitleCandidate(
        id=id,
        language="ja",
        source="asr",
        origin_stream="audio:0",
        segments=segments,
    )


def _make_config(llm_enabled: bool = True) -> MagicMock:
    """Minimal config mock sufficient for LLMPolisher construction."""
    cfg = MagicMock()
    cfg.llm_enabled = llm_enabled
    cfg.llm_base_url = "http://localhost:11434"
    cfg.llm_model_name = "test-model"
    cfg.llm_style = "natural"
    cfg.llm_timeout = 30
    cfg.llm_temperature = 0.3
    cfg.get.return_value = 0.9
    cfg.get_llm_prompt.return_value = "You are a subtitle polisher."
    return cfg


# ---------------------------------------------------------------------------
# _is_stock_phrase_collapse
# ---------------------------------------------------------------------------

class TestIsStockPhraseCollapse:
    def test_collapse_detected_sure_thing(self):
        raw = [
            "I'll give you the right address.",
            "(Laughter)",
            "No.",
            "Let's drink a little more.",
        ]
        polished = ["Sure thing."] * 4
        assert _is_stock_phrase_collapse(raw, polished) is True

    def test_collapse_detected_got_it(self):
        raw = [
            "What happened to the sudden arrival of Tokyo?",
            "There's a turtle at the university.",
        ]
        polished = ["Got it."] * 2
        assert _is_stock_phrase_collapse(raw, polished) is True

    def test_no_collapse_when_outputs_differ(self):
        raw = ["Hello there.", "How are you?"]
        polished = ["Hello there!", "How are you doing?"]
        assert _is_stock_phrase_collapse(raw, polished) is False

    def test_no_collapse_when_raw_also_same(self):
        """If raw lines are identical too, it is not a collapse — the LLM was consistent."""
        raw = ["Sure thing.", "Sure thing."]
        polished = ["Sure thing.", "Sure thing."]
        assert _is_stock_phrase_collapse(raw, polished) is False

    def test_no_collapse_single_segment(self):
        """Single-segment batch cannot be a collapse."""
        raw = ["I need a coffee."]
        polished = ["Sure thing."]
        assert _is_stock_phrase_collapse(raw, polished) is False

    def test_no_collapse_unknown_output(self):
        """Outputs that are all identical but not in the stock-phrase list are not flagged."""
        raw = ["Hello world.", "Goodbye world."]
        polished = ["Totally original line that is not a stock phrase."] * 2
        assert _is_stock_phrase_collapse(raw, polished) is False

    def test_case_insensitive(self):
        """Collapse detection is case-insensitive."""
        raw = ["Something different.", "Something else."]
        polished = ["SURE THING.", "SURE THING."]
        assert _is_stock_phrase_collapse(raw, polished) is True


# ---------------------------------------------------------------------------
# PolishStats
# ---------------------------------------------------------------------------

class TestPolishStats:
    def test_named_tuple_fields(self):
        stats = PolishStats(total=10, polished=6, reverted=2, unchanged=2)
        assert stats.total == 10
        assert stats.polished == 6
        assert stats.reverted == 2
        assert stats.unchanged == 2

    def test_asdict(self):
        stats = PolishStats(total=5, polished=3, reverted=1, unchanged=1)
        d = stats._asdict()
        assert d == {"total": 5, "polished": 3, "reverted": 1, "unchanged": 1}


# ---------------------------------------------------------------------------
# polish_candidate — drift revert
# ---------------------------------------------------------------------------

class TestPolishCandidateDriftRevert:
    """Verify that per-segment drift detection reverts bad polished outputs."""

    def _polisher_with_mock_polish_text(self, return_values: List[str]) -> LLMPolisher:
        """Return a polisher whose polish_text cycles through return_values."""
        cfg = _make_config(llm_enabled=True)
        polisher = LLMPolisher(cfg)
        polisher.check_connection = MagicMock(return_value=True)
        # side_effect iterates over the list
        polisher.polish_text = MagicMock(side_effect=return_values)
        return polisher

    def test_noun_change_reverts_to_raw(self):
        """If polished text drops a proper noun, segment reverts to raw MT."""
        raw_text = "Thank you for coming. I'm Alan Elburn."
        polished_text = "Thanks for coming, Alan."  # drops "Elburn"

        polisher = self._polisher_with_mock_polish_text([polished_text])
        candidate = _make_candidate([raw_text])

        result = polisher.polish_candidate(candidate)

        assert result.segments[0].text == raw_text, (
            "Segment with noun change should revert to raw MT"
        )
        assert result.meta["polish_stats"]["reverted"] == 1

    def test_accepted_polish_improves_fluency(self):
        """Polished text that passes drift check is accepted."""
        raw_text = "I cannot do this alone."
        polished_text = "I can't do this by myself."  # no noun change, length OK

        polisher = self._polisher_with_mock_polish_text([polished_text])
        candidate = _make_candidate([raw_text])

        result = polisher.polish_candidate(candidate)

        assert result.segments[0].text == polished_text
        assert result.meta["polish_stats"]["polished"] == 1
        assert result.meta["polish_stats"]["reverted"] == 0

    def test_length_ratio_too_short_reverts(self):
        """Severe word-count compression triggers drift revert."""
        raw_text = "We need to get out of here right now before it is too late for everyone"
        polished_text = "We run"

        polisher = self._polisher_with_mock_polish_text([polished_text])
        candidate = _make_candidate([raw_text])

        result = polisher.polish_candidate(candidate)

        assert result.segments[0].text == raw_text
        assert result.meta["polish_stats"]["reverted"] == 1

    def test_unchanged_segment_counted(self):
        """When LLM returns the same text, segment is counted as unchanged."""
        raw_text = "No."
        polisher = self._polisher_with_mock_polish_text([raw_text])
        candidate = _make_candidate([raw_text])

        result = polisher.polish_candidate(candidate)

        assert result.segments[0].text == raw_text
        assert result.meta["polish_stats"]["unchanged"] == 1
        assert result.meta["polish_stats"]["polished"] == 0

    def test_mixed_batch_stats(self):
        """A batch with accepted, reverted, and unchanged segments tallies correctly."""
        raw_texts = [
            "Thank you for coming. I'm Alan Elburn.",  # → noun-drop → reverted
            "I cannot do this alone.",                  # → minor fluency fix → polished
            "No.",                                       # → unchanged
        ]
        polished_texts = [
            "Thanks for coming, Alan.",                  # noun "Elburn" dropped
            "I can't do this by myself.",               # acceptable
            "No.",                                       # identical
        ]

        polisher = self._polisher_with_mock_polish_text(polished_texts)
        candidate = _make_candidate(raw_texts)

        result = polisher.polish_candidate(candidate)

        stats = result.meta["polish_stats"]
        assert stats["polished"] == 1
        assert stats["reverted"] == 1
        assert stats["unchanged"] == 1
        assert stats["total"] == 3


# ---------------------------------------------------------------------------
# polish_candidate — stock-phrase collapse guard
# ---------------------------------------------------------------------------

class TestPolishCandidateCollapseGuard:
    def _polisher_with_collapse(self, polished_phrase: str, n: int) -> LLMPolisher:
        cfg = _make_config(llm_enabled=True)
        polisher = LLMPolisher(cfg)
        polisher.check_connection = MagicMock(return_value=True)
        polisher.polish_text = MagicMock(return_value=polished_phrase)
        return polisher

    def test_sure_thing_collapse_reverts_all(self):
        """All segments that collapse to 'Sure thing.' must revert to raw MT."""
        raw_texts = [
            "I'll give you the right address.",
            "(Laughter)",
            "No.",
            "Let's drink a little more.",
        ]
        polisher = self._polisher_with_collapse("Sure thing.", len(raw_texts))
        candidate = _make_candidate(raw_texts)

        result = polisher.polish_candidate(candidate)

        for raw, seg in zip(raw_texts, result.segments):
            assert seg.text == raw, (
                f"Collapsed segment should revert to raw: expected {raw!r}, got {seg.text!r}"
            )
        assert result.meta["polish_stats"]["reverted"] == len(raw_texts)

    def test_got_it_collapse_reverts_all(self):
        raw_texts = [
            "What happened to the sudden arrival of Tokyo?",
            "There's a turtle at the university.",
            "I'm not worried about turtles.",
        ]
        polisher = self._polisher_with_collapse("Got it.", len(raw_texts))
        candidate = _make_candidate(raw_texts)

        result = polisher.polish_candidate(candidate)

        for raw, seg in zip(raw_texts, result.segments):
            assert seg.text == raw
        assert result.meta["polish_stats"]["reverted"] == len(raw_texts)


# ---------------------------------------------------------------------------
# polish_candidate — ja_candidate source context wiring
# ---------------------------------------------------------------------------

class TestPolishCandidateSourceContext:
    def test_ja_candidate_text_passed_to_polish_text(self):
        """When ja_candidate is provided, polish_text receives the Japanese text."""
        ja_texts = ["こんにちは", "ありがとう"]
        en_texts = ["Hello.", "Thank you."]

        cfg = _make_config(llm_enabled=True)
        polisher = LLMPolisher(cfg)
        polisher.check_connection = MagicMock(return_value=True)

        calls_received: List[dict] = []

        def capture_polish_text(text_ja, text_en_raw, style=None, retry_count=2):
            calls_received.append({"text_ja": text_ja, "text_en_raw": text_en_raw})
            return text_en_raw  # passthrough

        polisher.polish_text = capture_polish_text

        ja_cand = _make_ja_candidate(ja_texts)
        en_cand = _make_candidate(en_texts)

        polisher.polish_candidate(en_cand, ja_candidate=ja_cand)

        for i, (ja, en) in enumerate(zip(ja_texts, en_texts)):
            assert calls_received[i]["text_ja"] == ja, (
                f"Expected Japanese text {ja!r} at position {i}, "
                f"got {calls_received[i]['text_ja']!r}"
            )
            assert calls_received[i]["text_en_raw"] == en

    def test_mismatched_ja_candidate_falls_back_to_empty(self):
        """When segment counts differ, Japanese context is silently dropped."""
        ja_texts = ["日本語A"]         # 1 segment
        en_texts = ["English A.", "English B."]  # 2 segments

        cfg = _make_config(llm_enabled=True)
        polisher = LLMPolisher(cfg)
        polisher.check_connection = MagicMock(return_value=True)

        calls_received: List[dict] = []

        def capture_polish_text(text_ja, text_en_raw, style=None, retry_count=2):
            calls_received.append({"text_ja": text_ja, "text_en_raw": text_en_raw})
            return text_en_raw

        polisher.polish_text = capture_polish_text

        ja_cand = _make_ja_candidate(ja_texts)
        en_cand = _make_candidate(en_texts)

        polisher.polish_candidate(en_cand, ja_candidate=ja_cand)

        for call in calls_received:
            assert call["text_ja"] == "", (
                "Mismatched ja_candidate should fall back to empty Japanese text"
            )

    def test_no_ja_candidate_uses_empty_context(self):
        """When no ja_candidate is provided, text_ja defaults to empty string."""
        en_texts = ["Hello.", "Goodbye."]

        cfg = _make_config(llm_enabled=True)
        polisher = LLMPolisher(cfg)
        polisher.check_connection = MagicMock(return_value=True)

        calls_received: List[dict] = []

        def capture_polish_text(text_ja, text_en_raw, style=None, retry_count=2):
            calls_received.append({"text_ja": text_ja})
            return text_en_raw

        polisher.polish_text = capture_polish_text

        en_cand = _make_candidate(en_texts)
        polisher.polish_candidate(en_cand)  # no ja_candidate

        for call in calls_received:
            assert call["text_ja"] == ""


# ---------------------------------------------------------------------------
# polish_candidate_with_llm convenience wrapper
# ---------------------------------------------------------------------------

class TestPolishCandidateWithLlm:
    def test_ja_candidate_forwarded(self):
        """polish_candidate_with_llm passes ja_candidate through to LLMPolisher."""
        en_texts = ["Raw English."]
        ja_texts = ["日本語"]

        en_cand = _make_candidate(en_texts)
        ja_cand = _make_ja_candidate(ja_texts)

        cfg = _make_config(llm_enabled=True)

        with patch("llm_polish.LLMPolisher") as MockPolisher:
            instance = MockPolisher.return_value
            instance.polish_candidate.return_value = en_cand

            polish_candidate_with_llm(en_cand, cfg, ja_candidate=ja_cand)

            call_kwargs = instance.polish_candidate.call_args
            assert call_kwargs.kwargs.get("ja_candidate") is ja_cand or (
                len(call_kwargs.args) >= 2 and call_kwargs.args[1] is ja_cand
            ), "ja_candidate should be forwarded to LLMPolisher.polish_candidate"

    def test_no_ja_candidate_defaults_to_none(self):
        """Calling polish_candidate_with_llm without ja_candidate passes None."""
        en_texts = ["Raw English."]
        en_cand = _make_candidate(en_texts)
        cfg = _make_config(llm_enabled=True)

        with patch("llm_polish.LLMPolisher") as MockPolisher:
            instance = MockPolisher.return_value
            instance.polish_candidate.return_value = en_cand

            polish_candidate_with_llm(en_cand, cfg)

            call_kwargs = instance.polish_candidate.call_args
            # ja_candidate should be None or absent (defaults to None)
            ja_arg = call_kwargs.kwargs.get("ja_candidate")
            if ja_arg is not None and len(call_kwargs.args) >= 2:
                ja_arg = call_kwargs.args[1]
            assert ja_arg is None


# ---------------------------------------------------------------------------
# Named-term preservation regression
# ---------------------------------------------------------------------------

class TestNamedTermPreservation:
    """Regression cases from Vampire Hunter D - Bloodlust output review."""

    def _reverts(self, raw: str, polished: str) -> bool:
        """Return True if the polisher would revert this segment."""
        from subtitle_corrector import check_drift
        is_drift, _, _ = check_drift(raw, polished)
        return is_drift

    def test_alan_elburn_name_dropped(self):
        """'Alan Elburn' must not be replaced by 'Alan'."""
        raw = "Thank you for coming. I'm Alan Elburn."
        polished = "Thanks for coming, Alan."
        assert self._reverts(raw, polished), (
            "Dropping 'Elburn' is a noun change and must trigger drift revert"
        )

    def test_mizmelis_term_preserved(self):
        """Unknown term 'Mizmelis' must not be silently altered."""
        raw = "Mizmelis."
        polished = "Mizmélis."
        # The accented version no longer contains the exact "Mizmelis" substring.
        assert self._reverts(raw, polished), (
            "Mutating 'Mizmelis' to 'Mizmélis' is a noun change and must trigger drift revert"
        )

    def test_dallas_currency_normalized(self):
        """'Dallas' as a fantasy currency must not be silently rewritten to 'dollars'."""
        raw = "That's half a million Dallas reserves."
        polished = "That's half a million dollars in reserve."
        assert self._reverts(raw, polished), (
            "Replacing 'Dallas' with 'dollars' is a noun change and must trigger drift revert"
        )
