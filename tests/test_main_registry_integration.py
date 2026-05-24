"""Registry integration tests for core.runtime.run_generate."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.artifacts import (
    ARTIFACT_TYPE_QC_JSON,
    ARTIFACT_TYPE_SRT,
    ArtifactRegistry,
    PIPELINE_STATUS_COMPLETED,
    PIPELINE_STATUS_FAILED,
)
from core.runtime import Config, run_generate
from main import _emit_registry_run_id
from core.media import AudioStream, MediaInfo
from core.subtitles import Segment, SubtitleCandidate
from packs.language import LanguageRoutingHooks


def _make_config(tmp_path: Path) -> Config:
    cfg = Config(
        "/home/runner/work/anime-subtitle-pipeline/anime-subtitle-pipeline/config.yaml",
        profile_override="dev",
    )
    paths = {
        "inbox": tmp_path / "inbox",
        "outbox": tmp_path / "outbox",
        "temp": tmp_path / "temp",
        "logs": tmp_path / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    cfg._config.setdefault("paths", {})
    cfg._config["paths"].update({k: str(v) for k, v in paths.items()})
    cfg._config.setdefault("llm", {})
    cfg._config["llm"]["enabled"] = False
    cfg._config.setdefault("generate", {})
    cfg._config["generate"]["use_llm_polish"] = False
    return cfg


def _make_media(video: Path) -> MediaInfo:
    return MediaInfo(
        path=video,
        format_name="matroska",
        duration=120.0,
        audio_streams=[AudioStream(index=0, codec="aac", language="ja", raw_language="jpn")],
        subtitle_streams=[],
    )


def _write_candidate_srt(candidate, output_path, config):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n"
        f"{candidate.segments[0].text}\n",
        encoding="utf-8",
    )
    return path


def _extract_audio(audio_path: Path):
    def _inner(*_args, **_kwargs):
        audio_path.write_bytes(b"wav")
        return str(audio_path)

    return _inner


def _clean_qc_summary(*args, **kwargs):
    return {
        "parsed_ok": True,
        "cue_count": 1,
        "violations": [],
        "error_count": 0,
        "warning_count": 0,
        "pass_qc": True,
    }


def _translation_qc_summary(*args, **kwargs):
    return {"status": "pass", "reason_codes": [], "errors": []}


def _review_routing(*args, **kwargs):
    return {"status": "pass", "reason_codes": []}


def _routing_hooks_for_tests(translate_result):
    return LanguageRoutingHooks(
        pack_id="ja_en",
        source_language="ja",
        target_language="en",
        lang_aliases={
            "ja": frozenset({"ja", "jpn", "jp", "ja-jp", "japanese"}),
            "en": frozenset({"en", "eng", "en-us", "en-gb", "english"}),
        },
        untagged_audio_fallback_source_language="ja",
        translate_candidate=lambda candidate, cfg, source_candidate=None: translate_result,
    )


def test_run_generate_records_run_candidates_and_artifacts(tmp_path):
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"fake video")
    cfg = _make_config(tmp_path)
    media = _make_media(video)
    registry = ArtifactRegistry(":memory:")
    media_hash = "deadbeef"

    audio_path = tmp_path / "temp" / "episode_ja_a0.wav"
    asr_segments = [Segment(0.0, 1.0, "こんにちは")]
    ja_asr_candidate = SubtitleCandidate(
        id="ja_audio_asr_a0",
        language="ja",
        source="asr",
        origin_stream="audio:0",
        segments=asr_segments,
        meta={},
    )
    mt_candidate = SubtitleCandidate(
        id="ja_audio_asr_a0_mt",
        language="en",
        source="mt",
        origin_stream="audio:0",
        segments=[Segment(0.0, 1.0, "Hello.")],
        meta={"mt_model": "fake-mt"},
    )

    asr_instance = MagicMock()
    asr_instance.transcribe_audio_to_segments.return_value = (asr_segments, None)
    routing_hooks = _routing_hooks_for_tests(mt_candidate)

    with patch("core.runtime.orchestrator.extract_audio_with_ffmpeg", side_effect=_extract_audio(audio_path)), \
         patch("core.runtime.orchestrator.FasterWhisperASR", return_value=asr_instance), \
         patch("core.runtime.orchestrator.build_candidate_from_segments", return_value=ja_asr_candidate), \
         patch("core.runtime.orchestrator.load_language_routing_hooks", return_value=routing_hooks), \
         patch("core.runtime.orchestrator.write_candidate_srt", side_effect=_write_candidate_srt), \
         patch("core.runtime.orchestrator.run_qc", side_effect=_clean_qc_summary), \
         patch("core.runtime.orchestrator.run_translation_qc", side_effect=_translation_qc_summary), \
         patch("core.runtime.orchestrator.route_generate_review_task", side_effect=_review_routing):
        result = run_generate(
            media,
            cfg,
            no_llm=True,
            registry=registry,
            media_hash=media_hash,
        )

    assert result["registry_run_id"]
    run = registry.get_pipeline_run(result["registry_run_id"])
    assert run is not None
    assert run.status == PIPELINE_STATUS_COMPLETED

    candidates = registry.list_candidates(media_hash)
    assert [candidate.source for candidate in candidates] == ["asr", "mt"]
    assert candidates[1].parent_candidate_id == candidates[0].id

    artifacts = registry._conn.execute(
        "SELECT * FROM artifacts WHERE media_hash = ? ORDER BY id",
        (media_hash,),
    ).fetchall()
    assert [row["artifact_type"] for row in artifacts] == [
        ARTIFACT_TYPE_SRT,
        ARTIFACT_TYPE_QC_JSON,
    ]
    assert artifacts[0]["candidate_id"] == candidates[1].id
    assert artifacts[1]["candidate_id"] == candidates[1].id
    assert all(row["pipeline_run_id"] == run.id for row in artifacts)
    assert all(row["file_hash"] for row in artifacts)


def test_run_generate_without_registry_does_not_emit_registry_id(tmp_path):
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"fake video")
    cfg = _make_config(tmp_path)
    media = _make_media(video)

    audio_path = tmp_path / "temp" / "episode_ja_a0.wav"
    asr_segments = [Segment(0.0, 1.0, "こんにちは")]
    ja_asr_candidate = SubtitleCandidate(
        id="ja_audio_asr_a0",
        language="ja",
        source="asr",
        origin_stream="audio:0",
        segments=asr_segments,
        meta={},
    )
    mt_candidate = SubtitleCandidate(
        id="ja_audio_asr_a0_mt",
        language="en",
        source="mt",
        origin_stream="audio:0",
        segments=[Segment(0.0, 1.0, "Hello.")],
        meta={"mt_model": "fake-mt"},
    )
    asr_instance = MagicMock()
    asr_instance.transcribe_audio_to_segments.return_value = (asr_segments, None)
    routing_hooks = _routing_hooks_for_tests(mt_candidate)

    with patch("core.runtime.orchestrator.extract_audio_with_ffmpeg", side_effect=_extract_audio(audio_path)), \
         patch("core.runtime.orchestrator.FasterWhisperASR", return_value=asr_instance), \
         patch("core.runtime.orchestrator.build_candidate_from_segments", return_value=ja_asr_candidate), \
         patch("core.runtime.orchestrator.load_language_routing_hooks", return_value=routing_hooks), \
         patch("core.runtime.orchestrator.write_candidate_srt", side_effect=_write_candidate_srt), \
         patch("core.runtime.orchestrator.run_qc", side_effect=_clean_qc_summary), \
         patch("core.runtime.orchestrator.run_translation_qc", side_effect=_translation_qc_summary), \
         patch("core.runtime.orchestrator.route_generate_review_task", side_effect=_review_routing):
        result = run_generate(
            media,
            cfg,
            no_llm=True,
            registry=None,
            media_hash=None,
        )

    assert result["registry_run_id"] is None
    assert result["output_srt"] == str(tmp_path / "outbox" / "episode.en.srt")


def test_run_generate_marks_registry_run_failed_on_error(tmp_path):
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"fake video")
    cfg = _make_config(tmp_path)
    media = _make_media(video)
    registry = ArtifactRegistry(":memory:")
    media_hash = "deadbeef"

    with patch(
        "core.runtime.orchestrator.extract_audio_with_ffmpeg",
        side_effect=RuntimeError("probe failed"),
    ):
        with pytest.raises(RuntimeError, match="probe failed"):
            run_generate(
                media,
                cfg,
                no_llm=True,
                registry=registry,
                media_hash=media_hash,
            )

    runs = registry.list_pipeline_runs()
    assert len(runs) == 1
    assert runs[0].status == PIPELINE_STATUS_FAILED
    assert "probe failed" in (runs[0].error_message or "")


def test_emit_registry_run_id_prints_script_friendly_line(capsys):
    _emit_registry_run_id("run-123")
    captured = capsys.readouterr()
    assert captured.out == "registry_run_id=run-123\n"


def test_emit_registry_run_id_is_quiet_when_not_recorded(capsys):
    _emit_registry_run_id(None)
    captured = capsys.readouterr()
    assert captured.out == ""
