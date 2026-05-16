"""Tests for the literal-first / natural-second two-pass translation workflow.

Covers:
- Config: translation.workflow and translation.save_intermediate accessors.
- run_two_pass_translation: orchestration order (translator then adaptor).
- adapt_candidate_from_literal: natural pass behaviour, drift revert with QC
  warning, stock-phrase collapse guard, LLM-disabled fallback.
- Timing preservation: segment start/end unchanged from source candidate.
- Metadata wiring: literal_pass_candidate_id, translation_workflow,
  literal_pass_segments (when save_intermediate=True).
"""

from __future__ import annotations

from typing import List
from unittest.mock import MagicMock, call, patch

import pytest

from config import Config
from models import Segment, SubtitleCandidate
from llm_polish import (
    LLMPolisher,
    PolishStats,
    adapt_candidate_from_literal,
)
import mt


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _ja_candidate(texts: List[str], id: str = "asr_ja") -> SubtitleCandidate:
    segs = [Segment(float(i), float(i) + 1.0, t) for i, t in enumerate(texts)]
    return SubtitleCandidate(
        id=id,
        language="ja",
        source="asr",
        origin_stream="audio:0",
        segments=segs,
    )


def _en_candidate(texts: List[str], id: str = "asr_ja_mt") -> SubtitleCandidate:
    segs = [Segment(float(i), float(i) + 1.0, t) for i, t in enumerate(texts)]
    return SubtitleCandidate(
        id=id,
        language="en",
        source="mt",
        origin_stream="audio:0",
        segments=segs,
    )


def _cfg(workflow: str = "single_pass", save_intermediate: bool = False) -> Config:
    cfg = Config()
    cfg._config.setdefault("translation", {})
    cfg._config["translation"].update(
        {
            "engine": "marian",
            "fallback_engine": "marian",
            "context_window_segments": 2,
            "mode": "accuracy_first",
            "dialogue_profile": "default",
            "timeout": 5,
            "workflow": workflow,
            "save_intermediate": save_intermediate,
        }
    )
    cfg._config.setdefault("llm", {})
    cfg._config["llm"].update(
        {
            "enabled": True,
            "base_url": "http://localhost:11434",
            "model_name": "test-model",
            "style": "natural",
            "timeout": 5,
            "temperature": 0.3,
            "top_p": 0.9,
            "max_lines": 2,
            "max_chars_per_line": 42,
            "prompts": {
                "natural": "You are a subtitle polisher.",
                "literal": "You are a literal subtitle cleaner.",
                "natural_from_literal": (
                    "You are adapting a literal translation. "
                    "Max lines: {max_lines}. Max chars: {max_chars_per_line}."
                ),
            },
        }
    )
    return cfg


def _polisher(llm_enabled: bool = True) -> LLMPolisher:
    cfg = _cfg()
    polisher = LLMPolisher(cfg)
    polisher.check_connection = MagicMock(return_value=llm_enabled)
    return polisher


# ---------------------------------------------------------------------------
# Config accessors
# ---------------------------------------------------------------------------


class TestConfigWorkflowAccessors:
    def test_translation_workflow_defaults_to_single_pass(self):
        cfg = Config()
        assert cfg.translation_workflow == "single_pass"

    def test_translation_workflow_reads_from_config(self):
        cfg = _cfg(workflow="literal_then_natural")
        assert cfg.translation_workflow == "literal_then_natural"

    def test_translation_save_intermediate_defaults_to_false(self):
        cfg = Config()
        assert cfg.translation_save_intermediate is False

    def test_translation_save_intermediate_reads_from_config(self):
        cfg = _cfg(save_intermediate=True)
        assert cfg.translation_save_intermediate is True


# ---------------------------------------------------------------------------
# adapt_candidate_from_literal — basic behaviour
# ---------------------------------------------------------------------------


class TestAdaptCandidateFromLiteral:
    def test_adapted_text_replaces_literal_in_segments(self):
        literal = _en_candidate(["He is dead."], id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(return_value="He's dead.")

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.segments[0].text == "He's dead."

    def test_timing_preserved_from_literal_candidate(self):
        literal = _en_candidate(["He is dead."], id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(return_value="He's dead.")

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.segments[0].start == 0.0
        assert result.segments[0].end == 1.0

    def test_output_candidate_id_is_literal_id_plus_natural(self):
        literal = _en_candidate(["text"], id="asr_ja_mt")
        polisher = _polisher()
        polisher.polish_text = MagicMock(return_value="text")

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.id == "asr_ja_mt_natural"

    def test_source_is_two_pass_llm(self):
        literal = _en_candidate(["text"], id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(return_value="text")

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.source == "two_pass_llm"

    def test_meta_records_workflow_and_literal_pass_id(self):
        literal = _en_candidate(["text"], id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(return_value="text")

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.meta["translation_workflow"] == "literal_then_natural"
        assert result.meta["literal_pass_candidate_id"] == "lit"

    def test_adapted_segment_stores_literal_text_in_meta(self):
        literal = _en_candidate(["He is dead."], id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(return_value="He's dead.")

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.segments[0].meta.get("literal_text") == "He is dead."

    def test_adapt_stats_in_meta(self):
        literal = _en_candidate(["He is dead.", "No."], id="lit")
        polisher = _polisher()
        # first call: adapted; second call: unchanged (same as input)
        polisher.polish_text = MagicMock(side_effect=["He's dead.", "No."])

        result = polisher.adapt_candidate_from_literal(literal)

        stats = result.meta["two_pass_adapt_stats"]
        assert stats["total"] == 2
        assert stats["polished"] == 1
        assert stats["unchanged"] == 1
        assert stats["reverted"] == 0

    def test_uses_natural_from_literal_style(self):
        literal = _en_candidate(["text"], id="lit")
        polisher = _polisher()
        captured_styles: List[str] = []

        def capture(text_ja, text_en_raw, style=None, retry_count=2):
            captured_styles.append(style)
            return text_en_raw

        polisher.polish_text = capture

        polisher.adapt_candidate_from_literal(literal)

        assert captured_styles == ["natural_from_literal"]

    def test_ja_candidate_text_forwarded_as_context(self):
        ja = _ja_candidate(["日本語"])
        literal = _en_candidate(["He is dead."], id="lit")
        polisher = _polisher()
        calls_received: List[dict] = []

        def capture(text_ja, text_en_raw, style=None, retry_count=2):
            calls_received.append({"text_ja": text_ja, "text_en_raw": text_en_raw})
            return text_en_raw

        polisher.polish_text = capture
        polisher.adapt_candidate_from_literal(literal, ja_candidate=ja)

        assert calls_received[0]["text_ja"] == "日本語"
        assert calls_received[0]["text_en_raw"] == "He is dead."

    def test_mismatched_ja_candidate_uses_empty_context(self):
        ja = _ja_candidate(["日本語A", "日本語B"])  # 2 segments
        literal = _en_candidate(["text"], id="lit")  # 1 segment
        polisher = _polisher()
        calls_received: List[dict] = []

        def capture(text_ja, text_en_raw, style=None, retry_count=2):
            calls_received.append({"text_ja": text_ja})
            return text_en_raw

        polisher.polish_text = capture
        polisher.adapt_candidate_from_literal(literal, ja_candidate=ja)

        assert calls_received[0]["text_ja"] == ""

    def test_empty_literal_candidate_returns_empty_natural(self):
        literal = SubtitleCandidate(
            id="empty_lit",
            language="en",
            source="mt",
            origin_stream="audio:0",
            segments=[],
        )
        polisher = _polisher()

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.id == "empty_lit_natural"
        assert result.segments == []
        assert result.meta["translation_workflow"] == "literal_then_natural"


# ---------------------------------------------------------------------------
# adapt_candidate_from_literal — drift guard (QC warning)
# ---------------------------------------------------------------------------


class TestAdaptFromLiteralDriftGuard:
    def test_noun_change_reverts_to_literal_with_qc_warning(self):
        """If the natural output drops a proper noun, revert to literal + warn."""
        literal = _en_candidate(["Thank you for coming. I'm Alan Elburn."], id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(return_value="Thanks for coming, Alan.")

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.segments[0].text == "Thank you for coming. I'm Alan Elburn."
        assert "two_pass_qc_warning" in result.segments[0].meta
        assert "drift_reverted_to_literal" in result.segments[0].meta["two_pass_qc_warning"]
        assert result.meta["two_pass_adapt_stats"]["reverted"] == 1

    def test_severe_compression_reverts_to_literal(self):
        """Extreme shortening triggers drift revert."""
        literal_text = "We need to get out of here right now before it is too late for everyone"
        literal = _en_candidate([literal_text], id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(return_value="We run")

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.segments[0].text == literal_text
        assert result.meta["two_pass_adapt_stats"]["reverted"] == 1

    def test_acceptable_naturalisation_is_accepted(self):
        """Minor fluency improvement that passes drift check is accepted."""
        literal = _en_candidate(["I cannot do this alone."], id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(return_value="I can't do this by myself.")

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.segments[0].text == "I can't do this by myself."
        assert result.meta["two_pass_adapt_stats"]["polished"] == 1

    def test_mixed_batch_drift_stats(self):
        """Batch with accepted, reverted, and unchanged segments tallies correctly."""
        raw_texts = [
            "Thank you for coming. I'm Alan Elburn.",  # noun drop → reverted
            "I cannot do this alone.",                  # minor fix → adapted
            "No.",                                       # unchanged
        ]
        adapted_texts = [
            "Thanks for coming, Alan.",      # noun "Elburn" dropped
            "I can't do this by myself.",    # acceptable
            "No.",                           # identical
        ]

        literal = _en_candidate(raw_texts, id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(side_effect=adapted_texts)

        result = polisher.adapt_candidate_from_literal(literal)

        stats = result.meta["two_pass_adapt_stats"]
        assert stats["polished"] == 1
        assert stats["reverted"] == 1
        assert stats["unchanged"] == 1
        assert stats["total"] == 3


# ---------------------------------------------------------------------------
# adapt_candidate_from_literal — stock-phrase collapse guard
# ---------------------------------------------------------------------------


class TestAdaptFromLiteralCollapseGuard:
    def test_collapse_reverts_all_to_literal_with_qc_warning(self):
        raw_texts = [
            "He is standing by the river.",
            "She looks worried.",
            "It is time to go.",
        ]
        literal = _en_candidate(raw_texts, id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(return_value="Sure thing.")

        result = polisher.adapt_candidate_from_literal(literal)

        for orig, seg in zip(raw_texts, result.segments):
            assert seg.text == orig
        assert result.meta.get("two_pass_qc_warning") == "stock_phrase_collapse_reverted_to_literal"
        assert result.meta["two_pass_adapt_stats"]["reverted"] == 3

    def test_no_collapse_when_outputs_differ(self):
        raw_texts = ["He is standing by the river.", "She looks worried."]
        literal = _en_candidate(raw_texts, id="lit")
        polisher = _polisher()
        polisher.polish_text = MagicMock(side_effect=[
            "He stands by the river.",
            "She looks concerned.",
        ])

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.meta.get("two_pass_qc_warning") != "stock_phrase_collapse_reverted_to_literal"


# ---------------------------------------------------------------------------
# adapt_candidate_from_literal — LLM disabled / unreachable fallback
# ---------------------------------------------------------------------------


class TestAdaptFromLiteralLLMFallback:
    def test_llm_disabled_returns_literal_text_unchanged(self):
        literal = _en_candidate(["He is dead.", "It is over."], id="lit")
        polisher = _polisher(llm_enabled=False)

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.segments[0].text == "He is dead."
        assert result.segments[1].text == "It is over."
        assert result.meta.get("fallback") is True
        assert result.meta["translation_workflow"] == "literal_then_natural"

    def test_llm_unreachable_returns_literal_text_unchanged(self):
        literal = _en_candidate(["Hello."], id="lit")
        polisher = _polisher(llm_enabled=True)
        polisher.check_connection = MagicMock(return_value=False)

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.segments[0].text == "Hello."
        assert result.meta.get("fallback") is True

    def test_timing_preserved_in_fallback(self):
        segs = [Segment(1.5, 3.2, "He is dead.")]
        literal = SubtitleCandidate(
            id="lit", language="en", source="mt", origin_stream="a:0", segments=segs
        )
        polisher = _polisher(llm_enabled=False)

        result = polisher.adapt_candidate_from_literal(literal)

        assert result.segments[0].start == 1.5
        assert result.segments[0].end == 3.2


# ---------------------------------------------------------------------------
# adapt_candidate_from_literal convenience wrapper
# ---------------------------------------------------------------------------


class TestAdaptCandidateFromLiteralWrapper:
    def test_wrapper_delegates_to_polisher(self):
        literal = _en_candidate(["text"], id="lit")
        cfg = _cfg()

        with patch("llm_polish.LLMPolisher") as MockPolisher:
            instance = MockPolisher.return_value
            instance.adapt_candidate_from_literal.return_value = literal

            adapt_candidate_from_literal(literal, cfg)

            instance.adapt_candidate_from_literal.assert_called_once()
            args = instance.adapt_candidate_from_literal.call_args
            assert args.args[0] is literal

    def test_wrapper_forwards_ja_candidate(self):
        literal = _en_candidate(["text"], id="lit")
        ja = _ja_candidate(["日本語"])
        cfg = _cfg()

        with patch("llm_polish.LLMPolisher") as MockPolisher:
            instance = MockPolisher.return_value
            instance.adapt_candidate_from_literal.return_value = literal

            adapt_candidate_from_literal(literal, cfg, ja_candidate=ja)

            args = instance.adapt_candidate_from_literal.call_args
            passed_ja = args.kwargs.get("ja_candidate") or (
                args.args[1] if len(args.args) > 1 else None
            )
            assert passed_ja is ja


# ---------------------------------------------------------------------------
# run_two_pass_translation — orchestration order
# ---------------------------------------------------------------------------


class TestRunTwoPassTranslation:
    def test_calls_translate_then_adapt_in_order(self):
        """run_two_pass_translation must call translate_candidate then adapt_candidate_from_literal."""
        ja = _ja_candidate(["日本語A", "日本語B"])
        cfg = _cfg(workflow="literal_then_natural")

        call_order: List[str] = []

        literal_result = _en_candidate(["Literal A.", "Literal B."], id="lit")
        natural_result = _en_candidate(["Natural A.", "Natural B."], id="lit_natural")

        with patch("mt.translate_candidate", return_value=literal_result) as mock_translate, \
             patch("llm_polish.adapt_candidate_from_literal", return_value=natural_result) as mock_adapt:

            mock_translate.side_effect = lambda *a, **kw: (call_order.append("translate"), literal_result)[1]
            mock_adapt.side_effect = lambda *a, **kw: (call_order.append("adapt"), natural_result)[1]

            result = mt.run_two_pass_translation(ja, cfg)

        assert call_order == ["translate", "adapt"], (
            "translate_candidate must be called before adapt_candidate_from_literal"
        )
        assert result is natural_result

    def test_translate_candidate_receives_source_candidate(self):
        ja = _ja_candidate(["日本語"])
        cfg = _cfg(workflow="literal_then_natural")

        literal = _en_candidate(["Literal."], id="lit")
        natural = _en_candidate(["Natural."], id="lit_natural")

        with patch("mt.translate_candidate", return_value=literal) as mock_translate, \
             patch("llm_polish.adapt_candidate_from_literal", return_value=natural):

            mt.run_two_pass_translation(ja, cfg)

        called_candidate = mock_translate.call_args.args[0]
        assert called_candidate is ja

    def test_adapt_receives_literal_result_as_first_arg(self):
        ja = _ja_candidate(["日本語"])
        cfg = _cfg(workflow="literal_then_natural")

        literal = _en_candidate(["Literal."], id="lit")
        natural = _en_candidate(["Natural."], id="lit_natural")

        with patch("mt.translate_candidate", return_value=literal), \
             patch("llm_polish.adapt_candidate_from_literal", return_value=natural) as mock_adapt:

            mt.run_two_pass_translation(ja, cfg)

        passed_literal = mock_adapt.call_args.args[0]
        assert passed_literal is literal

    def test_literal_pass_id_stored_in_final_meta(self):
        ja = _ja_candidate(["日本語"])
        cfg = _cfg(workflow="literal_then_natural")

        literal = _en_candidate(["Literal."], id="asr_ja_mt")
        natural = _en_candidate(["Natural."], id="asr_ja_mt_natural")
        natural.meta = {}

        with patch("mt.translate_candidate", return_value=literal), \
             patch("llm_polish.adapt_candidate_from_literal", return_value=natural):

            result = mt.run_two_pass_translation(ja, cfg)

        assert result.meta["literal_pass_candidate_id"] == "asr_ja_mt"
        assert result.meta["translation_workflow"] == "literal_then_natural"

    def test_literal_pass_marked_as_literal_in_meta(self):
        """translate_candidate result should have translation_pass='literal' set."""
        ja = _ja_candidate(["日本語"])
        cfg = _cfg(workflow="literal_then_natural")

        literal = _en_candidate(["Literal."], id="lit")
        natural = _en_candidate(["Natural."], id="lit_natural")
        natural.meta = {}

        captured_literal: List[SubtitleCandidate] = []

        def capture_adapt(lit_cand, config, ja_candidate=None):
            captured_literal.append(lit_cand)
            return natural

        with patch("mt.translate_candidate", return_value=literal), \
             patch("llm_polish.adapt_candidate_from_literal", side_effect=capture_adapt):

            mt.run_two_pass_translation(ja, cfg)

        assert captured_literal[0].meta.get("translation_pass") == "literal"

    def test_timing_unchanged_from_source_candidate(self):
        """Segment timing in final output must match the source candidate."""
        segs = [Segment(0.5, 2.0, "日本語")]
        ja = SubtitleCandidate(
            id="asr_ja", language="ja", source="asr", origin_stream="a:0", segments=segs
        )
        cfg = _cfg(workflow="literal_then_natural")

        lit_segs = [Segment(0.5, 2.0, "Literal.")]
        literal = SubtitleCandidate(
            id="asr_ja_mt", language="en", source="mt", origin_stream="a:0", segments=lit_segs
        )
        nat_segs = [Segment(0.5, 2.0, "Natural.")]
        natural = SubtitleCandidate(
            id="asr_ja_mt_natural", language="en", source="two_pass_llm",
            origin_stream="a:0", segments=nat_segs, meta={}
        )

        with patch("mt.translate_candidate", return_value=literal), \
             patch("llm_polish.adapt_candidate_from_literal", return_value=natural):

            result = mt.run_two_pass_translation(ja, cfg)

        assert result.segments[0].start == 0.5
        assert result.segments[0].end == 2.0


# ---------------------------------------------------------------------------
# run_two_pass_translation — save_intermediate flag
# ---------------------------------------------------------------------------


class TestRunTwoPassSaveIntermediate:
    def test_literal_segments_stored_when_save_intermediate_true(self):
        ja = _ja_candidate(["日本語"])
        cfg = _cfg(workflow="literal_then_natural", save_intermediate=True)

        literal = _en_candidate(["Literal."], id="lit")
        natural = _en_candidate(["Natural."], id="lit_natural")
        natural.meta = {}

        with patch("mt.translate_candidate", return_value=literal), \
             patch("llm_polish.adapt_candidate_from_literal", return_value=natural):

            result = mt.run_two_pass_translation(ja, cfg)

        assert "literal_pass_segments" in result.meta
        assert result.meta["literal_pass_segments"][0]["text"] == "Literal."

    def test_literal_segments_not_stored_when_save_intermediate_false(self):
        ja = _ja_candidate(["日本語"])
        cfg = _cfg(workflow="literal_then_natural", save_intermediate=False)

        literal = _en_candidate(["Literal."], id="lit")
        natural = _en_candidate(["Natural."], id="lit_natural")
        natural.meta = {}

        with patch("mt.translate_candidate", return_value=literal), \
             patch("llm_polish.adapt_candidate_from_literal", return_value=natural):

            result = mt.run_two_pass_translation(ja, cfg)

        assert "literal_pass_segments" not in result.meta

    def test_literal_segments_preserve_timing(self):
        segs = [Segment(1.0, 2.5, "日本語")]
        ja = SubtitleCandidate(
            id="asr_ja", language="ja", source="asr", origin_stream="a:0", segments=segs
        )
        cfg = _cfg(workflow="literal_then_natural", save_intermediate=True)

        lit_segs = [Segment(1.0, 2.5, "Literal.")]
        literal = SubtitleCandidate(
            id="lit", language="en", source="mt", origin_stream="a:0", segments=lit_segs
        )
        natural = SubtitleCandidate(
            id="lit_natural", language="en", source="two_pass_llm",
            origin_stream="a:0", segments=[], meta={}
        )

        with patch("mt.translate_candidate", return_value=literal), \
             patch("llm_polish.adapt_candidate_from_literal", return_value=natural):

            result = mt.run_two_pass_translation(ja, cfg)

        saved = result.meta["literal_pass_segments"][0]
        assert saved["start"] == 1.0
        assert saved["end"] == 2.5


# ---------------------------------------------------------------------------
# VALID_TRANSLATION_WORKFLOWS constant
# ---------------------------------------------------------------------------


class TestValidTranslationWorkflows:
    def test_constant_contains_expected_values(self):
        assert "single_pass" in mt.VALID_TRANSLATION_WORKFLOWS
        assert "literal_then_natural" in mt.VALID_TRANSLATION_WORKFLOWS
