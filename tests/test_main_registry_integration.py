"""Registry integration tests for the legacy process_video path."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from asr import Segment as ASRSegment
from core.artifacts import (
    ARTIFACT_TYPE_MKV,
    ARTIFACT_TYPE_SRT,
    ArtifactRegistry,
    PIPELINE_STATUS_COMPLETED,
    PIPELINE_STATUS_FAILED,
)
from main import _emit_registry_run_id, process_video
from models import Segment, SubtitleCandidate


def _make_config(tmp_path: Path) -> MagicMock:
    cfg = MagicMock()
    cfg.profile = "test"
    cfg.asr_model_name = "fake-whisper"
    cfg.asr_compute_type = "int8"
    cfg.asr_beam_size = 1
    cfg.asr_vad_filter = False
    cfg.asr_language = "ja"
    cfg.mt_model_name = "fake-mt"
    cfg.mt_device = "cpu"
    cfg.llm_enabled = False
    cfg.llm_model_name = "fake-llm"
    cfg.llm_base_url = "http://localhost:11434"
    cfg.mux_enabled = False
    cfg.mux_output_suffix = "subbed"

    paths = {
        "outbox": tmp_path / "outbox",
        "temp": tmp_path / "temp",
        "logs": tmp_path / "logs",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    cfg.get_path.side_effect = lambda name: str(paths[name])

    def _get(*keys, default=None):
        if keys == ("logging", "save_segment_json"):
            return False
        if keys == ("audio", "preferred_languages"):
            return ["ja"]
        return default

    cfg.get.side_effect = _get
    return cfg


def _write_candidate_srt(candidate, output_path, config):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n"
        f"{candidate.segments[0].text}\n",
        encoding="utf-8",
    )
    return path


def _mux_subtitle_to_video(**kwargs):
    path = Path(kwargs["output_video_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"muxed mkv")
    return path


def _extract_audio(audio_path: Path):
    def _inner(**_kwargs):
        audio_path.write_bytes(b"wav")
        return audio_path

    return _inner


def test_process_video_records_run_candidates_and_artifacts(tmp_path):
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"fake video")
    cfg = _make_config(tmp_path)
    registry = ArtifactRegistry(":memory:")
    media_hash = "deadbeef"

    audio_path = tmp_path / "temp" / "episode.wav"
    asr_segments = [ASRSegment(0.0, 1.0, "こんにちは")]
    mt_candidate = SubtitleCandidate(
        id="asr_ja_mt",
        language="en",
        source="mt",
        origin_stream="audio:0",
        segments=[Segment(0.0, 1.0, "Hello.")],
        meta={"mt_model": "fake-mt"},
    )

    asr_instance = MagicMock()
    asr_instance.transcribe_audio_to_segments.return_value = (asr_segments, None)

    media = MagicMock()
    media.audio_streams = [MagicMock(language="ja", raw_language="jpn")]

    with patch("main.inspect_media", return_value=media), \
         patch("main.choose_audio_track", return_value=0), \
         patch("main.extract_audio_with_ffmpeg", side_effect=_extract_audio(audio_path)), \
         patch("main.FasterWhisperASR", return_value=asr_instance), \
         patch("main.translate_candidate_jp_to_en", return_value=mt_candidate), \
         patch("main.write_candidate_srt", side_effect=_write_candidate_srt):
        result = process_video(
            str(video),
            cfg,
            no_llm=True,
            no_mux=True,
            registry=registry,
            media_hash=media_hash,
        )

    assert result["success"] is True
    assert result["registry_run_id"]

    run = registry.get_pipeline_run(result["registry_run_id"])
    assert run is not None
    assert run.status == PIPELINE_STATUS_COMPLETED

    media = registry.get_media_asset(media_hash)
    assert media is not None
    assert media.file_path == str(video)
    assert media.file_name == video.name

    candidates = registry.list_candidates(media_hash)
    assert [candidate.source for candidate in candidates] == ["asr", "mt"]
    assert candidates[1].parent_candidate_id == candidates[0].id

    artifacts = registry._conn.execute(
        "SELECT * FROM artifacts WHERE media_hash = ? ORDER BY id",
        (media_hash,),
    ).fetchall()
    assert [row["artifact_type"] for row in artifacts] == [
        ARTIFACT_TYPE_SRT,
        ARTIFACT_TYPE_SRT,
    ]
    assert artifacts[0]["candidate_id"] == candidates[1].id
    assert artifacts[1]["candidate_id"] == candidates[1].id
    assert all(row["pipeline_run_id"] == run.id for row in artifacts)
    assert all(row["file_hash"] for row in artifacts)


def test_process_video_records_muxed_mkv_artifact(tmp_path):
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"fake video")
    cfg = _make_config(tmp_path)
    cfg.mux_enabled = True
    registry = ArtifactRegistry(":memory:")
    media_hash = "deadbeef"

    audio_path = tmp_path / "temp" / "episode.wav"
    asr_segments = [ASRSegment(0.0, 1.0, "こんにちは")]
    mt_candidate = SubtitleCandidate(
        id="asr_ja_mt",
        language="en",
        source="mt",
        origin_stream="audio:0",
        segments=[Segment(0.0, 1.0, "Hello.")],
        meta={"mt_model": "fake-mt"},
    )

    asr_instance = MagicMock()
    asr_instance.transcribe_audio_to_segments.return_value = (asr_segments, None)

    media = MagicMock()
    media.audio_streams = [MagicMock(language="ja", raw_language="jpn")]

    with patch("main.inspect_media", return_value=media), \
         patch("main.choose_audio_track", return_value=0), \
         patch("main.extract_audio_with_ffmpeg", side_effect=_extract_audio(audio_path)), \
         patch("main.FasterWhisperASR", return_value=asr_instance), \
         patch("main.translate_candidate_jp_to_en", return_value=mt_candidate), \
         patch("main.write_candidate_srt", side_effect=_write_candidate_srt), \
         patch("main.mux_subtitle_to_video", side_effect=_mux_subtitle_to_video):
        result = process_video(
            str(video),
            cfg,
            no_llm=True,
            no_mux=False,
            registry=registry,
            media_hash=media_hash,
        )

    assert result["success"] is True
    assert result["muxed_video"] == str(tmp_path / "outbox" / "episode.subbed.mkv")

    run = registry.get_pipeline_run(result["registry_run_id"])
    candidates = registry.list_candidates(media_hash)
    artifacts = registry._conn.execute(
        "SELECT * FROM artifacts WHERE media_hash = ? ORDER BY id",
        (media_hash,),
    ).fetchall()

    assert [row["artifact_type"] for row in artifacts] == [
        ARTIFACT_TYPE_SRT,
        ARTIFACT_TYPE_SRT,
        ARTIFACT_TYPE_MKV,
    ]
    mkv_artifact = artifacts[-1]
    assert mkv_artifact["file_path"] == result["muxed_video"]
    assert mkv_artifact["file_hash"]
    assert mkv_artifact["candidate_id"] == candidates[-1].id
    assert mkv_artifact["pipeline_run_id"] == run.id


def test_process_video_muxes_without_registry_when_hash_unavailable(tmp_path):
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"fake video")
    cfg = _make_config(tmp_path)
    cfg.mux_enabled = True

    audio_path = tmp_path / "temp" / "episode.wav"
    asr_segments = [ASRSegment(0.0, 1.0, "こんにちは")]
    mt_candidate = SubtitleCandidate(
        id="asr_ja_mt",
        language="en",
        source="mt",
        origin_stream="audio:0",
        segments=[Segment(0.0, 1.0, "Hello.")],
        meta={"mt_model": "fake-mt"},
    )

    asr_instance = MagicMock()
    asr_instance.transcribe_audio_to_segments.return_value = (asr_segments, None)

    media = MagicMock()
    media.audio_streams = [MagicMock(language="ja", raw_language="jpn")]

    with patch("main.compute_media_hash", side_effect=OSError("unreadable")), \
         patch("main.inspect_media", return_value=media), \
         patch("main.choose_audio_track", return_value=0), \
         patch("main.extract_audio_with_ffmpeg", side_effect=_extract_audio(audio_path)), \
         patch("main.FasterWhisperASR", return_value=asr_instance), \
         patch("main.translate_candidate_jp_to_en", return_value=mt_candidate), \
         patch("main.write_candidate_srt", side_effect=_write_candidate_srt), \
         patch("main.mux_subtitle_to_video", side_effect=_mux_subtitle_to_video):
        result = process_video(
            str(video),
            cfg,
            no_llm=True,
            no_mux=False,
            registry=None,
            media_hash=None,
        )

    assert result["success"] is True
    assert result["registry_run_id"] is None
    assert result["muxed_video"] == str(tmp_path / "outbox" / "episode.subbed.mkv")


def test_process_video_marks_registry_run_failed_on_error(tmp_path):
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"fake video")
    cfg = _make_config(tmp_path)
    registry = ArtifactRegistry(":memory:")
    media_hash = "deadbeef"

    with patch("main.inspect_media", return_value=MagicMock(audio_streams=[])), \
         patch("main.choose_audio_track", return_value=0), \
         patch("main.extract_audio_with_ffmpeg", side_effect=RuntimeError("probe failed")):
        result = process_video(
            str(video),
            cfg,
            no_llm=True,
            no_mux=True,
            registry=registry,
            media_hash=media_hash,
        )

    assert result["success"] is False
    assert "probe failed" in result["error"]
    run = registry.get_pipeline_run(result["registry_run_id"])
    assert run.status == PIPELINE_STATUS_FAILED
    assert "probe failed" in run.error_message


def test_emit_registry_run_id_prints_script_friendly_line(capsys):
    _emit_registry_run_id("run-123")
    captured = capsys.readouterr()
    assert captured.out == "registry_run_id=run-123\n"


def test_emit_registry_run_id_is_quiet_when_not_recorded(capsys):
    _emit_registry_run_id(None)
    captured = capsys.readouterr()
    assert captured.out == ""
