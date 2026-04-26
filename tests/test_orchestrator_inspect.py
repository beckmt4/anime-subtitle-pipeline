"""Tests for the generate-mode inspect-only flow (issue #53).

Verifies that ``run_generate_inspect`` performs source discovery and strategy
evaluation without invoking ASR, MT, LLM polish, mux, or any output writes.

Tests cover:
- Representative source layouts (embedded EN, JA subs, EN audio, JA audio,
  untagged audio, no source)
- Probe-required flag when auto-routing meets ambiguous input
- No-source failure reporting
- Result schema validation
- Guarantee that no heavy runtime calls are made
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from config import Config
from media_inspect import MediaInfo, AudioStream, SubtitleStream
import orchestrator as orch
from orchestrator import run_generate_inspect


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**generate_overrides) -> Config:
    cfg = Config()
    cfg._config.setdefault("generate", {})
    cfg._config["generate"].update(generate_overrides)
    return cfg


def _make_media(
    *,
    en_sub: bool = False,
    ja_sub: bool = False,
    en_audio: bool = False,
    ja_audio: bool = False,
    untagged_audio: bool = False,
    en_sub_lang: str = "en",
    sub_codec: str = "subrip",
) -> MediaInfo:
    audio_streams: list[AudioStream] = []
    subtitle_streams: list[SubtitleStream] = []
    idx = 0

    if en_audio:
        audio_streams.append(AudioStream(index=idx, codec="aac", language="en", raw_language="en"))
        idx += 1
    if ja_audio:
        audio_streams.append(AudioStream(index=idx, codec="aac", language="ja", raw_language="ja"))
        idx += 1
    if untagged_audio:
        audio_streams.append(AudioStream(index=idx, codec="aac", language=None, raw_language=None))
        idx += 1

    sidx = 10
    if en_sub:
        subtitle_streams.append(
            SubtitleStream(index=sidx, codec=sub_codec, language=en_sub_lang, raw_language=en_sub_lang)
        )
        sidx += 1
    if ja_sub:
        subtitle_streams.append(
            SubtitleStream(index=sidx, codec="subrip", language="ja", raw_language="ja")
        )
        sidx += 1

    return MediaInfo(
        path=Path("test.mkv"),
        format_name="matroska",
        duration=1440.0,
        audio_streams=audio_streams,
        subtitle_streams=subtitle_streams,
    )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "inspect_only", "video", "planned_strategy", "no_source",
    "sources_detected", "audio_streams", "subtitle_streams",
    "selection_report", "artifact_plan", "quality_risk",
    "probe_required", "probe_note",
    "formatting_artifact_risk", "formatting_artifact_note",
}


def _assert_schema(result: dict) -> None:
    missing = REQUIRED_KEYS - result.keys()
    assert not missing, f"inspect result missing keys: {missing}"
    assert result["inspect_only"] is True, "inspect_only sentinel must be True"
    for key in ("en_sub_idx", "ja_sub_idx", "en_audio_order", "ja_audio_order"):
        assert key in result["sources_detected"], f"sources_detected missing '{key}'"


# ---------------------------------------------------------------------------
# No heavy runtime calls
# ---------------------------------------------------------------------------

class TestNoHeavyCallsInInspectMode:
    """Verify that inspect-only mode never invokes ASR, MT, LLM, mux, or writes."""

    def test_no_asr_calls(self):
        media = _make_media(ja_audio=True)
        cfg = _make_config()
        with patch.object(orch, "FasterWhisperASR") as mock_asr, \
             patch.object(orch, "extract_audio_with_ffmpeg") as mock_audio, \
             patch.object(orch, "translate_candidate_jp_to_en") as mock_mt, \
             patch.object(orch, "polish_candidate_with_llm") as mock_llm, \
             patch.object(orch, "write_candidate_srt") as mock_write:
            run_generate_inspect(media, cfg)
            mock_asr.assert_not_called()
            mock_audio.assert_not_called()
            mock_mt.assert_not_called()
            mock_llm.assert_not_called()
            mock_write.assert_not_called()

    def test_no_asr_calls_embedded_en(self):
        media = _make_media(en_sub=True)
        cfg = _make_config()
        with patch.object(orch, "FasterWhisperASR") as mock_asr, \
             patch.object(orch, "extract_subtitle_track") as mock_extract, \
             patch.object(orch, "write_candidate_srt") as mock_write:
            run_generate_inspect(media, cfg)
            mock_asr.assert_not_called()
            mock_extract.assert_not_called()
            mock_write.assert_not_called()

    def test_no_probe_in_auto_mode_en_tagged_audio(self):
        """Even when a real run would probe, inspect mode must not call ASR."""
        media = _make_media(en_audio=True)
        cfg = _make_config(prefer_audio_language="auto")
        with patch.object(orch, "FasterWhisperASR") as mock_asr, \
             patch.object(orch, "_probe_audio_language") as mock_probe:
            run_generate_inspect(media, cfg)
            mock_asr.assert_not_called()
            mock_probe.assert_not_called()

    def test_no_probe_untagged_audio(self):
        """Inspect mode must not probe untagged audio."""
        media = _make_media(untagged_audio=True)
        cfg = _make_config(prefer_audio_language="auto")
        with patch.object(orch, "FasterWhisperASR") as mock_asr, \
             patch.object(orch, "_probe_audio_language") as mock_probe:
            run_generate_inspect(media, cfg)
            mock_asr.assert_not_called()
            mock_probe.assert_not_called()

    def test_no_file_writes(self, tmp_path):
        """Inspect mode must not create any files."""
        media = _make_media(ja_audio=True)
        cfg = _make_config()
        cfg._config.setdefault("paths", {})
        cfg._config["paths"]["outbox"] = str(tmp_path)
        cfg._config["paths"]["temp"] = str(tmp_path)
        run_generate_inspect(media, cfg)
        assert list(tmp_path.iterdir()) == [], "Inspect mode must not write any files"


# ---------------------------------------------------------------------------
# Strategy selection (representative source layouts)
# ---------------------------------------------------------------------------

class TestInspectStrategySelection:
    def test_embedded_en_selected(self):
        media = _make_media(en_sub=True, ja_audio=True, ja_sub=True)
        result = run_generate_inspect(media, _make_config())
        _assert_schema(result)
        assert result["planned_strategy"] == "embedded_en"
        assert result["no_source"] is False

    def test_embedded_jp_mt_selected(self):
        media = _make_media(ja_sub=True, ja_audio=True)
        result = run_generate_inspect(media, _make_config())
        _assert_schema(result)
        assert result["planned_strategy"] == "embedded_jp_mt"

    def test_ja_audio_asr_mt_selected(self):
        media = _make_media(ja_audio=True)
        result = run_generate_inspect(media, _make_config())
        _assert_schema(result)
        assert result["planned_strategy"] == "ja_audio_asr_mt"

    def test_en_audio_asr_selected_when_preferred(self):
        cfg = _make_config(prefer_audio_language="en", prefer_subtitles=False)
        media = _make_media(en_audio=True, ja_audio=True)
        result = run_generate_inspect(media, cfg)
        _assert_schema(result)
        assert result["planned_strategy"] == "en_audio_asr"

    def test_untagged_audio_fallback(self):
        media = _make_media(untagged_audio=True)
        result = run_generate_inspect(media, _make_config())
        _assert_schema(result)
        assert result["planned_strategy"] == "untagged_audio_asr_mt"

    def test_no_source_when_no_streams(self):
        media = MediaInfo(path=Path("empty.mkv"), format_name="matroska", duration=0.0)
        result = run_generate_inspect(media, _make_config())
        _assert_schema(result)
        assert result["planned_strategy"] is None
        assert result["no_source"] is True
        assert result["selection_report"] is None
        assert result["artifact_plan"] == {}


# ---------------------------------------------------------------------------
# Probe-required flag
# ---------------------------------------------------------------------------

class TestProbeRequiredFlag:
    def test_probe_required_for_auto_en_only_audio(self):
        """When only EN-tagged audio exists with auto mode, probe_required must be True."""
        media = _make_media(en_audio=True)
        cfg = _make_config(prefer_audio_language="auto")
        result = run_generate_inspect(media, cfg)
        _assert_schema(result)
        assert result["probe_required"] is True
        assert result["probe_note"] is not None
        assert len(result["probe_note"]) > 0

    def test_probe_required_for_untagged_audio(self):
        """Untagged audio with auto mode: probe_required must be True."""
        media = _make_media(untagged_audio=True)
        cfg = _make_config(prefer_audio_language="auto")
        result = run_generate_inspect(media, cfg)
        _assert_schema(result)
        assert result["probe_required"] is True

    def test_probe_not_required_when_ja_audio_present(self):
        """Explicit JA-tagged audio: no probe needed."""
        media = _make_media(ja_audio=True)
        result = run_generate_inspect(media, _make_config())
        assert result["probe_required"] is False
        assert result["probe_note"] is None

    def test_probe_not_required_when_en_sub_present(self):
        """Embedded EN sub available: no probe needed."""
        media = _make_media(en_sub=True)
        result = run_generate_inspect(media, _make_config())
        assert result["probe_required"] is False

    def test_probe_not_required_when_audio_track_override_set(self):
        """Explicit --audio-track override bypasses probe."""
        media = _make_media(en_audio=True)
        cfg = _make_config(prefer_audio_language="auto")
        result = run_generate_inspect(media, cfg, audio_track_override=0)
        assert result["probe_required"] is False


# ---------------------------------------------------------------------------
# Artifact plan
# ---------------------------------------------------------------------------

class TestArtifactPlan:
    def test_embedded_en_artifact_plan(self):
        media = _make_media(en_sub=True)
        result = run_generate_inspect(media, _make_config())
        plan = result["artifact_plan"]
        assert "final_srt" in plan
        assert "qc_json" in plan
        assert "raw_srt" not in plan  # EN sub path has no raw MT step

    def test_mt_strategy_artifact_plan_includes_raw_srt(self):
        media = _make_media(ja_audio=True)
        result = run_generate_inspect(media, _make_config())
        plan = result["artifact_plan"]
        assert "final_srt" in plan
        assert "raw_srt" in plan
        assert "qc_json" in plan

    def test_no_artifact_plan_when_no_source(self):
        media = MediaInfo(path=Path("empty.mkv"), format_name="matroska", duration=0.0)
        result = run_generate_inspect(media, _make_config())
        assert result["artifact_plan"] == {}


# ---------------------------------------------------------------------------
# Quality risk
# ---------------------------------------------------------------------------

class TestQualityRisk:
    def test_embedded_en_high_confidence(self):
        media = _make_media(en_sub=True)
        result = run_generate_inspect(media, _make_config())
        risk = result["quality_risk"]
        assert risk["confidence_tier"] == "high"
        assert risk["review_likely"] is False

    def test_ja_audio_low_confidence_review_likely(self):
        media = _make_media(ja_audio=True)
        result = run_generate_inspect(media, _make_config())
        risk = result["quality_risk"]
        assert risk["confidence_tier"] == "low"
        assert risk["review_likely"] is True

    def test_untagged_audio_heuristic_fallback_flagged(self):
        media = _make_media(untagged_audio=True)
        result = run_generate_inspect(media, _make_config())
        risk = result["quality_risk"]
        assert risk["heuristic_fallback"] is True

    def test_embedded_en_not_heuristic_fallback(self):
        media = _make_media(en_sub=True)
        result = run_generate_inspect(media, _make_config())
        assert result["quality_risk"].get("heuristic_fallback") is False


# ---------------------------------------------------------------------------
# Formatting artifact risk
# ---------------------------------------------------------------------------

class TestFormattingArtifactRisk:
    def test_ass_subtitle_flags_formatting_risk(self):
        media = _make_media(en_sub=True, sub_codec="ass")
        result = run_generate_inspect(media, _make_config())
        assert result["formatting_artifact_risk"] is True
        assert result["formatting_artifact_note"] is not None

    def test_subrip_subtitle_no_formatting_risk(self):
        media = _make_media(en_sub=True, sub_codec="subrip")
        result = run_generate_inspect(media, _make_config())
        assert result["formatting_artifact_risk"] is False
        assert result["formatting_artifact_note"] is None

    def test_no_subtitles_no_formatting_risk(self):
        media = _make_media(ja_audio=True)
        result = run_generate_inspect(media, _make_config())
        assert result["formatting_artifact_risk"] is False


# ---------------------------------------------------------------------------
# Inspect result is marked inspect_only
# ---------------------------------------------------------------------------

class TestInspectOnlySentinel:
    def test_inspect_only_true(self):
        media = _make_media(en_sub=True)
        result = run_generate_inspect(media, _make_config())
        assert result["inspect_only"] is True

    def test_inspect_result_has_no_segment_count(self):
        """Unlike run_generate, inspect result has no segment_count key."""
        media = _make_media(en_sub=True)
        result = run_generate_inspect(media, _make_config())
        assert "segment_count" not in result

    def test_inspect_result_has_no_candidate_id(self):
        """Unlike run_generate, inspect result has no candidate_id key."""
        media = _make_media(en_sub=True)
        result = run_generate_inspect(media, _make_config())
        assert "candidate_id" not in result


# ---------------------------------------------------------------------------
# Override handling
# ---------------------------------------------------------------------------

class TestOverrides:
    def test_skip_embedded_en_reflects_in_planned_strategy(self):
        media = _make_media(en_sub=True, ja_audio=True)
        result = run_generate_inspect(media, _make_config(), skip_embedded_en=True)
        assert result["planned_strategy"] != "embedded_en"
        assert result["planned_strategy"] == "ja_audio_asr_mt"

    def test_audio_track_override_forces_ja_asr_mt(self):
        media = _make_media(en_sub=True, en_audio=True)
        result = run_generate_inspect(media, _make_config(), audio_track_override=0)
        assert result["planned_strategy"] == "ja_audio_asr_mt"

    def test_audio_track_override_out_of_range_raises(self):
        media = _make_media(ja_audio=True)
        with pytest.raises(RuntimeError, match="out of range"):
            run_generate_inspect(media, _make_config(), audio_track_override=99)


# ---------------------------------------------------------------------------
# Selection report included
# ---------------------------------------------------------------------------

class TestSelectionReport:
    def test_selection_report_present_for_valid_source(self):
        media = _make_media(en_sub=True)
        result = run_generate_inspect(media, _make_config())
        report = result["selection_report"]
        assert report is not None
        assert "selected_source" in report
        assert "confidence_tier" in report
        assert "sources_evaluated" in report
        assert "review_recommended" in report

    def test_selection_report_none_when_no_source(self):
        media = MediaInfo(path=Path("empty.mkv"), format_name="matroska", duration=0.0)
        result = run_generate_inspect(media, _make_config())
        assert result["selection_report"] is None


# ---------------------------------------------------------------------------
# Stream descriptors
# ---------------------------------------------------------------------------

class TestStreamDescriptors:
    def test_audio_streams_listed(self):
        media = _make_media(en_audio=True, ja_audio=True)
        result = run_generate_inspect(media, _make_config())
        assert len(result["audio_streams"]) == 2
        for s in result["audio_streams"]:
            assert "order" in s and "codec" in s and "language" in s

    def test_subtitle_streams_listed(self):
        media = _make_media(en_sub=True, ja_sub=True)
        result = run_generate_inspect(media, _make_config())
        assert len(result["subtitle_streams"]) == 2
        for s in result["subtitle_streams"]:
            assert "order" in s and "codec" in s and "is_bitmap" in s

    def test_empty_streams_on_bare_media(self):
        media = MediaInfo(path=Path("bare.mkv"), format_name="matroska", duration=0.0)
        result = run_generate_inspect(media, _make_config())
        assert result["audio_streams"] == []
        assert result["subtitle_streams"] == []
