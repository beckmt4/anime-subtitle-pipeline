from __future__ import annotations

import sys
from pathlib import Path

import pytest

import main
from core.ocr import OCRBackend
from media_inspect import MediaInfo, SubtitleStream
from models import Segment, SubtitleCandidate


class FakeOCRBackend(OCRBackend):
    def extract(
        self,
        video_path: str,
        stream_index: int,
        language_hint: str | None = None,
    ) -> SubtitleCandidate:
        return SubtitleCandidate(
            id=f"bitmap_{language_hint}_s{stream_index}",
            language=language_hint or "und",
            source="embedded",
            origin_stream=f"sub:{stream_index}",
            segments=[Segment(0.0, 1.0, "ok", meta={"ocr_confidence": 0.9})],
            meta={},
        )


def test_main_generate_passes_configured_ocr_backend(monkeypatch, tmp_path):
    media = MediaInfo(
        path=tmp_path / "dummy.mkv",
        format_name="matroska",
        duration=10.0,
        audio_streams=[],
        subtitle_streams=[
            SubtitleStream(index=3, codec="pgssub", language="ja", raw_language="jpn", is_bitmap=True),
        ],
    )
    fake_backend = FakeOCRBackend()
    captured: dict[str, object] = {}

    def _fake_run_generate(*args, **kwargs):
        captured["ocr_backend"] = kwargs.get("ocr_backend")
        captured["inspect_only"] = kwargs.get("inspect_only")
        return {
            "strategy": "bitmap_jp_ocr_mt",
            "inspect_only": True,
            "planned_output_srt": str(tmp_path / "outbox" / "dummy.en.srt"),
            "planned_qc_json": str(tmp_path / "outbox" / "dummy.en.qc.json"),
            "selection_report": {"sources_evaluated": []},
            "registry_run_id": None,
        }

    monkeypatch.setattr(main, "check_ffmpeg_available", lambda: True)
    monkeypatch.setattr(main, "inspect_media", lambda _: media)
    monkeypatch.setattr(main, "create_ocr_backend", lambda _cfg: fake_backend)
    monkeypatch.setattr(main, "run_generate", _fake_run_generate)

    argv = [
        "main.py",
        str(media.path),
        "--mode",
        "generate",
        "--inspect-only",
    ]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as exc:
        main.main()

    assert exc.value.code == 0
    assert captured["ocr_backend"] is fake_backend
    assert captured["inspect_only"] is True
