"""Coverage for first non-Japanese language pack expansions."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from core.subtitles import Segment, SubtitleCandidate


class _DummyConfig:
    def __init__(self, workflow: str = "single_pass"):
        self._workflow = workflow

    def get(self, *keys, default=None):
        if keys == ("translation", "workflow"):
            return self._workflow
        return default


@pytest.mark.parametrize(
    "pack_id,source,target",
    [
        ("ko_en", "ko", "en"),
        ("zh_en", "zh", "en"),
        ("es_en", "es", "en"),
        ("en_en", "en", "en"),
    ],
)
def test_new_language_pack_hooks_load(pack_id, source, target):
    from packs.language import load_language_routing_hooks

    hooks = load_language_routing_hooks(source, target)

    assert hooks.pack_id == pack_id
    assert hooks.source_language == source
    assert hooks.target_language == target
    assert hooks.untagged_audio_fallback_source_language == source
    assert source in hooks.lang_aliases
    assert callable(hooks.translate_candidate)


def test_language_registry_includes_new_packs():
    from packs.language import list_available_packs

    packs = list_available_packs()

    for pack_id in ["ko_en", "zh_en", "es_en", "en_en"]:
        assert pack_id in packs


@pytest.mark.parametrize("pack_module", ["ko_en", "zh_en", "es_en"])
def test_non_japanese_routing_single_pass_delegates_to_core_translate(monkeypatch, pack_module):
    routing = import_module(f"packs.language.{pack_module}.routing")

    calls = []

    def fake_translate(candidate, cfg, target_language):
        calls.append((candidate.id, target_language))
        return SubtitleCandidate(
            id=f"{candidate.id}_translated",
            language=target_language,
            source="mt",
            origin_stream=candidate.origin_stream,
            segments=list(candidate.segments),
            meta={},
        )

    monkeypatch.setattr(routing, "_translate_candidate", fake_translate)

    candidate = SubtitleCandidate(
        id="source",
        language="ko",
        source="embedded",
        origin_stream="sub:0",
        segments=[Segment(start=0.0, end=1.0, text="line")],
        meta={},
    )

    result = routing.translate_candidate(candidate, _DummyConfig("single_pass"), candidate)

    assert calls == [("source", "en")]
    assert result.meta["translation_workflow"] == "single_pass"


@pytest.mark.parametrize("pack_module", ["ko_en", "zh_en", "es_en"])
def test_non_japanese_routing_two_pass_delegates_to_core_two_pass(monkeypatch, pack_module):
    routing = import_module(f"packs.language.{pack_module}.routing")

    calls = []

    def fake_two_pass(candidate, cfg, ja_candidate, target_language):
        calls.append((candidate.id, ja_candidate.id, target_language))
        return SubtitleCandidate(
            id=f"{candidate.id}_natural",
            language=target_language,
            source="two_pass_llm",
            origin_stream=candidate.origin_stream,
            segments=list(candidate.segments),
            meta={"translation_workflow": "literal_then_natural"},
        )

    monkeypatch.setattr(routing, "run_two_pass_translation", fake_two_pass)

    candidate = SubtitleCandidate(
        id="source",
        language="zh",
        source="embedded",
        origin_stream="sub:0",
        segments=[Segment(start=0.0, end=1.0, text="line")],
        meta={},
    )

    result = routing.translate_candidate(candidate, _DummyConfig("literal_then_natural"), candidate)

    assert calls == [("source", "source", "en")]
    assert result.meta["translation_workflow"] == "literal_then_natural"


def test_en_en_routing_is_transcription_only_passthrough():
    from packs.language.en_en.routing import translate_candidate

    candidate = SubtitleCandidate(
        id="asr_en_a0",
        language="en",
        source="asr",
        origin_stream="audio:0",
        segments=[Segment(start=0.0, end=1.0, text="Hello there")],
        meta={},
    )

    result = translate_candidate(candidate, _DummyConfig(), candidate)

    assert result.id == "asr_en_a0_transcription_only"
    assert result.language == "en"
    assert result.meta["translation_workflow"] == "transcription_only"
    assert result.meta["translation_engine"] == "none"
    assert result.meta["translation_skipped"] is True
    assert candidate.id == "asr_en_a0"


@pytest.mark.parametrize(
    "fixture_dir,source_file",
    [
        ("korean", "source.ko.srt"),
        ("chinese", "source.zh.srt"),
        ("spanish", "source.es.srt"),
        ("english_transcription", "source.en.srt"),
    ],
)
def test_non_japanese_benchmark_fixtures_exist(fixture_dir, source_file):
    fixture_path = Path(__file__).parent.parent / "fixtures" / "benchmark_translation" / fixture_dir

    assert (fixture_path / source_file).exists()
    assert (fixture_path / "reference.en.srt").exists()
    assert (fixture_path / "expected.json").exists()
