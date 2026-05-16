"""Tests for translation engine selection and fallback behavior."""

from __future__ import annotations

import pytest

from config import Config
from models import Segment, SubtitleCandidate
import mt


def _candidate() -> SubtitleCandidate:
    return SubtitleCandidate(
        id="embedded_ja_s1",
        language="ja",
        source="embedded",
        origin_stream="sub:1",
        segments=[
            Segment(0.0, 1.0, "こんにちは"),
            Segment(1.0, 2.0, "世界"),
        ],
        meta={},
    )


def _cfg(engine: str = "marian", dialogue_profile: str = "default") -> Config:
    cfg = Config()
    cfg._config.setdefault("translation", {})
    cfg._config["translation"].update({
        "engine": engine,
        "fallback_engine": "marian",
        "context_window_segments": 2,
        "mode": "accuracy_first",
        "dialogue_profile": dialogue_profile,
        "timeout": 5,
    })
    cfg._config.setdefault("llm", {})
    cfg._config["llm"]["enabled"] = True
    return cfg


def test_marian_engine_records_selector_metadata(monkeypatch):
    monkeypatch.setattr(
        mt.MarianTranslator,
        "translate_batch",
        lambda self, texts: [f"marian:{text}" for text in texts],
    )

    translated = mt.translate_candidate_jp_to_en(_candidate(), _cfg("marian"))

    assert translated.id == "embedded_ja_s1_mt"
    assert translated.meta["translation_engine"] == "marian"
    assert translated.meta["translation_model"] == "Helsinki-NLP/opus-mt-ja-en"
    assert translated.meta["translation_mode"] == "accuracy_first"
    assert translated.meta["translation_dialogue_profile"] == "default"
    assert translated.meta["translation_fallback"] is False
    assert translated.segments[0].text == "marian:こんにちは"


def test_llm_direct_engine_records_metadata(monkeypatch):
    monkeypatch.setattr(
        mt.LLMDirectTranslator,
        "_generate_text",
        lambda self, prompt: "direct translation",
    )

    translated = mt.translate_candidate_jp_to_en(_candidate(), _cfg("llm_direct"))

    assert translated.id == "embedded_ja_s1_llm_direct"
    assert translated.meta["translation_engine"] == "llm_direct"
    assert translated.meta["translation_model"]
    assert translated.meta["translation_dialogue_profile"] == "default"
    assert translated.meta["context_window_segments"] == 2
    assert translated.segments[0].text == "direct translation"


def test_llm_direct_falls_back_to_marian_with_explicit_metadata(monkeypatch):
    def fail_generate(self, prompt):
        raise RuntimeError("ollama unavailable")

    monkeypatch.setattr(mt.LLMDirectTranslator, "_generate_text", fail_generate)
    monkeypatch.setattr(
        mt.MarianTranslator,
        "translate_batch",
        lambda self, texts: [f"fallback:{text}" for text in texts],
    )

    translated = mt.translate_candidate_jp_to_en(_candidate(), _cfg("llm_direct"))

    assert translated.meta["translation_engine"] == "marian"
    assert translated.meta["translation_fallback"] is True
    assert translated.meta["failed_translation_engine"] == "llm_direct"
    assert translated.meta["fallback_engine"] == "marian"
    assert "ollama unavailable" in translated.meta["fallback_reason"]
    assert translated.segments[0].text == "fallback:こんにちは"


def test_hybrid_engine_uses_marian_baseline_and_llm_output(monkeypatch):
    monkeypatch.setattr(
        mt.MarianTranslator,
        "translate_batch",
        lambda self, texts: [f"baseline:{text}" for text in texts],
    )
    monkeypatch.setattr(
        mt.LLMDirectTranslator,
        "_generate_text",
        lambda self, prompt: "hybrid translation",
    )

    translated = mt.translate_candidate_jp_to_en(_candidate(), _cfg("hybrid"))

    assert translated.id == "embedded_ja_s1_hybrid"
    assert translated.meta["translation_engine"] == "hybrid"
    assert translated.meta["translation_dialogue_profile"] == "default"
    assert translated.meta["baseline_engine"] == "marian"
    assert translated.meta["baseline_model"] == "Helsinki-NLP/opus-mt-ja-en"
    assert translated.segments[0].text == "hybrid translation"


def test_invalid_translation_engine_fails_clearly():
    with pytest.raises(mt.InvalidTranslationEngineError, match="Invalid translation engine"):
        mt.translate_candidate_jp_to_en(_candidate(), _cfg("nonsense"))


def test_live_action_adult_profile_updates_prompt_and_metadata(monkeypatch):
    captured = {}

    def fake_generate(self, prompt):
        captured["prompt"] = prompt
        return "direct translation"

    monkeypatch.setattr(mt.LLMDirectTranslator, "_generate_text", fake_generate)

    translated = mt.translate_candidate_jp_to_en(
        _candidate(),
        _cfg("llm_direct", dialogue_profile="live_action_adult"),
    )

    assert translated.meta["translation_dialogue_profile"] == "live_action_adult"
    assert "Dialogue profile: live_action_adult" in captured["prompt"]
    assert "do not euphemize or sanitize direct content" in captured["prompt"]
