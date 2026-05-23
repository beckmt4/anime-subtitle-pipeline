"""Tests for translation engine selection and fallback behavior."""

from __future__ import annotations

import pytest
import requests

from config import Config
from core.translation import TranslationMemoryStore
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


def _term_candidate() -> SubtitleCandidate:
    return SubtitleCandidate(
        id="embedded_ja_terms",
        language="ja",
        source="embedded",
        origin_stream="sub:1",
        segments=[Segment(0.0, 1.0, "太郎は先輩です")],
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
        "preserve_adult_register": False,
        "flag_low_confidence": False,
        "flag_high_risk_content": False,
        "timeout": 5,
        "profiles": {
            "live_action_adult": {
                "engine": "llm_direct",
                "workflow": "literal_then_natural",
                "mode": "accuracy_first",
                "context_window_segments": 6,
                "preserve_adult_register": True,
                "flag_low_confidence": True,
                "flag_high_risk_content": True,
            }
        },
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
    assert translated.source == "llm_translate"
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

    translated = mt.translate_candidate_jp_to_en(_candidate(), _cfg(dialogue_profile="live_action_adult"))

    assert translated.meta["translation_dialogue_profile"] == "live_action_adult"
    assert translated.meta["translation_engine"] == "llm_direct"
    assert translated.meta["context_window_segments"] == 6
    assert translated.meta["translation_flag_low_confidence"] is True
    assert translated.meta["translation_flag_high_risk_content"] is True
    assert "Dialogue profile: live_action_adult" in captured["prompt"]
    lowered_prompt = captured["prompt"].lower()
    assert "do not euphemize or sanitize explicit content" in lowered_prompt
    assert "do not add sexual content that is not present" in lowered_prompt
    assert "[LOW_CONFIDENCE]" in captured["prompt"]
    assert "[REVIEW_HIGH_RISK]" in captured["prompt"]


def test_jav_domain_pack_applies_live_action_profile_defaults(monkeypatch):
    captured = {}

    def fake_generate(self, prompt):
        captured["prompt"] = prompt
        return "direct translation"

    monkeypatch.setattr(mt.LLMDirectTranslator, "_generate_text", fake_generate)

    cfg = _cfg(dialogue_profile="default")
    cfg._config["domain"] = {"pack": "jav", "adult_content_opt_in": True}

    translated = mt.translate_candidate_jp_to_en(_candidate(), cfg)

    assert translated.meta["translation_dialogue_profile"] == "live_action_adult"
    assert translated.meta["translation_engine"] == "llm_direct"
    assert translated.meta["translation_preserve_adult_register"] is True
    assert translated.meta["translation_flag_high_risk_content"] is True
    assert "Dialogue profile: live_action_adult" in captured["prompt"]


def test_llm_direct_prompt_includes_context_and_accepts_only_current_output(monkeypatch):
    prompts = []

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "Translation: focused output\nextra explanation that must be ignored"}

    def fake_post(url, json, timeout):
        prompts.append(json["prompt"])
        return _Response()

    monkeypatch.setattr(mt.requests, "post", fake_post)

    translated = mt.translate_candidate_jp_to_en(_candidate(), _cfg("llm_direct"))

    assert len(prompts) == 2
    assert ">> 1: こんにちは" in prompts[0]
    assert "  2: 世界" in prompts[0]
    assert ">> 2: 世界" in prompts[1]
    assert "  1: こんにちは" in prompts[1]
    assert "Previous accepted English output:\nfocused output" in prompts[1]
    assert translated.segments[0].text == "focused output"
    assert translated.segments[1].text == "focused output"


def test_llm_direct_prompt_injects_relevant_glossary_terms(monkeypatch):
    prompts = []

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "Taro is a senpai."}

    def fake_post(url, json, timeout):
        prompts.append(json["prompt"])
        return _Response()

    monkeypatch.setattr(mt.requests, "post", fake_post)

    cfg = _cfg("llm_direct")
    cfg._config["domain"] = {"pack": "anime"}
    mt.translate_candidate_jp_to_en(_term_candidate(), cfg)

    assert len(prompts) == 1
    assert "Glossary enforcement (must follow for this cue):" in prompts[0]
    assert "太郎 -> Taro" in prompts[0]
    assert "先輩 -> senpai" in prompts[0]


def test_llm_direct_prompt_injects_approved_translation_memory(monkeypatch, tmp_path):
    prompts = []
    memory_path = tmp_path / "translation_memory.jsonl"
    TranslationMemoryStore(memory_path).add(
        {
            "source_lang": "ja",
            "target_lang": "en",
            "domain": "anime",
            "source_text": "太郎は先輩です",
            "bad_translation": "He is my upperclassman.",
            "approved_translation": "Taro is a senpai.",
            "language_pack": "ja_en",
            "tags": ["name_error"],
        }
    )

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "Taro is a senpai."}

    def fake_post(url, json, timeout):
        prompts.append(json["prompt"])
        return _Response()

    monkeypatch.setattr(mt.requests, "post", fake_post)

    cfg = _cfg("llm_direct")
    cfg._config["domain"] = {"pack": "anime"}
    cfg._config["translation"]["memory"] = {"enabled": True, "path": str(memory_path), "max_matches": 3}
    mt.translate_candidate_jp_to_en(_term_candidate(), cfg)

    assert len(prompts) == 1
    assert "Approved translation memory (reuse when applicable):" in prompts[0]
    assert "Source: 太郎は先輩です" in prompts[0]
    assert "Approved: Taro is a senpai." in prompts[0]
    assert "Avoid: He is my upperclassman." in prompts[0]


def test_llm_direct_timeout_falls_back_to_marian(monkeypatch):
    monkeypatch.setattr(
        mt.MarianTranslator,
        "translate_batch",
        lambda self, texts: [f"fallback:{text}" for text in texts],
    )
    monkeypatch.setattr(
        mt.requests,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout()),
    )

    translated = mt.translate_candidate_jp_to_en(_candidate(), _cfg("llm_direct"))

    assert translated.meta["translation_fallback"] is True
    assert "failed after" in translated.meta["fallback_reason"]
    assert translated.segments[0].text == "fallback:こんにちは"


def test_llm_direct_empty_response_falls_back_to_marian(monkeypatch):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "   "}

    monkeypatch.setattr(
        mt.MarianTranslator,
        "translate_batch",
        lambda self, texts: [f"fallback:{text}" for text in texts],
    )
    monkeypatch.setattr(mt.requests, "post", lambda *args, **kwargs: _Response())

    translated = mt.translate_candidate_jp_to_en(_candidate(), _cfg("llm_direct"))

    assert translated.meta["translation_fallback"] is True
    assert "empty response" in translated.meta["fallback_reason"]
    assert translated.segments[0].text == "fallback:こんにちは"


def test_llm_direct_malformed_response_falls_back_to_marian(monkeypatch):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"unexpected": "shape"}

    monkeypatch.setattr(
        mt.MarianTranslator,
        "translate_batch",
        lambda self, texts: [f"fallback:{text}" for text in texts],
    )
    monkeypatch.setattr(mt.requests, "post", lambda *args, **kwargs: _Response())

    translated = mt.translate_candidate_jp_to_en(_candidate(), _cfg("llm_direct"))

    assert translated.meta["translation_fallback"] is True
    assert "malformed response payload" in translated.meta["fallback_reason"]
    assert translated.segments[0].text == "fallback:こんにちは"


def test_llm_direct_non_english_response_falls_back_to_marian(monkeypatch):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "日本語のままです"}

    monkeypatch.setattr(
        mt.MarianTranslator,
        "translate_batch",
        lambda self, texts: [f"fallback:{text}" for text in texts],
    )
    monkeypatch.setattr(mt.requests, "post", lambda *args, **kwargs: _Response())

    translated = mt.translate_candidate_jp_to_en(_candidate(), _cfg("llm_direct"))

    assert translated.meta["translation_fallback"] is True
    assert "non-English output" in translated.meta["fallback_reason"]
    assert translated.segments[0].text == "fallback:こんにちは"
