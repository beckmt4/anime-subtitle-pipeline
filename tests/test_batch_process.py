from __future__ import annotations

from pathlib import Path

from core.runtime import Config
from core.runtime import batch_process
from media_inspect import AudioStream, MediaInfo


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
    cfg._config["paths"].update({key: str(value) for key, value in paths.items()})
    return cfg


def test_process_batch_uses_run_generate(monkeypatch, tmp_path):
    video = tmp_path / "episode.mkv"
    video.write_bytes(b"video")
    cfg = _make_config(tmp_path)
    media = MediaInfo(
        path=video,
        format_name="matroska",
        duration=120.0,
        audio_streams=[AudioStream(index=0, codec="aac", language="ja", raw_language="jpn")],
        subtitle_streams=[],
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(batch_process, "inspect_media", lambda path: media)

    def _fake_run_generate(media_info, config, **kwargs):
        captured["media"] = media_info
        captured["config"] = config
        captured["kwargs"] = kwargs
        return {"strategy": "ja_audio_asr_mt"}

    monkeypatch.setattr(batch_process, "run_generate", _fake_run_generate)

    stats = batch_process.process_batch([video], cfg, no_llm=True, no_mux=True)

    assert stats == {
        "total": 1,
        "processed": 1,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }
    assert captured["media"] is media
    assert captured["config"] is cfg
    assert captured["kwargs"] == {"no_llm": True}
