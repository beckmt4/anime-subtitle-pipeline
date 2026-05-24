from __future__ import annotations

from pathlib import Path

from core.runtime.config import Config
from core.ocr import OCRBackend, create_backend
from core.policy import PolicyEngine
from core.media import MediaInfo, SubtitleStream
from core.subtitles import Segment, SubtitleCandidate
import core.runtime.orchestrator as orch
from subtitle_qc import run_qc
from core.extract.subtitle_utils import extract_subtitle_track


class DummyOCRBackend(OCRBackend):
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
            segments=[
                Segment(0.0, 1.0, "line 1", meta={"ocr_confidence": 0.55}),
                Segment(1.0, 2.0, "line 2", meta={"ocr_confidence": 0.90}),
            ],
            meta={},
        )


def _media_with_bitmap_only() -> MediaInfo:
    return MediaInfo(
        path=Path("dummy.mkv"),
        format_name="matroska",
        duration=120.0,
        audio_streams=[],
        subtitle_streams=[
            SubtitleStream(index=3, codec="pgssub", language="ja", raw_language="jpn", is_bitmap=True),
        ],
    )


def test_extract_bitmap_track_uses_ocr_backend(monkeypatch, tmp_path):
    video = tmp_path / "video.mkv"
    video.write_bytes(b"fake")
    media = MediaInfo(
        path=video,
        format_name="matroska",
        duration=10.0,
        subtitle_streams=[
            SubtitleStream(index=2, codec="pgssub", language="ja", raw_language="jpn", is_bitmap=True),
        ],
    )
    monkeypatch.setattr("core.extract.subtitle_utils.inspect_media", lambda _: media)

    cand = extract_subtitle_track(video, 2, "ja", ocr_backend=DummyOCRBackend())

    assert cand.meta["ocr"]["segment_count"] == 2
    assert cand.meta["ocr"]["low_confidence_segment_count"] == 1
    assert cand.segments[0].meta["ocr_confidence"] == 0.55


def test_run_generate_uses_sidecar_and_reports_bitmap_candidate(monkeypatch):
    cfg = Config()
    media = _media_with_bitmap_only()
    media.path = Path("dummy.mkv")

    sidecar = SubtitleCandidate(
        id="sidecar_en_dummy",
        language="en",
        source="sidecar",
        origin_stream="sidecar:dummy.en.srt",
        segments=[Segment(0.0, 1.0, "hello")],
        meta={"file": "dummy.en.srt"},
    )

    monkeypatch.setattr(orch, "discover_sidecar_subtitles", lambda _: [sidecar])
    monkeypatch.setattr(
        orch,
        "write_candidate_srt",
        lambda candidate, output_path, cfg: Path(output_path).write_text("1\n00:00:00,000 --> 00:00:01,000\nok\n", encoding="utf-8"),
    )
    monkeypatch.setattr(
        orch,
        "run_qc",
        lambda *args, **kwargs: {
            "parsed_ok": True,
            "cue_count": 1,
            "violations": [],
            "error_count": 0,
            "warning_count": 0,
            "pass_qc": True,
        },
    )

    meta = orch.run_generate(media, cfg, no_llm=True, inspect_only=False)
    report = meta["selection_report"]
    statuses = {s["source"]: s["status"] for s in report["sources_evaluated"]}

    assert meta["strategy"] == "sidecar_en"
    assert statuses["sidecar_en"] == "selected"
    assert "bitmap_jp_ocr_mt" in statuses


def test_qc_and_policy_route_ocr_heavy_results_to_review(tmp_path):
    srt = tmp_path / "sample.srt"
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\nA\n\n2\n00:00:01,000 --> 00:00:02,000\nB\n",
        encoding="utf-8",
    )
    candidate = SubtitleCandidate(
        id="bitmap_en",
        language="en",
        source="embedded",
        origin_stream="sub:0",
        segments=[
            Segment(0.0, 1.0, "A", meta={"ocr_confidence": 0.40}),
            Segment(1.0, 2.0, "B", meta={"ocr_confidence": 0.45}),
        ],
        meta={},
    )
    qc = run_qc(srt, candidate=candidate)
    score = orch.score_candidate("bitmap_en_ocr", candidate, qc)
    engine = PolicyEngine()

    decision = engine.route(score, {"review_recommended": False, "review_reason": None})

    assert score["ocr_warning_density"] == 1.0
    assert decision["decision"] == "review"
    assert "ocr_warning_density" in decision["triggered_by"]


def test_create_backend_loads_plugin_from_config():
    cfg = Config()
    cfg._config.setdefault("ocr", {})
    cfg._config["ocr"].update({
        "enabled": True,
        "backend": "tests.test_ocr_sidecar_support:DummyOCRBackend",
        "language_models": {"ja": "ja_model"},
    })

    backend = create_backend(cfg)

    assert backend is not None
    assert isinstance(backend, OCRBackend)
    assert backend.__class__.__name__ == "DummyOCRBackend"
